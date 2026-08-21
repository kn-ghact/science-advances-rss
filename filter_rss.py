import feedparser
import requests
from bs4 import BeautifulSoup
from xml.etree.ElementTree import Element, SubElement, ElementTree
from email.utils import format_datetime
from datetime import datetime, timezone
import re
import time
import html


# ============================================================
# 設定
# ============================================================

SOURCE_RSS = (
    "https://www.science.org/action/showFeed"
    "?type=etoc&feed=rss&jc=advances"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

REQUEST_TIMEOUT = 30
REQUEST_INTERVAL = 1.0


# ============================================================
# 電池関連キーワード
# ============================================================

BATTERY_KEYWORDS = [
    "battery",
    "batteries",
    "lithium",
    "lithium-ion",
    "lithium ion",
    "li-ion",
    "sodium-ion",
    "sodium ion",
    "solid-state battery",
    "solid state battery",
    "all-solid-state",
    "all solid state",
    "cathode",
    "anode",
    "electrode",
    "electrolyte",
    "electrochemical cell",
    "lithiation",
    "delithiation",
]


# ============================================================
# 電子顕微鏡関連キーワード
# ============================================================

MICROSCOPY_KEYWORDS = [
    "electron microscopy",
    "electron microscope",
    "transmission electron microscopy",
    "scanning transmission electron microscopy",
    "high-resolution transmission electron microscopy",
    "high resolution transmission electron microscopy",
    "cryo-electron microscopy",
    "cryo electron microscopy",
    "electron energy-loss spectroscopy",
    "electron energy loss spectroscopy",
    "energy-dispersive x-ray spectroscopy",
    "energy dispersive x-ray spectroscopy",
    "electron diffraction",
    "selected-area electron diffraction",
    "selected area electron diffraction",
    "nanobeam electron diffraction",
    "convergent-beam electron diffraction",
    "convergent beam electron diffraction",
    "HAADF",
    "ADF-STEM",
    "ABF-STEM",
    "DPC-STEM",
    "STEM-EELS",
    "TEM",
    "STEM",
    "EELS",
    "EDX",
    "EDS",
    "SAED",
]


# ============================================================
# テキスト整形
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# キーワード判定
# ============================================================

def contains_keyword(text, keywords):
    text_lower = text.lower()

    for keyword in keywords:
        keyword_lower = keyword.lower()

        # 短い略語は単語として完全一致
        if keyword_lower in {
            "tem",
            "stem",
            "eels",
            "edx",
            "eds",
            "saed",
        }:
            pattern = r"\b" + re.escape(keyword_lower) + r"\b"

            if re.search(pattern, text_lower):
                return True

        else:
            if keyword_lower in text_lower:
                return True

    return False


# ============================================================
# Science Advances RSSを取得
# ============================================================

def get_source_feed():
    print("Science Advances RSSへアクセスします...")

    try:
        response = requests.get(
            SOURCE_RSS,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        print(f"RSS HTTP status: {response.status_code}")
        print(f"RSS final URL: {response.url}")
        print(
            "RSS Content-Type: "
            f"{response.headers.get('Content-Type', 'unknown')}"
        )
        print(f"RSS response size: {len(response.content)} bytes")

        response.raise_for_status()

    except requests.RequestException as e:
        print(f"RSS取得失敗: {e}")
        return None

    feed = feedparser.parse(response.content)

    if getattr(feed, "bozo", False):
        print(f"RSS parser warning: {feed.bozo_exception}")

    print(f"RSS entries: {len(feed.entries)}")

    if len(feed.entries) == 0:
        preview = response.text[:500]
        preview = preview.replace("\n", " ")

        print("RSSから記事を取得できませんでした。")
        print("Response preview:")
        print(preview)

    return feed


# ============================================================
# Science論文ページからAbstractを取得
# ============================================================

def get_abstract(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

    except requests.RequestException as e:
        print(f"  ページ取得失敗: {e}")
        return ""

    soup = BeautifulSoup(response.text, "html.parser")

    # --------------------------------------------------------
    # 1. citation_abstract
    # --------------------------------------------------------

    meta = soup.find(
        "meta",
        attrs={"name": "citation_abstract"},
    )

    if meta and meta.get("content"):
        abstract = clean_text(meta["content"])

        if abstract:
            return abstract

    # --------------------------------------------------------
    # 2. DC.Description
    # --------------------------------------------------------

    meta = soup.find(
        "meta",
        attrs={"name": "DC.Description"},
    )

    if meta and meta.get("content"):
        abstract = clean_text(meta["content"])

        if abstract:
            return abstract

    # --------------------------------------------------------
    # 3. description / og:description
    # --------------------------------------------------------

    for attrs in [
        {"name": "description"},
        {"property": "og:description"},
    ]:
        meta = soup.find("meta", attrs=attrs)

        if meta and meta.get("content"):
            abstract = clean_text(meta["content"])

            if abstract:
                return abstract

    # --------------------------------------------------------
    # 4. AbstractセクションをHTMLから探索
    # --------------------------------------------------------

    selectors = [
        "section.abstract",
        "div.abstract",
        ".abstract",
        "#abstract",
        ".article__abstract",
        ".article-section__abstract",
    ]

    for selector in selectors:
        element = soup.select_one(selector)

        if element:
            abstract = clean_text(
                element.get_text(" ", strip=True)
            )

            abstract = re.sub(
                r"^Abstract\s*",
                "",
                abstract,
                flags=re.IGNORECASE,
            )

            if abstract:
                return abstract

    return ""


# ============================================================
# RSS作成
# ============================================================

def create_rss(filename, channel_title, articles):
    rss = Element(
        "rss",
        {
            "version": "2.0",
        },
    )

    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = channel_title

    SubElement(channel, "link").text = (
        "https://www.science.org/journal/sciadv"
    )

    SubElement(channel, "description").text = (
        "Filtered papers from Science Advances"
    )

    SubElement(channel, "language").text = "en"

    SubElement(channel, "lastBuildDate").text = format_datetime(
        datetime.now(timezone.utc)
    )

    for article in articles:
        item = SubElement(channel, "item")

        SubElement(item, "title").text = article["title"]
        SubElement(item, "link").text = article["link"]

        guid = SubElement(
            item,
            "guid",
            {"isPermaLink": "true"},
        )

        guid.text = article["link"]

        if article.get("published"):
            SubElement(
                item,
                "pubDate",
            ).text = article["published"]

        SubElement(
            item,
            "description",
        ).text = article["abstract"]

    tree = ElementTree(rss)

    tree.write(
        filename,
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"{filename}: {len(articles)} papers")


# ============================================================
# メイン処理
# ============================================================

def main():
    print("Science Advances RSSを取得します...")

    feed = get_source_feed()

    if feed is None:
        print("RSSを取得できなかったため終了します。")
        raise SystemExit(1)

    if len(feed.entries) == 0:
        print("RSSの記事数が0件のため終了します。")
        raise SystemExit(1)

    battery_articles = []
    microscopy_articles = []
    battery_microscopy_articles = []

    total = len(feed.entries)

    for number, entry in enumerate(
        feed.entries,
        start=1,
    ):
        title = clean_text(
            entry.get("title", "")
        )

        link = entry.get("link", "")

        print()
        print(f"[{number}/{total}]")
        print(title)
        print(link)

        if not link:
            print("  URLがないためスキップ")
            continue

        print("  Abstract取得中...")

        abstract = get_abstract(link)

        if abstract:
            print(
                "  Abstract取得成功 "
                f"({len(abstract)} characters)"
            )
        else:
            print(
                "  Abstractを取得できませんでした"
            )

        # --------------------------------------------
        # Title + Abstractを検索対象にする
        # --------------------------------------------

        search_text = f"{title} {abstract}"

        is_battery = contains_keyword(
            search_text,
            BATTERY_KEYWORDS,
        )

        is_microscopy = contains_keyword(
            search_text,
            MICROSCOPY_KEYWORDS,
        )

        article = {
            "title": title,
            "link": link,
            "abstract": abstract,
            "published": entry.get(
                "published",
                "",
            ),
        }

        if is_battery:
            battery_articles.append(article)
            print("  → Battery")

        if is_microscopy:
            microscopy_articles.append(article)
            print("  → Microscopy")

        if is_battery and is_microscopy:
            battery_microscopy_articles.append(
                article
            )

            print(
                "  → Battery + Microscopy"
            )

        time.sleep(REQUEST_INTERVAL)

    print()
    print("RSSファイルを作成します...")

    create_rss(
        "battery.xml",
        "Science Advances - Battery",
        battery_articles,
    )

    create_rss(
        "microscopy.xml",
        "Science Advances - Electron Microscopy",
        microscopy_articles,
    )

    create_rss(
        "battery_microscopy.xml",
        (
            "Science Advances - "
            "Battery and Electron Microscopy"
        ),
        battery_microscopy_articles,
    )

    print()
    print("完了しました。")


if __name__ == "__main__":
    main()
