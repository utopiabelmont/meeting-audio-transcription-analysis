---
name: meeting-audio-transcription-analysis
description: "Transcribe and analyze uploaded meeting, negotiation, research-discussion, and interview recordings in English, Japanese, Chinese, or mixed languages with anonymous multi-speaker separation, timestamped transcripts, summaries, topic timelines, decisions, action items, risks, and source-grounded follow-up answers. Use when the user asks to transcribe a recording, distinguish speakers, summarize a meeting, build a timeline, find decisions or tasks, analyze one speaker's views, verify whether a topic was mentioned, or locate when something was said in an audio or video attachment."
---

# Meeting Audio Transcription Analysis

## Follow the complete workflow

1. Resolve the recording from the current turn.
2. Collect only useful optional context without blocking on omissions.
3. Run the installed local skill wrapper.
4. Verify the transcript, review, analysis, timeline, and source-index outputs.
5. Summarize the result in chat.
6. Answer follow-up questions from indexed transcript evidence.

Read [input_contract.md](references/input_contract.md) before selecting an attachment. Read [backend.md](references/backend.md) before invoking a script. Read [quality_rules.md](references/quality_rules.md) before reporting analysis or answering questions. Read [output_schema.md](references/output_schema.md) when inspecting or regenerating outputs.

## Resolve the uploaded file

- Obtain the real readable local path from the current turn's Files mentioned section.
- Pass that exact path to scripts/run_meeting_skill.py with --input.
- Never hardcode an attachments directory, reconstruct a path from a display name, or assume the original filename was retained.
- Validate existence, regular-file status, supported extension, nonzero size, and a readable audio stream before starting the backend.
- Preserve paths containing spaces, Chinese, or Japanese as one argument.
- Select the file named by the user when multiple supported attachments exist.
- Select a single uniquely obvious main recording only when the user's wording makes that choice unambiguous.
- Otherwise list the candidate filenames and ask one concise selection question.
- Never concatenate or merge multiple attachments silently.
- Never modify, rename, move, or overwrite the original attachment.

## Collect context without blocking

Capture any supplied meeting title, date, topic, expected speaker count, languages, domain, glossary paths, known participants, speaker hint, output language, questions, resume preference, and job name.

Apply these defaults:

- Let the backend estimate speaker count when expected_speakers is absent.
- Keep language as auto and language strategy as per-chunk when languages is absent.
- Use only the general cleaning rules when glossary is absent and the domain is not optical, edge detection, or machine learning.
- Use the user's current conversation language when output_language is absent.
- Preserve anonymous SPEAKER labels when names are absent.
- Generate a job name from a sanitized file stem, date, and short content hash when job_name is absent.

Do not interrupt the workflow merely because optional context is missing. Do not infer a real identity from known participants or a speaker hint; treat those fields only as user-supplied analytical context unless an explicit speaker map is separately supported.

## Run transcription and analysis

Invoke scripts/run_meeting_skill.py through the local pyannote-environment Python described in [backend.md](references/backend.md). Supply the resolved attachment path with --input, always pass --output-language using the explicit request or the current conversation language, and add only the other user-provided options.

Keep all verified backend defaults unchanged:

- language auto
- language strategy per-chunk
- chunk duration 180 seconds
- chunk overlap 12 seconds
- keep chunks enabled
- anonymous speakers enabled
- general cleaning enabled
- technical review package enabled

Add the optical glossary automatically when the domain is optical, edge detection, or machine learning, or when the user explicitly requests that glossary. Pass an explicit expected speaker count only when supplied. Use --resume only for the same input and compatible job configuration. An incomplete existing Job never resumes implicitly: pass --resume explicitly. A compatible completed Job may be reused safely without --resume.

Let the wrapper run the complete transcript-to-analysis flow. Do not ask the user to run PowerShell. Do not copy model files or environments into the skill. Do not bypass the wrapper for a normal new task.

Treat the generated analysis as an evidence-first draft. Its headings, static summary, and quality notes use the requested output language; extracted evidence text deliberately remains in the recording language. In the chat response, synthesize it into clear prose in the requested output language, but preserve its timestamps, speaker labels, confidence, and evidence status. Never turn an extractive fragment into a stronger claim. If you materially rewrite a saved analysis artifact, rerun scripts/validate_skill_outputs.py before reporting success.

After completion, require these analysis outputs:

- meeting_analysis.json
- meeting_analysis.md
- meeting_timeline.md
- meeting_source_index.json

Also inspect meeting_skill_run.json, meeting_skill_console.log, pipeline_manifest.json, and the selected transcript and review-package paths. Treat a nonzero return code or a failed run manifest as failure unless meeting_skill_run.json explicitly records completed_degraded after validating the transcript_final triplet and completing no-model cleaning, review, analysis, and validation. Always disclose that degraded speaker attribution is unreliable.

## Select the transcript safely

Use transcript_cleaned.json only when it exists and the cleaning state in the manifest is completed. Otherwise use transcript_final.json when it exists and explicitly state that analysis used raw ASR text. Fail the analysis when neither file exists.

Read transcript_review_package.json when present. Surface every critical item. Continue with warnings, but mark affected conclusions or quotations as uncertain. Never describe a result with critical issues as fully reliable.

## Verify source grounding

Require every substantive key point, topic segment, decision, action item, open question, risk, disagreement, and speaker claim to include a time range and cue evidence. Preserve source speaker labels exactly.

Reject or repair conclusions that:

- cite missing cue indices;
- use a start time after the end time;
- fall outside the recording duration;
- invent an owner, deadline, identity, demographic trait, or decision;
- call a suggestion or possibility a confirmed decision;
- omit uncertainty for a flagged source region.

Use null or 未明确 when an owner or deadline was not stated. Do not infer gender, age, role, or real identity from a voice.

## Answer follow-up questions

Read meeting_analysis.json and meeting_source_index.json first. Read transcript_cleaned.json or the recorded raw-transcript fallback when more context is needed.

Attach a source citation to each supported answer, using this form:

    [00:12:34–00:13:08, SPEAKER_01]

Classify each claim as one of:

- explicitly stated in the recording;
- inferred from nearby context;
- not provided by the recording.

Use speaker labels for who questions and timestamps for when questions. Distinguish a decision from a suggestion or unresolved matter. Recheck the review package and source cues when terminology may be misrecognized.

Answer unsupported questions with:

    录音中没有找到足以支持该结论的内容。

Do not fill evidence gaps with general knowledge unless the user explicitly requests separate external research.

## Degrade honestly

- On transcription failure, identify the failed stage and log path, retain partial files, and generate no summary.
- On a backend or speaker-separation failure, first continue when valid transcript_final.json, transcript_final.txt, and transcript_final.vtt already exist. If and only if all three final files are absent, a nonempty, finite, monotonic word_timestamps.json may be converted with the existing generate_vtt.py build_cues and timestamp formatter into an all-UNKNOWN final triplet. Never overwrite a partial or invalid existing final triplet. Reuse the unified backend with --skip-pipeline to run only cleaning and review, mark speaker attribution unreliable, and record completed_degraded plus the source, original return code, and reason. Without either safe source, fail and generate no analysis.
- On cleaning failure, use transcript_final.json, disclose the raw-ASR fallback, and continue unless strict cleaning was requested.
- On analysis failure, preserve all transcript artifacts, report that transcription succeeded but analysis failed, and rerun analysis without rerunning the models.
- On absent evidence, return the required not-found sentence and cite nothing fabricated.

## Finish in chat

Lead with completion status rather than logs. Include:

1. whether transcription and analysis completed;
2. recording duration;
3. detected speaker count;
4. principal languages;
5. three to eight most important findings;
6. confirmed decisions;
7. action items;
8. a compact topic-timeline overview;
9. quality warnings and any fallback used;
10. absolute paths to the generated transcript, analysis, timeline, source index, and log;
11. an invitation to ask further questions about the recording.

Keep low-level model-loading output in the log rather than the primary response.
