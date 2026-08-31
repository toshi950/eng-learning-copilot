"""RSSフィードからの記事候補収集（フェーズ3の前段）

LLMに探索的なWeb検索をさせると、検索結果が文脈に累積したまま内部ターンごとに
再処理されるため、コストが検索回数に対してほぼ二乗で効く（実測：検索12回で
入力625Kトークン／1回あたり約$1.5）。そこで「何が起きているか」の発見だけを
RSSで肩代わりし、LLMには特定済みの記事の取得とレポート執筆だけを担当させる。

Google News RSSを主軸にしているのは、出版社の個別RSSが軒並み終了している
（PCAOB・IFRS・FASB・IIA・Journal of Accountancy はいずれも404/403）一方で、
Google News RSSはクエリ単位で安定して取得でき、Google Alertsと同じ仕組みで
あるため、利用者が自分のアラートを後から追加できるという利点があるため。

個人用のフィード（自分で設定したGoogle Alerts等）は、環境変数
`SOURCING_EXTRA_FEEDS`（カンマまたは改行区切りのURL）で追加できる。
"""
from __future__ import annotations

import html
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional

import feedparser
from dotenv import load_dotenv

load_dotenv()

RECENT_DAYS = 30
MAX_CANDIDATES = 40
MAX_SUMMARY_CHARS = 300


def _google_news(query: str, *, japanese: bool = False) -> str:
    q = urllib.parse.quote(query)
    if japanese:
        return f"https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


# 専門分野（内部設計メモの「ペルソナ」定義）に対応するクエリ群。
DEFAULT_FEEDS: dict[str, str] = {
    "監査とAI（英）": _google_news("audit artificial intelligence PCAOB OR IAASB"),
    "内部統制と生成AI（英）": _google_news("internal control generative AI COSO"),
    "内部監査（英）": _google_news("internal audit artificial intelligence governance"),
    "IFRS・会計基準（英）": _google_news("IFRS accounting standard IASB"),
    "ITガバナンス・IT監査（英）": _google_news(
        "IT general controls OR ITGC OR SOX compliance audit technology risk"
    ),
    "監査と生成AI（日）": _google_news("監査 生成AI 内部統制", japanese=True),
    "会計基準（日）": _google_news("会計基準 ASBJ 企業会計", japanese=True),
    "経理DX・税務（日）": _google_news("経理DX 税務 電子帳簿保存法", japanese=True),
}


def _extra_feeds() -> dict[str, str]:
    """環境変数から個人用フィード（自分で設定したGoogle Alerts等）を読み込む。"""
    raw = os.environ.get("SOURCING_EXTRA_FEEDS", "")
    urls = [u.strip() for u in re.split(r"[,\n]", raw) if u.strip()]
    return {f"追加フィード{i + 1}": url for i, url in enumerate(urls)}


def _clean(text: str, *, limit: Optional[int] = None) -> str:
    text = re.sub(r"(?s)<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    if limit and len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def _published_at(entry) -> Optional[datetime]:
    parsed = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=timezone.utc)


def collect_candidates(
    *, recent_days: int = RECENT_DAYS, max_candidates: int = MAX_CANDIDATES
) -> list[dict]:
    """設定済みのRSSフィードから、直近の記事候補を集めて返す。

    戻り値の各要素: title, source, url, summary, published, feed
    新しい順に並び、URLで重複排除したうえで max_candidates 件までに制限する。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=recent_days)
    feeds = {**DEFAULT_FEEDS, **_extra_feeds()}

    seen_urls: set[str] = set()
    candidates: list[dict] = []

    for feed_name, url in feeds.items():
        try:
            parsed = feedparser.parse(url)
        except Exception:
            # 1つのフィードの失敗で全体を止めない
            continue

        for entry in parsed.entries:
            link = getattr(entry, "link", "")
            if not link or link in seen_urls:
                continue
            published = _published_at(entry)
            if published and published < cutoff:
                continue
            seen_urls.add(link)

            source = ""
            if hasattr(entry, "source"):
                source = getattr(entry.source, "title", "") or ""
            candidates.append(
                {
                    "title": _clean(getattr(entry, "title", "")),
                    "source": source,
                    "url": link,
                    "summary": _clean(
                        getattr(entry, "summary", ""), limit=MAX_SUMMARY_CHARS
                    ),
                    "published": published.strftime("%Y-%m-%d") if published else "",
                    "feed": feed_name,
                }
            )

    candidates.sort(key=lambda c: c["published"], reverse=True)
    return candidates[:max_candidates]


def _is_redundant_summary(summary: str, title: str) -> bool:
    """Google News RSSの概要はタイトルの再掲であることが多いため、その判定。"""
    if not summary:
        return True
    core = re.sub(r"\W+", "", summary).lower()
    return re.sub(r"\W+", "", title).lower().startswith(core[:40])


def format_candidates(candidates: list[dict]) -> str:
    """候補一覧を、プロンプトに埋め込むテキストへ整形する。

    概要がタイトルの再掲にすぎない場合は省略し、入力トークンを節約する。
    """
    lines = []
    for i, c in enumerate(candidates, 1):
        line = (
            f"{i}. [{c['feed']}] {c['title']}\n"
            f"   媒体: {c['source'] or '不明'} / 公開日: {c['published'] or '不明'}"
        )
        if not _is_redundant_summary(c["summary"], c["title"]):
            line += f"\n   概要: {c['summary']}"
        lines.append(line)
    return "\n".join(lines)
