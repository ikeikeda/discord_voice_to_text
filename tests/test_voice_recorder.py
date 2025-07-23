import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, mock_open
from pathlib import Path
import tempfile
import os
from datetime import datetime, timedelta

from src.voice_recorder import VoiceRecorder


@pytest.fixture
def temp_dir():
    """テスト用の一時ディレクトリ"""
    import tempfile
    import shutil
    
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def voice_recorder(temp_dir):
    """テスト用のVoiceRecorderインスタンス"""
    return VoiceRecorder(output_dir=temp_dir)


@pytest.fixture
def mock_voice_client():
    """モックのDiscordVoiceClient"""
    client = Mock()
    client.channel = Mock()
    client.channel.members = [Mock(), Mock()]  # 2人のメンバー
    client.is_recording.return_value = False
    return client


@pytest.fixture
def mock_sink():
    """モックの録音Sink"""
    sink = Mock()
    sink.audio_data = {}
    
    # モック音声データを作成
    mock_audio_1 = Mock()
    mock_audio_1.file.getvalue.return_value = b"fake_audio_data_1"
    
    mock_audio_2 = Mock()
    mock_audio_2.file.getvalue.return_value = b"fake_audio_data_2"
    
    sink.audio_data = {
        "user_1": mock_audio_1,
        "user_2": mock_audio_2
    }
    
    return sink


class TestVoiceRecorder:
    def test_init_default_directory(self):
        """デフォルトディレクトリでのインスタンス作成"""
        recorder = VoiceRecorder()
        assert recorder.output_dir == Path("recordings")
    
    def test_init_custom_directory(self, temp_dir):
        """カスタムディレクトリでのインスタンス作成"""
        recorder = VoiceRecorder(output_dir=temp_dir)
        assert recorder.output_dir == Path(temp_dir)
        assert recorder.output_dir.exists()
    
    @pytest.mark.asyncio
    async def test_start_recording_success(self, voice_recorder, mock_voice_client):
        """録音開始成功ケース"""
        with patch('discord.sinks.WaveSink') as mock_wave_sink:
            mock_sink = Mock()
            mock_wave_sink.return_value = mock_sink
            
            await voice_recorder.start_recording(mock_voice_client)
            
            assert voice_recorder.sink == mock_sink
            mock_voice_client.start_recording.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_start_recording_exception(self, voice_recorder, mock_voice_client):
        """録音開始時の例外処理"""
        mock_voice_client.start_recording.side_effect = Exception("録音エラー")
        
        with pytest.raises(Exception, match="録音エラー"):
            await voice_recorder.start_recording(mock_voice_client)
    
    @pytest.mark.asyncio
    async def test_stop_recording_success(self, voice_recorder, mock_voice_client, mock_sink):
        """録音停止成功ケース"""
        mock_voice_client.is_recording.return_value = True
        voice_recorder.sink = mock_sink
        
        with patch.object(voice_recorder, '_merge_audio_files', 
                         new_callable=AsyncMock) as mock_merge:
            mock_merge.return_value = "test_output.wav"
            
            result = await voice_recorder.stop_recording(mock_voice_client)
            
            assert result == "test_output.wav"
            mock_voice_client.stop_recording.assert_called_once()
            mock_merge.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop_recording_not_recording(self, voice_recorder, mock_voice_client):
        """録音していない状態での停止"""
        mock_voice_client.is_recording.return_value = False
        
        with pytest.raises(ValueError, match="現在録音していません"):
            await voice_recorder.stop_recording(mock_voice_client)
    
    @pytest.mark.asyncio
    async def test_merge_audio_files_success(self, voice_recorder, mock_sink):
        """音声ファイル結合成功ケース"""
        voice_recorder.sink = mock_sink
        
        # pydub.AudioSegmentのモック
        mock_audio_segment = Mock()
        mock_combined = Mock()
        mock_audio_segment.from_file.return_value = mock_combined
        mock_combined.overlay.return_value = mock_combined
        
        with patch('src.voice_recorder.AudioSegment', mock_audio_segment):
            with patch('builtins.open', mock_open()):
                result = await voice_recorder._merge_audio_files()
                
                assert result.endswith('.wav')
                assert 'recording_' in result
                mock_combined.export.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_merge_audio_files_no_data(self, voice_recorder):
        """音声データなしでの結合"""
        voice_recorder.sink = None
        
        with pytest.raises(ValueError, match="録音データが見つかりません"):
            await voice_recorder._merge_audio_files()
    
    @pytest.mark.asyncio
    async def test_merge_audio_files_fallback(self, voice_recorder, mock_sink):
        """結合失敗時のフォールバック"""
        voice_recorder.sink = mock_sink
        
        with patch('src.voice_recorder.AudioSegment') as mock_audio_segment:
            mock_audio_segment.from_file.side_effect = Exception("結合エラー")
            
            with patch('builtins.open', mock_open()) as mock_file:
                result = await voice_recorder._merge_audio_files()
                
                assert result.endswith('.wav')
                mock_file.assert_called()
    
    def test_cleanup_old_recordings(self, voice_recorder):
        """古い録音ファイルのクリーンアップ"""
        # テスト用の古いファイルを作成
        old_file = voice_recorder.output_dir / "recording_20200101_120000.wav"
        old_file.touch()
        
        # ファイルの更新日時を古い日付に設定
        old_timestamp = (datetime.now() - timedelta(days=10)).timestamp()
        os.utime(old_file, (old_timestamp, old_timestamp))
        
        # 新しいファイルも作成
        new_file = voice_recorder.output_dir / "recording_20231201_120000.wav"
        new_file.touch()
        
        # クリーンアップ実行
        voice_recorder.cleanup_old_recordings(max_age_days=7)
        
        # 古いファイルは削除され、新しいファイルは残る
        assert not old_file.exists()
        assert new_file.exists()
    
    def test_cleanup_old_recordings_exception(self, voice_recorder):
        """クリーンアップ中の例外処理"""
        # 存在しないディレクトリでのクリーンアップ
        voice_recorder.output_dir = Path("/non_existent_directory")
        
        # 例外が発生しても正常に終了することを確認
        voice_recorder.cleanup_old_recordings()
    
    @pytest.mark.asyncio
    async def test_finished_callback(self, voice_recorder):
        """録音完了コールバック"""
        mock_sink = Mock()
        mock_channel = Mock()
        
        # コールバックが例外を発生させないことを確認
        await voice_recorder._finished_callback(mock_sink, mock_channel)
    
    def test_output_directory_creation(self, temp_dir):
        """出力ディレクトリの自動作成"""
        non_existent_dir = Path(temp_dir) / "new_recordings"
        assert not non_existent_dir.exists()
        
        recorder = VoiceRecorder(output_dir=str(non_existent_dir))
        assert non_existent_dir.exists()
        assert recorder.output_dir == non_existent_dir