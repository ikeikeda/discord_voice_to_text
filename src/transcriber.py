import asyncio
import logging
import os
from pathlib import Path
from typing import Optional
from .llm_providers import create_llm_provider, LLMProvider
from .text_postprocessor import TextPostProcessor

logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, provider: Optional[LLMProvider] = None):
        self.provider = provider or create_llm_provider()
        self.postprocessor = TextPostProcessor(self.provider)
        
        # 後処理の有効/無効設定
        self.enable_postprocessing = os.getenv("ENABLE_TEXT_POSTPROCESSING", "true").lower() == "true"
        self.enable_ai_correction = os.getenv("ENABLE_AI_CORRECTION", "false").lower() == "true"

    async def transcribe(
        self, audio_file_path: str, language: str = "ja", guild_id: int = None
    ) -> str:
        """音声ファイルを文字起こし"""
        # 基本的な文字起こし
        raw_text = await self.provider.transcribe(audio_file_path, language, guild_id)
        
        # 後処理の適用
        if self.enable_postprocessing and not raw_text.startswith("音声の文字起こしで"):
            try:
                processed_text = await self.postprocessor.process_transcription(
                    raw_text, guild_id, self.enable_ai_correction
                )
                
                # 統計情報をログに記録
                stats = self.postprocessor.get_text_statistics(raw_text, processed_text)
                logger.info(f"後処理統計: 元文字数={stats['original_length']}, "
                           f"処理後文字数={stats['processed_length']}, "
                           f"改善率={stats['improvement_ratio']:.2f}")
                
                return processed_text
            except Exception as e:
                logger.error(f"後処理中にエラーが発生: {e}")
                return raw_text
        
        return raw_text

    async def transcribe_with_timestamps(
        self, audio_file_path: str, language: str = "ja", guild_id: int = None
    ) -> dict:
        """タイムスタンプ付きで音声ファイルを文字起こし"""
        return await self.provider.transcribe_with_timestamps(
            audio_file_path, language, guild_id
        )

    def validate_api_key(self) -> bool:
        """APIキーの有効性をチェック"""
        return self.provider.validate_api_key()

    @property
    def provider_name(self) -> str:
        """現在のプロバイダー名を返す"""
        return self.provider.provider_name
