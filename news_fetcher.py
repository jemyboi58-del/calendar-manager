"""
news_fetcher.py — pulls top headlines from RSS feeds.

Usage:
    from news_fetcher import NewsFetcher
    fetcher = NewsFetcher()
    articles = fetcher.fetch()   # returns list of dicts
"""

import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

# Free RSS feeds — no API key needed
FEEDS = {
    "BBC World":       "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Reuters":         "https://feeds.reuters.com/reuters/topNews",
    "AP News":         "https://rsshub.app/apnews/topics/apf-topnews",
    "NYT Top Stories": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "NPR News":        "https://feeds.npr.org/1001/rss.xml",
}

# How many articles to pull per feed
MAX_PER_FEED = 5


class NewsFetcher:
    def __init__(self, feeds: dict = None, max_per_feed: int = MAX_PER_FEED):
        self.feeds = feeds or FEEDS
        self.max_per_feed = max_per_feed

    def fetch(self) -> list[dict]:
        """Fetch articles from all feeds. Returns a list of article dicts."""
        all_articles = []
        for source, url in self.feeds.items():
            try:
                articles = self._fetch_feed(source, url)
                all_articles.extend(articles)
            except Exception as e:
                print(f"[news_fetcher] Warning: could not fetch {source}: {e}")
        return all_articles

    def _fetch_feed(self, source: str, url: str) -> list[dict]:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()

        root = ET.fromstring(raw)

        # Handle both RSS <channel><item> and Atom <entry> formats
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        articles = []
        for item in items[: self.max_per_feed]:
            title = self._text(item, ["title", "atom:title"], ns) or "(no title)"
            description = (
                self._text(item, ["description", "summary", "atom:summary"], ns) or ""
            )
            link = self._text(item, ["link", "atom:link"], ns) or ""
            pub_date = self._text(item, ["pubDate", "published", "atom:published"], ns) or ""

            articles.append(
                {
                    "source": source,
                    "title": title.strip(),
                    "description": description.strip()[:400],
                    "link": link.strip(),
                    "published": pub_date.strip(),
                }
            )
        return articles

    def _text(self, element, tag_options: list, ns: dict) -> str:
        """Try each tag name in order and return the first non-empty text found."""
        for tag in tag_options:
            el = element.find(tag, ns)
            if el is not None:
                # <link> in Atom feeds stores the URL in the href attribute
                return el.get("href") or (el.text or "")
        return ""


if __name__ == "__main__":
    fetcher = NewsFetcher()
    articles = fetcher.fetch()
    print(f"Fetched {len(articles)} articles\n")
    for a in articles:
        print(f"[{a['source']}] {a['title']}")
        if a["description"]:
            print(f"  {a['description'][:120]}...")
        print()
