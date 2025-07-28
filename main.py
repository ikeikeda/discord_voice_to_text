import discord
from discord.ext import commands
import os
import logging
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from src.voice_recorder import VoiceRecorder
from src.transcriber import Transcriber
from src.minutes_generator import MinutesGenerator
from src.llm_providers import create_llm_provider

load_dotenv()

# ログ設定の改善
log_level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper())
log_file = os.getenv('LOG_FILE', 'bot.log')

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Discord Intents設定
intents = discord.Intents.default()
intents.message_content = True    # MESSAGE CONTENT INTENT (特権インテント)
intents.voice_states = True       # 音声状態の監視用
intents.guilds = True            # サーバー情報の取得

bot = commands.Bot(command_prefix='!', intents=intents)

# 設定値を環境変数から取得
recording_dir = os.getenv('RECORDING_OUTPUT_DIR', 'recordings')
max_age_days = int(os.getenv('MAX_RECORDING_AGE_DAYS', '7'))

# LLMプロバイダーを初期化
transcription_provider = create_llm_provider('openai')  # 音声転写は常にOpenAI Whisperを使用
minutes_provider = create_llm_provider()  # 議事録生成は設定されたプロバイダーを使用

# インスタンス初期化
voice_recorder = VoiceRecorder(recording_dir)
transcriber = Transcriber(transcription_provider)
minutes_generator = MinutesGenerator(minutes_provider)

# 録音状態管理
recording_status = {}

@bot.event
async def on_ready():
    logger.info(f'{bot.user} がログインしました')
    logger.info(f'Guild: {len(bot.guilds)}')
    
    # API キーの検証
    if not transcriber.validate_api_key():
        logger.error(f'{transcriber.provider_name} APIキーが無効です')
    if not minutes_generator.validate_api_key():
        logger.error(f'議事録生成用の{minutes_generator.provider_name} APIキーが無効です')
    
    logger.info(f'文字起こし用プロバイダー: {transcription_provider.provider_name}')
    logger.info(f'議事録生成用プロバイダー: {minutes_provider.provider_name}')
    
    # 古い録音ファイルをクリーンアップ
    try:
        voice_recorder.cleanup_old_recordings(max_age_days)
        logger.info('古い録音ファイルのクリーンアップ完了')
    except Exception as e:
        logger.warning(f'録音ファイルクリーンアップ中にエラー: {e}')

@bot.command(name='record')
async def start_recording(ctx):
    """音声録音を開始"""
    if ctx.author.voice is None:
        await ctx.send('ボイスチャンネルに参加してからコマンドを実行してください。')
        return
    
    # 既に録音中かチェック
    guild_id = ctx.guild.id
    if recording_status.get(guild_id, False):
        await ctx.send('既に録音中です。`!stop`で停止してから新しい録音を開始してください。')
        return
    
    channel = ctx.author.voice.channel
    try:
        if ctx.voice_client:
            # 既に接続している場合は移動
            await ctx.voice_client.move_to(channel)
            vc = ctx.voice_client
        else:
            # 新規接続
            vc = await channel.connect()
        
        # 接続の安定を待つ
        await asyncio.sleep(1)
        
        await voice_recorder.start_recording(vc)
        recording_status[guild_id] = True  # 録音状態を記録
        await ctx.send(f'🎙️ {channel.name}で録音を開始しました。\n`!stop`で録音を停止できます。')
        logger.info(f'録音開始: {channel.name} (ユーザー: {ctx.author.display_name})')
        
    except discord.ClientException as e:
        logger.error(f'Discord接続エラー: {e}')
        await ctx.send('ボイスチャンネルへの接続に失敗しました。Bot に適切な権限があることを確認してください。')
    except Exception as e:
        logger.error(f'録音開始エラー: {e}')
        recording_status[guild_id] = False  # エラー時は録音状態をリセット
        await ctx.send('録音の開始に失敗しました。もう一度お試しください。')
        # ボイス接続をクリーンアップ
        if ctx.voice_client:
            try:
                await ctx.voice_client.disconnect()
            except:
                pass

@bot.command(name='stop')
async def stop_recording(ctx):
    """音声録音を停止して文字起こし開始"""
    guild_id = ctx.guild.id
    
    if not ctx.voice_client:
        await ctx.send('現在録音していません。`!record`で録音を開始してください。')
        return
        
    if not recording_status.get(guild_id, False):
        await ctx.send('録音が開始されていません。`!record`で録音を開始してください。')
        return
    
    processing_msg = await ctx.send('🛑 録音を停止中...')
    
    try:
        # 録音停止
        audio_file = await voice_recorder.stop_recording(ctx.voice_client)
        recording_status[guild_id] = False  # 録音状態をリセット
        await ctx.voice_client.disconnect()
        
        await processing_msg.edit(content='🎵 音声ファイルを処理中...')
        
        # ファイルサイズチェック
        file_path = Path(audio_file)
        if not file_path.exists() or file_path.stat().st_size == 0:
            await processing_msg.edit(content='❌ 録音されたファイルが空または見つかりません。')
            return
        
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        logger.info(f'音声ファイルサイズ: {file_size_mb:.2f}MB')
        
        # 文字起こし
        await processing_msg.edit(content='📝 音声を文字起こししています...')
        transcription = await transcriber.transcribe(audio_file)
        
        if transcription.startswith('音声の文字起こしで'):
            await processing_msg.edit(content=f'❌ 文字起こしに失敗しました: {transcription}')
            return
        
        # 議事録生成
        await processing_msg.edit(content='📄 議事録を生成しています...')
        minutes = await minutes_generator.generate(transcription)
        
        # 結果送信
        if len(minutes) > 1900:
            # 長い場合は分割して送信
            chunks = [minutes[i:i+1900] for i in range(0, len(minutes), 1900)]
            await processing_msg.edit(content='✅ 処理完了！議事録を送信します...')
            for i, chunk in enumerate(chunks, 1):
                await ctx.send(f'```\n議事録 ({i}/{len(chunks)})\n\n{chunk}\n```')
        else:
            await processing_msg.edit(content='✅ 処理完了！')
            await ctx.send(f'```\n{minutes}\n```')
        
        # ファイル情報をログに記録
        logger.info(f'処理完了 - ファイル: {audio_file}, 文字数: {len(transcription)}, 議事録文字数: {len(minutes)}')
        
    except asyncio.TimeoutError:
        await processing_msg.edit(content='❌ 処理がタイムアウトしました。もう一度お試しください。')
        logger.error('処理タイムアウト')
    except Exception as e:
        recording_status[guild_id] = False  # エラー時も録音状態をリセット
        await processing_msg.edit(content='❌ 処理中にエラーが発生しました。')
        logger.error(f'処理エラー: {e}', exc_info=True)
    finally:
        # ボイス接続のクリーンアップ
        if ctx.voice_client:
            try:
                await ctx.voice_client.disconnect()
            except:
                pass

@bot.command(name='both')
async def stop_recording_both(ctx):
    """音声録音を停止して文字起こしと議事録の両方を生成"""
    guild_id = ctx.guild.id
    
    if not ctx.voice_client:
        await ctx.send('現在録音していません。`!record`で録音を開始してください。')
        return
        
    if not recording_status.get(guild_id, False):
        await ctx.send('録音が開始されていません。`!record`で録音を開始してください。')
        return
    
    processing_msg = await ctx.send('🛑 録音を停止中...')
    
    try:
        # 録音停止
        audio_file = await voice_recorder.stop_recording(ctx.voice_client)
        recording_status[guild_id] = False  # 録音状態をリセット
        await ctx.voice_client.disconnect()
        
        await processing_msg.edit(content='🎵 音声ファイルを処理中...')
        
        # ファイルサイズチェック
        file_path = Path(audio_file)
        if not file_path.exists() or file_path.stat().st_size == 0:
            await processing_msg.edit(content='❌ 録音されたファイルが空または見つかりません。')
            return
        
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        logger.info(f'音声ファイルサイズ: {file_size_mb:.2f}MB')
        
        # 文字起こし
        await processing_msg.edit(content='📝 音声を文字起こししています...')
        transcription = await transcriber.transcribe(audio_file)
        
        if transcription.startswith('音声の文字起こしで'):
            await processing_msg.edit(content=f'❌ 文字起こしに失敗しました: {transcription}')
            return
        
        # 議事録生成
        await processing_msg.edit(content='📄 議事録を生成しています...')
        minutes = await minutes_generator.generate(transcription)
        
        # 文字起こし結果を送信
        await processing_msg.edit(content='✅ 処理完了！文字起こし結果と議事録を送信します...')
        
        # 文字起こし結果の送信
        if len(transcription) > 1900:
            chunks = [transcription[i:i+1900] for i in range(0, len(transcription), 1900)]
            for i, chunk in enumerate(chunks, 1):
                await ctx.send(f'```\n文字起こし結果 ({i}/{len(chunks)})\n\n{chunk}\n```')
        else:
            await ctx.send(f'```\n文字起こし結果\n\n{transcription}\n```')
        
        # 議事録の送信
        if len(minutes) > 1900:
            chunks = [minutes[i:i+1900] for i in range(0, len(minutes), 1900)]
            for i, chunk in enumerate(chunks, 1):
                await ctx.send(f'```\n議事録 ({i}/{len(chunks)})\n\n{chunk}\n```')
        else:
            await ctx.send(f'```\n議事録\n\n{minutes}\n```')
        
        # ファイル情報をログに記録
        logger.info(f'処理完了 - ファイル: {audio_file}, 文字数: {len(transcription)}, 議事録文字数: {len(minutes)}')
        
    except asyncio.TimeoutError:
        await processing_msg.edit(content='❌ 処理がタイムアウトしました。もう一度お試しください。')
        logger.error('処理タイムアウト')
    except Exception as e:
        recording_status[guild_id] = False  # エラー時も録音状態をリセット
        await processing_msg.edit(content='❌ 処理中にエラーが発生しました。')
        logger.error(f'処理エラー: {e}', exc_info=True)
    finally:
        # ボイス接続のクリーンアップ
        if ctx.voice_client:
            try:
                await ctx.voice_client.disconnect()
            except:
                pass

@bot.command(name='bothelp')
async def help_command(ctx):
    """ヘルプ表示"""
    embed = discord.Embed(
        title="🎙️ Discord音声文字起こしBot",
        description="音声を自動で文字起こしして議事録を生成します",
        color=0x00ff00
    )
    
    embed.add_field(
        name="📋 コマンド一覧",
        value="""
        🎬 `!record` - 音声録音を開始
        ⏹️ `!stop` - 録音停止・議事録生成
        📄 `!both` - 録音停止・文字起こしと議事録の両方を取得
        ❓ `!bothelp` - このヘルプを表示
        🔧 `!status` - Bot の状態を確認
        """,
        inline=False
    )
    
    embed.add_field(
        name="📖 使用方法",
        value="""
        1️⃣ ボイスチャンネルに参加
        2️⃣ `!record`で録音開始
        3️⃣ 会話を行う
        4️⃣ `!stop`で議事録のみ または `!both`で文字起こし+議事録の両方
        """,
        inline=False
    )
    
    embed.add_field(
        name="⚠️ 注意事項",
        value="• OpenAI APIキーが必要です\n• 長時間の録音は処理時間が長くなります\n• ファイルは自動削除されます",
        inline=False
    )
    
    embed.set_footer(text=f"Discord Voice-to-Text Bot | Transcription: {transcription_provider.provider_name} | Minutes: {minutes_provider.provider_name}")
    await ctx.send(embed=embed)

@bot.command(name='status')
async def status_command(ctx):
    """Bot の状態確認"""
    embed = discord.Embed(
        title="🔧 Bot ステータス",
        color=0x0099ff
    )
    
    # API キー状態
    transcriber_status = "✅ 正常" if transcriber.validate_api_key() else "❌ エラー"
    minutes_status = "✅ 正常" if minutes_generator.validate_api_key() else "❌ エラー"
    
    embed.add_field(name=f"文字起こし ({transcriber.provider_name})", value=transcriber_status, inline=True)
    embed.add_field(name=f"議事録生成 ({minutes_generator.provider_name})", value=minutes_status, inline=True)
    
    # 録音状態
    guild_id = ctx.guild.id
    current_recording_status = "🎙️ 録音中" if recording_status.get(guild_id, False) else "⏹️ 停止中"
    embed.add_field(name="録音状態", value=current_recording_status, inline=True)
    
    # サーバー情報
    embed.add_field(name="接続サーバー数", value=f"{len(bot.guilds)}", inline=True)
    
    if ctx.voice_client:
        embed.add_field(name="現在のチャンネル", value=ctx.voice_client.channel.name, inline=True)
    
    await ctx.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    """コマンドエラーハンドリング"""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send('❌ コマンドが見つかりません。`!help`でコマンド一覧を確認してください。')
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send('❌ 必要な引数が不足しています。`!help`で使用方法を確認してください。')
    else:
        logger.error(f'コマンドエラー: {error}', exc_info=True)
        await ctx.send('❌ コマンド実行中にエラーが発生しました。')

@bot.event
async def on_voice_state_update(member, before, after):
    """ボイスチャンネルの状態変更を監視"""
    # Bot が一人になったら自動切断
    if member.bot:
        return
    
    voice_client = member.guild.voice_client
    if voice_client and voice_client.channel:
        # Bot 以外のメンバーが残っているかチェック
        human_members = [m for m in voice_client.channel.members if not m.bot]
        if len(human_members) == 0:
            guild_id = member.guild.id
            recording_status[guild_id] = False  # チャンネルが空になったら録音状態をリセット
            logger.info(f'チャンネルが空になったため自動切断: {voice_client.channel.name}')
            await voice_client.disconnect()

if __name__ == '__main__':
    # 起動前チェック
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error('DISCORD_TOKENが設定されていません。.envファイルを確認してください。')
        sys.exit(1)
    
    # 必要なAPIキーをチェック
    # 文字起こしは常にOpenAI Whisperを使用するため、OPENAI_API_KEYは必須
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        logger.error('OPENAI_API_KEYが設定されていません。音声転写に必要です。.envファイルを確認してください。')
        sys.exit(1)
    
    # 議事録生成でGeminiを使用する場合はGEMINI_API_KEYも必要
    llm_provider_name = os.getenv('LLM_PROVIDER', 'openai').lower()
    if llm_provider_name == 'gemini':
        gemini_key = os.getenv('GEMINI_API_KEY')
        if not gemini_key:
            logger.error('GEMINI_API_KEYが設定されていません。議事録生成にGeminiを使用する場合は必要です。.envファイルを確認してください。')
            sys.exit(1)
    
    logger.info('Discord Voice-to-Text Bot を起動しています...')
    
    try:
        bot.run(token)
    except discord.LoginFailure:
        logger.error('Discord Token が無効です')
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info('Bot を停止しています...')
        sys.exit(0)
    except Exception as e:
        logger.error(f'予期しないエラーが発生しました: {e}', exc_info=True)
        sys.exit(1)