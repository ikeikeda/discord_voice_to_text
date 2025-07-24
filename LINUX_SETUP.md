# 🐧 Linux サーバーセットアップガイド

Linux サーバーに Discord Voice-to-Text Bot をインストール・運用するための完全ガイドです。

## 📋 前提条件

- Linux サーバー（Ubuntu 20.04+ / CentOS 8+ / Debian 11+ 推奨）
- root または sudo 権限
- インターネット接続
- Discord Bot Token（特権インテント有効化済み）
- OpenAI API Key または Gemini API Key

## 🛠️ システム要件

### 推奨スペック
- **CPU**: 2コア以上
- **メモリ**: 4GB以上
- **ストレージ**: 10GB以上の空き容量
- **OS**: Ubuntu 20.04 LTS（推奨）

### 最小スペック
- **CPU**: 1コア
- **メモリ**: 2GB
- **ストレージ**: 5GB以上の空き容量

## 🚀 インストール手順

### 1. システムの更新

```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y

# CentOS/RHEL
sudo yum update -y
# または Rocky Linux/AlmaLinux の場合
sudo dnf update -y
```

### 2. 必要なパッケージのインストール

```bash
# Ubuntu/Debian
sudo apt install -y git curl wget ffmpeg build-essential

# CentOS/RHEL
sudo yum install -y git curl wget epel-release
sudo yum install -y ffmpeg gcc gcc-c++ make

# Rocky Linux/AlmaLinux
sudo dnf install -y git curl wget epel-release
sudo dnf install -y ffmpeg gcc gcc-c++ make
```

### 3. Docker のインストール

```bash
# Docker の公式インストールスクリプト使用
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 現在のユーザーを docker グループに追加
sudo usermod -aG docker $USER

# Docker の起動と自動起動設定
sudo systemctl start docker
sudo systemctl enable docker
```

### 4. Docker Compose のインストール

```bash
# 最新版の Docker Compose をインストール
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# インストール確認
docker-compose --version
```

### 5. プロジェクトのセットアップ

```bash
# 適切なディレクトリに移動
cd /opt

# プロジェクトをクローン
sudo git clone https://github.com/YOUR_USERNAME/discord_voice_to_text.git
sudo chown -R $USER:$USER discord_voice_to_text
cd discord_voice_to_text

# 環境設定ファイルの作成
cp .env.example .env

# 環境変数を編集
nano .env
```

### 6. 環境変数の設定

`.env` ファイルを編集して以下を設定：

```env
# Discord Bot設定
DISCORD_TOKEN=your_discord_bot_token_here

# LLM設定
LLM_PROVIDER=openai  # openai または gemini
OPENAI_API_KEY=your_openai_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here

# Discord サーバー設定（オプション - 現在未使用）
# GUILD_ID=your_discord_server_id_here

# 録音設定
RECORDING_OUTPUT_DIR=recordings
MAX_RECORDING_AGE_DAYS=7

# ログ設定
LOG_LEVEL=INFO
LOG_FILE=bot.log
```

### 7. アプリケーションのデプロイ

```bash
# デプロイスクリプトに実行権限を付与
chmod +x deploy.sh

# 自動デプロイの実行
./deploy.sh deploy
```

## 🔧 手動セットアップ（Docker を使わない場合）

### 1. Python 3.9+ のインストール

```bash
# Ubuntu/Debian
sudo apt install -y python3 python3-pip python3-venv

# CentOS/RHEL
sudo yum install -y python3 python3-pip

# 確認
python3 --version
```

### 2. uv パッケージマネージャーのインストール

```bash
# uv のインストール
curl -LsSf https://astral.sh/uv/install.sh | sh

# 確認
uv --version
```

### 3. プロジェクトセットアップ

```bash
# プロジェクトディレクトリに移動
cd /opt/discord_voice_to_text

# 依存関係のインストール
uv sync

# 環境設定
cp .env.example .env
nano .env

# Bot の起動
uv run python main.py
```

## 🔄 自動起動設定

### systemd サービスの作成

```bash
# サービスファイルを作成
sudo nano /etc/systemd/system/discord-voice-bot.service
```

#### Docker 版の場合：

```ini
[Unit]
Description=Discord Voice to Text Bot
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/discord_voice_to_text
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0
User=YOUR_USERNAME
Group=YOUR_USERNAME

[Install]
WantedBy=multi-user.target
```

#### Python 直接実行版の場合：

```ini
[Unit]
Description=Discord Voice to Text Bot
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/opt/discord_voice_to_text
Environment=PATH=/home/YOUR_USERNAME/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/home/YOUR_USERNAME/.local/bin/uv run python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### サービスの有効化

```bash
# サービスファイルを再読み込み
sudo systemctl daemon-reload

# サービスを有効化
sudo systemctl enable discord-voice-bot.service

# サービスを開始
sudo systemctl start discord-voice-bot.service

# ステータス確認
sudo systemctl status discord-voice-bot.service
```

## 📊 運用とメンテナンス

### ログの確認

```bash
# Docker版の場合
docker-compose logs -f

# systemd版の場合
sudo journalctl -u discord-voice-bot.service -f

# アプリケーションログ
tail -f /opt/discord_voice_to_text/bot.log
```

### 更新手順

```bash
# プロジェクトディレクトリに移動
cd /opt/discord_voice_to_text

# 最新版を取得
git pull origin main

# Docker版の場合
./deploy.sh update

# Python版の場合
uv sync
sudo systemctl restart discord-voice-bot.service
```

### バックアップ

```bash
# バックアップディレクトリ作成
sudo mkdir -p /opt/backups/discord_voice_to_text

# データのバックアップ
sudo tar -czf /opt/backups/discord_voice_to_text/backup_$(date +%Y%m%d_%H%M%S).tar.gz \
  -C /opt/discord_voice_to_text \
  data/ .env

# 古いバックアップの削除（7日以上古いもの）
sudo find /opt/backups/discord_voice_to_text -name "backup_*.tar.gz" -mtime +7 -delete
```

### ログローテーション設定

```bash
# logrotate 設定ファイルを作成
sudo nano /etc/logrotate.d/discord-voice-bot
```

```
/opt/discord_voice_to_text/bot.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    copytruncate
    su YOUR_USERNAME YOUR_USERNAME
}

/opt/discord_voice_to_text/data/logs/*.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    copytruncate
    su YOUR_USERNAME YOUR_USERNAME
}
```

## 🔐 セキュリティ設定

### ファイアウォール設定

```bash
# UFW の場合（Ubuntu）
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 22/tcp

# firewalld の場合（CentOS/RHEL）
sudo systemctl start firewalld
sudo systemctl enable firewalld
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --reload
```

### ファイル権限の設定

```bash
# 適切な権限を設定
sudo chown -R YOUR_USERNAME:YOUR_USERNAME /opt/discord_voice_to_text
chmod 600 /opt/discord_voice_to_text/.env
chmod 755 /opt/discord_voice_to_text/deploy.sh
```

## 🚨 トラブルシューティング

### よくある問題と解決方法

**1. 特権インテントエラー**
```
PrivilegedIntentsRequired: ... privileged intents that have not been explicitly enabled
```
- Discord Developer Portal → あなたのBot → Bot セクション
- 「Privileged Gateway Intents」で以下を有効化：
  - ✅ `MESSAGE CONTENT INTENT`
  - ✅ `SERVER MEMBERS INTENT`（推奨）
- 「Save Changes」をクリック

**2. Docker が起動しない**
```bash
sudo systemctl status docker
sudo systemctl start docker
```

**2. メモリ不足**
```bash
# スワップファイルの作成
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**3. ディスク容量不足**
```bash
# 不要なファイルの削除
sudo apt autoremove -y
sudo apt autoclean

# Docker の場合
docker system prune -a
```

**4. 音声処理エラー**
```bash
# FFmpeg の再インストール
sudo apt remove ffmpeg
sudo apt install ffmpeg
```

**8. 音声ファイルサイズ制限エラー（25MB超過）**
- OpenAI Whisper APIの制限により25MBを超える音声ファイルは処理できません
- Bot は自動的に音声圧縮を試行します（ビットレート64kbps、16kHzサンプリング）
- 圧縮後も25MBを超える場合：
  ```bash
  # 録音時間を短くする（推奨：1時間以内）
  # または手動で音声を圧縮
  ffmpeg -i input.wav -acodec mp3 -ab 64k -ar 16000 -ac 1 output.mp3
  ```

**5. 権限エラー**
```bash
# Docker グループに追加されているか確認
groups $USER

# 再ログインまたは
newgrp docker
```

**6. LLM API エラー**
```bash
# 使用中のプロバイダーを確認
grep LLM_PROVIDER /opt/discord_voice_to_text/.env

# OpenAI の場合
grep OPENAI_API_KEY /opt/discord_voice_to_text/.env

# Gemini の場合  
grep GEMINI_API_KEY /opt/discord_voice_to_text/.env

# API キーの形式確認
# OpenAI: sk-proj-... または sk-...
# Gemini: AIza...
```

**7. Gemini で音声転写エラー**
- Gemini は現在音声転写をサポートしていません
- 音声転写には OpenAI Whisper が必要です
- 混在設定の場合：
  ```env
  # 音声転写用（必須）
  OPENAI_API_KEY=your_openai_key
  
  # 議事録生成用（Gemini使用）
  LLM_PROVIDER=gemini  
  GEMINI_API_KEY=your_gemini_key
  ```

### ログの確認方法

```bash
# システムログ
sudo journalctl -u discord-voice-bot.service --since="1 hour ago"

# アプリケーションログ
tail -f /opt/discord_voice_to_text/bot.log

# Docker ログ
docker-compose logs --tail=100
```

## 📈 監視設定

### 簡易監視スクリプト

```bash
# 監視スクリプトを作成
nano /opt/discord_voice_to_text/monitor.sh
```

```bash
#!/bin/bash

# Discord Bot 監視スクリプト
LOG_FILE="/var/log/discord-bot-monitor.log"

check_service() {
    if systemctl is-active --quiet discord-voice-bot.service; then
        echo "$(date): Service is running" >> $LOG_FILE
    else
        echo "$(date): Service is down, restarting..." >> $LOG_FILE
        sudo systemctl start discord-voice-bot.service
    fi
}

check_disk_space() {
    DISK_USAGE=$(df /opt/discord_voice_to_text | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ $DISK_USAGE -gt 80 ]; then
        echo "$(date): Disk usage is ${DISK_USAGE}%" >> $LOG_FILE
    fi
}

check_service
check_disk_space
```

```bash
# 実行権限を付与
chmod +x /opt/discord_voice_to_text/monitor.sh

# cron に追加（5分ごとに実行）
echo "*/5 * * * * /opt/discord_voice_to_text/monitor.sh" | sudo crontab -
```

## 🎯 本番運用のベストプラクティス

1. **定期バックアップの設定**
2. **ログローテーションの設定**
3. **リソース監視の導入**
4. **セキュリティアップデートの自動適用**
5. **障害通知の設定**
6. **パフォーマンス最適化**

これで Linux サーバーでの本格運用が可能になります！