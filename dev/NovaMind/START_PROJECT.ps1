# ==============================================================================
#  NovaMind - Project Launcher
#  Run this script from D:\pfe2026\NovaMind\ to start all services.
#
#  SERVICES STARTED:
#    1. Qdrant Vector Database  (Docker, port 6333)
#    2. Django Backend API      (port 8000)
#    3. React Frontend          (Vite dev server, port 5173)
#
#  USAGE:
#    Right-click > "Run with PowerShell"
#    OR in a terminal: .\START_PROJECT.ps1
# ==============================================================================

$ErrorActionPreference = "Stop"

# ── Paths ─────────────────────────────────────────────────────────────────────
$ROOT         = "D:\pfe2026\NovaMind"
$BACKEND_DIR  = "$ROOT\backend"
$FRONTEND_DIR = "$ROOT\app"
$VENV_PYTHON  = "$BACKEND_DIR\venv\Scripts\python.exe"
$VENV_PIP     = "$BACKEND_DIR\venv\Scripts\pip.exe"

# ── Colors ────────────────────────────────────────────────────────────────────
function Write-Header($msg) { Write-Host "`n$('='*70)" -ForegroundColor Cyan; Write-Host "  $msg" -ForegroundColor Cyan; Write-Host "$('='*70)" -ForegroundColor Cyan }
function Write-Step($msg)   { Write-Host "`n>> $msg" -ForegroundColor Yellow }
function Write-OK($msg)     { Write-Host "   [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg)   { Write-Host "   [WARN] $msg" -ForegroundColor Magenta }
function Write-Fail($msg)   { Write-Host "   [FAIL] $msg" -ForegroundColor Red }

Write-Header "NovaMind Project Launcher"

# ==============================================================================
# STEP 1 — Qdrant Vector Database (Docker)
# ==============================================================================
Write-Step "Starting Qdrant vector database..."

$qdrantContainer = docker ps -q --filter "ancestor=qdrant/qdrant" 2>$null
if ($qdrantContainer) {
    Write-OK "Qdrant is already running (container: $qdrantContainer)"
} else {
    # Try to restart stopped container first
    $stoppedContainer = docker ps -aq --filter "ancestor=qdrant/qdrant" 2>$null
    if ($stoppedContainer) {
        Write-Host "   Restarting existing Qdrant container..." -ForegroundColor Gray
        docker start $stoppedContainer | Out-Null
        Write-OK "Qdrant container restarted (ID: $stoppedContainer)"
    } else {
        # Fresh container with persistent storage
        Write-Host "   Creating new Qdrant container..." -ForegroundColor Gray
        docker run -d `
            --name novamind-qdrant `
            -p 6333:6333 `
            -v "D:\pfe2026\qdrant_db_hybrid:/qdrant/storage" `
            qdrant/qdrant | Out-Null
        Write-OK "Qdrant container created and started"
    }

    # Wait for Qdrant to be ready
    Write-Host "   Waiting for Qdrant to be ready..." -ForegroundColor Gray
    $retries = 0
    do {
        Start-Sleep -Seconds 2
        $retries++
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:6333/readyz" -TimeoutSec 2 -ErrorAction SilentlyContinue
            $ready = $response.StatusCode -eq 200
        } catch { $ready = $false }
    } while (-not $ready -and $retries -lt 10)

    if ($ready) {
        Write-OK "Qdrant is ready on http://localhost:6333"
    } else {
        Write-Warn "Qdrant may still be starting - continuing anyway"
    }
}

# ==============================================================================
# STEP 2 — Django Backend (port 8000)
# ==============================================================================
Write-Step "Starting Django backend (port 8000)..."

if (-not (Test-Path $VENV_PYTHON)) {
    Write-Fail "Python venv not found at $VENV_PYTHON"
    Write-Host "   Run: python -m venv $BACKEND_DIR\venv" -ForegroundColor Gray
    exit 1
}

# Launch Django in a new terminal window
$djangoArgs = "-NoExit -Command `"cd '$BACKEND_DIR'; & '$VENV_PYTHON' manage.py runserver 0.0.0.0:8000`""
Start-Process powershell -ArgumentList $djangoArgs -WindowStyle Normal
Write-OK "Django backend launched -> http://localhost:8000"
Write-Host "   API docs  -> http://localhost:8000/admin/" -ForegroundColor Gray

# ==============================================================================
# STEP 3 — React Frontend (Vite, port 5173)
# ==============================================================================
Write-Step "Starting React frontend (Vite, port 5173)..."

if (-not (Test-Path "$FRONTEND_DIR\node_modules")) {
    Write-Warn "node_modules not found. Installing dependencies..."
    $installArgs = "-NoExit -Command `"cd '$FRONTEND_DIR'; pnpm install`""
    Start-Process powershell -ArgumentList $installArgs -WindowStyle Normal
    Write-OK "Dependency installation started in new window"
} else {
    $frontendArgs = "-NoExit -Command `"cd '$FRONTEND_DIR'; pnpm run dev`""
    Start-Process powershell -ArgumentList $frontendArgs -WindowStyle Normal
    Write-OK "Frontend launched -> http://localhost:5173"
}

# ==============================================================================
# SUMMARY
# ==============================================================================
Write-Header "All Services Launched"

Write-Host @"

  Service        URL                       Status
  -----------------------------------------------------
  Qdrant DB      http://localhost:6333      Running
  Django API     http://localhost:8000      Starting...
  React App      http://localhost:5173      Starting...

  Qdrant Dashboard -> http://localhost:6333/dashboard
  Django Admin     -> http://localhost:8000/admin/

  NOTE: The first API call will be slow (loading BGE-M3 + Qwen LLM ~20s).
  Press Ctrl+C in each terminal window to stop a service.

"@ -ForegroundColor White

# Keep this window open
Read-Host "Press Enter to close this launcher"
