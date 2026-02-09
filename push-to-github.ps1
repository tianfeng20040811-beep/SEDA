# 一键推送到 GitHub (Windows PowerShell)

Write-Host "🚀 SEDAI Solar2Grid - GitHub 部署脚本" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# 检查是否已安装 Git
$gitExists = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitExists) {
    Write-Host "❌ 未检测到 Git，请先安装 Git: https://git-scm.com/download/win" -ForegroundColor Red
    exit 1
}

# 检查是否已初始化 Git
if (-not (Test-Path ".git")) {
    Write-Host "📦 初始化 Git 仓库..." -ForegroundColor Yellow
    git init
    git branch -M main
}

# 添加所有文件
Write-Host "📝 添加文件到 Git..." -ForegroundColor Yellow
git add .

# 提交
Write-Host "💾 提交更改..." -ForegroundColor Yellow
$commit_message = Read-Host "请输入提交信息 (直接回车使用默认: Initial commit)"
if ([string]::IsNullOrWhiteSpace($commit_message)) {
    $commit_message = "Initial commit"
}
git commit -m "$commit_message"

# 询问 GitHub 仓库地址
Write-Host ""
Write-Host "🔗 GitHub 仓库设置" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "步骤:" -ForegroundColor Yellow
Write-Host "  1. 访问 https://github.com/new 创建新仓库" -ForegroundColor White
Write-Host "  2. 仓库名建议: sedai-solar2grid" -ForegroundColor White
Write-Host "  3. 设置为 Public（公开）以便分享" -ForegroundColor White
Write-Host "  4. 不要勾选 'Initialize with README'" -ForegroundColor White
Write-Host ""

$github_username = Read-Host "请输入您的 GitHub 用户名"
$repo_name = Read-Host "请输入仓库名 (直接回车使用默认: sedai-solar2grid)"
if ([string]::IsNullOrWhiteSpace($repo_name)) {
    $repo_name = "sedai-solar2grid"
}

# 设置远程仓库
$github_url = "https://github.com/$github_username/$repo_name.git"
Write-Host ""
Write-Host "🌐 设置远程仓库: $github_url" -ForegroundColor Cyan

# 检查是否已有 origin
$hasOrigin = git remote | Select-String "origin"
if ($hasOrigin) {
    git remote set-url origin "$github_url"
} else {
    git remote add origin "$github_url"
}

# 推送
Write-Host ""
Write-Host "⬆️  推送到 GitHub..." -ForegroundColor Yellow
Write-Host "   (首次推送可能需要输入 GitHub 用户名和密码/Token)" -ForegroundColor Gray
Write-Host ""

try {
    git push -u origin main
    
    Write-Host ""
    Write-Host "✅ 推送成功！" -ForegroundColor Green
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "🌐 您的项目链接:" -ForegroundColor Green
    Write-Host "   https://github.com/$github_username/$repo_name" -ForegroundColor White
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    
    Write-Host "📱 下一步 - 部署选项:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1️⃣  部署 Flutter Web 到 Vercel (推荐):" -ForegroundColor Yellow
    Write-Host "   cd apps\mobile_flutter" -ForegroundColor Gray
    Write-Host "   flutter build web --release" -ForegroundColor Gray
    Write-Host "   cd build\web" -ForegroundColor Gray
    Write-Host "   vercel --prod" -ForegroundColor Gray
    Write-Host "   >> 获得链接: https://sedai-solar2grid.vercel.app" -ForegroundColor Green
    Write-Host ""
    
    Write-Host "2️⃣  部署全栈到 Railway:" -ForegroundColor Yellow
    Write-Host "   访问: https://railway.app" -ForegroundColor Gray
    Write-Host "   点击 'Deploy from GitHub'" -ForegroundColor Gray
    Write-Host "   选择: $github_username/$repo_name" -ForegroundColor Gray
    Write-Host "   >> 自动部署所有服务" -ForegroundColor Green
    Write-Host ""
    
    Write-Host "3️⃣  启用 GitHub Pages:" -ForegroundColor Yellow
    Write-Host "   访问: https://github.com/$github_username/$repo_name/settings/pages" -ForegroundColor Gray
    Write-Host "   Source: Deploy from a branch" -ForegroundColor Gray
    Write-Host "   Branch: main -> /docs" -ForegroundColor Gray
    Write-Host ""
    
    Write-Host "📖 文档:" -ForegroundColor Cyan
    Write-Host "   README.md - 项目介绍" -ForegroundColor White
    Write-Host "   QUICKSTART.md - 快速启动指南" -ForegroundColor White
    Write-Host ""
    
    # 询问是否自动打开浏览器
    $openBrowser = Read-Host "是否在浏览器中打开项目页面？(Y/n)"
    if ([string]::IsNullOrWhiteSpace($openBrowser) -or $openBrowser -eq "Y" -or $openBrowser -eq "y") {
        Start-Process "https://github.com/$github_username/$repo_name"
    }
    
} catch {
    Write-Host ""
    Write-Host "❌ 推送失败" -ForegroundColor Red
    Write-Host ""
    Write-Host "可能的原因:" -ForegroundColor Yellow
    Write-Host "  1. 仓库尚未在 GitHub 创建" -ForegroundColor White
    Write-Host "  2. 需要 GitHub 身份验证" -ForegroundColor White
    Write-Host ""
    Write-Host "解决方案:" -ForegroundColor Yellow
    Write-Host "  1. 访问 https://github.com/new 创建仓库" -ForegroundColor White
    Write-Host "  2. 设置 Git 凭据: git config --global user.name 'Your Name'" -ForegroundColor White
    Write-Host "  3. 使用 Personal Access Token 而非密码" -ForegroundColor White
    Write-Host "     生成 Token: https://github.com/settings/tokens" -ForegroundColor White
    Write-Host ""
    Write-Host "完成后重新运行此脚本" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "按任意键退出..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
