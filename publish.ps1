<#
.SYNOPSIS
    构建、自检、提交并发布博客到 GitHub Pages。
.EXAMPLE
    .\publish.ps1
    .\publish.ps1 -Message "新增文章：我的第一篇博客"
#>
[CmdletBinding()]
param(
    [string]$Message = ""
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

& (Join-Path $root 'build.ps1')
if ($LASTEXITCODE -ne 0) { throw '构建失败，已停止发布。' }

& (Join-Path $root 'check.ps1')
if ($LASTEXITCODE -ne 0) { throw '自检失败，已停止发布。' }

git add .
$staged = git diff --cached --name-only
if (-not $staged) {
    Write-Host '没有需要发布的新内容。' -ForegroundColor Yellow
    exit 0
}

if (-not $Message) {
    $Message = "更新博客 $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
}

git commit -m $Message
if ($LASTEXITCODE -ne 0) { throw 'Git 提交失败，已停止发布。' }

git push
if ($LASTEXITCODE -ne 0) { throw 'Git 推送失败，请检查网络后重试。' }

Write-Host '发布完成：https://16369.github.io/' -ForegroundColor Green