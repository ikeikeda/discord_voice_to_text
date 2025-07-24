from abc import ABC, abstractmethod
from typing import Optional, Dict, List
import logging

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
    async def transcribe_with_timestamps(self, audio_file_path: str, language: str = "ja") -> dict:
        """タイムスタンプ付きで音声ファイルを文字起こし"""
        pass
    
    @abstractmethod
    async def generate_text(self, prompt: str, max_tokens: int = 2000, temperature: float = 0.3) -> str:
        """テキスト生成"""
        pass
    
    @abstractmethod
    async def generate_chat_completion(self, messages: List[Dict[str, str]], 
                                     max_tokens: int = 2000, temperature: float = 0.3) -> str:
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
        
        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv('OPENAI_API_KEY')
        )
        super().__init__(self.client.api_key)
    
    def _validate_api_key(self) -> None:
        if not self.client.api_key:
            raise ValueError("OpenAI APIキーが設定されていません")
    
    async def transcribe(self, audio_file_path: str, language: str = "ja") -> str:
        """音声ファイルを文字起こし"""
        try:
            from pathlib import Path
            import openai
            
            audio_file = Path(audio_file_path)
            if not audio_file.exists():
                raise FileNotFoundError(f"音声ファイルが見つかりません: {audio_file_path}")
            
            # ファイルサイズチェック（OpenAI Whisper API の制限: 25MB）
            file_size = audio_file.stat().st_size
            max_size = 25 * 1024 * 1024  # 25MB
            
            if file_size > max_size:
                logger.warning(f"音声ファイルが大きすぎます: {file_size / (1024*1024):.2f}MB > 25MB")
                # ファイル圧縮を試行
                compressed_file = await self._compress_audio_file(audio_file_path)
                if compressed_file:
                    audio_file = Path(compressed_file)
                    new_size = audio_file.stat().st_size
                    logger.info(f"音声ファイルを圧縮しました: {new_size / (1024*1024):.2f}MB")
                    
                    # 圧縮後もまだ大きい場合
                    if new_size > max_size:
                        return f"音声ファイルが大きすぎます ({new_size / (1024*1024):.2f}MB > 25MB)。より短い録音にするか、音質を下げてください。"
                else:
                    return f"音声ファイルが大きすぎます ({file_size / (1024*1024):.2f}MB > 25MB)。より短い録音にするか、音質を下げてください。"
            
            logger.info(f"音声ファイルを文字起こししています: {audio_file_path} ({file_size / (1024*1024):.2f}MB)")
            
            with open(audio_file, "rb") as file:
                transcription = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=file,
                    language=language,
                    response_format="text",
                    prompt="これはDiscordでの会話です。正確な文字起こしをお願いします。"
                )
            
            if isinstance(transcription, str):
                result = transcription.strip()
            else:
                result = str(transcription).strip()
            
            if not result:
                logger.warning("文字起こし結果が空でした")
                return "音声の文字起こしに失敗しました。"
            
            logger.info(f"文字起こし完了。文字数: {len(result)}")
            
            # 圧縮ファイルのクリーンアップ
            if 'compressed_file' in locals() and compressed_file and compressed_file != audio_file_path:
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
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                output_path = temp_file.name
            
            # FFmpegで音声を圧縮（ビットレート下げる、サンプリングレート下げる）
            cmd = [
                'ffmpeg', '-i', str(input_path),
                '-acodec', 'mp3',           # MP3形式
                '-ab', '64k',               # ビットレート64kbps（元は通常128k+）
                '-ar', '16000',             # サンプリングレート16kHz（元は通常44.1kHz）
                '-ac', '1',                 # モノラル
                '-y',                       # 上書き確認なし
                output_path
            ]
            
            logger.info("音声ファイルを圧縮中...")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
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
    
    async def transcribe_with_timestamps(self, audio_file_path: str, language: str = "ja") -> dict:
        """タイムスタンプ付きで音声ファイルを文字起こし"""
        try:
            from pathlib import Path
            import openai
            
            audio_file = Path(audio_file_path)
            if not audio_file.exists():
                raise FileNotFoundError(f"音声ファイルが見つかりません: {audio_file_path}")
            
            # ファイルサイズチェック
            file_size = audio_file.stat().st_size
            max_size = 25 * 1024 * 1024  # 25MB
            
            compressed_file = None
            if file_size > max_size:
                logger.warning(f"音声ファイルが大きすぎます: {file_size / (1024*1024):.2f}MB > 25MB")
                compressed_file = await self._compress_audio_file(audio_file_path)
                if compressed_file:
                    audio_file = Path(compressed_file)
                    new_size = audio_file.stat().st_size
                    logger.info(f"音声ファイルを圧縮しました: {new_size / (1024*1024):.2f}MB")
                    
                    if new_size > max_size:
                        return {
                            "text": f"音声ファイルが大きすぎます ({new_size / (1024*1024):.2f}MB > 25MB)。より短い録音にするか、音質を下げてください。",
                            "segments": [],
                            "language": language,
                            "duration": 0
                        }
                else:
                    return {
                        "text": f"音声ファイルが大きすぎます ({file_size / (1024*1024):.2f}MB > 25MB)。より短い録音にするか、音質を下げてください。",
                        "segments": [],
                        "language": language,
                        "duration": 0
                    }
            
            logger.info(f"タイムスタンプ付き文字起こしを実行中: {audio_file_path} ({file_size / (1024*1024):.2f}MB)")
            
            with open(audio_file, "rb") as file:
                transcription = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=file,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                    prompt="これはDiscordでの会話です。正確な文字起こしをお願いします。"
                )
            
            logger.info("タイムスタンプ付き文字起こし完了")
            
            # 圧縮ファイルのクリーンアップ
            if compressed_file and compressed_file != audio_file_path:
                try:
                    Path(compressed_file).unlink()
                    logger.debug(f"圧縮ファイルを削除しました: {compressed_file}")
                except Exception:
                    pass
            
            return {
                "text": transcription.text,
                "segments": transcription.segments if hasattr(transcription, 'segments') else [],
                "language": transcription.language if hasattr(transcription, 'language') else language,
                "duration": transcription.duration if hasattr(transcription, 'duration') else 0
            }
            
        except openai.OpenAIError as e:
            logger.error(f"OpenAI API エラー: {e}")
            return {
                "text": f"音声の文字起こしでAPIエラーが発生しました: {str(e)}",
                "segments": [],
                "language": language,
                "duration": 0
            }
        except Exception as e:
            logger.error(f"タイムスタンプ付き文字起こしエラー: {e}")
            return {
                "text": f"音声の文字起こし中に予期しないエラーが発生しました: {str(e)}",
                "segments": [],
                "language": language,
                "duration": 0
            }
    
    async def generate_text(self, prompt: str, max_tokens: int = 2000, temperature: float = 0.3) -> str:
        """テキスト生成"""
        try:
            import openai
            
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature
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
    
    async def generate_chat_completion(self, messages: List[Dict[str, str]], 
                                     max_tokens: int = 2000, temperature: float = 0.3) -> str:
        """チャット形式でのテキスト生成"""
        try:
            import openai
            
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
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
        
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        super().__init__(self.api_key)
        
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.genai = genai
            
            # モデルの初期化（複数のモデルを試行）
            model_names = ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro']
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
            raise ImportError("google-generativeai ライブラリがインストールされていません。pip install google-generativeai でインストールしてください。")
    
    def _validate_api_key(self) -> None:
        if not self.api_key:
            raise ValueError("Gemini APIキーが設定されていません")
    
    async def transcribe(self, audio_file_path: str, language: str = "ja") -> str:
        """音声ファイルを文字起こし（Geminiは現在音声転写をサポートしていないため、代替案を提示）"""
        logger.warning("Gemini は直接的な音声転写をサポートしていません。OpenAI Whisper の使用を推奨します。")
        return "Gemini プロバイダーでは音声転写は現在サポートされていません。OpenAI プロバイダーを使用してください。"
    
    async def transcribe_with_timestamps(self, audio_file_path: str, language: str = "ja") -> dict:
        """タイムスタンプ付きで音声ファイルを文字起こし"""
        logger.warning("Gemini は直接的な音声転写をサポートしていません。")
        return {
            "text": "Gemini プロバイダーでは音声転写は現在サポートされていません。OpenAI プロバイダーを使用してください。",
            "segments": [],
            "language": language,
            "duration": 0
        }
    
    async def generate_text(self, prompt: str, max_tokens: int = 2000, temperature: float = 0.3) -> str:
        """テキスト生成"""
        try:
            # Gemini の設定
            generation_config = {
                'max_output_tokens': max_tokens,
                'temperature': temperature,
            }
            
            # 同期メソッドを非同期で実行
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: self.text_model.generate_content(prompt, generation_config=generation_config)
            )
            
            if response.text:
                return response.text.strip()
            else:
                logger.warning("Gemini テキスト生成結果が空でした")
                return "テキストの生成に失敗しました。"
                
        except Exception as e:
            logger.error(f"Gemini API エラー: {e}")
            return f"テキスト生成でAPIエラーが発生しました: {str(e)}"
    
    async def generate_chat_completion(self, messages: List[Dict[str, str]], 
                                     max_tokens: int = 2000, temperature: float = 0.3) -> str:
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
        provider_name = os.getenv('LLM_PROVIDER', 'openai').lower()
    
    if provider_name == 'openai':
        return OpenAIProvider()
    elif provider_name == 'gemini':
        return GeminiProvider()
    else:
        raise ValueError(f"サポートされていないLLMプロバイダー: {provider_name}")