"""Minimal research adapters for competitor pages and arXiv."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen


class ResearchAdapterError(RuntimeError):
    """Raised when competitor or arXiv fetches fail."""


@dataclass
class PageSummary:
    url: str
    title: str
    description: str
    text_excerpt: str


@dataclass
class ArxivEntry:
    arxiv_id: str
    title: str
    summary: str
    published_at: datetime
    category: str
    link: str


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_text: list[str] = []
        self._in_title = False
        self.meta_description = ""
        self.body_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() == "meta":
            name = attr_map.get("name", "").lower()
            prop = attr_map.get("property", "").lower()
            if name == "description" or prop == "og:description":
                if not self.meta_description:
                    self.meta_description = attr_map.get("content", "").strip()

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        if self._in_title:
            self.title_text.append(cleaned)
        self.body_text.append(cleaned)


class CompetitorResearchClient:
    def __init__(self, user_agent: str = "auto-pm/0.1.0") -> None:
        self._user_agent = user_agent

    def fetch_page_summary(self, url: str) -> PageSummary:
        request = Request(url, headers={"User-Agent": self._user_agent})
        try:
            with urlopen(request, timeout=20) as response:
                raw_html = response.read().decode("utf-8", errors="ignore")
        except HTTPError as exc:
            raise ResearchAdapterError(f"competitor fetch failed {exc.code} for {url}") from exc
        except URLError as exc:
            raise ResearchAdapterError(f"competitor fetch failed for {url}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ResearchAdapterError(f"competitor fetch timed out for {url}") from exc

        parser = _MetaParser()
        parser.feed(raw_html)
        body_text = " ".join(parser.body_text)
        excerpt = re.sub(r"\s+", " ", body_text)[:500].strip()
        title = " ".join(parser.title_text).strip() or urlparse(url).netloc
        description = html.unescape(parser.meta_description.strip())
        if not description:
            description = excerpt[:220]
        return PageSummary(url=url, title=title, description=description, text_excerpt=excerpt)


class ArxivResearchClient:
    def __init__(self, user_agent: str = "auto-pm/0.1.0") -> None:
        self._user_agent = user_agent

    def fetch_category_entries(self, category: str, max_results: int = 5) -> list[ArxivEntry]:
        query = quote_plus(f"cat:{category}")
        url = (
            "https://export.arxiv.org/api/query"
            f"?search_query={query}&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
        )
        request = Request(url, headers={"User-Agent": self._user_agent})
        try:
            with urlopen(request, timeout=20) as response:
                xml_text = response.read().decode("utf-8", errors="ignore")
        except HTTPError as exc:
            raise ResearchAdapterError(f"arXiv fetch failed {exc.code} for {category}") from exc
        except URLError as exc:
            raise ResearchAdapterError(f"arXiv fetch failed for {category}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ResearchAdapterError(f"arXiv fetch timed out for {category}") from exc

        namespace = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        root = ET.fromstring(xml_text)
        entries: list[ArxivEntry] = []
        for entry in root.findall("atom:entry", namespace):
            entry_id = _text(entry.find("atom:id", namespace))
            title = _compact(_text(entry.find("atom:title", namespace)))
            summary = _compact(_text(entry.find("atom:summary", namespace)))
            published_raw = _text(entry.find("atom:published", namespace))
            published = datetime.fromisoformat(published_raw.replace("Z", "+00:00")).astimezone(UTC)
            link = entry_id
            entries.append(
                ArxivEntry(
                    arxiv_id=entry_id.rsplit("/", 1)[-1],
                    title=title,
                    summary=summary,
                    published_at=published,
                    category=category,
                    link=link,
                )
            )
        return entries


def _text(element: Any) -> str:
    return "" if element is None or element.text is None else element.text.strip()


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
