# Arranca TODO en modo SERVIDOR UV (GPU 16 GB): túnel SSH + app + buscador con qwen2.5:14b.
# Requiere la clave SSH ya instalada (ssh uv entra sin contraseña). Uso:  .\arrancar_uv.ps1
Set-Location $PSScriptRoot

# 1) túnel al Ollama de la UV (si no está ya): localhost:11435 -> servidor:11434
$tunnelUp = Test-NetConnection -ComputerName localhost -Port 11435 -InformationLevel Quiet -WarningAction SilentlyContinue
if (-not $tunnelUp) {
    Start-Process ssh -ArgumentList "-N","-L","11435:localhost:11434","uv" -WindowStyle Hidden
    Write-Host "[tunel] abriendo tunel SSH a la UV..." -ForegroundColor Yellow
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        if (Test-NetConnection -ComputerName localhost -Port 11435 -InformationLevel Quiet -WarningAction SilentlyContinue) { break }
        Start-Sleep -Milliseconds 800
    }
}
$tunnelUp = Test-NetConnection -ComputerName localhost -Port 11435 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($tunnelUp) {
    Write-Host "[tunel] OK: GPU de la UV disponible en localhost:11435" -ForegroundColor Green
    $env:PLENO_OLLAMA_HOST = 'http://localhost:11435'
    $env:PLENO_LLM_MODEL   = 'qwen2.5:14b'
} else {
    Write-Host "[tunel] NO conecta (¿fuera de la red UV sin VPN?). Sigo en modo LOCAL." -ForegroundColor Red
    Remove-Item Env:PLENO_OLLAMA_HOST -ErrorAction SilentlyContinue
    Remove-Item Env:PLENO_LLM_MODEL -ErrorAction SilentlyContinue
}

# 2) app (levanta también el buscador :8100; hereda las variables)
Write-Host "[app] arrancando en http://localhost:8000 ..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe -m app.server
