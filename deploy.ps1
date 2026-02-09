# SEDAI Solar2Grid - Quick Deploy Script (Windows)
# 用于快速部署到 Vercel/Netlify 获得演示链接

Write-Host "🚀 SEDAI Solar2Grid - 快速部署" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Flutter
$flutterExists = Get-Command flutter -ErrorAction SilentlyContinue
if (-not $flutterExists) {
    Write-Host "❌ Flutter 未安装，请先安装 Flutter SDK" -ForegroundColor Red
    exit 1
}

# 进入 Flutter 项目
Set-Location apps\mobile_flutter

# 安装依赖
Write-Host "📦 安装依赖..." -ForegroundColor Yellow
flutter pub get

# 构建 Web 版本
Write-Host "🏗️  构建 Flutter Web..." -ForegroundColor Yellow
flutter build web --release --web-renderer html

Write-Host ""
Write-Host "✅ 构建完成！" -ForegroundColor Green
Write-Host ""
Write-Host "📂 构建产物位置: apps\mobile_flutter\build\web" -ForegroundColor Cyan
Write-Host ""
Write-Host "🌐 部署选项：" -ForegroundColor Cyan
Write-Host ""
Write-Host "1️⃣  Vercel (推荐):" -ForegroundColor White
Write-Host "   npm i -g vercel" -ForegroundColor Gray
Write-Host "   cd build\web" -ForegroundColor Gray
Write-Host "   vercel --prod" -ForegroundColor Gray
Write-Host "   >> 会获得一个 https://your-app.vercel.app 链接" -ForegroundColor Green
Write-Host ""
Write-Host "2️⃣  Netlify:" -ForegroundColor White
Write-Host "   npm i -g netlify-cli" -ForegroundColor Gray
Write-Host "   cd build\web" -ForegroundColor Gray
Write-Host "   netlify deploy --prod" -ForegroundColor Gray
Write-Host "   >> 会获得一个 https://your-app.netlify.app 链接" -ForegroundColor Green
Write-Host ""
Write-Host "3️⃣  本地预览:" -ForegroundColor White
Write-Host "   cd build\web" -ForegroundColor Gray
Write-Host "   python -m http.server 8080" -ForegroundColor Gray
Write-Host "   >> 访问 http://localhost:8080" -ForegroundColor Green
Write-Host ""
Write-Host "4️⃣  自动打开本地预览 (推荐):" -ForegroundColor White
Write-Host "   按任意键启动本地服务器..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

Set-Location build\web
Start-Process "http://localhost:8080"
python -m http.server 8080
