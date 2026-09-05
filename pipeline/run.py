"""パイプライン実行（フェーズ4）

フェーズ3（記事選定）→フェーズ1（読解教材生成）→フェーズ2（音声化）を接続し、
Obsidian Vault内に「1ノート＋1音声」を出力する。

コスト面の設計：
- フェーズ3は1回あたり約$0.40、フェーズ1は約$0.20かかる（実測）。フェーズ3が成功した
  あとにフェーズ1で落ちると課金だけが無駄になるため、フェーズ3の結果は必ずキャッシュに
  保存し、`--from-cache`で再開できるようにしている。
- `--dry-run`はRSS収集（無料）のみを実行して候補一覧を表示する。
- 実行後は実測トークン数と概算コストを表示する。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from paths import display_path
from reading_material import generate_reading_material
from sourcing import find_article
from tts import synthesize_to_file

from .assemble import build_note, build_stem

load_dotenv()

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
CACHE_PATH = CACHE_DIR / "last_article.json"

# 実測値ベースの概算単価（内部設計メモ参照）
SONNET_INPUT_USD_PER_1M = 2.0
SONNET_OUTPUT_USD_PER_1M = 10.0
PHASE1_ESTIMATED_USD = 0.20


def _output_dir() -> Path:
    raw = os.environ.get("READING_MATERIAL_OUTPUT_DIR")
    if not raw:
        raise RuntimeError(
            "READING_MATERIAL_OUTPUT_DIR が設定されていません。.env を確認してください。"
        )
    path = Path(raw).expanduser()
    if not path.exists():
        # 誤設定に気づかずVault外へ書き込む事故を防ぐため、自動作成せず落とす
        raise RuntimeError(
            f"出力先が存在しません: {display_path(path)}\n"
            ".env の READING_MATERIAL_OUTPUT_DIR を確認してください。"
        )
    return path


def save_cache(article: dict) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(article)
    payload["_cached_at"] = datetime.now().isoformat(timespec="seconds")
    CACHE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return CACHE_PATH


def load_cache() -> dict:
    if not CACHE_PATH.exists():
        raise RuntimeError(
            f"キャッシュがありません: {display_path(CACHE_PATH)}\n"
            "--from-cache を付けずに実行して、まず記事を取得してください。"
        )
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))


def report_usage(usage: dict) -> str:
    """フェーズ3の実測利用量から概算コストを組み立てる。"""
    cost = (
        usage.get("input_tokens", 0) / 1_000_000 * SONNET_INPUT_USD_PER_1M
        + usage.get("output_tokens", 0) / 1_000_000 * SONNET_OUTPUT_USD_PER_1M
    )
    return (
        f"RSS候補 {usage.get('rss_candidates', '?')}件 / "
        f"ツール利用 {usage.get('tool_uses', '?')}回 / "
        f"入力 {usage.get('input_tokens', 0):,} tok / "
        f"出力 {usage.get('output_tokens', 0):,} tok / "
        f"フェーズ3概算 ${cost:.3f}"
    )


def run(
    *,
    from_cache: bool = False,
    skip_audio: bool = False,
    output_dir: Optional[Path] = None,
) -> dict:
    """パイプラインを実行し、生成物のパスを返す。

    戻り値: {"note": Path, "audio": Path | None, "article": dict}
    """
    output_dir = output_dir or _output_dir()

    # --- フェーズ3：記事の選定と取得 ---
    if from_cache:
        article = load_cache()
        print(f"[1/3] キャッシュから記事を読み込みました（{CACHE_PATH.name}）")
    else:
        print("[1/3] 記事を選定しています（RSS収集＋LLM）...")
        article = find_article()
        save_cache(article)
        usage = article.get("_usage", {})
        if usage:
            print(f"      {report_usage(usage)}")

    title = article.get("article_title", "(タイトル不明)")
    words = len(article.get("english_text", "").split())
    print(f"      {title}")
    print(f"      {article.get('article_source_name', '')} / {words} words")

    # --- フェーズ1：読解教材の生成 ---
    print("[2/3] 読解教材を生成しています（Opus、1〜2分かかります）...")
    english_text = article["english_text"]
    reading_md = generate_reading_material(english_text)
    print(f"      概算 ${PHASE1_ESTIMATED_USD:.2f}")

    stem = build_stem(article)

    # --- フェーズ2：音声化 ---
    audio_path: Optional[Path] = None
    if skip_audio:
        print("[3/3] 音声化をスキップしました（--skip-audio）")
    else:
        print("[3/3] 音声を合成しています（Google Cloud TTS、無料枠内）...")
        audio_path = synthesize_to_file(english_text, output_dir / f"{stem}.mp3")

    # --- 組み立てと保存 ---
    note = build_note(
        article, reading_md, audio_filename=audio_path.name if audio_path else None
    )
    note_path = output_dir / f"{stem}.md"
    note_path.write_text(note, encoding="utf-8")

    return {"note": note_path, "audio": audio_path, "article": article}


def dry_run() -> list[dict]:
    """RSS収集のみ実行して候補一覧を返す（APIコストなし）。"""
    from sourcing.feeds import collect_candidates

    return collect_candidates()
