# Optical research meeting example

## User request

> 请使用会议录音分析Skill处理上传的录音。预计4人，英语和日语混合，主题是光学边缘检测，请加载optical_edge_ml术语表，并总结教授提出的修改意见。

## Required handling

1. Resolve the exact uploaded file path from the current task.
2. Validate the source and pass expected speaker count 4.
3. Keep language auto, per-chunk detection, 180-second chunks, 12-second overlap, and retained chunks.
4. Add config\glossaries\optical_edge_ml.json to general cleaning.
5. Keep all speaker labels anonymous unless a reliable explicit mapping is supplied.
6. Check the review package for uncertain technical terms.
7. Separate explicit requested revisions from exploratory suggestions.
8. Cite each professor-attributed point only when the recording or a reliable speaker mapping establishes that attribution.

## Evidence discipline

Do not assume that the longest-speaking participant is the professor. If no explicit mapping exists, report the source as SPEAKER_00 or its actual anonymous label.

Treat possible terms such as defocus, Rayleigh, edge profile, sub-pixel, CNN, or Grad-CAM as uncertain when review flags or source cues indicate ambiguity. Quote the nearby transcript rather than silently correcting a term beyond the glossary.

## Follow-up example

Ask:

> 根据刚才的录音，关于defocus容许范围讨论了什么？请给出说话人和时间位置。

Read meeting_analysis.json and meeting_source_index.json, then inspect cited canonical cues. Distinguish an explicit numeric tolerance from a proposed test range or an inference. Cite every supported part:

    [00:12:34–00:13:08, SPEAKER_01]

Return the required not-found sentence when no sufficient cue mentions the requested range.

