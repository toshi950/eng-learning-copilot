"""専門分野の情報収集（フェーズ3）

web_searchツール（Anthropicのサーバーサイドツール）を使い、監査・会計・税務
ドメインの最新トピックを1件調査する。戻り値は日本語の長文リサーチレポートと、
読み上げ・学習用の英語記事抜粋（200〜600語）の両方を含む。

英語記事抜粋はフェーズ1（`reading_material`）への入力として、日本語リサーチ
レポートは最終Markdown出力の背景知識セクションとして使う想定（実際の結合は
フェーズ4「自動化フロー統合」側で行う）。
"""
from __future__ import annotations

import json
import os
from typing import Optional

from anthropic import Anthropic
from dotenv import load_dotenv

from .prompts import build_prompt

load_dotenv()

MODEL = "claude-opus-5"
MAX_TOKENS = 16000
MAX_SEARCH_USES = 25
MAX_PAUSE_RESTARTS = 3


def _get_client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY が設定されていません。.env を確認してください。"
        )
    return Anthropic(api_key=api_key)


def _run_with_web_search(prompt: str, *, client: Optional[Anthropic] = None) -> str:
    """web_searchツールを使い、Claudeの最終テキスト出力を返す。

    web_searchはAnthropicのサーバー上で自動実行されるサーバーサイドツールのため、
    クライアント側でツール結果を組み立てて送り返すループは不要。ただし検索回数が
    多い場合に`pause_turn`で応答が打ち切られることがあるため、その場合のみ
    会話を継続する。
    """
    client = client or _get_client()
    tools = [
        {
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": MAX_SEARCH_USES,
        }
    ]

    messages = [{"role": "user", "content": prompt}]
    restarts = 0
    while True:
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            tools=tools,
            messages=messages,
        ) as stream:
            message = stream.get_final_message()

        if message.stop_reason != "pause_turn":
            break
        restarts += 1
        if restarts > MAX_PAUSE_RESTARTS:
            raise RuntimeError("web_search: pause_turnが上限回数を超えました。")
        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": message.content},
        ]

    # ツール利用を伴う応答では、ツール呼び出し前に短い前置き（"I'll research..."等）
    # のtextブロックが入ることがある。JSON本体は必ず最後のtextブロックに入るため、
    # 全ブロックを連結せず最後のものだけを採用する。
    text_blocks = [block.text for block in message.content if block.type == "text"]
    if not text_blocks:
        raise RuntimeError(
            "web_search: レスポンスにtextブロックが含まれていません。"
            f"stop_reason={message.stop_reason}"
        )
    return text_blocks[-1].strip()


def _parse_json_output(raw_text: str) -> dict:
    """Claudeの出力からJSON部分を抽出してパースする。

    プロンプトでJSONのみ出力するよう指示しているが、念のためコードフェンス
    (```json ... ```) が付いた場合にも対応する。
    """
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


def find_domain_topic(*, client: Optional[Anthropic] = None) -> dict:
    """専門分野の最新トピックを1件調査し、日本語リサーチレポートと読み上げ・
    学習用の英語記事抜粋の両方を返す。

    戻り値のキー:
        topic_title, research_report_ja, article_title, article_source_url,
        article_source_name, article_published_date, english_text
    """
    prompt = build_prompt()
    raw_text = _run_with_web_search(prompt, client=client)
    return _parse_json_output(raw_text)
