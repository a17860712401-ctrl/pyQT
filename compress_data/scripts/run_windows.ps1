$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VirtualPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path -LiteralPath $VirtualPython) { $VirtualPython } else { "python" }
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
& $Python -m spectrum_compressor.main
exit $LASTEXITCODE
