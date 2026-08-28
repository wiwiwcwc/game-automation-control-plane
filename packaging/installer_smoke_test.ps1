[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [switch]$SkipPackagedSmoke,
    [switch]$KeepWorkspace
)

$ErrorActionPreference = "Stop"

$installer = (Resolve-Path -LiteralPath $InstallerPath).Path
$installerInfo = Get-Item -LiteralPath $installer
if ($installerInfo.Extension -ne ".exe") {
    throw "InstallerPath must point to an .exe installer: $installer"
}

$tempRoot = [System.IO.Path]::GetFullPath($env:TEMP)
$workspaceName = "hsiesta-installer-smoke-" + [Guid]::NewGuid().ToString("N")
$workspace = Join-Path $tempRoot $workspaceName
$installDirectory = Join-Path $workspace "install"
$dataDirectory = Join-Path $workspace "data\GameAutomationControlPlane"
$downloadLog = Join-Path $workspace "installer.log"
$groupName = "Hsiesta Smoke " + [Guid]::NewGuid().ToString("N")
$programsDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::Programs)
$desktopDirectory = [Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)
$startMenuDirectory = Join-Path $programsDirectory $groupName
$startMenuShortcut = Join-Path $startMenuDirectory "休汐 Hsiesta.lnk"
$uninstallShortcut = Join-Path $startMenuDirectory "Uninstall 休汐 Hsiesta.lnk"
$desktopShortcut = Join-Path $desktopDirectory "休汐 Hsiesta.lnk"
$sentinel = Join-Path $dataDirectory "installer-smoke-sentinel.txt"
$uninstallRegistryKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{57c41fc3-082e-4bf2-98ed-c6ac900d7211}_is1"

function Get-FullPath {
    param([string]$Path)
    return [System.IO.Path]::GetFullPath($Path)
}

function Assert-ChildPath {
    param(
        [string]$Root,
        [string]$Path,
        [switch]$AllowRoot
    )

    $rootFull = (Get-FullPath $Root).TrimEnd('\', '/')
    $pathFull = Get-FullPath $Path
    $prefix = $rootFull + [System.IO.Path]::DirectorySeparatorChar
    $inside = $pathFull.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)
    if ((-not $AllowRoot -and -not $inside) -or ($AllowRoot -and $pathFull -ne $rootFull -and -not $inside)) {
        throw "Refusing to use a path outside the smoke root. Root='$rootFull', Path='$pathFull'"
    }
    return $pathFull
}

function Assert-NoReparsePoint {
    param([string]$Path)

    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing to operate on a reparse point: $Path"
        }
    }
}

function Get-ExactInstalledProcesses {
    param([string]$Executable)

    $resolved = (Get-FullPath $Executable)
    return @(Get-CimInstance Win32_Process -Filter "Name = 'GameAutomationControlPlane.exe'" | Where-Object {
        $_.ExecutablePath -and [string]::Equals((Get-FullPath $_.ExecutablePath), $resolved, [System.StringComparison]::OrdinalIgnoreCase)
    })
}

$originalSmokeEnv = $env:GAME_CONTROL_PLANE_PACKAGED_SMOKE
$originalDataEnv = $env:GAME_CONTROL_PLANE_DATA_DIR
$success = $false
$cleanupAllowed = $false

try {
    New-Item -ItemType Directory -Force -Path $workspace | Out-Null
    Assert-ChildPath -Root $tempRoot -Path $workspace
    Assert-NoReparsePoint -Path $workspace
    Assert-ChildPath -Root $workspace -Path $installDirectory
    Assert-ChildPath -Root $workspace -Path $dataDirectory
    Assert-ChildPath -Root $workspace -Path $downloadLog
    Assert-ChildPath -Root $workspace -Path $sentinel

    if (Test-Path -LiteralPath $desktopShortcut) {
        throw "The smoke test requires the target desktop shortcut to be absent before installation: $desktopShortcut"
    }
    if (Test-Path -LiteralPath $startMenuDirectory) {
        throw "The smoke test requires its unique Start Menu group to be absent: $startMenuDirectory"
    }

    New-Item -ItemType Directory -Force -Path $dataDirectory | Out-Null
    Set-Content -LiteralPath $sentinel -Value "installer smoke data must survive uninstall" -Encoding utf8

    $installArguments = @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        ('/DIR="' + $installDirectory + '"'),
        ('/GROUP="' + $groupName + '"'),
        ('/TASKS=""'),
        ('/LOG="' + $downloadLog + '"')
    )
    $installProcess = Start-Process -FilePath $installer -ArgumentList $installArguments -Wait -PassThru
    if ($installProcess.ExitCode -ne 0) {
        throw "Silent installer exited with code $($installProcess.ExitCode)."
    }

    $installedExe = Join-Path $installDirectory "GameAutomationControlPlane.exe"
    $required = @(
        "GameAutomationControlPlane.exe",
        "_internal",
        "_internal\PySide6\plugins\platforms\qwindows.dll",
        "_internal\game_control_plane\persistence\migrations\001_initial.sql",
        "_internal\game_control_plane\assets\app_icon.ico",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "licenses\LGPL-3.0-only.txt",
        "licenses\GPL-3.0-only.txt"
    )
    foreach ($relative in $required) {
        $candidate = Join-Path $installDirectory $relative
        if (-not (Test-Path -LiteralPath $candidate)) {
            throw "Installed payload is missing: $candidate"
        }
    }

    if (-not (Test-Path -LiteralPath $startMenuShortcut -PathType Leaf)) {
        throw "Expected Start Menu shortcut is missing: $startMenuShortcut"
    }
    if (-not (Test-Path -LiteralPath $uninstallShortcut -PathType Leaf)) {
        throw "Expected Start Menu uninstall shortcut is missing: $uninstallShortcut"
    }
    if (Test-Path -LiteralPath $desktopShortcut) {
        throw "Desktop shortcut was created although the task is unchecked by default: $desktopShortcut"
    }
    if (-not (Test-Path -LiteralPath $uninstallRegistryKey)) {
        throw "Per-user uninstall registration is missing: $uninstallRegistryKey"
    }

    $env:GAME_CONTROL_PLANE_PACKAGED_SMOKE = "1"
    $env:GAME_CONTROL_PLANE_DATA_DIR = $dataDirectory
    if ($SkipPackagedSmoke) {
        Write-Warning "Packaged smoke was explicitly skipped; install and uninstall checks still ran."
    }
    else {
        & (Join-Path $PSScriptRoot "smoke_test.ps1") -ExecutablePath $installedExe -DataDirectory $dataDirectory
    }

    if (-not $SkipPackagedSmoke -and -not (Test-Path -LiteralPath (Join-Path $dataDirectory "control_plane.sqlite3") -PathType Leaf)) {
        throw "The installed executable did not create its SQLite database."
    }

    $uninstallers = @(Get-ChildItem -LiteralPath $installDirectory -Filter "unins*.exe" -File)
    if ($uninstallers.Count -ne 1) {
        throw "Expected exactly one Inno Setup uninstaller, found $($uninstallers.Count) in $installDirectory."
    }
    $uninstaller = $uninstallers[0].FullName
    $uninstallProcess = Start-Process -FilePath $uninstaller -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART"
    ) -Wait -PassThru
    if ($uninstallProcess.ExitCode -ne 0) {
        throw "Silent uninstaller exited with code $($uninstallProcess.ExitCode)."
    }

    if (Test-Path -LiteralPath $installDirectory) {
        throw "Install directory remains after uninstall: $installDirectory"
    }
    if (Test-Path -LiteralPath $startMenuDirectory) {
        throw "Start Menu group remains after uninstall: $startMenuDirectory"
    }
    if (Test-Path -LiteralPath $desktopShortcut) {
        throw "Desktop shortcut remains after uninstall: $desktopShortcut"
    }
    if (Test-Path -LiteralPath $uninstallRegistryKey) {
        throw "Per-user uninstall registration remains after uninstall: $uninstallRegistryKey"
    }
    if (-not (Test-Path -LiteralPath $sentinel -PathType Leaf)) {
        throw "User data sentinel was deleted by uninstall: $sentinel"
    }
    if (-not $SkipPackagedSmoke -and -not (Test-Path -LiteralPath (Join-Path $dataDirectory "control_plane.sqlite3") -PathType Leaf)) {
        throw "SQLite data was deleted by uninstall: $dataDirectory"
    }
    if ((Get-ExactInstalledProcesses -Executable $installedExe).Count -ne 0) {
        throw "The installed executable still has a running process after uninstall."
    }

    $cleanupAllowed = $true
    $success = $true
    Write-Output "Installer install/uninstall smoke passed: $installer"
    Write-Output "Data sentinel survived: $sentinel"
}
finally {
    if ($null -eq $originalSmokeEnv) {
        Remove-Item Env:GAME_CONTROL_PLANE_PACKAGED_SMOKE -ErrorAction SilentlyContinue
    }
    else {
        $env:GAME_CONTROL_PLANE_PACKAGED_SMOKE = $originalSmokeEnv
    }
    if ($null -eq $originalDataEnv) {
        Remove-Item Env:GAME_CONTROL_PLANE_DATA_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:GAME_CONTROL_PLANE_DATA_DIR = $originalDataEnv
    }

    $running = @(Get-ExactInstalledProcesses -Executable (Join-Path $installDirectory "GameAutomationControlPlane.exe"))
    if ($running.Count -gt 0) {
        Write-Warning "Leaving smoke workspace because an exact installed process is still running: $workspace"
        $cleanupAllowed = $false
    }
    if (-not $KeepWorkspace -and $cleanupAllowed -and $success) {
        Assert-ChildPath -Root $tempRoot -Path $workspace
        Assert-NoReparsePoint -Path $workspace
        Remove-Item -LiteralPath $workspace -Recurse -Force
    }
    elseif (-not $success) {
        Write-Warning "Leaving smoke workspace for investigation: $workspace"
    }
    elseif ($KeepWorkspace) {
        Write-Output "Smoke workspace retained: $workspace"
    }
}
