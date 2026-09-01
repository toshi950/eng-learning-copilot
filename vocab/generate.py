"""単語カード内容の生成（フェーズ5）

Sheetsから取得した「単語/イディオム」＋「それを含む原文（学習者の実際の
転記）」から、Ankiカード用の内容（空所補充文・英語定義・簡潔な日本語訳）を
Claude Haikuで生成する。

モデル選定：フォーマット整形・簡潔な定義生成のみで深い推論を要さないため
claude-haiku-4-5を使う（内部設計メモのモデル選定を参照。フェーズ1・3の
claude-opus-5とは異なる）。

学習効果の設計根拠（内部設計メモ「フェーズ5」参照）：
- 日本語訳オンリーのカードはL1媒介依存を招き汎用的な意味理解に繋がりにくいため、
  英語定義を主・日本語訳は補助（1行）にとどめる
- 単語単体より実文脈での提示が定着率が高いため、Sheets側で転記された原文を
  そのまま使う（LLMによる文脈生成のフォールバックは不要）
- 穴埋め（cloze deletion）形式が単純な暗記より想起の質を高める
- 画像は不採用（Openverse APIでの実証検証の結果、対象語彙〈監査・会計等の
  抽象語・専門語が中心〉には機能しないと判断。内部設計メモ参照）
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 1024

PROMPT_TEMPLATE = """あなたは英語学習者向けの単語カード編集者です。以下の単語/イディオムと、\
それを含む原文（学習者が実際に読んだ文からの転記）をもとに、Ankiカード用の内容を\
JSON形式で1つだけ出力してください。JSON以外のテキスト（前置き・説明等）は一切\
含めないでください。

単語/イディオム: {word}
原文: {sentence}

出力するJSON:
{{
  "word": "{word}",
  "cloze_sentence": "原文中の単語/イディオム部分を ___ に置き換えた文（原文の他の部分は変更しない）",
  "definition_en": "この文脈での意味を表す簡潔な英語定義（1文、平易な英語で）",
  "gloss_ja": "簡潔な日本語訳（1行。直訳ではなく文脈に即した訳）"
}}
"""


def _get_client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY が設定されていません。.env を確認してください。"
        )
    return Anthropic(api_key=api_key)


def _extract_json_text(raw_text: str) -> str:
    """Claudeの出力からJSON部分を抽出する。

    フェーズ3（sourcing/generate.py の _extract_json_text）で、LLMが前置き
    コメント付きでJSONを返し json.loads が失敗する不具合が実際に発生し
    修正した経緯があるため（内部設計メモ参照）、同じ頑健な抽出方式を
    最初から採用する：
      1. テキスト中のどこにあってもよいコードフェンスを探す
      2. 見つからなければ最初の "{" から最後の "}" までを切り出す
      3. それでも見つからなければ元のテキストのまま返す
    """
    text = raw_text.strip()

    fence_match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1]

    return text


def generate_card(word: str, sentence: str, *, client: Optional[Anthropic] = None) -> dict:
    """単語/イディオムと原文から、Ankiカード用の内容を生成する。

    戻り値: {"word": str, "cloze_sentence": str, "definition_en": str, "gloss_ja": str}
    """
    client = client or _get_client()
    prompt = PROMPT_TEMPLATE.format(word=word, sentence=sentence)

    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()

    text_blocks = [block.text for block in message.content if block.type == "text"]
    raw_text = "\n".join(text_blocks).strip()
    return json.loads(_extract_json_text(raw_text))
