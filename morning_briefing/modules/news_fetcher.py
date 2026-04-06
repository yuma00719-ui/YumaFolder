"""
news_fetcher.py — RSS フィードからニュース記事を取得するモジュール

取得フロー:
  1. 各カテゴリの RSS フィード URL からフィードを取得
  2. 当日の記事を抽出（フィードに日付がない場合は全件対象）
  3. 記事リストを返す（Claude が最重要1本を選定）
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse

import feedparser
import requests

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))


@dataclass
class Article:
    title: str
    url: str
    summary: str
    published: Optional[datetime]
    source: str
    category: str

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "published": self.published.isoformat() if self.published else None,
            "source": self.source,
            "category": self.category,
        }


def _parse_entry_date(entry) -> Optional[datetime]:
    """feedparser の entry から published datetime を取得する。"""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc).astimezone(JST)
            except Exception:
                pass
    return None


def _is_today(dt: Optional[datetime]) -> bool:
    """日付が今日（JST）かどうかを判定する。日付不明の場合は True を返す。"""
    if dt is None:
        return True
    today = datetime.now(JST).date()
    return dt.date() == today


def _fetch_feed(feed_url: str, max_articles: int, category: str, source_name: str,
                retry_max: int = 3, retry_wait: int = 5) -> list[Article]:
    """1つの RSS フィードから記事を取得する。"""
    articles: list[Article] = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; MorningBriefingBot/1.0; "
            "+https://github.com/your-repo)"
        )
    }

    for attempt in range(1, retry_max + 1):
        try:
            resp = requests.get(feed_url, headers=headers, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            break
        except Exception as e:
            logger.warning("フィード取得失敗 (試行 %d/%d): %s — %s", attempt, retry_max, feed_url, e)
            if attempt < retry_max:
                time.sleep(retry_wait)
            else:
                logger.error("フィード取得を断念: %s", feed_url)
                return articles

    for entry in feed.entries[:max_articles * 2]:  # 多めに取ってフィルタリング
        published = _parse_entry_date(entry)
        if not _is_today(published):
            continue

        title = getattr(entry, "title", "").strip()
        url = getattr(entry, "link", "").strip()
        summary = (
            getattr(entry, "summary", "")
            or getattr(entry, "description", "")
            or ""
        ).strip()

        # HTML タグを簡易除去
        import re
        summary = re.sub(r"<[^>]+>", "", summary).strip()
        summary = summary[:500]  # 500文字で切り詰め

        if not title or not url:
            continue

        articles.append(Article(
            title=title,
            url=url,
            summary=summary,
            published=published,
            source=source_name,
            category=category,
        ))

        if len(articles) >= max_articles:
            break

    logger.info("フィード %s から %d 件取得", source_name, len(articles))
    return articles


def fetch_news_by_category(
    category_config: dict,
    category_key: str,
    retry_max: int = 3,
    retry_wait: int = 5,
) -> list[Article]:
    """
    カテゴリ設定に基づき複数フィードから記事を集約して返す。

    category_config: config.yaml の news_sources[category_key] に対応する dict
    category_key: "politics" / "economy" / "business"
    """
    all_articles: list[Article] = []
    max_articles: int = category_config.get("max_articles", 10)
    category_name: str = category_config.get("name", category_key)

    for feed_conf in category_config.get("feeds", []):
        feed_url = feed_conf.get("url", "")
        source_name = feed_conf.get("name", urlparse(feed_url).netloc)

        if not feed_url:
            continue

        fetched = _fetch_feed(
            feed_url=feed_url,
            max_articles=max_articles,
            category=category_name,
            source_name=source_name,
            retry_max=retry_max,
            retry_wait=retry_wait,
        )
        all_articles.extend(fetched)

    # 重複 URL を除去（先着優先）
    seen: set[str] = set()
    unique: list[Article] = []
    for a in all_articles:
        if a.url not in seen:
            seen.add(a.url)
            unique.append(a)

    logger.info("カテゴリ「%s」: 合計 %d 件（重複除去後）", category_name, len(unique))
    return unique[:max_articles]


def fetch_all_categories(news_sources_config: dict, retry_max: int = 3, retry_wait: int = 5) -> dict[str, list[Article]]:
    """
    全カテゴリのニュースを取得して返す。

    Returns:
        {
            "politics":  [Article, ...],
            "economy":   [Article, ...],
            "business":  [Article, ...],
        }
    """
    result: dict[str, list[Article]] = {}

    for category_key, category_conf in news_sources_config.items():
        articles = fetch_news_by_category(
            category_config=category_conf,
            category_key=category_key,
            retry_max=retry_max,
            retry_wait=retry_wait,
        )
        result[category_key] = articles

        if not articles:
            logger.warning("カテゴリ「%s」: 記事を取得できませんでした", category_key)

    return result
