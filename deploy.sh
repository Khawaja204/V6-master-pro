#!/bin/bash
echo "=========================================="
echo "🚀 V6 MASTER PRO - DEPLOY SCRIPT"
echo "=========================================="

# 1. Git conflict marker check & fix
if grep -q "<<<<<<< HEAD" scoring_engine.py; then
    echo "⚠️  Git conflict marker mila! Fix kar raha hoon..."
    sed -i '/<<<<<<< HEAD/,/>>>>>>> .*/d' scoring_engine.py
    echo "✅ Conflict marker hata diya!"
else
    echo "✅ No conflict markers found"
fi

# 2. .gitignore check
if [ ! -f ".gitignore" ]; then
    echo "api_keys.json" > .gitignore
    echo "*.log" >> .gitignore
    echo "__pycache__/" >> .gitignore
    echo "✅ .gitignore banaya!"
elif ! grep -q "api_keys.json" .gitignore; then
    echo "api_keys.json" >> .gitignore
    echo "*.log" >> .gitignore
    echo "✅ .gitignore update kiya!"
else
    echo "✅ .gitignore theek hai"
fi

# 3. Git status
echo ""
echo "📁 Git Status:"
git status --short

# 4. Add all
echo ""
echo "➕ Adding all changes..."
git add .

# 5. Commit
echo ""
read -p "💬 Commit message likho (ya Enter dabaao for auto): " msg
if [ -z "$msg" ]; then
    msg="V6 update: $(date '+%Y-%m-%d %H:%M')"
fi
git commit -m "$msg"
echo "✅ Commit ho gaya: $msg"

# 6. Pull latest (conflict avoid karne ke liye)
echo ""
echo "⬇️  Latest code pull kar raha hoon..."
git pull origin main --rebase

# 7. Push
echo ""
echo "⬆️  GitHub pe push kar raha hoon..."
git push origin main

echo ""
echo "=========================================="
echo "✅ DONE! Render deploy hoga in 30-60 sec"
echo "🔗 Check: https://r-pro-1.onrender.com"
echo "=========================================="
