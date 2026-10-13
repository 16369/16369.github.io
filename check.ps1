<#
.SYNOPSIS
    构建后自检：内部链接、资源引用、RSS、站点地图、搜索索引。
.EXAMPLE
    .\check.ps1
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { & (Join-Path $root 'build.ps1') | Out-Null }
& $python (Join-Path $root 'tools\check.py')