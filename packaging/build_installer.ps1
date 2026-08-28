[CmdletBinding()]
param(
    [string]$IsccPath = "",
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$package = Join-Path $projectRoot "dist\GameAutomationControlPlane"
$iss = Join-Path $PSScriptRoot "hsiesta.iss"
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $dist = Join-Path $projectRoot "dist"
}
else {
    $dist = [System.IO.Path]::GetFullPath($OutputDirectory)
}
$versionPattern = '(?m)^\s*version\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"\s*$'

function Read-ProjectVersion {
    $projectMetadata = Get-Content -LiteralPath (Join-Path $projectRoot "pyproject.toml") -Raw
    $metadataMatch = [regex]::Match($projectMetadata, $versionPattern)
    if (-not $metadataMatch.Success) {
        throw "Unable to read a semver project version from pyproject.toml."
    }

    $runtimeMetadata = Get-Content -LiteralPath (Join-Path $projectRoot "src\game_control_plane\__init__.py") -Raw
    $runtimeMatch = [regex]::Match($runtimeMetadata, '__version__\s*=\s*"([^"]+)"')
    if (-not $runtimeMatch.Success) {
        throw "Unable to read __version__ from src\game_control_plane\__init__.py."
    }

    $metadataVersion = $metadataMatch.Groups[1].Value
    $runtimeVersion = $runtimeMatch.Groups[1].Value
    if ($metadataVersion -ne $runtimeVersion) {
        throw "Project version mismatch: pyproject.toml=$metadataVersion, __init__.py=$runtimeVersion."
    }
    return $metadataVersion
}

function Resolve-Iscc {
    param([string]$RequestedPath)

    $candidates = [System.Collections.Generic.List[string]]::new()
    if (-not [string]::IsNullOrWhiteSpace($RequestedPath)) {
        $candidates.Add($RequestedPath)
    }

    if ($env:ProgramFiles) {
        $candidates.Add((Join-Path $env:ProgramFiles "Inno Setup 7\ISCC.exe"))
    }
    if (${env:ProgramFiles(x86)}) {
        $candidates.Add((Join-Path ${env:ProgramFiles(x86)} "Inno Setup 7\ISCC.exe"))
    }
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        $candidates.Add($command.Source)
    }

    foreach ($candidate in $candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    throw "Inno Setup 7.1.0 ISCC.exe was not found. Pass -IsccPath explicitly or install the verified official compiler."
}

function Get-InnoCompilerVersion {
    param([string]$CompilerPath)

    $compilerInfo = Get-Item -LiteralPath $CompilerPath
    $directVersion = "$($compilerInfo.VersionInfo.ProductVersion)".Trim()
    if ($directVersion -and $directVersion -ne "0.0.0.0") {
        return $directVersion
    }

    # ISCC.exe in the official 7.1.0 distribution has a zeroed PE product
    # version. Its adjacent signed Inno uninstaller carries the distribution
    # version, so use that metadata when the compiler resource is unavailable.
    $uninstallerVersions = @(Get-ChildItem -LiteralPath $compilerInfo.Directory.FullName -Filter "unins*.exe" -File -ErrorAction SilentlyContinue | ForEach-Object {
        "$($_.VersionInfo.ProductVersion)".Trim()
    } | Where-Object { $_ -and $_ -ne "0.0.0.0" })
    if ($uninstallerVersions.Count -eq 1) {
        return $uninstallerVersions[0]
    }
    return $directVersion
}

function Get-RelativePath {
    param(
        [string]$Root,
        [string]$Path
    )

    return $Path.Substring($Root.Length).TrimStart('\', '/')
}

function Assert-OnedirPackage {
    if (-not (Test-Path -LiteralPath $package -PathType Container)) {
        throw "The existing PyInstaller onedir package is missing: $package"
    }

    $required = @(
        "GameAutomationControlPlane.exe",
        "_internal\game_control_plane\persistence\migrations\001_initial.sql",
        "_internal\game_control_plane\assets\app_icon.png",
        "_internal\game_control_plane\assets\app_icon.ico",
        "_internal\PySide6\plugins\platforms\qwindows.dll",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "licenses\LGPL-3.0-only.txt",
        "licenses\GPL-3.0-only.txt"
    )
    foreach ($relative in $required) {
        $candidate = Join-Path $package $relative
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw "Required onedir file is missing: $candidate"
        }
    }

    $forbiddenSegments = @("build", "dist", "tests", "codex-runtimes", ".git", ".venv", "__pycache__")
    $entries = Get-ChildItem -LiteralPath $package -Recurse -Force
    foreach ($entry in $entries) {
        $relative = Get-RelativePath -Root $package -Path $entry.FullName
        $segments = $relative -split '[\\/]'
        if ($segments | Where-Object { $forbiddenSegments -contains $_.ToLowerInvariant() }) {
            throw "Forbidden development/runtime payload in onedir package: $relative"
        }
        if ($segments | Where-Object { $_ -ieq "pyproject.toml" }) {
            throw "Project metadata must not be packaged: $relative"
        }
    }
}

$version = Read-ProjectVersion
Assert-OnedirPackage

if (-not (Test-Path -LiteralPath $iss -PathType Leaf)) {
    throw "Inno Setup script is missing: $iss"
}

$resolvedIscc = Resolve-Iscc -RequestedPath $IsccPath
$compilerVersion = Get-InnoCompilerVersion -CompilerPath $resolvedIscc
if ($compilerVersion -notmatch '^7\.1\.0(?:\.|$)') {
    throw "Expected Inno Setup 7.1.0 ISCC.exe, found ProductVersion '$compilerVersion' at $resolvedIscc."
}
$isccInfo = Get-Item -LiteralPath $resolvedIscc

$compilerRoot = $isccInfo.Directory.FullName
foreach ($languageFile in @("Default.isl", "Languages\ChineseSimplified.isl")) {
    $languagePath = Join-Path $compilerRoot $languageFile
    if (-not (Test-Path -LiteralPath $languagePath -PathType Leaf)) {
        throw "The verified Inno Setup distribution is missing the required language file: $languagePath"
    }
}

$output = Join-Path $dist "Hsiesta-$version-Setup.exe"
$hashFile = "$output.sha256"
New-Item -ItemType Directory -Force -Path $dist | Out-Null
foreach ($target in @($output, $hashFile)) {
    if (Test-Path -LiteralPath $target) {
        throw "Refusing to overwrite an existing installer artifact: $target"
    }
}

Push-Location $projectRoot
try {
    & $resolvedIscc "/Qp" "/DAppVersion=$version" ('/O' + $dist) $iss
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
    throw "Inno Setup did not create the expected installer: $output"
}

$hash = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  Hsiesta-$version-Setup.exe" | Set-Content -LiteralPath $hashFile -Encoding ascii
Write-Output "Installer built: $output"
Write-Output "Installer SHA-256: $hash"
