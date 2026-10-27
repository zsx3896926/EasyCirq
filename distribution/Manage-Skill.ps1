param(
    [ValidateSet('menu','install','check','update','status','repair','rollback','recover','discover','update-agent')]
    [string]$Action = 'menu',
    [ValidateSet('claude','codex','workbuddy')][string]$Client,
    [string]$Package,
    [string]$Manifest,
    [string]$HomeDirectory,
    [switch]$Adopt,
    [switch]$Idle,
    [string]$Easyeda,
    [string]$AgentVersion
)
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$python = $null
$prefix = @()
foreach ($candidate in @('py','python3','python')) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($command) {
        $probe = @('-c','import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)')
        $candidatePrefix = @()
        if ($candidate -eq 'py') { $candidatePrefix = @('-3') }
        try { & $command.Source @candidatePrefix @probe 2>$null }
        catch { continue }
        if ($LASTEXITCODE -eq 0) { $python = $command.Source; $prefix = $candidatePrefix; break }
    }
}
if (-not $python) { throw 'Python 3.10+ is required. Install from https://www.python.org/downloads/ and reopen this window.' }
$manager = Join-Path $PSScriptRoot 'skill_update.py'
if (-not (Test-Path -LiteralPath $manager)) {
    $manager = Join-Path $PSScriptRoot '../design-hardware/scripts/skill_update.py'
}
if ($Action -eq 'menu') {
    Write-Host '硬件设计 Skill - 安装与更新'
    Write-Host '1 安装 / 2 检查更新 / 3 升级 / 4 查看安装 / 5 回退 / 6 修复安装 / 7 恢复中断 / 8 升级EDA执行器'
    $actions = @{'1'='install';'2'='check';'3'='update';'4'='status';'5'='rollback';'6'='repair';'7'='recover';'8'='update-agent'}
    $Action = $actions[(Read-Host '输入操作编号')]
    if (-not $Action) { throw '无效操作编号' }
    $clients = @{'1'='claude';'2'='codex';'3'='workbuddy'}
    Write-Host '1 Claude Code / 2 Codex / 3 WorkBuddy'
    $Client = $clients[(Read-Host '输入客户端编号')]
    if (-not $Client) { throw '无效客户端编号' }
    if ($Action -in @('install','update','repair','update-agent')) {
        Write-Host '请先结束当前画板任务。旧安装会备份；升级后需要新会话或重新加载。'
        if ($Action -eq 'repair') { Write-Host '修复会恢复发布版文件；本地修改保存在整目录备份中。' }
        if ((Read-Host '确认现在执行？输入 YES') -cne 'YES') { exit 0 }
    }
    if ($Action -eq 'update-agent') { $Idle = $true }
    if ($Action -eq 'install') {
        if ((Read-Host '若已有手动复制的旧版本，是否整目录备份后迁移？输入 YES，否则回车') -ceq 'YES') { $Adopt = $true }
    }
    if ($Action -in @('install','repair')) {
        $localManifest = Join-Path $PSScriptRoot 'release.json'
        if (Test-Path -LiteralPath $localManifest) {
            $release = Get-Content -LiteralPath $localManifest -Raw -Encoding UTF8 | ConvertFrom-Json
            $Package = Join-Path $PSScriptRoot $release.archive
            $Manifest = $localManifest
        }
    }
}
$argsList = @($manager, $Action)
if ($Client) { $argsList += @('--client',$Client) }
if ($HomeDirectory) { $argsList += @('--home',$HomeDirectory) }
if ($Package) { $argsList += @('--package',$Package) }
if ($Manifest) { $argsList += @('--manifest',$Manifest) }
if ($Adopt) { $argsList += '--adopt' }
if ($Idle) { $argsList += '--idle' }
if ($Easyeda) { $argsList += @('--easyeda',$Easyeda) }
if ($AgentVersion) { $argsList += @('--agent-version',$AgentVersion) }
& $python @prefix @argsList
$code = $LASTEXITCODE
if ($code -eq 0 -and $Action -in @('install','update','repair','rollback')) {
    Write-Host '文件操作完成。请重新加载 Skill 或开启新会话；本窗口无法证明客户端已经加载新版。'
}
exit $code
