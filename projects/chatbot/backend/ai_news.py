import asyncio
import logging
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from sqlalchemy import select

from db.database import create_sessionmaker_for, init_database
from db.models import AiNewsItem

logger = logging.getLogger("chatbot.ai_news")

DB_PATH = "db/data/app.db"
DEFAULT_INTERVAL_SECONDS = 24 * 60 * 60

RSS_SOURCES = [
    {"name": "OpenAI", "url": "https://openai.com/news/rss.xml"},
    {"name": "Anthropic", "url": "https://www.anthropic.com/news/rss.xml"},
    {"name": "Hugging Face", "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "Google DeepMind", "url": "https://deepmind.google/blog/rss.xml"},
    {"name": "NVIDIA AI", "url": "https://blogs.nvidia.com/blog/category/ai/feed/"},
]


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    return re.sub(r"<[^>]+>", "", text).strip() or None


def _safe_int_timestamp(raw: str | None) -> int:
    if not raw:
        return int(time.time())
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except Exception:
            return int(time.time())


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _find_text(node: ET.Element, names: list[str]) -> str:
    for child in node:
        if _local_name(child.tag) in names and child.text:
            return child.text.strip()
    return ""


def _fetch_feed(url: str, timeout: int = 12) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; AgentForgeNewsBot/1.0)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _parse_feed(xml_data: bytes, source_name: str) -> list[dict]:
    root = ET.fromstring(xml_data)
    items: list[dict] = []

    root_name = _local_name(root.tag)
    if root_name == "rss":
        channel = next((c for c in root if _local_name(c.tag) == "channel"), None)
        if channel is None:
            return []
        for item in channel:
            if _local_name(item.tag) != "item":
                continue
            title = _find_text(item, ["title"])
            link = _find_text(item, ["link"])
            summary = _find_text(item, ["description", "summary"])
            pub = _find_text(item, ["pubDate", "published", "updated"])
            if not title or not link:
                continue
            items.append(
                {
                    "title": title,
                    "url": link,
                    "summary": _strip_html(summary),
                    "published_at": _safe_int_timestamp(pub),
                    "source": source_name,
                }
            )
        return items

    if root_name == "feed":
        for entry in root:
            if _local_name(entry.tag) != "entry":
                continue
            title = _find_text(entry, ["title"])
            summary = _find_text(entry, ["summary", "content"])
            published = _find_text(entry, ["published", "updated"])
            link = ""
            for child in entry:
                if _local_name(child.tag) == "link":
                    href = child.attrib.get("href", "").strip()
                    if href:
                        link = href
                        break
            if not title or not link:
                continue
            items.append(
                {
                    "title": title,
                    "url": link,
                    "summary": _strip_html(summary),
                    "published_at": _safe_int_timestamp(published),
                    "source": source_name,
                }
            )
    return items


async def crawl_and_store_ai_news(limit_per_source: int = 12) -> dict:
    await init_database(DB_PATH)
    sessionmaker = create_sessionmaker_for(DB_PATH)

    inserted = 0
    updated = 0
    scanned = 0

    async with sessionmaker() as session:
        for source in RSS_SOURCES:
            source_name = source["name"]
            source_url = source["url"]
            try:
                xml_data = await asyncio.to_thread(_fetch_feed, source_url)
                items = _parse_feed(xml_data, source_name)[:limit_per_source]
            except Exception as exc:
                logger.warning("[ai_news] fetch failed for %s: %s", source_name, exc)
                continue

            for item in items:
                scanned += 1
                existing = await session.scalar(select(AiNewsItem).where(AiNewsItem.url == item["url"]))
                if existing:
                    existing.title = item["title"]
                    existing.summary = item["summary"]
                    existing.source = item["source"]
                    existing.published_at = item["published_at"]
                    existing.updated_at = int(time.time())
                    updated += 1
                else:
                    session.add(
                        AiNewsItem(
                            title=item["title"],
                            url=item["url"],
                            source=item["source"],
                            summary=item["summary"],
                            published_at=item["published_at"],
                            created_at=int(time.time()),
                            updated_at=int(time.time()),
                        )
                    )
                    inserted += 1

        await session.commit()

    result = {"sources": len(RSS_SOURCES), "scanned": scanned, "inserted": inserted, "updated": updated}
    logger.info("[ai_news] crawl done: %s", result)
    return result


async def run_daily_ai_news_job(interval_seconds: int = DEFAULT_INTERVAL_SECONDS):
    while True:
        try:
            await crawl_and_store_ai_news()
        except Exception as exc:
            logger.exception("[ai_news] scheduled crawl failed: %s", exc)
        await asyncio.sleep(interval_seconds)