param([int]$Port=8561,[switch]$BackendOnly,[switch]$LegacyTutor)
$ErrorActionPreference='Stop'
$ProjectRoot=Split-Path -Parent $PSScriptRoot
$RuntimeRoot=Join-Path $ProjectRoot '.local_data/development'
New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
$Python=Join-Path $ProjectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $Python)) { throw '请先安装项目运行环境。' }
$env:MINDTRACE_DATA_DIR=$RuntimeRoot
$env:MINDTRACE_CLASSROOM_DIR=Join-Path $RuntimeRoot 'classrooms'
$env:MINDTRACE_DATABASE=Join-Path $RuntimeRoot 'mindtrace.db'
$env:MINDTRACE_ENV='development'
$env:MINDTRACE_SHARED_MODE='0'
$env:MINDTRACE_BACKGROUND='1'
$env:MINDTRACE_HEADLESS='1'
if (-not $BackendOnly -and -not $LegacyTutor) { . (Join-Path $PSScriptRoot 'start_deeptutor.ps1') }
$WorkerLog=Join-Path $RuntimeRoot 'worker.log'
$WorkerError=Join-Path $RuntimeRoot 'worker-error.log'
$Worker=Start-Process -FilePath $Python -ArgumentList '-u','scripts/run_worker.py' -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $WorkerLog -RedirectStandardError $WorkerError
$Worker.Id | Set-Content -LiteralPath (Join-Path $RuntimeRoot 'worker.pid')
if ($BackendOnly) {
    & $Python -m uvicorn api.app:app --host 127.0.0.1 --port 8570
} else {
    Remove-Item Env:MINDTRACE_BACKEND_URL -ErrorAction SilentlyContinue
    $env:MINDTRACE_HEADLESS='0'
    & $Python -m streamlit run app.py --server.address 127.0.0.1 --server.port $Port --browser.gatherUsageStats false
}
