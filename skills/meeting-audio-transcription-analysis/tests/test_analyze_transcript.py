from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "analyze_transcript.py"
)
SPEC = importlib.util.spec_from_file_location(
    "analyze_transcript_under_test", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
analyzer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyzer)


def write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class AnalyzeTranscriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="meeting_analysis_test_"
        )
        self.addCleanup(self.temporary.cleanup)
        self.job_dir = Path(self.temporary.name)
        self.cues = [
            {
                "start_time": 0.0,
                "end_time": 2.0,
                "speaker": "Mapped Person",
                "speaker_id": "SPEAKER_00",
                "text": "Today, I will present my research on optical inspection.",
            },
            {
                "start_time": 2.2,
                "end_time": 5.0,
                "speaker": "Mapped Person",
                "speaker_id": "SPEAKER_00",
                "text": "The scientific conclusion is that localization remains stable.",
            },
            {
                "start_time": 5.2,
                "end_time": 7.0,
                "speaker": "Other Name",
                "speaker_id": "SPEAKER_01",
                "text": "We agreed to use option A.",
            },
            {
                "start_time": 7.2,
                "end_time": 9.0,
                "speaker": "Other Name",
                "speaker_id": "SPEAKER_01",
                "text": "I will send the report by tomorrow.",
            },
            {
                "start_time": 35.0,
                "end_time": 38.0,
                "speaker": "Mapped Person",
                "speaker_id": "SPEAKER_00",
                "text": "Defocus changes the optical edge profile.",
            },
            {
                "start_time": 38.2,
                "end_time": 40.0,
                "speaker": "Other Name",
                "speaker_id": "SPEAKER_01",
                "text": "The remaining calibration issue is still unresolved.",
            },
        ]
        write_json(
            self.job_dir / "transcript_final.json", {"cues": self.cues}
        )
        write_json(
            self.job_dir / "transcript_cleaned.json", {"cues": self.cues}
        )
        write_json(
            self.job_dir / "pipeline_manifest.json",
            {
                "status": "completed",
                "postprocessing": {
                    "text_cleaning": {"status": "completed"}
                },
            },
        )
        write_json(
            self.job_dir / "transcript_review_package.json",
            {
                "summary": {
                    "audio_duration_seconds": 40.0,
                    "critical_count": 0,
                    "warning_count": 0,
                    "language_counts": {"English": 6},
                },
                "issues": {"critical": [], "warning": [], "info": []},
                "unresolved_terms": [],
            },
        )
        self.context = {
            "meeting_title": "Optical test",
            "meeting_topic": "optical inspection",
            "questions": [
                "有哪些明确决定？",
                "有哪些待办事项？",
                "defocus什么时候出现？",
                "有没有讨论火星预算？",
            ],
        }

    def run_analysis(
        self, output_language: str | None = None
    ) -> dict[str, object]:
        transcript, raw = analyzer.select_transcript(self.job_dir, None)
        context = dict(self.context)
        if output_language is not None:
            context["output_language"] = output_language
        result = analyzer.analyze(
            job_dir=self.job_dir,
            transcript_path=transcript,
            used_raw_fallback=raw,
            review_path=self.job_dir / "transcript_review_package.json",
            context=context,
            output_dir=self.job_dir,
        )
        return result

    def test_prefers_cleaned_and_preserves_speaker_ids(self) -> None:
        result = self.run_analysis()
        self.assertEqual(
            Path(result["source_files"]["transcript"]).name,  # type: ignore[index]
            "transcript_cleaned.json",
        )
        speakers = {item["speaker"] for item in result["speakers"]}  # type: ignore[index]
        self.assertEqual(speakers, {"SPEAKER_00", "SPEAKER_01"})
        self.assertNotIn("Mapped Person", speakers)

    def test_scientific_conclusion_and_presentation_are_not_actions_or_decisions(self) -> None:
        result = self.run_analysis()
        decisions = result["decisions"]  # type: ignore[index]
        actions = result["action_items"]  # type: ignore[index]
        self.assertEqual(len(decisions), 1)
        self.assertIn("agreed", decisions[0]["decision"])
        self.assertEqual(len(actions), 1)
        self.assertIn("send the report", actions[0]["task"])
        self.assertEqual(actions[0]["owner"], "SPEAKER_01")
        self.assertEqual(actions[0]["deadline"], "tomorrow")

    def test_every_supported_claim_is_indexed(self) -> None:
        result = self.run_analysis()
        index = json.loads(
            (self.job_dir / "meeting_source_index.json").read_text(
                encoding="utf-8"
            )
        )
        for collection in (
            "key_points",
            "topic_segments",
            "timeline",
            "decisions",
            "action_items",
            "open_questions",
            "risks",
            "disagreements",
        ):
            for item in result[collection]:  # type: ignore[index]
                self.assertIn(item["id"], index["entries"])
                self.assertLessEqual(item["start_time"], item["end_time"])

    def test_question_answers_include_time_or_exact_not_found(self) -> None:
        result = self.run_analysis()
        questions = result["user_questions"]  # type: ignore[index]
        self.assertTrue(questions[0]["found"])
        self.assertTrue(questions[1]["found"])
        self.assertTrue(questions[2]["found"])
        self.assertFalse(questions[3]["found"])
        self.assertEqual(questions[3]["answer"], analyzer.NOT_FOUND)
        self.assertNotIn("cue_indices", questions[3])

    def test_outputs_are_written_without_temporary_files(self) -> None:
        self.run_analysis()
        for name in (
            "meeting_analysis.json",
            "meeting_analysis.md",
            "meeting_timeline.md",
            "meeting_source_index.json",
        ):
            self.assertTrue((self.job_dir / name).is_file())
        self.assertEqual(list(self.job_dir.glob(".*.tmp")), [])

    def test_output_language_controls_static_report_text(self) -> None:
        expectations = {
            "zh": ("Chinese", "## 执行摘要", "技术复核未发现"),
            "EN": ("English", "## Executive summary", "Technical review found"),
            "ja": ("Japanese", "## 概要", "技術レビューでは"),
        }
        for requested, (normalized, heading, quality_text) in expectations.items():
            with self.subTest(requested=requested):
                result = self.run_analysis(requested)
                metadata = result["metadata"]  # type: ignore[index]
                self.assertEqual(metadata["requested_output_language"], requested)
                self.assertEqual(metadata["output_language"], normalized)
                markdown = (self.job_dir / "meeting_analysis.md").read_text(
                    encoding="utf-8"
                )
                timeline = (self.job_dir / "meeting_timeline.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn(heading, markdown)
                self.assertIn(quality_text, markdown)
                self.assertIn("scientific conclusion", markdown)
                self.assertIn("scientific conclusion", timeline)

    def test_unsupported_output_language_fails_clearly(self) -> None:
        with self.assertRaisesRegex(ValueError, "不支持的output_language"):
            self.run_analysis("Klingon")

    def test_timeline_uses_full_segment_and_separate_evidence_range(self) -> None:
        result = self.run_analysis("English")
        for item in result["timeline"]:  # type: ignore[index]
            self.assertEqual(item["start_time"], item["segment_start_time"])
            self.assertEqual(item["end_time"], item["segment_end_time"])
            self.assertLessEqual(item["start_time"], item["evidence_start_time"])
            self.assertGreaterEqual(item["end_time"], item["evidence_end_time"])

    def test_speaker_summary_fields_are_traceable_evidence_objects(self) -> None:
        result = self.run_analysis()
        required = {
            "id",
            "start_time",
            "end_time",
            "speakers",
            "cue_indices",
            "source_text",
            "confidence",
        }
        for summary in result["speaker_summaries"]:  # type: ignore[index]
            for field in ("main_points", "questions", "commitments", "concerns"):
                for item in summary[field]:
                    self.assertTrue(required.issubset(item))
                    self.assertIn(item["id"], json.loads(
                        (self.job_dir / "meeting_source_index.json").read_text(
                            encoding="utf-8"
                        )
                    )["entries"])

    def test_not_found_sentence_stays_exact_in_english_report(self) -> None:
        result = self.run_analysis("English")
        missing = result["user_questions"][3]  # type: ignore[index]
        self.assertEqual(missing["answer"], analyzer.NOT_FOUND)
        markdown = (self.job_dir / "meeting_analysis.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(analyzer.NOT_FOUND, markdown)

    def test_executive_summary_does_not_count_unknown_as_identified_speaker(self) -> None:
        cues = [
            *self.cues,
            {
                "start_time": 40.2,
                "end_time": 42.0,
                "speaker": "UNKNOWN",
                "speaker_id": "UNKNOWN",
                "text": "Unattributed closing remark.",
            },
        ]
        write_json(self.job_dir / "transcript_final.json", {"cues": cues})
        write_json(self.job_dir / "transcript_cleaned.json", {"cues": cues})
        result = self.run_analysis("Chinese")
        metadata = result["metadata"]  # type: ignore[index]
        self.assertEqual(metadata["identified_speaker_count"], 2)
        self.assertTrue(metadata["unknown_speaker_present"])
        overview = result["executive_summary"]["overview"]  # type: ignore[index]
        self.assertIn("2个匿名说话人", overview)
        self.assertNotIn("3个匿名说话人", overview)


if __name__ == "__main__":
    unittest.main()
