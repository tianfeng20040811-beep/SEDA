#!/bin/bash

# SEDAI Solar2Grid - Quick Deploy Script
# 用于快速部署到 Vercel/Netlify 获得演示链接

echo "🚀 SEDAI Solar2Grid - 快速部署"
echo "================================"

# 检查 Flutter
if ! command -v flutter &> /dev/null; then
    echo "❌ Flutter 未安装，请先安装 Flutter SDK"
    exit 1
fi

# 进入 Flutter 项目
cd apps/mobile_flutter

# 安装依赖
echo "📦 安装依赖..."
flutter pub get

# 构建 Web 版本
echo "🏗️  构建 Flutter Web..."
flutter build web --release --web-renderer html

echo ""
echo "✅ 构建完成！"
echo ""
echo "📂 构建产物位置: apps/mobile_flutter/build/web"
echo ""
echo "🌐 部署选项："
echo ""
echo "1️⃣  Vercel (推荐):"
echo "   npm i -g vercel"
echo "   cd build/web"
echo "   vercel --prod"
echo "   >> 会获得一个 https://your-app.vercel.app 链接"
echo ""
echo "2️⃣  Netlify:"
echo "   npm i -g netlify-cli"
echo "   cd build/web"
echo "   netlify deploy --prod"
echo "   >> 会获得一个 https://your-app.netlify.app 链接"
echo ""
echo "3️⃣  GitHub Pages:"
echo "   将 build/web 目录推送到 gh-pages 分支"
echo "   >> 会获得一个 https://username.github.io/repo 链接"
echo ""
echo "4️⃣  本地预览:"
echo "   cd build/web"
echo "   python -m http.server 8080"
echo "   >> 访问 http://localhost:8080"
echo ""
