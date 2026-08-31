"""専門分野の情報収集（フェーズ3）

監査・会計・税務ドメインの最新トピックを1件調査し、日本語の長文リサーチレポートと、
読み上げ・学習用の英語記事抜粋（200〜600語）の両方を返す。

処理は2段構成：
  1. RSSフィードから記事候補を収集（`feeds.collect_candidates`、無料）
  2. その候補一覧を渡してLLMに1回だけ問い合わせ、トピック選定・裏取り・
     レポート執筆をまとめて行わせる

当初はLLMにweb_searchで探索から任せていたが、検索結果が文脈に累積したまま
内部ターンごとに再処理されるためコストが検索回数に対してほぼ二乗で効き、
1回あたり約$1.5に達した（実測：検索12回・入力625Kトークン）。発見の工程を
RSSに移し、LLM側のツール利用を少数回に絞ることでこれを圧縮している。

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

from .feeds import collect_candidates, format_candidates
from .prompts import build_prompt

load_dotenv()

# フェーズ1（読解教材生成）はOpusを使うが、フェーズ3は収集済みの候補を踏まえた
# リサーチ・要約タスクでモデルの推論力への依存度が低いため、Sonnetを使う
# （コスト最適化。詳細は内部設計メモ参照）。
MODEL = "claude-sonnet-5"
MAX_TOKENS = 16000
# 探索はRSS側で済んでいるため、ツール利用は「選んだ記事の本文取得と最小限の
# 裏取り」に限る。検索結果は毎ターン文脈に累積して再処理されコストが二乗で
# 効くため、ここを絞ることがコスト制御の主たるレバーになる。
MAX_SEARCH_USES = 5
MAX_FETCH_USES = 5
MAX_PAUSE_RESTARTS = 3
EFFORT = "medium"


def _get_client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY が設定されていません。.env を確認してください。"
        )
    return Anthropic(api_key=api_key)


def _run_with_web_search(
    prompt: str, *, client: Optional[Anthropic] = None
) -> tuple[str, dict]:
    """web_searchツールを使い、Claudeの最終テキスト出力と利用量情報を返す。

    web_searchはAnthropicのサーバー上で自動実行されるサーバーサイドツールのため、
    クライアント側でツール結果を組み立てて送り返すループは不要。ただし検索回数が
    多い場合に`pause_turn`で応答が打ち切られることがあるため、その場合のみ
    会話を継続する。

    戻り値の2要素目は、コストを実測するための累積トークン数・検索回数。
    """
    client = client or _get_client()
    tools = [
        {
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": MAX_SEARCH_USES,
        },
        {
            "type": "web_fetch_20260209",
            "name": "web_fetch",
            "max_uses": MAX_FETCH_USES,
        },
    ]

    usage = {"input_tokens": 0, "output_tokens": 0, "web_searches": 0, "requests": 0}
    messages = [{"role": "user", "content": prompt}]
    restarts = 0
    while True:
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            output_config={"effort": EFFORT},
            tools=tools,
            messages=messages,
        ) as stream:
            message = stream.get_final_message()

        usage["requests"] += 1
        usage["input_tokens"] += message.usage.input_tokens
        usage["output_tokens"] += message.usage.output_tokens
        usage["web_searches"] += sum(
            1
            for block in message.content
            if block.type == "server_tool_use"
            and block.name in ("web_search", "web_fetch")
        )

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
    return text_blocks[-1].strip(), usage


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

    まずRSSフィードから記事候補を集め（無料）、その一覧を踏まえてLLMに1回だけ
    問い合わせる。

    戻り値のキー:
        topic_title, research_report_ja, article_title, article_source_url,
        article_source_name, article_published_date, english_text
        _usage（実測コスト確認用：input_tokens・output_tokens・web_searches・
        requests・rss_candidates）
    """
    candidates = collect_candidates()
    if not candidates:
        raise RuntimeError(
            "RSSフィードから記事候補を取得できませんでした。"
            "ネットワーク接続、またはフィードURLの有効性を確認してください。"
        )

    prompt = build_prompt(format_candidates(candidates))
    raw_text, usage = _run_with_web_search(prompt, client=client)
    result = _parse_json_output(raw_text)
    usage["rss_candidates"] = len(candidates)
    result["_usage"] = usage
    return result
