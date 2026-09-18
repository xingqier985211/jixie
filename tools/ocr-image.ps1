# OCR an image with the OCR engine built into Windows (WinRT), no extra installs.
# ASCII only on purpose (Windows PowerShell 5.1 reads non-BOM UTF-8 as GBK).
#
# Run:
#   powershell -ExecutionPolicy Bypass -File .\tools\ocr-image.ps1 -Path _tools\pdf-page1.png
#
# Output: _tools\ocr-result.txt  (UTF-8)

param(
  [string]$Path = '',
  [string]$Lang = ''
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Path) { $Path = Join-Path $RepoRoot '_tools\pdf-page1.png' }
if (-not (Test-Path $Path)) { throw "image not found: $Path" }
$Path = (Resolve-Path $Path).Path

# WinRT types work in Windows PowerShell (5.1); pwsh 7 needs the extra load step
[void][Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
[void][Windows.Media.Ocr.OcrEngine, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime]
[void][Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime]
[void][Windows.Globalization.Language, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime]

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]
function Await($task, $type) {
  $m = $asTaskGeneric.MakeGenericMethod($type)
  $t = $m.Invoke($null, @($task))
  $t.Wait(-1) | Out-Null
  $t.Result
}

$engine = $null
if ($Lang) {
  try {
    $langObj = [Windows.Globalization.Language]::new($Lang)
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($langObj)
  } catch { $engine = $null }
}
if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if (-not $engine) {
  # 退化方案：在系统已安装的 OCR 语言里挑一个
  $avail = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages
  Write-Host ("Available OCR languages: " + (($avail | ForEach-Object { $_.LanguageTag }) -join ', ')) -ForegroundColor Yellow
  foreach ($l in $avail) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($l)
    if ($engine) { break }
  }
}
if (-not $engine) { throw 'No OCR engine available on this machine.' }

$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

$outFile = Join-Path (Split-Path $Path -Parent) 'ocr-result.txt'
$lines = @("OCR language: " + $engine.RecognizerLanguage.LanguageTag, "source image: $Path", '')
foreach ($line in $result.Lines) { $lines += $line.Text }
$lines | Set-Content -Path $outFile -Encoding UTF8

Write-Host ''
Write-Host ("OCR done: {0} lines -> {1}" -f $result.Lines.Count, $outFile) -ForegroundColor Green
Write-Host ''
Get-Content $outFile -Encoding UTF8 | Select-Object -First 40
