# Capture a screenshot of profile.pdf using the PDF viewer built into Edge.
# ASCII only: Windows PowerShell 5.1 parses non-BOM UTF-8 files as GBK.
#
# Run:
#   powershell -ExecutionPolicy Bypass -File .\tools\capture-pdf-preview.ps1
#
# Output: _tools\pdf-page1.png  (please tell me when it is done)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pdfPath  = Join-Path $RepoRoot 'profile.pdf'
$outDir   = Join-Path $RepoRoot '_tools'
$outPng   = Join-Path $outDir 'pdf-page1.png'

if (-not (Test-Path $pdfPath)) { throw "profile.pdf not found at $pdfPath" }
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
if (Test-Path $outPng) { Remove-Item $outPng -Force }

$edges = @(
  'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
  'C:\Program Files\Microsoft\Edge\Application\msedge.exe'
)
$edge = $null
foreach ($e in $edges) { if (Test-Path $e) { $edge = $e; break } }
if (-not $edge) { throw 'Microsoft Edge not found.' }

$profileDir = Join-Path $outDir 'edge-shot-profile'
New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

$uri = 'file:///' + ($pdfPath -replace '\\', '/')

Write-Host "Rendering $pdfPath with the Edge PDF viewer ..." -ForegroundColor Cyan
$p = Start-Process -FilePath $edge -PassThru -ArgumentList @(
  '--headless=new',
  '--disable-gpu',
  '--window-size=1400,1900',
  '--force-device-scale-factor=1.5',
  '--hide-scrollbars',
  "--user-data-dir=$profileDir",
  '--no-first-run',
  '--no-default-browser-check',
  "--screenshot=$outPng",
  $uri
)

$done = $false
try { Wait-Process -Id $p.Id -Timeout 90 -ErrorAction Stop; $done = $true } catch { }
if (-not $done) { try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch { } }

if (Test-Path $outPng) {
  $size = (Get-Item $outPng).Length
  Write-Host ''
  Write-Host ("OK  screenshot saved: {0} ({1:N0} bytes)" -f $outPng, $size) -ForegroundColor Green
  if ($size -lt 20000) {
    Write-Host 'The image looks very small - the PDF may not have rendered. Tell me if so.' -ForegroundColor Yellow
  }
} else {
  Write-Host 'Screenshot was not produced. Please copy this whole window and send it to me.' -ForegroundColor Red
}
