"""パス表示用のユーティリティ。

標準出力・エラーメッセージに絶対パスをそのまま出すと、ホームディレクトリ以下の
ユーザー名が表記に含まれてしまう。表示目的ではホームディレクトリ部分を `~` に
置き換えることで、実用上必要な情報（どのフォルダ配下に保存されたか）を保ちつつ
ユーザー名を含まない表記にする。
"""
from __future__ import annotations

from pathlib import Path


def display_path(path: Path | str) -> str:
    """ホームディレクトリ配下なら `~/...` 形式で、それ以外はそのまま返す。"""
    p = Path(path)
    try:
        return "~/" + str(p.relative_to(Path.home()))
    except ValueError:
        return str(p)
