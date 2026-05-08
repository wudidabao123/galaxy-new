param(
    [string]$OutputDir = "dist\GalaxyNewPortable",
    [string]$CloudflaredPath = "C:\Users\26043\Desktop\cloudflared-windows-amd64.exe",
    [string]$PythonVersion = "3.12.8",
    [switch]$NoZip
)

$ErrorActionPreference = "Stop"

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$OutputPath = if ([IO.Path]::IsPathRooted($OutputDir)) { $OutputDir } else { Join-Path $RepoRoot $OutputDir }
$CacheDir = Join-Path $RepoRoot ".portable-cache"
$PythonZip = Join-Path $CacheDir "python-$PythonVersion-embed-amd64.zip"
$GetPip = Join-Path $CacheDir "get-pip.py"
$PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"

Write-Step "Preparing output folder"
if (Test-Path $OutputPath) {
    Remove-Item -LiteralPath $OutputPath -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null

Write-Step "Copying Galaxy New source"
$excludeDirs = @(".git", ".keys", ".pytest_cache", "__pycache__", "pip", "dist", "runs", "uploads", "generated", "avatars", ".venv", "runtime", ".portable-cache")
$excludeFiles = @(".env", "galaxy.db", "galaxy.db-shm", "galaxy.db-wal", "*.pyc", "*.pyo", "_test.png", "Bn")
$robocopyArgs = @(
    $RepoRoot,
    $OutputPath,
    "/E",
    "/XD"
) + $excludeDirs + @("/XF") + $excludeFiles + @("/R:2", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
& robocopy @robocopyArgs | Out-Null
if ($LASTEXITCODE -gt 7) {
    throw "robocopy failed with exit code $LASTEXITCODE"
}

Write-Step "Installing portable Python $PythonVersion"
$RuntimeDir = Join-Path $OutputPath "runtime"
$PythonDir = Join-Path $RuntimeDir "python"
New-Item -ItemType Directory -Force -Path $PythonDir | Out-Null
if (!(Test-Path $PythonZip)) {
    Invoke-WebRequest -Uri $PythonUrl -OutFile $PythonZip
}
Expand-Archive -Path $PythonZip -DestinationPath $PythonDir -Force

$PthFile = Get-ChildItem -Path $PythonDir -Filter "python*._pth" | Select-Object -First 1
if ($PthFile) {
    $pth = Get-Content $PthFile.FullName
    $pth = $pth | ForEach-Object { if ($_ -eq "#import site") { "import site" } else { $_ } }
    if ($pth -notcontains "Lib/site-packages") {
        $pth += "Lib/site-packages"
    }
    if ($pth -notcontains "..\..") {
        $pth += "..\.."
    }
    Set-Content -Path $PthFile.FullName -Value $pth -Encoding ASCII
}

$PythonExe = Join-Path $PythonDir "python.exe"
if (!(Test-Path $GetPip)) {
    Invoke-WebRequest -Uri $GetPipUrl -OutFile $GetPip
}
& $PythonExe $GetPip --no-warn-script-location
& $PythonExe -m pip install --upgrade pip --no-warn-script-location
& $PythonExe -m pip install --no-cache-dir --no-warn-script-location -r (Join-Path $OutputPath "requirements.txt")

Write-Step "Copying cloudflared"
$ToolsDir = Join-Path $OutputPath "tools"
New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null
if (Test-Path $CloudflaredPath) {
    Copy-Item -LiteralPath $CloudflaredPath -Destination (Join-Path $ToolsDir "cloudflared.exe") -Force
} else {
    Write-Warning "cloudflared not found: $CloudflaredPath. Public tunnel will be disabled until tools\cloudflared.exe is added."
}

Write-Step "Creating one-click scripts"
@'
@echo off
chcp 65001 >nul
cd /d "%~dp0"
set GALAXY_PORTABLE=1
set GALAXY_DATA_DIR=%~dp0workspace
runtime\python\python.exe portable_launcher.py setup
pause
'@ | Set-Content -Path (Join-Path $OutputPath "setup.bat") -Encoding ASCII

@'
@echo off
chcp 65001 >nul
cd /d "%~dp0"
set GALAXY_PORTABLE=1
set GALAXY_DATA_DIR=%~dp0workspace
runtime\python\python.exe portable_launcher.py start
pause
'@ | Set-Content -Path (Join-Path $OutputPath "start.bat") -Encoding ASCII

@'
@echo off
chcp 65001 >nul
cd /d "%~dp0"
set GALAXY_PORTABLE=1
set GALAXY_DATA_DIR=%~dp0workspace
runtime\python\python.exe portable_launcher.py public
pause
'@ | Set-Content -Path (Join-Path $OutputPath "start_public.bat") -Encoding ASCII

@'
@echo off
chcp 65001 >nul
cd /d "%~dp0"
runtime\python\python.exe portable_launcher.py stop
pause
'@ | Set-Content -Path (Join-Path $OutputPath "stop.bat") -Encoding ASCII

@'
Galaxy New Portable
===================

First run:
  1. Double-click setup.bat and enter the model API key.
  2. Double-click start.bat for local access.
  3. Double-click start_public.bat to start a Cloudflare quick tunnel.

Local URL:
  http://localhost:8502

Public tunnel:
  start_public.bat prints an https://*.trycloudflare.com URL in the console.

Data folders:
  workspace\   agent-created files, uploads, generated outputs
  galaxy.db    local app database
  .keys\       local API-key fallback if Windows Credential Manager is unavailable

Do not share a configured package unless you intentionally want to share its API keys.
'@ | Set-Content -Path (Join-Path $OutputPath "README_PORTABLE.txt") -Encoding ASCII

Write-Step "Smoke checking portable runtime"
Push-Location $OutputPath
try {
    & $PythonExe -c "from config import ensure_runtime_dirs; from data.database import init_db; ensure_runtime_dirs(); init_db(); print('portable smoke ok')"
    if ($LASTEXITCODE -ne 0) {
        throw "portable smoke check failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

if (-not $NoZip) {
    Write-Step "Creating zip"
    $ZipPath = "$OutputPath.zip"
    if (Test-Path $ZipPath) {
        Remove-Item -LiteralPath $ZipPath -Force
    }
    Compress-Archive -Path (Join-Path $OutputPath "*") -DestinationPath $ZipPath -Force
    Write-Host "Zip: $ZipPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "Portable package ready: $OutputPath" -ForegroundColor Green
