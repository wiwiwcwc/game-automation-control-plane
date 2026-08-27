[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ExecutablePath,
    [string]$DataDirectory
)

$ErrorActionPreference = "Stop"
$resolvedExecutable = (Resolve-Path -LiteralPath $ExecutablePath).Path
if ([string]::IsNullOrWhiteSpace($DataDirectory)) {
    $DataDirectory = Join-Path $env:TEMP ("game-control-plane-smoke-" + [Guid]::NewGuid().ToString("N"))
}
$resolvedData = New-Item -ItemType Directory -Force -Path $DataDirectory

$env:GAME_CONTROL_PLANE_PACKAGED_SMOKE = "1"
$env:GAME_CONTROL_PLANE_DATA_DIR = $resolvedData.FullName
$smokeDataArgument = '--game-control-plane-smoke-data="' + $resolvedData.FullName + '"'
$process = Start-Process -FilePath $resolvedExecutable -ArgumentList @(
    "--game-control-plane-packaged-smoke",
    $smokeDataArgument
) -Wait -PassThru
if ($process.ExitCode -ne 0) {
    throw "Packaged smoke process exited with code $($process.ExitCode)."
}

$database = Join-Path $resolvedData.FullName "control_plane.sqlite3"
if (-not (Test-Path -LiteralPath $database -PathType Leaf)) {
    throw "Packaged smoke did not create its SQLite database at $database."
}
if ((Get-Item -LiteralPath $database).Length -le 0) {
    throw "Packaged smoke created an empty SQLite database at $database."
}
Write-Output "Packaged smoke passed: $resolvedExecutable"
Write-Output "Smoke data directory: $($resolvedData.FullName)"
