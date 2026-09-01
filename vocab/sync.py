"""単語帳同期の実行（フェーズ5）

Sheets（発見）→ Haiku（カード生成）→ AnkiConnect（追加）の3ステップを
接続する薄いオーケストレーション層。フェーズ3の「RSS発見→LLM執筆」、
フェーズ4の「フェーズ3→1→2の接続」と同じ設計思想（機能単位を積み上げて
繋ぐ）を踏襲する。

処理済み行は .cache/vocab_processed_rows.json に行番号のリストとして記録し、
次回実行時にSheets API問い合わせ済みの行へのLLM再呼び出しを防ぐ（フェーズ4の
.cache/last_article.json と同じ考え方）。AnkiConnect側の重複チェック
（同一デッキ内でFront値が同一のノートを弾く）と合わせた二段構え。
"""
from __future__ import annotations

import json
from pathlib import Path

from .anki import add_card, ensure_deck
from .generate import generate_card
from .sheets import fetch_rows

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
CACHE_PATH = CACHE_DIR / "vocab_processed_rows.json"


def _load_processed_rows() -> set[int]:
    if not CACHE_PATH.exists():
        return set()
    return set(json.loads(CACHE_PATH.read_text(encoding="utf-8")))


def _save_processed_rows(processed: set[int]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(sorted(processed), ensure_ascii=False), encoding="utf-8"
    )


def sync_vocab() -> dict:
    """未処理のSheets行からAnkiカードを生成・追加する。

    戻り値: {"added": int, "skipped_duplicate": int, "total_rows": int, "new_rows": int}
    """
    rows = fetch_rows()
    processed = _load_processed_rows()
    new_rows = [r for r in rows if r["row_number"] not in processed]

    ensure_deck()

    added = 0
    skipped_duplicate = 0

    for row in new_rows:
        card = generate_card(row["word"], row["sentence"])
        note_id = add_card(card)

        if note_id is not None:
            added += 1
        else:
            skipped_duplicate += 1

        processed.add(row["row_number"])

    _save_processed_rows(processed)

    return {
        "added": added,
        "skipped_duplicate": skipped_duplicate,
        "total_rows": len(rows),
        "new_rows": len(new_rows),
    }
