param([string]$SourceRoot=$env:MINDTRACE_DEEPTUTOR_SOURCE)
$ErrorActionPreference='Stop'
$ProductRoot=Split-Path -Parent $PSScriptRoot
if (-not $SourceRoot) { $SourceRoot=Join-Path (Split-Path -Parent $ProductRoot) '_education_source_research/DeepTutor' }
$SourceRoot=[IO.Path]::GetFullPath($SourceRoot)
$Commit='341af371bf8143b2da3569084edf8e6cb46d7404'
function Invoke-Checked {
    param([string]$Program,[string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('安装步骤失败：'+$Program) }
}
if (-not (Test-Path -LiteralPath $SourceRoot)) {
    Invoke-Checked git @('clone','https://github.com/HKUDS/DeepTutor.git',$SourceRoot)
    Invoke-Checked git @('-C',$SourceRoot,'checkout','--detach',$Commit)
}
$ActualCommit=(& git -C $SourceRoot rev-parse HEAD).Trim()
if ($ActualCommit -ne $Commit) { throw '已有研究目录版本不匹配；请使用独立空目录安装，避免覆盖已有研究。' }
$TutorPython=Join-Path $SourceRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $TutorPython)) {
    Invoke-Checked (Join-Path $ProductRoot '.venv/Scripts/python.exe') @('-m','venv',(Join-Path $SourceRoot '.venv'))
}
Invoke-Checked $TutorPython @('-m','pip','install','-r',(Join-Path $ProductRoot 'integrations/deeptutor/requirements.lock.txt'))
Invoke-Checked $TutorPython @('-m','pip','install','-e',$SourceRoot,'--no-deps')
Invoke-Checked $TutorPython @('-m','pip','install','-e',(Join-Path $ProductRoot 'integrations/deeptutor/plugin'),'--no-deps')
Invoke-Checked $TutorPython @((Join-Path $ProductRoot 'scripts/prepare_deeptutor_web.py'),$SourceRoot)
Push-Location (Join-Path $SourceRoot 'web')
try { Invoke-Checked npm @('ci','--legacy-peer-deps','--no-audit','--no-fund') } finally { Pop-Location }
Write-Host '独立教学环境安装完成。现有教师端运行环境未被替换。'
