"""会話フィードバック同期の実行（フェーズ6）

Sheets（対話ログ取得）→ Opus（改善フレーズ抽出）→ AnkiConnect（追加）の
3ステップを接続する薄いオーケストレーション層。vocab/sync.py（フェーズ5）と
同型の設計。1件の対話ログから複数枚のカードが生成される点がフェーズ5との
主な違い。

処理済み行は .cache/conversation_processed_rows.json に行番号のリストとして
記録し、次回実行時に同じ対話ログへのLLM再呼び出しを防ぐ。AnkiConnect側の
重複チェック（同一デッキ内でFront値が同一のノートを弾く）と合わせた二段構え
（vocab/sync.pyと同じ考え方。内部設計メモ参照）。
"""
from __future__ import annotations

import json
from pathlib import Path

from anki import add_card, ensure_deck

from .analyze import analyze_conversation
from .sheets import fetch_rows

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
CACHE_PATH = CACHE_DIR / "conversation_processed_rows.json"


def _load_processed_rows() -> set[int]:
    if not CACHE_PATH.exists():
        return set()
    return set(json.loads(CACHE_PATH.read_text(encoding="utf-8")))


def _save_processed_rows(processed: set[int]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(sorted(processed), ensure_ascii=False), encoding="utf-8"
    )


def sync_conversations() -> dict:
    """未処理の対話ログを分析し、改善フレーズのAnkiカードを生成・追加する。

    戻り値: {"added": int, "skipped_duplicate": int, "conversations_processed": int,
             "new_conversations": int, "cards_extracted": int}
    """
    rows = fetch_rows()
    processed = _load_processed_rows()
    new_rows = [r for r in rows if r["row_number"] not in processed]

    ensure_deck()

    added = 0
    skipped_duplicate = 0
    cards_extracted = 0

    for row in new_rows:
        cards = analyze_conversation(row["transcript"])
        cards_extracted += len(cards)

        for card in cards:
            note_id = add_card(card, extra_tags=["conversation-feedback"])
            if note_id is not None:
                added += 1
            else:
                skipped_duplicate += 1

        processed.add(row["row_number"])

    _save_processed_rows(processed)

    return {
        "added": added,
        "skipped_duplicate": skipped_duplicate,
        "conversations_processed": len(rows),
        "new_conversations": len(new_rows),
        "cards_extracted": cards_extracted,
    }
