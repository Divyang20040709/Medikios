# MediKiosk - Speech Environment Setup Script
# Sets up dedicated isolated Python virtual environment for IndicConformer inference (.venv_speech)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "=== MediKiosk Speech Inference Setup ===" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"

# 1. Check Python
$PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonExe) {
    Write-Error "Python 3 is required but not found in PATH."
    exit 1
}
Write-Host "Found Python at: $PythonExe"

# 2. Create .venv_speech if not exists
$VenvDir = Join-Path $ProjectRoot ".venv_speech"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtual environment at $VenvDir..." -ForegroundColor Yellow
    python -m venv $VenvDir
} else {
    Write-Host "Virtual environment already exists at $VenvDir." -ForegroundColor Green
}

# 3. Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
& $VenvPython -m pip install --upgrade pip

# 4. Install PyTorch with CUDA 12.6
Write-Host "Installing PyTorch + torchaudio (CUDA 12.6)..." -ForegroundColor Yellow
& $VenvPython -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126

# 5. Install audio processing and model dependencies
Write-Host "Installing audio libraries & model dependencies..." -ForegroundColor Yellow
& $VenvPython -m pip install soundfile librosa sentencepiece pyyaml transformers onnxruntime-gpu huggingface_hub

# 6. Verify PyTorch & CUDA
Write-Host "Verifying PyTorch CUDA installation..." -ForegroundColor Yellow
& $VenvPython -c "import torch; print(f'PyTorch {torch.__version__}, CUDA available: {torch.cuda.is_available()}'); print(f'Device count: {torch.cuda.device_count()}') if torch.cuda.is_available() else None"

Write-Host "=== Speech Environment Setup Complete ===" -ForegroundColor Green
