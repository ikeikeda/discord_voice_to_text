import logging
import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import discord
from pydub import AudioSegment
import io
import tempfile
from dataclasses import dataclass
import re

logger = logging.getLogger(__name__)


@dataclass
class SpeakerSegment:
    """話者ごとの発言セグメント"""
    user_id: int
    user_name: str
    start_time: float
    end_time: float
    text: str
    confidence: float = 1.0


@dataclass
class SpeechStatistics:
    """発言統計情報"""
    user_id: int
    user_name: str
    total_duration: float  # 総発言時間（秒）
    segment_count: int     # 発言回数
    word_count: int        # 単語数
    avg_segment_length: float  # 平均発言時間
    participation_ratio: float  # 参加率（%）


class SpeakerAnalyzer:
    """話者識別・分析クラス"""

    def __init__(self, output_dir: str = "recordings"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # 話者識別の有効/無効設定
        self.enable_speaker_identification = os.getenv("ENABLE_SPEAKER_IDENTIFICATION", "true").lower() == "true"
        self.enable_speaker_statistics = os.getenv("ENABLE_SPEAKER_STATISTICS", "true").lower() == "true"
        
        # 最小発言時間（秒）- これより短い発言は無視
        self.min_speech_duration = float(os.getenv("MIN_SPEECH_DURATION", "1.0"))
        
        # 話者切り替え検出の閾値（秒）
        self.speaker_change_threshold = float(os.getenv("SPEAKER_CHANGE_THRESHOLD", "0.5"))

    async def analyze_recording_with_speakers(
        self, 
        sink: discord.sinks.Sink, 
        participants: List[discord.Member],
        transcription: str
    ) -> Tuple[List[SpeakerSegment], List[SpeechStatistics]]:
        """録音データから話者識別・統計分析を実行"""
        try:
            if not self.enable_speaker_identification:
                # 話者識別無効時は全体を1つのセグメントとして扱う
                return self._create_single_segment(transcription, participants), []
            
            logger.info("話者識別分析を開始")
            
            # 1. 各参加者の個別音声ファイルを作成
            speaker_audio_files = await self._extract_individual_audio(sink, participants)
            
            # 2. 各音声の活動区間を検出
            speaker_activities = await self._detect_speech_activities(speaker_audio_files)
            
            # 3. 文字起こし結果を話者ごとに分割
            speaker_segments = await self._assign_text_to_speakers(
                transcription, speaker_activities, participants
            )
            
            # 4. 統計情報を計算
            statistics = self._calculate_statistics(speaker_segments, participants)
            
            # 5. 一時ファイルをクリーンアップ
            await self._cleanup_temp_files(speaker_audio_files)
            
            logger.info(f"話者識別完了: {len(speaker_segments)} セグメント, {len(statistics)} 話者")
            return speaker_segments, statistics
            
        except Exception as e:
            logger.error(f"話者分析エラー: {e}")
            # エラー時は全体を1つのセグメントとして返す
            return self._create_single_segment(transcription, participants), []

    async def _extract_individual_audio(
        self, 
        sink: discord.sinks.Sink, 
        participants: List[discord.Member]
    ) -> Dict[int, str]:
        """各参加者の個別音声ファイルを抽出"""
        speaker_files = {}
        
        if not sink.audio_data:
            logger.warning("録音データが空です")
            return speaker_files
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for user_id, audio_data in sink.audio_data.items():
            try:
                # Discordのユーザー情報を取得
                user = next((p for p in participants if p.id == user_id), None)
                if not user:
                    continue
                
                # ファイル名に使用する安全な表示名を作成
                safe_name = re.sub(r"[^0-9A-Za-z._-]", "_", str(user.display_name))

                # 音声データをファイルに保存
                temp_file = tempfile.NamedTemporaryFile(
                    suffix=f"_{safe_name}_{timestamp}.wav",
                    delete=False
                )

                # AudioSegmentを使用して音声データを処理（バッファを安全に取得）
                raw_audio: bytes = audio_data.file.getvalue()
                audio = AudioSegment.from_file(io.BytesIO(raw_audio), format="wav")
                
                # 無音部分が多い場合はスキップ
                if len(audio) < self.min_speech_duration * 1000:  # ms変換
                    temp_file.close()
                    os.unlink(temp_file.name)
                    continue
                
                audio.export(temp_file.name, format="wav")
                temp_file.close()
                speaker_files[user_id] = temp_file.name
                
                logger.debug(f"個別音声ファイル作成: {user.display_name} -> {temp_file.name}")
                
            except Exception as e:
                logger.error(f"個別音声抽出エラー (user_id: {user_id}): {e}")
                continue
        
        return speaker_files

    async def _detect_speech_activities(
        self, 
        speaker_audio_files: Dict[int, str]
    ) -> Dict[int, List[Tuple[float, float]]]:
        """各話者の発言区間を検出"""
        activities = {}
        
        for user_id, audio_file in speaker_audio_files.items():
            try:
                # AudioSegmentで音声を読み込み
                audio = AudioSegment.from_wav(audio_file)
                
                # 音声活動区間を検出（簡易版）
                activity_segments = self._detect_voice_activity(audio)
                activities[user_id] = activity_segments
                
            except Exception as e:
                logger.error(f"音声活動検出エラー (user_id: {user_id}): {e}")
                activities[user_id] = []
        
        return activities

    def _detect_voice_activity(self, audio: AudioSegment) -> List[Tuple[float, float]]:
        """音声活動区間検出（VAD: Voice Activity Detection）"""
        # 簡易的なVAD実装
        # 実際の実装では、より高度なVADアルゴリズム（WebRTCVAD等）を使用することを推奨
        
        silence_threshold = -40  # dBFS
        min_silence_duration = 500  # ms
        min_speech_duration = int(self.min_speech_duration * 1000)  # ms
        
        segments = []
        speech_start = None
        
        # 100msごとにチェック
        chunk_length = 100
        for i in range(0, len(audio), chunk_length):
            chunk = audio[i:i + chunk_length]
            
            if len(chunk) < chunk_length:
                break
            
            # 音量レベルをチェック
            db_level = chunk.dBFS
            
            if db_level > silence_threshold:
                # 音声検出
                if speech_start is None:
                    speech_start = i / 1000.0  # 秒に変換
            else:
                # 無音検出
                if speech_start is not None:
                    speech_end = i / 1000.0
                    duration = (speech_end - speech_start) * 1000
                    
                    # 最小発言時間以上の場合のみ記録
                    if duration >= min_speech_duration:
                        segments.append((speech_start, speech_end))
                    
                    speech_start = None
        
        # 最後のセグメントを処理
        if speech_start is not None:
            speech_end = len(audio) / 1000.0
            duration = (speech_end - speech_start) * 1000
            if duration >= min_speech_duration:
                segments.append((speech_start, speech_end))
        
        return segments

    async def _assign_text_to_speakers(
        self,
        transcription: str,
        speaker_activities: Dict[int, List[Tuple[float, float]]],
        participants: List[discord.Member]
    ) -> List[SpeakerSegment]:
        """文字起こし結果を話者ごとに分割"""
        segments = []
        
        if not speaker_activities:
            # 話者活動が検出されない場合は、全体を最初の参加者として扱う
            return self._create_single_segment(transcription, participants)
        
        # 全ての発言区間を時系列順にソート
        all_activities = []
        for user_id, activities in speaker_activities.items():
            user = next((p for p in participants if p.id == user_id), None)
            if user:
                for start, end in activities:
                    all_activities.append((start, end, user_id, user.display_name))
        
        all_activities.sort(key=lambda x: x[0])  # 開始時間でソート
        
        # 文字起こし結果を文単位に分割（簡易・日本語優先だが句読点の揺れに多少対応）
        # 区切り: 。 ． ！ ？ ! ? と改行
        raw_sentences = re.split(r"[。．！？!?]+|\n+", transcription)
        sentences = [s.strip() for s in raw_sentences if s and s.strip()]
        if not sentences:
            return segments
        
        # 各発言区間にテキストを割り当て（全文章を確実に配分）
        segment_count = len(all_activities)
        base = len(sentences) // segment_count if segment_count > 0 else len(sentences)
        remainder = len(sentences) % segment_count if segment_count > 0 else 0

        cursor = 0
        for i, (start, end, user_id, user_name) in enumerate(all_activities):
            take = base + (1 if i < remainder else 0)
            if take <= 0:
                continue
            end_cursor = min(cursor + take, len(sentences))
            chosen = sentences[cursor:end_cursor]
            cursor = end_cursor

            if chosen:
                segment_text = '。'.join(chosen)
                if segment_text and not segment_text.endswith('。'):
                    segment_text += '。'
                segments.append(SpeakerSegment(
                    user_id=user_id,
                    user_name=user_name,
                    start_time=start,
                    end_time=end,
                    text=segment_text
                ))
        
        return segments

    def _create_single_segment(
        self, 
        transcription: str, 
        participants: List[discord.Member]
    ) -> List[SpeakerSegment]:
        """話者識別なしで全体を1つのセグメントとして作成"""
        if not participants or not transcription.strip():
            return []
        
        # 最初の「人間」参加者を優先（botを除外）。見つからなければ先頭要素を使用
        human_participants = [p for p in participants if not getattr(p, 'bot', False)]
        first_participant = human_participants[0] if human_participants else participants[0]
        return [SpeakerSegment(
            user_id=first_participant.id,
            user_name=first_participant.display_name,
            start_time=0.0,
            end_time=0.0,  # 時間情報なし
            text=transcription.strip()
        )]

    def _calculate_statistics(
        self,
        segments: List[SpeakerSegment],
        participants: List[discord.Member]
    ) -> List[SpeechStatistics]:
        """発言統計を計算"""
        if not self.enable_speaker_statistics:
            return []
        
        stats_dict = {}
        total_duration = sum(seg.end_time - seg.start_time for seg in segments if seg.end_time > 0)
        
        for segment in segments:
            user_id = segment.user_id
            if user_id not in stats_dict:
                stats_dict[user_id] = {
                    'user_name': segment.user_name,
                    'total_duration': 0.0,
                    'segment_count': 0,
                    'word_count': 0
                }
            
            stats = stats_dict[user_id]
            stats['total_duration'] += segment.end_time - segment.start_time
            stats['segment_count'] += 1
            stats['word_count'] += len(segment.text.replace('。', ' ').split())
        
        # 統計オブジェクトを作成
        statistics = []
        for user_id, stats in stats_dict.items():
            avg_length = stats['total_duration'] / stats['segment_count'] if stats['segment_count'] > 0 else 0
            participation = (stats['total_duration'] / total_duration * 100) if total_duration > 0 else 0
            
            statistics.append(SpeechStatistics(
                user_id=user_id,
                user_name=stats['user_name'],
                total_duration=stats['total_duration'],
                segment_count=stats['segment_count'],
                word_count=stats['word_count'],
                avg_segment_length=avg_length,
                participation_ratio=participation
            ))
        
        return sorted(statistics, key=lambda x: x.total_duration, reverse=True)

    async def _cleanup_temp_files(self, speaker_audio_files: Dict[int, str]):
        """一時ファイルのクリーンアップ"""
        for user_id, file_path in speaker_audio_files.items():
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    logger.debug(f"一時ファイル削除: {file_path}")
            except Exception as e:
                logger.warning(f"一時ファイル削除エラー: {e}")

    def format_speaker_segments(self, segments: List[SpeakerSegment]) -> str:
        """話者識別結果を整形されたテキストとして出力"""
        if not segments:
            return "話者識別結果がありません。"
        
        formatted_lines = []
        formatted_lines.append("=== 話者別文字起こし結果 ===\n")
        
        for i, segment in enumerate(segments, 1):
            time_info = ""
            if segment.end_time > 0:
                time_info = f" [{segment.start_time:.1f}s - {segment.end_time:.1f}s]"
            
            formatted_lines.append(f"【{segment.user_name}】{time_info}")
            formatted_lines.append(f"{segment.text}\n")
        
        return "\n".join(formatted_lines)

    def format_statistics(self, statistics: List[SpeechStatistics]) -> str:
        """統計情報を整形されたテキストとして出力"""
        if not statistics:
            return "統計情報がありません。"
        
        formatted_lines = []
        formatted_lines.append("=== 会議統計情報 ===\n")
        
        for stat in statistics:
            formatted_lines.append(f"👤 {stat.user_name}")
            formatted_lines.append(f"  • 発言時間: {stat.total_duration:.1f}秒")
            formatted_lines.append(f"  • 発言回数: {stat.segment_count}回")
            formatted_lines.append(f"  • 単語数: {stat.word_count}語")
            formatted_lines.append(f"  • 平均発言時間: {stat.avg_segment_length:.1f}秒")
            formatted_lines.append(f"  • 参加率: {stat.participation_ratio:.1f}%\n")
        
        return "\n".join(formatted_lines)