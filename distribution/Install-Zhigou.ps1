param(
    [ValidateSet('menu', 'install', 'upgrade', 'rollback', 'uninstall', 'status', 'verify', 'inspect-bundle', 'recover')]
    [string]$Action = 'menu',
    [string]$Bundle,
    [string]$Release,
    [string]$InstallDir,
    [string]$StateDir,
    [string]$HomeDirectory,
    [ValidateSet('none', 'claude', 'codex', 'agents')]
    [string]$SkillClient = 'none',
    [string]$SkillRoot,
    [switch]$Force,
    [switch]$Adopt,
    [switch]$NoSelfCheck,
    [switch]$DryRun,
    [switch]$PurgeState,
    [string]$To,
    [string]$Backup,
    [switch]$Yes
)
<#
.SYNOPSIS
  Zhigou 工具链统一安装器（Skill + 运行时 + 连接器）。

.DESCRIPTION
  入口包装：只负责参数校验、中文/空格路径传递与调用 distribution/zhigou_install.py。
  它不做任何文件写入本身——所有事务（锁、备份、回滚、清单校验）由 Python 实现。

  安全边界：
    * 不写入用户既有的 easyeda-agent 目录；
    * 不修改 PATH；
    * 不把连接器自动导入 EasyEDA（只打印导入步骤）；
    * 卸载只删除 installation.json 记录的本工具链文件。

.EXAMPLE
  .\Install-Zhigou.ps1 install -Bundle .\dist\zhigou-toolchain-0.2.0.zip
.EXAMPLE
  .\Install-Zhigou.ps1 status
.EXAMPLE
  .\Install-Zhigou.ps1 rollback
#>
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$installer = Join-Path $PSScriptRoot 'zhigou_install.py'

function Find-Python {
    foreach ($candidate in @('py', 'python3', 'python')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        $prefix = @()
        if ($candidate -eq 'py') { $prefix = @('-3') }
        try { & $command.Source @prefix '-c' 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>$null }
        catch { continue }
        if ($LASTEXITCODE -eq 0) { return @{ Exe = $command.Source; Prefix = $prefix } }
    }
    throw '需要 Python 3.10+。请安装 https://www.python.org/downloads/ 后重新打开本窗口。'
}

if ($Action -eq 'menu') {
    Write-Host '智构 Zhigou 工具链 - 安装 / 升级 / 回退 / 卸载'
    Write-Host '  1 安装或升级   2 查看状态   3 校验文件   4 回退   5 卸载   6 查看安装包信息   7 恢复中断'
    $map = @{ '1' = 'install'; '2' = 'status'; '3' = 'verify'; '4' = 'rollback'; '5' = 'uninstall'; '6' = 'inspect-bundle'; '7' = 'recover' }
    $Action = $map[(Read-Host '输入操作编号')]
    if (-not $Action) { throw '无效操作编号' }

    if ($Action -in @('install', 'upgrade') -and -not $Bundle) {
        $Bundle = Read-Host '安装包 .zip 完整路径'
    }
    if ($Action -in @('install', 'upgrade')) {
        Write-Host ''
        Write-Host '提示：安装/升级不会导入 EasyEDA 扩展，也不会自动启动 daemon。'
        Write-Host '      升级会先备份旧版本；失败自动回退。'
        if (-not $Yes -and (Read-Host '确认现在执行？输入 YES') -cne 'YES') { exit 0 }
        Write-Host ''
        Write-Host '是否同时把 Skill 装进某个 AI 客户端目录？(1 Claude / 2 Codex / 3 Agents / 直接回车=只装到安装目录)'
        $client = @{ '1' = 'claude'; '2' = 'codex'; '3' = 'agents' }[(Read-Host '输入编号')]
        if ($client) { $SkillClient = $client }
    }
    if ($Action -eq 'uninstall') {
        Write-Host '卸载只删除本工具链记录的文件；用户 config/ 默认保留。'
        if (-not $Yes -and (Read-Host '确认卸载？输入 YES') -cne 'YES') { exit 0 }
    }
}

# Locate the bundle next to this script (the installer ZIP ships them side by side)
# unless the caller passed -Bundle explicitly. This is what makes "extract and
# double-click" work, and it keeps --release.json bound to that exact archive.
if ($Action -in @('install', 'upgrade') -and -not $Bundle) {
    $releaseFile = Join-Path $PSScriptRoot 'toolchain-release.json'
    if (Test-Path -LiteralPath $releaseFile) {
        try {
            $rel = Get-Content -LiteralPath $releaseFile -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($rel.archive) {
                $candidate = Join-Path $PSScriptRoot $rel.archive
                if (Test-Path -LiteralPath $candidate) {
                    $Bundle = $candidate
                    if (-not $Release) { $Release = $releaseFile }
                }
            }
        }
        catch { Write-Warning "toolchain-release.json 无法解析，改为按文件名查找安装包：$($_.Exception.Message)" }
    }
    if (-not $Bundle) {
        $found = Get-ChildItem -LiteralPath $PSScriptRoot -Filter 'zhigou-toolchain-*.zip' -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($found) { $Bundle = $found.FullName }
    }
    if (-not $Bundle) {
        throw '未找到安装包：请把 zhigou-toolchain-<版本>.zip 与本脚本放在同一目录，或用 -Bundle 指定完整路径。'
    }
}
if ($Action -in @('install', 'upgrade')) {
    Write-Verbose "bundle: $Bundle"
}

$python = Find-Python
$argsList = @($installer, $Action)
if ($Bundle) { $argsList += @('--bundle', $Bundle) }
if ($Release) { $argsList += @('--release', $Release) }
if ($InstallDir) { $argsList += @('--install-dir', $InstallDir) }
if ($StateDir) { $argsList += @('--state-dir', $StateDir) }
if ($HomeDirectory) { $argsList += @('--home', $HomeDirectory) }
if ($SkillClient -and $SkillClient -ne 'none') { $argsList += @('--skill-client', $SkillClient) }
if ($SkillRoot) { $argsList += @('--skill-root', $SkillRoot) }
if ($Force) { $argsList += '--force' }
if ($Adopt) { $argsList += '--adopt' }
if ($NoSelfCheck) { $argsList += '--no-self-check' }
if ($DryRun) { $argsList += '--dry-run' }
if ($PurgeState) { $argsList += '--purge-state' }
if ($To) { $argsList += @('--to', $To) }
if ($Backup) { $argsList += @('--backup', $Backup) }

& $python.Exe @($python.Prefix) @argsList
$code = $LASTEXITCODE
if ($code -eq 0 -and $Action -in @('install', 'upgrade', 'rollback')) {
    Write-Host ''
    Write-Host '文件操作完成。下一步需人工在 EasyEDA Pro 导入 .eext 并完全重启 EDA（安装器不会自动导入）。'
}
exit $code
