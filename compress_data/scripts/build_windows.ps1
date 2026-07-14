$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VirtualPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path -LiteralPath $VirtualPython) { $VirtualPython } else { "python" }
Push-Location $ProjectRoot
try {
    & $Python -m PyInstaller --noconfirm --clean --windowed `
        --name "SpectrumCompressor" `
        --paths "src" `
        --collect-submodules "serial" `
        "run_app.py"
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
