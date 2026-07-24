# 安装与使用

## Skill 与后端的关系

`meeting-audio-transcription-analysis` 只包含 Codex Skill、会议分析脚本、校验脚本、规则和模板，不包含模型、Conda 环境或转录后端。

安装后的典型目录为：

```text
%USERPROFILE%\.codex\skills\meeting-audio-transcription-analysis
```

本地后端项目根应包含：

```text
backend_root\
├─ app\
│  ├─ run_pipeline_complete.py
│  ├─ generate_vtt.py
│  └─ config\
└─ conda\
   └─ envs\
      ├─ pyannote\
      └─ qwen3_asr\
```

还需保留现有模型缓存、ffmpeg/ffprobe，以及后端访问受限模型时所需的 Hugging Face 授权。不要把令牌写入聊天、日志、manifest、Skill 文件或 GitHub 仓库。

## 安装 Skill

将完整的 `meeting-audio-transcription-analysis` 文件夹复制到：

```text
%USERPROFILE%\.codex\skills\
```

确认以下文件存在：

```text
%USERPROFILE%\.codex\skills\meeting-audio-transcription-analysis\SKILL.md
```

随后新建 Codex 任务或重新加载 Skill 列表。

## 配置本机后端

推荐只设置项目根：

```powershell
$BackendRoot = (Resolve-Path -LiteralPath (Read-Host '请输入后端根目录')).Path
$env:VTT_PLUS_ANALYSIS_ROOT = $BackendRoot
```

如需持久保存，可使用 Windows 用户级环境变量：

```powershell
[Environment]::SetEnvironmentVariable(
  'VTT_PLUS_ANALYSIS_ROOT',
  (Resolve-Path -LiteralPath (Read-Host '请输入后端根目录')).Path,
  'User'
)
```

重新启动 Codex 后生效。

也可分别设置：

```powershell
$env:VTT_PLUS_APP_DIR = (Resolve-Path -LiteralPath (Read-Host '请输入app目录')).Path
$env:VTT_PLUS_PYANNOTE_PYTHON = (Resolve-Path -LiteralPath (Read-Host '请输入pyannote python.exe')).Path
$env:VTT_PLUS_FFPROBE = (Resolve-Path -LiteralPath (Read-Host '请输入ffprobe.exe')).Path
```

第三种方式是在安装后的 Skill 根创建 `local_backend.json`：

```json
{
  "project_root": "填写本机后端根目录"
}
```

也可使用完整配置：

```json
{
  "project_root": "填写本机后端根目录",
  "app_dir": "填写本机app目录",
  "pyannote_python": "填写pyannote环境的python.exe",
  "ffprobe": "填写ffprobe.exe"
}
```

`local_backend.json` 含本机路径，禁止提交到 GitHub 或打入发布压缩包。仓库中只保留脱敏的示例配置。

路径优先级为：

1. 对应组件的专用环境变量；
2. `local_backend.json` 中对应字段；
3. 从 `project_root` 推导。

`project_root` 优先使用 `VTT_PLUS_ANALYSIS_ROOT`，其次使用 `local_backend.json.project_root`，最后可由显式 `app_dir` 的父目录推导。完全没有配置时，runner 会在加载模型前明确失败，不会尝试其他用户的固定目录。

## 验证安装

使用 Skill Creator 自带校验器检查 Skill 结构：

```powershell
$PythonExe = (Resolve-Path -LiteralPath (Read-Host '请输入可用的python.exe')).Path
& $PythonExe "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" `
  "$env:USERPROFILE\.codex\skills\meeting-audio-transcription-analysis"
```

runner 每次启动还会验证：

- 后端 app 目录；
- pyannote Python；
- ffprobe；
- `run_pipeline_complete.py`；
- `generate_vtt.py`；
- 通用清理配置；
- Skill 分析与输出校验脚本。

任一项缺失都会在模型启动前给出具体路径和配置提示。

## 在 Codex 中使用

上传一份录音或带音轨的视频，然后用自然语言描述需求。Codex 会从当前任务的 `Files mentioned` 获取真实附件路径，不应猜测附件缓存目录。

普通会议：

> 请使用会议录音分析Skill处理我上传的录音。预计3人，日语为主。请输出完整转录、重点摘要、决定、待办和时间轴。

光学研究会议：

> 请使用会议录音分析Skill处理上传的录音。预计4人，英语和日语混合，主题是光学边缘检测，请加载optical_edge_ml术语表，并总结教授提出的修改意见。

录音问答：

> 根据刚才的录音，关于defocus容许范围讨论了什么？请给出说话人和时间位置。

可补充会议标题、日期、主题、预计人数、预期语言、领域、术语表、已知参与者、报告语言及问题。`languages` 仅作为报告上下文；后端仍固定使用 `auto + per-chunk`。

## 更新与卸载

更新时只替换 Skill 的 `SKILL.md`、`scripts`、`references`、`assets` 和 `agents`。保留本机 `local_backend.json`、后端项目、已有 jobs、Conda 环境和模型缓存。

卸载时只删除：

```text
%USERPROFILE%\.codex\skills\meeting-audio-transcription-analysis
```

不要删除后端项目、Conda 环境、缓存或后端 `app\jobs`。

## 常见错误

### 未配置或配置路径不存在

设置 `VTT_PLUS_ANALYSIS_ROOT`，或创建本机 `local_backend.json`。根据错误中列出的绝对路径检查 app、解释器和 ffprobe。

### 附件不支持或没有音轨

使用可读取的 wav、mp3、m4a、mp4、mov 或 mkv 文件。Skill 会用 ffprobe 检查实际音轨，而不是只相信扩展名。

### 模型授权失败

在本机环境恢复原有 Hugging Face 授权，不要把 token 写入配置文件或日志。

### 已有 Job 不匹配

录音 SHA-256、预计人数或固定配置不同，请使用新 Job 名。只有完全相同且兼容的未完成任务才能显式 `--resume`。

### 转录后分析失败

对已完成 Job 单独重跑 `scripts\analyze_transcript.py`，不要仅为重新生成分析而再次加载转录模型。
