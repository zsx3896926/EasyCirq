# 跑一遍全部检查，串行、每条都存日志。
#
# 为什么是脚本而不是记在脑子里：
#   2026-11-01 同一个错误犯了三次 —— 手工跑检查时用管道截断输出，
#   把失败细节扔掉，于是只能记成"偶发"而无法修。
#   串行 + 存盘必须由工具保证，不能靠当时的我记着。
#
# 为什么不再用 `pwsh -Command` 包一层：
#   第一版把每条检查交给嵌套 pwsh 执行，结果 pytest 跑到 73% 被杀，
#   脚本却报成"失败"。多一层进程就多一个没人监控的生命周期。
#   现在直接在当前进程里跑 scriptblock。
#
# 为什么区分"失败"和"没跑完"：
#   被杀掉和被判失败是两件事。前者说明环境或超时，后者说明代码。
#   混在一起会让人去修没问题的代码。
#
# 用法：
#   pwsh -File tools/run_all_checks.ps1
#   pwsh -File tools/run_all_checks.ps1 -SkipGo
#   pwsh -File tools/run_all_checks.ps1 -SkipPython
#   pwsh -File tools/run_all_checks.ps1 -SkipAudits
#
# 日志写到 reports\checks-<时间戳>\ 下，一个检查一个文件。

param(
    [switch]$SkipPython,
    [switch]$SkipGo,
    [switch]$SkipAudits
)

$ErrorActionPreference = 'Stop'

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
    param(
        [string]$Name,
        [scriptblock]$Body,
        [string]$WorkDir = $repo,
        # 日志里必须出现的标记；没有它 = 没跑完，而不是失败
        [string]$Expect = ''
    )

    $log = Join-Path $logDir "$Name.log"
    $started = Get-Date
    Push-Location $WorkDir
    try {
        $output = & $Body 2>&1
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    $elapsed = (Get-Date) - $started

    $text = ($output | Out-String)
    $text | Out-File -FilePath $log -Encoding UTF8

    $finished = $true
    if ($Expect) {
        $finished = $text -match $Expect
    }

    $status = if (-not $finished) { 'INCOMPLETE' }
              elseif ($code -ne 0) { 'FAILED' }
              else { 'ok' }

    $tail = ($text.Trim() -split "`n" | Select-Object -Last 1)
    if ($tail.Length -gt 80) { $tail = $tail.Substring(0, 80) }

    $script:results += [PSCustomObject]@{
        Check   = $Name
        Status  = $status
        Exit    = $code
        Seconds = [math]::Round($elapsed.TotalSeconds, 1)
        Detail  = $tail
        Log     = $log
    }
}

if (-not $SkipPython) {
    Invoke-Check 'pytest' { python -m pytest tests -q } -Expect '\d+ (passed|failed)'
}
if (-not $SkipGo) {
    $rt = Join-Path $repo 'runtime'
    Invoke-Check 'go-vet' { go vet ./... } $rt
    Invoke-Check 'go-test' { go test ./... -count=1 -vet=off } $rt -Expect '(?m)^(ok|FAIL)'
}
if (-not $SkipAudits) {
    foreach ($tool in 'check_release_consistency', 'check_deliverable', 'check_handoff', 'check_published') {
        $name = $tool
        Invoke-Check $name { python "tools/$name.py" } -Expect '\S'
    }
    $selftest = Join-Path $env:USERPROFILE '.agents\skills\easycirq\scripts\skill_selftest.py'
    if (Test-Path $selftest) {
        Invoke-Check 'skill-selftest' { python $selftest } -Expect 'PASS'
    }
}

Write-Host ''
$results | Format-Table -AutoSize

Write-Host "logs: $logDir"
$bad = $results | Where-Object { $_.Status -ne 'ok' }
if ($bad) {
    Write-Host ''
    foreach ($item in $bad) {
        $colour = if ($item.Status -eq 'INCOMPLETE') { 'Yellow' } else { 'Red' }
        Write-Host ("{0}: {1} (exit {2}) -> {3}" -f $item.Status, $item.Check, $item.Exit, $item.Log) -ForegroundColor $colour
    }
    Write-Host ''
    if ($bad.Status -contains 'INCOMPLETE') {
        Write-Host 'INCOMPLETE 表示它没跑完（被杀或超时），不是代码失败——先看日志末尾停在哪一步。'
    }
    Write-Host '失败日志已保存。先读日志再动手，不要重跑一次就当它好了。'
    exit 1
}

Write-Host '全部检查通过。' -ForegroundColor Green
exit 0
