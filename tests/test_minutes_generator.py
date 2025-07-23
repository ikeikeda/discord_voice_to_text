import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import os

from src.minutes_generator import MinutesGenerator


@pytest.fixture
def minutes_generator():
    """テスト用のMinutesGeneratorインスタンス"""
    return MinutesGenerator(api_key="test_key_1234567890")


@pytest.fixture
def sample_transcription():
    """テスト用の文字起こしデータ"""
    return """
    こんにちは、今日のミーティングを開始します。
    まず、プロジェクトの進捗について確認しましょう。
    次に、来週の計画を立てる必要があります。
    山田さんは来週までにドキュメントを作成してください。
    佐藤さんはテストの準備をお願いします。
    それでは、今日のミーティングを終了します。
    """


class TestMinutesGenerator:
    def test_init_with_api_key(self):
        """APIキーを指定してのインスタンス作成"""
        generator = MinutesGenerator(api_key="test_key")
        assert generator.client.api_key == "test_key"
    
    def test_init_without_api_key_raises_error(self):
        """APIキーなしでのインスタンス作成はエラー"""
        from openai import OpenAIError
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(OpenAIError):
                MinutesGenerator()
    
    def test_validate_api_key(self, minutes_generator):
        """APIキー検証"""
        assert minutes_generator.validate_api_key() is True
        
        # 短いキーの場合
        minutes_generator.client.api_key = "short"
        assert minutes_generator.validate_api_key() is False
    
    @pytest.mark.asyncio
    async def test_generate_success(self, minutes_generator, sample_transcription):
        """議事録生成成功ケース"""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "生成された議事録の内容です。"
        
        with patch.object(minutes_generator.client.chat.completions, 'create',
                         new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            
            result = await minutes_generator.generate(sample_transcription)
            
            assert result == "生成された議事録の内容です。"
            mock_create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_empty_transcription(self, minutes_generator):
        """空の文字起こしデータ"""
        result = await minutes_generator.generate("")
        assert "文字起こしデータが空のため" in result
        
        result2 = await minutes_generator.generate("   ")
        assert "文字起こしデータが空のため" in result2
    
    @pytest.mark.asyncio
    async def test_generate_openai_error(self, minutes_generator, sample_transcription):
        """OpenAI APIエラー"""
        from openai import OpenAIError
        
        with patch.object(minutes_generator.client.chat.completions, 'create',
                         new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = OpenAIError("API Error")
            
            result = await minutes_generator.generate(sample_transcription)
            
            assert "議事録生成でAPIエラーが発生しました" in result
    
    @pytest.mark.asyncio
    async def test_generate_detailed_success(self, minutes_generator, sample_transcription):
        """詳細議事録生成成功ケース"""
        # 各API呼び出しのモックレスポンス
        mock_responses = [
            "プロジェクトの進捗確認と来週の計画立てについて議論しました。",  # summary
            "• 山田さん：来週までにドキュメント作成\n• 佐藤さん：テスト準備",  # action_items
            "• プロジェクト進捗の確認\n• 来週の計画立案",  # key_points
            "• 来週の計画を立てることに決定"  # decisions
        ]
        
        async def mock_create_side_effect(*args, **kwargs):
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = mock_responses.pop(0)
            return mock_response
        
        with patch.object(minutes_generator.client.chat.completions, 'create',
                         new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = mock_create_side_effect
            
            result = await minutes_generator.generate_detailed(sample_transcription)
            
            assert "full_minutes" in result
            assert "summary" in result
            assert "action_items" in result
            assert "key_points" in result
            assert "decisions" in result
            
            assert "プロジェクトの進捗確認" in result["summary"]
            assert "山田さん：来週までにドキュメント作成" in result["action_items"]
    
    def test_create_minutes_prompt(self, minutes_generator):
        """議事録プロンプト作成"""
        transcription = "テスト会話内容"
        title = "テスト会議"
        
        prompt = minutes_generator._create_minutes_prompt(transcription, title)
        
        assert title in prompt
        assert transcription in prompt
        assert "議事録:" in prompt
    
    def test_format_detailed_minutes(self, minutes_generator):
        """詳細議事録フォーマット"""
        title = "テスト会議"
        summary = "要約内容"
        key_points = "重要ポイント"
        decisions = "決定事項"
        action_items = "アクションアイテム"
        
        result = minutes_generator._format_detailed_minutes(
            title, summary, key_points, decisions, action_items
        )
        
        assert title in result
        assert summary in result
        assert key_points in result
        assert decisions in result
        assert action_items in result
        assert "## 会議要約" in result
    
    def test_empty_minutes_response(self, minutes_generator):
        """空の議事録レスポンス"""
        error_msg = "テストエラー"
        result = minutes_generator._empty_minutes_response(error_msg)
        
        assert result["full_minutes"] == f"議事録の生成に失敗しました: {error_msg}"
        assert result["summary"] == error_msg
        assert all("抽出できませんでした" in value for key, value in result.items() 
                  if key not in ["full_minutes", "summary"])
    
    @pytest.mark.asyncio
    async def test_generate_empty_response(self, minutes_generator, sample_transcription):
        """空のAPIレスポンス"""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = ""
        
        with patch.object(minutes_generator.client.chat.completions, 'create',
                         new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            
            result = await minutes_generator.generate(sample_transcription)
            
            assert result == "議事録の生成に失敗しました。"