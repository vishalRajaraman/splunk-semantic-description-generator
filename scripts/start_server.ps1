$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
& ".\.venv\Scripts\python.exe" "src\server.py" > "output\server.log" 2>&1
