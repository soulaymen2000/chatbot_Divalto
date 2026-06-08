# ==============================================================================
#  NovaMind — Stop All Services
#  Stops Qdrant Docker container and any running Django/Vite processes.
# ==============================================================================

function Write-Step($msg) { Write-Host "`n>> $msg" -ForegroundColor Yellow }
function Write-OK($msg)   { Write-Host "   [OK] $msg" -ForegroundColor Green }

Write-Host "`n$('='*70)" -ForegroundColor Red
Write-Host "  NovaMind — Stopping All Services" -ForegroundColor Red
Write-Host "$('='*70)`n" -ForegroundColor Red

# Stop Qdrant container
Write-Step "Stopping Qdrant container..."
$qdrantContainer = docker ps -q --filter "ancestor=qdrant/qdrant" 2>$null
if ($qdrantContainer) {
    docker stop $qdrantContainer | Out-Null
    Write-OK "Qdrant stopped"
} else {
    Write-Host "   Qdrant was not running" -ForegroundColor Gray
}

# Kill Django
Write-Step "Stopping Django backend (port 8000)..."
$djangoProc = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -ErrorAction SilentlyContinue
if ($djangoProc) {
    Stop-Process -Id $djangoProc -Force -ErrorAction SilentlyContinue
    Write-OK "Django process stopped (PID $djangoProc)"
} else {
    Write-Host "   Django was not running on port 8000" -ForegroundColor Gray
}

# Kill Vite
Write-Step "Stopping Vite frontend (port 5173)..."
$viteProc = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -ErrorAction SilentlyContinue
if ($viteProc) {
    Stop-Process -Id $viteProc -Force -ErrorAction SilentlyContinue
    Write-OK "Vite process stopped (PID $viteProc)"
} else {
    Write-Host "   Vite was not running on port 5173" -ForegroundColor Gray
}

Write-Host "`n  All services stopped.`n" -ForegroundColor Green
Read-Host "Press Enter to close"
