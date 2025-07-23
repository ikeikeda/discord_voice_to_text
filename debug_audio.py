#!/usr/bin/env python3
"""
音声ファイルのデバッグ用スクリプト
"""
import sys
import wave
from pathlib import Path

def analyze_wav_file(file_path):
    """WAVファイルを解析"""
    path = Path(file_path)
    
    if not path.exists():
        print(f"❌ ファイルが存在しません: {file_path}")
        return
    
    file_size = path.stat().st_size
    print(f"📁 ファイルサイズ: {file_size:,} バイト ({file_size/1024:.1f} KB)")
    
    if file_size == 0:
        print("❌ ファイルが空です")
        return
    
    try:
        with wave.open(str(path), 'rb') as wav_file:
            frames = wav_file.getnframes()
            sample_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            duration = frames / sample_rate if sample_rate > 0 else 0
            
            print(f"🎵 チャンネル数: {channels}")
            print(f"🎵 サンプルレート: {sample_rate:,} Hz")
            print(f"🎵 サンプル幅: {sample_width} バイト")
            print(f"🎵 フレーム数: {frames:,}")
            print(f"⏱️  再生時間: {duration:.2f} 秒")
            
            if duration < 0.1:
                print("⚠️  警告: 再生時間が0.1秒未満です（OpenAI API制限）")
            else:
                print("✅ OpenAI APIで処理可能な長さです")
                
    except wave.Error as e:
        print(f"❌ WAVファイル解析エラー: {e}")
    except Exception as e:
        print(f"❌ 予期しないエラー: {e}")

def main():
    if len(sys.argv) != 2:
        print("使用方法: python debug_audio.py <WAVファイルパス>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    print(f"=== 音声ファイル解析: {file_path} ===")
    analyze_wav_file(file_path)

if __name__ == "__main__":
    main()