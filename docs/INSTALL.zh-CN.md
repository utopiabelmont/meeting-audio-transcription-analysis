# 安装、更新与卸载

## 1. 安装前检查

本仓库只安装 Codex Skill。请先确认本地后端根目录下存在 `app` 目录、两个 Conda 环境和 ffprobe。安装脚本不会下载模型、创建 Conda 环境或修改后端算法。

## 2. 推荐：使用仓库安装脚本

首次安装：

```powershell
git clone https://github.com/utopiabelmont/meeting-audio-transcription-analysis.git
Set-Location .\meeting-audio-transcription-analysis
$BackendRoot = (Resolve-Path -LiteralPath (Read-Host "请输入 vtt_plus_analysis 根目录")).Path
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 `
  -ProjectRoot $BackendRoot
```

安装脚本会：

1. 校验仓库内 Skill 和后端关键文件；
2. 复制 `skills\meeting-audio-transcription-analysis`；
3. 在用户 Skill 安装目录创建 `local_backend.json`；
4. 不复制模型、环境、录音、Job 或日志；
5. 已存在同名 Skill 时停止，避免静默覆盖。

更新已安装 Skill 时使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 `
  -Update
```

`-Update` 只更新受版本控制的 Skill 文件，并保留已有 `local_backend.json`。若同时传入新的路径参数，则会在验证后更新本地配置。

## 3. 自定义后端组件路径

只给 `-ProjectRoot` 时，默认推导：

- App：`ProjectRoot\app`
- pyannote Python：`ProjectRoot\conda\envs\pyannote\python.exe`
- ffprobe：`ProjectRoot\conda\envs\pyannote\Library\bin\ffprobe.exe`

布局不同可显式传入：

```powershell
$Root = Read-Host "后端根目录"
$App = Read-Host "app目录"
$PyannotePython = Read-Host "pyannote python.exe"
$Ffprobe = Read-Host "ffprobe.exe"

powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 `
  -ProjectRoot $Root `
  -AppDir $App `
  -PyannotePython $PyannotePython `
  -Ffprobe $Ffprobe
```

路径中的空格、中文和日文会作为独立参数处理。

## 4. 通过 Codex Skill Installer 安装

当前 Codex 的安装器支持从 GitHub 子目录安装：

```powershell
$Installer = Join-Path $HOME ".codex\skills\.system\skill-installer\scripts\install-skill-from-github.py"
python $Installer `
  --repo utopiabelmont/meeting-audio-transcription-analysis `
  --path skills/meeting-audio-transcription-analysis
```

这种方式只复制 Skill，不会生成本机后端配置。安装后必须选择以下一种方式：

### 方式 A：设置环境变量

```powershell
[Environment]::SetEnvironmentVariable(
  "VTT_PLUS_ANALYSIS_ROOT",
  (Resolve-Path -LiteralPath (Read-Host "请输入 vtt_plus_analysis 根目录")).Path,
  "User"
)
```

重新启动 Codex 后生效。

### 方式 B：创建本地配置

把仓库的 `config\local_backend.example.json` 复制为：

```text
%USERPROFILE%\.codex\skills\meeting-audio-transcription-analysis\local_backend.json
```

然后填写 `project_root`，或分别填写 `app_dir`、`pyannote_python` 和 `ffprobe`。该文件包含本机路径，不应提交到 GitHub。

## 5. 配置优先级

运行器按以下规则解析：

1. 专用环境变量；
2. 安装目录中的 `local_backend.json` 对应字段；
3. 从 `project_root` 推导默认组件路径。

支持的环境变量：

- `VTT_PLUS_ANALYSIS_ROOT`
- `VTT_PLUS_APP_DIR`
- `VTT_PLUS_PYANNOTE_PYTHON`
- `VTT_PLUS_FFPROBE`

完全未配置或关键文件不存在时，Skill 会在加载模型前明确失败。

## 6. 验证安装

确认以下文件存在：

```powershell
$SkillRoot = Join-Path $HOME ".codex\skills\meeting-audio-transcription-analysis"
Test-Path (Join-Path $SkillRoot "SKILL.md")
Test-Path (Join-Path $SkillRoot "local_backend.json")
```

重新打开 Codex 任务后，Skill 名称应显示为 `meeting-audio-transcription-analysis`。

## 7. 卸载

预览将删除的准确路径：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall.ps1
```

确认后卸载：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall.ps1 -ConfirmRemoval
```

卸载脚本只删除 Skill 安装目录，不删除后端、Conda 环境、模型缓存、原始录音或既有 Job。

## 8. 许可证提示

当前发布包没有 `LICENSE`。公开发布前请由仓库所有者选择许可证；私有仓库可先保持现状。
