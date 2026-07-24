from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence


REQUIRED_ANALYSIS_KEYS = (
    "metadata",
    "source_files",
    "audio_duration",
    "languages",
    "speakers",
    "executive_summary",
    "key_points",
    "topic_segments",
    "timeline",
    "decisions",
    "action_items",
    "open_questions",
    "risks",
    "disagreements",
    "speaker_summaries",
    "terminology",
    "user_questions",
    "quality_notes",
)

EVIDENCE_COLLECTIONS = (
    "key_points",
    "topic_segments",
    "timeline",
    "decisions",
    "action_items",
    "open_questions",
    "risks",
    "disagreements",
)

EVIDENCE_KEYS = (
    "id",
    "start_time",
    "end_time",
    "speakers",
    "cue_indices",
    "source_text",
    "confidence",
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as file:
        value = json.load(file)

    if not isinstance(value, dict):
        raise TypeError(f"JSON顶层必须是对象：{path}")

    return value


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")

    with temporary.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")

    temporary.replace(path)


def resolve_recorded_path(value: object, base_dir: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None

    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def preferred_speaker(cue: dict[str, Any]) -> str:
    value = cue.get("speaker_id") or cue.get("speaker") or "UNKNOWN"
    return str(value).strip() or "UNKNOWN"


def normalized_text(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def iter_claim_items(
    analysis: dict[str, Any],
) -> Iterable[tuple[str, dict[str, Any]]]:
    for collection_name in EVIDENCE_COLLECTIONS:
        collection = analysis.get(collection_name, [])
        if not isinstance(collection, list):
            continue
        for item in collection:
            if isinstance(item, dict):
                yield collection_name, item

    speaker_summaries = analysis.get("speaker_summaries", [])
    if isinstance(speaker_summaries, list):
        for summary in speaker_summaries:
            if not isinstance(summary, dict):
                continue
            for field in ("main_points", "questions", "commitments", "concerns"):
                values = summary.get(field, [])
                if not isinstance(values, list):
                    continue
                for item in values:
                    if isinstance(item, dict):
                        yield f"speaker_summaries.{field}", item

    questions = analysis.get("user_questions", [])
    if isinstance(questions, list):
        for item in questions:
            if not isinstance(item, dict):
                continue
            found = item.get("found")
            cue_indices = item.get("cue_indices")
            if found is True or cue_indices:
                yield "user_questions", item


def iter_evidence_items(
    analysis: dict[str, Any],
) -> Iterable[tuple[str, dict[str, Any]]]:
    seen_ids: set[str] = set()
    for category, item in iter_claim_items(analysis):
        identifier = str(item.get("id") or f"missing-{id(item)}")
        seen_ids.add(identifier)
        yield category, item

    speaker_summaries = analysis.get("speaker_summaries", [])
    if not isinstance(speaker_summaries, list):
        return
    for summary in speaker_summaries:
        if not isinstance(summary, dict):
            continue
        evidence = summary.get("evidence", [])
        if not isinstance(evidence, list):
            continue
        for item in evidence:
            if not isinstance(item, dict):
                continue
            identifier = str(item.get("id") or f"missing-{id(item)}")
            if identifier in seen_ids:
                continue
            seen_ids.add(identifier)
            yield "speaker_summaries.evidence", item


def validate_evidence_item(
    category: str,
    item: dict[str, Any],
    cues: list[dict[str, Any]],
    allowed_speakers: set[str],
    index_entries: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    identifier = str(item.get("id") or "(missing-id)")
    prefix = f"{category}:{identifier}"

    for key in EVIDENCE_KEYS:
        if key not in item:
            errors.append(f"{prefix}缺少证据字段：{key}")

    cue_indices = item.get("cue_indices")
    if not isinstance(cue_indices, list) or not cue_indices:
        errors.append(f"{prefix}.cue_indices必须是非空数组")
        return errors

    if any(not isinstance(index, int) for index in cue_indices):
        errors.append(f"{prefix}.cue_indices只能包含整数")
        return errors

    if cue_indices != sorted(set(cue_indices)):
        errors.append(f"{prefix}.cue_indices必须严格递增且不重复")

    invalid_indices = [
        index for index in cue_indices if index < 0 or index >= len(cues)
    ]
    if invalid_indices:
        errors.append(f"{prefix}包含越界cue索引：{invalid_indices}")
        return errors

    evidence_cues = [cues[index] for index in cue_indices]
    expected_start = min(float(cue["start_time"]) for cue in evidence_cues)
    expected_end = max(float(cue["end_time"]) for cue in evidence_cues)

    try:
        start_time = float(item.get("start_time"))
        end_time = float(item.get("end_time"))
    except (TypeError, ValueError):
        errors.append(f"{prefix}的时间字段不是有效数值")
    else:
        if not math.isfinite(start_time) or not math.isfinite(end_time):
            errors.append(f"{prefix}的时间字段必须是有限数值")
        if end_time < start_time:
            errors.append(f"{prefix}的end_time早于start_time")
        if category == "timeline":
            try:
                evidence_start = float(item.get("evidence_start_time"))
                evidence_end = float(item.get("evidence_end_time"))
            except (TypeError, ValueError):
                errors.append(f"{prefix}缺少有效的代表证据时间范围")
            else:
                if abs(evidence_start - expected_start) > 0.011:
                    errors.append(
                        f"{prefix}.evidence_start_time未对应cue：{evidence_start} != {expected_start}"
                    )
                if abs(evidence_end - expected_end) > 0.011:
                    errors.append(
                        f"{prefix}.evidence_end_time未对应cue：{evidence_end} != {expected_end}"
                    )
                if start_time > evidence_start or end_time < evidence_end:
                    errors.append(f"{prefix}的完整时间段未覆盖代表证据")
            if item.get("segment_start_time") != item.get("start_time"):
                errors.append(f"{prefix}.start_time未对应完整topic segment起点")
            if item.get("segment_end_time") != item.get("end_time"):
                errors.append(f"{prefix}.end_time未对应完整topic segment终点")
        else:
            if abs(start_time - expected_start) > 0.011:
                errors.append(
                    f"{prefix}.start_time未对应cue：{start_time} != {expected_start}"
                )
            if abs(end_time - expected_end) > 0.011:
                errors.append(
                    f"{prefix}.end_time未对应cue：{end_time} != {expected_end}"
                )

    speakers = item.get("speakers")
    if not isinstance(speakers, list) or not speakers:
        errors.append(f"{prefix}.speakers必须是非空数组")
    else:
        unknown = [str(value) for value in speakers if str(value) not in allowed_speakers]
        if unknown:
            errors.append(f"{prefix}包含非转录speaker标签：{unknown}")

        expected_speakers = {
            preferred_speaker(cue) for cue in evidence_cues
        }
        if not set(map(str, speakers)).issubset(expected_speakers):
            errors.append(f"{prefix}.speakers与所引cue不一致")

    source_text = normalized_text(item.get("source_text"))
    if not source_text:
        errors.append(f"{prefix}.source_text不能为空")
    elif not any(
        normalized_text(cue.get("text")) in source_text
        for cue in evidence_cues
        if normalized_text(cue.get("text"))
    ):
        errors.append(f"{prefix}.source_text未包含所引cue原文")

    if identifier == "(missing-id)":
        errors.append(f"{prefix}缺少id")
    elif identifier not in index_entries:
        errors.append(f"{prefix}未登记到meeting_source_index.json")
    else:
        entry = index_entries[identifier]
        if not isinstance(entry, dict):
            errors.append(f"source index条目不是对象：{identifier}")
        elif entry.get("cue_indices") != cue_indices:
            errors.append(f"source index的cue_indices不一致：{identifier}")
        elif (
            entry.get("start_time") != item.get("start_time")
            or entry.get("end_time") != item.get("end_time")
        ):
            errors.append(f"source index的时间范围不一致：{identifier}")

    return errors


def validate_claim_ids(analysis: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    locations_by_id: dict[str, list[str]] = {}
    for category, item in iter_claim_items(analysis):
        identifier = str(item.get("id") or "").strip()
        if not identifier:
            continue
        locations_by_id.setdefault(identifier, []).append(category)
    for identifier, locations in locations_by_id.items():
        if len(locations) > 1:
            errors.append(
                f"重复claim id：{identifier}（{', '.join(locations)}）"
            )
    return errors


def validate_evidence_duration_bounds(
    analysis: dict[str, Any], audio_duration: float
) -> list[str]:
    errors: list[str] = []
    maximum = audio_duration + 0.5
    for category, item in iter_evidence_items(analysis):
        identifier = str(item.get("id") or "(missing-id)")
        try:
            start_time = float(item.get("start_time"))
            end_time = float(item.get("end_time"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(start_time) or not math.isfinite(end_time):
            continue
        if start_time > maximum or end_time > maximum:
            errors.append(
                f"{category}:{identifier}的时间超出audio_duration+0.5秒"
            )
    return errors


def validate_outputs(job_dir: Path) -> dict[str, Any]:
    analysis_path = job_dir / "meeting_analysis.json"
    index_path = job_dir / "meeting_source_index.json"
    markdown_path = job_dir / "meeting_analysis.md"
    timeline_path = job_dir / "meeting_timeline.md"
    errors: list[str] = []

    for path in (analysis_path, index_path, markdown_path, timeline_path):
        if not path.is_file():
            errors.append(f"缺少分析输出：{path}")

    if errors:
        return {"status": "failed", "errors": errors}

    try:
        analysis = load_json(analysis_path)
        source_index = load_json(index_path)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
        return {"status": "failed", "errors": [str(exc)]}

    missing_keys = [key for key in REQUIRED_ANALYSIS_KEYS if key not in analysis]
    errors.extend(f"meeting_analysis.json缺少顶层字段：{key}" for key in missing_keys)

    audio_duration: float | None = None
    try:
        candidate_duration = float(analysis.get("audio_duration"))
    except (TypeError, ValueError):
        errors.append("analysis.audio_duration必须是有效数值")
    else:
        if not math.isfinite(candidate_duration) or candidate_duration < 0.0:
            errors.append("analysis.audio_duration必须是有限且非负的数值")
        else:
            audio_duration = candidate_duration

    errors.extend(validate_claim_ids(analysis))
    if audio_duration is not None:
        errors.extend(validate_evidence_duration_bounds(analysis, audio_duration))

    source_files = analysis.get("source_files")
    transcript_path: Path | None = None
    cue_times_valid = True
    if isinstance(source_files, dict):
        transcript_path = resolve_recorded_path(
            source_files.get("transcript"), job_dir
        )
    if transcript_path is None or not transcript_path.is_file():
        errors.append(f"分析引用的transcript不存在：{transcript_path}")
        cues: list[dict[str, Any]] = []
    else:
        try:
            transcript = load_json(transcript_path)
            raw_cues = transcript.get("cues")
            if not isinstance(raw_cues, list) or not raw_cues:
                raise TypeError(f"transcript.cues必须是非空数组：{transcript_path}")
            cues = [cue for cue in raw_cues if isinstance(cue, dict)]
            if len(cues) != len(raw_cues):
                errors.append("transcript.cues包含非对象条目")
                cue_times_valid = False
            previous_start = -math.inf
            for cue_index, cue in enumerate(cues):
                try:
                    start_time = float(cue.get("start_time"))
                    end_time = float(cue.get("end_time"))
                except (TypeError, ValueError):
                    errors.append(f"transcript cue {cue_index}时间字段无效")
                    cue_times_valid = False
                    continue
                if not math.isfinite(start_time) or not math.isfinite(end_time):
                    errors.append(f"transcript cue {cue_index}时间必须是有限数值")
                    cue_times_valid = False
                    continue
                if start_time < 0.0:
                    errors.append(f"transcript cue {cue_index}.start_time不能为负")
                    cue_times_valid = False
                if end_time < start_time:
                    errors.append(f"transcript cue {cue_index}.end_time早于start_time")
                    cue_times_valid = False
                if start_time < previous_start:
                    errors.append(f"transcript cue {cue_index}.start_time发生倒退")
                    cue_times_valid = False
                if audio_duration is not None and end_time > audio_duration + 0.5:
                    errors.append(
                        f"transcript cue {cue_index}.end_time超出audio_duration+0.5秒"
                    )
                    cue_times_valid = False
                previous_start = start_time
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
            errors.append(str(exc))
            cues = []
            cue_times_valid = False

    entries = source_index.get("entries")
    if not isinstance(entries, dict):
        errors.append("meeting_source_index.json的entries必须是对象")
        entries = {}

    allowed_speakers = {preferred_speaker(cue) for cue in cues}

    speaker_summaries = analysis.get("speaker_summaries", [])
    if not isinstance(speaker_summaries, list):
        errors.append("analysis.speaker_summaries必须是数组")
    else:
        for summary_index, summary in enumerate(speaker_summaries):
            if not isinstance(summary, dict):
                errors.append(
                    f"speaker_summaries[{summary_index}]必须是对象"
                )
                continue
            for field in ("main_points", "questions", "commitments", "concerns"):
                values = summary.get(field, [])
                if not isinstance(values, list):
                    errors.append(
                        f"speaker_summaries[{summary_index}].{field}必须是数组"
                    )
                    continue
                if any(not isinstance(item, dict) for item in values):
                    errors.append(
                        f"speaker_summaries[{summary_index}].{field}每项必须是可追溯证据对象"
                    )

    if cues and cue_times_valid:
        for category, item in iter_evidence_items(analysis):
            errors.extend(
                validate_evidence_item(
                    category,
                    item,
                    cues,
                    allowed_speakers,
                    entries,
                )
            )

    speakers = analysis.get("speakers")
    if isinstance(speakers, list):
        recorded_speakers = {
            str(item.get("speaker"))
            for item in speakers
            if isinstance(item, dict) and item.get("speaker") is not None
        }
        if recorded_speakers != allowed_speakers:
            errors.append(
                "analysis.speakers与transcript中的匿名speaker_id集合不一致"
            )
    else:
        errors.append("analysis.speakers必须是数组")

    decisions = analysis.get("decisions", [])
    if isinstance(decisions, list):
        for item in decisions:
            if isinstance(item, dict) and item.get("decision_type") not in (
                "explicit",
                None,
            ):
                errors.append("decisions只允许明确决定：decision_type必须为explicit")

    action_items = analysis.get("action_items", [])
    if isinstance(action_items, list):
        for item in action_items:
            if not isinstance(item, dict):
                continue
            owner = item.get("owner")
            if owner is not None and str(owner) not in allowed_speakers:
                errors.append(f"待办owner不是录音speaker标签：{owner}")

    markdown_text = markdown_path.read_text(encoding="utf-8-sig")
    timeline_text = timeline_path.read_text(encoding="utf-8-sig")
    if not markdown_text.strip():
        errors.append("meeting_analysis.md为空")
    if not timeline_text.strip():
        errors.append("meeting_timeline.md为空")

    evidence_count = sum(1 for _ in iter_evidence_items(analysis))
    result = {
        "status": "completed" if not errors else "failed",
        "job_dir": str(job_dir),
        "transcript": str(transcript_path) if transcript_path else None,
        "cue_count": len(cues),
        "speaker_count": len(allowed_speakers),
        "evidence_item_count": evidence_count,
        "source_index_entry_count": len(entries),
        "errors": errors,
    }
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="校验会议Skill分析文件及其cue证据链。"
    )
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument(
        "--no-write-report",
        action="store_true",
        help="不写meeting_skill_validation.json。",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    job_dir = args.job_dir.expanduser().resolve()

    if not job_dir.is_dir():
        print(f"ERROR: Job目录不存在：{job_dir}", file=sys.stderr)
        return 2

    result = validate_outputs(job_dir)
    if not args.no_write_report:
        atomic_write_json(job_dir / "meeting_skill_validation.json", result)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
