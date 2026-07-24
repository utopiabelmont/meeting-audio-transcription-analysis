[CmdletBinding()]
param(
    [string]$ProjectRoot,
    [string]$AppDir,
    [string]$PyannotePython,
    [string]$Ffprobe,
    [string]$CodexSkillsRoot,
    [switch]$Update
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$skillName = "meeting-audio-transcription-analysis"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$sourceSkill = Join-Path $repositoryRoot "skills\$skillName"

function Resolve-ExistingDirectory {
    param([string]$Value, [string]$Label)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }
    if (-not (Test-Path -LiteralPath $Value -PathType Container)) {
        throw "$Label 不存在或不是目录：$Value"
    }
    return (Resolve-Path -LiteralPath $Value).Path
}

function Resolve-ExistingFile {
    param([string]$Value, [string]$Label)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }
    if (-not (Test-Path -LiteralPath $Value -PathType Leaf)) {
        throw "$Label 不存在或不是文件：$Value"
    }
    return (Resolve-Path -LiteralPath $Value).Path
}

function Get-ConfigValue {
    param([object]$ConfigObject, [string]$PropertyName)
    $property = $ConfigObject.PSObject.Properties[$PropertyName]
    if ($null -eq $property -or $null -eq $property.Value) {
        return ""
    }
    return [string]$property.Value
}

if (-not (Test-Path -LiteralPath (Join-Path $sourceSkill "SKILL.md") -PathType Leaf)) {
    throw "仓库中的 Skill 不完整：$sourceSkill"
}

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

$skillsRootFull = [IO.Path]::GetFullPath($CodexSkillsRoot)
$destinationSkill = Join-Path $skillsRootFull $skillName
$existingConfigPath = Join-Path $destinationSkill "local_backend.json"
$hasNewBackendArguments = -not (
    [string]::IsNullOrWhiteSpace($ProjectRoot) -and
    [string]::IsNullOrWhiteSpace($AppDir) -and
    [string]::IsNullOrWhiteSpace($PyannotePython) -and
    [string]::IsNullOrWhiteSpace($Ffprobe)
)
$reuseExistingConfig = $false

if ((Test-Path -LiteralPath $destinationSkill) -and -not $Update) {
    throw "目标 Skill 已存在：$destinationSkill。更新请显式使用 -Update。"
}

if (-not $hasNewBackendArguments) {
    if ($Update -and (Test-Path -LiteralPath $existingConfigPath -PathType Leaf)) {
        $existingConfig = Get-Content -LiteralPath $existingConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $ProjectRoot = Get-ConfigValue -ConfigObject $existingConfig -PropertyName "project_root"
        $AppDir = Get-ConfigValue -ConfigObject $existingConfig -PropertyName "app_dir"
        $PyannotePython = Get-ConfigValue -ConfigObject $existingConfig -PropertyName "pyannote_python"
        $Ffprobe = Get-ConfigValue -ConfigObject $existingConfig -PropertyName "ffprobe"
        $reuseExistingConfig = $true
    }
    else {
        throw "首次安装必须提供 -ProjectRoot，或提供明确的 AppDir、PyannotePython 和 Ffprobe。"
    }
}

$resolvedProjectRoot = Resolve-ExistingDirectory -Value $ProjectRoot -Label "ProjectRoot"
$resolvedAppDir = Resolve-ExistingDirectory -Value $AppDir -Label "AppDir"

if ($null -eq $resolvedProjectRoot -and $null -ne $resolvedAppDir) {
    $resolvedProjectRoot = Split-Path -Parent $resolvedAppDir
}
if ($null -eq $resolvedProjectRoot) {
    throw "无法确定后端根目录。请提供 -ProjectRoot 或 -AppDir。"
}
if ($null -eq $resolvedAppDir) {
    $resolvedAppDir = Resolve-ExistingDirectory `
        -Value (Join-Path $resolvedProjectRoot "app") `
        -Label "推导的 AppDir"
}

$resolvedPyannotePython = Resolve-ExistingFile -Value $PyannotePython -Label "PyannotePython"
if ($null -eq $resolvedPyannotePython) {
    $resolvedPyannotePython = Resolve-ExistingFile `
        -Value (Join-Path $resolvedProjectRoot "conda\envs\pyannote\python.exe") `
        -Label "推导的 PyannotePython"
}

$resolvedFfprobe = Resolve-ExistingFile -Value $Ffprobe -Label "Ffprobe"
if ($null -eq $resolvedFfprobe) {
    $resolvedFfprobe = Resolve-ExistingFile `
        -Value (Join-Path $resolvedProjectRoot "conda\envs\pyannote\Library\bin\ffprobe.exe") `
        -Label "推导的 Ffprobe"
}

$requiredBackendFiles = @(
    (Join-Path $resolvedAppDir "run_pipeline_complete.py"),
    (Join-Path $resolvedAppDir "generate_vtt.py"),
    (Join-Path $resolvedAppDir "config\transcript_cleaning_base.json")
)
foreach ($requiredFile in $requiredBackendFiles) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "后端关键文件不存在：$requiredFile"
    }
}

New-Item -ItemType Directory -Path $skillsRootFull -Force | Out-Null
New-Item -ItemType Directory -Path $destinationSkill -Force | Out-Null

Get-ChildItem -LiteralPath $sourceSkill -Recurse -File -Force | ForEach-Object {
    $relativePath = $_.FullName.Substring($sourceSkill.Length + 1)
    if ($relativePath -eq "local_backend.json" -or $_.Extension -eq ".pyc") {
        return
    }
    if ($relativePath -match "(^|[\\/])__pycache__([\\/]|$)") {
        return
    }
    $destinationFile = Join-Path $destinationSkill $relativePath
    $destinationDirectory = Split-Path -Parent $destinationFile
    New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $destinationFile -Force
}

$backendConfig = [ordered]@{
    project_root = $resolvedProjectRoot
    app_dir = $resolvedAppDir
    pyannote_python = $resolvedPyannotePython
    ffprobe = $resolvedFfprobe
}
if (-not $reuseExistingConfig) {
    $configJson = $backendConfig | ConvertTo-Json -Depth 4
    $utf8WithoutBom = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($existingConfigPath, $configJson + [Environment]::NewLine, $utf8WithoutBom)
}

Write-Host "安装完成：$destinationSkill"
Write-Host "本地后端配置：$existingConfigPath"
Write-Host "请重新打开 Codex 任务或刷新 Skill 列表。"
