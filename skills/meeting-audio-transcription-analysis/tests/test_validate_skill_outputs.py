from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "validate_skill_outputs.py"
)
SPEC = importlib.util.spec_from_file_location(
    "validate_skill_outputs_under_test", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class ValidateSkillOutputsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="meeting_skill_validation_test_"
        )
        self.addCleanup(self.temporary.cleanup)
        self.job_dir = Path(self.temporary.name)
        self.cues = [
            {
                "start_time": 1.0,
                "end_time": 2.0,
                "speaker": "Mapped Name",
                "speaker_id": "SPEAKER_00",
                "text": "We agreed to use option A.",
            },
            {
                "start_time": 2.1,
                "end_time": 3.0,
                "speaker": "Another Name",
                "speaker_id": "SPEAKER_01",
                "text": "I will send the report tomorrow.",
            },
        ]
        write_json(
            self.job_dir / "transcript_cleaned.json", {"cues": self.cues}
        )
        evidence = {
            "id": "key-001",
            "content": "The group explicitly selected option A.",
            "start_time": 1.0,
            "end_time": 2.0,
            "speakers": ["SPEAKER_00"],
            "cue_indices": [0],
            "source_text": "We agreed to use option A.",
            "confidence": 0.98,
        }
        self.analysis: dict[str, object] = {
            "schema_version": "1.0",
            "metadata": {},
            "source_files": {
                "transcript": str(
                    self.job_dir / "transcript_cleaned.json"
                )
            },
            "audio_duration": 3.0,
            "languages": ["English"],
            "speakers": [
                {"speaker": "SPEAKER_00", "cue_count": 1},
                {"speaker": "SPEAKER_01", "cue_count": 1},
            ],
            "executive_summary": "Option A was selected.",
            "key_points": [evidence],
            "topic_segments": [],
            "timeline": [],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "risks": [],
            "disagreements": [],
            "speaker_summaries": [],
            "terminology": [],
            "user_questions": [
                {
                    "id": "question-001",
                    "question": "Was Mars discussed?",
                    "answer": "录音中没有找到足以支持该结论的内容。",
                    "found": False,
                    "evidence_status": "not_found",
                }
            ],
            "quality_notes": [],
        }
        self.source_index: dict[str, object] = {
            "schema_version": "1.0",
            "transcript": str(
                self.job_dir / "transcript_cleaned.json"
            ),
            "entries": {
                "key-001": {
                    "category": "key_points",
                    "start_time": 1.0,
                    "end_time": 2.0,
                    "speakers": ["SPEAKER_00"],
                    "cue_indices": [0],
                    "source_text": "We agreed to use option A.",
                }
            },
        }

    def write_outputs(self) -> None:
        write_json(self.job_dir / "meeting_analysis.json", self.analysis)
        write_json(
            self.job_dir / "meeting_source_index.json", self.source_index
        )
        (self.job_dir / "meeting_analysis.md").write_text(
            "# Analysis\n", encoding="utf-8"
        )
        (self.job_dir / "meeting_timeline.md").write_text(
            "# Timeline\n", encoding="utf-8"
        )

    def test_valid_outputs_preserve_anonymous_speakers(self) -> None:
        self.write_outputs()
        result = validator.validate_outputs(self.job_dir)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["speaker_count"], 2)
        self.assertEqual(result["evidence_item_count"], 1)

    def test_missing_source_index_entry_fails(self) -> None:
        self.source_index["entries"] = {}
        self.write_outputs()
        result = validator.validate_outputs(self.job_dir)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("未登记" in message for message in result["errors"])
        )

    def test_mapped_names_cannot_replace_speaker_ids(self) -> None:
        speakers = self.analysis["speakers"]
        assert isinstance(speakers, list)
        speakers[0] = {"speaker": "Mapped Name", "cue_count": 1}
        self.write_outputs()
        result = validator.validate_outputs(self.job_dir)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("speaker_id集合" in message for message in result["errors"])
        )

    def test_not_found_question_requires_no_fabricated_source(self) -> None:
        self.write_outputs()
        result = validator.validate_outputs(self.job_dir)
        self.assertEqual(result["status"], "completed")
        entries = self.source_index["entries"]
        assert isinstance(entries, dict)
        self.assertNotIn("question-001", entries)

    def test_action_owner_must_be_recorded_speaker(self) -> None:
        action = deepcopy(self.analysis["key_points"][0])  # type: ignore[index]
        action.update(
            {
                "id": "action-001",
                "task": "Send the report",
                "owner": "Invented Person",
                "deadline": None,
                "status": "未明确",
            }
        )
        self.analysis["action_items"] = [action]
        entries = self.source_index["entries"]
        assert isinstance(entries, dict)
        entries["action-001"] = {
            "category": "action_items",
            "start_time": 1.0,
            "end_time": 2.0,
            "speakers": ["SPEAKER_00"],
            "cue_indices": [0],
            "source_text": "We agreed to use option A.",
        }
        self.write_outputs()
        result = validator.validate_outputs(self.job_dir)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("owner不是录音speaker标签" in message for message in result["errors"])
        )

    def test_timeline_accepts_full_segment_with_representative_evidence(self) -> None:
        timeline = deepcopy(self.analysis["key_points"][0])  # type: ignore[index]
        timeline.update(
            {
                "id": "timeline-001",
                "start_time": 1.0,
                "end_time": 3.0,
                "segment_start_time": 1.0,
                "segment_end_time": 3.0,
                "evidence_start_time": 1.0,
                "evidence_end_time": 2.0,
                "title": "Option A",
                "summary": "Representative evidence",
            }
        )
        self.analysis["timeline"] = [timeline]
        entries = self.source_index["entries"]
        assert isinstance(entries, dict)
        entries["timeline-001"] = {
            "category": "timeline",
            "start_time": 1.0,
            "end_time": 3.0,
            "evidence_start_time": 1.0,
            "evidence_end_time": 2.0,
            "speakers": ["SPEAKER_00"],
            "cue_indices": [0],
            "source_text": "We agreed to use option A.",
        }
        self.write_outputs()
        result = validator.validate_outputs(self.job_dir)
        self.assertEqual(result["status"], "completed")

    def test_speaker_summary_rejects_untraceable_strings(self) -> None:
        self.analysis["speaker_summaries"] = [
            {
                "speaker": "SPEAKER_00",
                "main_points": ["Untraceable summary"],
                "questions": [],
                "commitments": [],
                "concerns": [],
            }
        ]
        self.write_outputs()
        result = validator.validate_outputs(self.job_dir)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("可追溯证据对象" in message for message in result["errors"])
        )

    def test_transcript_start_time_regression_fails(self) -> None:
        self.cues[1]["start_time"] = 0.5
        write_json(
            self.job_dir / "transcript_cleaned.json", {"cues": self.cues}
        )
        self.write_outputs()
        result = validator.validate_outputs(self.job_dir)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("start_time发生倒退" in message for message in result["errors"])
        )

    def test_cue_and_evidence_beyond_audio_duration_fail(self) -> None:
        self.cues[1]["end_time"] = 4.0
        write_json(
            self.job_dir / "transcript_cleaned.json", {"cues": self.cues}
        )
        evidence = self.analysis["key_points"][0]  # type: ignore[index]
        assert isinstance(evidence, dict)
        evidence["start_time"] = 4.0
        evidence["end_time"] = 4.0
        entries = self.source_index["entries"]
        assert isinstance(entries, dict)
        entry = entries["key-001"]
        assert isinstance(entry, dict)
        entry["start_time"] = 4.0
        entry["end_time"] = 4.0
        self.write_outputs()
        result = validator.validate_outputs(self.job_dir)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("cue 1.end_time超出" in message for message in result["errors"])
        )
        self.assertTrue(
            any("key_points:key-001的时间超出" in message for message in result["errors"])
        )

    def test_duplicate_claim_id_fails_but_aggregate_evidence_does_not(self) -> None:
        duplicate = deepcopy(self.analysis["key_points"][0])  # type: ignore[index]
        duplicate["decision"] = "Option A"
        self.analysis["decisions"] = [duplicate]
        self.write_outputs()
        result = validator.validate_outputs(self.job_dir)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("重复claim id：key-001" in message for message in result["errors"])
        )

        self.analysis["decisions"] = []
        self.analysis["speaker_summaries"] = [
            {
                "speaker": "SPEAKER_00",
                "main_points": [deepcopy(self.analysis["key_points"][0])],  # type: ignore[index]
                "questions": [],
                "commitments": [],
                "concerns": [],
                "evidence": [deepcopy(self.analysis["key_points"][0])],  # type: ignore[index]
            }
        ]
        main_point = self.analysis["speaker_summaries"][0]["main_points"][0]  # type: ignore[index]
        assert isinstance(main_point, dict)
        main_point["id"] = "speaker-main-001"
        aggregate = self.analysis["speaker_summaries"][0]["evidence"][0]  # type: ignore[index]
        assert isinstance(aggregate, dict)
        aggregate["id"] = "speaker-main-001"
        entries = self.source_index["entries"]
        assert isinstance(entries, dict)
        entries["speaker-main-001"] = deepcopy(entries["key-001"])
        self.write_outputs()
        aggregate_result = validator.validate_outputs(self.job_dir)
        self.assertEqual(aggregate_result["status"], "completed")
        self.assertFalse(
            any("重复claim id：speaker-main-001" in message for message in aggregate_result["errors"])
        )

    def test_invalid_audio_duration_fails(self) -> None:
        self.analysis["audio_duration"] = -1.0
        self.write_outputs()
        result = validator.validate_outputs(self.job_dir)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("audio_duration必须是有限且非负" in message for message in result["errors"])
        )


if __name__ == "__main__":
    unittest.main()
