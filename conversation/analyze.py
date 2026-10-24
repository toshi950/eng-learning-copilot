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

カード設計の変更（2026-10-24）：空欄の答えが節全体になり、正解が1つに決まらない
カードが多く、間違いと復習の量を押し上げていたため、空欄を誤りの核になる最小の
チャンク（原則1〜4語）に絞り、英語のヒント（hint_en）と自然な別解（alt_answers）を
加えた（日本語のヒントは、原義から離れやすいため使わない）。

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
import sys
from pathlib import Path
from typing import Optional

from anthropic import Anthropic
from dotenv import load_dotenv

from anki import hint_problem

load_dotenv()

MODEL = "claude-opus-5"
# 出力の上限。長い対話では、検証用のcleaned_dialogue（対話全文の写し）だけで4,000
# トークンを超え、JSONの途中で出力が切れる不具合があったため、16,000に引き上げた
# （2026-10-24）。あわせて、カード（cards）を先に、cleaned_dialogueを最後に出力させ、
# 万一途中で切れてもカードは取れるようにしている。
MAX_TOKENS = 16000
# 1回の対話から作る最大カード数。復習の量は、ここで絞らず、Ankiの「1日の新規カード数」
# で調整する（ここで絞るとカードが永久に作られないが、Anki側なら出すペースを遅らせる
# だけで済むため。2026-10-24に一度3に下げたが、5に戻した）。
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

【カードの作り方（重要）】
- 空欄にする対象は、学習者の誤りの核になる「最小のチャンク」とする（原則1〜4語。\
固定の言い回しでも最大5語まで）。節や文全体を空欄にしない。誤りが文の構造にある場合は、\
文の枠を残し、核になる語（前置詞・冠詞・時制・助動詞など）だけを空欄にする。
- cloze_sentence は20語以内、空欄は1つだけ。
- hint_en に、答えを含まない英語の短いヒントを入れる（平易な英語で12語以内。\
意味、または誤りの種類。例："to make something better or more impressive"、\
"the preposition used before a workplace"）。日本語のヒントは入れない。\
答えの語自体と、その活用形・派生語をヒントに含めない。
- alt_answers に、同じ空欄に入りうる自然な別解を0〜3個入れる。別解が複数あり得る場合は、\
文脈かヒントで絞る。それでも絞れない場合は、別解を必ず示す。
- word は、空欄に入る答えそのもの（核のチャンク）にする。

【件数】
本質的な誤り・不自然さが見つかった分だけ、最大{max_phrases}件まで。\
無理に{max_phrases}件に水増ししないでください。該当が少ない、またはゼロでも構いません。

【書き起こし全文】
{transcript}

【出力形式】
以下のキーを持つJSONオブジェクトを1つだけ出力してください（他のテキストは一切含めない）。\
**キーの順序は、必ず "cards" を先、"cleaned_dialogue" を最後にしてください。**
{{
  "cards": [
    {{
      "word": "空欄に入る答え（誤りの核になる最小のチャンク、原則1〜4語、英語）",
      "cloze_sentence": "答えを含む自然な文（20語以内）を、答えの部分だけ ___ に置き換えたもの（空欄は1つ）",
      "hint_en": "答えを含まない英語の短いヒント（12語以内。意味、または誤りの種類）",
      "alt_answers": ["同じ空欄に入りうる自然な別解（0〜3個）"],
      "definition_en": "その表現の意味を表す簡潔な英語定義（1文）",
      "gloss_ja": "簡潔な日本語訳（1行）",
      "note_ja": "学習者が実際に言った不自然な表現の引用と、何が不自然だったかの簡潔な説明（日本語）"
    }}
  ],
  "cleaned_dialogue": "上記タスク1で抽出した、UIノイズを除いた実際の対話部分のみのテキスト（学習者・対話相手双方の発話。検証用に出力するもので、この内容自体はAnkiカードにはしない）"
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


def _parse_result(raw_text: str, stop_reason: Optional[str]) -> dict:
    """モデルの出力をJSONとして読み取る。

    出力が上限（max_tokens）で途中で切れた場合でも、cardsが先に出力されていれば
    カードだけを救出する（cleaned_dialogueは検証用の副産物のため、欠けてもよい）。
    """
    try:
        return json.loads(_extract_json_text(raw_text))
    except json.JSONDecodeError as exc:
        if stop_reason != "max_tokens":
            raise

        marker = raw_text.find('"cleaned_dialogue"')
        first_brace = raw_text.find("{")
        if marker == -1 or first_brace == -1 or marker < first_brace:
            raise RuntimeError(
                "出力が上限で途中で切れ、カードを取り出せませんでした"
                "（対話が長すぎる可能性があります。MAX_TOKENSを引き上げるか、"
                "対話を短くしてください）"
            ) from exc

        head = raw_text[first_brace:marker].rstrip().rstrip(",")
        try:
            result = json.loads(head + "\n}")
        except json.JSONDecodeError:
            result = {}
        if "cards" not in result:
            raise RuntimeError(
                "出力が上限で途中で切れ、カードを取り出せませんでした"
            ) from exc
        result["cleaned_dialogue"] = "（出力が上限で途中で切れたため、検証用の対話全文は保存していません）"
        print("[警告] 出力が上限で途中で切れたため、カードのみ取り出しました", file=sys.stderr)
        return result


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
    result = _parse_result(raw_text, getattr(message, "stop_reason", None))

    # UIノイズ除去後の対話部分を保存（毎回上書き）。実際に何が「対話」として
    # 認識され、何がノイズとして除外されたかを目視確認できるようにするため。
    cleaned_dialogue = result.get("cleaned_dialogue", "")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CLEANED_DIALOGUE_PATH.write_text(cleaned_dialogue, encoding="utf-8")

    # 英語の意味ヒント（hint_en）は必須。欠けている・答えが含まれている場合は、
    # 英語定義（definition_en）で代用し、それも使えなければそのカードは作らない。
    cards = []
    for card in result.get("cards", []):
        word = card.get("word", "")
        if hint_problem(card, word) is not None:
            fallback = {**card, "hint_en": card.get("definition_en", "")}
            if hint_problem(fallback, word) is not None:
                print(f"[警告] 英語のヒントを付けられないためカードを除外: {word}", file=sys.stderr)
                continue
            card = fallback
        cards.append(card)
    return cards
