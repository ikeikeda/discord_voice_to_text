# 🎙️ Discord Voice-to-Text Bot

Discord の音声データを自動で文字起こしし、AI により議事録を生成する Bot です。

## ✨ 機能

- 🎵 **Discord 音声録音**: ボイスチャンネルでの会話を高品質で録音
- 📝 **AI 文字起こし**: OpenAI Whisper API による正確な文字起こし
- 📋 **議事録自動生成**: GPT-3.5 による構造化された議事録作成
- 🔄 **リアルタイム処理**: 録音停止後すぐに文字起こし・議事録生成
- 🧹 **自動クリーンアップ**: 古い録音ファイルの自動削除
- ⚠️ **エラーハンドリング**: 堅牢なエラー処理とロギング機能

## 🚀 セットアップ

### 1. 前提条件

- Python 3.9+
- [uv](https://github.com/astral-sh/uv) パッケージマネージャー
- Discord Bot Token
- OpenAI API Key
- FFmpeg（音声処理用）

### 2. インストール

```bash
# リポジトリをクローン
git clone https://github.com/your-username/discord_voice_to_text.git
cd discord_voice_to_text

# uv で依存関係をインストール
uv sync

# 開発用依存関係も含める場合
uv sync --extra dev
```

### 3. 環境設定

`.env.example` をコピーして `.env` を作成し、必要な値を設定してください：

```bash
cp .env.example .env
```

`.env` ファイルを編集：

```env
# Discord Bot設定
DISCORD_TOKEN=your_discord_bot_token_here

# OpenAI API設定  
OPENAI_API_KEY=your_openai_api_key_here

# Discord サーバー設定（オプション）
GUILD_ID=your_discord_server_id_here

# 録音設定
RECORDING_OUTPUT_DIR=recordings
MAX_RECORDING_AGE_DAYS=7

# ログ設定
LOG_LEVEL=INFO
LOG_FILE=bot.log
```

### 4. Discord Bot の作成

1. [Discord Developer Portal](https://discord.com/developers/applications) にアクセス
2. 新しいアプリケーションを作成
3. **Bot セクション**でトークンを取得
4. **重要: Privileged Gateway Intents を有効化**
   - ✅ `MESSAGE CONTENT INTENT` - メッセージ内容の読み取り
   - ✅ `SERVER MEMBERS INTENT` - サーバーメンバー情報（推奨）
5. Bot に以下の権限を付与：
   - `Send Messages`
   - `Connect`
   - `Speak` 
   - `Use Voice Activity`

### 5. Bot の招待

生成された招待リンクを使用して、Bot をサーバーに招待してください。

## 📖 使用方法

### コマンド一覧

| コマンド | 説明 |
|---------|------|
| `!record` | 音声録音を開始 |
| `!stop` | 録音停止・文字起こし・議事録生成 |
| `!help` | ヘルプ表示 |
| `!status` | Bot の状態確認 |

### 使用手順

1. **ボイスチャンネルに参加**
2. **`!record` で録音開始**
   ```
   !record
   ```
3. **会話を行う**
4. **`!stop` で録音停止・自動処理**
   ```
   !stop
   ```

Bot が自動的に以下を実行します：
- 📹 録音停止
- 🎵 音声ファイル処理  
- 📝 文字起こし
- 📋 議事録生成
- 💬 Discord チャンネルに結果を投稿

## 🏃 実行

### ローカル環境

```bash
# Bot を起動
uv run python main.py

# または仮想環境を有効化して実行
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows
python main.py
```

### Docker での実行

```bash
# Docker Compose で起動
docker-compose up -d

# ログを確認
docker-compose logs -f

# 停止
docker-compose down
```

### Linux サーバーでの本格運用

Linux サーバーでの本格運用については、[LINUX_SETUP.md](LINUX_SETUP.md) を参照してください。

```bash
# 自動デプロイスクリプト使用
chmod +x deploy.sh
./deploy.sh deploy
```

## 🧪 テスト

```bash
# テストを実行
uv run python -m pytest tests/ -v

# カバレッジ付きでテスト
uv run python -m pytest tests/ --cov=src --cov-report=html
```

## 📁 プロジェクト構造

```
discord_voice_to_text/
├── src/
│   ├── __init__.py
│   ├── voice_recorder.py      # 音声録音機能
│   ├── transcriber.py         # 文字起こし機能  
│   └── minutes_generator.py   # 議事録生成機能
├── tests/
│   ├── test_voice_recorder.py
│   ├── test_transcriber.py
│   └── test_minutes_generator.py
├── main.py                    # Bot のメインファイル
├── pyproject.toml            # 依存関係とプロジェクト設定
├── .env.example              # 環境変数テンプレート
└── README.md
```

## ⚙️ 設定

### 環境変数

| 変数名 | 説明 | デフォルト |
|-------|------|----------|
| `DISCORD_TOKEN` | Discord Bot トークン | - |
| `OPENAI_API_KEY` | OpenAI API キー | - |
| `RECORDING_OUTPUT_DIR` | 録音ファイル保存先 | `recordings` |
| `MAX_RECORDING_AGE_DAYS` | 録音ファイル保持日数 | `7` |
| `LOG_LEVEL` | ログレベル | `INFO` |
| `LOG_FILE` | ログファイル名 | `bot.log` |

## 🤝 コントリビューション

1. Fork このリポジトリ
2. Feature ブランチを作成 (`git checkout -b feature/amazing-feature`)
3. 変更をコミット (`git commit -m 'Add amazing feature'`)
4. ブランチにプッシュ (`git push origin feature/amazing-feature`)
5. Pull Request を作成

## 📄 ライセンス

このプロジェクトは MIT ライセンスの下で公開されています。詳細は [LICENSE](LICENSE) ファイルを参照してください。

## ⚠️ 注意事項

- OpenAI API の使用には料金が発生します
- 長時間の録音は処理時間が長くなる場合があります
- 録音ファイルは設定された日数後に自動削除されます
- Bot には適切な Discord 権限が必要です

## 🆘 トラブルシューティング

### よくある問題

**Bot がボイスチャンネルに接続できない**
- Bot に `Connect` 権限があることを確認
- サーバーの権限設定を確認

**文字起こしでエラーが発生する**
- OpenAI API キーが正しく設定されていることを確認  
- API の使用制限に達していないか確認

**音声ファイルが空**
- マイクの権限設定を確認
- FFmpeg が正しくインストールされていることを確認

詳細なログは `bot.log` ファイルで確認できます。

