$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Src = Join-Path $Root "source"
$Dist = Join-Path $Root "dist-windows"
$Venv = Join-Path $Root ".build-venv-windows"
$Version = "v26.08.15.05"
$Python = (Get-Command python -ErrorAction Stop).Source

Write-Host "HV P2P SRVR $Version - Windows Qt/QML build"
& $Python --version

if (Test-Path $Dist) { Remove-Item $Dist -Recurse -Force }
if (Test-Path $Venv) { Remove-Item $Venv -Recurse -Force }
& $Python -m venv $Venv
& "$Venv\Scripts\python.exe" -m pip install --upgrade pip
& "$Venv\Scripts\python.exe" -m pip install -r "$Src\requirements.txt"

# Compile-check Python only. Do not run pyside6-project qmllint; this project
# exposes the Python bridge with QQmlContext.setContextProperty rather than
# registering Python classes as QML types.
& "$Venv\Scripts\python.exe" -m py_compile `
    "$Src\main.py" `
    "$Src\bridge.py" `
    "$Src\backend_worker.py" `
    "$Src\hv_p2p_legacy_core.py"

Push-Location $Src
try {
    if (Test-Path "pysidedeploy.spec") { Remove-Item "pysidedeploy.spec" -Force }
    & "$Venv\Scripts\pyside6-deploy.exe" main.py --force --name "HV P2P SRVR"
} finally { Pop-Location }

$Exe = Get-ChildItem $Src -Filter "HV P2P SRVR.exe" -Recurse | Select-Object -First 1
if (-not $Exe) {
    $Exe = Get-ChildItem $Src -Filter "*.exe" -Recurse |
        Where-Object { $_.Name -notmatch "python|nuitka" } |
        Select-Object -First 1
}
if (-not $Exe) { throw "Build completed but no application .exe was found." }

New-Item -ItemType Directory -Force -Path $Dist | Out-Null
Copy-Item $Exe.FullName (Join-Path $Dist "HV P2P SRVR $Version.exe") -Force
Write-Host "Built: $Dist\HV P2P SRVR $Version.exe"
