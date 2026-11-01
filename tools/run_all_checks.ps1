# 跑一遍全部检查，串行、每条都存日志。
#
# 为什么是脚本而不是记在脑子里：
#   2026-11-01 同一个错误犯了三次 —— 手工跑检查时用管道截断输出，
#   把失败细节扔掉，于是只能记成"偶发"而无法修。
#   串行 + 存盘必须由工具保证，不能靠当时的我记着。
#
# 用法：
#   pwsh -File tools/run_all_checks.ps1
#   pwsh -File tools/run_all_checks.ps1 -SkipGo
#   pwsh -File tools/run_all_checks.ps1 -SkipPython
#
# 日志写到 reports\checks-<时间戳>\ 下，一个检查一个文件。

param(
    [switch]$SkipPython,
    [switch]$SkipGo,
    [switch]$SkipAudits
)

$ErrorActionPreference = 'Stop'
# The script normally lives in <repo>/tools/, but it may be copied elsewhere for
# testing. Only trust the derived path if it actually looks like this repository.
$candidate = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$repo = if ((Test-Path (Join-Path $candidate 'runtime')) -and
            (Test-Path (Join-Path $candidate 'easycirq'))) {
    $candidate
} else {
    (Get-Location).Path
}
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logDir = Join-Path $repo "reports\checks-$stamp"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$results = @()
$env:PYTHONIOENCODING = 'utf-8'

function Invoke-Check {
    param([string]$Name, [string]$Command, [string]$WorkDir = $repo)

    $log = Join-Path $logDir "$Name.log"
    Push-Location $WorkDir
    try {
        # 先落盘，再判断：输出一旦被管道截断，失败就没法查了。
        & pwsh -NoProfile -Command $Command 2>&1 | Tee-Object -FilePath $log | Out-Null
        $code = $LASTEXITCODE
        # A check that prints nothing (a clean go vet) would leave no file behind.
        if (-not (Test-Path $log)) { New-Item -ItemType File -Path $log | Out-Null }
    } finally {
        Pop-Location
    }

    $tail = (Get-Content $log -Tail 2) -join ' | '
    $script:results += [PSCustomObject]@{
        Check  = $Name
        Exit   = $code
        Detail = if ($tail.Length -gt 90) { $tail.Substring(0, 90) } else { $tail }
        Log    = $log
    }
    return $code
}

if (-not $SkipPython) {
    Invoke-Check 'pytest' 'python -m pytest tests -q' | Out-Null
}
if (-not $SkipGo) {
    $rt = Join-Path $repo 'runtime'
    Invoke-Check 'go-vet' 'go vet ./...' $rt | Out-Null
    Invoke-Check 'go-test' 'go test ./... -count=1 -vet=off' $rt | Out-Null
}
if (-not $SkipAudits) {
    foreach ($tool in 'check_release_consistency', 'check_deliverable', 'check_handoff', 'check_published') {
        Invoke-Check $tool "python tools/$tool.py" | Out-Null
    }
    $selftest = Join-Path $env:USERPROFILE '.agents\skills\easycirq\scripts\skill_selftest.py'
    if (Test-Path $selftest) {
        Invoke-Check 'skill-selftest' "python `"$selftest`"" | Out-Null
    }
}

Write-Host ''
$results | Format-Table -AutoSize

$failed = $results | Where-Object { $_.Exit -ne 0 }
Write-Host "logs: $logDir"
if ($failed) {
    Write-Host ''
    Write-Host "FAILED ($($failed.Count)):" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host ("  {0} (exit {1}) -> {2}" -f $_.Check, $_.Exit, $_.Log) -ForegroundColor Red }
    Write-Host ''
    Write-Host '失败日志已保存。先读日志再动手，不要重跑一次就当它好了。'
    exit 1
}

Write-Host '全部检查通过。' -ForegroundColor Green
exit 0
