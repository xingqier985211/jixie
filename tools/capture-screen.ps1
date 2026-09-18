# Capture the whole screen to a PNG (no GUI, works from a normal PowerShell window).
# ASCII only: Windows PowerShell 5.1 parses non-BOM UTF-8 files as GBK.
#
# Run:
#   powershell -ExecutionPolicy Bypass -File .\tools\capture-screen.ps1
#   powershell -ExecutionPolicy Bypass -File .\tools\capture-screen.ps1 -DelaySeconds 8
#
# Output: _tools\screen.png  (tell me when it is done and I will look at it)

param(
  [int]$DelaySeconds = 5
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$outDir = Join-Path $RepoRoot '_tools'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$out = Join-Path $outDir 'screen.png'

Write-Host ''
Write-Host "Taking a screenshot of the whole screen in $DelaySeconds seconds." -ForegroundColor Cyan
Write-Host 'Please bring the PDF window to the front now.' -ForegroundColor Cyan
for ($i = $DelaySeconds; $i -gt 0; $i--) {
  Write-Host ("  {0}..." -f $i) -NoNewline
  Start-Sleep -Seconds 1
}
Write-Host ''

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($bounds.X, $bounds.Y, 0, 0, $bmp.Size)
$g.Dispose()
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()

$size = (Get-Item $out).Length
Write-Host ''
Write-Host ("OK  screenshot saved: {0} ({1:N0} bytes, {2}x{3})" -f $out, $size, $bounds.Width, $bounds.Height) -ForegroundColor Green
Write-Host 'Tell me when it is done and I will inspect it.'
