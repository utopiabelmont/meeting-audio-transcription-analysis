# Quality and evidence rules

## Ground every conclusion

Attach cue indices, source text, speaker labels, and a time range to every substantive conclusion. Prefer a small contiguous evidence window. Add surrounding cues only when needed to preserve meaning.

Classify support as:

- explicit: directly stated by a cited speaker;
- inferred: a conservative interpretation of cited nearby context;
- not_found: no sufficient cue evidence.

Never present inferred content as a quotation or confirmed fact.

## Separate decisions from discussion

Record a decision only when the recording shows a clear commitment, agreement, approval, rejection, or chosen course of action.

Do not promote these to decisions:

- suggestions;
- hypothetical options;
- tentative preferences;
- questions;
- individual proposals without agreement;
- topics deferred for later.

Move unresolved alternatives to open_questions or disagreements as appropriate.

## Extract action items conservatively

Require a task to be explicit enough that a listener could identify the expected action. Record owner and deadline only when stated or unmistakably assigned in the cited passage.

Use:

- owner: null when no responsible party is stated;
- deadline: null when no date or time constraint is stated;
- status: the output-language equivalent of "not stated" unless completion state is stated;
- confidence: a bounded numeric score;
- source evidence: exact cue indices and time range.

Do not turn general intentions into assigned work.

## Describe disagreement accurately

Distinguish:

- explicit opposition;
- differing interpretation;
- absence of consensus;
- ordinary clarification or supplementary detail.

Do not label normal questions, turn-taking, or elaboration as conflict.

## Preserve anonymous speakers

Keep SPEAKER_00, SPEAKER_01, and other recorded labels unchanged. Keep UNKNOWN unchanged. Do not infer a name, gender, age, seniority, job title, nationality, or relationship from voice characteristics.

Use known participant names only as user-provided context. Attribute a real name only when reliable source material explicitly maps it to a speaker label.

## Interpret review findings

- Treat critical count above zero as a material reliability limitation.
- Continue analysis with warnings, but tag affected claims or segments.
- Recheck source cues around terminology, fast speaker switches, UNKNOWN segments, short cues, and timestamp anomalies.
- State whether cleaned or raw ASR text was analyzed.
- Never claim perfect accuracy.

## Validate times and cues

Require:

- finite, nonnegative audio_duration;
- start_time at least zero;
- end_time at least start_time;
- transcript cue start_time values monotonically nondecreasing;
- end_time no later than audio_duration plus 0.5 seconds;
- existing cue indices;
- monotonic source cues;
- no duplicated claim identifiers;
- no empty source_text for a supported claim.

Apply claim-identifier uniqueness across core evidence collections, all four speaker-summary fields, and supported user-question answers. speaker_summaries.evidence is a compatibility aggregate of those same claims and does not create a duplicate by itself.

Mark a cross-speaker passage as multi-speaker instead of arbitrarily assigning one speaker.

## Build topic segments semantically

Segment on changes of subject, objective, decision phase, or discussion focus. Do not divide mechanically by minute. Avoid overlapping segments unless the source itself contains intertwined topics and the overlap is explained.

Summarize a segment rather than repeating every cue. Keep its time boundary traceable to source cues.

Use the complete semantic segment for timeline start_time and end_time. Keep the representative cue range separately as evidence_start_time and evidence_end_time.

## Preserve source language

Localize report headings, static summaries, and quality explanations to the requested Chinese, English, or Japanese output language. Keep every source_text field and extractive evidence fragment in the original transcript language; do not imply that evidence text was translated.

## Answer questions from evidence

Read meeting_analysis.json and meeting_source_index.json first. Inspect the canonical transcript cues when the summary is insufficient.

Use citations such as:

    [00:12:34–00:13:08, SPEAKER_01]

For absent evidence, reply exactly:

    录音中没有找到足以支持该结论的内容。

Do not cite unrelated cues to make an answer appear supported.

## Apply degradation rules

| Failure | Required behavior |
| --- | --- |
| Transcription | Report failed stage and log; do not summarize |
| Speaker separation with usable ASR | Continue with UNKNOWN or existing labels; mark attribution unreliable |
| Cleaning | Use transcript_final.json; disclose raw-ASR fallback; fail only in strict mode |
| Analysis | Preserve transcript; report analysis failure; allow analysis-only rerun |
| Unsupported question | Return the required not-found sentence |

## Check the final response

Before responding, verify that the chat summary:

- reports completion status, duration, speaker count, and languages;
- contains three to eight supported findings;
- separates decisions, tasks, and unresolved questions;
- includes a compact topic timeline;
- surfaces critical issues, warnings, and fallbacks;
- links to transcript, analysis, timeline, source index, and log;
- invites source-grounded follow-up questions;
- does not lead with low-level runtime logs.
