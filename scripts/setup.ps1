# ============================================================
# Setup del Buscador Plenario Inteligente
# Windows · Python 3.12 · RTX 3050 (CUDA 12.x)
# Ejecutar desde la carpeta R2:   .\scripts\setup.ps1
# ============================================================
$ErrorActionPreference = "Stop"

# 1. ffmpeg (extrae y convierte el audio)
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "==> Instalando ffmpeg con winget..." -ForegroundColor Cyan
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    Write-Host "   (reinicia la terminal si ffmpeg no aparece en el PATH)" -ForegroundColor Yellow
} else {
    Write-Host "==> ffmpeg ya instalado." -ForegroundColor Green
}

# 2. Entorno virtual con Python 3.12
if (-not (Test-Path ".venv")) {
    Write-Host "==> Creando entorno virtual .venv (Python 3.12)..." -ForegroundColor Cyan
    py -3.12 -m venv .venv
}
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

# 3. PyTorch con CUDA 12.1 (RTX 3050, compute 8.6)
Write-Host "==> Instalando PyTorch CUDA 12.1 (~2.5 GB)..." -ForegroundColor Cyan
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 4. Resto de dependencias
Write-Host "==> Instalando dependencias del proyecto..." -ForegroundColor Cyan
pip install -r requirements.txt

# 5. Verificación
Write-Host "`n==> Comprobando CUDA..." -ForegroundColor Cyan
python -c "import torch; print('CUDA:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
Write-Host "`nListo. Activa el entorno con:  .\.venv\Scripts\Activate.ps1" -ForegroundColor Green
