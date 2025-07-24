import asyncio
import logging
import os
from pathlib import Path
from typing import Optional
from .llm_providers import create_llm_provider, LLMProvider

logger = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, provider: Optional[LLMProvider] = None):
        self.provider = provider or create_llm_provider()
    
    async def transcribe(self, audio_file_path: str, language: str = "ja") -> str:
        """音声ファイルを文字起こし"""
        return await self.provider.transcribe(audio_file_path, language)
    
    async def transcribe_with_timestamps(self, audio_file_path: str, language: str = "ja") -> dict:
        """タイムスタンプ付きで音声ファイルを文字起こし"""
        return await self.provider.transcribe_with_timestamps(audio_file_path, language)
    
    def validate_api_key(self) -> bool:
        """APIキーの有効性をチェック"""
        return self.provider.validate_api_key()
    
    @property
    def provider_name(self) -> str:
        """現在のプロバイダー名を返す"""
        return self.provider.provider_name