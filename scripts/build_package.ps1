[CmdletBinding()]
param(
    [string]$PythonExecutable = "python"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$skillName = "meeting-audio-transcription-analysis"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Split-Path -Parent $scriptDirectory
$sourceSkill = Join-Path $repositoryRoot "skills\$skillName"
$version = (Get-Content -LiteralPath (Join-Path $repositoryRoot "VERSION") -Raw -Encoding UTF8).Trim()
$distDirectory = Join-Path $repositoryRoot "dist"
$skillArchive = Join-Path $distDirectory "$skillName-skill-v$version.zip"
$repositoryArchive = Join-Path $distDirectory "$skillName-repository-v$version.zip"
$checksumFile = Join-Path $distDirectory "SHA256SUMS.txt"

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Copy-PublishableTree {
    param([string]$Source, [string]$Destination)

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Get-ChildItem -LiteralPath $Source -Recurse -File -Force | ForEach-Object {
        $relativePath = $_.FullName.Substring($Source.Length + 1)
        $parts = $relativePath -split "[\\/]"
        if ($parts[0] -in @(".git", "dist")) {
            return
        }
        if ($parts -contains "__pycache__") {
            return
        }
        if ($_.Name -eq "local_backend.json" -or $_.Extension -eq ".pyc") {
            return
        }
        $destinationFile = Join-Path $Destination $relativePath
        New-Item -ItemType Directory -Path (Split-Path -Parent $destinationFile) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $destinationFile -Force
    }
}

function New-PortableZip {
    param([string]$SourceDirectory, [string]$DestinationArchive)

    $sourceFull = [IO.Path]::GetFullPath($SourceDirectory).TrimEnd("\", "/")
    $archiveStream = [IO.File]::Open(
        $DestinationArchive,
        [IO.FileMode]::CreateNew,
        [IO.FileAccess]::Write,
        [IO.FileShare]::None
    )
    $archive = $null
    try {
        $archive = [System.IO.Compression.ZipArchive]::new(
            $archiveStream,
            [System.IO.Compression.ZipArchiveMode]::Create,
            $false
        )
        Get-ChildItem -LiteralPath $sourceFull -Recurse -File -Force |
            Sort-Object FullName |
            ForEach-Object {
                $relativePath = $_.FullName.Substring($sourceFull.Length + 1)
                $entryName = $relativePath.Replace("\", "/")
                $entry = $archive.CreateEntry(
                    $entryName,
                    [System.IO.Compression.CompressionLevel]::Optimal
                )
                $entry.LastWriteTime = $_.LastWriteTime
                $inputStream = [IO.File]::OpenRead($_.FullName)
                $outputStream = $entry.Open()
                try {
                    $inputStream.CopyTo($outputStream)
                }
                finally {
                    $outputStream.Dispose()
                    $inputStream.Dispose()
                }
            }
    }
    finally {
        if ($null -ne $archive) {
            $archive.Dispose()
        }
        else {
            $archiveStream.Dispose()
        }
    }
}

$env:PYTHONUTF8 = "1"
& $PythonExecutable (Join-Path $scriptDirectory "validate_release.py")
if ($LASTEXITCODE -ne 0) {
    throw "发布验证失败，未创建压缩包。"
}

if (-not (Test-Path -LiteralPath (Join-Path $sourceSkill "SKILL.md") -PathType Leaf)) {
    throw "Skill 源目录无效：$sourceSkill"
}

New-Item -ItemType Directory -Path $distDirectory -Force | Out-Null
foreach ($target in @($skillArchive, $repositoryArchive, $checksumFile)) {
    if (Test-Path -LiteralPath $target -PathType Leaf) {
        Remove-Item -LiteralPath $target -Force
    }
}

$temporaryBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$temporaryWork = Join-Path $temporaryBase ("meeting_skill_release_" + [Guid]::NewGuid().ToString("N"))
$temporaryWorkFull = [IO.Path]::GetFullPath($temporaryWork)
if (
    -not $temporaryWorkFull.StartsWith($temporaryBase, [StringComparison]::OrdinalIgnoreCase) -or
    -not ([IO.Path]::GetFileName($temporaryWorkFull)).StartsWith("meeting_skill_release_")
) {
    throw "临时目录校验失败：$temporaryWorkFull"
}

try {
    $skillStageRoot = Join-Path $temporaryWorkFull "skill-package"
    $skillStage = Join-Path $skillStageRoot $skillName
    Copy-PublishableTree -Source $sourceSkill -Destination $skillStage

    $repositoryStageRoot = Join-Path $temporaryWorkFull "repository-package"
    $repositoryStage = Join-Path $repositoryStageRoot $skillName
    Copy-PublishableTree -Source $repositoryRoot -Destination $repositoryStage

    New-PortableZip -SourceDirectory $skillStageRoot -DestinationArchive $skillArchive
    New-PortableZip -SourceDirectory $repositoryStageRoot -DestinationArchive $repositoryArchive

    $hashLines = @(
        (Get-FileHash -LiteralPath $skillArchive -Algorithm SHA256),
        (Get-FileHash -LiteralPath $repositoryArchive -Algorithm SHA256)
    ) | ForEach-Object {
        "$($_.Hash.ToLowerInvariant()) *$([IO.Path]::GetFileName($_.Path))"
    }
    $utf8WithoutBom = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText(
        $checksumFile,
        ($hashLines -join [Environment]::NewLine) + [Environment]::NewLine,
        $utf8WithoutBom
    )
}
finally {
    if (Test-Path -LiteralPath $temporaryWorkFull -PathType Container) {
        Remove-Item -LiteralPath $temporaryWorkFull -Recurse -Force
    }
}

Write-Host "Skill 安装包：$skillArchive"
Write-Host "GitHub 仓库包：$repositoryArchive"
Write-Host "SHA-256：$checksumFile"
