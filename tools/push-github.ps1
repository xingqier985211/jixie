# Push this repository to GitHub and turn on GitHub Pages.
# ASCII only on purpose: Windows PowerShell 5.1 reads non-BOM UTF-8 files as GBK
# and would fail to parse a script containing Chinese comments.
#
# Run:
#   powershell -ExecutionPolicy Bypass -File .\tools\push-github.ps1

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $RepoRoot

# git is not on PATH on this machine; use the copy shipped with VS Code / GitHub tools
$candidates = @(
  'C:\Users\LEGION\AppData\Local\github-copilot-git-2.53.0-3\cmd\git.exe',
  "$env:LOCALAPPDATA\GitHubDesktop\app-3.6.5\resources\app\git\cmd\git.exe",
  'C:\Program Files\Git\cmd\git.exe'
)
$gitExe = $null
foreach ($c in $candidates) { if (Test-Path $c) { $gitExe = $c; break } }
if (-not $gitExe) { throw 'git.exe not found.' }

Write-Host "git     : $gitExe" -ForegroundColor DarkGray
Write-Host "workdir : $RepoRoot" -ForegroundColor DarkGray
& $gitExe log --oneline -3
Write-Host ''

$secure = Read-Host 'Paste GitHub token (input is hidden)' -AsSecureString
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $token = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
  [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
if ([string]::IsNullOrWhiteSpace($token)) { throw 'No token entered.' }

# one-shot credential, local to this repository only
$credFile = Join-Path $RepoRoot '.git-credentials'
& $gitExe config --local credential.helper "store --file=$credFile"
Set-Content -Path $credFile -Value ("https://xingqier985211:" + $token + "@github.com") -Encoding ASCII -NoNewline

$pushOk = $false
try {
  Write-Host ''
  Write-Host 'Pushing main ...' -ForegroundColor Cyan
  & $gitExe push -u origin main
  if ($LASTEXITCODE -ne 0) { throw 'git push failed, see the message above.' }
  $pushOk = $true

  Write-Host ''
  Write-Host 'Enabling GitHub Pages ...' -ForegroundColor Cyan
  $headers = @{
    Authorization          = 'Bearer ' + $token
    Accept                 = 'application/vnd.github+json'
    'X-GitHub-Api-Version' = '2022-11-28'
    'User-Agent'           = 'dsh-setup'
  }
  $body = '{"source":{"branch":"main","path":"/"}}'
  try {
    Invoke-RestMethod -Method Post -Uri 'https://api.github.com/repos/xingqier985211/jixie/pages' `
      -Headers $headers -Body $body -ContentType 'application/json' | Out-Null
    Write-Host 'Pages enabled.' -ForegroundColor Green
  } catch {
    Write-Host 'Could not enable Pages automatically (token may lack the Pages permission).' -ForegroundColor Yellow
    Write-Host 'Do it by hand: repo -> Settings -> Pages -> Source: Deploy from a branch -> main / (root) -> Save' -ForegroundColor Yellow
  }
} finally {
  Remove-Item $credFile -Force -ErrorAction SilentlyContinue
  & $gitExe config --local --unset credential.helper 2>$null
  Write-Host 'Local credential cleaned up.' -ForegroundColor DarkGray
}

if ($pushOk) {
  Write-Host ''
  Write-Host 'Done. Wait 1-2 minutes, then open:' -ForegroundColor Green
  Write-Host '  https://xingqier985211.github.io/jixie/'
  Write-Host '  https://xingqier985211.github.io/jixie/2048/2048.html'
}
