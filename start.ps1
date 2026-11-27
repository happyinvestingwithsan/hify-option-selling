<#
.SYNOPSIS
    HIFY Option Selling System — Local & Tailscale Launcher
.DESCRIPTION
    Starts the FastAPI backend (0.0.0.0:8000) and Next.js frontend (0.0.0.0:3011)
    in separate PowerShell windows and prints Desktop + Mobile Tailscale URLs.
.PARAMETER Production
    Run Next.js in production mode (npm run build && npm run start) instead of dev mode.
#>
param(
    [switch]$Production
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $RootDir "backend"
$FrontendDir = Join-Path $RootDir "frontend"
$UvicornExe = Join-Path $BackendDir ".venv\Scripts\uvicorn.exe"
$NodeModules = Join-Path $FrontendDir "node_modules"

if (-not (Test-Path $UvicornExe)) {
    Write-Error "Missing backend virtualenv uvicorn at: $UvicornExe`nRun: python -m venv backend\.venv && backend\.venv\Scripts\pip install -r backend\requirements.txt"
    exit 1
}

if (-not (Test-Path $NodeModules)) {
    Write-Error "Missing frontend dependencies at: $NodeModules`nRun: cd frontend && npm install"
    exit 1
}

# Detect Tailscale IPv4 with graceful fallback
$TailscaleIp = $null
$TailscaleCmd = Get-Command tailscale -ErrorAction SilentlyContinue
if ($TailscaleCmd) {
    try {
        $ipOutput = & tailscale ip -4 2>$null
        if ($LASTEXITCODE -eq 0 -and $ipOutput) {
            $TailscaleIp = ($ipOutput | Select-Object -First 1).Trim()
        }
    } catch {
        $TailscaleIp = $null
    }
}

if ($Production) {
    Write-Host "[HIFY] Building frontend for Production mode..." -ForegroundColor Yellow
    Push-Location $FrontendDir
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend production build failed."
        }
    } finally {
        Pop-Location
    }

    $BackendCmd = "Set-Location '$BackendDir'; & '$UvicornExe' app.main:app --host 0.0.0.0 --port 8000"
    $FrontendCmd = "Set-Location '$FrontendDir'; npm run start -- -H 0.0.0.0 -p 3011"
    $ModeLabel = "PRODUCTION"
} else {
    $BackendCmd = "Set-Location '$BackendDir'; & '$UvicornExe' app.main:app --host 0.0.0.0 --port 8000 --reload"
    $FrontendCmd = "Set-Location '$FrontendDir'; npm run dev -- -H 0.0.0.0 -p 3011"
    $ModeLabel = "DEVELOPMENT"
}

Write-Host ""
Write-Host "=====================================================" -ForegroundColor DarkYellow
Write-Host "  HIFY Option Selling System ($ModeLabel)" -ForegroundColor Yellow
Write-Host "=====================================================" -ForegroundColor DarkYellow

Start-Process powershell -ArgumentList "-NoExit", "-Command", $BackendCmd -WorkingDirectory $BackendDir
Start-Process powershell -ArgumentList "-NoExit", "-Command", $FrontendCmd -WorkingDirectory $FrontendDir

Write-Host "  Desktop Frontend : http://localhost:3011" -ForegroundColor Green
Write-Host "  Desktop Backend  : http://localhost:8000/docs" -ForegroundColor Green

if ($TailscaleIp) {
    Write-Host "  Mobile Tailscale : http://${TailscaleIp}:3011" -ForegroundColor Cyan
    Write-Host "  Tailscale API    : http://${TailscaleIp}:8000/health" -ForegroundColor Cyan
} else {
    Write-Host "  Mobile Tailscale : tailscale CLI not detected or offline (check Tailscale app for 100.x.x.x IP)" -ForegroundColor DarkGray
}

Write-Host "=====================================================" -ForegroundColor DarkYellow
Write-Host ""
