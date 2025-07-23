import asyncio
import logging
import os
from datetime import datetime
from typing import Optional, Dict, List
import openai
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class MinutesGenerator:
    def __init__(self, api_key: Optional[str] = None):
        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv('OPENAI_API_KEY')
        )
        if not self.client.api_key:
            raise ValueError("OpenAI APIキーが設定されていません")
    
    async def generate(self, transcription: str, meeting_title: str = "Discord会議") -> str:
        """文字起こしから議事録を生成"""
        try:
            if not transcription or transcription.strip() == "":
                return "文字起こしデータが空のため、議事録を生成できませんでした。"
            
            logger.info("議事録を生成しています...")
            
            prompt = self._create_minutes_prompt(transcription, meeting_title)
            
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたは優秀な議事録作成アシスタントです。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.3
            )
            
            minutes = response.choices[0].message.content.strip()
            
            if not minutes:
                logger.warning("議事録生成結果が空でした")
                return "議事録の生成に失敗しました。"
            
            logger.info(f"議事録生成完了。文字数: {len(minutes)}")
            return minutes
            
        except openai.OpenAIError as e:
            logger.error(f"OpenAI API エラー: {e}")
            return f"議事録生成でAPIエラーが発生しました: {str(e)}"
        except Exception as e:
            logger.error(f"議事録生成エラー: {e}")
            return f"議事録生成中に予期しないエラーが発生しました: {str(e)}"
    
    async def generate_detailed(self, transcription: str, segments: List[Dict] = None, 
                              meeting_title: str = "Discord会議") -> Dict[str, str]:
        """詳細な議事録を生成（要約、アクションアイテム、参加者など）"""
        try:
            if not transcription or transcription.strip() == "":
                return self._empty_minutes_response("文字起こしデータが空です")
            
            logger.info("詳細議事録を生成しています...")
            
            # 複数のプロンプトを並行実行
            tasks = [
                self._generate_summary(transcription, meeting_title),
                self._generate_action_items(transcription),
                self._generate_key_points(transcription),
                self._generate_decisions(transcription)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            summary = results[0] if not isinstance(results[0], Exception) else "要約の生成に失敗しました"
            action_items = results[1] if not isinstance(results[1], Exception) else "アクションアイテムの抽出に失敗しました"
            key_points = results[2] if not isinstance(results[2], Exception) else "重要ポイントの抽出に失敗しました"
            decisions = results[3] if not isinstance(results[3], Exception) else "決定事項の抽出に失敗しました"
            
            # 詳細議事録を組み立て
            detailed_minutes = self._format_detailed_minutes(
                meeting_title, summary, key_points, decisions, action_items
            )
            
            logger.info("詳細議事録生成完了")
            return {
                "full_minutes": detailed_minutes,
                "summary": summary,
                "action_items": action_items,
                "key_points": key_points,
                "decisions": decisions
            }
            
        except Exception as e:
            logger.error(f"詳細議事録生成エラー: {e}")
            return self._empty_minutes_response(f"エラー: {str(e)}")
    
    def _create_minutes_prompt(self, transcription: str, meeting_title: str) -> str:
        """議事録生成用のプロンプトを作成"""
        timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        
        return f"""
以下のDiscord会議の文字起こしから、読みやすい議事録を作成してください。

【会議情報】
- タイトル: {meeting_title}
- 日時: {timestamp}

【文字起こし内容】
{transcription}

【議事録作成の要件】
1. 会議の要点を整理して記載
2. 重要な決定事項があれば明記
3. アクションアイテム（やるべきこと）があれば整理
4. 読みやすい形式で出力
5. 日本語で作成

議事録:
"""
    
    async def _generate_summary(self, transcription: str, meeting_title: str) -> str:
        """会議の要約を生成"""
        prompt = f"""
以下の{meeting_title}の文字起こしから、会議の要約を3-5行で作成してください。

文字起こし:
{transcription}

要約:
"""
        response = await self.client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "あなたは会議要約のエキスパートです。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    
    async def _generate_action_items(self, transcription: str) -> str:
        """アクションアイテムを抽出"""
        prompt = f"""
以下の文字起こしから、アクションアイテム（やるべきこと、宿題、次回までにやること）を箇条書きで抽出してください。
アクションアイテムが見つからない場合は「アクションアイテムはありませんでした」と回答してください。

文字起こし:
{transcription}

アクションアイテム:
"""
        response = await self.client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "アクションアイテム抽出のエキスパートです。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=400,
            temperature=0.1
        )
        return response.choices[0].message.content.strip()
    
    async def _generate_key_points(self, transcription: str) -> str:
        """重要なポイントを抽出"""
        prompt = f"""
以下の文字起こしから、重要なポイントや議論された主要な話題を箇条書きで抽出してください。

文字起こし:
{transcription}

重要ポイント:
"""
        response = await self.client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "重要ポイント抽出のエキスパートです。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=400,
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    
    async def _generate_decisions(self, transcription: str) -> str:
        """決定事項を抽出"""
        prompt = f"""
以下の文字起こしから、会議で決定された事項を箇条書きで抽出してください。
決定事項が見つからない場合は「決定事項はありませんでした」と回答してください。

文字起こし:
{transcription}

決定事項:
"""
        response = await self.client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "決定事項抽出のエキスパートです。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=400,
            temperature=0.1
        )
        return response.choices[0].message.content.strip()
    
    def _format_detailed_minutes(self, title: str, summary: str, key_points: str, 
                               decisions: str, action_items: str) -> str:
        """詳細議事録をフォーマット"""
        timestamp = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        
        return f"""
# {title} 議事録

**日時**: {timestamp}

## 会議要約
{summary}

## 重要ポイント
{key_points}

## 決定事項
{decisions}

## アクションアイテム
{action_items}

---
*この議事録はAIによって自動生成されました。*
"""
    
    def _empty_minutes_response(self, error_message: str) -> Dict[str, str]:
        """空の議事録レスポンスを生成"""
        return {
            "full_minutes": f"議事録の生成に失敗しました: {error_message}",
            "summary": error_message,
            "action_items": "抽出できませんでした",
            "key_points": "抽出できませんでした",
            "decisions": "抽出できませんでした"
        }
    
    def validate_api_key(self) -> bool:
        """APIキーの有効性をチェック"""
        try:
            return bool(self.client.api_key and len(self.client.api_key) > 10)
        except Exception:
            return False