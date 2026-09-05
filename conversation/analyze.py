"""対話ログからの改善フレーズ抽出（フェーズ6）

Gemini Live等での英会話の書き起こし全文（自由形式のテキスト、話者ラベルの
付き方は対話サービス依存）を受け取り、**学習者自身の発話**の中にあった
不自然な表現・文法ミスを特定し、改善後の自然な表現をAnkiカード用のJSONで
返す。Gemini（相手役）が使った良い表現は対象外とする（ユーザー指示、
2026-09-01。内部設計メモ「フェーズ6」参照）。

モデル選定：フェーズ1と同じ基準（誤りの検出・訂正の精度が学習効果に
直結するため）で claude-opus-5 を使う（フェーズ5のカード整形が
claude-haiku-4-5 なのとは異なる。内部設計メモ参照）。

出力はフェーズ5（vocab/generate.py）と同一のカードスキーマに正規化する
ことで、Anki連携（トップレベルの anki.py）をそのまま共有できるようにして
いる。note_ja には「元の不自然な表現＋何が不自然だったか」を入れる。

書き起こしはGemini Live等のページ全体を選択してコピー&ペーストしたものを
想定しており、対話と無関係な日本語UIテキスト等のノイズが混入しうる
（2026-09-05、ユーザー指摘）。このため、プロンプト側でノイズの無視を明示的に
指示するとともに、LLMにノイズ除去後の対話部分（cleaned_dialogue）も
出力させ、`.cache/last_conversation_cleaned.txt`に毎回保存する。実際に何が
「対話」として認識されたか（＝ノイズが正しく除外されたか）を目視確認できる
ようにするための、検証用の副産物。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-5"
MAX_TOKENS = 4000
DEFAULT_MAX_PHRASES = 5

# UIノイズ除去後の対話部分を毎回ここに保存する（デバッグ・検証用。
# 画面全体コピー&ペーストによるノイズ混入の懸念に対応、2026-09-05）。
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
CLEANED_DIALOGUE_PATH = CACHE_DIR / "last_conversation_cleaned.txt"

PROMPT_TEMPLATE = """あなたは英語学習者向けの会話コーチです。以下は、学習者が英会話サービス\
（Gemini Live等）と行った英会話の書き起こし全文です。話者ラベルの付き方は\
サービスによって異なりますが、文脈から「学習者自身の発話」と「対話相手（AI）の発話」を\
判別してください。

**注意**：この書き起こしは、対話サービスのページ全体を選択してコピー&ペーストした\
ものである可能性があります。そのため、実際の対話とは無関係な要素（日本語のメニュー・\
ボタン名・見出し・操作ログ等のUIテキスト）が混在していることがあります。これらは\
対話の一部ではないため完全に無視し、実際に交わされた英会話のやり取り部分だけを\
分析対象にしてください。

【あなたのタスク】
1. まず、書き起こし全文からUIノイズを除いた「実際の対話部分」だけを抽出してください。
2. その対話部分の中から、学習者自身の発話にあった不自然な表現・文法的な誤り・\
語彙選択のミスを特定し、それぞれについて自然な英語表現に改善したものをカード化\
してください。

【対象に含めないもの】
- 対話相手（Gemini等）が使った表現（どれだけ良い表現でも対象外）
- 単純な言い淀み（"um", "uh"程度）や、内容に関係ない相槌
- 意味は正しく通じており、些細な言い回しの違いに過ぎないもの

【件数】
本質的な誤り・不自然さが見つかった分だけ、最大{max_phrases}件まで。\
無理に{max_phrases}件に水増ししないでください。該当が少ない、またはゼロでも構いません。

【書き起こし全文】
{transcript}

【出力形式】
以下のキーを持つJSONオブジェクトを1つだけ出力してください（他のテキストは一切含めない）:
{{
  "cleaned_dialogue": "上記タスク1で抽出した、UIノイズを除いた実際の対話部分のみのテキスト（学習者・対話相手双方の発話。検証用に出力するもので、この内容自体はAnkiカードにはしない）",
  "cards": [
    {{
      "word": "改善後の自然な表現（英語）",
      "cloze_sentence": "改善後の表現を含む自然な文を、対象表現の部分だけ ___ に置き換えたもの",
      "definition_en": "その表現の意味を表す簡潔な英語定義（1文）",
      "gloss_ja": "簡潔な日本語訳（1行）",
      "note_ja": "学習者が実際に言った不自然な表現の引用と、何が不自然だったかの簡潔な説明（日本語）"
    }}
  ]
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
    """Claudeの出力からJSON部分を抽出する（sourcing/generate.py・vocab/generate.py
    と同じ頑健な抽出ロジック。内部設計メモ「フェーズ3」参照）。
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


def analyze_conversation(
    transcript: str,
    *,
    max_phrases: Optional[int] = None,
    client: Optional[Anthropic] = None,
) -> list[dict]:
    """対話全文から、学習者自身の不自然な表現を改善したカードのリストを生成する。

    戻り値: [{"word", "cloze_sentence", "definition_en", "gloss_ja", "note_ja"}, ...]
    （0件のこともある。該当なしの場合は無理に埋めない）
    """
    max_phrases = max_phrases or int(
        os.environ.get("CONVERSATION_MAX_PHRASES", DEFAULT_MAX_PHRASES)
    )
    client = client or _get_client()
    prompt = PROMPT_TEMPLATE.format(max_phrases=max_phrases, transcript=transcript.strip())

    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()

    text_blocks = [block.text for block in message.content if block.type == "text"]
    raw_text = "\n".join(text_blocks).strip()
    result = json.loads(_extract_json_text(raw_text))

    # UIノイズ除去後の対話部分を保存（毎回上書き）。実際に何が「対話」として
    # 認識され、何がノイズとして除外されたかを目視確認できるようにするため。
    cleaned_dialogue = result.get("cleaned_dialogue", "")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CLEANED_DIALOGUE_PATH.write_text(cleaned_dialogue, encoding="utf-8")

    return result.get("cards", [])
