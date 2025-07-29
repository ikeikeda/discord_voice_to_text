import logging
from datetime import datetime
from typing import Dict, List, Optional
import discord

logger = logging.getLogger(__name__)


class DiscordContextManager:
    """Discord特有のコンテキスト情報を管理するクラス"""

    def __init__(self):
        self.recording_sessions = {}

    def create_recording_context(
        self,
        guild: discord.Guild,
        channel: discord.VoiceChannel,
        initiator: discord.Member,
        participants: List[discord.Member],
    ) -> Dict:
        """録音セッションのコンテキスト情報を作成"""
        context = {
            "session_id": f"{guild.id}_{channel.id}_{int(datetime.now().timestamp())}",
            "guild_info": {
                "id": guild.id,
                "name": guild.name,
                "member_count": guild.member_count,
            },
            "channel_info": {
                "id": channel.id,
                "name": channel.name,
                "type": str(channel.type),
                "category": channel.category.name if channel.category else None,
            },
            "initiator_info": {
                "id": initiator.id,
                "name": initiator.display_name,
                "username": initiator.name,
                "roles": [
                    role.name for role in initiator.roles if role.name != "@everyone"
                ],
            },
            "participants": [
                {
                    "id": member.id,
                    "name": member.display_name,
                    "username": member.name,
                    "roles": [
                        role.name for role in member.roles if role.name != "@everyone"
                    ],
                    "bot": member.bot,
                }
                for member in participants
                if not member.bot
            ],
            "timestamp": {
                "start": datetime.now().isoformat(),
                "timezone": "Asia/Tokyo",
            },
            "metadata": {
                "participant_count": len([m for m in participants if not m.bot]),
                "has_admin": any(
                    member.guild_permissions.administrator for member in participants
                ),
                "channel_category": (
                    channel.category.name if channel.category else "未分類"
                ),
            },
        }

        self.recording_sessions[guild.id] = context
        logger.info(f"録音コンテキスト作成: {context['session_id']}")
        return context

    def get_context_enhanced_prompt(
        self, guild_id: int, base_context: str = "discord"
    ) -> str:
        """コンテキスト情報を活用した強化プロンプトを生成"""
        if guild_id not in self.recording_sessions:
            return self._get_default_prompt(base_context)

        context = self.recording_sessions[guild_id]

        # 参加者情報を基にした動的プロンプト生成
        participant_names = [p["name"] for p in context["participants"]]
        channel_info = context["channel_info"]

        # チャンネル名から会話の性質を推測
        channel_hints = self._analyze_channel_context(
            channel_info["name"], channel_info.get("category", "")
        )

        # 参加者の役職から会話の性質を推測
        role_hints = self._analyze_participant_roles(context["participants"])

        enhanced_prompt = f"""これは{context["guild_info"]["name"]}サーバーの{channel_info["name"]}チャンネルでの会話です。

参加者: {", ".join(participant_names)}

会話の性質: {channel_hints}
{role_hints}

以下の点に注意して正確に文字起こししてください：
- 参加者の名前に関連する専門用語を正確に認識
- チャンネルの特性に応じた文脈理解
- 日本語の自然な会話として文字起こし
- 音声が不明瞭な場合は文脈から推測して補完
- 固有名詞、専門用語、カタカナ語を正確に記録"""

        return enhanced_prompt

    def _analyze_channel_context(self, channel_name: str, category: str) -> str:
        """チャンネル名から会話の性質を分析"""
        channel_lower = channel_name.lower()
        category_lower = category.lower() if category else ""

        if any(word in channel_lower for word in ["meeting", "会議", "ミーティング"]):
            return "会議・ミーティング"
        elif any(
            word in channel_lower
            for word in ["dev", "開発", "development", "プログラミング"]
        ):
            return "開発・技術関連の議論"
        elif any(word in channel_lower for word in ["review", "レビュー", "相談"]):
            return "レビュー・相談"
        elif any(word in channel_lower for word in ["chat", "雑談", "general"]):
            return "カジュアルな雑談"
        elif any(word in category_lower for word in ["work", "業務", "プロジェクト"]):
            return "業務・プロジェクト関連"
        else:
            return "一般的な会話"

    def _analyze_participant_roles(self, participants: List[Dict]) -> str:
        """参加者の役職から会話の性質を分析"""
        all_roles = []
        for p in participants:
            all_roles.extend(p["roles"])

        role_hints = []
        if any("admin" in role.lower() or "管理" in role for role in all_roles):
            role_hints.append("管理者が参加")
        if any("dev" in role.lower() or "開発" in role for role in all_roles):
            role_hints.append("開発者中心の議論")
        if any("lead" in role.lower() or "リード" in role for role in all_roles):
            role_hints.append("リーダー層の会議")

        return "参加者特性: " + ", ".join(role_hints) if role_hints else ""

    def _get_default_prompt(self, base_context: str) -> str:
        """デフォルトプロンプトを返す"""
        if base_context == "segment":
            return """これは長い会話の一部分です。
前後のセグメントと繋がりのある内容として、
文脈を考慮して自然な日本語に文字起こししてください。"""
        else:
            return """これはDiscordでの会話です。
日本語での自然な会話を正確に文字起こししてください。
専門用語、固有名詞、カタカナ語も正確に認識してください。"""

    def update_session_end(self, guild_id: int):
        """録音セッション終了時の処理"""
        if guild_id in self.recording_sessions:
            self.recording_sessions[guild_id]["timestamp"][
                "end"
            ] = datetime.now().isoformat()
            logger.info(f"録音セッション終了: {guild_id}")

    def cleanup_session(self, guild_id: int):
        """セッション情報のクリーンアップ"""
        if guild_id in self.recording_sessions:
            del self.recording_sessions[guild_id]
            logger.debug(f"セッションクリーンアップ: {guild_id}")

    def get_session_summary(self, guild_id: int) -> Optional[str]:
        """セッションの要約情報を取得"""
        if guild_id not in self.recording_sessions:
            return None

        context = self.recording_sessions[guild_id]
        start_time = datetime.fromisoformat(context["timestamp"]["start"])

        if "end" in context["timestamp"]:
            end_time = datetime.fromisoformat(context["timestamp"]["end"])
            duration = end_time - start_time
            duration_str = f"{int(duration.total_seconds() // 60)}分{int(duration.total_seconds() % 60)}秒"
        else:
            duration_str = "進行中"

        summary = f"""【録音セッション情報】
サーバー: {context["guild_info"]["name"]}
チャンネル: {context["channel_info"]["name"]}
開始者: {context["initiator_info"]["name"]}
参加者数: {context["metadata"]["participant_count"]}人
録音時間: {duration_str}
開始時刻: {start_time.strftime('%Y/%m/%d %H:%M:%S')}"""

        return summary
