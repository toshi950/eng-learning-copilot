"""成果物の組み立て（フェーズ4）

`sourcing`が返す記事メタデータと、`reading_material`が返す読解教材Markdownを
1つのノートに組み立てる。

`reading_material`の出力契約（本文＋Chunk Reading＋構文解析テーブルの2セクション）は
フェーズ1で確定済みのため変更せず、メタデータの付与はこの層で行う。Obsidianで扱う
前提のため、出典情報はYAMLフロントマターに置き、音声は`![[...]]`で埋め込む。
"""
from __future__ import annotations

import re
from datetime import datetime


def build_stem(article: dict, *, now: datetime | None = None, max_words: int = 6) -> str:
    """Markdownとmp3で共有するファイル名の幹を作る。

    拡張子だけを変えて対にすることで、ノート側から音声を`![[stem.mp3]]`で
    埋め込めるようにする。
    """
    now = now or datetime.now()
    words = re.findall(r"[A-Za-z0-9]+", article.get("article_title", ""))[:max_words]
    slug = "_".join(words) or "article"
    return f"{now.strftime('%Y%m%d_%H%M%S')}_{slug}"


def _escape_yaml(value: str) -> str:
    return str(value).replace('"', '\\"')


def build_note(article: dict, reading_material_md: str, *, audio_filename: str | None = None) -> str:
    """記事メタデータ＋読解教材＋音声リンクを1つのMarkdownノートに組み立てる。"""
    title = article.get("article_title", "")
    source_name = article.get("article_source_name", "")
    source_url = article.get("article_source_url", "")
    published = article.get("article_published_date", "")
    summary_ja = article.get("topic_summary_ja", "")

    front_matter = [
        "---",
        f'title: "{_escape_yaml(title)}"',
        f'source: "{_escape_yaml(source_name)}"',
        f'url: "{_escape_yaml(source_url)}"',
        f'published: "{_escape_yaml(published)}"',
        f'created: "{datetime.now().strftime("%Y-%m-%d")}"',
        "tags: [english-learning, reading-material]",
        "---",
    ]

    parts = ["\n".join(front_matter), ""]

    if summary_ja:
        parts.append("## 概要\n")
        parts.append(summary_ja)
        parts.append("")

    if audio_filename:
        parts.append("## 音声\n")
        parts.append(f"![[{audio_filename}]]")
        parts.append("")

    parts.append(reading_material_md.strip())
    parts.append("")

    source_line = f"出典: [{source_name}]({source_url})" if source_url else f"出典: {source_name}"
    if published:
        source_line += f"（{published}）"
    parts.append("---\n")
    parts.append(source_line)

    return "\n".join(parts) + "\n"
