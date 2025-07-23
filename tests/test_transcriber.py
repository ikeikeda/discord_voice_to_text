import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
import tempfile
import os

from src.transcriber import Transcriber


@pytest.fixture
def transcriber():
    """テスト用のTranscriberインスタンス"""
    return Transcriber(api_key="test_key_1234567890")


@pytest.fixture
def temp_audio_file():
    """テスト用の一時音声ファイル"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(b"fake_audio_data")
        temp_path = f.name
    
    yield temp_path
    
    # クリーンアップ
    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestTranscriber:
    def test_init_with_api_key(self):
        """APIキーを指定してのインスタンス作成"""
        transcriber = Transcriber(api_key="test_key")
        assert transcriber.client.api_key == "test_key"
    
    def test_init_without_api_key_raises_error(self):
        """APIキーなしでのインスタンス作成はエラー"""
        from openai import OpenAIError
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(OpenAIError):
                Transcriber()
    
    def test_validate_api_key(self, transcriber):
        """APIキー検証"""
        assert transcriber.validate_api_key() is True
        
        # 短いキーの場合
        transcriber.client.api_key = "short"
        assert transcriber.validate_api_key() is False
    
    @pytest.mark.asyncio
    async def test_transcribe_success(self, transcriber, temp_audio_file):
        """文字起こし成功ケース"""
        mock_response = "これはテストの文字起こし結果です。"
        
        with patch.object(transcriber.client.audio.transcriptions, 'create', 
                         new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            
            result = await transcriber.transcribe(temp_audio_file)
            
            assert result == mock_response
            mock_create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_transcribe_file_not_found(self, transcriber):
        """存在しないファイルでの文字起こし"""
        result = await transcriber.transcribe("non_existent_file.wav")
        assert "音声ファイルが見つかりませんでした" in result
    
    @pytest.mark.asyncio
    async def test_transcribe_openai_error(self, transcriber, temp_audio_file):
        """OpenAI APIエラー"""
        from openai import OpenAIError
        
        with patch.object(transcriber.client.audio.transcriptions, 'create',
                         new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = OpenAIError("API Error")
            
            result = await transcriber.transcribe(temp_audio_file)
            
            assert "音声の文字起こしでAPIエラーが発生しました" in result
    
    @pytest.mark.asyncio
    async def test_transcribe_with_timestamps_success(self, transcriber, temp_audio_file):
        """タイムスタンプ付き文字起こし成功"""
        mock_response = Mock()
        mock_response.text = "テスト文字起こし"
        mock_response.segments = [{"start": 0.0, "end": 5.0, "text": "テスト"}]
        mock_response.language = "ja"
        mock_response.duration = 10.0
        
        with patch.object(transcriber.client.audio.transcriptions, 'create',
                         new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            
            result = await transcriber.transcribe_with_timestamps(temp_audio_file)
            
            assert result["text"] == "テスト文字起こし"
            assert result["language"] == "ja"
            assert result["duration"] == 10.0
            assert len(result["segments"]) == 1
    
    @pytest.mark.asyncio
    async def test_transcribe_empty_result(self, transcriber, temp_audio_file):
        """空の文字起こし結果"""
        with patch.object(transcriber.client.audio.transcriptions, 'create',
                         new_callable=AsyncMock) as mock_create:
            mock_create.return_value = ""
            
            result = await transcriber.transcribe(temp_audio_file)
            
            assert result == "音声の文字起こしに失敗しました。"