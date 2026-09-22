# Arranca TODO en modo LOCAL (sin servidor UV): app + buscador con qwen2.5:3b en tu GPU.
# Uso:  .\arrancar.ps1
Set-Location $PSScriptRoot
Remove-Item Env:PLENO_OLLAMA_HOST -ErrorAction SilentlyContinue
Remove-Item Env:PLENO_LLM_MODEL -ErrorAction SilentlyContinue
Write-Host "[app] modo LOCAL · http://localhost:8000 ..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe -m app.server
