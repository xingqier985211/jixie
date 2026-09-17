# ============================================================================
# 一键提交到 GitHub（在本机 PowerShell 里运行，不用管理员权限）
#
# 用法：
#   1. 到 https://github.com/settings/personal-access-tokens/new 新建
#      Fine-grained token，Repository access 选 “Only select repositories” → jixie，
#      Permissions 里把 Contents 设为 Read and write（想让我顺便开 Pages，再给 Pages: Read and write），
#      Expiration 建议 7 天；生成后复制那串 github_pat_xxx（只显示一次）。
#   2. 在本窗口执行：  .\tools\push-to-github.ps1
#      粘贴 token 时不会显示、也不会经过任何人，用完我会立刻帮你删掉本地凭据。
# ============================================================================

$ErrorActionPreference = 'Stop'

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $RepoRoot

# 本机 git 没在 PATH 里，这里用 VS Code 自带的
$gitCandidates = @(
  "C:\Users\LEGION\AppData\Local\github-copilot-git-2.53.0-3\cmd\git.exe",
  "$env:LOCALAPPDATA\GitHubDesktop\app-3.6.5\resources\app\git\cmd\git.exe",
  "C:\Program Files\Git\cmd\git.exe"
)
$gitExe = $gitCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $gitExe) { throw "没找到 git.exe，请先告诉我，我换一种方式。" }

Write-Host "使用 git: $gitExe" -ForegroundColor DarkGray
Write-Host "仓库目录: $RepoRoot" -ForegroundColor DarkGray
& $gitExe log --oneline -3
Write-Host ""

$token = Read-Host "请粘贴 GitHub Token（输入时不显示）" -AsSecureString
$plain = [System.Net.NetworkCredential]::new('', $token).Password
if ([string]::IsNullOrWhiteSpace($plain)) { throw "没有输入 token，已取消。" }

# 把 token 作为一次性认证信息写进本仓库的 credential store（只在本仓库生效）
& $gitExe config --local credential.helper "store --file=$RepoRoot\.git-credentials"
"https://xingqier985211:$plain@github.com" | Set-Content -Encoding ASCII -NoNewline "$RepoRoot\.git-credentials"

try {
  Write-Host "`n正在推送 main 分支..." -ForegroundColor Cyan
  & $gitExe push -u origin main
  if ($LASTEXITCODE -ne 0) { throw "推送失败（上面有 git 的错误信息）" }

  Write-Host "`n正在开启 GitHub Pages..." -ForegroundColor Cyan
  $headers = @{
    Authorization = "Bearer $plain"
    Accept        = "application/vnd.github+json"
    'User-Agent'  = 'dsh-setup'
  }
  $body = '{"source":{"branch":"main","path":"/"}}'
  try {
    Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/xingqier985211/jixie/pages" `
      -Headers $headers -Body $body -ContentType 'application/json' | Out-Null
    Write-Host "Pages 已开启（main 分支根目录）。" -ForegroundColor Green
  } catch {
    Write-Host "自动开启 Pages 没成功（可能是 token 没给 Pages 权限）。" -ForegroundColor Yellow
    Write-Host "请手动开启：仓库 → Settings → Pages → Source 选 Deploy from a branch → main / (root) → Save" -ForegroundColor Yellow
  }
  Write-Host "`n完成！稍等 1~2 分钟后访问：" -ForegroundColor Green
  Write-Host "  个人主页: https://xingqier985211.github.io/jixie/" -ForegroundColor Green
  Write-Host "  2048 游戏: https://xingqier985211.github.io/jixie/2048/2048.html" -ForegroundColor Green
} finally {
  # 清理凭据，避免明文 token 留在磁盘上
  Remove-Item "$RepoRoot\.git-credentials" -Force -ErrorAction SilentlyContinue
  & $gitExe config --local --unset credential.helper 2>$null
  Write-Host "`n已清理本地保存的 token。" -ForegroundColor DarkGray
}
