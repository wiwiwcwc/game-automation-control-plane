[CmdletBinding()]
param(
    [string]$InstallDirectory = "",
    [string]$DownloadDirectory = ""
)

$ErrorActionPreference = "Stop"

$innoVersion = "7.1.0"
$installerName = "innosetup-$innoVersion-x64.exe"
$installerUrl = "https://github.com/jrsoftware/issrc/releases/download/is-7_1_0/$installerName"
$expectedSha256 = "0362a383ed217d4c4239b5933866dd96d3eb2102737da92f80f6057a4b40df2f"
$expectedPublisher = "Pyrsys B.V."

if ([string]::IsNullOrWhiteSpace($DownloadDirectory)) {
    $DownloadDirectory = Join-Path $env:TEMP "hsiesta-inno-setup"
}
if ([string]::IsNullOrWhiteSpace($InstallDirectory)) {
    $InstallDirectory = Join-Path $env:TEMP "hsiesta-inno-setup-$innoVersion"
}

$downloadRoot = [System.IO.Path]::GetFullPath($DownloadDirectory)
$installRoot = [System.IO.Path]::GetFullPath($InstallDirectory)
New-Item -ItemType Directory -Force -Path $downloadRoot | Out-Null

$installerPath = Join-Path $downloadRoot $installerName
$isccPath = Join-Path $installRoot "ISCC.exe"

function Assert-SignedOfficialFile {
    param([string]$Path)

    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne "Valid") {
        throw "Authenticode validation failed for ${Path}: $($signature.Status) - $($signature.StatusMessage)"
    }
    $subject = $signature.SignerCertificate.Subject
    if ($subject -notmatch [regex]::Escape($expectedPublisher)) {
        throw "Unexpected Authenticode publisher for ${Path}: $subject"
    }
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

if (Test-Path -LiteralPath $installerPath -PathType Leaf) {
    $existingHash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($existingHash -ne $expectedSha256) {
        throw "Existing Inno Setup download has an unexpected SHA-256: $installerPath"
    }
}
else {
    Write-Host "Downloading the pinned official Inno Setup $innoVersion compiler..."
    Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
}

$actualHash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedSha256) {
    throw "Inno Setup download SHA-256 mismatch: expected $expectedSha256, got $actualHash"
}
Assert-SignedOfficialFile -Path $installerPath

if (Test-Path -LiteralPath $isccPath -PathType Leaf) {
    $installedVersion = Get-InnoCompilerVersion -CompilerPath $isccPath
    if ($installedVersion -notmatch '^7\.1\.0(?:\.|$)') {
        throw "Existing ISCC.exe has an unexpected version '$installedVersion': $isccPath"
    }
}
else {
    if (Test-Path -LiteralPath $installRoot) {
        $existingEntries = Get-ChildItem -LiteralPath $installRoot -Force
        if ($existingEntries.Count -gt 0) {
            throw "Refusing to install into a non-empty directory without a verified 7.1.0 ISCC.exe: $installRoot"
        }
    }
    New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
    $arguments = @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        ('/TASKS=""'),
        ('/DIR="' + $installRoot + '"')
    )
    $process = Start-Process -FilePath $installerPath -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Inno Setup $innoVersion installation failed with exit code $($process.ExitCode)."
    }
}

if (-not (Test-Path -LiteralPath $isccPath -PathType Leaf)) {
    throw "Inno Setup installation completed without ISCC.exe: $isccPath"
}
$finalInfo = Get-Item -LiteralPath $isccPath
$finalVersion = Get-InnoCompilerVersion -CompilerPath $isccPath
if ($finalVersion -notmatch '^7\.1\.0(?:\.|$)') {
    throw "Installed ISCC.exe has an unexpected version '$finalVersion': $isccPath"
}
Assert-SignedOfficialFile -Path $isccPath
Write-Output $isccPath
