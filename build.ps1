<#
.SYNOPSIS
    把 content/ 里的 Markdown 生成到 public/。
.EXAMPLE
    .\build.ps1
    .\build.ps1 -Drafts
#>
[CmdletBinding()]
param(
    [switch]$Drafts,          # 连 draft: true 的草稿一起构建
    [string]$Out,             # 自定义输出目录
    [switch]$NoClean          # 不清理输出目录
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Host '第一次运行：正在创建虚拟环境并安装依赖…' -ForegroundColor Cyan
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw '没找到 Python。请先安装 Python 3.10+ 并勾选 “Add to PATH”。'
    }
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '创建 Python 虚拟环境失败。' }
}
$readyFile = Join-Path $root '.venv\.blog-ready'
$requirementsHash = (Get-FileHash -LiteralPath (Join-Path $root 'requirements.txt') -Algorithm SHA256).Hash
$installedHash = if (Test-Path -LiteralPath $readyFile) { Get-Content -LiteralPath $readyFile -Raw } else { '' }
if ($installedHash -ne $requirementsHash) {
    & $python -m pip install -r requirements.txt -q
    if ($LASTEXITCODE -ne 0) { throw '安装博客依赖失败，请检查网络后重试。' }
    Set-Content -LiteralPath $readyFile -Value $requirementsHash -NoNewline -Encoding ascii
}

$pyArgs = @((Join-Path $root 'tools\build.py'))
if ($Drafts)  { $pyArgs += '--drafts' }
if ($Out)     { $pyArgs += @('--out', $Out) }
if ($NoClean) { $pyArgs += '--no-clean' }

& $python @pyArgs
