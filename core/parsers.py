import datetime
import time
import xml.etree.ElementTree as ET
from collections import defaultdict

import feedparser
from bs4 import BeautifulSoup

from core.models.feed import Feed, FeedArticle
from core.constants import SUMMARY_LENGTH

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/128.0",
    "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.google.com/",
}


def parse_opml(file_text: str) -> list[Feed]:
    """
    Parses OPML file text and returns a list of dictionaries with feed information.

    Args:
        file_text (str): The content of the OPML file as a string.

    Returns:
        list: A list of dictionaries containing feed information.
    """

    # Parse the OPML XML
    root = ET.fromstring(file_text)

    feeds = []

    for outline in root.findall(".//outline[@type='rss']"):
        feed = Feed(
            0,
            outline.get("title"),
            outline.get("xmlUrl"),
        )
        feeds.append(feed)

    return feeds


def parse_feed(feeds: list[Feed]) -> dict[str, list[FeedArticle]]:
    """
    Parses a feed and get recent published articles.
    Filter out articles which has read.
    Args:
        feeds (Feed): The feed object containing the XML URL.
    Returns:
        dict: A dictionary with feed titles as keys and a list of articles as values.
    """
    articles = defaultdict(list)
    for feed in feeds:
        data = feedparser.parse(feed.url, request_headers=HEADERS)
        if not data.entries:
            continue
        for entry in data.entries:
            # TODO: deal with other article metadata
            published_struct = getattr(entry, "published_parsed", None) or getattr(
                entry, "updated_parsed", None
            )
            if not published_struct:
                continue
            pub_date = _convert_to_datetime(published_struct)
            # if pub_date.date() != datetime.datetime.today().date():
            #     continue
            guid = None
            if not hasattr(entry, "id"):
                guid = entry.link
            else:
                guid = entry.id
            title = entry.title
            url = entry.link
            content, has_full_content = _extract_text_from_entry(entry)
            summary = content[:SUMMARY_LENGTH] if content else ""
            articles[feed.title].append(
                FeedArticle(
                    id=guid,
                    title=title[:256],
                    url=url,
                    content=content,
                    pub_date=pub_date,
                    summary=summary,
                    has_full_content=has_full_content,
                )
            )
    return articles


def parse_html_content(html_content: str) -> str:
    """
    Extracts main content from HTML using BeautifulSoup and lxml,
    applying common heuristics and cleaning.
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "lxml")  # Use the lxml parser

    # --- Strategy 1: Find specific semantic tags or common IDs/Classes ---
    potential_containers = [
        soup.find("article"),
        soup.find("main"),
        soup.find(id="main-content"),
        soup.find(id="content"),
        soup.find(class_="post-content"),
        soup.find(class_="entry-content"),
        soup.find(class_="article-body"),
        # Add more specific selectors if you know the target site structure
    ]

    # Find the first valid container from the list
    content_container = None
    for container in potential_containers:
        if container:
            content_container = container
            # print(f"Found potential container: <{container.name}> with id='{container.get('id')}' class='{' '.join(container.get('class', []))}'") # Debug print
            break

    # Fallback to body if no specific container found
    if not content_container:
        content_container = soup.body
        if not content_container:  # Should almost never happen for valid HTML
            return ""
        # print("No specific container found, falling back to <body>") # Debug print

    # --- Strategy 2: Clean the container by removing common boilerplate ---
    # List of selectors for elements to remove
    selectors_to_remove = [
        "nav",
        "header",
        "footer",
        "aside",
        "script",
        "style",
        "noscript",
        '[role="navigation"]',
        '[role="banner"]',
        '[role="contentinfo"]',
        '[id*="comments"]',
        '[class*="comments"]',
        '[id*="sidebar"]',
        '[class*="sidebar"]',
        '[id*="footer"]',
        '[class*="footer"]',
        '[id*="header"]',
        '[class*="header"]',
        '[id*="nav"]',
        '[class*="nav"]',
        '[class*="advert"]',
        '[class*="banner"]',
        '[class*="share"]',
        '[class*="social"]',
        '[class*="related"]',
        '[class*="author-info"]',
        # Add more specific selectors for ads, related posts, etc.
    ]

    elements_removed_count = 0
    for selector in selectors_to_remove:
        for element in content_container.select(selector):
            element.decompose()  # Remove the element and its content entirely
            elements_removed_count += 1

    # print(f"Removed {elements_removed_count} boilerplate elements.") # Debug print

    # --- Strategy 3: Extract text from the cleaned container ---
    # get_text() extracts all text within the tag.
    # separator='\n' attempts to put newlines between text from different tags.
    # strip=True removes leading/trailing whitespace from each chunk.
    main_text = content_container.get_text(separator="\n", strip=True)

    # Optional: Further clean the text (e.g., remove excessive blank lines)
    lines = [line for line in main_text.split("\n") if line.strip()]
    cleaned_text = "\n".join(lines)

    return cleaned_text


def _extract_text_from_entry(entry) -> tuple[str, bool]:
    """
    Extracts text from HTML content using BeautifulSoup.

    Args:
        entry: The feed entry containing HTML content.

    Returns:
        tuple: A tuple containing the extracted text and the link to the entry (if no full content in the feed).
    """
    full_content = ""
    if hasattr(entry, "content"):
        if entry.content and isinstance(entry.content, list):
            if entry.content[0].value:
                full_content = entry.content[0].value
                full_content = parse_html_content(full_content)
                return full_content, True

    if not full_content:
        if hasattr(entry, "summary"):
            full_content = entry.summary[:SUMMARY_LENGTH]
            full_content = parse_html_content(full_content)
            return full_content, False
    return "", False


def _convert_to_datetime(ttime: time.struct_time) -> datetime.datetime:
    """
    Converts a feed entry to a datetime object.

    Args:
        ttime (struct_time): The time structure to convert.

    Returns:
        datetime: A datetime object representing the published date.
    """
    t = time.mktime(ttime)
    dt = datetime.datetime.fromtimestamp(t)
    return dt
