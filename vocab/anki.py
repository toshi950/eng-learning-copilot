"""AnkiConnect経由でのノート追加（フェーズ5）

ローカルで起動中のAnki（AnkiConnectアドオン導入済み）に、生成したカード内容を
直接ノートとして追加する。AnkiConnectはAnki本体にHTTPサーバーを立てる
アドオンのため、実行時にAnkiが起動している必要がある。

前提（ユーザー側の事前準備・未実施）：
1. Ankiで「ツール」→「アドオン」→「アドオンを取得」→ コード 2055492159
   （AnkiConnect）を入力してインストール
2. Anki再起動
3. デフォルトのポート（8765）を変更していない前提。変更している場合は
   .env の ANKI_CONNECT_URL で上書きする

ノートタイプはAnkiの標準「Basic」（フィールド名 Front/Back）を前提とする。
カスタマイズ済みの場合はフィールド名を要調整。
"""
from __future__ import annotations

import os
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_URL = "http://127.0.0.1:8765"
DEFAULT_DECK = "English::Vocab"
NOTE_TYPE = "Basic"


class AnkiConnectError(RuntimeError):
    pass


def _request(action: str, **params) -> object:
    url = os.environ.get("ANKI_CONNECT_URL", DEFAULT_URL)
    payload = {"action": action, "version": 6, "params": params}

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise AnkiConnectError(
            f"AnkiConnectに接続できません（{url}）。Ankiが起動しているか、"
            "AnkiConnectアドオンが導入されているか確認してください。"
        ) from exc

    result = response.json()
    if result.get("error"):
        raise AnkiConnectError(f"AnkiConnectエラー: {result['error']}")
    return result["result"]


def ensure_deck(deck_name: Optional[str] = None) -> None:
    """デッキが存在しなければ作成する（既存の場合は何もしない）。"""
    deck_name = deck_name or os.environ.get("ANKI_DECK_NAME", DEFAULT_DECK)
    _request("createDeck", deck=deck_name)


def add_card(
    card: dict, *, deck_name: Optional[str] = None, allow_duplicate: bool = False
) -> Optional[int]:
    """生成済みのカード内容を1件、Ankiにノートとして追加する。

    表面＝空所補充文（cloze_sentence）、裏面＝単語＋英語定義＋日本語訳
    （内部設計メモ「フェーズ5」のカード構成決定に対応）。

    重複判定はAnkiConnect側の仕組み（同一デッキ内でFront値が同一のノートを
    弾く）に委ねる（内部設計メモの「二段構え」の後段。前段は sync.py の
    処理済み行キャッシュ）。追加できた場合はノートID、重複等でスキップされた
    場合は None を返す。
    """
    deck_name = deck_name or os.environ.get("ANKI_DECK_NAME", DEFAULT_DECK)

    front = card["cloze_sentence"]
    back = f"<b>{card['word']}</b><br>{card['definition_en']}<br>{card['gloss_ja']}"

    note = {
        "deckName": deck_name,
        "modelName": NOTE_TYPE,
        "fields": {"Front": front, "Back": back},
        "options": {"allowDuplicate": allow_duplicate, "duplicateScope": "deck"},
        "tags": ["eng-learning-copilot"],
    }

    can_add = _request("canAddNotes", notes=[note])
    if not can_add[0]:
        return None

    note_ids = _request("addNotes", notes=[note])
    return note_ids[0]
