import logging
import re
import os
from typing import List, Dict, Tuple, Optional
from collections import Counter, defaultdict
from dataclasses import dataclass
from .llm_providers import LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class KeywordInfo:
    """キーワード情報"""
    word: str
    frequency: int
    importance_score: float
    category: str
    contexts: List[str]  # 出現文脈


@dataclass
class ActionItem:
    """アクションアイテム"""
    task: str
    assignee: Optional[str]
    deadline: Optional[str]
    priority: str
    context: str


class KeywordExtractor:
    """キーワード抽出・分析クラス"""

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider
        
        # キーワード抽出の有効/無効設定
        self.enable_keyword_extraction = os.getenv("ENABLE_KEYWORD_EXTRACTION", "true").lower() == "true"
        self.enable_action_items = os.getenv("ENABLE_ACTION_ITEMS", "true").lower() == "true"
        
        # 除外する一般的な単語（ストップワード）
        self.stop_words = {
            'です', 'ます', 'である', 'する', 'なる', 'ある', 'いる', 'れる', 'られる',
            'という', 'について', 'として', 'により', 'によって', 'に対して',
            'それ', 'これ', 'あれ', 'どれ', 'その', 'この', 'あの', 'どの',
            '私', '僕', '俺', '彼', '彼女', '我々', '皆さん', 'みなさん',
            'はい', 'いいえ', 'そうですね', 'なるほど', 'わかりました',
            'あー', 'えー', 'うー', 'んー', 'ええ', 'あの', 'その', 'まあ'
        }
        
        # 専門用語のカテゴリ
        self.tech_keywords = {
            'プログラミング': ['プログラミング', 'コーディング', '開発', '実装', 'バグ', 'デバッグ'],
            'プロジェクト管理': ['スケジュール', 'デッドライン', '進捗', 'タスク', 'アサイン', 'リリース'],
            'ツール・技術': ['GitHub', 'Git', 'Docker', 'API', 'データベース', 'サーバー'],
            '会議・コミュニケーション': ['レビュー', 'ミーティング', '相談', '決定', '承認', '報告'],
            '品質・テスト': ['テスト', 'テスト駆動', 'QA', '品質', 'パフォーマンス', 'セキュリティ']
        }
        
        # アクションを示すキーワード
        self.action_indicators = {
            'やる', '実装する', '作成する', '修正する', '調査する', '検討する',
            '確認する', '対応する', 'やります', '担当する', '進める', '完了する',
            'お願いします', 'やってください', 'してください', '対応してください'
        }

    async def extract_keywords_and_actions(
        self, 
        transcription: str,
        speaker_segments: Optional[List] = None
    ) -> Tuple[List[KeywordInfo], List[ActionItem]]:
        """キーワードとアクションアイテムを抽出"""
        try:
            if not self.enable_keyword_extraction:
                return [], []
            
            logger.info("キーワード・アクション抽出を開始")
            
            # 1. 基本的なキーワード抽出
            keywords = await self._extract_basic_keywords(transcription)
            
            # 2. AI による高度なキーワード抽出
            if self.llm_provider:
                ai_keywords = await self._extract_ai_keywords(transcription)
                keywords = self._merge_keywords(keywords, ai_keywords)
            
            # 3. アクションアイテム抽出
            action_items = []
            if self.enable_action_items:
                action_items = await self._extract_action_items(transcription, speaker_segments)
            
            logger.info(f"キーワード抽出完了: {len(keywords)} キーワード, {len(action_items)} アクション")
            return keywords, action_items
            
        except Exception as e:
            logger.error(f"キーワード抽出エラー: {e}")
            return [], []

    async def _extract_basic_keywords(self, text: str) -> List[KeywordInfo]:
        """基本的なキーワード抽出"""
        # 文を分割
        sentences = [s.strip() for s in text.split('。') if s.strip()]
        
        # 単語を抽出（簡易版）
        words = []
        for sentence in sentences:
            # カタカナ語を抽出
            katakana_words = re.findall(r'[ア-ン]{2,}', sentence)
            words.extend(katakana_words)
            
            # 英語単語を抽出
            english_words = re.findall(r'[A-Za-z]{2,}', sentence)
            words.extend(english_words)
            
            # 漢字を含む単語を抽出（簡易版）
            kanji_words = re.findall(r'[一-龯]{2,}', sentence)
            words.extend(kanji_words)
        
        # ストップワードを除去し、頻度をカウント
        filtered_words = [w for w in words if w.lower() not in self.stop_words and len(w) >= 2]
        word_counts = Counter(filtered_words)
        
        # キーワード情報を生成
        keywords = []
        for word, freq in word_counts.most_common(20):  # 上位20個
            category = self._categorize_keyword(word)
            contexts = self._find_contexts(word, sentences)
            importance = self._calculate_importance(word, freq, len(sentences))
            
            keywords.append(KeywordInfo(
                word=word,
                frequency=freq,
                importance_score=importance,
                category=category,
                contexts=contexts[:3]  # 最大3つの文脈
            ))
        
        return keywords

    async def _extract_ai_keywords(self, text: str) -> List[KeywordInfo]:
        """AI による高度なキーワード抽出"""
        try:
            prompt = f"""以下の会議文字起こしテキストから、重要なキーワードを抽出してください。

テキスト:
{text}

以下の形式で、最大15個のキーワードを抽出してください：
- 技術用語、プロジェクト名、重要な概念を優先
- 一般的すぎる単語は除外
- 各キーワードの重要度を1-10で評価

回答形式:
キーワード1 (重要度: X) - カテゴリ: Y
キーワード2 (重要度: X) - カテゴリ: Y
..."""

            if hasattr(self.llm_provider, 'generate_text'):
                response = await self.llm_provider.generate_text(prompt, max_tokens=1000, temperature=0.3)
                return self._parse_ai_keywords(response)
            
        except Exception as e:
            logger.error(f"AI キーワード抽出エラー: {e}")
        
        return []

    def _parse_ai_keywords(self, ai_response: str) -> List[KeywordInfo]:
        """AI の回答からキーワード情報を解析"""
        keywords = []
        lines = ai_response.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # パターンマッチング: "キーワード (重要度: X) - カテゴリ: Y"
            match = re.match(r'(.+?)\s*\(重要度:\s*(\d+)\)\s*-\s*カテゴリ:\s*(.+)', line)
            if match:
                word = match.group(1).strip()
                importance = float(match.group(2))
                category = match.group(3).strip()
                
                keywords.append(KeywordInfo(
                    word=word,
                    frequency=1,  # AI抽出では頻度は1
                    importance_score=importance,
                    category=category,
                    contexts=[]
                ))
        
        return keywords

    def _merge_keywords(self, basic_keywords: List[KeywordInfo], ai_keywords: List[KeywordInfo]) -> List[KeywordInfo]:
        """基本抽出とAI抽出のキーワードをマージ"""
        keyword_dict = {}
        
        # 基本キーワードを追加
        for kw in basic_keywords:
            keyword_dict[kw.word.lower()] = kw
        
        # AI キーワードを追加（重複は重要度を更新）
        for kw in ai_keywords:
            key = kw.word.lower()
            if key in keyword_dict:
                # 既存のキーワードの重要度を更新
                existing = keyword_dict[key]
                existing.importance_score = max(existing.importance_score, kw.importance_score)
                if kw.category and existing.category == '一般':
                    existing.category = kw.category
            else:
                keyword_dict[key] = kw
        
        # 重要度順にソート
        return sorted(keyword_dict.values(), key=lambda x: x.importance_score, reverse=True)

    async def _extract_action_items(
        self, 
        text: str, 
        speaker_segments: Optional[List] = None
    ) -> List[ActionItem]:
        """アクションアイテムを抽出"""
        action_items = []
        
        if not self.llm_provider:  # AI が利用できない場合は簡易抽出
            return self._extract_basic_actions(text)
        
        try:
            prompt = f"""以下の会議文字起こしテキストから、アクションアイテム（タスク・TODO）を抽出してください。

テキスト:
{text}

以下の観点で抽出してください：
- 具体的なタスクや作業項目
- 担当者が明示されているもの
- 期限が言及されているもの
- 決定事項や次回までに行うこと

回答形式:
タスク: [具体的なタスク内容]
担当者: [担当者名 または 不明]
期限: [期限 または 不明]
優先度: [高/中/低]
文脈: [該当する文の抜粋]
---"""

            response = await self.llm_provider.generate_text(prompt, max_tokens=1500, temperature=0.2)
            action_items = self._parse_action_items(response)
            
        except Exception as e:
            logger.error(f"アクションアイテム抽出エラー: {e}")
            action_items = self._extract_basic_actions(text)
        
        return action_items

    def _extract_basic_actions(self, text: str) -> List[ActionItem]:
        """基本的なアクションアイテム抽出"""
        actions = []
        sentences = [s.strip() for s in text.split('。') if s.strip()]
        
        for sentence in sentences:
            # アクション指示語を含む文を検索
            for indicator in self.action_indicators:
                if indicator in sentence:
                    # 簡易的にタスクとして抽出
                    task = sentence
                    assignee = self._extract_assignee(sentence)
                    
                    actions.append(ActionItem(
                        task=task,
                        assignee=assignee,
                        deadline=None,
                        priority='中',
                        context=sentence
                    ))
                    break
        
        return actions[:10]  # 最大10個

    def _extract_assignee(self, sentence: str) -> Optional[str]:
        """文から担当者を抽出"""
        # 簡易的な担当者抽出パターン
        patterns = [
            r'([ぁ-ん]+)さん.{0,20}(やる|やります|担当)',
            r'([ぁ-ん]+)が.{0,20}(やる|やります|担当)',
            r'([A-Za-z]+)さん.{0,20}(やる|やります|担当)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, sentence)
            if match:
                return match.group(1) + 'さん'
        
        return None

    def _parse_action_items(self, ai_response: str) -> List[ActionItem]:
        """AI回答からアクションアイテムを解析"""
        actions = []
        items = ai_response.split('---')
        
        for item in items:
            lines = [line.strip() for line in item.strip().split('\n') if line.strip()]
            if len(lines) < 4:
                continue
            
            task = assignee = deadline = priority = context = None
            
            for line in lines:
                if line.startswith('タスク:'):
                    task = line.replace('タスク:', '').strip()
                elif line.startswith('担当者:'):
                    assignee = line.replace('担当者:', '').strip()
                    if assignee == '不明':
                        assignee = None
                elif line.startswith('期限:'):
                    deadline = line.replace('期限:', '').strip()
                    if deadline == '不明':
                        deadline = None
                elif line.startswith('優先度:'):
                    priority = line.replace('優先度:', '').strip()
                elif line.startswith('文脈:'):
                    context = line.replace('文脈:', '').strip()
            
            if task:
                actions.append(ActionItem(
                    task=task,
                    assignee=assignee,
                    deadline=deadline,
                    priority=priority or '中',
                    context=context or task
                ))
        
        return actions

    def _categorize_keyword(self, word: str) -> str:
        """キーワードをカテゴライズ"""
        for category, keywords in self.tech_keywords.items():
            if any(kw in word for kw in keywords):
                return category
        
        # カタカナ語は技術用語として分類
        if re.match(r'^[ア-ン]+$', word):
            return 'ツール・技術'
        
        # 英語は技術用語として分類
        if re.match(r'^[A-Za-z]+$', word):
            return 'ツール・技術'
        
        return '一般'

    def _find_contexts(self, word: str, sentences: List[str]) -> List[str]:
        """キーワードが出現する文脈を検索"""
        contexts = []
        for sentence in sentences:
            if word in sentence:
                contexts.append(sentence)
                if len(contexts) >= 3:
                    break
        return contexts

    def _calculate_importance(self, word: str, frequency: int, total_sentences: int) -> float:
        """キーワードの重要度を計算"""
        # 基本的な重要度計算
        base_score = frequency / total_sentences * 10
        
        # 専門用語ボーナス
        if self._categorize_keyword(word) != '一般':
            base_score *= 1.5
        
        # 長い単語ボーナス
        if len(word) >= 4:
            base_score *= 1.2
        
        return min(base_score, 10.0)  # 最大10点

    def format_keywords(self, keywords: List[KeywordInfo]) -> str:
        """キーワード情報を整形"""
        if not keywords:
            return "キーワードが抽出されませんでした。"
        
        lines = ["=== 重要キーワード ===\n"]
        
        for i, kw in enumerate(keywords[:15], 1):  # 上位15個
            lines.append(f"{i}. **{kw.word}** (重要度: {kw.importance_score:.1f})")
            lines.append(f"   カテゴリ: {kw.category} | 出現回数: {kw.frequency}回")
            if kw.contexts:
                lines.append(f"   例: {kw.contexts[0][:50]}...")
            lines.append("")
        
        return "\n".join(lines)

    def format_action_items(self, actions: List[ActionItem]) -> str:
        """アクションアイテムを整形"""
        if not actions:
            return "アクションアイテムが見つかりませんでした。"
        
        lines = ["=== アクションアイテム ===\n"]
        
        for i, action in enumerate(actions, 1):
            priority_emoji = {"高": "🔴", "中": "🟡", "低": "🟢"}.get(action.priority, "⚪")
            
            lines.append(f"{i}. {priority_emoji} **{action.task}**")
            if action.assignee:
                lines.append(f"   👤 担当者: {action.assignee}")
            if action.deadline:
                lines.append(f"   📅 期限: {action.deadline}")
            lines.append(f"   📝 文脈: {action.context[:100]}...")
            lines.append("")
        
        return "\n".join(lines)