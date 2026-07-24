from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "run_meeting_skill.py"
)
SPEC = importlib.util.spec_from_file_location("run_meeting_skill_under_test", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
wrapper = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = wrapper
SPEC.loader.exec_module(wrapper)


def write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class InputAndProbeTests(unittest.TestCase):
    def test_rejects_unsupported_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "recording.txt"
            path.write_bytes(b"not audio")
            with self.assertRaises(wrapper.SkillInputError):
                wrapper.validate_input_path(path)

    def test_rejects_empty_supported_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "recording.wav"
            path.touch()
            with self.assertRaises(wrapper.SkillInputError):
                wrapper.validate_input_path(path)

    def test_actual_ffprobe_with_generated_sample(self) -> None:
        try:
            configured_ffprobe = wrapper.resolve_backend_paths().ffprobe
        except wrapper.SkillInputError:
            configured_ffprobe = Path(shutil.which("ffprobe") or "")
        if not configured_ffprobe.is_file():
            self.skipTest("ffprobe未配置，跳过实际媒体探测集成测试。")

        with tempfile.TemporaryDirectory() as temporary:
            sample = Path(temporary) / "generated.wav"
            with wave.open(str(sample), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(b"\0\0" * 16000)
            path, stat = wrapper.validate_input_path(sample)
            info = wrapper.probe_media(path, configured_ffprobe)
            self.assertGreater(stat.st_size, 0)
            self.assertAlmostEqual(info["duration_seconds"], 1.0, places=2)
            self.assertEqual(info["sample_rate"], 16000)
            self.assertEqual(info["channels"], 1)

    def test_automatic_job_name_is_stable_and_backend_safe(self) -> None:
        path = Path("meeting with spaces 日本語.wav")
        digest = "a" * 64
        first = wrapper.automatic_job_name(path, digest)
        second = wrapper.automatic_job_name(path, digest)
        self.assertEqual(first, second)
        self.assertEqual(wrapper.safe_job_name(first), first)
        self.assertRegex(first, re.compile(r"_\d{8}_a{12}$"))
        self.assertNotRegex(first, re.compile(r'[<>:"/\\|?*\s]'))


class BackendConfigurationTests(unittest.TestCase):
    def test_project_root_environment_derives_component_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "portable-backend"
            config_path = Path(temporary) / "missing.json"
            resolved = wrapper.resolve_backend_paths(
                environ={"VTT_PLUS_ANALYSIS_ROOT": str(root)},
                config_path=config_path,
            )

            self.assertEqual(resolved.project_root, root.resolve())
            self.assertEqual(resolved.app_dir, (root / "app").resolve())
            self.assertEqual(
                resolved.pyannote_python,
                (
                    root / "conda" / "envs" / "pyannote" / "python.exe"
                ).resolve(),
            )
            self.assertEqual(
                resolved.ffprobe,
                (
                    root
                    / "conda"
                    / "envs"
                    / "pyannote"
                    / "Library"
                    / "bin"
                    / "ffprobe.exe"
                ).resolve(),
            )
            self.assertEqual(
                resolved.sources["app_dir"],
                "derived:project_root/app",
            )

    def test_local_component_paths_override_project_root_derivation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            config_path = base / "local_backend.json"
            write_json(
                config_path,
                {
                    "project_root": "root",
                    "app_dir": "custom-app",
                    "pyannote_python": "tools/python.exe",
                    "ffprobe": "tools/ffprobe.exe",
                },
            )

            resolved = wrapper.resolve_backend_paths(
                environ={},
                config_path=config_path,
            )

            self.assertEqual(resolved.project_root, (base / "root").resolve())
            self.assertEqual(resolved.app_dir, (base / "custom-app").resolve())
            self.assertEqual(
                resolved.pyannote_python,
                (base / "tools" / "python.exe").resolve(),
            )
            self.assertEqual(
                resolved.ffprobe,
                (base / "tools" / "ffprobe.exe").resolve(),
            )
            self.assertEqual(
                resolved.sources["app_dir"],
                "local_backend.json:app_dir",
            )

    def test_local_component_overrides_environment_root_derivation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            config_path = base / "local_backend.json"
            write_json(config_path, {"app_dir": "custom-app"})

            resolved = wrapper.resolve_backend_paths(
                environ={
                    "VTT_PLUS_ANALYSIS_ROOT": str(base / "environment-root")
                },
                config_path=config_path,
            )

            self.assertEqual(
                resolved.project_root,
                (base / "environment-root").resolve(),
            )
            self.assertEqual(resolved.app_dir, (base / "custom-app").resolve())
            self.assertEqual(
                resolved.sources["app_dir"],
                "local_backend.json:app_dir",
            )

    def test_dedicated_environment_overrides_local_component_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            config_path = base / "local_backend.json"
            write_json(
                config_path,
                {
                    "project_root": str(base / "local-root"),
                    "app_dir": str(base / "local-app"),
                    "pyannote_python": str(base / "local-python.exe"),
                    "ffprobe": str(base / "local-ffprobe.exe"),
                },
            )
            environment = {
                "VTT_PLUS_ANALYSIS_ROOT": str(base / "environment-root"),
                "VTT_PLUS_APP_DIR": str(base / "environment-app"),
                "VTT_PLUS_PYANNOTE_PYTHON": str(
                    base / "environment-python.exe"
                ),
                "VTT_PLUS_FFPROBE": str(base / "environment-ffprobe.exe"),
            }

            resolved = wrapper.resolve_backend_paths(
                environ=environment,
                config_path=config_path,
            )

            self.assertEqual(
                resolved.project_root,
                (base / "environment-root").resolve(),
            )
            self.assertEqual(
                resolved.app_dir,
                (base / "environment-app").resolve(),
            )
            self.assertEqual(
                resolved.pyannote_python,
                (base / "environment-python.exe").resolve(),
            )
            self.assertEqual(
                resolved.ffprobe,
                (base / "environment-ffprobe.exe").resolve(),
            )
            self.assertTrue(
                all(source.startswith("env:") for source in resolved.sources.values())
            )

    def test_missing_configuration_is_rejected_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "local_backend.json"
            with self.assertRaisesRegex(
                wrapper.SkillInputError,
                "未配置本地转录后端",
            ):
                wrapper.resolve_backend_paths(
                    environ={},
                    config_path=missing,
                )

    def test_missing_configured_dependencies_are_rejected_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            backend = wrapper.resolve_backend_paths(
                environ={"VTT_PLUS_ANALYSIS_ROOT": str(base / "missing-root")},
                config_path=base / "missing.json",
            )
            with self.assertRaisesRegex(
                wrapper.SkillInputError,
                "后端配置验证失败",
            ):
                wrapper.validate_backend_paths(backend)


class WrapperFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="meeting_skill_test_")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.app = self.root / "app"
        self.skill = self.root / "skill"
        self.jobs = self.app / "jobs"
        for directory in (
            self.jobs,
            self.app / "config" / "glossaries",
            self.skill / "scripts",
        ):
            directory.mkdir(parents=True, exist_ok=True)

        self.base_config = self.app / "config" / "transcript_cleaning_base.json"
        self.optical_config = (
            self.app / "config" / "glossaries" / "optical_edge_ml.json"
        )
        self.pipeline_script = self.app / "run_pipeline_complete.py"
        self.generate_vtt_script = self.app / "generate_vtt.py"
        self.analysis_script = self.skill / "scripts" / "analyze_transcript.py"
        self.validator_script = (
            self.skill / "scripts" / "validate_skill_outputs.py"
        )
        self.ffprobe = self.root / "ffprobe.exe"
        for path, text in (
            (self.base_config, "{}\n"),
            (self.optical_config, "{}\n"),
            (self.pipeline_script, "# fake\n"),
            (
                self.generate_vtt_script,
                (
                    "def build_cues(*, transcript, word_timestamps):\n"
                    "    return [{'text': transcript, "
                    "'start_time': word_timestamps[0]['start_time'], "
                    "'end_time': word_timestamps[-1]['end_time']}]\n\n"
                    "def format_vtt_timestamp(seconds):\n"
                    "    milliseconds = round(float(seconds) * 1000)\n"
                    "    hours, remainder = divmod(milliseconds, 3600000)\n"
                    "    minutes, remainder = divmod(remainder, 60000)\n"
                    "    whole_seconds, milliseconds = divmod(remainder, 1000)\n"
                    "    return f'{hours:02d}:{minutes:02d}:"
                    "{whole_seconds:02d}.{milliseconds:03d}'\n"
                ),
            ),
            (self.analysis_script, "# fake\n"),
            (self.validator_script, "# fake\n"),
            (self.ffprobe, "fake\n"),
        ):
            path.write_text(text, encoding="utf-8")

        replacements = {
            "SKILL_DIR": self.skill,
            "ANALYSIS_SCRIPT": self.analysis_script,
            "VALIDATOR_SCRIPT": self.validator_script,
        }
        self.constants_patch = mock.patch.multiple(wrapper, **replacements)
        self.constants_patch.start()
        self.addCleanup(self.constants_patch.stop)

        self.backend_paths = wrapper.BackendPaths(
            project_root=self.root,
            app_dir=self.app,
            pyannote_python=Path(sys.executable),
            ffprobe=self.ffprobe,
            sources={
                "project_root": "test",
                "app_dir": "test",
                "pyannote_python": "test",
                "ffprobe": "test",
            },
            local_config_path=self.skill / "local_backend.json",
        )
        self.backend_config_patch = mock.patch.object(
            wrapper,
            "resolve_backend_paths",
            return_value=self.backend_paths,
        )
        self.backend_config_patch.start()
        self.addCleanup(self.backend_config_patch.stop)

        self.probe_patch = mock.patch.object(
            wrapper,
            "probe_media",
            side_effect=lambda path, ffprobe_exe=None: {
                "duration_seconds": 12.5,
                "audio_stream_index": 0,
                "codec_name": "pcm_s16le",
                "sample_rate": 16000,
                "channels": 1,
                "format_name": "wav",
                "reported_size_bytes": path.stat().st_size,
            },
        )
        self.probe_patch.start()
        self.addCleanup(self.probe_patch.stop)

        self.calls: list[tuple[str, list[str]]] = []
        self.backend_return_code = 0
        self.write_backend_outputs = True
        self.degraded_postprocessing_return_code = 0
        self.word_timestamps_payload: dict[str, object] | None = None
        self.partial_final_names: set[str] = set()
        self.command_patch = mock.patch.object(
            wrapper, "run_streaming_command", side_effect=self.fake_command
        )
        self.command_patch.start()
        self.addCleanup(self.command_patch.stop)

        self.audio = self.root / "meeting audio.wav"
        self.original_audio = b"RIFF-fake-audio"
        self.audio.write_bytes(self.original_audio)

    def fake_command(
        self, command: list[str], cwd: Path, log_file: object, title: str
    ) -> tuple[int, float]:
        del cwd, log_file
        self.calls.append((title, list(command)))
        job_dir = Path(command[command.index("--job-dir") + 1])
        job_dir.mkdir(parents=True, exist_ok=True)

        if title in {
            "LOCAL TRANSCRIPTION BACKEND",
            "DEGRADED POSTPROCESSING (NO MODELS)",
        }:
            is_degraded_postprocessing = title.startswith("DEGRADED")
            if not self.write_backend_outputs and not is_degraded_postprocessing:
                if self.word_timestamps_payload is not None:
                    write_json(
                        job_dir / "word_timestamps.json",
                        self.word_timestamps_payload,
                    )
                if "transcript_final.json" in self.partial_final_names:
                    write_json(job_dir / "transcript_final.json", {"cues": []})
                if "transcript_final.txt" in self.partial_final_names:
                    (job_dir / "transcript_final.txt").write_text(
                        "DO NOT OVERWRITE\n", encoding="utf-8"
                    )
                if "transcript_final.vtt" in self.partial_final_names:
                    (job_dir / "transcript_final.vtt").write_text(
                        "WEBVTT\n", encoding="utf-8"
                    )
                return self.backend_return_code, 0.01
            cue = {
                "start_time": 0.0,
                "end_time": 1.0,
                "speaker": "SPEAKER_00",
                "speaker_id": "SPEAKER_00",
                "text": "hello",
            }
            if not is_degraded_postprocessing:
                write_json(job_dir / "transcript_final.json", {"cues": [cue]})
                (job_dir / "transcript_final.txt").write_text(
                    "[SPEAKER_00] hello\n", encoding="utf-8"
                )
                (job_dir / "transcript_final.vtt").write_text(
                    "WEBVTT\n", encoding="utf-8"
                )
            write_json(job_dir / "transcript_cleaned.json", {"cues": [cue]})
            write_json(
                job_dir / "transcript_review_package.json",
                {"summary": {"critical_count": 0}, "issues": {}},
            )
            write_json(
                job_dir / "pipeline_manifest.json",
                {
                    "status": "completed",
                    "complete_pipeline": {
                        "status": "completed",
                        "main_pipeline_status": (
                            "skipped"
                            if "--skip-pipeline" in command
                            else "completed"
                        ),
                        "text_cleaning_status": "completed",
                        "review_package_status": "completed",
                    },
                },
            )
            if is_degraded_postprocessing:
                return self.degraded_postprocessing_return_code, 0.01
            return self.backend_return_code, 0.01
        elif title == "MEETING CONTENT ANALYSIS":
            write_json(job_dir / "meeting_analysis.json", {"metadata": {}})
            write_json(job_dir / "meeting_source_index.json", {"entries": {}})
            (job_dir / "meeting_analysis.md").write_text(
                "analysis\n", encoding="utf-8"
            )
            (job_dir / "meeting_timeline.md").write_text(
                "timeline\n", encoding="utf-8"
            )
        elif title == "SKILL OUTPUT VALIDATION":
            write_json(
                job_dir / "meeting_skill_validation.json",
                {"status": "completed", "errors": []},
            )
        return 0, 0.01

    def run_quietly(self, arguments: list[str]) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            return wrapper.run(arguments)

    def common_arguments(self) -> list[str]:
        return [
            "--input",
            str(self.audio),
            "--job-name",
            "test_job",
            "--expected-speakers",
            "2",
        ]

    def test_fixed_backend_command_parameters_and_anonymous_mode(self) -> None:
        command = wrapper.build_backend_command(
            backend=self.backend_paths,
            job_dir=self.jobs / "fixed",
            input_path=self.audio,
            job_name="fixed",
            expected_speakers=2,
            project_configs=[],
            action="new",
        )
        self.assertEqual(command[command.index("--language") + 1], "auto")
        self.assertEqual(
            command[command.index("--language-strategy") + 1], "per-chunk"
        )
        self.assertEqual(command[command.index("--chunk-duration") + 1], "180")
        self.assertEqual(command[command.index("--chunk-overlap") + 1], "12")
        self.assertIn("--keep-chunks", command)
        self.assertNotIn("--speaker-map", command)
        self.assertEqual(command[command.index("--num-speakers") + 1], "2")
        self.assertLess(command.index("--"), command.index("--language"))

    def test_invalid_output_language_fails_before_backend(self) -> None:
        arguments = [
            *self.common_arguments(),
            "--output-language",
            "Klingon",
        ]

        self.assertEqual(self.run_quietly(arguments), 2)

        self.assertEqual(self.calls, [])
        self.assertFalse((self.jobs / "test_job").exists())

    def test_optical_domain_selects_project_glossary(self) -> None:
        selected = wrapper.resolve_project_configs(
            "optical edge detection",
            [],
            optical_config=self.optical_config,
        )
        self.assertEqual(selected, [self.optical_config.resolve()])
        self.assertEqual(
            wrapper.resolve_project_configs(
                "general meeting",
                [],
                optical_config=self.optical_config,
            ),
            [],
        )

    def test_same_job_with_different_sha_is_rejected(self) -> None:
        arguments = self.common_arguments()
        self.assertEqual(self.run_quietly(arguments), 0)
        self.audio.write_bytes(self.original_audio + b"changed")
        self.assertEqual(self.run_quietly(arguments), 2)

    def test_same_completed_job_skips_backend(self) -> None:
        arguments = self.common_arguments()
        self.assertEqual(self.run_quietly(arguments), 0)
        self.calls.clear()
        self.assertEqual(self.run_quietly(arguments), 0)
        self.assertFalse(
            any(title == "LOCAL TRANSCRIPTION BACKEND" for title, _ in self.calls)
        )
        state = json.loads(
            (self.jobs / "test_job" / "meeting_skill_run.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(state["action"], "skip_completed")

    def test_cleaning_failure_uses_raw_transcript_fallback(self) -> None:
        arguments = self.common_arguments()
        self.assertEqual(self.run_quietly(arguments), 0)
        job_dir = self.jobs / "test_job"
        (job_dir / "transcript_cleaned.json").unlink()
        manifest_path = job_dir / "pipeline_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        complete = manifest["complete_pipeline"]
        complete["status"] = "completed_with_warnings"
        complete["text_cleaning_status"] = "failed"
        write_json(manifest_path, manifest)

        self.calls.clear()
        self.assertEqual(self.run_quietly(arguments), 0)
        state = json.loads(
            (job_dir / "meeting_skill_run.json").read_text(encoding="utf-8")
        )
        self.assertEqual(state["status"], "completed_with_warnings")
        self.assertTrue(state["used_raw_transcript_fallback"])
        self.assertTrue(state["outputs"]["transcript"].endswith("transcript_final.json"))

    def test_backend_failure_with_valid_final_uses_degraded_analysis(self) -> None:
        self.backend_return_code = 17

        self.assertEqual(self.run_quietly(self.common_arguments()), 0)

        job_dir = self.jobs / "test_job"
        state = json.loads(
            (job_dir / "meeting_skill_run.json").read_text(encoding="utf-8")
        )
        manifest = json.loads(
            (job_dir / "pipeline_manifest.json").read_text(encoding="utf-8")
        )
        transcript = json.loads(
            (job_dir / "transcript_final.json").read_text(encoding="utf-8")
        )
        titles = [title for title, _ in self.calls]

        self.assertEqual(state["status"], "completed_degraded")
        self.assertTrue(state["degraded_mode"])
        self.assertFalse(state["speaker_attribution_reliable"])
        self.assertEqual(state["return_codes"]["backend"], 17)
        self.assertEqual(state["return_codes"]["degraded_postprocessing"], 0)
        self.assertIn("说话人归属不可靠", state["degraded_reason"])
        self.assertEqual(
            manifest["meeting_skill_degraded_fallback"]["status"], "completed"
        )
        self.assertEqual(
            manifest["complete_pipeline"]["main_pipeline_status"],
            "degraded_partial_transcript",
        )
        self.assertEqual(transcript["cues"][0]["speaker_id"], "SPEAKER_00")
        self.assertIn("DEGRADED POSTPROCESSING (NO MODELS)", titles)
        fallback_command = next(
            command
            for title, command in self.calls
            if title == "DEGRADED POSTPROCESSING (NO MODELS)"
        )
        self.assertIn("--skip-pipeline", fallback_command)
        self.assertIn("MEETING CONTENT ANALYSIS", titles)

    def test_backend_failure_without_valid_final_still_fails(self) -> None:
        self.backend_return_code = 17
        self.write_backend_outputs = False

        self.assertEqual(self.run_quietly(self.common_arguments()), 1)

        job_dir = self.jobs / "test_job"
        state = json.loads(
            (job_dir / "meeting_skill_run.json").read_text(encoding="utf-8")
        )
        titles = [title for title, _ in self.calls]
        self.assertEqual(state["status"], "transcription_failed")
        self.assertFalse(state["degraded_fallback"]["attempted"])
        self.assertTrue(
            state["degraded_fallback"]["transcript_validation_errors"]
        )
        self.assertNotIn("DEGRADED POSTPROCESSING (NO MODELS)", titles)
        self.assertNotIn("MEETING CONTENT ANALYSIS", titles)
        self.assertNotIn("outputs", state)

    def test_word_timestamps_generate_unknown_degraded_transcript(self) -> None:
        self.backend_return_code = 17
        self.write_backend_outputs = False
        self.word_timestamps_payload = {
            "audio": "input_16k_mono.wav",
            "language": "English",
            "transcript": "Hello world.",
            "word_timestamps": [
                {"text": "Hello", "start_time": 0.0, "end_time": 0.4},
                {"text": "world", "start_time": 0.5, "end_time": 1.0},
            ],
        }

        self.assertEqual(self.run_quietly(self.common_arguments()), 0)

        job_dir = self.jobs / "test_job"
        transcript = json.loads(
            (job_dir / "transcript_final.json").read_text(encoding="utf-8")
        )
        state = json.loads(
            (job_dir / "meeting_skill_run.json").read_text(encoding="utf-8")
        )
        manifest = json.loads(
            (job_dir / "pipeline_manifest.json").read_text(encoding="utf-8")
        )
        self.assertTrue(transcript["generated_unknown_from_word_timestamps"])
        self.assertEqual(transcript["speaker_attribution"], "UNKNOWN")
        self.assertTrue(transcript["cues"])
        self.assertTrue(
            all(cue["speaker_id"] == "UNKNOWN" for cue in transcript["cues"])
        )
        self.assertTrue(
            (job_dir / "transcript_final.txt")
            .read_text(encoding="utf-8")
            .startswith("[00:00:00.000] UNKNOWN：")
        )
        self.assertTrue(
            (job_dir / "transcript_final.vtt")
            .read_text(encoding="utf-8")
            .startswith("WEBVTT")
        )
        self.assertEqual(state["status"], "completed_degraded")
        self.assertTrue(state["generated_unknown_from_word_timestamps"])
        self.assertEqual(state["speaker_label_policy"], "all_UNKNOWN")
        self.assertEqual(
            state["degraded_fallback"]["fallback_source"],
            "generated_unknown_from_word_timestamps",
        )
        self.assertTrue(
            manifest["meeting_skill_degraded_fallback"]
            ["generated_unknown_from_word_timestamps"]
        )

    def test_partial_final_refuses_word_timestamp_overwrite(self) -> None:
        self.backend_return_code = 17
        self.write_backend_outputs = False
        self.partial_final_names = {"transcript_final.txt"}
        self.word_timestamps_payload = {
            "transcript": "Hello.",
            "word_timestamps": [
                {"text": "Hello", "start_time": 0.0, "end_time": 0.5}
            ],
        }

        self.assertEqual(self.run_quietly(self.common_arguments()), 1)

        job_dir = self.jobs / "test_job"
        self.assertEqual(
            (job_dir / "transcript_final.txt").read_text(encoding="utf-8"),
            "DO NOT OVERWRITE\n",
        )
        self.assertFalse((job_dir / "transcript_final.json").exists())
        self.assertFalse((job_dir / "transcript_final.vtt").exists())
        state = json.loads(
            (job_dir / "meeting_skill_run.json").read_text(encoding="utf-8")
        )
        self.assertEqual(state["status"], "transcription_failed")
        self.assertEqual(
            state["degraded_fallback"]["present_final_outputs"],
            [str((job_dir / "transcript_final.txt").resolve())],
        )
        self.assertNotIn(
            "DEGRADED POSTPROCESSING (NO MODELS)",
            [title for title, _ in self.calls],
        )

    def test_invalid_word_timestamps_do_not_generate_final_outputs(self) -> None:
        self.backend_return_code = 17
        self.write_backend_outputs = False
        self.word_timestamps_payload = {
            "transcript": "out of order",
            "word_timestamps": [
                {"text": "out", "start_time": 1.0, "end_time": 1.5},
                {"text": "order", "start_time": 0.5, "end_time": 0.8},
            ],
        }

        self.assertEqual(self.run_quietly(self.common_arguments()), 1)

        job_dir = self.jobs / "test_job"
        self.assertFalse(any(path.exists() for path in wrapper.final_output_paths(job_dir)))
        state = json.loads(
            (job_dir / "meeting_skill_run.json").read_text(encoding="utf-8")
        )
        self.assertEqual(state["status"], "transcription_failed")
        self.assertIn(
            "单调不下降",
            state["degraded_fallback"]["word_timestamp_generation_error"],
        )
        self.assertNotIn("MEETING CONTENT ANALYSIS", [title for title, _ in self.calls])

    def make_job_incomplete(self) -> None:
        self.assertEqual(self.run_quietly(self.common_arguments()), 0)
        job_dir = self.jobs / "test_job"
        write_json(job_dir / "pipeline_state.json", {"status": "failed"})
        manifest_path = job_dir / "pipeline_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["status"] = "failed"
        manifest["complete_pipeline"]["status"] = "failed"
        manifest["complete_pipeline"]["main_pipeline_status"] = "failed"
        write_json(manifest_path, manifest)
        self.calls.clear()

    def test_incomplete_job_without_explicit_resume_is_rejected(self) -> None:
        self.make_job_incomplete()

        self.assertEqual(self.run_quietly(self.common_arguments()), 2)

        self.assertEqual(self.calls, [])
        state = json.loads(
            (self.jobs / "test_job" / "meeting_skill_run.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(state["status"], "completed")

    def test_incomplete_job_with_explicit_resume_continues(self) -> None:
        self.make_job_incomplete()

        arguments = [*self.common_arguments(), "--resume"]
        self.assertEqual(self.run_quietly(arguments), 0)

        backend_command = next(
            command
            for title, command in self.calls
            if title == "LOCAL TRANSCRIPTION BACKEND"
        )
        self.assertIn("--resume", backend_command)
        state = json.loads(
            (self.jobs / "test_job" / "meeting_skill_run.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(state["action"], "resume")
        self.assertEqual(state["status"], "completed")


if __name__ == "__main__":
    unittest.main()
