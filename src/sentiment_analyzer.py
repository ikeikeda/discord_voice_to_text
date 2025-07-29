import logging
import re
import os
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
from .llm_providers import LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class SentimentInfo:
    """感情分析情報"""
    text: str
    sentiment: str  # positive, negative, neutral
    confidence: float
    emotions: Dict[str, float]  # 具体的な感情（喜び、怒り、心配など）
    speaker: Optional[str] = None


@dataclass
class MeetingSentiment:
    """会議全体の感情分析結果"""
    overall_sentiment: str
    positive_ratio: float
    negative_ratio: float
    neutral_ratio: float
    key_positive_moments: List[str]
    key_negative_moments: List[str]
    speaker_sentiments: Dict[str, Dict[str, float]]


class SentimentAnalyzer:
    """感情分析クラス"""

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider
        
        # 感情分析の有効/無効設定
        self.enable_sentiment_analysis = os.getenv("ENABLE_SENTIMENT_ANALYSIS", "false").lower() == "true"
        
        # 感情を表すキーワード辞書
        self.emotion_keywords = {
            'positive': {
                'joy': ['嬉しい', 'うれしい', '楽しい', '喜ぶ', '満足', '良かった', 'よかった', '素晴らしい', 'すばらしい'],
                'enthusiasm': ['やる気', 'がんばる', '頑張る', '期待', '楽しみ', 'わくわく', 'ワクワク'],
                'agreement': ['賛成', '同感', 'そうですね', 'いいですね', 'その通り', '正しい'],
                'appreciation': ['ありがとう', '感謝', 'お疲れ様', 'おつかれさま', '助かる', 'すごい'],
            },
            'negative': {
                'concern': ['心配', '不安', '気になる', '困る', '問題', '課題', 'リスク'],
                'frustration': ['困った', 'イライラ', 'いらいら', '大変', 'きつい', '厳しい'],
                'disagreement': ['反対', '違う', 'おかしい', '間違い', 'だめ', 'ダメ', '無理'],
                'disappointment': ['残念', 'がっかり', '期待外れ', '失敗', 'うまくいかない'],
            },
            'neutral': {
                'factual': ['です', 'ます', 'について', 'として', 'による', '確認', '報告'],
                'inquiry': ['どう', 'なぜ', 'いつ', 'どこで', '質問', '疑問', '確認したい'],
            }
        }
        
        # 感情の強度を表す修飾語
        self.intensity_modifiers = {
            'very_high': ['本当に', '非常に', 'とても', 'すごく', 'めちゃくちゃ', '超'],
            'high': ['かなり', 'だいぶ', 'すごい', '結構'],
            'medium': ['ちょっと', 'やや', '少し', 'まあまあ'],
            'low': ['それほど', 'あまり', 'そんなに']
        }

    async def analyze_meeting_sentiment(
        self, 
        transcription: str,
        speaker_segments: Optional[List] = None
    ) -> Optional[MeetingSentiment]:
        """会議全体の感情分析を実行"""
        try:
            if not self.enable_sentiment_analysis:
                return None
            
            logger.info("感情分析を開始")
            
            # 1. 文ごとの感情分析
            sentence_sentiments = await self._analyze_sentences(transcription)
            
            # 2. 話者別感情分析
            speaker_sentiments = {}
            if speaker_segments:
                speaker_sentiments = await self._analyze_speaker_sentiments(speaker_segments)
            
            # 3. 会議全体の感情サマリー
            meeting_sentiment = self._create_meeting_summary(
                sentence_sentiments, speaker_sentiments
            )
            
            logger.info(f"感情分析完了: 全体感情={meeting_sentiment.overall_sentiment}")
            return meeting_sentiment
            
        except Exception as e:
            logger.error(f"感情分析エラー: {e}")
            return None

    async def _analyze_sentences(self, text: str) -> List[SentimentInfo]:
        """文ごとの感情分析"""
        sentences = [s.strip() for s in text.split('。') if s.strip() and len(s.strip()) > 5]
        sentiments = []
        
        for sentence in sentences:
            if self.llm_provider:
                # AI による高度な感情分析
                sentiment_info = await self._ai_sentiment_analysis(sentence)
            else:
                # ルールベースの基本感情分析
                sentiment_info = self._basic_sentiment_analysis(sentence)
            
            if sentiment_info:
                sentiments.append(sentiment_info)
        
        return sentiments

    async def _ai_sentiment_analysis(self, text: str) -> Optional[SentimentInfo]:
        """AI による感情分析"""
        try:
            prompt = f"""以下のテキストの感情を分析してください。

テキスト: "{text}"

以下の項目を評価してください：
1. 全体的な感情: positive/negative/neutral
2. 信頼度: 0-1の数値
3. 具体的な感情:
   - 喜び (0-1)
   - 心配・不安 (0-1)
   - 怒り・不満 (0-1)
   - 同意・賛成 (0-1)
   - 期待・意欲 (0-1)

回答形式:
感情: [positive/negative/neutral]
信頼度: [0-1の数値]
喜び: [0-1の数値]
心配: [0-1の数値]
怒り: [0-1の数値]
同意: [0-1の数値]
期待: [0-1の数値]"""

            if hasattr(self.llm_provider, 'generate_text'):
                response = await self.llm_provider.generate_text(prompt, max_tokens=300, temperature=0.2)
                return self._parse_ai_sentiment(text, response)
        
        except Exception as e:
            logger.error(f"AI感情分析エラー: {e}")
        
        return None

    def _parse_ai_sentiment(self, text: str, ai_response: str) -> Optional[SentimentInfo]:
        """AI の感情分析結果を解析"""
        try:
            lines = ai_response.strip().split('\n')
            sentiment = 'neutral'
            confidence = 0.5
            emotions = {}
            
            for line in lines:
                line = line.strip()
                if line.startswith('感情:'):
                    sentiment = line.split(':')[1].strip()
                elif line.startswith('信頼度:'):
                    confidence = float(line.split(':')[1].strip())
                elif ':' in line:
                    key, value = line.split(':', 1)
                    try:
                        emotions[key.strip()] = float(value.strip())
                    except ValueError:
                        continue
            
            return SentimentInfo(
                text=text,
                sentiment=sentiment,
                confidence=confidence,
                emotions=emotions
            )
        
        except Exception as e:
            logger.error(f"AI感情分析結果解析エラー: {e}")
            return None

    def _basic_sentiment_analysis(self, text: str) -> SentimentInfo:
        """ルールベースの基本感情分析"""
        positive_score = 0
        negative_score = 0
        emotions = defaultdict(float)
        
        # 感情キーワードをチェック
        for sentiment_type, emotion_dict in self.emotion_keywords.items():
            for emotion, keywords in emotion_dict.items():
                for keyword in keywords:
                    if keyword in text:
                        if sentiment_type == 'positive':
                            positive_score += 1
                            emotions[emotion] += 1
                        elif sentiment_type == 'negative':
                            negative_score += 1
                            emotions[emotion] += 1
                        else:  # neutral
                            emotions[emotion] += 0.5
        
        # 強度修飾語を考慮
        intensity_multiplier = 1.0
        for intensity, modifiers in self.intensity_modifiers.items():
            for modifier in modifiers:
                if modifier in text:
                    if intensity == 'very_high':
                        intensity_multiplier = 2.0
                    elif intensity == 'high':
                        intensity_multiplier = 1.5
                    elif intensity == 'medium':
                        intensity_multiplier = 1.2
                    elif intensity == 'low':
                        intensity_multiplier = 0.8
                    break
        
        positive_score *= intensity_multiplier
        negative_score *= intensity_multiplier
        
        # 感情を決定
        if positive_score > negative_score and positive_score > 0:
            sentiment = 'positive'
            confidence = min(positive_score / (positive_score + negative_score + 1), 0.9)
        elif negative_score > positive_score and negative_score > 0:
            sentiment = 'negative'
            confidence = min(negative_score / (positive_score + negative_score + 1), 0.9)
        else:
            sentiment = 'neutral'
            confidence = 0.3
        
        return SentimentInfo(
            text=text,
            sentiment=sentiment,
            confidence=confidence,
            emotions=dict(emotions)
        )

    async def _analyze_speaker_sentiments(self, speaker_segments: List) -> Dict[str, Dict[str, float]]:
        """話者別感情分析"""
        speaker_sentiments = defaultdict(lambda: {'positive': 0, 'negative': 0, 'neutral': 0})
        
        for segment in speaker_segments:
            if hasattr(segment, 'text') and hasattr(segment, 'user_name'):
                sentiment_info = await self._ai_sentiment_analysis(segment.text)
                if not sentiment_info:
                    sentiment_info = self._basic_sentiment_analysis(segment.text)
                
                speaker_name = segment.user_name
                sentiment = sentiment_info.sentiment
                confidence = sentiment_info.confidence
                
                speaker_sentiments[speaker_name][sentiment] += confidence
        
        # 正規化
        for speaker, sentiments in speaker_sentiments.items():
            total = sum(sentiments.values())
            if total > 0:
                for sentiment in sentiments:
                    sentiments[sentiment] = sentiments[sentiment] / total
        
        return dict(speaker_sentiments)

    def _create_meeting_summary(
        self,
        sentence_sentiments: List[SentimentInfo],
        speaker_sentiments: Dict[str, Dict[str, float]]
    ) -> MeetingSentiment:
        """会議全体の感情サマリーを作成"""
        if not sentence_sentiments:
            return MeetingSentiment(
                overall_sentiment='neutral',
                positive_ratio=0.0,
                negative_ratio=0.0,
                neutral_ratio=1.0,
                key_positive_moments=[],
                key_negative_moments=[],
                speaker_sentiments=speaker_sentiments
            )
        
        # 全体的な感情比率を計算
        positive_count = sum(1 for s in sentence_sentiments if s.sentiment == 'positive')
        negative_count = sum(1 for s in sentence_sentiments if s.sentiment == 'negative')
        neutral_count = len(sentence_sentiments) - positive_count - negative_count
        
        total = len(sentence_sentiments)
        positive_ratio = positive_count / total
        negative_ratio = negative_count / total
        neutral_ratio = neutral_count / total
        
        # 全体感情を決定
        if positive_ratio > negative_ratio and positive_ratio > 0.4:
            overall_sentiment = 'positive'
        elif negative_ratio > positive_ratio and negative_ratio > 0.3:
            overall_sentiment = 'negative'
        else:
            overall_sentiment = 'neutral'
        
        # 重要なポジティブ・ネガティブモーメントを抽出
        positive_moments = [
            s.text for s in sentence_sentiments 
            if s.sentiment == 'positive' and s.confidence > 0.7
        ][:3]
        
        negative_moments = [
            s.text for s in sentence_sentiments 
            if s.sentiment == 'negative' and s.confidence > 0.7
        ][:3]
        
        return MeetingSentiment(
            overall_sentiment=overall_sentiment,
            positive_ratio=positive_ratio,
            negative_ratio=negative_ratio,
            neutral_ratio=neutral_ratio,
            key_positive_moments=positive_moments,
            key_negative_moments=negative_moments,
            speaker_sentiments=speaker_sentiments
        )

    def format_sentiment_analysis(self, meeting_sentiment: MeetingSentiment) -> str:
        """感情分析結果を整形"""
        if not meeting_sentiment:
            return "感情分析結果がありません。"
        
        # 感情の絵文字マッピング
        sentiment_emoji = {
            'positive': '😊',
            'negative': '😟',
            'neutral': '😐'
        }
        
        lines = ["=== 会議感情分析 ===\n"]
        
        # 全体感情
        emoji = sentiment_emoji.get(meeting_sentiment.overall_sentiment, '😐')
        lines.append(f"🎭 **全体的な雰囲気**: {emoji} {meeting_sentiment.overall_sentiment}")
        lines.append("")
        
        # 感情比率
        lines.append("📊 **感情分布**")
        lines.append(f"  😊 ポジティブ: {meeting_sentiment.positive_ratio:.1%}")
        lines.append(f"  😟 ネガティブ: {meeting_sentiment.negative_ratio:.1%}")
        lines.append(f"  😐 ニュートラル: {meeting_sentiment.neutral_ratio:.1%}")
        lines.append("")
        
        # ポジティブモーメント
        if meeting_sentiment.key_positive_moments:
            lines.append("✨ **前向きな発言**")
            for i, moment in enumerate(meeting_sentiment.key_positive_moments, 1):
                lines.append(f"  {i}. {moment[:100]}...")
            lines.append("")
        
        # ネガティブモーメント
        if meeting_sentiment.key_negative_moments:
            lines.append("⚠️ **懸念事項・課題**")
            for i, moment in enumerate(meeting_sentiment.key_negative_moments, 1):
                lines.append(f"  {i}. {moment[:100]}...")
            lines.append("")
        
        # 話者別感情
        if meeting_sentiment.speaker_sentiments:
            lines.append("👥 **参加者別感情傾向**")
            for speaker, sentiments in meeting_sentiment.speaker_sentiments.items():
                dominant = max(sentiments.keys(), key=lambda k: sentiments[k])
                dominant_emoji = sentiment_emoji.get(dominant, '😐')
                lines.append(f"  {dominant_emoji} {speaker}: {dominant} ({sentiments[dominant]:.1%})")
            lines.append("")
        
        return "\n".join(lines)