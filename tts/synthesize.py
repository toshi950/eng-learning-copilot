"""音声化（フェーズ2）

生成済みの英語テキストを Google Cloud Text-to-Speech（Studioボイス）で
音声合成し、mp3ファイルとして保存する。

認証は `GOOGLE_APPLICATION_CREDENTIALS`（サービスアカウントJSONキーのパス、
.env経由）をクライアントライブラリが自動的に参照する標準環境変数として利用する。

ボイス：en-US-Studio-Q（男性）を採用（2026-08-31、en-US-Studio-Oとの聴き比べで確定。
内部設計メモ参照）。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google.cloud import texttospeech

load_dotenv()

DEFAULT_VOICE = "en-US-Studio-Q"
DEFAULT_LANGUAGE_CODE = "en-US"


def _get_client() -> texttospeech.TextToSpeechClient:
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS が設定されていません。.env を確認してください。"
        )
    return texttospeech.TextToSpeechClient()


def synthesize_speech(
    text: str,
    *,
    voice_name: str = DEFAULT_VOICE,
    language_code: str = DEFAULT_LANGUAGE_CODE,
    client: Optional[texttospeech.TextToSpeechClient] = None,
) -> bytes:
    """英語テキストを音声合成し、mp3のバイト列を返す。"""
    client = client or _get_client()

    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code=language_code,
        name=voice_name,
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )
    return response.audio_content


def synthesize_to_file(
    text: str,
    output_path: Path,
    *,
    voice_name: str = DEFAULT_VOICE,
    language_code: str = DEFAULT_LANGUAGE_CODE,
    client: Optional[texttospeech.TextToSpeechClient] = None,
) -> Path:
    """英語テキストを音声合成し、mp3ファイルとして保存してパスを返す。"""
    audio_content = synthesize_speech(
        text,
        voice_name=voice_name,
        language_code=language_code,
        client=client,
    )
    output_path = Path(output_path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio_content)
    return output_path
