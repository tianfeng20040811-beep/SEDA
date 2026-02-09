#!/bin/bash
# 一键推送到 GitHub

echo "🚀 SEDAI Solar2Grid - GitHub 部署脚本"
echo "======================================"
echo ""

# 检查是否已初始化 Git
if [ ! -d ".git" ]; then
    echo "📦 初始化 Git 仓库..."
    git init
    git branch -M main
fi

# 添加所有文件
echo "📝 添加文件到 Git..."
git add .

# 提交
echo "💾 提交更改..."
read -p "请输入提交信息 (默认: Initial commit): " commit_message
commit_message=${commit_message:-"Initial commit"}
git commit -m "$commit_message"

# 询问 GitHub 仓库地址
echo ""
echo "🔗 请提供 GitHub 仓库信息"
echo "   1. 访问 https://github.com/new 创建新仓库"
echo "   2. 仓库名建议: sedai-solar2grid"
echo "   3. 不要勾选 'Initialize with README'"
echo ""
read -p "请输入您的 GitHub 用户名: " github_username
read -p "请输入仓库名 (默认: sedai-solar2grid): " repo_name
repo_name=${repo_name:-sedai-solar2grid}

# 设置远程仓库
github_url="https://github.com/$github_username/$repo_name.git"
echo ""
echo "🌐 设置远程仓库: $github_url"

# 检查是否已有 origin
if git remote | grep -q "origin"; then
    git remote set-url origin "$github_url"
else
    git remote add origin "$github_url"
fi

# 推送
echo ""
echo "⬆️  推送到 GitHub..."
git push -u origin main

echo ""
echo "✅ 完成！"
echo ""
echo "🌐 您的项目链接:"
echo "   https://github.com/$github_username/$repo_name"
echo ""
echo "📱 下一步:"
echo "   1. 部署到 Vercel: cd apps/mobile_flutter && flutter build web && cd build/web && vercel --prod"
echo "   2. 部署到 Railway: 在 railway.app 导入您的 GitHub 仓库"
echo "   3. 设置 GitHub Pages: 在仓库设置中启用 Pages"
echo ""
