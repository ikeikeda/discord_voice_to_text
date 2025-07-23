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
        
    async def start_recording(self, voice_client: discord.VoiceClient) -> None:
        """音声録音を開始"""
        try:
            self.sink = discord.sinks.WaveSink()
            voice_client.start_recording(
                self.sink,
                self._finished_callback,
                *voice_client.channel.members
            )
            logger.info("音声録音を開始しました")
        except Exception as e:
            logger.error(f"録音開始エラー: {e}")
            raise
    
    async def stop_recording(self, voice_client: discord.VoiceClient) -> str:
        """音声録音を停止してファイルを保存"""
        try:
            if not voice_client.is_recording():
                raise ValueError("現在録音していません")
            
            voice_client.stop_recording()
            
            # 録音データが処理されるまで少し待つ
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
        logger.debug("録音コールバックが呼ばれました")
    
    async def _merge_audio_files(self) -> str:
        """複数の音声ファイルを結合して1つのファイルにする"""
        if not self.sink or not self.sink.audio_data:
            raise ValueError("録音データが見つかりません")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"recording_{timestamp}.wav"
        
        try:
            # 最初のユーザーの音声データを基準にする
            combined_audio = None
            
            for user_id, audio_data in self.sink.audio_data.items():
                # バイナリデータからAudioSegmentを作成
                audio_io = io.BytesIO(audio_data.file.getvalue())
                audio_segment = AudioSegment.from_file(audio_io, format="wav")
                
                if combined_audio is None:
                    combined_audio = audio_segment
                else:
                    # 音声を重ね合わせる（ミックス）
                    combined_audio = combined_audio.overlay(audio_segment)
            
            if combined_audio is not None:
                # WAVファイルとして出力
                combined_audio.export(str(output_file), format="wav")
                logger.info(f"音声ファイルを結合しました: {output_file}")
                return str(output_file)
            else:
                raise ValueError("結合する音声データが見つかりません")
                
        except Exception as e:
            logger.error(f"音声ファイル結合エラー: {e}")
            # フォールバック: 最初のユーザーのデータのみ保存
            if self.sink.audio_data:
                first_user_data = list(self.sink.audio_data.values())[0]
                with open(output_file, 'wb') as f:
                    f.write(first_user_data.file.getvalue())
                logger.info(f"フォールバック: 単一ユーザーの音声を保存しました: {output_file}")
                return str(output_file)
            raise
    
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