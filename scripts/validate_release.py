from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "meeting-audio-transcription-analysis"
SKILL_ROOT = REPOSITORY_ROOT / "skills" / SKILL_NAME

REQUIRED_PATHS = (
    REPOSITORY_ROOT / "README.md",
    REPOSITORY_ROOT / "VERSION",
    REPOSITORY_ROOT / ".gitignore",
    REPOSITORY_ROOT / ".github" / "workflows" / "validate.yml",
    REPOSITORY_ROOT / "config" / "local_backend.example.json",
    REPOSITORY_ROOT / "docs" / "INSTALL.zh-CN.md",
    REPOSITORY_ROOT / "docs" / "USAGE.zh-CN.md",
    REPOSITORY_ROOT / "docs" / "BACKEND.zh-CN.md",
    REPOSITORY_ROOT / "docs" / "REPOSITORY_LAYOUT.zh-CN.md",
    REPOSITORY_ROOT / "scripts" / "install.ps1",
    REPOSITORY_ROOT / "scripts" / "uninstall.ps1",
    REPOSITORY_ROOT / "scripts" / "build_package.ps1",
    REPOSITORY_ROOT / "scripts" / "validate_release.py",
    SKILL_ROOT / "SKILL.md",
    SKILL_ROOT / "agents" / "openai.yaml",
    SKILL_ROOT / "scripts" / "run_meeting_skill.py",
    SKILL_ROOT / "scripts" / "analyze_transcript.py",
    SKILL_ROOT / "scripts" / "validate_skill_outputs.py",
)

FORBIDDEN_DIRECTORY_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "venv",
    "conda",
    "jobs",
    "chunks",
    "models",
    "cache",
}
FORBIDDEN_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".wav",
    ".mp3",
    ".m4a",
    ".flac",
    ".aac",
    ".ogg",
    ".mp4",
    ".mov",
    ".mkv",
    ".bin",
    ".ckpt",
    ".onnx",
    ".pt",
    ".pth",
    ".safetensors",
}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def repository_files() -> list[Path]:
    files: list[Path] = []
    for path in REPOSITORY_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(REPOSITORY_ROOT)
        if relative.parts and relative.parts[0] in {".git", "dist"}:
            continue
        files.append(path)
    return sorted(files)


def validate_skill_frontmatter(errors: list[str]) -> None:
    path = SKILL_ROOT / "SKILL.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"无法读取 SKILL.md：{exc}")
        return
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, flags=re.DOTALL)
    if match is None:
        errors.append("SKILL.md 缺少有效 YAML frontmatter。")
        return
    frontmatter = match.group(1)
    if re.search(rf"(?m)^name:\s*{re.escape(SKILL_NAME)}\s*$", frontmatter) is None:
        errors.append("SKILL.md 的 name 不正确。")
    description_match = re.search(r"(?m)^description:\s*(.+)$", frontmatter)
    if description_match is None or not description_match.group(1).strip().strip('"'):
        errors.append("SKILL.md 缺少非空 description。")


def validate_json(files: list[Path], errors: list[str]) -> None:
    for path in files:
        if path.suffix.lower() != ".json":
            continue
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"JSON 无效：{path.relative_to(REPOSITORY_ROOT)}：{exc}")


def validate_markdown_links(files: list[Path], errors: list[str]) -> None:
    for path in files:
        if path.suffix.lower() != ".md":
            continue
        text = path.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK_PATTERN.findall(text):
            target = raw_target.strip().strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            target = unquote(target.split("#", 1)[0])
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                errors.append(
                    f"Markdown 链接不存在：{path.relative_to(REPOSITORY_ROOT)} -> {target}"
                )


def validate_contents(files: list[Path], errors: list[str]) -> None:
    for path in files:
        relative = path.relative_to(REPOSITORY_ROOT)
        lowered_parts = {part.casefold() for part in relative.parts[:-1]}
        forbidden_parts = lowered_parts & FORBIDDEN_DIRECTORY_NAMES
        if forbidden_parts:
            errors.append(f"包含禁止目录：{relative}")
        if path.name.casefold() == "local_backend.json":
            errors.append(f"包含本机私有配置：{relative}")
        if path.suffix.casefold() in FORBIDDEN_SUFFIXES:
            errors.append(f"包含禁止发布的文件类型：{relative}")

        if path.suffix.casefold() not in {
            ".md",
            ".py",
            ".ps1",
            ".json",
            ".yaml",
            ".yml",
            ".txt",
            "",
        } and path.name != ".gitignore":
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            errors.append(f"文本文件无法按 UTF-8 读取：{relative}：{exc}")
            continue
        if "C:\\Users\\Admin" in text or "D:\\NGSU" in text:
            errors.append(f"包含作者机器绝对路径：{relative}")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"疑似包含凭据或私钥：{relative}")
                break


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED_PATHS:
        if not path.is_file():
            errors.append(f"缺少必需文件：{path.relative_to(REPOSITORY_ROOT)}")

    files = repository_files()
    validate_skill_frontmatter(errors)
    validate_json(files, errors)
    validate_markdown_links(files, errors)
    validate_contents(files, errors)

    openai_yaml = SKILL_ROOT / "agents" / "openai.yaml"
    if openai_yaml.is_file():
        yaml_text = openai_yaml.read_text(encoding="utf-8")
        if f"${SKILL_NAME}" not in yaml_text:
            errors.append("agents/openai.yaml 的 default_prompt 未引用 Skill 名称。")

    version = (REPOSITORY_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if re.fullmatch(r"\d+\.\d+\.\d+", version) is None:
        errors.append(f"VERSION 不是语义版本：{version!r}")

    if errors:
        print("发布验证失败：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        f"发布验证通过：{len(files)} 个文件，Skill={SKILL_NAME}，version={version}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
