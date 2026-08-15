"""長文読解教材の生成（フェーズ1）

英語の長文テキストを受け取り、Claude Opus 5でスラッシュリーディング教材
（Chunk Reading + 構文読解・意味解析テーブル）を生成し、入力した原文と
結合して1つのMarkdown文字列として返す。

背景知識生成はここでは扱わない（Web検索なしでは学習データカットオフ以降の
事実を誤判定するリスクがあるため、Web検索を伴うフェーズ3「専門分野の情報収集」
側に統合する方針。詳細は内部設計メモを参照）。

`READING_MATERIAL_OUTPUT_DIR` 環境変数が設定されている場合、生成結果を
そのディレクトリに .md ファイルとして保存できる（save_to_output_dir）。
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
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
    """英語長文テキストを受け取り、本文＋Chunk Reading＋構文解析テーブルを結合したMarkdownを返す。

    戻り値のフォーマット:
        # 英語読解教材 - <生成日時>

        ## 本文

        <english_text>

        ## Chunk Reading

        ...

        ## 構文読解・意味解析テーブル

        ...
    """
    english_text = english_text.strip()
    analysis = call_claude(english_text, client=client)
    title = f"# 英語読解教材 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    return f"{title}\n\n## 本文\n\n{english_text}\n\n{analysis}\n"


def _slugify(text: str, *, max_words: int = 6) -> str:
    """ファイル名用に、英文の先頭から簡易スラッグを作る（英数字のみ抽出）。"""
    words = re.findall(r"[A-Za-z0-9]+", text)[:max_words]
    return "_".join(words) or "reading_material"


def save_to_output_dir(markdown: str, english_text: str) -> Optional[Path]:
    """READING_MATERIAL_OUTPUT_DIR が設定されていれば、Markdownをファイルに保存する。

    ディレクトリが存在しない場合は作成する。未設定の場合は何もせず None を返す
    （呼び出し側は標準出力のみで動作すればよい）。
    """
    output_dir = os.environ.get("READING_MATERIAL_OUTPUT_DIR")
    if not output_dir:
        return None

    output_path = Path(output_dir).expanduser()
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{_slugify(english_text)}.md"
    file_path = output_path / filename
    file_path.write_text(markdown, encoding="utf-8")
    return file_path
