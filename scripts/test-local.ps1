$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "[1/2] compile baseline/*.py"
@'
from pathlib import Path
import py_compile

for path in sorted(Path("baseline").glob("*.py")):
    py_compile.compile(str(path), doraise=True)
print("compiled baseline python files")
'@ | python -

Write-Host "[2/2] pytest"
python -m pytest -q
