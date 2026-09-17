# Push this repository to GitHub and turn on GitHub Pages.
#
# ASCII only on purpose: Windows PowerShell 5.1 reads non-BOM UTF-8 files as GBK
# and fails to parse a script that contains Chinese comments.
#
# Run:
#   powershell -ExecutionPolicy Bypass -File .\tools\push-github.ps1
#   (optional) -Token <token>   skip the interactive prompt
#   (optional) -Yes             do not ask before the no-verify retry
#
# Notes:
# - tries the Windows certificate store first (http.sslBackend=schannel);
# - if that fails it ASKS you before retrying with certificate checking disabled;
# - the token is never written to disk: it is handed to git through GIT_ASKPASS.

param(
  [string]$Token = '',
  [switch]$Yes
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $RepoRoot

# 1) locate git (it is not on PATH on this machine)
$candidates = @(
  'C:\Users\LEGION\AppData\Local\github-copilot-git-2.53.0-3\cmd\git.exe',
  "$env:LOCALAPPDATA\GitHubDesktop\app-3.6.5\resources\app\git\cmd\git.exe",
  'C:\Program Files\Git\cmd\git.exe'
)
$gitExe = $null
foreach ($c in $candidates) { if (Test-Path $c) { $gitExe = $c; break } }
if (-not $gitExe) { throw 'git.exe not found.' }

# 2) custom git config: no pager (there is no less here) + Windows cert store
$cfgFile = Join-Path $RepoRoot '.git-tmpconfig'
$tab = [char]9
$cfgLines = @(
  '[core]',
  ($tab + 'pager = cat'),
  '[http]',
  ($tab + 'sslBackend = schannel'),
  ($tab + 'schannelCheckRevoke = false')
)
Set-Content -Path $cfgFile -Value $cfgLines -Encoding ASCII

# 3) one-shot askpass helper so the token stays in memory / env only
#    (helper writes the answer; a tiny .cmd wrapper keeps git's invocation simple)
$askPs1 = Join-Path $RepoRoot '.git-askpass-tmp.ps1'
$askCmd = Join-Path $RepoRoot '.git-askpass-tmp.cmd'
$askLines = @(
  'param([string]$Prompt)',
  'if ($Prompt -match ''(?i)username'') { Write-Output ''xingqier985211'' }',
  'else { Write-Output $env:GIT_PUSH_TOKEN }'
)
Set-Content -Path $askPs1 -Value $askLines -Encoding ASCII
Set-Content -Path $askCmd -Value ('powershell -NoProfile -ExecutionPolicy Bypass -File ' + $askPs1 + ' %*') -Encoding ASCII

$env:GIT_ASKPASS = $askCmd
$env:GIT_TERMINAL_PROMPT = '0'

Write-Host "git     : $gitExe" -ForegroundColor DarkGray
Write-Host "workdir : $RepoRoot" -ForegroundColor DarkGray
& $gitExe --no-pager -c "include.path=$cfgFile" log --oneline -3
Write-Host ''

# 4) read the token
$token = $Token
if ([string]::IsNullOrWhiteSpace($token)) {
  $secure = Read-Host 'Paste GitHub token (input is hidden)' -AsSecureString
  $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  try {
    $token = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  } finally {
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  }
}
if ([string]::IsNullOrWhiteSpace($token)) { throw 'No token entered.' }
$env:GIT_PUSH_TOKEN = $token

function Invoke-Push([string[]]$extra) {
  $gitArgs = @('--no-pager', '-c', "include.path=$cfgFile") + $extra + @('push', '-u', 'origin', 'main')
  & $gitExe @gitArgs
  return $LASTEXITCODE
}

$pushOk = $false
try {
  Write-Host ''
  Write-Host 'Pushing main (Windows certificate store) ...' -ForegroundColor Cyan
  $code = Invoke-Push @()
  if ($code -ne 0) {
    Write-Host ''
    Write-Host 'That failed. Most likely the certificate could not be verified.' -ForegroundColor Yellow
    Write-Host 'Retrying once WITHOUT certificate verification would send your token to' -ForegroundColor Yellow
    Write-Host 'whatever answers on that TLS connection, so decide for yourself.' -ForegroundColor Yellow
    $ans = 'n'
    if ($Yes) {
      $ans = 'y'
    } else {
      $ans = Read-Host 'Retry with certificate verification disabled? (y/N)'
    }
    if ($ans -eq 'y' -or $ans -eq 'Y') {
      Write-Host 'Retrying ...' -ForegroundColor Cyan
      $code = Invoke-Push @('-c', 'http.sslBackend=openssl', '-c', 'http.sslVerify=false')
      if ($code -ne 0) { throw 'git push failed, see the message above.' }
    } else {
      throw 'Stopped at your request. Nothing was pushed.'
    }
  }
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
    Write-Host 'By hand: repo -> Settings -> Pages -> Source: Deploy from a branch -> main / (root) -> Save' -ForegroundColor Yellow
  }
} finally {
  $env:GIT_PUSH_TOKEN = ''
  Remove-Item $askPs1 -Force -ErrorAction SilentlyContinue
  Remove-Item $askCmd -Force -ErrorAction SilentlyContinue
  Remove-Item $cfgFile -Force -ErrorAction SilentlyContinue
  Write-Host ''
  Write-Host 'Temp files and token removed.' -ForegroundColor DarkGray
}

if ($pushOk) {
  Write-Host ''
  Write-Host 'Done. Wait 1-2 minutes, then open:' -ForegroundColor Green
  Write-Host '  https://xingqier985211.github.io/jixie/'
  Write-Host '  https://xingqier985211.github.io/jixie/2048/2048.html'
}
