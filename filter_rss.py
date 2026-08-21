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
#
# 強いキーワード:
#   単独で出現しても電池関連である可能性が高いもの
#
# 弱いキーワード:
#   electrode など、他分野でも頻繁に使われるもの
#
# ============================================================

BATTERY_STRONG_KEYWORDS = [
    "battery",
    "batteries",
    "lithium-ion",
    "lithium ion",
    "li-ion",
    "sodium-ion",
    "sodium ion",
    "potassium-ion",
    "potassium ion",
    "solid-state battery",
    "solid state battery",
    "all-solid-state battery",
    "all solid state battery",
    "lithium-sulfur battery",
    "lithium sulfur battery",
    "lithium-metal battery",
    "lithium metal battery",
    "metal-air battery",
    "metal air battery",
    "zinc-air battery",
    "zinc air battery",
    "redox flow battery",
    "lithiation",
    "delithiation",
    "sodiation",
    "desodiation",
]


BATTERY_CONTEXT_KEYWORDS = [
    "lithium",
    "sodium",
    "potassium",
    "cathode",
    "anode",
    "electrolyte",
    "electrode",
    "electrochemical",
    "intercalation",
    "deintercalation",
    "charge-discharge",
    "charge discharge",
    "state of charge",
    "energy storage",
]


# ============================================================
# 電子顕微鏡関連キーワード
# ============================================================
#
# TEM / STEM / EDS などの短い略語は、
# 他の意味で使用される可能性があるため、
# 単独では判定しません。
#
# ============================================================

MICROSCOPY_STRONG_KEYWORDS = [
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
    "energy-dispersive x-ray spectrometry",
    "energy dispersive x-ray spectrometry",
    "electron diffraction",
    "selected-area electron diffraction",
    "selected area electron diffraction",
    "nanobeam electron diffraction",
    "nano-beam electron diffraction",
    "convergent-beam electron diffraction",
    "convergent beam electron diffraction",
    "electron tomography",
    "electron holography",
    "HAADF-STEM",
    "HAADF STEM",
    "ADF-STEM",
    "ADF STEM",
    "ABF-STEM",
    "ABF STEM",
    "DPC-STEM",
    "DPC STEM",
    "STEM-EELS",
    "STEM EELS",
    "4D-STEM",
    "4D STEM",
]


# ============================================================
# テキスト整形
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = html.unescape(text)

    # OpenAlexのタイトル等にHTMLタグが含まれる場合があるため除去
    text = re.sub(r"<[^>]+>", "", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# OpenAlex Abstract復元
# ============================================================

def reconstruct_abstract(inverted_index):
    """
    OpenAlexのabstract_inverted_indexを
    通常の文章へ復元する。
    """

    if not inverted_index:
        return ""

    words = []

    for word, positions in inverted_index.items():
        for position in positions:
            words.append(
                (position, word)
            )

    words.sort(
        key=lambda x: x[0]
    )

    abstract = " ".join(
        word
        for _, word in words
    )

    return clean_text(abstract)


# ============================================================
# フレーズ検索
# ============================================================

def contains_phrase(text, phrase):
    return phrase.lower() in text.lower()


# ============================================================
# 電池関連判定
# ============================================================

def is_battery_related(text):
    text_lower = text.lower()

    # --------------------------------------------------------
    # 1. 強いキーワード
    # --------------------------------------------------------

    for keyword in BATTERY_STRONG_KEYWORDS:
        if keyword.lower() in text_lower:
            return True

    # --------------------------------------------------------
    # 2. 文脈キーワード
    #
    # 1語だけでは判定せず、2種類以上存在する場合に採用
    # --------------------------------------------------------

    matched = set()

    for keyword in BATTERY_CONTEXT_KEYWORDS:
        if keyword.lower() in text_lower:
            matched.add(
                keyword.lower()
            )

    if len(matched) >= 2:
        return True

    return False


# ============================================================
# 電子顕微鏡関連判定
# ============================================================

def is_microscopy_related(text):
    text_lower = text.lower()

    # --------------------------------------------------------
    # 1. 強いキーワード
    # --------------------------------------------------------

    for keyword in MICROSCOPY_STRONG_KEYWORDS:
        if keyword.lower() in text_lower:
            return True

    # --------------------------------------------------------
    # 2. TEM / STEM + microscopy系文脈
    # --------------------------------------------------------

    microscopy_context = [
        "microscopy",
        "microscope",
        "electron beam",
        "electron imaging",
        "atomic-resolution",
        "atomic resolution",
        "nanoscale imaging",
        "microstructure",
    ]

    has_context = any(
        keyword in text_lower
        for keyword in microscopy_context
    )

    if has_context:
        if re.search(
            r"\b(TEM|STEM|EELS|SAED|HAADF|ABF)\b",
            text,
            flags=re.IGNORECASE,
        ):
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
# Science Advances Source ID取得
# ============================================================

def get_science_advances_source():
    print(
        "Science AdvancesのSource情報を取得します..."
    )

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
            "Source API HTTP status: "
            f"{response.status_code}"
        )

        response.raise_for_status()

    except requests.RequestException as e:
        print(
            f"Source取得失敗: {e}"
        )
        raise SystemExit(1)

    source = response.json()

    source_id = source.get(
        "id",
        "",
    )

    source_name = source.get(
        "display_name",
        "",
    )

    print(
        f"Source name: {source_name}"
    )

    print(
        f"Source ID: {source_id}"
    )

    if not source_id:
        print(
            "Science AdvancesのSource IDを"
            "取得できませんでした。"
        )
        raise SystemExit(1)

    if source_name.lower() != "science advances":
        print(
            "警告: Source名が"
            "Science Advancesではありません。"
        )

    return source_id.split("/")[-1]


# ============================================================
# Science Advances論文を全件取得
# ============================================================

def get_articles(source_id):
    """
    OpenAlexのcursor paginationを使用して、
    LOOKBACK_DAYS期間内の論文を全件取得する。
    """

    today = datetime.now(
        timezone.utc
    ).date()

    start_date = (
        today
        - timedelta(
            days=LOOKBACK_DAYS
        )
    )

    print()
    print(
        f"{start_date} ～ {today} の論文を"
        "OpenAlexから取得します..."
    )

    url = (
        f"{OPENALEX_API}/works"
    )

    all_results = []

    cursor = "*"
    page_number = 1

    while cursor:
        print()
        print(
            f"OpenAlex page {page_number} を取得中..."
        )

        params = {
            "filter": (
                f"primary_location.source.id:{source_id},"
                f"from_publication_date:{start_date},"
                f"to_publication_date:{today}"
            ),
            "sort": "publication_date:desc",
            "per_page": 100,
            "cursor": cursor,
        }

        params = add_api_key(
            params
        )

        try:
            response = requests.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

            print(
                "Works API HTTP status: "
                f"{response.status_code}"
            )

            response.raise_for_status()

        except requests.RequestException as e:
            print(
                f"Works取得失敗: {e}"
            )
            raise SystemExit(1)

        data = response.json()

        results = data.get(
            "results",
            [],
        )

        print(
            f"このページ: {len(results)} papers"
        )

        all_results.extend(
            results
        )

        meta = data.get(
            "meta",
            {},
        )

        next_cursor = meta.get(
            "next_cursor"
        )

        # 結果が0件なら終了
        if not results:
            break

        # 次のcursorがなければ終了
        if not next_cursor:
            break

        cursor = next_cursor
        page_number += 1

    print()
    print(
        "取得論文総数: "
        f"{len(all_results)}"
    )

    return all_results


# ============================================================
# 論文URL
# ============================================================

def get_article_url(work):
    doi = work.get(
        "doi"
    )

    if doi:
        return doi

    primary_location = (
        work.get(
            "primary_location"
        )
        or {}
    )

    landing_page_url = (
        primary_location.get(
            "landing_page_url"
        )
    )

    if landing_page_url:
        return landing_page_url

    return work.get(
        "id",
        "",
    )


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
        datetime.now(
            timezone.utc
        )
    )

    for article in articles:
        item = SubElement(
            channel,
            "item",
        )

        SubElement(
            item,
            "title",
        ).text = article[
            "title"
        ]

        SubElement(
            item,
            "link",
        ).text = article[
            "link"
        ]

        guid = SubElement(
            item,
            "guid",
            {
                "isPermaLink":
                    "false",
            },
        )

        guid.text = article[
            "id"
        ]

        publication_date = (
            article.get(
                "publication_date"
            )
        )

        if publication_date:
            try:
                publication_datetime = (
                    datetime.strptime(
                        publication_date,
                        "%Y-%m-%d",
                    ).replace(
                        tzinfo=timezone.utc
                    )
                )

                SubElement(
                    item,
                    "pubDate",
                ).text = (
                    format_datetime(
                        publication_datetime
                    )
                )

            except ValueError:
                pass

        # ----------------------------------------------------
        # Abstract全文をRSSのdescriptionへ格納
        # ----------------------------------------------------

        SubElement(
            item,
            "description",
        ).text = article[
            "abstract"
        ]

    tree = ElementTree(
        rss
    )

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
        "OpenAlexを使用して"
        "Science Advancesの論文を取得します。"
    )

    if not API_KEY:
        print(
            "エラー: OPENALEX_API_KEYが"
            "設定されていません。"
        )

        raise SystemExit(1)

    # --------------------------------------------------------
    # Science Advancesを特定
    # --------------------------------------------------------

    source_id = (
        get_science_advances_source()
    )

    # --------------------------------------------------------
    # 論文を全件取得
    # --------------------------------------------------------

    works = get_articles(
        source_id
    )

    if not works:
        print(
            "対象期間の論文を"
            "取得できませんでした。"
        )

        raise SystemExit(1)

    battery_articles = []
    microscopy_articles = []
    battery_microscopy_articles = []

    abstract_count = 0

    total = len(
        works
    )

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

        abstract = (
            reconstruct_abstract(
                work.get(
                    "abstract_inverted_index"
                )
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

        print(
            title
        )

        print(
            "Publication date: "
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

        # ----------------------------------------------------
        # Title + Abstractを判定対象にする
        # ----------------------------------------------------

        search_text = (
            f"{title} {abstract}"
        )

        battery = (
            is_battery_related(
                search_text
            )
        )

        microscopy = (
            is_microscopy_related(
                search_text
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

        if battery:
            battery_articles.append(
                article
            )

            print(
                "→ Battery"
            )

        if microscopy:
            microscopy_articles.append(
                article
            )

            print(
                "→ Microscopy"
            )

        if battery and microscopy:
            battery_microscopy_articles.append(
                article
            )

            print(
                "→ Battery + Microscopy"
            )

    # ========================================================
    # 統計
    # ========================================================

    print()
    print(
        "=============================="
    )
    print(
        "取得結果"
    )
    print(
        "=============================="
    )

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

    print(
        "Battery: "
        f"{len(battery_articles)}"
    )

    print(
        "Microscopy: "
        f"{len(microscopy_articles)}"
    )

    print(
        "Battery + Microscopy: "
        f"{len(battery_microscopy_articles)}"
    )

    print()

    # ========================================================
    # RSS生成
    # ========================================================

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
    print(
        "完了しました。"
    )


if __name__ == "__main__":
    main()
