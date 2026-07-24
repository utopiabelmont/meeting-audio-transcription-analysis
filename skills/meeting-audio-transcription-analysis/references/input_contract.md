# Input contract

## Required input

Require exactly one readable audio or video attachment for a new transcription run.

Accept backend and ffmpeg-readable files with these common extensions:

- .wav
- .mp3
- .m4a
- .mp4
- .mov
- .mkv

Treat extension matching case-insensitively. Confirm an audio stream rather than trusting the suffix.

## Resolve attachments

1. Read the current turn's Files mentioned entries.
2. Retain candidates that resolve to existing regular files with supported extensions.
3. Honor an explicit filename or ordinal choice from the user.
4. Select the only supported candidate automatically.
5. Select a uniquely obvious main recording only when the user's wording makes it unambiguous.
6. Otherwise show the candidate filenames and ask which one to process.
7. Pass the chosen resolved path unchanged to --input.

Never hardcode the Codex attachment storage root. Never assume an attachment retained its upload name. Never merge candidates without explicit instruction.

## Validate before execution

Resolve and validate the local backend configuration before probing media or starting models. Accept configuration from `VTT_PLUS_ANALYSIS_ROOT`, the three component-specific environment variables, or the private Skill-root `local_backend.json` described in [backend.md](backend.md). A missing or invalid backend configuration is an input error and must identify the unresolved path. Never search disks for a likely backend.

Reject the input before starting models when:

- the path is missing or unreadable;
- it is not a regular file;
- the file is empty;
- the extension is unsupported;
- ffprobe finds no audio stream;
- duration is missing, non-finite, or non-positive.

Record normalized user context in meeting_skill_input.json. Record the resolved path, byte size, input hash, duration, sample rate, channels, and selected audio-stream index under input and media in meeting_skill_run.json. Do not copy, edit, rename, or delete the source.

## Optional context

Accept these fields without requiring them:

| Field | Meaning | Default |
| --- | --- | --- |
| meeting_title | Human-readable title | Derive from filename |
| meeting_date | Meeting date supplied by user | null |
| meeting_topic | Expected subject | null |
| expected_speakers | Exact expected count | Backend estimation |
| languages | User expectation, not a forced ASR language | auto |
| domain | Domain-selection hint | general |
| glossary | Additional cleaning glossary paths | General rules only |
| known_participants | User-provided names for analytical context | empty list |
| user_speaker_hint | User-supplied attribution hint | null |
| output_language | Analysis and chat language | Current conversation language |
| questions | Initial source-grounded questions | empty list |
| resume | Continue a compatible job | false |
| job_name | Explicit backend job name | Generated safely |

Do not force an ASR language from the languages hint. Keep backend language auto and per-chunk detection.

When output_language is supplied, validate it before starting the backend. Accept Chinese, English, Japanese, zh, en, ja, and the analyzer's existing case-insensitive aliases (zh-cn, en-us, en-gb, ja-jp, 中文, 英语, 日语, 日本語). Reject any other value without invoking transcription.

Do not treat known_participants or user_speaker_hint as verified speaker identity. Preserve anonymous SPEAKER labels unless the backend receives an explicitly supported mapping in a separate workflow.

## Normalize metadata

- Store missing scalar values as null.
- Store missing collections as empty arrays.
- Preserve Unicode text as UTF-8.
- Reject booleans where an integer speaker count is expected.
- Require expected_speakers to be an integer from 1 through 64 when supplied.
- Normalize glossary paths to canonical readable files.
- Preserve the user's wording for questions.

## Generate a safe job name

Build a default job name from:

1. a sanitized attachment stem;
2. the local run date;
3. a short prefix of the input content hash.

Restrict generated names to filesystem-safe Unicode letters and digits, underscores, and hyphens. Do not use user-controlled path separators. Never allow a generated or supplied name to escape the backend jobs root.
