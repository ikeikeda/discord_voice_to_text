import re
import logging
import asyncio
from typing import Optional, Dict, List
from .llm_providers import LLMProvider

logger = logging.getLogger(__name__)


class TextPostProcessor:
    """文字起こし結果の後処理クラス"""

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider
        
        # 日本語の句読点と文章区切りパターン
        self.sentence_end_patterns = re.compile(r'[。！？]')
        self.pause_patterns = re.compile(r'[、，]')
        
        # よくある音声認識エラーパターン
        self.common_errors = {
            'ですが': ['です が', 'です　が'],
            'ここで': ['ここ で', 'ここ　で'],
            'そうですね': ['そう です ね', 'そう　です　ね'],
            'について': ['に ついて', 'に　ついて'],
            'だと思います': ['だ と 思います', 'だ　と　思います'],
            'という': ['と いう', 'と　いう'],
            'なので': ['な ので', 'な　ので'],
            'じゃあ': ['じゃ あ', 'じゃ　あ'],
            'というか': ['と いうか', 'と　いうか'],
        }
        
        # カタカナ語の正規化パターン
        self.katakana_patterns = {
            'プログラミング': ['プログラム イング', 'プログラム　イング'],
            'コミット': ['コ ミット', 'コ　ミット'],
            'プルリクエスト': ['プル リクエスト', 'プル　リクエスト'],
            'マージ': ['マー ジ', 'マー　ジ'],
            'デバッグ': ['デ バッグ', 'デ　バッグ'],
            'リファクタリング': ['リファクタ リング', 'リファクタ　リング'],
            'デプロイ': ['デ プロイ', 'デ　プロイ'],
            'サーバー': ['サー バー', 'サー　バー'],
            'データベース': ['データ ベース', 'データ　ベース'],
            'アルゴリズム': ['アルゴ リズム', 'アルゴ　リズム'],
        }

    async def process_transcription(
        self, 
        text: str, 
        guild_id: Optional[int] = None,
        use_ai_correction: bool = True
    ) -> str:
        """文字起こし結果の包括的な後処理"""
        try:
            logger.info("文字起こし後処理を開始")
            
            # 1. 基本的なクリーンアップ
            processed_text = self._basic_cleanup(text)
            
            # 2. 一般的なエラーパターンの修正
            processed_text = self._fix_common_errors(processed_text)
            
            # 3. カタカナ語の正規化
            processed_text = self._fix_katakana_words(processed_text)
            
            # 4. 句読点の整理
            processed_text = self._normalize_punctuation(processed_text)
            
            # 5. 文章構造の改善
            processed_text = self._improve_sentence_structure(processed_text)
            
            # 6. AIによる高度な修正（オプション）
            if use_ai_correction and self.llm_provider:
                processed_text = await self._ai_correction(processed_text, guild_id)
            
            logger.info(f"後処理完了: {len(text)} → {len(processed_text)} 文字")
            return processed_text
            
        except Exception as e:
            logger.error(f"後処理エラー: {e}")
            return text  # エラー時は元のテキストを返す

    def _basic_cleanup(self, text: str) -> str:
        """基本的なクリーンアップ処理"""
        # 余分な空白を除去
        text = re.sub(r'\s+', ' ', text)
        
        # 先頭と末尾の空白を除去
        text = text.strip()
        
        # 連続する句読点を整理
        text = re.sub(r'[。]{2,}', '。', text)
        text = re.sub(r'[、]{2,}', '、', text)
        
        # 不完全な文の除去（3文字未満の単独文）
        sentences = text.split('。')
        cleaned_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) >= 3 or sentence == '':
                cleaned_sentences.append(sentence)
        
        return '。'.join(cleaned_sentences)

    def _fix_common_errors(self, text: str) -> str:
        """よくあるエラーパターンの修正"""
        for correct, error_patterns in self.common_errors.items():
            for error_pattern in error_patterns:
                text = text.replace(error_pattern, correct)
        return text

    def _fix_katakana_words(self, text: str) -> str:
        """カタカナ語の正規化"""
        for correct, error_patterns in self.katakana_patterns.items():
            for error_pattern in error_patterns:
                text = text.replace(error_pattern, correct)
        return text

    def _normalize_punctuation(self, text: str) -> str:
        """句読点の正規化"""
        # 句読点の前後の空白を調整
        text = re.sub(r'\s*([。、！？])\s*', r'\1', text)
        
        # 文の始まりの小文字を大文字に（英語部分）
        text = re.sub(r'([。！？]\s*)([a-z])', r'\1\2'.upper(), text)
        
        # 感嘆符・疑問符の後に適切な空白を追加
        text = re.sub(r'([！？])([あ-んア-ンa-zA-Z])', r'\1 \2', text)
        
        return text

    def _improve_sentence_structure(self, text: str) -> str:
        """文章構造の改善"""
        # 長すぎる文を適切に分割
        sentences = text.split('。')
        improved_sentences = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # 100文字を超える文を分割候補として検討
            if len(sentence) > 100:
                # 接続詞で分割可能な箇所を探す
                split_candidates = ['そして', 'また', 'それから', 'その後', 'しかし', 'ただし', 'なお']
                for candidate in split_candidates:
                    if candidate in sentence:
                        parts = sentence.split(candidate, 1)
                        if len(parts) == 2 and len(parts[0].strip()) > 20:
                            improved_sentences.append(parts[0].strip())
                            improved_sentences.append(candidate + parts[1].strip())
                            break
                else:
                    improved_sentences.append(sentence)
            else:
                improved_sentences.append(sentence)
        
        return '。'.join(improved_sentences)

    async def _ai_correction(self, text: str, guild_id: Optional[int] = None) -> str:
        """AIによる高度な文章修正"""
        try:
            if not self.llm_provider:
                return text
            
            # 修正用プロンプト
            correction_prompt = f"""以下は音声認識による文字起こし結果です。自然な日本語として読みやすくなるよう修正してください。

修正の方針:
1. 文法的に正しい日本語に修正
2. 不自然な区切りや繰り返しを整理
3. 専門用語や固有名詞の正しい表記に修正
4. 文章の流れを自然にする
5. 元の意味を変えないよう注意

修正対象のテキスト:
{text}

修正後のテキスト:"""

            # AIに修正を依頼
            if hasattr(self.llm_provider, 'generate_text'):
                corrected_text = await self.llm_provider.generate_text(correction_prompt)
                
                # 修正結果が元のテキストより大幅に短くなった場合は元を返す
                if len(corrected_text) < len(text) * 0.7:
                    logger.warning("AI修正結果が短すぎるため、元のテキストを使用")
                    return text
                
                return corrected_text.strip()
            else:
                logger.info("AIプロバイダーがtext生成に対応していないため、AI修正をスキップ")
                return text
                
        except Exception as e:
            logger.error(f"AI修正エラー: {e}")
            return text

    def get_text_statistics(self, original: str, processed: str) -> Dict:
        """処理前後のテキスト統計情報を取得"""
        return {
            "original_length": len(original),
            "processed_length": len(processed),
            "original_sentences": len(original.split('。')) - 1,
            "processed_sentences": len(processed.split('。')) - 1,
            "improvement_ratio": len(processed) / len(original) if len(original) > 0 else 1.0,
        }