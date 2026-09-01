"""CLI: 英語学習教材の生成。

サブコマンド:
    daily    フェーズ3→1→2を通しで実行し、Vaultに「ノート＋音声」を出力する
    reading  英文を渡して読解教材だけを生成する（フェーズ1単体、従来の使い方）
    vocab    フェーズ5単体：Sheetsの未処理行からAnkiカードを生成・追加する

使い方:
    python main.py daily                  # 通常実行
    python main.py daily --dry-run        # RSS候補の確認のみ（APIコストなし）
    python main.py daily --from-cache     # 記事取得をやり直さず再開する
    python main.py daily --skip-audio     # 音声化を省く

    python main.py reading path/to/text.txt
    echo "..." | python main.py reading

    python main.py vocab                  # Sheets→Anki同期

`daily`は課金が発生する（実測で1回あたり約$0.60）。運用頻度の方針は内部設計メモを参照。
`vocab`はGoogleフォーム／Sheets作成・AnkiConnect導入・.env設定が前提（未実施の場合エラーになる。
内部設計メモ「フェーズ5」参照）。
"""
from __future__ import annotations

import argparse
import sys

from reading_material import generate_reading_material
from reading_material.generate import save_to_output_dir


def _read_text(path: str | None) -> str:
    if path:
        with open(path, encoding="utf-8") as f:
            return f.read()
    return sys.stdin.read()


def cmd_reading(args: argparse.Namespace) -> int:
    text = _read_text(args.file)
    if not text.strip():
        print(
            "英語の長文テキストを引数のファイルパスまたは標準入力で渡してください。",
            file=sys.stderr,
        )
        return 1

    result = generate_reading_material(text)
    print(result)

    saved_path = save_to_output_dir(result, text)
    if saved_path:
        print(f"---\n保存先: {saved_path}", file=sys.stderr)
    return 0


def cmd_daily(args: argparse.Namespace) -> int:
    from pipeline import dry_run, run

    if args.dry_run:
        candidates = dry_run()
        print(f"RSS候補 {len(candidates)}件（APIコストなし）\n")
        for i, c in enumerate(candidates, 1):
            print(f"{i:2d}. [{c['feed']}] {c['title']}")
            print(f"    {c['source'] or '媒体不明'} / {c['published'] or '日付不明'}")
        return 0

    result = run(from_cache=args.from_cache, skip_audio=args.skip_audio)
    print("\n完了しました。")
    print(f"  ノート: {result['note']}")
    if result["audio"]:
        print(f"  音声  : {result['audio']}")
    return 0


def cmd_vocab(args: argparse.Namespace) -> int:
    from vocab import sync_vocab

    result = sync_vocab()
    print(
        f"完了しました。"
        f"追加 {result['added']}件 / 重複スキップ {result['skipped_duplicate']}件"
        f"（未処理 {result['new_rows']}件 / シート総行数 {result['total_rows']}件）"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="英語学習教材の生成")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_daily = subparsers.add_parser(
        "daily", help="フェーズ3→1→2を通しで実行してVaultに出力する"
    )
    p_daily.add_argument(
        "--dry-run",
        action="store_true",
        help="RSS候補の確認のみ行う（APIコストなし）",
    )
    p_daily.add_argument(
        "--from-cache",
        action="store_true",
        help="記事取得をやり直さず、前回取得した記事から再開する",
    )
    p_daily.add_argument("--skip-audio", action="store_true", help="音声化を省く")
    p_daily.set_defaults(func=cmd_daily)

    p_reading = subparsers.add_parser(
        "reading", help="英文から読解教材だけを生成する（フェーズ1単体）"
    )
    p_reading.add_argument("file", nargs="?", help="英文ファイル（省略時は標準入力）")
    p_reading.set_defaults(func=cmd_reading)

    p_vocab = subparsers.add_parser(
        "vocab", help="Sheetsの未処理行からAnkiカードを生成・追加する（フェーズ5）"
    )
    p_vocab.set_defaults(func=cmd_vocab)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
