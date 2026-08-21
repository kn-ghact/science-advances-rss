import os
import re
import html
import requests

from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from xml.etree.ElementTree import Element, SubElement, ElementTree


# ============================================================
# 設定
# ============================================================

OPENALEX_API = "https://api.openalex.org"

# Science Advances
SCIENCE_ADVANCES_ISSN = "2375-2548"

API_KEY = os.environ.get("OPENALEX_API_KEY")

REQUEST_TIMEOUT = 30

# 直近何日分の論文を取得するか
LOOKBACK_DAYS = 30


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
# OpenAlexのAbstractを通常の文章に復元
# ============================================================

def reconstruct_abstract(inverted_index):
    """
    OpenAlexのabstract_inverted_indexを通常の文章へ戻す。

    例:
    {
        "Lithium": [0],
        "batteries": [1]
    }

    ↓

    "Lithium batteries"
    """

    if not inverted_index:
        return ""

    words = []

    for word, positions in inverted_index.items():
        for position in positions:
            words.append((position, word))

    words.sort(key=lambda x: x[0])

    abstract = " ".join(
        word for _, word in words
    )

    return clean_text(abstract)


# ============================================================
# キーワード判定
# ============================================================

def contains_keyword(text, keywords):
    text_lower = text.lower()

    for keyword in keywords:
        keyword_lower = keyword.lower()

        # 短い略語については単語単位で検索
        if keyword_lower in {
            "tem",
            "stem",
            "eels",
            "edx",
            "eds",
            "saed",
        }:
            pattern = (
                r"\b"
                + re.escape(keyword_lower)
                + r"\b"
            )

            if re.search(pattern, text_lower):
                return True

        else:
            if keyword_lower in text_lower:
                return True

    return False


# ============================================================
# API共通パラメータ
# ============================================================

def add_api_key(params=None):
    if params is None:
        params = {}

    if API_KEY:
        params["api_key"] = API_KEY

    return params


# ============================================================
# Science AdvancesのOpenAlex Source IDを取得
# ============================================================

def get_science_advances_source():
    print("Science AdvancesのSource情報を取得します...")

    url = (
        f"{OPENALEX_API}/sources/"
        f"issn:{SCIENCE_ADVANCES_ISSN}"
    )

    try:
        response = requests.get(
            url,
            params=add_api_key(),
            timeout=REQUEST_TIMEOUT,
        )

        print(
            f"Source API HTTP status: "
            f"{response.status_code}"
        )

        response.raise_for_status()

    except requests.RequestException as e:
        print(f"Source取得失敗: {e}")
        raise SystemExit(1)

    source = response.json()

    source_id = source.get("id", "")
    source_name = source.get("display_name", "")

    print(f"Source name: {source_name}")
    print(f"Source ID: {source_id}")

    if not source_id:
        print(
            "Science AdvancesのSource IDを"
            "取得できませんでした。"
        )
        raise SystemExit(1)

    # 念のためジャーナル名も確認
    if source_name.lower() != "science advances":
        print(
            "警告: 取得されたSource名が"
            "Science Advancesではありません。"
        )

    return source_id.split("/")[-1]


# ============================================================
# Science Advancesの論文をOpenAlexから取得
# ============================================================

def get_articles(source_id):
    today = datetime.now(timezone.utc).date()

    start_date = today - timedelta(
        days=LOOKBACK_DAYS
    )

    print()
    print(
        f"{start_date} ～ {today} の論文を"
        "OpenAlexから取得します..."
    )

    url = f"{OPENALEX_API}/works"

    params = {
        "filter": (
            f"primary_location.source.id:{source_id},"
            f"from_publication_date:{start_date},"
            f"to_publication_date:{today}"
        ),
        "sort": "publication_date:desc",
        "per_page": 100,
    }

    params = add_api_key(params)

    try:
        response = requests.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        print(
            f"Works API HTTP status: "
            f"{response.status_code}"
        )

        response.raise_for_status()

    except requests.RequestException as e:
        print(f"Works取得失敗: {e}")
        raise SystemExit(1)

    data = response.json()

    results = data.get("results", [])

    print(
        f"取得論文数: {len(results)}"
    )

    return results


# ============================================================
# 論文URLを決定
# ============================================================

def get_article_url(work):
    doi = work.get("doi")

    if doi:
        return doi

    primary_location = (
        work.get("primary_location") or {}
    )

    landing_page_url = (
        primary_location.get(
            "landing_page_url"
        )
    )

    if landing_page_url:
        return landing_page_url

    return work.get("id", "")


# ============================================================
# RSS作成
# ============================================================

def create_rss(
    filename,
    channel_title,
    articles,
):
    rss = Element(
        "rss",
        {
            "version": "2.0",
        },
    )

    channel = SubElement(
        rss,
        "channel",
    )

    SubElement(
        channel,
        "title",
    ).text = channel_title

    SubElement(
        channel,
        "link",
    ).text = (
        "https://www.science.org/"
        "journal/sciadv"
    )

    SubElement(
        channel,
        "description",
    ).text = (
        "Science Advances papers "
        "filtered using OpenAlex metadata"
    )

    SubElement(
        channel,
        "language",
    ).text = "en"

    SubElement(
        channel,
        "lastBuildDate",
    ).text = format_datetime(
        datetime.now(timezone.utc)
    )

    for article in articles:
        item = SubElement(
            channel,
            "item",
        )

        SubElement(
            item,
            "title",
        ).text = article["title"]

        SubElement(
            item,
            "link",
        ).text = article["link"]

        guid = SubElement(
            item,
            "guid",
            {
                "isPermaLink": "false",
            },
        )

        guid.text = article["id"]

        if article.get("publication_date"):
            try:
                publication_datetime = (
                    datetime.strptime(
                        article[
                            "publication_date"
                        ],
                        "%Y-%m-%d",
                    ).replace(
                        tzinfo=timezone.utc
                    )
                )

                SubElement(
                    item,
                    "pubDate",
                ).text = format_datetime(
                    publication_datetime
                )

            except ValueError:
                pass

        # Abstract全文をRSS Contentとして格納
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

    print(
        f"{filename}: "
        f"{len(articles)} papers"
    )


# ============================================================
# メイン処理
# ============================================================

def main():
    print(
        "OpenAlexを使用してScience Advancesの"
        "論文を取得します。"
    )

    if not API_KEY:
        print(
            "警告: OPENALEX_API_KEYが"
            "設定されていません。"
        )

    # --------------------------------------------------------
    # Science Advancesを特定
    # --------------------------------------------------------

    source_id = (
        get_science_advances_source()
    )

    # --------------------------------------------------------
    # 論文取得
    # --------------------------------------------------------

    works = get_articles(
        source_id
    )

    if not works:
        print(
            "対象期間の論文を取得できませんでした。"
        )
        raise SystemExit(1)

    battery_articles = []
    microscopy_articles = []
    battery_microscopy_articles = []

    abstract_count = 0

    total = len(works)

    # --------------------------------------------------------
    # 各論文を処理
    # --------------------------------------------------------

    for number, work in enumerate(
        works,
        start=1,
    ):
        title = clean_text(
            work.get(
                "display_name",
                "",
            )
        )

        abstract = reconstruct_abstract(
            work.get(
                "abstract_inverted_index"
            )
        )

        if abstract:
            abstract_count += 1

        link = get_article_url(
            work
        )

        publication_date = (
            work.get(
                "publication_date",
                "",
            )
        )

        print()
        print(
            f"[{number}/{total}]"
        )

        print(title)

        print(
            f"Publication date: "
            f"{publication_date}"
        )

        if abstract:
            print(
                "Abstract: "
                f"{len(abstract)} characters"
            )
        else:
            print(
                "Abstract: なし"
            )

        # --------------------------------------------
        # Title + Abstractを検索
        # --------------------------------------------

        search_text = (
            f"{title} {abstract}"
        )

        is_battery = contains_keyword(
            search_text,
            BATTERY_KEYWORDS,
        )

        is_microscopy = (
            contains_keyword(
                search_text,
                MICROSCOPY_KEYWORDS,
            )
        )

        article = {
            "id": work.get(
                "id",
                link,
            ),
            "title": title,
            "link": link,
            "abstract": abstract,
            "publication_date":
                publication_date,
        }

        if is_battery:
            battery_articles.append(
                article
            )

            print("→ Battery")

        if is_microscopy:
            microscopy_articles.append(
                article
            )

            print("→ Microscopy")

        if (
            is_battery
            and is_microscopy
        ):
            battery_microscopy_articles.append(
                article
            )

            print(
                "→ Battery + Microscopy"
            )

    # --------------------------------------------------------
    # 統計
    # --------------------------------------------------------

    print()
    print("==============================")
    print("取得結果")
    print("==============================")

    print(
        f"全論文: {total}"
    )

    print(
        "Abstractあり: "
        f"{abstract_count}"
    )

    print(
        "Abstractなし: "
        f"{total - abstract_count}"
    )

    print(
        "Abstract収録率: "
        f"{abstract_count / total * 100:.1f}%"
    )

    print()

    # --------------------------------------------------------
    # RSS生成
    # --------------------------------------------------------

    create_rss(
        "battery.xml",
        "Science Advances - Battery",
        battery_articles,
    )

    create_rss(
        "microscopy.xml",
        (
            "Science Advances - "
            "Electron Microscopy"
        ),
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
