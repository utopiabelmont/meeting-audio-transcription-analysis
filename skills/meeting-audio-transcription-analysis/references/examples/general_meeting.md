# General meeting example

## User request

> 请使用会议录音分析Skill处理我上传的录音。预计3人，日语为主。请输出完整转录、重点摘要、决定、待办和时间轴。

## Required handling

1. Resolve the exact uploaded recording path from the current task.
2. Validate its audio stream without modifying the file.
3. Pass expected speaker count 3.
4. Keep ASR language auto and per-chunk despite the user's language expectation.
5. Use general cleaning only.
6. Preserve anonymous speaker labels.
7. Generate transcript, review package, analysis, timeline, and source index.
8. Surface quality warnings.
9. Reply with supported findings and file paths.

## Follow-up examples

Ask:

> 最后确定了哪些事项？

Answer only with explicit decisions. Cite each item with a time range and speaker label.

Ask:

> 谁负责发送报价，什么时候完成？

Fill owner or deadline only when stated. Otherwise use 未明确 and cite the relevant discussion.

Ask:

> 录音中是否决定在大阪开设新办公室？

If no supporting cue exists, answer:

> 录音中没有找到足以支持该结论的内容。

## Expected chat shape

- State whether transcription and analysis completed.
- Report duration, anonymous speaker count, and languages.
- Give three to eight evidence-backed findings.
- Separate decisions, action items, and open questions.
- Show a compact semantic timeline.
- Note critical issues, warnings, and any raw-ASR fallback.
- Link the generated transcript, analysis, timeline, source index, and log.
- Invite further questions.

