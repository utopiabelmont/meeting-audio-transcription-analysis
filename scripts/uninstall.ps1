[CmdletBinding()]
param(
    [string]$CodexSkillsRoot,
    [switch]$ConfirmRemoval
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$skillName = "meeting-audio-transcription-analysis"

if ([string]::IsNullOrWhiteSpace($CodexSkillsRoot)) {
    $codexBase = [Environment]::GetEnvironmentVariable("CODEX_HOME")
    if ([string]::IsNullOrWhiteSpace($codexBase)) {
        $userProfile = [Environment]::GetFolderPath("UserProfile")
        $CodexSkillsRoot = Join-Path $userProfile ".codex\skills"
    }
    else {
        $CodexSkillsRoot = Join-Path $codexBase "skills"
    }
}

$skillsRootFull = [IO.Path]::GetFullPath($CodexSkillsRoot).TrimEnd("\", "/")
$targetFull = [IO.Path]::GetFullPath((Join-Path $skillsRootFull $skillName)).TrimEnd("\", "/")
$targetParent = [IO.Path]::GetDirectoryName($targetFull).TrimEnd("\", "/")

if ($targetParent -ne $skillsRootFull) {
    throw "卸载目标不是 Skill 根目录的直接子目录，已拒绝：$targetFull"
}

if (-not (Test-Path -LiteralPath $targetFull -PathType Container)) {
    Write-Host "Skill 未安装：$targetFull"
    exit 0
}

if (-not (Test-Path -LiteralPath (Join-Path $targetFull "SKILL.md") -PathType Leaf)) {
    throw "目标目录缺少 SKILL.md，已拒绝递归删除：$targetFull"
}

if (-not $ConfirmRemoval) {
    Write-Host "预览：将只删除以下 Skill 目录："
    Write-Host $targetFull
    Write-Host "确认后重新运行并添加 -ConfirmRemoval。"
    exit 0
}

Remove-Item -LiteralPath $targetFull -Recurse -Force
Write-Host "已卸载 Skill：$targetFull"
Write-Host "本地转录后端、模型、环境、录音和 Job 未被删除。"
