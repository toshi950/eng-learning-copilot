"""CLI: 英語長文テキストを渡すと、本文＋Chunk Reading＋構文解析テーブルを標準出力に表示する。

READING_MATERIAL_OUTPUT_DIR が設定されていれば、同じ内容をMarkdownファイルとして
そのディレクトリにも保存する。

使い方:
    python main.py path/to/text.txt
    echo "..." | python main.py
"""
from __future__ import annotations

import sys

from reading_material import generate_reading_material
from reading_material.generate import save_to_output_dir


def _read_input() -> str:
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            return f.read()
    return sys.stdin.read()


def main() -> None:
    text = _read_input()
    if not text.strip():
        print(
            "英語の長文テキストを引数のファイルパスまたは標準入力で渡してください。",
            file=sys.stderr,
        )
        sys.exit(1)

    result = generate_reading_material(text)
    print(result)

    saved_path = save_to_output_dir(result, text)
    if saved_path:
        print(f"---\n保存先: {saved_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
