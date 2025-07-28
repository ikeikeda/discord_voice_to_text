from abc import ABC, abstractmethod
from typing import Optional, Dict, List
import logging
import asyncio

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """LLMプロバイダーの基底クラス"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self._validate_api_key()

    @abstractmethod
    def _validate_api_key(self) -> None:
        """APIキーの検証"""
        pass

    @abstractmethod
    async def transcribe(self, audio_file_path: str, language: str = "ja") -> str:
        """音声ファイルを文字起こし"""
        pass

    @abstractmethod
    async def transcribe_with_timestamps(
        self, audio_file_path: str, language: str = "ja"
    ) -> dict:
        """タイムスタンプ付きで音声ファイルを文字起こし"""
        pass

    @abstractmethod
    async def generate_text(
        self, prompt: str, max_tokens: int = 2000, temperature: float = 0.3
    ) -> str:
        """テキスト生成"""
        pass

    @abstractmethod
    async def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> str:
        """チャット形式でのテキスト生成"""
        pass

    @abstractmethod
    def validate_api_key(self) -> bool:
        """APIキーの有効性をチェック"""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """プロバイダー名を返す"""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI APIプロバイダー"""

    def __init__(self, api_key: Optional[str] = None):
        import os
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        super().__init__(self.client.api_key)

    def _validate_api_key(self) -> None:
        if not self.client.api_key:
            raise ValueError("OpenAI APIキーが設定されていません")

    async def transcribe(self, audio_file_path: str, language: str = "ja") -> str:
        """音声ファイルを文字起こし"""
        try:
            from pathlib import Path
            import openai
            import os

            audio_file = Path(audio_file_path)
            if not audio_file.exists():
                raise FileNotFoundError(
                    f"音声ファイルが見つかりません: {audio_file_path}"
                )

            # 音声前処理による品質向上
            logger.info("音声前処理を実行します...")
            enhanced_file = await self._enhance_audio_for_transcription(audio_file_path)

            if enhanced_file:
                audio_file = Path(enhanced_file)
                logger.info("音声前処理が完了しました")
            else:
                logger.warning("音声前処理に失敗しました。元ファイルを使用します")
                audio_file = Path(audio_file_path)

            # ファイルサイズチェック（OpenAI Whisper API の制限: 25MB）
            file_size = audio_file.stat().st_size
            max_size = 25 * 1024 * 1024  # 25MB

            if file_size > max_size:
                logger.warning(
                    f"音声ファイルが大きすぎます: {file_size / (1024*1024):.2f}MB > 25MB"
                )
                # ファイル圧縮を試行
                compressed_file = await self._compress_audio_file(audio_file_path)
                if compressed_file:
                    audio_file = Path(compressed_file)
                    new_size = audio_file.stat().st_size
                    logger.info(
                        f"音声ファイルを圧縮しました: {new_size / (1024*1024):.2f}MB"
                    )

                    # 圧縮後もまだ大きい場合は分割処理
                    if new_size > max_size:
                        logger.info("圧縮後もサイズが大きいため、音声分割を実行します")
                        # 圧縮ファイルを分割
                        segments = await self._split_audio_file(
                            compressed_file, target_size_mb=20
                        )
                        if segments:
                            # 分割されたセグメントを文字起こし
                            result = await self._transcribe_segments(segments, language)
                            # 圧縮ファイルをクリーンアップ
                            try:
                                Path(compressed_file).unlink()
                                logger.debug(
                                    f"圧縮ファイルを削除しました: {compressed_file}"
                                )
                            except Exception as e:
                                logger.warning(f"圧縮ファイル削除エラー: {e}")
                            return result
                        else:
                            return f"音声ファイルが大きすぎます ({new_size / (1024*1024):.2f}MB > 25MB)。音声分割にも失敗しました。"
                else:
                    # 圧縮に失敗した場合、元ファイルを直接分割
                    logger.info("圧縮に失敗したため、元ファイルを分割します")
                    segments = await self._split_audio_file(
                        audio_file_path, target_size_mb=20
                    )
                    if segments:
                        return await self._transcribe_segments(segments, language)
                    else:
                        return f"音声ファイルが大きすぎます ({file_size / (1024*1024):.2f}MB > 25MB)。圧縮と分割の両方に失敗しました。"

            logger.info(
                f"音声ファイルを文字起こししています: {audio_file_path} ({file_size / (1024*1024):.2f}MB)"
            )

            # 最適化されたWhisperパラメータを取得
            whisper_params = self._get_whisper_parameters("discord")
            whisper_params["language"] = language

            # パフォーマンス監視
            import time

            start_time = time.time()

            with open(audio_file, "rb") as file:
                transcription = await self.client.audio.transcriptions.create(
                    file=file, **whisper_params
                )

            processing_time = time.time() - start_time
            logger.info(f"Whisper処理時間: {processing_time:.2f}秒")

            if isinstance(transcription, str):
                result = transcription.strip()
            else:
                result = str(transcription).strip()

            if not result:
                logger.warning("文字起こし結果が空でした")
                return "音声の文字起こしに失敗しました。"

            logger.info(f"文字起こし完了。文字数: {len(result)}")

            # 一時ファイルのクリーンアップ
            # 前処理ファイル
            if (
                "enhanced_file" in locals()
                and enhanced_file
                and enhanced_file != audio_file_path
            ):
                try:
                    Path(enhanced_file).unlink()
                    logger.debug(f"前処理ファイルを削除しました: {enhanced_file}")
                except Exception:
                    pass

            # 圧縮ファイル
            if (
                "compressed_file" in locals()
                and compressed_file
                and compressed_file != audio_file_path
            ):
                try:
                    Path(compressed_file).unlink()
                    logger.debug(f"圧縮ファイルを削除しました: {compressed_file}")
                except Exception:
                    pass

            return result

        except openai.OpenAIError as e:
            logger.error(f"OpenAI API エラー: {e}")
            return f"音声の文字起こしでAPIエラーが発生しました: {str(e)}"
        except FileNotFoundError as e:
            logger.error(f"ファイルエラー: {e}")
            return "音声ファイルが見つかりませんでした。"
        except Exception as e:
            logger.error(f"文字起こしエラー: {e}")
            return f"音声の文字起こし中に予期しないエラーが発生しました: {str(e)}"

    async def _compress_audio_file(self, audio_file_path: str) -> str:
        """音声ファイルを圧縮"""
        try:
            import tempfile
            from pathlib import Path

            input_path = Path(audio_file_path)

            # 一時ファイル作成
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                output_path = temp_file.name

            # FFmpegで音声を圧縮（ビットレート下げる、サンプリングレート下げる）
            cmd = [
                "ffmpeg",
                "-i",
                str(input_path),
                "-acodec",
                "mp3",  # MP3形式
                "-ab",
                "64k",  # ビットレート64kbps（元は通常128k+）
                "-ar",
                "16000",  # サンプリングレート16kHz（元は通常44.1kHz）
                "-ac",
                "1",  # モノラル
                "-y",  # 上書き確認なし
                output_path,
            ]

            logger.info("音声ファイルを圧縮中...")
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                output_file = Path(output_path)
                if output_file.exists() and output_file.stat().st_size > 0:
                    logger.info(f"音声ファイル圧縮完了: {output_path}")
                    return output_path
                else:
                    logger.error("圧縮ファイルが正常に作成されませんでした")
                    return None
            else:
                logger.error(f"FFmpeg圧縮エラー: {stderr.decode()}")
                return None

        except Exception as e:
            logger.error(f"音声圧縮エラー: {e}")
            return None

    async def _preprocess_audio_file(self, audio_file_path: str) -> str:
        """音声ファイルを前処理して品質を向上"""
        try:
            import tempfile
            from pathlib import Path

            input_path = Path(audio_file_path)

            # 一時ファイル作成
            with tempfile.NamedTemporaryFile(
                suffix="_preprocessed.wav", delete=False
            ) as temp_file:
                output_path = temp_file.name

            # FFmpegで音声前処理
            cmd = [
                "ffmpeg",
                "-i",
                str(input_path),
                # ノイズ除去フィルター
                "-af",
                "highpass=f=80,lowpass=f=8000,volume=2.0,dynaudnorm",
                # 音声品質最適化
                "-acodec",
                "pcm_s16le",  # 16bit PCM
                "-ar",
                "16000",  # Whisperに最適な16kHz
                "-ac",
                "1",  # モノラル
                "-y",  # 上書き確認なし
                output_path,
            ]

            logger.info("音声ファイルを前処理中...")
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                output_file = Path(output_path)
                if output_file.exists() and output_file.stat().st_size > 0:
                    logger.info(f"音声ファイル前処理完了: {output_path}")
                    return output_path
                else:
                    logger.error("前処理ファイルが正常に作成されませんでした")
                    return None
            else:
                logger.error(f"FFmpeg前処理エラー: {stderr.decode()}")
                return None

        except Exception as e:
            logger.error(f"音声前処理エラー: {e}")
            return None

    async def _enhance_audio_for_transcription(self, audio_file_path: str) -> str:
        """文字起こし精度向上のための音声品質向上処理"""
        try:
            import tempfile
            import os
            from pathlib import Path

            # 環境変数での前処理設定
            enable_preprocessing = (
                os.getenv("ENABLE_AUDIO_PREPROCESSING", "true").lower() == "true"
            )
            if not enable_preprocessing:
                logger.info("音声前処理が無効化されています")
                return None

            input_path = Path(audio_file_path)

            # 一時ファイル作成
            with tempfile.NamedTemporaryFile(
                suffix="_enhanced.wav", delete=False
            ) as temp_file:
                output_path = temp_file.name

            # 前処理強度の設定
            preprocessing_level = os.getenv(
                "AUDIO_PREPROCESSING_LEVEL", "medium"
            ).lower()

            if preprocessing_level == "light":
                # 軽い前処理
                audio_filter = (
                    "highpass=f=80,"  # 軽いローカット
                    "lowpass=f=8000,"  # 軽いハイカット
                    "volume=1.2,"  # 軽い音量調整
                    "dynaudnorm"  # 動的音量正規化のみ
                )
            elif preprocessing_level == "heavy":
                # 強い前処理
                audio_filter = (
                    "highpass=f=120,"  # 強いローカット
                    "lowpass=f=6000,"  # 強いハイカット
                    "volume=2.0,"  # 強い音量調整
                    "dynaudnorm=p=0.95:s=3,"  # 強い動的音量正規化
                    "deesser=i=0.15:m=0.15:f=5500:s=o,"  # 強い歯擦音除去
                    "compand=0.3,1:6:-70/-60,-20,0,0:0:0.2:0"  # コンプレッサー
                )
            else:
                # 中程度の前処理（デフォルト）
                audio_filter = (
                    "highpass=f=100,"  # 低周波ノイズ除去
                    "lowpass=f=7000,"  # 高周波ノイズ除去
                    "volume=1.5,"  # 音量調整
                    "dynaudnorm=p=0.9:s=5,"  # 動的音量正規化
                    "deesser=i=0.1:m=0.1:f=6000:s=o"  # 歯擦音除去
                )

            # 高度な音声品質向上処理
            cmd = [
                "ffmpeg",
                "-i",
                str(input_path),
                # 複合フィルター
                "-af",
                audio_filter,
                # 最適な音声形式
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",  # Whisper最適化
                "-ac",
                "1",  # モノラル
                "-y",
                output_path,
            ]

            logger.info("音声品質向上処理中...")
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                output_file = Path(output_path)
                if output_file.exists() and output_file.stat().st_size > 0:
                    original_size = input_path.stat().st_size / (1024 * 1024)
                    enhanced_size = output_file.stat().st_size / (1024 * 1024)
                    logger.info(
                        f"音声品質向上完了: {output_path} "
                        f"({original_size:.2f}MB → {enhanced_size:.2f}MB)"
                    )
                    return output_path
                else:
                    logger.error("品質向上ファイルが正常に作成されませんでした")
                    return None
            else:
                logger.error(f"FFmpeg品質向上エラー: {stderr.decode()}")
                return None

        except Exception as e:
            logger.error(f"音声品質向上エラー: {e}")
            return None

    def _get_whisper_parameters(self, audio_context: str = "discord") -> dict:
        """文脈に応じた最適化されたWhisperパラメータを取得"""
        import os

        # 基本パラメータ
        params = {"model": "whisper-1", "language": "ja", "response_format": "text"}

        # 文脈別プロンプトの最適化
        if audio_context == "discord":
            # Discord会話用の最適化プロンプト
            context_keywords = os.getenv(
                "DISCORD_CONTEXT_KEYWORDS",
                "Discord,ボイスチャット,会議,ミーティング,議論,相談,チーム,プロジェクト",
            )

            params[
                "prompt"
            ] = f"""これはDiscordでの{context_keywords.replace(',', '、')}です。
日本語での自然な会話を正確に文字起こししてください。
専門用語、固有名詞、カタカナ語も正確に認識してください。
音声の不明瞭な部分は文脈から推測して補完してください。"""

        elif audio_context == "segment":
            # 分割セグメント用の最適化プロンプト
            params[
                "prompt"
            ] = """これは長い会話の一部分です。
前後のセグメントと繋がりのある内容として、
文脈を考慮して自然な日本語に文字起こししてください。
文の途中で切れている場合も自然に補完してください。"""

        # 温度パラメータの最適化（利用可能であれば）
        temperature = float(os.getenv("WHISPER_TEMPERATURE", "0.0"))
        if temperature > 0:
            params["temperature"] = temperature

        # レスポンス形式の設定
        response_format = os.getenv("WHISPER_RESPONSE_FORMAT", "text")
        if response_format in ["text", "json", "srt", "verbose_json", "vtt"]:
            params["response_format"] = response_format

        logger.debug(f"Whisperパラメータ: {params}")
        return params

    def _get_whisper_timestamp_parameters(self, audio_context: str = "discord") -> dict:
        """タイムスタンプ付き文字起こし用の最適化パラメータ"""
        import os

        params = self._get_whisper_parameters(audio_context)

        # タイムスタンプ用の設定
        params["response_format"] = "verbose_json"
        params["timestamp_granularities"] = ["segment"]

        # より詳細なタイムスタンプが必要な場合
        if os.getenv("ENABLE_WORD_TIMESTAMPS", "false").lower() == "true":
            try:
                params["timestamp_granularities"] = ["word", "segment"]
                logger.info("単語レベルのタイムスタンプを有効化しました")
            except Exception as e:
                logger.warning(f"単語レベルタイムスタンプの設定に失敗: {e}")

        return params

    async def _split_audio_file(
        self, audio_file_path: str, target_size_mb: int = 20
    ) -> list:
        """音声ファイルを指定サイズ以下のセグメントに分割"""
        try:
            import tempfile
            import asyncio
            from pathlib import Path

            input_path = Path(audio_file_path)
            segments = []

            # 音声の長さを取得
            duration_cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(input_path),
            ]

            process = await asyncio.create_subprocess_exec(
                *duration_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"音声長さ取得エラー: {stderr.decode()}")
                return []

            total_duration = float(stdout.decode().strip())
            logger.info(f"音声の総長さ: {total_duration:.2f}秒")

            # ファイルサイズから必要な分割数を推定
            file_size_mb = input_path.stat().st_size / (1024 * 1024)
            estimated_segments = int((file_size_mb / target_size_mb) + 1)
            segment_duration = total_duration / estimated_segments

            logger.info(
                f"推定分割数: {estimated_segments}, セグメント長: {segment_duration:.2f}秒"
            )

            # セグメントごとに分割
            for i in range(estimated_segments):
                start_time = i * segment_duration

                # 最後のセグメントは残り全部
                if i == estimated_segments - 1:
                    duration = total_duration - start_time
                else:
                    duration = segment_duration

                # 一時ファイル作成
                with tempfile.NamedTemporaryFile(
                    suffix=f"_segment_{i}.mp3", delete=False
                ) as temp_file:
                    output_path = temp_file.name

                # FFmpegでセグメント抽出
                split_cmd = [
                    "ffmpeg",
                    "-i",
                    str(input_path),
                    "-ss",
                    str(start_time),  # 開始時間
                    "-t",
                    str(duration),  # 長さ
                    "-acodec",
                    "copy",  # 音声コーデックはコピー（高速）
                    "-y",  # 上書き確認なし
                    output_path,
                ]

                logger.info(f"セグメント {i+1}/{estimated_segments} を作成中...")
                process = await asyncio.create_subprocess_exec(
                    *split_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    output_file = Path(output_path)
                    if output_file.exists() and output_file.stat().st_size > 0:
                        segments.append(
                            {
                                "file_path": output_path,
                                "start_time": start_time,
                                "duration": duration,
                                "segment_index": i,
                            }
                        )
                        logger.info(f"セグメント {i+1} 作成完了: {output_path}")
                    else:
                        logger.error(f"セグメント {i+1} の作成に失敗")
                else:
                    logger.error(f"セグメント {i+1} 分割エラー: {stderr.decode()}")

            logger.info(f"音声分割完了: {len(segments)}個のセグメント")
            return segments

        except Exception as e:
            logger.error(f"音声分割エラー: {e}")
            return []

    async def _transcribe_segments(self, segments: list, language: str = "ja") -> str:
        """分割されたセグメントを順次文字起こしして統合"""
        try:
            transcriptions = []

            for segment in segments:
                segment_path = segment["file_path"]
                start_time = segment["start_time"]
                segment_index = segment["segment_index"]

                logger.info(f"セグメント {segment_index + 1} の文字起こし中...")

                # セグメントを個別に文字起こし（最適化パラメータ使用）
                whisper_params = self._get_whisper_parameters("segment")
                whisper_params["language"] = language

                with open(segment_path, "rb") as file:
                    transcription = await self.client.audio.transcriptions.create(
                        file=file, **whisper_params
                    )

                if isinstance(transcription, str):
                    result = transcription.strip()
                else:
                    result = str(transcription).strip()

                if result:
                    # タイムスタンプ情報を含めて保存
                    minutes = int(start_time // 60)
                    seconds = int(start_time % 60)
                    transcriptions.append(
                        {
                            "text": result,
                            "start_time": start_time,
                            "time_label": f"[{minutes:02d}:{seconds:02d}]",
                            "segment_index": segment_index,
                        }
                    )
                    logger.info(
                        f"セグメント {segment_index + 1} 完了 ({len(result)}文字)"
                    )
                else:
                    logger.warning(
                        f"セグメント {segment_index + 1} の文字起こし結果が空でした"
                    )

            # セグメントのクリーンアップ
            for segment in segments:
                try:
                    Path(segment["file_path"]).unlink()
                    logger.debug(f"セグメントファイルを削除: {segment['file_path']}")
                except Exception as e:
                    logger.warning(f"セグメントファイル削除エラー: {e}")

            if not transcriptions:
                return "分割された音声セグメントの文字起こしに失敗しました。"

            # 結果を統合（タイムスタンプ付き）
            combined_text = "【分割音声の文字起こし結果】\n\n"
            for trans in transcriptions:
                combined_text += f"{trans['time_label']} {trans['text']}\n\n"

            total_chars = sum(len(trans["text"]) for trans in transcriptions)
            logger.info(
                f"分割音声の文字起こし完了: {len(transcriptions)}セグメント, 総文字数: {total_chars}"
            )

            return combined_text.strip()

        except Exception as e:
            logger.error(f"セグメント文字起こしエラー: {e}")
            # エラー時もセグメントファイルをクリーンアップ
            for segment in segments:
                try:
                    Path(segment["file_path"]).unlink()
                except:
                    pass
            return f"分割音声の文字起こし中にエラーが発生しました: {e}"

    async def _transcribe_segments_with_timestamps(
        self, segments: list, language: str = "ja"
    ) -> dict:
        """分割されたセグメントをタイムスタンプ付きで文字起こしして統合"""
        try:
            all_segments = []
            combined_text = ""
            total_duration = 0

            for segment in segments:
                segment_path = segment["file_path"]
                start_time_offset = segment["start_time"]
                segment_index = segment["segment_index"]
                segment_duration = segment["duration"]

                logger.info(
                    f"セグメント {segment_index + 1} のタイムスタンプ付き文字起こし中..."
                )

                # セグメントをタイムスタンプ付きで文字起こし（最適化パラメータ使用）
                whisper_params = self._get_whisper_timestamp_parameters("segment")
                whisper_params["language"] = language

                with open(segment_path, "rb") as file:
                    transcription = await self.client.audio.transcriptions.create(
                        file=file, **whisper_params
                    )

                # 結果を処理
                if hasattr(transcription, "text"):
                    segment_text = transcription.text.strip()
                else:
                    segment_text = str(transcription).strip()

                if segment_text:
                    combined_text += segment_text + "\n"

                # セグメント情報を処理（タイムスタンプを全体の時間軸に調整）
                if hasattr(transcription, "segments") and transcription.segments:
                    for ts_segment in transcription.segments:
                        adjusted_segment = {
                            "id": len(all_segments),
                            "seek": ts_segment.get("seek", 0),
                            "start": ts_segment.get("start", 0) + start_time_offset,
                            "end": ts_segment.get("end", 0) + start_time_offset,
                            "text": ts_segment.get("text", ""),
                            "tokens": ts_segment.get("tokens", []),
                            "temperature": ts_segment.get("temperature", 0.0),
                            "avg_logprob": ts_segment.get("avg_logprob", 0.0),
                            "compression_ratio": ts_segment.get(
                                "compression_ratio", 0.0
                            ),
                            "no_speech_prob": ts_segment.get("no_speech_prob", 0.0),
                        }
                        all_segments.append(adjusted_segment)

                total_duration = max(
                    total_duration, start_time_offset + segment_duration
                )
                logger.info(
                    f"セグメント {segment_index + 1} 完了 ({len(segment_text)}文字)"
                )

            # セグメントのクリーンアップ
            for segment in segments:
                try:
                    Path(segment["file_path"]).unlink()
                    logger.debug(f"セグメントファイルを削除: {segment['file_path']}")
                except Exception as e:
                    logger.warning(f"セグメントファイル削除エラー: {e}")

            if not combined_text.strip():
                return {
                    "text": "分割された音声セグメントの文字起こしに失敗しました。",
                    "segments": [],
                    "language": language,
                    "duration": 0,
                }

            result = {
                "text": combined_text.strip(),
                "segments": all_segments,
                "language": language,
                "duration": total_duration,
            }

            logger.info(
                f"分割音声のタイムスタンプ付き文字起こし完了: {len(all_segments)}セグメント, 総文字数: {len(combined_text)}, 総時間: {total_duration:.2f}秒"
            )
            return result

        except Exception as e:
            logger.error(f"セグメントタイムスタンプ付き文字起こしエラー: {e}")
            # エラー時もセグメントファイルをクリーンアップ
            for segment in segments:
                try:
                    Path(segment["file_path"]).unlink()
                except:
                    pass
            return {
                "text": f"分割音声のタイムスタンプ付き文字起こし中にエラーが発生しました: {e}",
                "segments": [],
                "language": language,
                "duration": 0,
            }

    async def transcribe_with_timestamps(
        self, audio_file_path: str, language: str = "ja"
    ) -> dict:
        """タイムスタンプ付きで音声ファイルを文字起こし"""
        try:
            from pathlib import Path
            import openai

            audio_file = Path(audio_file_path)
            if not audio_file.exists():
                raise FileNotFoundError(
                    f"音声ファイルが見つかりません: {audio_file_path}"
                )

            # 音声前処理による品質向上
            logger.info("音声前処理を実行します...")
            enhanced_file = await self._enhance_audio_for_transcription(audio_file_path)

            if enhanced_file:
                audio_file = Path(enhanced_file)
                logger.info("音声前処理が完了しました")
            else:
                logger.warning("音声前処理に失敗しました。元ファイルを使用します")
                audio_file = Path(audio_file_path)

            # ファイルサイズチェック
            file_size = audio_file.stat().st_size
            max_size = 25 * 1024 * 1024  # 25MB

            compressed_file = None
            if file_size > max_size:
                logger.warning(
                    f"音声ファイルが大きすぎます: {file_size / (1024*1024):.2f}MB > 25MB"
                )
                compressed_file = await self._compress_audio_file(audio_file_path)
                if compressed_file:
                    audio_file = Path(compressed_file)
                    new_size = audio_file.stat().st_size
                    logger.info(
                        f"音声ファイルを圧縮しました: {new_size / (1024*1024):.2f}MB"
                    )

                    if new_size > max_size:
                        logger.info(
                            "圧縮後もサイズが大きいため、音声分割してタイムスタンプ付き文字起こしを実行します"
                        )
                        # 分割処理（タイムスタンプ付き）
                        segments = await self._split_audio_file(
                            compressed_file, target_size_mb=20
                        )
                        if segments:
                            result = await self._transcribe_segments_with_timestamps(
                                segments, language
                            )
                            # 圧縮ファイルをクリーンアップ
                            try:
                                Path(compressed_file).unlink()
                                logger.debug(
                                    f"圧縮ファイルを削除しました: {compressed_file}"
                                )
                            except Exception as e:
                                logger.warning(f"圧縮ファイル削除エラー: {e}")
                            return result
                        else:
                            return {
                                "text": f"音声ファイルが大きすぎます ({new_size / (1024*1024):.2f}MB > 25MB)。音声分割にも失敗しました。",
                                "segments": [],
                                "language": language,
                                "duration": 0,
                            }
                else:
                    # 圧縮に失敗した場合、元ファイルを直接分割
                    logger.info(
                        "圧縮に失敗したため、元ファイルを分割してタイムスタンプ付き文字起こしを実行します"
                    )
                    segments = await self._split_audio_file(
                        audio_file_path, target_size_mb=20
                    )
                    if segments:
                        return await self._transcribe_segments_with_timestamps(
                            segments, language
                        )
                    else:
                        return {
                            "text": f"音声ファイルが大きすぎます ({file_size / (1024*1024):.2f}MB > 25MB)。圧縮と分割の両方に失敗しました。",
                            "segments": [],
                            "language": language,
                            "duration": 0,
                        }

            logger.info(
                f"タイムスタンプ付き文字起こしを実行中: {audio_file_path} ({file_size / (1024*1024):.2f}MB)"
            )

            # 最適化されたWhisperパラメータを取得（タイムスタンプ付き）
            whisper_params = self._get_whisper_timestamp_parameters("discord")
            whisper_params["language"] = language

            with open(audio_file, "rb") as file:
                transcription = await self.client.audio.transcriptions.create(
                    file=file, **whisper_params
                )

            logger.info("タイムスタンプ付き文字起こし完了")

            # 一時ファイルのクリーンアップ
            # 前処理ファイル
            if (
                "enhanced_file" in locals()
                and enhanced_file
                and enhanced_file != audio_file_path
            ):
                try:
                    Path(enhanced_file).unlink()
                    logger.debug(f"前処理ファイルを削除しました: {enhanced_file}")
                except Exception:
                    pass

            # 圧縮ファイル
            if compressed_file and compressed_file != audio_file_path:
                try:
                    Path(compressed_file).unlink()
                    logger.debug(f"圧縮ファイルを削除しました: {compressed_file}")
                except Exception:
                    pass

            return {
                "text": transcription.text,
                "segments": (
                    transcription.segments if hasattr(transcription, "segments") else []
                ),
                "language": (
                    transcription.language
                    if hasattr(transcription, "language")
                    else language
                ),
                "duration": (
                    transcription.duration if hasattr(transcription, "duration") else 0
                ),
            }

        except openai.OpenAIError as e:
            logger.error(f"OpenAI API エラー: {e}")
            return {
                "text": f"音声の文字起こしでAPIエラーが発生しました: {str(e)}",
                "segments": [],
                "language": language,
                "duration": 0,
            }
        except Exception as e:
            logger.error(f"タイムスタンプ付き文字起こしエラー: {e}")
            return {
                "text": f"音声の文字起こし中に予期しないエラーが発生しました: {str(e)}",
                "segments": [],
                "language": language,
                "duration": 0,
            }

    async def generate_text(
        self, prompt: str, max_tokens: int = 2000, temperature: float = 0.3
    ) -> str:
        """テキスト生成"""
        try:
            import openai

            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )

            result = response.choices[0].message.content.strip()
            if not result:
                logger.warning("テキスト生成結果が空でした")
                return "テキストの生成に失敗しました。"

            return result

        except openai.OpenAIError as e:
            logger.error(f"OpenAI API エラー: {e}")
            return f"テキスト生成でAPIエラーが発生しました: {str(e)}"
        except Exception as e:
            logger.error(f"テキスト生成エラー: {e}")
            return f"テキスト生成中に予期しないエラーが発生しました: {str(e)}"

    async def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> str:
        """チャット形式でのテキスト生成"""
        try:
            import openai

            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            result = response.choices[0].message.content.strip()
            if not result:
                logger.warning("チャット生成結果が空でした")
                return "チャットの生成に失敗しました。"

            return result

        except openai.OpenAIError as e:
            logger.error(f"OpenAI API エラー: {e}")
            return f"チャット生成でAPIエラーが発生しました: {str(e)}"
        except Exception as e:
            logger.error(f"チャット生成エラー: {e}")
            return f"チャット生成中に予期しないエラーが発生しました: {str(e)}"

    def validate_api_key(self) -> bool:
        """APIキーの有効性をチェック"""
        try:
            return bool(self.client.api_key and len(self.client.api_key) > 10)
        except Exception:
            return False

    @property
    def provider_name(self) -> str:
        return "OpenAI"


class GeminiProvider(LLMProvider):
    """Gemini APIプロバイダー"""

    def __init__(self, api_key: Optional[str] = None):
        import os

        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        super().__init__(self.api_key)

        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            self.genai = genai

            # モデルの初期化（複数のモデルを試行）
            model_names = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
            self.text_model = None
            self.model_name = None

            for model_name in model_names:
                try:
                    self.text_model = genai.GenerativeModel(model_name)
                    self.model_name = model_name
                    logger.info(f"Gemini モデルを初期化しました: {model_name}")
                    break
                except Exception as e:
                    logger.warning(f"モデル {model_name} の初期化に失敗: {e}")
                    continue

            if not self.text_model:
                raise ValueError("利用可能なGeminiモデルが見つかりませんでした")
        except ImportError:
            raise ImportError(
                "google-generativeai ライブラリがインストールされていません。pip install google-generativeai でインストールしてください。"
            )

    def _validate_api_key(self) -> None:
        if not self.api_key:
            raise ValueError("Gemini APIキーが設定されていません")

    async def transcribe(self, audio_file_path: str, language: str = "ja") -> str:
        """音声ファイルを文字起こし（Geminiは現在音声転写をサポートしていないため、代替案を提示）"""
        logger.warning(
            "Gemini は直接的な音声転写をサポートしていません。OpenAI Whisper の使用を推奨します。"
        )
        return "Gemini プロバイダーでは音声転写は現在サポートされていません。OpenAI プロバイダーを使用してください。"

    async def transcribe_with_timestamps(
        self, audio_file_path: str, language: str = "ja"
    ) -> dict:
        """タイムスタンプ付きで音声ファイルを文字起こし"""
        logger.warning("Gemini は直接的な音声転写をサポートしていません。")
        return {
            "text": "Gemini プロバイダーでは音声転写は現在サポートされていません。OpenAI プロバイダーを使用してください。",
            "segments": [],
            "language": language,
            "duration": 0,
        }

    async def generate_text(
        self, prompt: str, max_tokens: int = 2000, temperature: float = 0.3
    ) -> str:
        """テキスト生成"""
        try:
            # Gemini の設定
            generation_config = {
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            }

            # 同期メソッドを非同期で実行
            import asyncio

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.text_model.generate_content(
                    prompt, generation_config=generation_config
                ),
            )

            if response.text:
                return response.text.strip()
            else:
                logger.warning("Gemini テキスト生成結果が空でした")
                return "テキストの生成に失敗しました。"

        except Exception as e:
            logger.error(f"Gemini API エラー: {e}")
            return f"テキスト生成でAPIエラーが発生しました: {str(e)}"

    async def generate_chat_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> str:
        """チャット形式でのテキスト生成"""
        try:
            # メッセージを Gemini 形式に変換
            prompt_parts = []
            for message in messages:
                role = message.get("role", "user")
                content = message.get("content", "")

                if role == "system":
                    prompt_parts.append(f"システム: {content}")
                elif role == "user":
                    prompt_parts.append(f"ユーザー: {content}")
                elif role == "assistant":
                    prompt_parts.append(f"アシスタント: {content}")

            full_prompt = "\n\n".join(prompt_parts)

            return await self.generate_text(full_prompt, max_tokens, temperature)

        except Exception as e:
            logger.error(f"Gemini チャット生成エラー: {e}")
            return f"チャット生成中に予期しないエラーが発生しました: {str(e)}"

    def validate_api_key(self) -> bool:
        """APIキーの有効性をチェック"""
        try:
            return bool(self.api_key and len(self.api_key) > 10)
        except Exception:
            return False

    @property
    def provider_name(self) -> str:
        return "Gemini"


def create_llm_provider(provider_name: str = None) -> LLMProvider:
    """LLMプロバイダーのファクトリー関数"""
    import os

    if provider_name is None:
        provider_name = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider_name == "openai":
        return OpenAIProvider()
    elif provider_name == "gemini":
        return GeminiProvider()
    else:
        raise ValueError(f"サポートされていないLLMプロバイダー: {provider_name}")
