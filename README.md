# Meeting Audio Transcription Analysis

这是一个面向 Codex 的本地会议录音转录与证据化分析 Skill。它调用已经安装在电脑上的 `vtt_plus_analysis` 后端，完成多人说话人分离、日英混合长音频转录、词级时间戳、字幕清理、会议摘要、主题时间轴、决定、待办事项和基于原始 cue 的后续问答。

> 本仓库是 **Codex Skill 适配层**，不是独立的 ASR 安装包。仓库不包含 Qwen3-ASR、Forced Aligner、pyannote 模型、Conda 环境、Hugging Face 令牌、用户录音或任务输出。运行前必须先准备兼容的本地转录后端。

## 能力

- 支持 WAV、MP3、M4A、MP4、MOV、MKV 等后端可读取格式；
- 支持英语、日语、中文或混合语言会议；
- 长录音按 180 秒切块、12 秒重叠，并按块自动检测语言；
- 保留匿名 `SPEAKER_00`、`SPEAKER_01` 等标签；
- 输出 JSON、TXT、VTT、摘要、时间轴和证据索引；
- 每项重要结论尽量保留说话人、时间范围、cue 索引与原始文本；
- 支持相同输入和兼容配置下的显式 Resume；
- 转录、清理或说话人分离异常时按既有安全规则降级，不伪造摘要。

## 前置条件

1. Windows 10/11 与可使用本地 Skill 的 Codex。
2. 已验证的 `vtt_plus_analysis` 后端，其中至少包含：
   - `app/run_pipeline_complete.py`
   - `app/generate_vtt.py`
   - `app/config/transcript_cleaning_base.json`
   - pyannote 和 Qwen3-ASR Conda 环境
   - 可执行的 `ffprobe`
3. 后端需要 gated 模型时，本机已有有效的 Hugging Face 授权或缓存。

详细要求见 [后端契约](docs/BACKEND.zh-CN.md)。

## 推荐安装

克隆拟发布仓库：

```powershell
git clone https://github.com/utopiabelmont/meeting-audio-transcription-analysis.git
Set-Location .\meeting-audio-transcription-analysis
```

安装时输入本机真实后端根目录：

```powershell
$BackendRoot = (Resolve-Path -LiteralPath (Read-Host "请输入 vtt_plus_analysis 根目录")).Path
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 `
  -ProjectRoot $BackendRoot
```

脚本会把 Skill 安装到当前用户的 `.codex\skills\meeting-audio-transcription-analysis`，并只在安装目录创建不入库的 `local_backend.json`。安装后重新打开 Codex 任务或刷新 Skill 列表。

完整安装、更新和卸载说明见 [安装指南](docs/INSTALL.zh-CN.md)。

## 在 Codex 中使用

上传一个录音或含音轨的视频，然后直接说：

> 请使用会议录音分析 Skill 处理我上传的录音。预计 3 人，日语为主。请输出完整转录、重点摘要、决定、待办和时间轴。

光学研究会议：

> 请使用会议录音分析 Skill 处理上传的录音。预计 4 人，英语和日语混合，主题是光学边缘检测，请加载 optical_edge_ml 术语表，并总结教授提出的修改意见。

继续提问：

> 根据刚才的录音，关于 defocus 容许范围讨论了什么？请给出说话人和时间位置。

Codex 会从当前任务的附件信息取得真实本地路径；不要猜测或硬编码附件目录。更多示例见 [使用指南](docs/USAGE.zh-CN.md)。

## 主要输出

后端 Job 目录通常包含：

- `transcript_final.json`、`.txt`、`.vtt`：原始最终转录；
- `transcript_cleaned.json`、`.txt`、`.vtt`：不改变时间戳和说话人的清理版本；
- `transcript_review_package.json`、`.txt`：技术复核包；
- `meeting_analysis.json`、`.md`：证据化会议分析；
- `meeting_timeline.md`：主题时间轴；
- `meeting_source_index.json`：结论到原始 cue 的索引；
- `meeting_skill_console.log`：Skill 与子进程日志；
- `meeting_skill_run.json`：输入、配置、状态和输出清单。

这些运行产物可能包含敏感会议内容，不应提交到 GitHub。

## 验证

纯静态和单元测试不会加载模型或处理真实录音：

```powershell
$PythonExe = (Resolve-Path -LiteralPath (Read-Host "请输入可用的 python.exe")).Path
$env:PYTHONUTF8 = "1"
& $PythonExe .\scripts\validate_release.py
& $PythonExe -m unittest discover -s .\skills\meeting-audio-transcription-analysis\tests -v
```

构建两个发布压缩包：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_package.ps1 `
  -PythonExecutable $PythonExe
```

产物写入 `dist`，并被 `.gitignore` 排除。

## 仓库结构

安装型 Skill 位于 `skills/meeting-audio-transcription-analysis`；仓库根目录只放发布文档、配置示例、安装/验证脚本和 CI。逐文件放置说明见 [仓库布局](docs/REPOSITORY_LAYOUT.zh-CN.md)。

## 隐私与安全

- 所有转录与分析默认在本机执行；
- 不要把令牌写进 Skill、命令、日志或 Manifest；
- 不要提交 `local_backend.json`、录音、Job、日志、模型和环境；
- 匿名说话人标签只在单次录音内部有效，不代表跨录音身份；
- Skill 不根据声音推断姓名、性别、年龄或职务。

## 许可证状态

本发布包暂未包含 `LICENSE`。在仓库公开供他人复制、修改或分发前，请由仓库所有者明确选择许可证；本项目不会替所有者自动作出许可决定。

## 建议 GitHub 信息

- 仓库名：`meeting-audio-transcription-analysis`
- 描述：面向 Codex 的本地多语种会议录音转录与证据化分析 Skill，支持日英混合、匿名说话人、时间戳转录、摘要、决定、待办和主题时间轴。
- Topics：`codex-skill`、`meeting-transcription`、`speech-to-text`、`speaker-diarization`、`qwen3-asr`、`pyannote`、`multilingual-asr`、`japanese-asr`、`audio-analysis`、`local-ai`
