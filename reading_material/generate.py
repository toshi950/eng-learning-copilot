"""長文読解教材の生成（フェーズ1）

英語の長文テキストを受け取り、Claude Opus 5でスラッシュリーディング教材
（Chunk Reading + 構文読解・意味解析テーブル）を生成し、入力した原文と
改行結合して1つの文字列として返す。
"""
from __future__ import annotations

import os
from typing import Optional

from anthropic import Anthropic
from dotenv import load_dotenv

from .prompts import build_prompt

load_dotenv()

MODEL = "claude-opus-5"
MAX_TOKENS = 16000


def _get_client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY が設定されていません。.env を確認してください。"
        )
    return Anthropic(api_key=api_key)


def call_claude(text: str, *, client: Optional[Anthropic] = None) -> str:
    """英文テキストから Chunk Reading + 構文読解・意味解析テーブルを生成する。"""
    client = client or _get_client()
    prompt = build_prompt(text)

    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()

    text_blocks = [block.text for block in message.content if block.type == "text"]
    return "\n".join(text_blocks).strip()


def generate_reading_material(english_text: str, *, client: Optional[Anthropic] = None) -> str:
    """英語長文テキストを受け取り、本文＋Chunk Reading＋構文解析テーブルを結合して返す。

    戻り値のフォーマット:
        ■本文
        <english_text>
        ■ Chunk Reading (本文)
        ...
        ■ 構文読解・意味解析テーブル
        ...
    """
    english_text = english_text.strip()
    analysis = call_claude(english_text, client=client)
    return f"■本文\n{english_text}\n{analysis}"
