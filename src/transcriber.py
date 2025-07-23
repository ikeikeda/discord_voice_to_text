import asyncio
import logging
import os
from pathlib import Path
from typing import Optional
import openai
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, api_key: Optional[str] = None):
        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv('OPENAI_API_KEY')
        )
        if not self.client.api_key:
            raise ValueError("OpenAI APIキーが設定されていません")
    
    async def transcribe(self, audio_file_path: str, language: str = "ja") -> str:
        """音声ファイルを文字起こし"""
        try:
            audio_file = Path(audio_file_path)
            if not audio_file.exists():
                raise FileNotFoundError(f"音声ファイルが見つかりません: {audio_file_path}")
            
            logger.info(f"音声ファイルを文字起こししています: {audio_file_path}")
            
            with open(audio_file, "rb") as file:
                transcription = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=file,
                    language=language,
                    response_format="text",
                    prompt="これはDiscordでの会話です。正確な文字起こしをお願いします。"
                )
            
            # OpenAI APIの応答処理
            if isinstance(transcription, str):
                result = transcription.strip()
            else:
                # APIのレスポンス形式が変わった場合の対応
                result = str(transcription).strip()
            
            if not result:
                logger.warning("文字起こし結果が空でした")
                return "音声の文字起こしに失敗しました。"
            
            logger.info(f"文字起こし完了。文字数: {len(result)}")
            return result
            
        except openai.OpenAIError as e:
            logger.error(f"OpenAI API エラー: {e}")
            return f"音声の文字起こしでAPIエラーが発生しました: {str(e)}"
        except FileNotFoundError as e:
            logger.error(f"ファイルエラー: {e}")
            return "音声ファイルが見つかりませんでした。"
        except Exception as e:
            logger.error(f"文字起こしエラー: {e}")
            return f"音声の文字起こし中に予期しないエラーが発生しました: {str(e)}"
    
    async def transcribe_with_timestamps(self, audio_file_path: str, language: str = "ja") -> dict:
        """タイムスタンプ付きで音声ファイルを文字起こし"""
        try:
            audio_file = Path(audio_file_path)
            if not audio_file.exists():
                raise FileNotFoundError(f"音声ファイルが見つかりません: {audio_file_path}")
            
            logger.info(f"タイムスタンプ付き文字起こしを実行中: {audio_file_path}")
            
            with open(audio_file, "rb") as file:
                transcription = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=file,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                    prompt="これはDiscordでの会話です。正確な文字起こしをお願いします。"
                )
            
            logger.info("タイムスタンプ付き文字起こし完了")
            return {
                "text": transcription.text,
                "segments": transcription.segments if hasattr(transcription, 'segments') else [],
                "language": transcription.language if hasattr(transcription, 'language') else language,
                "duration": transcription.duration if hasattr(transcription, 'duration') else 0
            }
            
        except openai.OpenAIError as e:
            logger.error(f"OpenAI API エラー: {e}")
            return {
                "text": f"音声の文字起こしでAPIエラーが発生しました: {str(e)}",
                "segments": [],
                "language": language,
                "duration": 0
            }
        except Exception as e:
            logger.error(f"タイムスタンプ付き文字起こしエラー: {e}")
            return {
                "text": f"音声の文字起こし中に予期しないエラーが発生しました: {str(e)}",
                "segments": [],
                "language": language,
                "duration": 0
            }
    
    def validate_api_key(self) -> bool:
        """APIキーの有効性をチェック"""
        try:
            return bool(self.client.api_key and len(self.client.api_key) > 10)
        except Exception:
            return False