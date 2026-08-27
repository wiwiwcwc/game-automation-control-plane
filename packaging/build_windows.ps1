[CmdletBinding()]
param(
    [string]$PythonExecutable = "python"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$expectedPySideVersion = "6.11.2"
$actualPySideVersion = & $PythonExecutable -c "import PySide6; print(PySide6.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read the PySide6 version from $PythonExecutable."
}
if ($actualPySideVersion.Trim() -ne $expectedPySideVersion) {
    throw "Windows notices are pinned to PySide6 $expectedPySideVersion, but the build environment has $actualPySideVersion."
}

Push-Location $projectRoot
try {
    & $PythonExecutable -m PyInstaller --noconfirm --clean packaging\game_control_plane.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    $package = (Resolve-Path "dist\GameAutomationControlPlane").Path
    $internal = Join-Path $package "_internal"
    $internalNotice = Join-Path $internal "THIRD_PARTY_NOTICES.md"
    $internalProjectLicense = Join-Path $internal "LICENSE"
    $internalLicenses = Join-Path $internal "licenses"
    if (-not (Test-Path -LiteralPath $internalNotice -PathType Leaf)) {
        throw "Packaged third-party notice is missing: $internalNotice"
    }
    if (-not (Test-Path -LiteralPath $internalLicenses -PathType Container)) {
        throw "Packaged license directory is missing: $internalLicenses"
    }
    if (-not (Test-Path -LiteralPath $internalProjectLicense -PathType Leaf)) {
        throw "Packaged project license is missing: $internalProjectLicense"
    }

    Move-Item -LiteralPath $internalNotice -Destination (Join-Path $package "THIRD_PARTY_NOTICES.md")
    Move-Item -LiteralPath $internalProjectLicense -Destination (Join-Path $package "LICENSE")
    Move-Item -LiteralPath $internalLicenses -Destination (Join-Path $package "licenses")
    Write-Output "Windows package built with project and Qt/PySide6 license materials: $package"
}
finally {
    Pop-Location
}
