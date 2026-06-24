<#
.SYNOPSIS
    把 3Dmigoto-MI 运行时安装到游戏目录，或从游戏目录卸载。

.DESCRIPTION
    复制 3DMigoto 二进制、所选 d3dx 配置（release/dev）和 ShaderFixes 到游戏目录，
    并确保存在 Mods 目录。二进制不随仓库分发，需先放到本目录下。

.EXAMPLE
    ./install.ps1 -GameDir "D:\Games\gakumas"
    ./install.ps1 -GameDir "D:\Games\gakumas" -Config dev
    ./install.ps1 -GameDir "D:\Games\gakumas" -Uninstall
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$GameDir,
    [ValidateSet('release', 'dev')][string]$Config = 'release',
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Binaries = @('d3d11.dll', 'nvapi64.dll', 'd3dcompiler_47.dll')

if (-not (Test-Path $GameDir)) { throw "游戏目录不存在: $GameDir" }
if (-not (Test-Path (Join-Path $GameDir 'gakumas.exe'))) {
    Write-Warning "未在目标目录找到 gakumas.exe，请确认 -GameDir 是否正确: $GameDir"
}

if ($Uninstall) {
    foreach ($f in ($Binaries + 'd3dx.ini')) {
        $p = Join-Path $GameDir $f
        if (Test-Path $p) { Remove-Item $p -Force; Write-Host "已删除 $f" }
    }
    Write-Host "卸载完成。ShaderFixes/ 与 Mods/ 未自动删除，如需彻底清理请手动删除。"
    return
}

# 二进制不入库，安装前确认已补齐。
$missing = $Binaries | Where-Object { -not (Test-Path (Join-Path $Root $_)) }
if ($missing) {
    throw "缺少 3DMigoto 二进制: $($missing -join ', ')。请从 3DMigoto v1.4.9 发行版或可工作的游戏目录补齐到 3Dmigoto-MI\ 后再安装。"
}

$iniSource = if ($Config -eq 'dev') { 'd3dx.ini' } else { 'd3dx-release.ini' }
$iniPath = Join-Path $Root $iniSource
if (-not (Test-Path $iniPath)) { throw "找不到配置文件: $iniSource" }

foreach ($f in $Binaries) {
    Copy-Item (Join-Path $Root $f) (Join-Path $GameDir $f) -Force
    Write-Host "已复制 $f"
}
Copy-Item $iniPath (Join-Path $GameDir 'd3dx.ini') -Force
Write-Host "已应用配置: $iniSource -> d3dx.ini ($Config)"

$sfSrc = Join-Path $Root 'ShaderFixes'
if (Test-Path $sfSrc) {
    $sfDst = Join-Path $GameDir 'ShaderFixes'
    New-Item -ItemType Directory -Force -Path $sfDst | Out-Null
    Copy-Item (Join-Path $sfSrc '*') $sfDst -Recurse -Force
    Write-Host "已复制 ShaderFixes"
}

New-Item -ItemType Directory -Force -Path (Join-Path $GameDir 'Mods') | Out-Null

Write-Host ""
Write-Host "安装完成（$Config 配置）。用 -force-d3d11 启动游戏即可。" -ForegroundColor Green
if ($Config -eq 'dev') {
    Write-Host "提示: dev 配置开启了 Hunting / Frame Analysis，发布给玩家请改用 -Config release。"
}
