param([string]$SourceRoot=$env:MINDTRACE_DEEPTUTOR_SOURCE)
$ErrorActionPreference='Stop'
$ProductRoot=Split-Path -Parent $PSScriptRoot
if (-not $SourceRoot) { $SourceRoot=Join-Path (Split-Path -Parent $ProductRoot) '_education_source_research/DeepTutor' }
$SourceRoot=[IO.Path]::GetFullPath($SourceRoot)
$TutorPython=Join-Path $SourceRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $TutorPython)) { throw '教学环境尚未安装，请先运行 scripts/install_deeptutor.ps1。' }
$ActualCommit=(& git -C $SourceRoot rev-parse HEAD).Trim()
if ($ActualCommit -ne '341af371bf8143b2da3569084edf8e6cb46d7404') { throw '教学源码版本与适配器不匹配。' }
$TutorRuntime=Join-Path $ProductRoot '.local_data/deeptutor'
New-Item -ItemType Directory -Force -Path $TutorRuntime | Out-Null
$env:DEEPTUTOR_HOME=$TutorRuntime
$env:MINDTRACE_TUTOR_URL='http://127.0.0.1:8591'
$env:MINDTRACE_TUTOR_WEB_URL='http://127.0.0.1:8592'
$env:NEXT_PUBLIC_API_BASE=$env:MINDTRACE_TUTOR_URL
$env:BACKEND_URL=$env:MINDTRACE_TUTOR_URL
$env:PORT='8592'
function Get-TutorHealth {
    try { return (Invoke-RestMethod -Uri 'http://127.0.0.1:8591/api/mindtrace/health' -TimeoutSec 2).engine -eq 'official-deeptutor' }
    catch { return $false }
}
if (-not (Get-TutorHealth)) {
    $Launcher='"'+(Join-Path $ProductRoot 'scripts/run_deeptutor.py')+'"'
    $Service=Start-Process -FilePath $TutorPython -ArgumentList '-u',$Launcher -WorkingDirectory $ProductRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $TutorRuntime 'api.log') -RedirectStandardError (Join-Path $TutorRuntime 'api-error.log')
    $Service.Id | Set-Content -LiteralPath (Join-Path $TutorRuntime 'api.pid')
    $Ready=$false
    for ($Attempt=0;$Attempt -lt 45;$Attempt++) {
        if (Get-TutorHealth) { $Ready=$true; break }
        if ($Service.HasExited) { throw '教学服务启动失败，详情见 .local_data/deeptutor/api-error.log。' }
        Start-Sleep -Milliseconds 1000
    }
    if (-not $Ready) { throw '教学服务尚未就绪，请查看本地运行日志。' }
}
& $TutorPython (Join-Path $ProductRoot 'scripts/prepare_deeptutor_web.py') $SourceRoot
if ($LASTEXITCODE -ne 0) { throw '教学界面适配失败。' }
$WebReady=$false
try { $WebReady=(Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8592/mindtrace' -TimeoutSec 3).StatusCode -eq 200 } catch {}
if (-not $WebReady) {
    $Node=(Get-Command node -ErrorAction Stop).Source
    $Web=Start-Process -FilePath $Node -ArgumentList 'scripts/dev.mjs','--hostname','127.0.0.1' -WorkingDirectory (Join-Path $SourceRoot 'web') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $TutorRuntime 'web.log') -RedirectStandardError (Join-Path $TutorRuntime 'web-error.log')
    $Web.Id | Set-Content -LiteralPath (Join-Path $TutorRuntime 'web.pid')
}
Write-Host '教学服务已连接；学生端将进入循理学习空间。'
