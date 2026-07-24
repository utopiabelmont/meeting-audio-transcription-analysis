# Output contract

## Select authoritative sources

Choose the transcript in this order:

1. Use transcript_cleaned.json only when pipeline_manifest.json records cleaning status completed.
2. Otherwise use transcript_final.json and record raw_asr_fallback in quality notes.
3. Fail analysis when neither exists.

Read transcript_review_package.json when available. Preserve transcript_final files unchanged.

## Require backend artifacts

Expect a complete job to contain:

- pipeline_manifest.json
- transcript_final.json
- transcript_final.txt
- transcript_final.vtt
- transcript_cleaned.json when cleaning succeeds
- transcript_cleaned.txt when cleaning succeeds
- transcript_cleaned.vtt when cleaning succeeds
- transcript_review_package.json
- transcript_review_package.txt
- pipeline_complete_console.log

The skill wrapper additionally records meeting_skill_input.json, meeting_skill_run.json, meeting_skill_console.log, and meeting_skill_validation.json.

## Require analysis artifacts

Generate these four files in the job directory:

- meeting_analysis.json
- meeting_analysis.md
- meeting_timeline.md
- meeting_source_index.json

Validate JSON output against:

- references/meeting_analysis.schema.json
- references/meeting_source_index.schema.json

Render the Markdown files from the corresponding templates in assets/templates without removing source citations.

## Structure meeting_analysis.json

Require these top-level keys:

- schema_version
- metadata
- source_files
- audio_duration
- languages
- speakers
- executive_summary
- key_points
- topic_segments
- timeline
- decisions
- action_items
- open_questions
- risks
- disagreements
- speaker_summaries
- terminology
- user_questions
- quality_notes

Use nonnegative seconds for machine-readable start_time and end_time. Format human-facing times as HH:MM:SS. Preserve speaker labels exactly as recorded.

Validation requires audio_duration and all cue/evidence times to be finite. Cue starts must be monotonically nondecreasing, cue ends must not precede starts, and no cue or evidence end may exceed audio_duration by more than 0.5 seconds. Claim ids are unique across core collections, the four traceable speaker-summary fields, and supported question answers; repeated references in the compatibility speaker_summaries.evidence aggregate are exempt.

Normalize metadata.output_language to Chinese, English, or Japanese; accept zh, en, and ja aliases case-insensitively. Keep the caller's original value in metadata.requested_output_language. Reject unsupported values clearly. The normalized language controls the static executive-summary text, quality notes, meeting_analysis.md, and meeting_timeline.md. Never translate source_text: it is evidence copied from the canonical transcript. The exact unsupported-answer sentence remains `录音中没有找到足以支持该结论的内容。` in every report language.

Require every semantic evidence item to carry:

- id
- start_time
- end_time
- speakers
- cue_indices
- source_text
- confidence

Keep owner and deadline null when an action item does not state them. Use an empty array for a category with no supported items.

Every item in speaker_summaries.main_points, questions, commitments, and concerns is an evidence object, not a bare string. Each item therefore has its own id, cue indices, time range, speaker labels, source text, and confidence. speaker_summaries.evidence may aggregate those same objects for compatibility.

For timeline items, start_time and end_time cover the complete topic segment. evidence_start_time and evidence_end_time cover the representative cue_indices, which remain a smaller auditable evidence sample when possible. Record both ranges in the source index and require the segment range to contain the evidence range.

## Structure meeting_source_index.json

Require:

- schema_version
- transcript
- entries

Store entries as an object keyed by the same id used in meeting_analysis.json. Give every entry category, start_time, end_time, speakers, zero-based cue_indices, and source_text. Record the selected canonical transcript in transcript.

Keep source text close enough to the cited cues for audit, but do not rewrite it into a stronger claim.

## Preserve traceability

For each claim:

1. find its same-id entry in meeting_source_index.json;
2. resolve every zero-based cue index against the canonical transcript;
3. compute a bounding time range from cited cues;
4. preserve all contributing speaker labels;
5. retain source text;
6. distinguish explicit, inferred, and not_found evidence;
7. carry relevant review flags into quality notes.

Do not create a source claim for a not_found answer.

## Write safely

- Encode JSON and Markdown as UTF-8.
- Write JSON atomically through a temporary sibling file and replacement.
- Avoid NaN and Infinity.
- Keep absolute source-file paths in machine-readable run metadata.
- Avoid overwriting original transcript artifacts.
- Preserve partial analysis files only when clearly marked failed in meeting_skill_run.json.
