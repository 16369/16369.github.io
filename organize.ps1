<#
.SYNOPSIS
    整理 content/posts/ 里的文章文件名（统一成 日期-标题.md），并检查缺失的元信息。
.EXAMPLE
    .\organize.ps1          # 只看会改什么
    .\organize.ps1 -Apply   # 真的改
#>
[CmdletBinding()]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { & (Join-Path $root 'build.ps1') | Out-Null }

$pyArgs = @((Join-Path $root 'tools\organize.py'))
if ($Apply) { $pyArgs += '--apply' }
& $python @pyArgs