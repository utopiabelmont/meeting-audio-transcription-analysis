from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence, TextIO


SKILL_DIR = Path(__file__).resolve().parent.parent
LOCAL_BACKEND_CONFIG = SKILL_DIR / "local_backend.json"
ANALYSIS_SCRIPT = SKILL_DIR / "scripts" / "analyze_transcript.py"
VALIDATOR_SCRIPT = SKILL_DIR / "scripts" / "validate_skill_outputs.py"

BACKEND_CONFIG_FIELDS = {
    "project_root",
    "app_dir",
    "pyannote_python",
    "ffprobe",
}
BACKEND_ENVIRONMENT_VARIABLES = {
    "project_root": "VTT_PLUS_ANALYSIS_ROOT",
    "app_dir": "VTT_PLUS_APP_DIR",
    "pyannote_python": "VTT_PLUS_PYANNOTE_PYTHON",
    "ffprobe": "VTT_PLUS_FFPROBE",
}

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".mp4", ".mov", ".mkv"}
SUPPORTED_OUTPUT_LANGUAGE_ALIASES = {
    "chinese",
    "zh",
    "zh-cn",
    "中文",
    "english",
    "en",
    "en-us",
    "en-gb",
    "英语",
    "japanese",
    "ja",
    "ja-jp",
    "日语",
    "日本語",
}
FIXED_LANGUAGE = "auto"
FIXED_LANGUAGE_STRATEGY = "per-chunk"
FIXED_CHUNK_DURATION = 180
FIXED_CHUNK_OVERLAP = 12
STATE_SCHEMA_VERSION = 1

RAW_OUTPUT_NAMES = (
    "transcript_final.json",
    "transcript_final.txt",
    "transcript_final.vtt",
)
ANALYSIS_OUTPUT_NAMES = (
    "meeting_analysis.json",
    "meeting_analysis.md",
    "meeting_timeline.md",
    "meeting_source_index.json",
)


class SkillInputError(ValueError):
    pass


@dataclass(frozen=True)
class BackendPaths:
    project_root: Path
    app_dir: Path
    pyannote_python: Path
    ffprobe: Path
    sources: dict[str, str]
    local_config_path: Path

    @property
    def pipeline_script(self) -> Path:
        return self.app_dir / "run_pipeline_complete.py"

    @property
    def generate_vtt_script(self) -> Path:
        return self.app_dir / "generate_vtt.py"

    @property
    def base_config(self) -> Path:
        return self.app_dir / "config" / "transcript_cleaning_base.json"

    @property
    def optical_config(self) -> Path:
        return self.app_dir / "config" / "glossaries" / "optical_edge_ml.json"

    @property
    def jobs_dir(self) -> Path:
        return self.app_dir / "jobs"

    @property
    def state_dir(self) -> Path:
        return self.jobs_dir / ".meeting_skill_state"

    def as_record(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root),
            "app_dir": str(self.app_dir),
            "pyannote_python": str(self.pyannote_python),
            "ffprobe": str(self.ffprobe),
            "sources": dict(self.sources),
            "local_config_path": str(self.local_config_path),
            "local_config_present": self.local_config_path.is_file(),
        }


def normalize_configured_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def configured_path(
    values: Mapping[str, Any],
    key: str,
    *,
    base_dir: Path,
    source_label: str,
) -> Path | None:
    if key not in values:
        return None
    value = values[key]
    if not isinstance(value, str) or not value.strip():
        raise SkillInputError(
            f"{source_label}中的{key}必须是非空路径字符串。"
        )
    return normalize_configured_path(value.strip(), base_dir=base_dir)


def load_local_backend_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if not path.is_file():
        raise SkillInputError(f"本机后端配置不是普通文件：{path}")
    try:
        value = load_json_object(path)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as error:
        raise SkillInputError(
            f"本机后端配置不是有效UTF-8 JSON：{path}；{error}"
        ) from error
    unsupported = sorted(set(value) - BACKEND_CONFIG_FIELDS)
    if unsupported:
        raise SkillInputError(
            f"本机后端配置包含不支持的字段：{unsupported}；"
            f"允许字段：{sorted(BACKEND_CONFIG_FIELDS)}"
        )
    return value


def resolve_backend_paths(
    *,
    environ: Mapping[str, str] | None = None,
    config_path: Path | None = None,
) -> BackendPaths:
    environment = os.environ if environ is None else environ
    local_path = (
        LOCAL_BACKEND_CONFIG if config_path is None else config_path
    ).expanduser().resolve()
    local_values = load_local_backend_config(local_path)

    environment_values: dict[str, str] = {}
    for field, variable in BACKEND_ENVIRONMENT_VARIABLES.items():
        if variable not in environment:
            continue
        value = environment[variable]
        if not isinstance(value, str) or not value.strip():
            raise SkillInputError(f"环境变量{variable}不能是空路径。")
        environment_values[field] = value.strip()

    environment_paths = {
        field: configured_path(
            environment_values,
            field,
            base_dir=Path.cwd(),
            source_label=BACKEND_ENVIRONMENT_VARIABLES[field],
        )
        for field in BACKEND_CONFIG_FIELDS
    }
    local_paths = {
        field: configured_path(
            local_values,
            field,
            base_dir=local_path.parent,
            source_label=str(local_path),
        )
        for field in BACKEND_CONFIG_FIELDS
    }

    environment_root = environment_paths["project_root"]
    local_root = local_paths["project_root"]
    environment_app = environment_paths["app_dir"]
    local_app = local_paths["app_dir"]

    if environment_root is not None:
        project_root = environment_root
        project_root_source = "env:VTT_PLUS_ANALYSIS_ROOT"
    elif local_root is not None:
        project_root = local_root
        project_root_source = "local_backend.json:project_root"
    elif environment_app is not None:
        project_root = environment_app.parent
        project_root_source = "derived:VTT_PLUS_APP_DIR.parent"
    elif local_app is not None:
        project_root = local_app.parent
        project_root_source = "derived:local_backend.json:app_dir.parent"
    else:
        raise SkillInputError(
            "未配置本地转录后端。请设置VTT_PLUS_ANALYSIS_ROOT，或设置"
            "VTT_PLUS_APP_DIR及其他专用环境变量，或在Skill根创建"
            f"本机私有配置：{local_path}"
        )

    if environment_app is not None:
        app_dir = environment_app
        app_source = "env:VTT_PLUS_APP_DIR"
    elif local_app is not None:
        app_dir = local_app
        app_source = "local_backend.json:app_dir"
    else:
        app_dir = (project_root / "app").resolve()
        app_source = "derived:project_root/app"

    environment_python = environment_paths["pyannote_python"]
    local_python = local_paths["pyannote_python"]
    if environment_python is not None:
        pyannote_python = environment_python
        python_source = "env:VTT_PLUS_PYANNOTE_PYTHON"
    elif local_python is not None:
        pyannote_python = local_python
        python_source = "local_backend.json:pyannote_python"
    else:
        pyannote_python = (
            project_root / "conda" / "envs" / "pyannote" / "python.exe"
        ).resolve()
        python_source = "derived:project_root/conda/envs/pyannote"

    environment_ffprobe = environment_paths["ffprobe"]
    local_ffprobe = local_paths["ffprobe"]
    if environment_ffprobe is not None:
        ffprobe = environment_ffprobe
        ffprobe_source = "env:VTT_PLUS_FFPROBE"
    elif local_ffprobe is not None:
        ffprobe = local_ffprobe
        ffprobe_source = "local_backend.json:ffprobe"
    else:
        ffprobe = (
            project_root
            / "conda"
            / "envs"
            / "pyannote"
            / "Library"
            / "bin"
            / "ffprobe.exe"
        ).resolve()
        ffprobe_source = "derived:project_root/conda/envs/pyannote"

    return BackendPaths(
        project_root=project_root,
        app_dir=app_dir,
        pyannote_python=pyannote_python,
        ffprobe=ffprobe,
        sources={
            "project_root": project_root_source,
            "app_dir": app_source,
            "pyannote_python": python_source,
            "ffprobe": ffprobe_source,
        },
        local_config_path=local_path,
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise TypeError(f"JSON顶层必须是对象：{path}")
    return value


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as file:
            file.write(value)
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def write_terminal(stream: TextIO, text: str) -> None:
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        stream.write(
            text.encode(encoding, errors="replace").decode(
                encoding, errors="replace"
            )
        )


def emit(log_file: TextIO | None, message: str, *, error: bool = False) -> None:
    text = message if message.endswith("\n") else message + "\n"
    stream = sys.stderr if error else sys.stdout
    write_terminal(stream, text)
    stream.flush()
    if log_file is not None:
        log_file.write(text)
        log_file.flush()


class SkillConsoleLog:
    def __init__(self, job_dir: Path, append: bool) -> None:
        self.final_path = job_dir / "meeting_skill_console.log"
        jobs_dir = job_dir.parent
        jobs_dir.mkdir(parents=True, exist_ok=True)
        if job_dir.is_dir():
            self.current_path = self.final_path
            self.file = self.final_path.open(
                "a" if append else "w", encoding="utf-8", newline="\n"
            )
        else:
            self.current_path = jobs_dir / (
                f".{job_dir.name}.meeting_skill_console.{os.getpid()}.tmp"
            )
            self.file = self.current_path.open(
                "a" if append else "w", encoding="utf-8", newline="\n"
            )

        marker = "RESUME/SKIP" if append else "NEW"
        self.file.write(
            "\n"
            + "=" * 20
            + f" SKILL {marker} RUN {datetime.now().isoformat(timespec='seconds')} "
            + "=" * 20
            + "\n"
        )
        self.file.flush()

    def close(self) -> None:
        self.file.flush()
        self.file.close()
        if self.current_path == self.final_path:
            return
        self.final_path.parent.mkdir(parents=True, exist_ok=True)
        if self.final_path.exists():
            with self.current_path.open("r", encoding="utf-8") as source:
                with self.final_path.open(
                    "a", encoding="utf-8", newline="\n"
                ) as target:
                    shutil.copyfileobj(source, target)
            self.current_path.unlink()
        else:
            self.current_path.replace(self.final_path)


def safe_job_name(value: str) -> str:
    value = value.strip()
    value = re.sub(r'[<>:"/\\|?*]+', "_", value)
    value = re.sub(r"\s+", "_", value)
    value = value.strip(" ._")
    return value or "transcription"


def explicit_job_name_is_safe(value: str) -> bool:
    if safe_job_name(value) != value or len(value) > 120:
        return False
    device_name = value.split(".", 1)[0].casefold()
    reserved = {"con", "prn", "aux", "nul", "clock$"}
    reserved.update(f"com{index}" for index in range(1, 10))
    reserved.update(f"lpt{index}" for index in range(1, 10))
    return device_name not in reserved


def automatic_job_name(input_path: Path, sha256: str) -> str:
    stem = safe_job_name(input_path.stem)[:64].rstrip(" ._") or "recording"
    return safe_job_name(f"{stem}_{date.today():%Y%m%d}_{sha256[:12]}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while block := file.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def validate_input_path(value: Path) -> tuple[Path, os.stat_result]:
    path = value.expanduser().resolve()
    if not path.is_file():
        raise SkillInputError(f"输入文件不存在或不是普通文件：{path}")
    if path.suffix.casefold() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise SkillInputError(
            f"不支持的输入扩展名{path.suffix!r}；支持：{supported}"
        )
    stat = path.stat()
    if stat.st_size <= 0:
        raise SkillInputError(f"输入文件为空：{path}")
    return path, stat


def validate_output_language(value: str | None) -> None:
    if value is None or not value.strip():
        return
    if value.strip().casefold() not in SUPPORTED_OUTPUT_LANGUAGE_ALIASES:
        raise SkillInputError(
            f"不支持的output-language：{value!r}；"
            "支持Chinese/English/Japanese、zh/en/ja及现有地区/中日文别名。"
        )


def probe_media(path: Path, ffprobe_exe: Path | None = None) -> dict[str, Any]:
    if ffprobe_exe is None:
        ffprobe_exe = resolve_backend_paths().ffprobe
    command = [
        str(ffprobe_exe),
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        (
            "format=duration,size,format_name:"
            "stream=index,codec_name,codec_type,sample_rate,channels,duration"
        ),
        "-of",
        "json",
        str(path),
    ]
    try:
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except OSError as error:
        raise SkillInputError(f"无法运行ffprobe：{error}") from error
    except subprocess.TimeoutExpired as error:
        raise SkillInputError("ffprobe在120秒内没有完成。") from error

    if process.returncode != 0:
        detail = process.stderr.strip() or "无详细错误"
        raise SkillInputError(
            f"ffprobe无法读取输入文件（返回码{process.returncode}）：{detail}"
        )
    try:
        probe = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise SkillInputError("ffprobe没有返回有效JSON。") from error
    if not isinstance(probe, dict):
        raise SkillInputError("ffprobe JSON结构无效。")

    streams = probe.get("streams")
    if not isinstance(streams, list) or not streams:
        raise SkillInputError("输入文件不包含可读取的音轨。")
    stream = streams[0]
    if not isinstance(stream, dict) or stream.get("codec_type") != "audio":
        raise SkillInputError("输入文件的第一条所选流不是音轨。")

    format_info = probe.get("format")
    if not isinstance(format_info, dict):
        format_info = {}
    duration_value = format_info.get("duration", stream.get("duration"))
    try:
        duration = float(duration_value)
        sample_rate = int(stream.get("sample_rate"))
        channels = int(stream.get("channels"))
    except (TypeError, ValueError) as error:
        raise SkillInputError("ffprobe未返回有效的时长、采样率或声道数。") from error
    if not math.isfinite(duration) or duration <= 0.0:
        raise SkillInputError("输入媒体时长必须大于0秒。")
    if sample_rate <= 0 or channels <= 0:
        raise SkillInputError("输入音轨采样率或声道数无效。")

    reported_size = format_info.get("size")
    try:
        reported_size_bytes = int(reported_size)
    except (TypeError, ValueError):
        reported_size_bytes = path.stat().st_size

    return {
        "duration_seconds": round(duration, 6),
        "audio_stream_index": int(stream.get("index", 0)),
        "codec_name": stream.get("codec_name"),
        "sample_rate": sample_rate,
        "channels": channels,
        "format_name": format_info.get("format_name"),
        "reported_size_bytes": reported_size_bytes,
    }


def validate_json_config(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise SkillInputError(f"术语表配置不存在：{resolved}")
    try:
        load_json_object(resolved)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as error:
        raise SkillInputError(f"术语表不是有效UTF-8 JSON：{resolved}；{error}") from error
    return resolved


def is_optical_domain(domain: str | None) -> bool:
    if not domain:
        return False
    normalized = re.sub(r"[_-]+", " ", domain.casefold()).strip()
    phrases = (
        "optical",
        "edge detection",
        "machine learning",
        "光学",
        "边缘检测",
        "邊緣檢測",
        "機械学習",
        "机器学习",
    )
    return any(phrase in normalized for phrase in phrases)


def resolve_project_configs(
    domain: str | None,
    glossary_values: Sequence[Path],
    *,
    optical_config: Path,
) -> list[Path]:
    candidates: list[Path] = []
    if is_optical_domain(domain):
        candidates.append(optical_config)
    candidates.extend(glossary_values)

    result: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = validate_json_config(candidate)
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


def config_descriptors(paths: Sequence[Path]) -> list[dict[str, str]]:
    return [{"path": str(path), "sha256": sha256_file(path)} for path in paths]


def state_path_for_job(job_name: str, state_dir: Path) -> Path:
    return state_dir / f"{job_name}.json"


def load_skill_state(job_dir: Path, external_path: Path) -> dict[str, Any] | None:
    candidates = (job_dir / "meeting_skill_run.json", external_path)
    for path in candidates:
        if path.is_file():
            try:
                return load_json_object(path)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as error:
                raise SkillInputError(f"Skill状态文件无效：{path}；{error}") from error
    return None


def state_input_hash(state: dict[str, Any]) -> str | None:
    value = state.get("input")
    if isinstance(value, dict) and isinstance(value.get("sha256"), str):
        return value["sha256"]
    return None


def state_expected_speakers(state: dict[str, Any]) -> int | None:
    settings = state.get("backend_settings")
    if isinstance(settings, dict):
        value = settings.get("expected_speakers")
        if value is None or isinstance(value, int):
            return value
    return None


def rebind_pipeline_state_input(
    job_dir: Path, input_path: Path, input_stat: os.stat_result
) -> dict[str, Any] | None:
    """同一SHA文件换了附件路径时，更新backend的非哈希身份字段。"""
    path = job_dir / "pipeline_state.json"
    if not path.is_file():
        return None
    value = load_json_object(path)
    old_identity = value.get("input_audio")
    new_identity = {
        "path": str(input_path),
        "size_bytes": input_stat.st_size,
        "modified_time_ns": input_stat.st_mtime_ns,
    }
    if old_identity == new_identity:
        return None
    value["input_audio"] = new_identity
    atomic_write_json(path, value)
    return {"old": old_identity, "new": new_identity, "reason": "sha256_match"}


def valid_json_with_list(path: Path, list_key: str) -> bool:
    try:
        value = load_json_object(path)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return False
    return isinstance(value.get(list_key), list)


def validate_transcript_final_outputs(job_dir: Path) -> list[str]:
    """检查可用于安全降级的原始转录三件套，不依赖失败manifest。"""
    errors: list[str] = []
    json_path = job_dir / "transcript_final.json"
    txt_path = job_dir / "transcript_final.txt"
    vtt_path = job_dir / "transcript_final.vtt"

    try:
        transcript = load_json_object(json_path)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as error:
        errors.append(f"JSON不可读取：{json_path}；{error}")
    else:
        cues = transcript.get("cues")
        if not isinstance(cues, list) or not cues:
            errors.append(f"无可分析的非空cues数组：{json_path}")

    for label, path in (("TXT", txt_path), ("VTT", vtt_path)):
        if not path.is_file():
            errors.append(f"缺少{label}：{path}")
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as error:
            errors.append(f"{label}不可读取：{path}；{error}")
            continue
        if label == "TXT" and not text.strip():
            errors.append(f"TXT内容为空：{path}")
        if label == "VTT" and not text.lstrip("\ufeff").startswith("WEBVTT"):
            errors.append(f"VTT缺少WEBVTT头：{path}")

    return errors


def final_output_paths(job_dir: Path) -> tuple[Path, Path, Path]:
    return (
        job_dir / RAW_OUTPUT_NAMES[0],
        job_dir / RAW_OUTPUT_NAMES[1],
        job_dir / RAW_OUTPUT_NAMES[2],
    )


def load_generate_vtt_helpers(generate_vtt_script: Path) -> tuple[Any, Any]:
    spec = importlib.util.spec_from_file_location(
        "meeting_skill_generate_vtt", generate_vtt_script
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载现有字幕生成模块：{generate_vtt_script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    build_cues = getattr(module, "build_cues", None)
    format_timestamp = getattr(module, "format_vtt_timestamp", None)
    if not callable(build_cues) or not callable(format_timestamp):
        raise RuntimeError(
            "现有generate_vtt.py缺少build_cues或format_vtt_timestamp。"
        )
    return build_cues, format_timestamp


def validated_word_timestamp_source(
    path: Path,
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    try:
        source = load_json_object(path)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as error:
        raise RuntimeError(f"word_timestamps.json无效：{path}；{error}") from error

    transcript = source.get("transcript")
    if not isinstance(transcript, str) or not transcript.strip():
        raise RuntimeError("word_timestamps.json的transcript必须是非空字符串。")
    values = source.get("word_timestamps")
    if not isinstance(values, list) or not values:
        raise RuntimeError("word_timestamps.json必须包含非空word_timestamps数组。")

    result: list[dict[str, Any]] = []
    previous_start = -math.inf
    previous_end = -math.inf
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise RuntimeError(f"word_timestamps[{index}]不是对象。")
        text = item.get("text")
        start_value = item.get("start_time")
        end_value = item.get("end_time")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError(f"word_timestamps[{index}].text为空或无效。")
        if isinstance(start_value, bool) or isinstance(end_value, bool):
            raise RuntimeError(f"word_timestamps[{index}]时间戳不能是布尔值。")
        try:
            start_time = float(start_value)
            end_time = float(end_value)
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                f"word_timestamps[{index}]时间戳不是数字。"
            ) from error
        if not math.isfinite(start_time) or not math.isfinite(end_time):
            raise RuntimeError(f"word_timestamps[{index}]时间戳不是有限值。")
        if start_time < 0.0 or end_time < start_time:
            raise RuntimeError(f"word_timestamps[{index}]时间范围无效。")
        if start_time < previous_start or end_time < previous_end:
            raise RuntimeError(f"word_timestamps[{index}]时间戳不是单调不下降。")
        previous_start = start_time
        previous_end = end_time
        result.append(
            {
                **item,
                "text": text.strip(),
                "start_time": start_time,
                "end_time": end_time,
            }
        )
    return source, transcript.strip(), result


def generate_unknown_final_from_word_timestamps(
    job_dir: Path,
    generate_vtt_script: Path,
) -> dict[str, Any]:
    """仅在final三件套全不存在时，从现有对齐结果生成UNKNOWN转录。"""
    output_paths = final_output_paths(job_dir)
    present = [path for path in output_paths if path.exists()]
    if present:
        raise RuntimeError(
            "检测到已有或部分transcript_final文件，拒绝覆盖："
            + "，".join(str(path) for path in present)
        )

    source_path = job_dir / "word_timestamps.json"
    source, transcript, word_timestamps = validated_word_timestamp_source(
        source_path
    )
    build_cues, format_timestamp = load_generate_vtt_helpers(generate_vtt_script)
    generated = build_cues(
        transcript=transcript,
        word_timestamps=word_timestamps,
    )
    if not isinstance(generated, list) or not generated:
        raise RuntimeError("generate_vtt.build_cues没有生成可用字幕。")

    cues: list[dict[str, Any]] = []
    for index, cue in enumerate(generated):
        if not isinstance(cue, dict):
            raise RuntimeError(f"generate_vtt.build_cues结果[{index}]不是对象。")
        try:
            start_time = float(cue["start_time"])
            end_time = float(cue["end_time"])
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(
                f"generate_vtt.build_cues结果[{index}]时间无效。"
            ) from error
        text = str(cue.get("text", "")).strip()
        if not text or not math.isfinite(start_time) or not math.isfinite(end_time):
            raise RuntimeError(
                f"generate_vtt.build_cues结果[{index}]内容或时间无效。"
            )
        cues.append(
            {
                "start_time": start_time,
                "end_time": end_time,
                "speaker": "UNKNOWN",
                "speaker_id": "UNKNOWN",
                "text": text,
            }
        )

    final_json = {
        "audio": source.get("audio"),
        "language": source.get("language"),
        "anonymous_speakers": True,
        "speaker_map": {},
        "generated_unknown_from_word_timestamps": True,
        "fallback_source": str(source_path),
        "speaker_attribution": "UNKNOWN",
        "processing": {
            "fallback_source": "word_timestamps.json",
            "generated_unknown_from_word_timestamps": True,
            "speaker_assignment": "UNKNOWN",
            "source_word_count": len(word_timestamps),
            "cue_count": len(cues),
        },
        "cues": cues,
    }
    txt_text = "".join(
        f"[{format_timestamp(cue['start_time'])}] UNKNOWN：{cue['text']}\n"
        for cue in cues
    )
    vtt_lines = [
        "WEBVTT",
        "",
        "NOTE Generated from word_timestamps.json; speaker attribution UNKNOWN",
        "",
    ]
    for number, cue in enumerate(cues, start=1):
        vtt_lines.extend(
            [
                str(number),
                f"{format_timestamp(cue['start_time'])} --> "
                f"{format_timestamp(cue['end_time'])}",
                f"<v UNKNOWN>UNKNOWN: {cue['text']}</v>",
                "",
            ]
        )
    vtt_text = "\n".join(vtt_lines)

    if any(path.exists() for path in output_paths):
        raise RuntimeError("生成前检测到transcript_final文件，拒绝覆盖。")
    atomic_write_json(output_paths[0], final_json)
    atomic_write_text(output_paths[1], txt_text)
    atomic_write_text(output_paths[2], vtt_text)
    return {
        "source": str(source_path),
        "word_count": len(word_timestamps),
        "cue_count": len(cues),
        "speaker": "UNKNOWN",
        "outputs": [str(path) for path in output_paths],
    }


def prepare_degraded_postprocessing_manifest(
    job_dir: Path,
    *,
    backend_return_code: int,
    reason: str,
    fallback_source: str,
    generated_unknown_from_word_timestamps: bool,
) -> dict[str, Any]:
    """保留主流水线失败信息，并允许统一入口只运行清理与复核。"""
    manifest_path = job_dir / "pipeline_manifest.json"
    try:
        manifest = load_json_object(manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        manifest = {
            "job_name": job_dir.name,
            "job_dir": str(job_dir),
        }

    complete = manifest.get("complete_pipeline")
    if not isinstance(complete, dict):
        complete = {}
        manifest["complete_pipeline"] = complete
    original = {
        "manifest_status": manifest.get("status"),
        "main_pipeline_status": complete.get("main_pipeline_status"),
        "errors": complete.get("errors"),
    }
    fallback = {
        "status": "pending_postprocessing",
        "reason": reason,
        "backend_return_code": backend_return_code,
        "fallback_source": fallback_source,
        "generated_unknown_from_word_timestamps": (
            generated_unknown_from_word_timestamps
        ),
        "speaker_attribution_reliable": False,
        "prepared_at": utc_now(),
        "original_failure": original,
    }
    manifest["status"] = "completed_with_warnings"
    complete["status"] = "completed_with_warnings"
    complete["main_pipeline_status"] = "degraded_partial_transcript"
    manifest["meeting_skill_degraded_fallback"] = fallback
    atomic_write_json(manifest_path, manifest)
    return fallback


def finish_degraded_postprocessing_manifest(
    job_dir: Path,
    *,
    backend_return_code: int,
    reason: str,
    fallback_source: str,
    generated_unknown_from_word_timestamps: bool,
) -> None:
    manifest_path = job_dir / "pipeline_manifest.json"
    manifest = load_json_object(manifest_path)
    complete = manifest.get("complete_pipeline")
    if not isinstance(complete, dict):
        complete = {}
        manifest["complete_pipeline"] = complete
    fallback = manifest.get("meeting_skill_degraded_fallback")
    if not isinstance(fallback, dict):
        fallback = {}
        manifest["meeting_skill_degraded_fallback"] = fallback
    fallback.update(
        {
            "status": "completed",
            "reason": reason,
            "backend_return_code": backend_return_code,
            "fallback_source": fallback_source,
            "generated_unknown_from_word_timestamps": (
                generated_unknown_from_word_timestamps
            ),
            "speaker_attribution_reliable": False,
            "completed_at": utc_now(),
        }
    )
    manifest["status"] = "completed_with_warnings"
    complete["status"] = "completed_with_warnings"
    complete["main_pipeline_status"] = "degraded_partial_transcript"
    atomic_write_json(manifest_path, manifest)


def main_pipeline_is_complete(job_dir: Path) -> bool:
    if any(not (job_dir / name).is_file() for name in RAW_OUTPUT_NAMES):
        return False
    if not valid_json_with_list(job_dir / "transcript_final.json", "cues"):
        return False
    manifest_path = job_dir / "pipeline_manifest.json"
    try:
        manifest = load_json_object(manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return False
    if str(manifest.get("status", "")).casefold() == "failed":
        return False
    complete = manifest.get("complete_pipeline")
    if isinstance(complete, dict) and str(
        complete.get("main_pipeline_status", "")
    ).casefold() == "failed":
        return False
    manifest_status = str(manifest.get("status", "")).casefold()
    if manifest_status == "completed":
        return True
    fallback = manifest.get("meeting_skill_degraded_fallback")
    return (
        manifest_status == "completed_with_warnings"
        and isinstance(fallback, dict)
        and fallback.get("status") == "completed"
    )


def postprocessing_is_complete(job_dir: Path) -> bool:
    try:
        review = load_json_object(job_dir / "transcript_review_package.json")
        manifest = load_json_object(job_dir / "pipeline_manifest.json")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return False
    if not isinstance(review.get("summary"), dict):
        return False
    complete = manifest.get("complete_pipeline")
    if not isinstance(complete, dict):
        return False
    return (
        complete.get("review_package_status") == "completed"
        and complete.get("status") in {"completed", "completed_with_warnings"}
    )


def select_analysis_transcript(job_dir: Path) -> tuple[Path, bool]:
    """按manifest选择cleaned；清理失败时安全降级到final。"""
    manifest = load_json_object(job_dir / "pipeline_manifest.json")
    complete = manifest.get("complete_pipeline")
    cleaning_status = (
        complete.get("text_cleaning_status")
        if isinstance(complete, dict)
        else None
    )
    cleaned_path = job_dir / "transcript_cleaned.json"
    if cleaning_status == "completed" and valid_json_with_list(
        cleaned_path, "cues"
    ):
        return cleaned_path, False
    final_path = job_dir / "transcript_final.json"
    if valid_json_with_list(final_path, "cues"):
        return final_path, True
    raise RuntimeError("cleaned和final转录均不可用于分析。")


def run_streaming_command(
    command: Sequence[str], cwd: Path, log_file: TextIO, title: str
) -> tuple[int, float]:
    emit(log_file, "=" * 72)
    emit(log_file, title)
    emit(log_file, "=" * 72)
    emit(log_file, "COMMAND:")
    emit(log_file, subprocess.list2cmdline(list(command)))
    emit(log_file, "")
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    started = time.perf_counter()
    process = subprocess.Popen(
        list(command),
        cwd=str(cwd),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None
    try:
        for line in process.stdout:
            write_terminal(sys.stdout, line)
            sys.stdout.flush()
            log_file.write(line)
            log_file.flush()
        return_code = process.wait()
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        raise
    finally:
        process.stdout.close()
    elapsed = time.perf_counter() - started
    emit(log_file, "")
    emit(log_file, f"RETURN CODE: {return_code}")
    emit(log_file, f"ELAPSED SECONDS: {elapsed:.3f}")
    emit(log_file, "")
    return return_code, elapsed


def build_backend_command(
    *,
    backend: BackendPaths,
    job_dir: Path,
    input_path: Path,
    job_name: str,
    expected_speakers: int | None,
    project_configs: Sequence[Path],
    action: str,
) -> list[str]:
    command = [
        str(backend.pyannote_python),
        "-X",
        "utf8",
        str(backend.pipeline_script),
        "--job-dir",
        str(job_dir),
        "--pipeline-python",
        str(backend.pyannote_python),
        "--postprocess-python",
        str(backend.pyannote_python),
        "--review-python",
        str(backend.pyannote_python),
        "--pipeline-cwd",
        str(backend.app_dir),
        "--base-config",
        str(backend.base_config),
        "--input-name",
        "transcript_final.json",
        "--clean-transcript",
        "--build-review-package",
    ]
    for path in project_configs:
        command.extend(["--project-config", str(path)])

    if action == "postprocess_existing":
        command.append("--skip-pipeline")
        return command

    command.extend(
        [
            "--",
            str(input_path),
            "--job-name",
            job_name,
            "--language",
            FIXED_LANGUAGE,
            "--language-strategy",
            FIXED_LANGUAGE_STRATEGY,
            "--chunk-duration",
            str(FIXED_CHUNK_DURATION),
            "--chunk-overlap",
            str(FIXED_CHUNK_OVERLAP),
            "--keep-chunks",
        ]
    )
    if expected_speakers is not None:
        command.extend(["--num-speakers", str(expected_speakers)])
    if action == "resume":
        command.append("--resume")
    return command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="调用本地多人转录后端并生成会议分析。",
        allow_abbrev=False,
    )
    parser.add_argument("--input", required=True, type=Path, help="音频或视频文件。")
    parser.add_argument("--job-name", help="可选安全Job名称；默认由文件名、日期和SHA生成。")
    parser.add_argument("--resume", action="store_true", help="恢复同名未完成Job。")
    parser.add_argument("--expected-speakers", type=int, help="预计且固定的说话人数。")
    parser.add_argument("--meeting-title")
    parser.add_argument("--meeting-date")
    parser.add_argument("--meeting-topic")
    parser.add_argument("--languages", action="append", default=[])
    parser.add_argument("--domain")
    parser.add_argument(
        "--glossary", action="append", default=[], type=Path, help="附加清理JSON，可重复。"
    )
    parser.add_argument("--known-participant", action="append", default=[])
    parser.add_argument("--user-speaker-hint")
    parser.add_argument("--output-language")
    parser.add_argument("--question", action="append", default=[])
    return parser


def required_dependencies(backend: BackendPaths) -> dict[str, Path]:
    return {
        "pyannote Python": backend.pyannote_python,
        "ffprobe": backend.ffprobe,
        "统一流水线": backend.pipeline_script,
        "现有字幕生成模块": backend.generate_vtt_script,
        "通用清理配置": backend.base_config,
        "分析脚本": ANALYSIS_SCRIPT,
        "输出校验脚本": VALIDATOR_SCRIPT,
    }


def validate_backend_paths(backend: BackendPaths) -> None:
    errors: list[str] = []
    if not backend.app_dir.is_dir():
        errors.append(f"后端app目录不存在：{backend.app_dir}")
    errors.extend(
        f"{label}不存在：{path}"
        for label, path in required_dependencies(backend).items()
        if not path.is_file()
    )
    if errors:
        raise SkillInputError(
            "后端配置验证失败："
            + "；".join(errors)
            + "。请设置VTT_PLUS_ANALYSIS_ROOT，或设置对应的"
            "VTT_PLUS_APP_DIR/VTT_PLUS_PYANNOTE_PYTHON/VTT_PLUS_FFPROBE，"
            f"或在Skill根创建本机私有配置：{backend.local_config_path}"
        )


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log: SkillConsoleLog | None = None
    state: dict[str, Any] | None = None
    external_state_path: Path | None = None
    job_dir: Path | None = None
    backend: BackendPaths | None = None

    try:
        if args.expected_speakers is not None and not (
            1 <= args.expected_speakers <= 64
        ):
            raise SkillInputError("expected-speakers必须在1到64之间。")
        validate_output_language(args.output_language)
        backend = resolve_backend_paths()
        validate_backend_paths(backend)

        input_path, input_stat = validate_input_path(args.input)
        input_sha256 = sha256_file(input_path)
        media_info = probe_media(input_path, backend.ffprobe)
        project_configs = resolve_project_configs(
            args.domain,
            args.glossary,
            optical_config=backend.optical_config,
        )
        all_configs = [backend.base_config, *project_configs]
        config_info = config_descriptors(all_configs)

        if args.job_name is None:
            job_name = automatic_job_name(input_path, input_sha256)
        else:
            job_name = args.job_name
            if not explicit_job_name_is_safe(job_name):
                raise SkillInputError(
                    "job-name必须是不含空格、路径分隔符、Windows非法字符或"
                    "保留设备名的单个短目录名。"
                )

        job_dir = (backend.jobs_dir / job_name).resolve()
        if job_dir.parent != backend.jobs_dir.resolve():
            raise SkillInputError(f"Job目录必须位于：{backend.jobs_dir.resolve()}")
        external_state_path = state_path_for_job(job_name, backend.state_dir)
        existing_state = load_skill_state(job_dir, external_state_path)

        input_identity = {
            "path": str(input_path),
            "size_bytes": input_stat.st_size,
            "modified_time_ns": input_stat.st_mtime_ns,
            "extension": input_path.suffix.casefold(),
            "sha256": input_sha256,
        }
        current_config_signature = hashlib.sha256(
            json.dumps(config_info, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        action: str
        input_rebound: dict[str, Any] | None = None

        if job_dir.exists():
            if not job_dir.is_dir():
                raise SkillInputError(f"Job路径存在但不是目录：{job_dir}")
            if existing_state is None:
                raise SkillInputError(
                    "Job已存在但缺少可验证SHA-256的meeting_skill状态；"
                    "为避免误覆盖，请使用新的job-name。"
                )
            old_hash = state_input_hash(existing_state)
            if old_hash != input_sha256:
                raise SkillInputError(
                    f"Job输入SHA-256不一致，拒绝复用：{job_dir}"
                )
            if state_expected_speakers(existing_state) != args.expected_speakers:
                raise SkillInputError(
                    "Job的expected-speakers与原任务不一致；请使用新的job-name。"
                )

            old_signature = existing_state.get("cleaning_config_signature")
            if main_pipeline_is_complete(job_dir):
                if (
                    postprocessing_is_complete(job_dir)
                    and old_signature == current_config_signature
                ):
                    action = "skip_completed"
                else:
                    action = "postprocess_existing"
            else:
                if not args.resume:
                    raise SkillInputError(
                        "Job尚未完成；为避免意外继续或覆盖，必须显式传入"
                        "--resume，或改用新的job-name。"
                    )
                if not (job_dir / "pipeline_state.json").is_file():
                    raise SkillInputError(
                        "Job不完整且缺少pipeline_state.json，不能安全Resume；"
                        "请使用新的job-name。"
                    )
                action = "resume"
                input_rebound = rebind_pipeline_state_input(
                    job_dir, input_path, input_stat
                )
        else:
            if args.resume:
                raise SkillInputError(f"--resume要求已有Job目录：{job_dir}")
            action = "new"

        request_context = {
            "meeting_title": args.meeting_title,
            "meeting_date": args.meeting_date,
            "meeting_topic": args.meeting_topic,
            "expected_speakers": args.expected_speakers,
            "languages": list(args.languages),
            "domain": args.domain,
            "glossary_configs": [str(path) for path in project_configs],
            "known_participants": list(args.known_participant),
            "user_speaker_hint": args.user_speaker_hint,
            "output_language": args.output_language,
            "questions": list(args.question),
            "anonymous_speakers": True,
        }
        created_at = (
            existing_state.get("created_at")
            if isinstance(existing_state, dict)
            else utc_now()
        )
        existing_degraded = (
            bool(existing_state.get("degraded_mode"))
            if isinstance(existing_state, dict)
            else False
        )
        existing_degraded_reason = (
            existing_state.get("degraded_reason")
            if isinstance(existing_state, dict)
            else None
        )
        state = {
            "schema_version": STATE_SCHEMA_VERSION,
            "status": "running",
            "created_at": created_at,
            "updated_at": utc_now(),
            "job_name": job_name,
            "job_dir": str(job_dir),
            "action": action,
            "backend_paths": backend.as_record(),
            "input": input_identity,
            "media": media_info,
            "backend_settings": {
                "language": FIXED_LANGUAGE,
                "language_strategy": FIXED_LANGUAGE_STRATEGY,
                "chunk_duration": FIXED_CHUNK_DURATION,
                "chunk_overlap": FIXED_CHUNK_OVERLAP,
                "keep_chunks": True,
                "anonymous_speakers": True,
                "expected_speakers": args.expected_speakers,
            },
            "cleaning_configs": config_info,
            "cleaning_config_signature": current_config_signature,
            "request": request_context,
            "input_rebound": input_rebound,
            "degraded_mode": existing_degraded,
            "degraded_reason": existing_degraded_reason,
            "speaker_attribution_reliable": not existing_degraded,
            "return_codes": {},
            "timings_seconds": {},
            "logs": {
                "skill": str(job_dir / "meeting_skill_console.log"),
                "pipeline": str(job_dir / "pipeline_console.log"),
                "complete_pipeline": str(job_dir / "pipeline_complete_console.log"),
            },
        }
        atomic_write_json(external_state_path, state)

        log = SkillConsoleLog(job_dir, append=job_dir.exists())
        emit(log.file, f"输入文件：{input_path}")
        emit(log.file, f"输入SHA-256：{input_sha256}")
        emit(log.file, f"媒体时长：{media_info['duration_seconds']:.3f}秒")
        emit(log.file, f"Job目录：{job_dir}")
        emit(log.file, f"执行策略：{action}")
        emit(log.file, f"后端app目录：{backend.app_dir}")
        emit(
            log.file,
            "后端配置来源："
            + json.dumps(backend.sources, ensure_ascii=False, sort_keys=True),
        )
        emit(log.file, "说话人模式：匿名")
        if input_rebound is not None:
            emit(log.file, "Resume输入路径已在SHA-256一致后安全重绑定。")

        if action != "skip_completed":
            backend_command = build_backend_command(
                backend=backend,
                job_dir=job_dir,
                input_path=input_path,
                job_name=job_name,
                expected_speakers=args.expected_speakers,
                project_configs=project_configs,
                action=action,
            )
            state["backend_command"] = backend_command
            atomic_write_json(external_state_path, state)
            backend_code, backend_elapsed = run_streaming_command(
                backend_command,
                backend.app_dir,
                log.file,
                "LOCAL TRANSCRIPTION BACKEND",
            )
            state["return_codes"]["backend"] = backend_code
            state["timings_seconds"]["backend"] = round(backend_elapsed, 6)
            if backend_code != 0:
                final_output_errors = validate_transcript_final_outputs(job_dir)
                present_final_outputs = [
                    path for path in final_output_paths(job_dir) if path.exists()
                ]
                generated_unknown: dict[str, Any] | None = None
                generation_error: str | None = None
                if (
                    action in {"new", "resume"}
                    and final_output_errors
                    and not present_final_outputs
                ):
                    try:
                        generated_unknown = (
                            generate_unknown_final_from_word_timestamps(
                                job_dir,
                                backend.generate_vtt_script,
                            )
                        )
                    except (OSError, UnicodeError, RuntimeError) as error:
                        generation_error = str(error)
                    else:
                        final_output_errors = validate_transcript_final_outputs(
                            job_dir
                        )

                if action not in {"new", "resume"} or final_output_errors:
                    state["status"] = "transcription_failed"
                    state["updated_at"] = utc_now()
                    state["degraded_fallback"] = {
                        "attempted": False,
                        "backend_return_code": backend_code,
                        "transcript_validation_errors": final_output_errors,
                        "present_final_outputs": [
                            str(path) for path in present_final_outputs
                        ],
                        "word_timestamp_generation_error": generation_error,
                        "generated_unknown_from_word_timestamps": False,
                    }
                    details = list(final_output_errors)
                    if present_final_outputs:
                        details.append(
                            "存在已有或部分final文件，绝不覆盖："
                            + "，".join(str(path) for path in present_final_outputs)
                        )
                    if generation_error:
                        details.append(
                            "word_timestamps降级生成失败：" + generation_error
                        )
                    if not details:
                        details.append("当前步骤不是可降级的主转录执行")
                    raise RuntimeError(
                        f"本地转录后端失败，返回码={backend_code}；"
                        "没有可安全降级使用的transcript_final三件套："
                        f"{'；'.join(details)}；"
                        f"日志={job_dir / 'pipeline_complete_console.log'}"
                    )

                generated_unknown_flag = generated_unknown is not None
                fallback_source = (
                    "generated_unknown_from_word_timestamps"
                    if generated_unknown_flag
                    else "existing_transcript_final"
                )
                if generated_unknown_flag:
                    degraded_reason = (
                        f"本地转录后端返回码={backend_code}，且未留下任何"
                        "transcript_final文件；已复用generate_vtt.py从有效"
                        "word_timestamps.json生成全UNKNOWN转录，再跳过模型继续"
                        "文本清理、技术复核和内容分析。说话人归属不可靠。"
                    )
                else:
                    degraded_reason = (
                        f"本地转录后端返回码={backend_code}，但已留下有效的"
                        "transcript_final JSON/TXT/VTT；跳过模型，仅继续文本清理、"
                        "技术复核和内容分析。说话人归属不可靠。"
                    )
                state["status"] = "degraded_postprocessing"
                state["degraded_mode"] = True
                state["degraded_reason"] = degraded_reason
                state["speaker_attribution_reliable"] = False
                state["generated_unknown_from_word_timestamps"] = (
                    generated_unknown_flag
                )
                state["speaker_label_policy"] = (
                    "all_UNKNOWN"
                    if generated_unknown_flag
                    else "preserve_existing_else_UNKNOWN"
                )
                state["degraded_fallback"] = {
                    "attempted": True,
                    "backend_return_code": backend_code,
                    "transcript_validation_errors": [],
                    "fallback_source": fallback_source,
                    "generated_unknown_from_word_timestamps": (
                        generated_unknown_flag
                    ),
                    "generated_output": generated_unknown,
                }
                state["updated_at"] = utc_now()
                atomic_write_json(external_state_path, state)
                atomic_write_json(job_dir / "meeting_skill_run.json", state)
                emit(log.file, f"WARNING: {degraded_reason}", error=True)
                emit(
                    log.file,
                    (
                        "降级模式已生成全UNKNOWN transcript_final；"
                        "说话人信息不可用。"
                        if generated_unknown_flag
                        else "降级模式不会修改原始transcript_final；分析保留现有"
                        "speaker_id/speaker，缺失标签按UNKNOWN处理。"
                    ),
                    error=True,
                )

                fallback_manifest = prepare_degraded_postprocessing_manifest(
                    job_dir,
                    backend_return_code=backend_code,
                    reason=degraded_reason,
                    fallback_source=fallback_source,
                    generated_unknown_from_word_timestamps=(
                        generated_unknown_flag
                    ),
                )
                state["degraded_fallback"]["manifest"] = fallback_manifest
                fallback_command = build_backend_command(
                    backend=backend,
                    job_dir=job_dir,
                    input_path=input_path,
                    job_name=job_name,
                    expected_speakers=args.expected_speakers,
                    project_configs=project_configs,
                    action="postprocess_existing",
                )
                state["degraded_postprocessing_command"] = fallback_command
                atomic_write_json(external_state_path, state)
                atomic_write_json(job_dir / "meeting_skill_run.json", state)
                fallback_code, fallback_elapsed = run_streaming_command(
                    fallback_command,
                    backend.app_dir,
                    log.file,
                    "DEGRADED POSTPROCESSING (NO MODELS)",
                )
                state["return_codes"]["degraded_postprocessing"] = fallback_code
                state["timings_seconds"]["degraded_postprocessing"] = round(
                    fallback_elapsed, 6
                )
                if fallback_code != 0:
                    state["status"] = "degraded_postprocessing_failed"
                    state["updated_at"] = utc_now()
                    raise RuntimeError(
                        "转录后端失败后找到了可用原始转录，但降级清理/复核失败，"
                        f"返回码={fallback_code}；日志="
                        f"{job_dir / 'pipeline_complete_console.log'}"
                    )
                finish_degraded_postprocessing_manifest(
                    job_dir,
                    backend_return_code=backend_code,
                    reason=degraded_reason,
                    fallback_source=fallback_source,
                    generated_unknown_from_word_timestamps=(
                        generated_unknown_flag
                    ),
                )
                state["degraded_fallback"]["status"] = "completed"
        else:
            emit(log.file, "现有Job的转录、清理和复核均已完成；跳过模型与后处理。")
            state["return_codes"]["backend"] = 0
            state["timings_seconds"]["backend"] = 0.0

        if not main_pipeline_is_complete(job_dir):
            state["status"] = "transcription_outputs_invalid"
            raise RuntimeError("转录后端未留下有效的transcript_final三件套。")
        if not postprocessing_is_complete(job_dir):
            state["status"] = "review_outputs_invalid"
            raise RuntimeError("技术复核包未成功完成。")

        analysis_transcript, used_raw_fallback = select_analysis_transcript(
            job_dir
        )
        state["analysis_transcript"] = str(analysis_transcript)
        state["used_raw_transcript_fallback"] = used_raw_fallback
        if used_raw_fallback:
            emit(
                log.file,
                "WARNING: 文本清理未完成；分析将使用原始transcript_final.json。",
                error=True,
            )

        context_path = job_dir / "meeting_skill_input.json"
        atomic_write_json(context_path, request_context)
        state["context_json"] = str(context_path)
        state["status"] = "analyzing"
        state["updated_at"] = utc_now()
        atomic_write_json(external_state_path, state)
        atomic_write_json(job_dir / "meeting_skill_run.json", state)

        analysis_command = [
            str(backend.pyannote_python),
            "-X",
            "utf8",
            str(ANALYSIS_SCRIPT),
            "--job-dir",
            str(job_dir),
            "--context-json",
            str(context_path),
        ]
        state["analysis_command"] = analysis_command
        analysis_code, analysis_elapsed = run_streaming_command(
            analysis_command, SKILL_DIR, log.file, "MEETING CONTENT ANALYSIS"
        )
        state["return_codes"]["analysis"] = analysis_code
        state["timings_seconds"]["analysis"] = round(analysis_elapsed, 6)
        missing_analysis = [
            str(job_dir / name)
            for name in ANALYSIS_OUTPUT_NAMES
            if not (job_dir / name).is_file()
        ]
        if analysis_code != 0 or missing_analysis:
            state["status"] = "analysis_failed"
            raise RuntimeError(
                f"会议分析失败，返回码={analysis_code}，"
                f"缺少输出={missing_analysis or '无'}"
            )

        validator_command = [
            str(backend.pyannote_python),
            "-X",
            "utf8",
            str(VALIDATOR_SCRIPT),
            "--job-dir",
            str(job_dir),
        ]
        state["validator_command"] = validator_command
        validator_code, validator_elapsed = run_streaming_command(
            validator_command, SKILL_DIR, log.file, "SKILL OUTPUT VALIDATION"
        )
        state["return_codes"]["validation"] = validator_code
        state["timings_seconds"]["validation"] = round(validator_elapsed, 6)
        validation_path = job_dir / "meeting_skill_validation.json"
        if validator_code != 0 or not validation_path.is_file():
            state["status"] = "validation_failed"
            raise RuntimeError(
                f"Skill输出验证失败，返回码={validator_code}，"
                f"报告存在={validation_path.is_file()}"
            )

        if state.get("degraded_mode"):
            state["status"] = "completed_degraded"
        else:
            state["status"] = (
                "completed_with_warnings" if used_raw_fallback else "completed"
            )
        state["updated_at"] = utc_now()
        state["outputs"] = {
            "transcript": str(analysis_transcript),
            "review_package": str(job_dir / "transcript_review_package.json"),
            "analysis_json": str(job_dir / "meeting_analysis.json"),
            "analysis_markdown": str(job_dir / "meeting_analysis.md"),
            "timeline_markdown": str(job_dir / "meeting_timeline.md"),
            "source_index_json": str(job_dir / "meeting_source_index.json"),
            "validation_json": str(validation_path),
        }
        atomic_write_json(external_state_path, state)
        atomic_write_json(job_dir / "meeting_skill_run.json", state)
        emit(log.file, "=" * 72)
        emit(log.file, f"MEETING SKILL STATUS: {state['status']}")
        emit(log.file, f"分析报告：{job_dir / 'meeting_analysis.md'}")
        emit(log.file, f"主题时间轴：{job_dir / 'meeting_timeline.md'}")
        emit(log.file, f"来源索引：{job_dir / 'meeting_source_index.json'}")
        return 0

    except SkillInputError as error:
        emit(log.file if log is not None else None, f"ERROR: {error}", error=True)
        return 2
    except BaseException as error:
        if state is not None:
            state["updated_at"] = utc_now()
            state["error_type"] = type(error).__name__
            state["error"] = str(error)
            if state.get("status") in {"running", "analyzing"}:
                state["status"] = "failed"
            if external_state_path is not None:
                atomic_write_json(external_state_path, state)
            if job_dir is not None and job_dir.is_dir():
                atomic_write_json(job_dir / "meeting_skill_run.json", state)
        emit(
            log.file if log is not None else None,
            f"ERROR: {type(error).__name__}: {error}",
            error=True,
        )
        if log is not None:
            emit(log.file, traceback.format_exc(), error=True)
        return 1
    finally:
        if log is not None:
            log.close()


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
