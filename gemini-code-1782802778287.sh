# 1. フォルダに移動
cd /path/to/oss-wee

# 2. Gitの初期化とリモートリポジトリの紐付け
git init
git remote add origin https://github.com/kiki054-n/oss-wee.git

# 3. 憲章と動画をコミット
git add .
git commit -m "Genesis: 友朋共生 OSWアンセムと憲章のデプロイ"

# 4. GitHubへプッシュ（メインブランチへ）
git branch -M main
git push -u origin main