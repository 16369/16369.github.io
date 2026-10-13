<#
.SYNOPSIS
    新建一篇文章，自动填好日期、标签和 front matter。
.EXAMPLE
    .\new-post.ps1 "从零搭建一个博客" -Tags 建站,Python -Category 技术
    .\new-post.ps1 "随手记" -Draft
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Title,
    [string[]]$Tags = @(),
    [string[]]$Category = @(),
    [string]$Slug,
    [string]$Date,
    [switch]$Draft,
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { & (Join-Path $root 'build.ps1') | Out-Null }

$pyArgs = @((Join-Path $root 'tools\new_post.py'), $Title)
if ($Tags.Count -gt 0)     { $pyArgs += @('--tags', ($Tags -join ',')) }
if ($Category.Count -gt 0) { $pyArgs += @('--category', ($Category -join ',')) }
if ($Slug)  { $pyArgs += @('--slug', $Slug) }
if ($Date)  { $pyArgs += @('--date', $Date) }
if ($Draft) { $pyArgs += '--draft' }
if ($Force) { $pyArgs += '--force' }

& $python @pyArgs