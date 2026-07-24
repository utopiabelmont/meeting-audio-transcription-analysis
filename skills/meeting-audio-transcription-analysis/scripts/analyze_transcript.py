from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


NOT_FOUND = "录音中没有找到足以支持该结论的内容。"
SCHEMA_VERSION = "1.0"

OUTPUT_LANGUAGE_ALIASES = {
    "chinese": "Chinese",
    "zh": "Chinese",
    "zh-cn": "Chinese",
    "中文": "Chinese",
    "english": "English",
    "en": "English",
    "en-us": "English",
    "en-gb": "English",
    "英语": "English",
    "japanese": "Japanese",
    "ja": "Japanese",
    "ja-jp": "Japanese",
    "日语": "Japanese",
    "日本語": "Japanese",
}

REPORT_TEXT: dict[str, dict[str, str]] = {
    "Chinese": {
        "default_title": "会议分析",
        "default_timeline_title": "会议",
        "basic_information": "基本信息",
        "date": "日期",
        "topic": "主题",
        "duration": "时长",
        "languages": "语言",
        "speakers": "说话人",
        "analysis_source": "分析文本",
        "not_provided": "未提供",
        "executive_summary": "执行摘要",
        "key_points": "关键要点",
        "decisions": "明确决定",
        "action_items": "待办事项",
        "open_questions": "开放问题",
        "risks": "风险",
        "disagreements": "分歧与未达成共识",
        "speaker_summaries": "说话人摘要",
        "main_points": "主要观点",
        "speaker_questions": "提出的问题",
        "commitments": "作出的承诺",
        "concerns": "关注点",
        "user_questions": "用户问题",
        "quality_notes": "质量说明",
        "generated_files": "生成文件",
        "analysis_file": "内容分析",
        "timeline_file": "主题时间轴",
        "source_index_file": "来源索引",
        "task": "任务",
        "owner": "负责人",
        "deadline": "截止时间",
        "status": "状态",
        "confidence": "置信度",
        "evidence": "依据",
        "content": "内容",
        "main_speakers": "主要说话人",
        "transcript_mode": "使用文本",
        "message": "说明",
        "not_explicit": "未明确",
        "none_supported": "未从录音中提取到有充分依据的项目。",
        "no_actions": "未从录音中提取到明确待办事项。",
        "none_for_speaker": "未提取到明确内容",
        "no_user_questions": "未提供初始问题。",
        "quality_hint": "质量提示",
        "timeline_suffix": "主题时间轴",
        "source_text_note": "证据原文保持录音转录语言，未作翻译。",
        "overview": "录音包含{cue_count}条字幕、{speaker_count}个匿名说话人，主要围绕{topic}展开。",
        "quality_critical": "存在critical问题，结论必须结合原始cue复核。",
        "quality_warning": "存在warning，相关术语、UNKNOWN或短字幕需人工抽听。",
        "quality_clear": "技术复核未发现critical或warning。",
        "raw_fallback": "文本清理未完成，已使用原始ASR文本；",
    },
    "English": {
        "default_title": "Meeting analysis",
        "default_timeline_title": "Meeting",
        "basic_information": "Basic information",
        "date": "Date",
        "topic": "Topic",
        "duration": "Duration",
        "languages": "Languages",
        "speakers": "Speakers",
        "analysis_source": "Analysis source",
        "not_provided": "Not provided",
        "executive_summary": "Executive summary",
        "key_points": "Key points",
        "decisions": "Confirmed decisions",
        "action_items": "Action items",
        "open_questions": "Open questions",
        "risks": "Risks",
        "disagreements": "Disagreements and unresolved consensus",
        "speaker_summaries": "Speaker summaries",
        "main_points": "Main points",
        "speaker_questions": "Questions raised",
        "commitments": "Commitments",
        "concerns": "Concerns",
        "user_questions": "User questions",
        "quality_notes": "Quality notes",
        "generated_files": "Generated files",
        "analysis_file": "Content analysis",
        "timeline_file": "Topic timeline",
        "source_index_file": "Source index",
        "task": "Task",
        "owner": "Owner",
        "deadline": "Deadline",
        "status": "Status",
        "confidence": "Confidence",
        "evidence": "Evidence",
        "content": "Content",
        "main_speakers": "Main speakers",
        "transcript_mode": "Transcript mode",
        "message": "Note",
        "not_explicit": "Not stated",
        "none_supported": "No sufficiently supported item was extracted from the recording.",
        "no_actions": "No explicit action item was extracted from the recording.",
        "none_for_speaker": "No explicit content extracted",
        "no_user_questions": "No initial questions were provided.",
        "quality_hint": "Quality flag",
        "timeline_suffix": "Topic timeline",
        "source_text_note": "Evidence source text is preserved in the original transcript language and is not translated.",
        "overview": "The recording contains {cue_count} subtitle cues and {speaker_count} anonymous speakers, mainly concerning {topic}.",
        "quality_critical": "Critical issues exist; conclusions must be checked against the original cues.",
        "quality_warning": "Warnings exist; affected terminology, UNKNOWN attribution, or short cues require listening review.",
        "quality_clear": "Technical review found no critical issues or warnings.",
        "raw_fallback": "Text cleaning was incomplete, so the raw ASR transcript was used; ",
    },
    "Japanese": {
        "default_title": "会議分析",
        "default_timeline_title": "会議",
        "basic_information": "基本情報",
        "date": "日付",
        "topic": "議題",
        "duration": "時間",
        "languages": "言語",
        "speakers": "話者",
        "analysis_source": "分析対象テキスト",
        "not_provided": "未提供",
        "executive_summary": "概要",
        "key_points": "重要ポイント",
        "decisions": "確認済みの決定事項",
        "action_items": "アクション項目",
        "open_questions": "未解決の質問",
        "risks": "リスク",
        "disagreements": "相違点と未合意事項",
        "speaker_summaries": "話者別要約",
        "main_points": "主な発言",
        "speaker_questions": "提起した質問",
        "commitments": "約束事項",
        "concerns": "懸念事項",
        "user_questions": "ユーザー質問",
        "quality_notes": "品質に関する注記",
        "generated_files": "生成ファイル",
        "analysis_file": "内容分析",
        "timeline_file": "トピックタイムライン",
        "source_index_file": "出典索引",
        "task": "タスク",
        "owner": "担当者",
        "deadline": "期限",
        "status": "状態",
        "confidence": "信頼度",
        "evidence": "根拠",
        "content": "内容",
        "main_speakers": "主な話者",
        "transcript_mode": "使用テキスト",
        "message": "説明",
        "not_explicit": "明示なし",
        "none_supported": "録音から十分な根拠のある項目を抽出できませんでした。",
        "no_actions": "録音から明示的なアクション項目を抽出できませんでした。",
        "none_for_speaker": "明示的な内容は抽出されませんでした",
        "no_user_questions": "事前質問はありません。",
        "quality_hint": "品質上の注意",
        "timeline_suffix": "トピックタイムライン",
        "source_text_note": "根拠の原文は録音の転写言語のまま保持され、翻訳されていません。",
        "overview": "録音には{cue_count}件の字幕と{speaker_count}人の匿名話者が含まれ、主に{topic}について扱っています。",
        "quality_critical": "critical問題があります。結論は元のcueと照合する必要があります。",
        "quality_warning": "warningがあります。該当する用語、UNKNOWN、短い字幕は音声確認が必要です。",
        "quality_clear": "技術レビューではcriticalまたはwarningは見つかりませんでした。",
        "raw_fallback": "テキスト整形が完了していないため、元のASRテキストを使用しました；",
    },
}

ENGLISH_STOPWORDS = {
    "a", "about", "after", "again", "all", "also", "am", "an", "and",
    "are", "as", "at", "be", "because", "been", "before", "being", "but",
    "by", "can", "could", "did", "do", "does", "doing", "for", "from",
    "had", "has", "have", "he", "her", "here", "him", "his", "how", "i",
    "if", "in", "into", "is", "it", "its", "just", "like", "may", "me",
    "more", "most", "my", "no", "not", "now", "of", "on", "one", "or",
    "our", "out", "really", "she", "should", "so", "some", "that", "the",
    "their", "them", "then", "there", "these", "they", "this", "those",
    "to", "two", "up", "very", "was", "we", "were", "what", "when",
    "which", "who", "will", "with", "would", "you", "your",
}

CJK_STOPWORDS = {
    "これ", "それ", "あれ", "ここ", "そこ", "です", "ます", "する", "した",
    "して", "いる", "ある", "なる", "から", "まで", "ので", "こと", "もの",
    "よう", "ため", "今回", "という", "そして", "しかし", "この", "その",
    "我们", "这个", "那个", "然后", "因为", "所以", "可以", "就是", "一个",
    "录音", "会议", "内容", "讨论", "提到", "什么", "哪些", "有没有",
}

DECISION_PATTERNS = (
    re.compile(
        r"\b(?:we|the team|everyone)\s+(?:have\s+)?"
        r"(?:agreed|decided|approved|rejected)\b",
        re.I,
    ),
    re.compile(r"\bit\s+(?:was|is)\s+(?:agreed|decided|approved)\b", re.I),
    re.compile(r"(?:決定|合意|承認|却下)(?:しました|した|された|です)", re.I),
    re.compile(r"(?:决定|达成一致|批准|否决)(?:了|为|采用)", re.I),
)

DECISION_EXCLUSIONS = re.compile(
    r"\bconclusion\b|we can conclude|result(?:s)? (?:show|indicate)|"
    r"suggest|propos|might|could|should|maybe|perhaps|"
    r"検討|提案|可能性|仮定|结论|结果表明|建议|可能",
    re.I,
)

ACTION_PATTERNS = (
    re.compile(r"\bI(?:'ll| will)\s+(?!present\b|talk\b|discuss\b|explain\b|show\b)", re.I),
    re.compile(r"\bI\s+(?:can|shall)\s+(?:send|prepare|check|confirm|update|contact|review)\b", re.I),
    re.compile(r"私が.{0,40}(?:対応します|確認します|送ります|準備します|やります)"),
    re.compile(r"我(?:会|来).{0,40}(?:发送|准备|确认|检查|联系|更新|整理)"),
)

ACTION_EXCLUSIONS = re.compile(
    r"\b(?:present|represent|introduce|talk about|discuss|explain|show)\b"
    r".{0,40}\b(?:research|study|presentation|title)\b|"
    r"(?:発表|説明|紹介)します|(?:介绍|说明|展示)",
    re.I,
)

OPEN_QUESTION_PATTERN = re.compile(
    r"remains? open|still need to decide|not (?:yet )?decided|unresolved|TBD|"
    r"未解決|未決|まだ決ま|今後検討|合意に至っていない|"
    r"尚未决定|仍未解决|还需要决定|待讨论",
    re.I,
)

RISK_PATTERN = re.compile(
    r"\brisk\b|\bconcern\b|\bproblem\b|\bissue\b|\buncertain\b|"
    r"\bfail(?:ure|ed)?\b|\bdifficult(?:y)?\b|"
    r"リスク|懸念|問題|課題|難し|不確実|风险|担忧|问题|困难|不确定",
    re.I,
)

DISAGREEMENT_PATTERNS = (
    ("explicit_opposition", re.compile(r"\bI disagree\b|\bdo not agree\b|反対|同意できない|不同意", re.I)),
    ("different_interpretation", re.compile(r"my understanding is|I interpret|解釈が違|認識が違|我的理解是|解释不同", re.I)),
    ("no_consensus", re.compile(r"no consensus|did not agree|合意に至っていない|共识尚未形成", re.I)),
)

DEADLINE_PATTERN = re.compile(
    r"\bby\s+(?P<deadline>(?:tomorrow|today|next\s+\w+|"
    r"\w+day|\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}))\b|"
    r"(?P<cjk>(?:明日|今日|来週|今週|\d{1,2}月\d{1,2}日)(?:までに)?)",
    re.I,
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise TypeError(f"JSON顶层必须是对象：{path}")
    return value


def normalize_output_language(value: object) -> tuple[str | None, str]:
    requested = str(value).strip() if value is not None else None
    if not requested:
        return requested, "Chinese"
    normalized = OUTPUT_LANGUAGE_ALIASES.get(requested.casefold())
    if normalized is None:
        supported = "Chinese/English/Japanese (zh/en/ja)"
        raise ValueError(
            f"不支持的output_language：{requested!r}；支持值：{supported}"
        )
    return requested, normalized


def report_text(language: str) -> dict[str, str]:
    return REPORT_TEXT[language]


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(
                value,
                file,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            file.write("\n")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def resolve_path(value: str | Path | None, base: Path) -> Path | None:
    if value is None or not str(value).strip():
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        cwd_candidate = Path.cwd() / path
        path = cwd_candidate if cwd_candidate.exists() else base / path
    return path.resolve()


def preferred_speaker(cue: dict[str, Any]) -> str:
    value = cue.get("speaker_id") or cue.get("speaker") or "UNKNOWN"
    return str(value).strip() or "UNKNOWN"


def classify_language(text: str) -> str:
    japanese = bool(re.search(r"[\u3040-\u30ff]", text))
    cjk = bool(re.search(r"[\u3400-\u9fff]", text))
    latin = bool(re.search(r"[A-Za-z]", text))
    if japanese and latin:
        return "Mixed"
    if japanese:
        return "Japanese"
    if cjk and latin:
        return "Mixed"
    if cjk:
        return "Chinese"
    if latin:
        return "English"
    return "Other"


def tokenize(text: str) -> list[str]:
    lowered = text.casefold()
    tokens = [
        token
        for token in re.findall(r"[a-z][a-z0-9+.-]{2,}", lowered)
        if token not in ENGLISH_STOPWORDS and not token.isdigit()
    ]
    for sequence in re.findall(r"[\u3040-\u30ff\u3400-\u9fff]{2,}", text):
        if sequence not in CJK_STOPWORDS:
            tokens.append(sequence)
        if len(sequence) >= 4:
            tokens.extend(
                sequence[index:index + 2]
                for index in range(len(sequence) - 1)
                if sequence[index:index + 2] not in CJK_STOPWORDS
            )
    return tokens


def cue_tokens(cues: Sequence[dict[str, Any]], start: int, end: int) -> set[str]:
    result: set[str] = set()
    for cue in cues[start:end]:
        result.update(tokenize(cue["text"]))
    return result


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 1.0
    return len(left & right) / len(left | right)


def normalize_cues(raw_cues: object) -> list[dict[str, Any]]:
    if not isinstance(raw_cues, list) or not raw_cues:
        raise TypeError("transcript.cues必须是非空数组。")
    result: list[dict[str, Any]] = []
    previous_start = -math.inf
    for index, value in enumerate(raw_cues):
        if not isinstance(value, dict):
            raise TypeError(f"cue {index}不是对象。")
        try:
            start = float(value["start_time"])
            end = float(value["end_time"])
        except (KeyError, TypeError, ValueError) as error:
            raise TypeError(f"cue {index}时间字段无效。") from error
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError(f"cue {index}时间必须有限。")
        if start < previous_start or end < start or start < 0.0:
            raise ValueError(f"cue {index}时间顺序无效。")
        text = str(value.get("text") or "").strip()
        result.append(
            {
                "index": index,
                "start_time": start,
                "end_time": end,
                "speaker": preferred_speaker(value),
                "text": text,
                "language": classify_language(text),
            }
        )
        previous_start = start
    return result


def dominant_language(cues: Sequence[dict[str, Any]], start: int, end: int) -> str:
    counts = Counter(cue["language"] for cue in cues[start:end])
    return counts.most_common(1)[0][0] if counts else "Other"


def build_segments(cues: list[dict[str, Any]]) -> list[tuple[int, int]]:
    boundaries = [0]
    segment_start = 0
    for index in range(1, len(cues)):
        elapsed = cues[index]["start_time"] - cues[segment_start]["start_time"]
        gap = cues[index]["start_time"] - cues[index - 1]["end_time"]
        enough_cues = index - segment_start >= 12
        boundary = gap >= 18.0

        if not boundary and enough_cues and elapsed >= 120.0:
            left_start = max(segment_start, index - 10)
            right_end = min(len(cues), index + 10)
            similarity = jaccard(
                cue_tokens(cues, left_start, index),
                cue_tokens(cues, index, right_end),
            )
            left_language = dominant_language(cues, left_start, index)
            right_language = dominant_language(cues, index, right_end)
            marker = bool(
                re.search(
                    r"^(?:next|now|moving on|では|次に|続いて|それでは|接下来|下面)",
                    cues[index]["text"],
                    re.I,
                )
            )
            boundary = (
                similarity < 0.035
                or (left_language != right_language and elapsed >= 180.0)
                or marker
            )

        if elapsed >= 600.0:
            boundary = True

        if boundary:
            boundaries.append(index)
            segment_start = index

    boundaries.append(len(cues))
    raw_segments = [
        (boundaries[index], boundaries[index + 1])
        for index in range(len(boundaries) - 1)
        if boundaries[index + 1] > boundaries[index]
    ]
    segments: list[tuple[int, int]] = []
    index = 0
    while index < len(raw_segments):
        start, end = raw_segments[index]
        duration = cues[end - 1]["end_time"] - cues[start]["start_time"]
        if (end - start < 3 or duration < 10.0) and index + 1 < len(raw_segments):
            _, next_end = raw_segments[index + 1]
            segments.append((start, next_end))
            index += 2
        else:
            segments.append((start, end))
            index += 1
    return segments


def best_indices_from_candidates(
    cues: list[dict[str, Any]], candidates: Sequence[int], limit: int
) -> list[int]:
    token_frequency = Counter(
        token for index in candidates for token in tokenize(cues[index]["text"])
    )
    scored: list[tuple[float, int]] = []
    for index in candidates:
        text = cues[index]["text"]
        tokens = tokenize(text)
        if len(text) < 12 or not tokens:
            continue
        score = sum(1.0 / math.sqrt(token_frequency[token]) for token in set(tokens))
        score += min(len(text), 180) / 180.0
        scored.append((score, index))
    chosen: list[int] = []
    for _, index in sorted(scored, reverse=True):
        if all(abs(index - other) >= 3 for other in chosen):
            chosen.append(index)
        if len(chosen) >= limit:
            break
    if not chosen and candidates:
        chosen = [candidates[0]]
    return sorted(chosen)


def representative_indices(
    cues: list[dict[str, Any]], start: int, end: int, limit: int = 3
) -> list[int]:
    candidates = list(range(start, end))
    return best_indices_from_candidates(cues, candidates, limit)


def top_terms(cues: Sequence[dict[str, Any]], limit: int = 4) -> list[str]:
    counts = Counter(token for cue in cues for token in tokenize(cue["text"]))
    return [token for token, _ in counts.most_common(limit)]


def source_text_for(cues: Sequence[dict[str, Any]], indices: Sequence[int]) -> str:
    return "\n".join(
        f"[{cues[index]['speaker']}] {cues[index]['text']}" for index in indices
    )


def make_evidence(
    *,
    identifier: str,
    category: str,
    cues: list[dict[str, Any]],
    indices: Iterable[int],
    confidence: float,
    index_entries: dict[str, Any],
    **fields: Any,
) -> dict[str, Any]:
    cue_indices = sorted(set(int(index) for index in indices))
    if not cue_indices:
        raise ValueError(f"证据项缺少cue：{identifier}")
    speakers = list(
        dict.fromkeys(cues[index]["speaker"] for index in cue_indices)
    )
    item = {
        "id": identifier,
        **fields,
        "start_time": min(cues[index]["start_time"] for index in cue_indices),
        "end_time": max(cues[index]["end_time"] for index in cue_indices),
        "speakers": speakers,
        "cue_indices": cue_indices,
        "source_text": source_text_for(cues, cue_indices),
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
    }
    index_entries[identifier] = {
        "category": category,
        "start_time": item["start_time"],
        "end_time": item["end_time"],
        "speakers": item["speakers"],
        "cue_indices": item["cue_indices"],
        "source_text": item["source_text"],
        "confidence": item["confidence"],
        "evidence_status": item.get("evidence_status", "explicit"),
    }
    return item


def extract_review_flags(review: dict[str, Any] | None) -> dict[int, list[str]]:
    flags: dict[int, list[str]] = defaultdict(list)
    if not review:
        return flags
    issues = review.get("issues")
    if not isinstance(issues, dict):
        return flags
    for priority, items in issues.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "review_issue")
            indices: list[int] = []
            if isinstance(item.get("cue_index"), int):
                indices.append(item["cue_index"])
            if isinstance(item.get("cue_indices"), list):
                indices.extend(
                    value for value in item["cue_indices"] if isinstance(value, int)
                )
            for index in indices:
                flags[index].append(f"{priority}:{code}")
    return flags


def attach_flags(item: dict[str, Any], flags: dict[int, list[str]]) -> None:
    values = sorted(
        {
            flag
            for index in item.get("cue_indices", [])
            for flag in flags.get(index, [])
        }
    )
    if values:
        item["review_flags"] = values


def format_time(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def citation(item: dict[str, Any]) -> str:
    speakers = ", ".join(item.get("speakers", []))
    return (
        f"[{format_time(float(item['start_time']))}–"
        f"{format_time(float(item['end_time']))}, {speakers}]"
    )


def select_transcript(job_dir: Path, override: Path | None) -> tuple[Path, bool]:
    if override is not None:
        path = override.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"指定transcript不存在：{path}")
        return path, path.name == "transcript_final.json"

    manifest_path = job_dir / "pipeline_manifest.json"
    manifest = load_json(manifest_path)
    cleaning_status: object = None
    postprocessing = manifest.get("postprocessing")
    if isinstance(postprocessing, dict):
        cleaning = postprocessing.get("text_cleaning")
        if isinstance(cleaning, dict):
            cleaning_status = cleaning.get("status")
    complete = manifest.get("complete_pipeline")
    if cleaning_status is None and isinstance(complete, dict):
        cleaning_status = complete.get("text_cleaning_status")

    cleaned = job_dir / "transcript_cleaned.json"
    if cleaning_status == "completed" and cleaned.is_file():
        return cleaned.resolve(), False
    final = job_dir / "transcript_final.json"
    if final.is_file():
        return final.resolve(), True
    raise FileNotFoundError("transcript_cleaned.json和transcript_final.json均不存在。")


def context_value(context: dict[str, Any], key: str, override: Any) -> Any:
    return override if override not in (None, []) else context.get(key)


def question_query_tokens(question: str) -> set[str]:
    cleaned = re.sub(
        r"录音|会议|有没有|是否|什么时候|哪里|出现|提到|讨论|相关|内容|"
        r"what|when|where|recording|meeting|mention|discuss",
        " ",
        question,
        flags=re.I,
    )
    return set(tokenize(cleaned))


def retrieve_question_cues(
    question: str, cues: list[dict[str, Any]], limit: int = 4
) -> list[int]:
    query = question_query_tokens(question)
    if not query:
        return []
    scored: list[tuple[int, int]] = []
    lowered_question = question.casefold()
    for cue in cues:
        text = cue["text"]
        tokens = set(tokenize(text))
        score = len(query & tokens)
        for token in query:
            if len(token) >= 3 and token in text.casefold():
                score += 2
        if score:
            scored.append((score, cue["index"]))
    if not scored:
        return []
    best_score = max(score for score, _ in scored)
    if best_score < 2 and len(query) > 1:
        return []
    chosen = [index for score, index in sorted(scored, reverse=True) if score >= best_score][:limit]
    del lowered_question
    return sorted(chosen)


def evidence_content(item: dict[str, Any]) -> str:
    for key in (
        "content",
        "task",
        "decision",
        "question",
        "risk",
        "description",
        "summary",
        "title",
    ):
        value = item.get(key)
        if value:
            return str(value)
    return str(item.get("source_text") or "")


def build_markdown(analysis: dict[str, Any], output_path: Path) -> str:
    metadata = analysis["metadata"]
    labels = report_text(metadata["output_language"])
    title = metadata.get("meeting_title") or labels["default_title"]
    missing = labels["not_provided"]
    lines = [f"# {title}", "", f"## {labels['basic_information']}", ""]
    lines.extend(
        [
            f"- {labels['date']}：{metadata.get('meeting_date') or missing}",
            f"- {labels['topic']}：{metadata.get('meeting_topic') or missing}",
            f"- {labels['duration']}：{format_time(float(analysis['audio_duration']))}",
            f"- {labels['languages']}：{', '.join(analysis['languages'])}",
            f"- {labels['speakers']}：{', '.join(item['speaker'] for item in analysis['speakers'])}",
            f"- {labels['analysis_source']}：{analysis['source_files']['transcript']}",
            f"- {labels['evidence']}：{labels['source_text_note']}",
            "",
            f"## {labels['executive_summary']}",
            "",
        ]
    )
    summary = analysis["executive_summary"]
    lines.append(str(summary.get("overview") if isinstance(summary, dict) else summary))

    def render_evidence_section(title_key: str, key: str, text_key: str) -> None:
        lines.extend(["", f"## {labels[title_key]}", ""])
        items = analysis[key]
        if not items:
            lines.append(labels["none_supported"])
            return
        for item in items:
            value = item.get(text_key) or evidence_content(item)
            lines.append(f"- {value} {citation(item)}")
            if item.get("review_flags"):
                lines.append(
                    f"  - {labels['quality_hint']}：{', '.join(item['review_flags'])}"
                )

    render_evidence_section("key_points", "key_points", "content")
    render_evidence_section("decisions", "decisions", "decision")

    lines.extend(["", f"## {labels['action_items']}", ""])
    if analysis["action_items"]:
        lines.extend(
            [
                "| {task} | {owner} | {deadline} | {status} | {confidence} | {evidence} |".format(
                    **{key: labels[key] for key in ("task", "owner", "deadline", "status", "confidence", "evidence")}
                ),
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in analysis["action_items"]:
            lines.append(
                "| {task} | {owner} | {deadline} | {status} | {confidence:.2f} | {source} |".format(
                    task=str(item["task"]).replace("|", "\\|"),
                    owner=item.get("owner") or labels["not_explicit"],
                    deadline=item.get("deadline") or labels["not_explicit"],
                    status=item.get("status") or labels["not_explicit"],
                    confidence=float(item["confidence"]),
                    source=citation(item),
                )
            )
    else:
        lines.append(labels["no_actions"])

    render_evidence_section("open_questions", "open_questions", "question")
    render_evidence_section("risks", "risks", "risk")
    render_evidence_section("disagreements", "disagreements", "description")

    lines.extend(["", f"## {labels['speaker_summaries']}", ""])
    for speaker in analysis["speaker_summaries"]:
        lines.extend([f"### {speaker['speaker']}", ""])
        for label_key, key in (
            ("main_points", "main_points"),
            ("speaker_questions", "questions"),
            ("commitments", "commitments"),
            ("concerns", "concerns"),
        ):
            values = speaker.get(key, [])
            lines.append(f"- {labels[label_key]}：")
            if values:
                for item in values:
                    lines.append(f"  - {evidence_content(item)} {citation(item)}")
            else:
                lines.append(f"  - {labels['none_for_speaker']}")
        lines.append("")

    lines.extend([f"## {labels['user_questions']}", ""])
    if analysis["user_questions"]:
        for item in analysis["user_questions"]:
            lines.extend([f"### {item['question']}", "", item["answer"], ""])
            if item.get("found"):
                lines.extend([f"{labels['evidence']}：{citation(item)}", ""])
    else:
        lines.append(labels["no_user_questions"])

    quality = analysis["quality_notes"]
    lines.extend(
        [
            "",
            f"## {labels['quality_notes']}",
            "",
            f"- {labels['transcript_mode']}：{quality['transcript_mode']}",
            f"- critical：{quality['critical_count']}",
            f"- warning：{quality['warning_count']}",
            f"- {labels['message']}：{quality['message']}",
            f"- {labels['evidence']}：{quality['source_text_note']}",
            "",
            f"## {labels['generated_files']}",
            "",
            f"- {labels['analysis_file']}：{output_path / 'meeting_analysis.json'}",
            f"- {labels['timeline_file']}：{output_path / 'meeting_timeline.md'}",
            f"- {labels['source_index_file']}：{output_path / 'meeting_source_index.json'}",
            "",
        ]
    )
    return "\n".join(lines)


def build_timeline_markdown(analysis: dict[str, Any]) -> str:
    metadata = analysis["metadata"]
    labels = report_text(metadata["output_language"])
    title = metadata.get("meeting_title") or labels["default_timeline_title"]
    lines = [f"# {title}：{labels['timeline_suffix']}", "", labels["source_text_note"], ""]
    for item in analysis["timeline"]:
        evidence_citation = (
            f"[{format_time(item['evidence_start_time'])}–"
            f"{format_time(item['evidence_end_time'])}, {', '.join(item['speakers'])}]"
        )
        lines.extend(
            [
                f"## {format_time(item['start_time'])}–{format_time(item['end_time'])}　{item['title']}",
                "",
                f"- {labels['main_speakers']}：{', '.join(item['speakers'])}",
                f"- {labels['content']}：{item['summary']}",
                f"- {labels['evidence']}：{evidence_citation}",
                f"- {labels['confidence']}：{item['confidence']:.2f}",
                "",
            ]
        )
    quality = analysis["quality_notes"]
    lines.extend(
        [
            f"## {labels['quality_notes']}",
            "",
            f"critical={quality['critical_count']}，warning={quality['warning_count']}；{quality['message']}",
            "",
        ]
    )
    return "\n".join(lines)


def analyze(
    *,
    job_dir: Path,
    transcript_path: Path,
    used_raw_fallback: bool,
    review_path: Path | None,
    context: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    transcript = load_json(transcript_path)
    cues = normalize_cues(transcript.get("cues"))
    review = load_json(review_path) if review_path and review_path.is_file() else None
    review_flags = extract_review_flags(review)
    source_entries: dict[str, Any] = {}
    requested_output_language, output_language = normalize_output_language(
        context.get("output_language")
    )
    labels = report_text(output_language)

    audio_duration = max(cue["end_time"] for cue in cues)
    if review:
        summary = review.get("summary")
        if isinstance(summary, dict):
            try:
                reported = float(summary.get("audio_duration_seconds"))
                if math.isfinite(reported) and reported >= audio_duration:
                    audio_duration = reported
            except (TypeError, ValueError):
                pass

    segments = build_segments(cues)
    topic_segments: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    for number, (start, end) in enumerate(segments, 1):
        evidence_indices = representative_indices(cues, start, end)
        terms = top_terms(cues[start:end])
        title = " / ".join(terms[:3]) if terms else f"Topic {number}"
        summary_indices = [
            index for index in evidence_indices if len(cues[index]["text"]) >= 12
        ] or evidence_indices
        representative_text = " ".join(
            cues[index]["text"] for index in summary_indices if cues[index]["text"]
        )
        summary_text = representative_text[:700]
        topic = make_evidence(
            identifier=f"topic-{number:03d}",
            category="topic_segments",
            cues=cues,
            indices=evidence_indices,
            confidence=0.72,
            index_entries=source_entries,
            title=title,
            summary=summary_text,
            segment_start_time=cues[start]["start_time"],
            segment_end_time=cues[end - 1]["end_time"],
            evidence_status="inferred",
        )
        attach_flags(topic, review_flags)
        topic_segments.append(topic)
        timeline_item = make_evidence(
            identifier=f"timeline-{number:03d}",
            category="timeline",
            cues=cues,
            indices=evidence_indices,
            confidence=0.72,
            index_entries=source_entries,
            title=title,
            summary=summary_text,
            segment_start_time=cues[start]["start_time"],
            segment_end_time=cues[end - 1]["end_time"],
            evidence_status="inferred",
        )
        evidence_start_time = timeline_item["start_time"]
        evidence_end_time = timeline_item["end_time"]
        timeline_item.update(
            {
                "start_time": cues[start]["start_time"],
                "end_time": cues[end - 1]["end_time"],
                "evidence_start_time": evidence_start_time,
                "evidence_end_time": evidence_end_time,
            }
        )
        source_entries[timeline_item["id"]].update(
            {
                "start_time": timeline_item["start_time"],
                "end_time": timeline_item["end_time"],
                "evidence_start_time": evidence_start_time,
                "evidence_end_time": evidence_end_time,
            }
        )
        attach_flags(timeline_item, review_flags)
        timeline.append(timeline_item)

    key_points: list[dict[str, Any]] = []
    for number, topic in enumerate(topic_segments[:8], 1):
        point = make_evidence(
            identifier=f"key-{number:03d}",
            category="key_points",
            cues=cues,
            indices=topic["cue_indices"],
            confidence=0.7,
            index_entries=source_entries,
            content=topic["summary"],
            topic=topic["title"],
            evidence_status="inferred",
        )
        attach_flags(point, review_flags)
        key_points.append(point)

    decisions: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    open_questions: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    seen: dict[str, set[str]] = defaultdict(set)

    for cue in cues:
        text = cue["text"]
        normalized = " ".join(text.casefold().split())
        index = cue["index"]
        if (
            text
            and not DECISION_EXCLUSIONS.search(text)
            and any(pattern.search(text) for pattern in DECISION_PATTERNS)
            and normalized not in seen["decision"]
        ):
            seen["decision"].add(normalized)
            item = make_evidence(
                identifier=f"decision-{len(decisions) + 1:03d}",
                category="decisions",
                cues=cues,
                indices=[index],
                confidence=0.94,
                index_entries=source_entries,
                decision=text,
                decision_type="explicit",
                evidence_status="explicit",
            )
            attach_flags(item, review_flags)
            decisions.append(item)

        if (
            text
            and not ACTION_EXCLUSIONS.search(text)
            and any(pattern.search(text) for pattern in ACTION_PATTERNS)
            and normalized not in seen["action"]
        ):
            seen["action"].add(normalized)
            deadline_match = DEADLINE_PATTERN.search(text)
            deadline = None
            if deadline_match:
                deadline = deadline_match.group("deadline") or deadline_match.group("cjk")
            item = make_evidence(
                identifier=f"action-{len(actions) + 1:03d}",
                category="action_items",
                cues=cues,
                indices=[index],
                confidence=0.9,
                index_entries=source_entries,
                task=text,
                owner=cue["speaker"],
                deadline=deadline,
                status=labels["not_explicit"],
                evidence_status="explicit",
            )
            attach_flags(item, review_flags)
            actions.append(item)

        if text and OPEN_QUESTION_PATTERN.search(text) and normalized not in seen["open"]:
            seen["open"].add(normalized)
            item = make_evidence(
                identifier=f"open-question-{len(open_questions) + 1:03d}",
                category="open_questions",
                cues=cues,
                indices=[index],
                confidence=0.87,
                index_entries=source_entries,
                question=text,
                evidence_status="explicit",
            )
            attach_flags(item, review_flags)
            open_questions.append(item)

        if text and RISK_PATTERN.search(text) and normalized not in seen["risk"]:
            seen["risk"].add(normalized)
            item = make_evidence(
                identifier=f"risk-{len(risks) + 1:03d}",
                category="risks",
                cues=cues,
                indices=[index],
                confidence=0.78,
                index_entries=source_entries,
                risk=text,
                evidence_status="explicit",
            )
            attach_flags(item, review_flags)
            risks.append(item)

        for kind, pattern in DISAGREEMENT_PATTERNS:
            if text and pattern.search(text) and normalized not in seen["disagreement"]:
                seen["disagreement"].add(normalized)
                item = make_evidence(
                    identifier=f"disagreement-{len(disagreements) + 1:03d}",
                    category="disagreements",
                    cues=cues,
                    indices=[index],
                    confidence=0.9,
                    index_entries=source_entries,
                    description=text,
                    disagreement_type=kind,
                    evidence_status="explicit",
                )
                attach_flags(item, review_flags)
                disagreements.append(item)
                break

    decisions = decisions[:20]
    actions = actions[:30]
    open_questions = open_questions[:30]
    risks = risks[:40]
    disagreements = disagreements[:20]

    language_counts = Counter(cue["language"] for cue in cues)
    review_language_counts = (
        review.get("summary", {}).get("language_counts")
        if review and isinstance(review.get("summary"), dict)
        else None
    )
    if isinstance(review_language_counts, dict):
        languages = [
            str(language)
            for language, count in review_language_counts.items()
            if isinstance(count, (int, float)) and count > 0 and language != "Other"
        ]
    else:
        languages = [
            language for language, count in language_counts.most_common() if count > 0
        ]
    speaker_cues: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cue in cues:
        speaker_cues[cue["speaker"]].append(cue)

    speakers: list[dict[str, Any]] = []
    speaker_summaries: list[dict[str, Any]] = []
    for speaker in sorted(speaker_cues):
        own = speaker_cues[speaker]
        duration = sum(cue["end_time"] - cue["start_time"] for cue in own)
        own_languages = Counter(cue["language"] for cue in own)
        speakers.append(
            {
                "speaker": speaker,
                "cue_count": len(own),
                "speaking_duration": round(duration, 3),
                "language_counts": dict(own_languages),
            }
        )
        own_indices = best_indices_from_candidates(
            cues, [cue["index"] for cue in own], 5
        )
        if not own_indices:
            own_indices = [own[0]["index"]]
        speaker_slug = (
            re.sub(r"[^A-Za-z0-9]+", "-", speaker).strip("-").lower()
            or "unknown"
        )
        representative_evidence: list[dict[str, Any]] = []
        for number, index in enumerate(own_indices, 1):
            item = make_evidence(
                identifier=f"speaker-{speaker_slug}-main-{number:03d}",
                category="speaker_summaries.main_points",
                cues=cues,
                indices=[index],
                confidence=0.76,
                index_entries=source_entries,
                content=cues[index]["text"],
                evidence_status="explicit",
            )
            attach_flags(item, review_flags)
            representative_evidence.append(item)

        question_evidence: list[dict[str, Any]] = []
        question_cues = [
            cue for cue in own if "?" in cue["text"] or "？" in cue["text"]
        ][:3]
        for number, cue in enumerate(question_cues, 1):
            item = make_evidence(
                identifier=f"speaker-{speaker_slug}-question-{number:03d}",
                category="speaker_summaries.questions",
                cues=cues,
                indices=[cue["index"]],
                confidence=0.9,
                index_entries=source_entries,
                content=cue["text"],
                evidence_status="explicit",
            )
            attach_flags(item, review_flags)
            question_evidence.append(item)

        commitment_evidence: list[dict[str, Any]] = []
        for number, action in enumerate(
            [item for item in actions if item["owner"] == speaker][:3], 1
        ):
            item = make_evidence(
                identifier=f"speaker-{speaker_slug}-commitment-{number:03d}",
                category="speaker_summaries.commitments",
                cues=cues,
                indices=action["cue_indices"],
                confidence=float(action["confidence"]),
                index_entries=source_entries,
                content=action["task"],
                evidence_status="explicit",
            )
            attach_flags(item, review_flags)
            commitment_evidence.append(item)

        concern_evidence: list[dict[str, Any]] = []
        for number, risk in enumerate(
            [item for item in risks if speaker in item["speakers"]][:3], 1
        ):
            item = make_evidence(
                identifier=f"speaker-{speaker_slug}-concern-{number:03d}",
                category="speaker_summaries.concerns",
                cues=cues,
                indices=risk["cue_indices"],
                confidence=float(risk["confidence"]),
                index_entries=source_entries,
                content=risk["risk"],
                evidence_status="explicit",
            )
            attach_flags(item, review_flags)
            concern_evidence.append(item)

        all_speaker_evidence = [
            *representative_evidence,
            *question_evidence,
            *commitment_evidence,
            *concern_evidence,
        ]
        speaker_summaries.append(
            {
                "speaker": speaker,
                "main_points": representative_evidence[:3],
                "questions": question_evidence,
                "commitments": commitment_evidence,
                "concerns": concern_evidence,
                "evidence": all_speaker_evidence,
            }
        )

    questions = list(context.get("questions") or [])
    user_questions: list[dict[str, Any]] = []
    for number, question_value in enumerate(questions, 1):
        question = str(question_value).strip()
        if not question:
            continue
        lowered = question.casefold()
        indices: list[int] = []
        answer: str | None = None

        if re.search(r"主要讨论|main topic|what.*(?:meeting|recording).*(?:about|discuss)", lowered):
            indices = key_points[0]["cue_indices"] if key_points else []
            answer = key_points[0]["content"] if key_points else None
        elif re.search(r"每位说话人|each speaker|who (?:said|discussed)", lowered):
            indices = sorted(
                {item["cue_indices"][0] for summary in speaker_summaries for item in summary["evidence"][:1]}
            )
            separator = "; " if output_language == "English" else "；"
            colon = ": " if output_language == "English" else "："
            answer = separator.join(
                f"{summary['speaker']}{colon}{separator.join(evidence_content(item) for item in summary['main_points'][:2])}"
                for summary in speaker_summaries
            )
        elif re.search(r"明确决定|哪些决定|decision", lowered):
            indices = sorted({index for item in decisions for index in item["cue_indices"]})
            answer = "；".join(item["decision"] for item in decisions) or None
        elif re.search(r"待办|行动项|action item|todo", lowered):
            indices = sorted({index for item in actions for index in item["cue_indices"]})
            answer = "；".join(item["task"] for item in actions) or None
        else:
            indices = retrieve_question_cues(question, cues)
            if indices:
                answer = " ".join(cues[index]["text"] for index in indices)

        identifier = f"user-question-{number:03d}"
        if not indices or not answer:
            user_questions.append(
                {
                    "id": identifier,
                    "question": question,
                    "answer": NOT_FOUND,
                    "found": False,
                    "evidence_status": "not_found",
                }
            )
            continue
        item = make_evidence(
            identifier=identifier,
            category="user_questions",
            cues=cues,
            indices=indices,
            confidence=0.82,
            index_entries=source_entries,
            question=question,
            answer=answer,
            found=True,
            evidence_status="explicit" if len(indices) == 1 else "inferred",
        )
        attach_flags(item, review_flags)
        user_questions.append(item)

    review_summary = review.get("summary", {}) if review else {}
    if not isinstance(review_summary, dict):
        review_summary = {}
    critical_count = int(review_summary.get("critical_count") or 0)
    warning_count = int(review_summary.get("warning_count") or 0)
    quality_message = (
        labels["quality_critical"]
        if critical_count
        else (
            labels["quality_warning"]
            if warning_count
            else labels["quality_clear"]
        )
    )
    if used_raw_fallback:
        quality_message = labels["raw_fallback"] + quality_message

    terminology = [
        {"term": term, "source": "frequency"}
        for term in top_terms(cues, 20)
    ]
    if review and isinstance(review.get("unresolved_terms"), list):
        for item in review["unresolved_terms"][:50]:
            terminology.append({"term": item, "source": "review_unresolved"})

    metadata = {
        "meeting_title": context.get("meeting_title") or transcript_path.stem,
        "meeting_date": context.get("meeting_date"),
        "meeting_topic": context.get("meeting_topic"),
        "domain": context.get("domain"),
        "expected_speakers": context.get("expected_speakers"),
        "known_participants": list(context.get("known_participants") or []),
        "user_speaker_hint": context.get("user_speaker_hint"),
        "requested_output_language": requested_output_language,
        "output_language": output_language,
        "identified_speaker_count": sum(
            1 for speaker in speakers if speaker["speaker"] != "UNKNOWN"
        ),
        "unknown_speaker_present": any(
            speaker["speaker"] == "UNKNOWN" for speaker in speakers
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    overview = labels["overview"].format(
        cue_count=len(cues),
        speaker_count=metadata["identified_speaker_count"],
        topic=metadata["meeting_topic"]
        or (topic_segments[0]["title"] if topic_segments else labels["default_title"]),
    )
    analysis = {
        "schema_version": SCHEMA_VERSION,
        "metadata": metadata,
        "source_files": {
            "transcript": str(transcript_path),
            "review_package": str(review_path) if review_path and review_path.is_file() else None,
            "pipeline_manifest": str(job_dir / "pipeline_manifest.json"),
            "context": str(job_dir / "meeting_skill_input.json") if (job_dir / "meeting_skill_input.json").is_file() else None,
        },
        "audio_duration": round(audio_duration, 6),
        "languages": languages,
        "speakers": speakers,
        "executive_summary": {
            "overview": overview,
            "key_point_ids": [item["id"] for item in key_points[:5]],
            "decision_ids": [item["id"] for item in decisions],
            "action_item_ids": [item["id"] for item in actions],
            "open_question_ids": [item["id"] for item in open_questions],
        },
        "key_points": key_points,
        "topic_segments": topic_segments,
        "timeline": timeline,
        "decisions": decisions,
        "action_items": actions,
        "open_questions": open_questions,
        "risks": risks,
        "disagreements": disagreements,
        "speaker_summaries": speaker_summaries,
        "terminology": terminology,
        "user_questions": user_questions,
        "quality_notes": {
            "transcript_mode": "raw_asr_fallback" if used_raw_fallback else "cleaned",
            "critical_count": critical_count,
            "warning_count": warning_count,
            "message": quality_message,
            "source_text_note": labels["source_text_note"],
        },
    }
    source_index = {
        "schema_version": SCHEMA_VERSION,
        "transcript": str(transcript_path),
        "entries": source_entries,
    }
    atomic_write_json(output_dir / "meeting_analysis.json", analysis)
    atomic_write_json(output_dir / "meeting_source_index.json", source_index)
    atomic_write_text(
        output_dir / "meeting_analysis.md", build_markdown(analysis, output_dir)
    )
    atomic_write_text(
        output_dir / "meeting_timeline.md", build_timeline_markdown(analysis)
    )
    return analysis


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从已完成的多人转录生成可追溯会议分析。",
        allow_abbrev=False,
    )
    parser.add_argument("--job-dir", required=True, type=Path)
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--review-package", type=Path)
    parser.add_argument("--context-json", type=Path)
    parser.add_argument("--meeting-title")
    parser.add_argument("--meeting-date")
    parser.add_argument("--meeting-topic")
    parser.add_argument("--domain")
    parser.add_argument("--known-participant", action="append", default=[])
    parser.add_argument("--question", action="append", default=[])
    parser.add_argument("--output-language")
    parser.add_argument("--output-dir", type=Path)
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    job_dir = args.job_dir.expanduser().resolve()
    if not job_dir.is_dir():
        raise FileNotFoundError(f"Job目录不存在：{job_dir}")

    context: dict[str, Any] = {}
    context_path = resolve_path(args.context_json, job_dir)
    if context_path is not None:
        context = load_json(context_path)
    overrides = {
        "meeting_title": args.meeting_title,
        "meeting_date": args.meeting_date,
        "meeting_topic": args.meeting_topic,
        "domain": args.domain,
        "output_language": args.output_language,
    }
    for key, value in overrides.items():
        if value is not None:
            context[key] = value
    if args.known_participant:
        context["known_participants"] = list(args.known_participant)
    if args.question:
        context["questions"] = list(args.question)

    transcript_override = resolve_path(args.transcript, job_dir)
    transcript_path, raw_fallback = select_transcript(job_dir, transcript_override)
    review_path = resolve_path(args.review_package, job_dir)
    if review_path is None:
        candidate = job_dir / "transcript_review_package.json"
        review_path = candidate.resolve() if candidate.is_file() else None
    output_dir = resolve_path(args.output_dir, job_dir) or job_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    analysis = analyze(
        job_dir=job_dir,
        transcript_path=transcript_path,
        used_raw_fallback=raw_fallback,
        review_path=review_path,
        context=context,
        output_dir=output_dir,
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "transcript": str(transcript_path),
                "cue_count": sum(item["cue_count"] for item in analysis["speakers"]),
                "speaker_count": len(analysis["speakers"]),
                "topic_segment_count": len(analysis["topic_segments"]),
                "decision_count": len(analysis["decisions"]),
                "action_item_count": len(analysis["action_items"]),
                "question_count": len(analysis["user_questions"]),
                "output_dir": str(output_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> None:
    try:
        raise SystemExit(run())
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
