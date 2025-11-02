import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
import discord
from pydub import AudioSegment
import io

logger = logging.getLogger(__name__)


class VoiceRecorder:
    def __init__(self, output_dir: str = "recordings"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.sink = None
        self.recording_task = None
        self.recording_finished = False
        
    async def start_recording(self, voice_client: discord.VoiceClient) -> None:
        """音声録音を開始"""
        try:
            if not voice_client or not voice_client.is_connected():
                raise Exception("Not connected to voice channel.")

            if not voice_client.channel:
                raise Exception("Voice client is not connected to any channel.")

            self.sink = discord.sinks.WaveSink()
            self.recording_finished = False

            # 全てのチャンネルメンバーを録音対象に
            members = voice_client.channel.members
            logger.info(f"録音対象メンバー数: {len(members)}")

            # 詳細なログ出力
            for member in members:
                logger.info(f"録音対象: {member.display_name} (ID: {member.id}, Bot: {member.bot})")

            voice_client.start_recording(
                self.sink,
                self._finished_callback,
                *members
            )
            logger.info("音声録音を開始しました")
        except Exception as e:
            logger.error(f"録音開始エラー: {e}")
            raise
    
    async def stop_recording(self, voice_client: discord.VoiceClient) -> str:
        """音声録音を停止してファイルを保存"""
        try:
            # py-cordではis_recording()が存在しないため、録音状態チェックは呼び出し側で行う
            voice_client.stop_recording()
            
            # 録音完了コールバックを待機（最大10秒）
            wait_time = 0
            while not self.recording_finished and wait_time < 10:
                await asyncio.sleep(0.5)
                wait_time += 0.5
            
            if not self.recording_finished:
                logger.warning("録音完了コールバックがタイムアウトしました")
            
            # 追加の待機時間でデータが確実に書き込まれるまで待つ
            await asyncio.sleep(1)
            
            # 録音ファイルを結合して保存
            output_file = await self._merge_audio_files()
            logger.info(f"録音を停止し、ファイルを保存しました: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"録音停止エラー: {e}")
            raise
    
    async def _finished_callback(self, sink: discord.sinks.Sink, channel: discord.abc.Connectable, *args):
        """録音完了時のコールバック"""
        logger.info("録音完了コールバックが呼ばれました")
        logger.info(f"録音データ数: {len(sink.audio_data) if sink.audio_data else 0}")
        self.recording_finished = True
    
    async def _merge_audio_files(self) -> str:
        """複数の音声ファイルをミックスして1つのファイルにする"""
        if not self.sink:
            raise ValueError("録音Sinkが見つかりません")

        if not self.sink.audio_data:
            logger.warning("録音データが空です")
            # 空のファイルを作成する代わりに、エラーを投げる
            raise ValueError("録音データが見つかりません - マイクが有効か確認してください")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"recording_{timestamp}.wav"

        # 音声ミックスモードを環境変数から取得
        merge_mode = os.getenv("AUDIO_MERGE_MODE", "mix").lower()

        try:
            logger.info(f"処理する音声データ: {len(self.sink.audio_data)} ユーザー")

            if merge_mode == "mix" and len(self.sink.audio_data) > 1:
                # 全ユーザーの音声をミックス（推奨）
                return await self._mix_all_audio(output_file)
            else:
                # 最大のユーザーの音声のみを使用（従来の動作）
                return await self._use_largest_audio(output_file)

        except Exception as e:
            logger.error(f"音声ファイル処理エラー: {e}")
            # フォールバック: 最初のユーザーのデータのみ保存
            if self.sink.audio_data:
                first_user_data = list(self.sink.audio_data.values())[0]
                raw_data = first_user_data.file.getvalue()
                logger.info(f"フォールバック処理: {len(raw_data)} バイトの音声データ")

                with open(output_file, 'wb') as f:
                    f.write(raw_data)

                # ファイルサイズ確認
                file_size = output_file.stat().st_size
                logger.info(f"フォールバック保存ファイルサイズ: {file_size} バイト")

                if file_size > 0:
                    logger.info(f"フォールバック: 音声ファイルを保存しました: {output_file}")
                    return str(output_file)
                else:
                    logger.error("フォールバックでも空ファイルが生成されました")
            raise

    async def _mix_all_audio(self, output_file: Path) -> str:
        """全ユーザーの音声をミックスして保存"""
        logger.info("全ユーザーの音声をミックスします...")

        # 全ユーザーの音声を AudioSegment として読み込む
        audio_segments = []
        max_duration = 0

        for user_id, audio_data in self.sink.audio_data.items():
            try:
                raw_audio = audio_data.file.getvalue()
                data_size = len(raw_audio)
                logger.info(f"ユーザー {user_id} の音声データサイズ: {data_size} バイト")

                if data_size == 0:
                    logger.warning(f"ユーザー {user_id} の音声データが空です")
                    continue

                # AudioSegment として読み込み
                audio = AudioSegment.from_file(io.BytesIO(raw_audio), format="wav")
                audio_segments.append((user_id, audio))
                max_duration = max(max_duration, len(audio))
                logger.debug(f"ユーザー {user_id} の音声: {len(audio)}ms")

            except Exception as e:
                logger.error(f"ユーザー {user_id} の音声読み込みエラー: {e}")
                continue

        if not audio_segments:
            raise ValueError("有効な音声データが見つかりません")

        logger.info(f"{len(audio_segments)} ユーザーの音声をミックス中... (最大長: {max_duration}ms)")

        # 無音の基底トラックを作成
        mixed_audio = AudioSegment.silent(duration=max_duration)

        # 各ユーザーの音声を重ねる
        for i, (user_id, audio) in enumerate(audio_segments):
            mixed_audio = mixed_audio.overlay(audio)
            logger.debug(f"音声 {i+1}/{len(audio_segments)} (ユーザー {user_id}) をミックス")

        # ファイルに保存
        mixed_audio.export(str(output_file), format="wav")

        # ファイルサイズを確認
        file_size = output_file.stat().st_size
        logger.info(f"ミックスされた音声ファイルサイズ: {file_size} バイト")

        if file_size == 0:
            raise ValueError("保存された音声ファイルが空です")

        logger.info(f"音声ファイルをミックスして保存しました: {output_file}")
        return str(output_file)

    async def _use_largest_audio(self, output_file: Path) -> str:
        """最大の音声データを持つユーザーの音声のみを使用"""
        logger.info("最大の音声データを持つユーザーの音声を使用します...")

        # 最大の音声データを持つユーザーを選択
        largest_user_id = None
        largest_size = 0

        for user_id, audio_data in self.sink.audio_data.items():
            data_size = len(audio_data.file.getvalue())
            logger.info(f"ユーザー {user_id} の音声データサイズ: {data_size} バイト")

            if data_size > largest_size:
                largest_size = data_size
                largest_user_id = user_id

        if largest_user_id is None or largest_size == 0:
            raise ValueError("有効な音声データが見つかりません")

        # 最大のデータを持つユーザーの音声を保存
        logger.info(f"ユーザー {largest_user_id} の音声データを使用 ({largest_size} バイト)")

        audio_data = self.sink.audio_data[largest_user_id]
        raw_audio = audio_data.file.getvalue()

        # 直接WAVファイルとして保存
        with open(output_file, 'wb') as f:
            f.write(raw_audio)

        # ファイルサイズを確認
        file_size = output_file.stat().st_size
        logger.info(f"保存された音声ファイルサイズ: {file_size} バイト")

        if file_size == 0:
            raise ValueError("保存された音声ファイルが空です")

        logger.info(f"音声ファイルを保存しました: {output_file}")
        return str(output_file)
    
    def cleanup_old_recordings(self, max_age_days: int = 7) -> None:
        """古い録音ファイルを削除"""
        try:
            current_time = datetime.now()
            for file_path in self.output_dir.glob("recording_*.wav"):
                file_age = current_time - datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_age.days > max_age_days:
                    file_path.unlink()
                    logger.info(f"古い録音ファイルを削除しました: {file_path}")
        except Exception as e:
            logger.error(f"録音ファイルクリーンアップエラー: {e}")