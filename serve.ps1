<#
.SYNOPSIS
    本地预览博客，改动后自动重建并刷新浏览器。
.EXAMPLE
    .\serve.ps1
    .\serve.ps1 -Port 9000 -Drafts
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Drafts,
    [switch]$NoBrowser,
    [switch]$NoWatch
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { & (Join-Path $root 'build.ps1') -Drafts:$Drafts }

$pyArgs = @((Join-Path $root 'tools\serve.py'), '--port', $Port)
if ($Drafts)    { $pyArgs += '--drafts' }
if ($NoBrowser) { $pyArgs += '--no-browser' }
if ($NoWatch)   { $pyArgs += '--no-watch' }

& $python @pyArgs