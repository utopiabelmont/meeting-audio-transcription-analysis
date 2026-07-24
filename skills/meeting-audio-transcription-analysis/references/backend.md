# Local backend contract

## 可移植后端配置

Skill 不包含模型、Conda 环境或转录后端，也不绑定某台机器的绝对路径。运行前用以下任一种方式配置本地后端：

1. 设置项目根环境变量 `VTT_PLUS_ANALYSIS_ROOT`。该目录须包含 `app` 和 `conda`。
2. 按组件设置 `VTT_PLUS_APP_DIR`、`VTT_PLUS_PYANNOTE_PYTHON`、`VTT_PLUS_FFPROBE`。
3. 在 Skill 根创建仅供本机使用的 `local_backend.json`，可写 `project_root`、`app_dir`、`pyannote_python`、`ffprobe`。

组件路径的优先级为：

1. 对应的专用环境变量；
2. `local_backend.json` 中对应的组件字段；
3. 从 `project_root` 推导。

`project_root` 的优先级为 `VTT_PLUS_ANALYSIS_ROOT`、`local_backend.json.project_root`、显式 `app_dir` 的父目录。完全没有配置时必须明确失败，不得猜测其他用户的目录。JSON 中的相对路径相对于 `local_backend.json` 所在目录解析；环境变量中的相对路径相对于当前工作目录解析。

从项目根推导：

- app：`project_root\app`
- pyannote Python：`project_root\conda\envs\pyannote\python.exe`
- ffprobe：`project_root\conda\envs\pyannote\Library\bin\ffprobe.exe`

从 app 目录继续定位 `run_pipeline_complete.py`、`generate_vtt.py`、`config\transcript_cleaning_base.json`、`config\glossaries\optical_edge_ml.json` 和 `jobs`。启动模型前验证 app 目录、解释器、ffprobe、统一流水线、字幕生成模块、通用清理配置及 Skill 自身分析脚本。

`local_backend.json` 是机器私有文件，发布到 GitHub、制作压缩包或复制 Skill 时必须排除。仓库只应提供不含真实本机路径的示例配置。

所有路径均作为 `pathlib.Path` 处理，并作为独立进程参数传递。不要通过拼接未引用的字符串构造 shell 命令。

## Invoke the skill wrapper

Run the installed wrapper with the resolved pyannote interpreter. Build a process argument list whose executable is that interpreter, whose script is the installed scripts\run_meeting_skill.py, and whose --input value is the exact path obtained from the current turn's Files mentioned entry. Do not render the attachment path into an interpolated shell string, and do not ask the user to type the command.

Use these optional arguments only when applicable:

- --job-name NAME
- --expected-speakers N
- --meeting-title TEXT
- --meeting-date TEXT
- --meeting-topic TEXT
- --languages LANGUAGE, repeated for multiple expected languages
- --domain DOMAIN
- --glossary PATH, repeated for multiple project glossaries
- --known-participant NAME, repeated for multiple supplied participants
- --user-speaker-hint TEXT
- --output-language LANGUAGE
- --question TEXT, repeated for initial questions
- --resume

Treat --languages as report context only; never let it replace the fixed ASR language settings. Require --expected-speakers to be an integer from 1 through 64. The wrapper owns backend command construction, job naming, input probing, logging, transcript selection, analysis invocation, and output validation. Do not call PowerShell for a normal skill run.

Validate --output-language before invoking the backend. Accept only Chinese, English, Japanese, zh, en, ja, and the analyzer's existing case-insensitive aliases. Return an input error without starting models for any unsupported value.

## Preserve verified backend settings

Require the wrapper to pass these settings without alteration:

| Setting | Required value |
| --- | --- |
| language | auto |
| language_strategy | per-chunk |
| chunk_duration | 180 seconds |
| chunk_overlap | 12 seconds |
| keep_chunks | true |
| speaker naming | anonymous |
| text cleaning | enabled |
| technical review package | enabled |

Do not change backend model selection, GPU settings, speaker merge logic, or chunking behavior from this skill.

## Apply domain rules

Use only the general cleaning rules by default. Add optical_edge_ml.json when:

- domain indicates optical research;
- domain indicates edge detection;
- domain indicates machine learning;
- the user explicitly requests the optical glossary.

Append any readable user-provided glossary with --glossary. Never silently substitute a missing glossary.

## Manage jobs and resume

Generate a sanitized job name from the attachment stem, local date, and a short input hash when the user provides no name. Keep output under the backend jobs root.

Before reuse:

1. compare the canonical input identity and hash;
2. compare the fixed settings and relevant project glossary configuration;
3. allow an incomplete Job to continue only when the caller explicitly passes --resume and all identities match;
4. allow a compatible completed Job to skip safely without requiring --resume;
5. reject a mismatch or an implicit resume instead of overwriting the job.

Do not overwrite transcript_final.json, transcript_final.txt, or transcript_final.vtt during cleaning or analysis. Write derived files beside them.

## Degrade from valid final outputs

When the main backend returns nonzero, the wrapper first continues if all three original outputs are usable: transcript_final.json has a nonempty cues array, transcript_final.txt has readable nonempty text, and transcript_final.vtt is readable with a WEBVTT header. It preserves those originals and calls the unified backend with --skip-pipeline so only cleaning and the technical review run. It must not load models again.

There is one narrower fallback when all three final files are absent. The wrapper may load job\word_timestamps.json only when its transcript is nonempty and every nonempty word has finite, nonnegative, valid, monotonically nondecreasing start and end times. Reuse functions from the existing app\generate_vtt.py to build cues and format timestamps; do not copy or alter its segmentation algorithm. Write transcript_final.json, transcript_final.txt, and transcript_final.vtt atomically with every cue labeled speaker=UNKNOWN and speaker_id=UNKNOWN. The generated JSON must record fallback_source, generated_unknown_from_word_timestamps=true, and speaker_attribution=UNKNOWN.

If any one or two final files already exist, or if all three exist but any is invalid, never generate or overwrite a final file. Fail instead, even when word_timestamps.json is valid.

Record the original backend return code, the degraded reason, source mode, generated_unknown_from_word_timestamps, speaker_attribution_reliable=false, and the applicable speaker-label policy in meeting_skill_run.json. Mark the final wrapper status completed_degraded. Also retain the same source mode and original failure details under meeting_skill_degraded_fallback in pipeline_manifest.json. Existing valid final labels remain unchanged; generated final cues are always UNKNOWN.

If neither a complete valid final-output triplet nor the strictly eligible word-timestamp source exists, or if degraded cleaning/review fails, stop without generating meeting analysis outputs.

## Record the run

Expect the wrapper to write:

- meeting_skill_input.json for normalized user context;
- meeting_skill_run.json for command, stage status, return codes, selected sources, and outputs;
- meeting_skill_console.log for wrapper and subprocess stdout and stderr;
- meeting_skill_validation.json for output checks when validation runs.

Keep subprocess output visible in the active tool result while also saving it to the job log. On failure, report the failed stage, return code, and absolute log path.

## Probe input before model startup

Use ffprobe or the backend's existing probe helper to confirm:

- a supported container or extension;
- nonzero file size;
- at least one audio stream;
- duration;
- sample rate;
- channel count.

Use an audio track from supported video files. Never alter the source file; let the backend create its standardized WAV inside the job.

## Run analysis without models

Use scripts\analyze_transcript.py directly for an existing valid job or to retry only the analysis stage. Require --job-dir. Use these overrides only when needed:

- --transcript PATH
- --review-package PATH
- --context-json PATH
- --meeting-title TEXT
- --meeting-date TEXT
- --meeting-topic TEXT
- --domain TEXT
- --known-participant TEXT, repeated as needed
- --question TEXT, repeated as needed
- --output-language TEXT
- --output-dir PATH

Let output-dir default to the job directory. Do not rerun transcription merely to regenerate analysis.
