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
    $ahead = git rev-list --count 'origin/main..HEAD'
    if ($LASTEXITCODE -ne 0) { throw '无法读取本地提交状态。' }
    if ([int]$ahead -eq 0) {
        Write-Host '没有需要发布的新内容。' -ForegroundColor Yellow
        exit 0
    }
    Write-Host "检测到 $ahead 个尚未推送的本地提交，继续发布…" -ForegroundColor Yellow
} else {
    if (-not $Message) {
        $Message = "更新博客 $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    }

    git commit -m $Message
    if ($LASTEXITCODE -ne 0) { throw 'Git 提交失败，已停止发布。' }
}

$pushed = $false
for ($attempt = 1; $attempt -le 3; $attempt++) {
    git push
    if ($LASTEXITCODE -eq 0) { $pushed = $true; break }
    if ($attempt -lt 3) {
        Write-Host "推送失败，正在重试（$attempt/3）…" -ForegroundColor Yellow
        Start-Sleep -Seconds (2 * $attempt)
    }
}
if (-not $pushed) {
    Write-Host '常规 Git 推送失败，正在改用 GitHub API 通道发布…' -ForegroundColor Yellow
    & (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $root 'tools\api_publish.py')
    if ($LASTEXITCODE -ne 0) {
        throw '两种发布通道都失败了。提交已保存在本地，网络恢复后重新运行 .\publish.ps1 即可。'
    }
}

Write-Host '发布完成：https://16369.github.io/' -ForegroundColor Green