import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import tempfile
import os

from src.llm_providers import OpenAIProvider, GeminiProvider, create_llm_provider


class TestOpenAIProvider:
    def test_init_with_api_key(self):
        """APIキーを指定してのインスタンス作成"""
        provider = OpenAIProvider(api_key="test_key")
        assert provider.api_key == "test_key"
        assert provider.provider_name == "OpenAI"
    
    def test_init_without_api_key_raises_error(self):
        """APIキーなしでのインスタンス作成はエラー"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="OpenAI APIキーが設定されていません"):
                OpenAIProvider()
    
    def test_validate_api_key(self):
        """APIキー検証"""
        provider = OpenAIProvider(api_key="test_key_1234567890")
        assert provider.validate_api_key() is True
        
        # 短いキーの場合
        provider.api_key = "short"
        provider.client.api_key = "short"
        assert provider.validate_api_key() is False
    
    @pytest.mark.asyncio
    async def test_transcribe_success(self):
        """文字起こし成功ケース"""
        provider = OpenAIProvider(api_key="test_key_1234567890")
        
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"fake_audio_data")
            temp_path = f.name
        
        try:
            with patch.object(provider.client.audio.transcriptions, 'create',
                             new_callable=AsyncMock) as mock_create:
                mock_create.return_value = "テスト文字起こし結果"
                
                result = await provider.transcribe(temp_path)
                
                assert result == "テスト文字起こし結果"
                mock_create.assert_called_once()
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_generate_chat_completion_success(self):
        """チャット生成成功ケース"""
        provider = OpenAIProvider(api_key="test_key_1234567890")
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "生成されたテキスト"
        
        with patch.object(provider.client.chat.completions, 'create',
                         new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            
            messages = [{"role": "user", "content": "テストメッセージ"}]
            result = await provider.generate_chat_completion(messages)
            
            assert result == "生成されたテキスト"
            mock_create.assert_called_once()


class TestGeminiProvider:
    def test_init_with_api_key(self):
        """APIキーを指定してのインスタンス作成"""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                provider = GeminiProvider(api_key="test_key")
                assert provider.api_key == "test_key"
                assert provider.provider_name == "Gemini"
    
    def test_init_without_api_key_raises_error(self):
        """APIキーなしでのインスタンス作成はエラー"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Gemini APIキーが設定されていません"):
                GeminiProvider()
    
    def test_init_missing_library_raises_error(self):
        """google-generativeaiライブラリなしでのインスタンス作成はエラー"""
        with patch('builtins.__import__', side_effect=ImportError):
            with pytest.raises(ImportError, match="google-generativeai ライブラリがインストールされていません"):
                GeminiProvider(api_key="test_key")
    
    @pytest.mark.asyncio
    async def test_transcribe_not_supported(self):
        """音声転写は未サポート"""
        with patch('google.generativeai.configure'):
            with patch('google.generativeai.GenerativeModel'):
                provider = GeminiProvider(api_key="test_key")
                
                result = await provider.transcribe("dummy_path")
                
                assert "Gemini プロバイダーでは音声転写は現在サポートされていません" in result
    
    @pytest.mark.asyncio
    async def test_generate_text_success(self):
        """テキスト生成成功ケース"""
        with patch('google.generativeai.configure'):
            mock_model = Mock()
            mock_response = Mock()
            mock_response.text = "生成されたテキスト"
            mock_model.generate_content = Mock(return_value=mock_response)
            
            with patch('google.generativeai.GenerativeModel', return_value=mock_model):
                provider = GeminiProvider(api_key="test_key")
                
                with patch('asyncio.get_event_loop') as mock_loop:
                    mock_executor = AsyncMock(return_value=mock_response)
                    mock_loop.return_value.run_in_executor = mock_executor
                    
                    result = await provider.generate_text("テストプロンプト")
                    
                    assert result == "生成されたテキスト"


class TestCreateLLMProvider:
    def test_create_openai_provider(self):
        """OpenAIプロバイダーの作成"""
        with patch.dict(os.environ, {'LLM_PROVIDER': 'openai', 'OPENAI_API_KEY': 'test_key'}):
            provider = create_llm_provider()
            assert isinstance(provider, OpenAIProvider)
    
    def test_create_gemini_provider(self):
        """Geminiプロバイダーの作成"""
        with patch.dict(os.environ, {'LLM_PROVIDER': 'gemini', 'GEMINI_API_KEY': 'test_key'}):
            with patch('google.generativeai.configure'):
                with patch('google.generativeai.GenerativeModel'):
                    provider = create_llm_provider()
                    assert isinstance(provider, GeminiProvider)
    
    def test_create_unsupported_provider_raises_error(self):
        """サポートされていないプロバイダーでエラー"""
        with pytest.raises(ValueError, match="サポートされていないLLMプロバイダー"):
            create_llm_provider("unsupported")
    
    def test_default_provider_is_openai(self):
        """デフォルトプロバイダーはOpenAI"""
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test_key'}, clear=True):
            provider = create_llm_provider()
            assert isinstance(provider, OpenAIProvider)