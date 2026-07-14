from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

from openai import OpenAI
import requests


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0 Safari/537.36"
)


@dataclass
class NewsItem:
    title: str
    source: str
    published_at: str | None
    summary: str | None
    url: str | None
    zh_title: str | None = None
    zh_summary: str | None = None

    def to_payload(self) -> dict:
        return {
            "title": self.title,
            "source": self.source,
            "published_at": self.published_at,
            "summary": self.summary,
            "url": self.url,
            "zh_title": self.zh_title,
            "zh_summary": self.zh_summary,
        }


@dataclass
class NewsSection:
    key: str
    title: str
    items: list[NewsItem]

    def to_payload(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "items": [item.to_payload() for item in self.items],
        }


@dataclass
class NewsDigest:
    highlights: list[str]
    sections: list[NewsSection]
    errors: list[str]

    def to_payload(self) -> dict:
        return {
            "highlights": self.highlights,
            "sections": [section.to_payload() for section in self.sections],
            "errors": self.errors,
        }


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _clean_text(text: str | None) -> str:
    if not text:
        return ""
    cleaned = html.unescape(text)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _normalize_title(title: str) -> str:
    title = _clean_text(title)
    title = re.sub(r"\s+-\s+(Reuters|Bloomberg|CNBC|MarketWatch|Barron's)$", "", title)
    return title


def _parse_published_at(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    try:
        return parsedate_to_datetime(raw_value).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return raw_value


def _parse_rss_items(xml_text: str) -> list[NewsItem]:
    root = ET.fromstring(xml_text)
    items: list[NewsItem] = []
    for node in root.findall(".//channel/item"):
        title = _normalize_title(node.findtext("title"))
        if not title:
            continue

        source = _clean_text(node.findtext("source")) or "公开新闻源"
        description = _clean_text(node.findtext("description"))
        link = _clean_text(node.findtext("link")) or None
        published_at = _parse_published_at(node.findtext("pubDate"))

        items.append(
            NewsItem(
                title=title,
                source=source,
                published_at=published_at,
                summary=description or None,
                url=link,
            )
        )
    return items


def _fetch_feed(url: str, timeout: int = 12) -> list[NewsItem]:
    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return _parse_rss_items(response.text)


def fetch_news_digest(config_data: dict | None) -> NewsDigest | None:
    if not config_data or not config_data.get("sections"):
        return None

    sections: list[NewsSection] = []
    highlights: list[str] = []
    errors: list[str] = []

    for section_config in config_data.get("sections", []):
        key = section_config.get("key", "news")
        title = section_config.get("title", key)
        max_items = int(section_config.get("max_items", 2))
        items: list[NewsItem] = []
        seen_titles: set[str] = set()

        for feed in section_config.get("feeds", []):
            url = feed.get("url")
            if not url:
                continue
            try:
                feed_items = _fetch_feed(url)
            except Exception as error:  # pragma: no cover - network path
                errors.append(f"{title}：{error}")
                continue

            for item in feed_items:
                normalized = item.title.casefold()
                if normalized in seen_titles:
                    continue
                seen_titles.add(normalized)
                items.append(item)
                if len(items) >= max_items:
                    break
            if len(items) >= max_items:
                break

        if not items:
            continue

        sections.append(NewsSection(key=key, title=title, items=items))
        first_item = items[0]
        highlights.append(f"{title}：{first_item.title}")

    return NewsDigest(highlights=highlights, sections=sections, errors=errors)


def localize_news_digest_with_deepseek(
    news_digest: NewsDigest, api_key: str, model: str
) -> NewsDigest:
    if not news_digest.sections:
        return news_digest

    serializable_items: list[dict] = []
    for section_index, section in enumerate(news_digest.sections):
        for item_index, item in enumerate(section.items):
            serializable_items.append(
                {
                    "section_index": section_index,
                    "item_index": item_index,
                    "section_title": section.title,
                    "title": item.title,
                    "summary": item.summary,
                    "source": item.source,
                }
            )

    if not serializable_items:
        return news_digest

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    prompt = f"""
你是一名中文财经编辑。请把下面这些英文财经新闻标题翻译并压缩成中文晨报可直接引用的短句。

要求：
1. 仅基于提供的 title 和 summary 翻译，不得补充新事实。
2. 输出中文，避免英文字母，除非是必须保留的缩写如 AI、ETF、CPI。
3. 每条只返回：
   - section_index
   - item_index
   - zh_title
4. `zh_title` 要像晨报 bullet 标题，长度尽量控制在 14 到 32 个汉字。
5. 输出必须是 JSON 数组，不要使用 Markdown 代码块，不要添加解释。

输入：
{json.dumps(serializable_items, ensure_ascii=False)}
""".strip()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是严谨的中文财经新闻编辑。"},
            {"role": "user", "content": prompt},
        ],
        stream=False,
    )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        return news_digest

    translated_items = json.loads(_strip_code_fence(content))
    translated_map = {
        (int(item["section_index"]), int(item["item_index"])): str(item["zh_title"]).strip()
        for item in translated_items
        if item.get("zh_title")
    }

    localized_sections: list[NewsSection] = []
    localized_highlights: list[str] = []
    for section_index, section in enumerate(news_digest.sections):
        localized_items: list[NewsItem] = []
        for item_index, item in enumerate(section.items):
            zh_title = translated_map.get((section_index, item_index))
            localized_items.append(
                NewsItem(
                    title=item.title,
                    source=item.source,
                    published_at=item.published_at,
                    summary=item.summary,
                    url=item.url,
                    zh_title=zh_title,
                    zh_summary=item.zh_summary,
                )
            )

        localized_section = NewsSection(
            key=section.key,
            title=section.title,
            items=localized_items,
        )
        localized_sections.append(localized_section)
        if localized_items:
            first_item = localized_items[0]
            localized_highlights.append(
                f"{section.title}：{first_item.zh_title or first_item.title}"
            )

    return NewsDigest(
        highlights=localized_highlights or news_digest.highlights,
        sections=localized_sections,
        errors=news_digest.errors,
    )
