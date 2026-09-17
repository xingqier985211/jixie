# 供本仓库使用的 Git 启动脚本（PowerShell）
#
# 为什么需要它：这台机器上 git 没有加入 PATH，而且用户主目录在当前沙箱下不可写，
# 所以把 HOME / 配置目录指到工作区内部，再使用 VS Code 自带的 git 可执行文件。
#
# 用法：  . .\tools\git-env.ps1        （点号加载，之后直接用 git ...）

$env:HOME = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:XDG_CONFIG_HOME = Join-Path $env:HOME '.gitconfig.d'

$gitExe = "C:\Users\LEGION\AppData\Local\github-copilot-git-2.53.0-3\cmd\git.exe"
function git {
  & $gitExe @args
}
Set-Alias -Name g -Value git -Scope Global

Write-Host "git 环境已就绪：$gitExe" -ForegroundColor Green
& $gitExe --version
