#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, sys, json, time, hashlib
from datetime import datetime, timedelta, timezone, date
from urllib.parse import quote_plus, urlparse, parse_qs, unquote, urljoin
import requests
import feedparser
from dateutil.parser import parse as dtparse
import pytz
from bs4 import BeautifulSoup as BS
from html import unescape
from markdown import markdown as md_to_html

# ---------------------------------------------------------------------------
# Čas / období
# ---------------------------------------------------------------------------
TZ = pytz.timezone("Europe/Prague")
TODAY = datetime.now(TZ).date()
EVENT_PAST_DAYS = 7
EVENT_FUTURE_DAYS = 7

def week_bounds(d: date):
    """Pondělí–Neděle týdne obsahujícího datum d."""
    mon = d - timedelta(days=d.weekday())
    sun = mon + timedelta(days=6)
    return mon, sun

# Minulý týden: pondělí–neděle bezprostředně před dneškem
PREV_MON, PREV_SUN = week_bounds(TODAY - timedelta(days=7))

# ---------------------------------------------------------------------------
# Pomocné
# ---------------------------------------------------------------------------
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": DEFAULT_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,cs;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}
RUN_MAIN = os.environ.get("DNB_BRIEFING_SKIP_MAIN") != "1"

FACEBOOK_ACCESS_TOKEN = (
    os.environ.get("DNB_BRIEFING_FACEBOOK_TOKEN")
    or os.environ.get("FACEBOOK_GRAPH_TOKEN")
    or os.environ.get("FACEBOOK_ACCESS_TOKEN")
)

FACEBOOK_DEFAULT_PAGES = {
    "hospitalitydnb": "Hospitality",
    "rampagebelgium": "Rampage",
    "Liquicity": "Liquicity",
    "KorsakovMusic": "Korsakov",
    "DnBAllstars": "DnB Allstars",
    "darkshirednb": "Darkshire",
    "BeatsForLoveFestival": "Beats for Love",
    "hoofbeatsmusic": "Hoofbeats",
    "roxyprague": "Roxy Prague",
    "epicprague": "EPIC Prague",
}

def parse_facebook_pages_config(value: str):
    mapping = {}
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            page_id, label = chunk.split(":", 1)
        else:
            page_id, label = chunk, chunk
        page_id = page_id.strip()
        label = label.strip() or page_id
        if page_id:
            mapping[page_id] = label
    return mapping

def load_facebook_pages():
    env = os.environ.get("DNB_BRIEFING_FACEBOOK_PAGES", "").strip()
    if env:
        return parse_facebook_pages_config(env)
    return FACEBOOK_DEFAULT_PAGES

def fmt_date(dt: datetime) -> str:
    return f"{dt.day}. {dt.month}. {dt.year}"

def fmt_date_range(start: date, end: date) -> str:
    if start > end:
        start, end = end, start
    if start.year == end.year:
        if start.month == end.month:
            return f"{start.day}.–{end.day}. {end.month}. {end.year}"
        return f"{start.day}. {start.month}. {start.year} – {end.day}. {end.month}. {end.year}"
    return f"{start.day}. {start.month}. {start.year} – {end.day}. {end.month}. {end.year}"

def within(date_dt: datetime, start_date: date, end_date: date) -> bool:
    d = date_dt.astimezone(TZ).date()
    return start_date <= d <= end_date

def clean_text(s, limit=400):
    if not s: return ""
    s = unescape(BS(s, "html.parser").get_text(" ", strip=True))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit].rstrip()

def get_best_date(entry):
    for k in ("published", "updated", "created"):
        if k in entry and entry[k]:
            try:
                return dtparse(entry[k]).astimezone(TZ)
            except Exception:
                pass
    for k in ("published_parsed", "updated_parsed"):
        if k in entry and entry[k]:
            return datetime(*entry[k][:6], tzinfo=timezone.utc).astimezone(TZ)
    return None

def merge_headers(base, extra):
    if not extra:
        return base.copy()
    merged = base.copy()
    for key, value in extra.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged

def fetch(url, headers=None, timeout=20):
    h = merge_headers(HEADERS, headers)
    r = requests.get(url, headers=h, timeout=timeout)
    r.raise_for_status()
    return r

def resolve_news_url(link: str) -> str:
    """Rozbal Google News wrapper ?url=..."""
    try:
        u = urlparse(link)
        if u.netloc.endswith("news.google.com"):
            qs = parse_qs(u.query)
            if "url" in qs and qs["url"]:
                return unquote(qs["url"][0])
    except Exception:
        pass
    return link

def normalize_url(u: str) -> str:
    """Sjednoť URL bez UTM a fragmentů."""
    try:
        p = urlparse(u)
        if not p.scheme or not p.netloc: return u
        qs = parse_qs(p.query)
        qs = {k: v for k, v in qs.items() if not k.lower().startswith("utm_")}
        base = f"{p.scheme}://{p.netloc}{p.path}"
        if qs:
            q = "&".join(f"{k}={quote_plus(v[0])}" for k, v in qs.items() if v)
            return f"{base}?{q}"
        return base
    except Exception:
        return u

# ---------------------------------------------------------------------------
# Feedy / dotazy
# ---------------------------------------------------------------------------
def google_news_feed(site, when_days=14):
    """Dotaz na doménu za posledních N dní. Filtrovat budeme až heuristikou."""
    if site.endswith(".cz") or site.endswith(".sk") or site in ("rave.cz","musicserver.cz"):
        hl, gl, ceid = "cs", "CZ", "CZ:cs"
    else:
        hl, gl, ceid = "en-US", "US", "US:en"
    query = f"site:{site} when:{when_days}d"
    base = "https://news.google.com/rss/search?q="
    tail = f"&hl={hl}&gl={gl}&ceid={ceid}"
    return base + quote_plus(query) + tail

def reddit_rss(sub):
    return f"https://old.reddit.com/r/{sub}/.rss"

def youtube_channel_id_from_handle(handle):
    if handle.startswith("http"):
        url = handle
    else:
        url = f"https://www.youtube.com/{handle.lstrip('@')}"
        if "/@" not in url:
            url = "https://www.youtube.com/@" + handle.lstrip('@')
    try:
        html = fetch(url).text
        m = re.search(r'"channelId"\s*:\s*"([A-Za-z0-9_-]{20,})"', html)
        if m: return m.group(1)
    except Exception:
        return None
    return None

def youtube_rss_from_handle(handle):
    cid = youtube_channel_id_from_handle(handle)
    if not cid: return None
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"

def xenforo_forum_index_rss(base):
    return base.rstrip("/") + "/forums/index.rss"

# ---------------------------------------------------------------------------
# Konfigurace a heuristiky
# ---------------------------------------------------------------------------
PRIMARY_SITES = [
    ("Mixmag", "mixmag.net"),
    ("Resident Advisor", "ra.co"),
    ("UKF", "ukf.com"),
    ("DJ Mag", "djmag.com"),
    ("Musicserver.cz", "musicserver.cz"),
    ("Rave.cz", "rave.cz"),
    ("PM Studio", "pmstudio.com"),
    ("DogsOnAcid", "dogsonacid.com"),
]
REDDITS = [("r/DnB","DnB"), ("r/LetItRollFestival","LetItRollFestival")]
YOUTUBES = ["@Liquicity", "@dnballstars", "@WeAreRampageEvents", "@UKFDrumandBass"]

SECONDARY_SITES = [
    ("EDM.com", "edm.com"),
    ("Dancing Astronaut", "dancingastronaut.com"),
    ("Rolling Stone Australia", "rollingstone.com.au"),
    ("Billboard", "billboard.com"),
]

POS = [
    "drum and bass","drum’n’bass","drum n bass","dnb","dn'b","jungle",
    "neurofunk","liquid","jump up","rollers","ukf","hospital records",
    "let it roll","ram records","blackout music","shogun audio",
]
NEG = [
    "techno","tech house","house","trance","edm pop","electro house",
    "hardstyle","psytrance","deep house","progressive house",
]
CZSK_TOKENS = [
    "dnb","drum and bass","drum’n’bass","drum n bass","neuro","liquid","jump up","let it roll"
]
ALLOWLIST = (
    "mixmag.net","ra.co","ukf.com","djmag.com","edm.com","dancingastronaut.com",
    "rollingstone.com.au","billboard.com","youtube.com","youtu.be",
    "rave.cz","musicserver.cz","dogsonacid.com"
)

MIN_WORLD = 5
MIN_CZSK  = 2
MIN_REDDIT= 2

def is_dnb_related(title: str, summary: str, url: str) -> bool:
    t = f"{title} {summary}".lower()
    host = urlparse(url).netloc.lower()
    if any(host.endswith(d) for d in ALLOWLIST):
        return not any(n in t for n in NEG)
    return any(p in t for p in POS) and not any(n in t for n in NEG)

def is_czsk_dnb(title: str, summary: str) -> bool:
    t = f"{title} {summary}".lower()
    return any(x in t for x in CZSK_TOKENS) and not any(n in t for n in NEG)

# ---------------------------------------------------------------------------
# Build seznam feedů
# ---------------------------------------------------------------------------
FEEDS = []
for name, domain in PRIMARY_SITES:
    FEEDS.append({
        "name": f"GoogleNews:{name}",
        "kind": "rss",
        "section": "world",
        "url": google_news_feed(domain, when_days=14),
        "source_label": name
    })
FEEDS.append({
    "name":"Rave.cz",
    "kind":"rss",
    "section":"czsk",
    "url":"https://www.rave.cz/feed/",
    "source_label":"RAVE.cz"
})
for label, sub in REDDITS:
    FEEDS.append({
        "name": f"Reddit:{label}",
        "kind": "rss",
        "section": "reddit",
        "url": reddit_rss(sub),
        "source_label": f"Reddit {label}"
    })
for handle in YOUTUBES:
    url = youtube_rss_from_handle(handle)
    if url:
        FEEDS.append({
            "name": f"YouTube:{handle}",
            "kind": "rss",
            "section": "world",
            "url": url,
            "source_label": f"YouTube {handle}"
        })
FEEDS.append({
    "name":"DogsOnAcidForum",
    "kind":"rss",
    "section":"world",
    "url": xenforo_forum_index_rss("https://www.dogsonacid.com"),
    "source_label":"DogsOnAcid Forum"
})

# ---------------------------------------------------------------------------
# Zpracování položek z feedů
# ---------------------------------------------------------------------------
def classify_section(entry, src_label, link):
    host = re.sub(r"^www\.", "", (re.findall(r"https?://([^/]+)", link) or [""])[0])
    tld = host.split(".")[-1] if host else ""
    if tld in ("cz","sk") or "rave.cz" in host or "musicserver.cz" in host:
        return "czsk"
    return "world"

def entry_to_item(entry, source_label):
    raw_link = entry.get("link") or ""
    link = normalize_url(resolve_news_url(raw_link))
    title = clean_text(entry.get("title") or "")
    desc = clean_text(entry.get("summary") or entry.get("description") or "")
    dt = get_best_date(entry)
    return {"title": title, "summary": desc, "link": link, "date": dt, "source": source_label}

def fetch_feed(url):
    try:
        resp = fetch(url, headers=HEADERS, timeout=20)
        return feedparser.parse(resp.text)
    except Exception:
        try:
            return feedparser.parse(url)
        except Exception:
            return None

def summarize_item(it):
    base = it["title"]
    if it["summary"] and it["summary"][:len(base)].lower() != base.lower():
        text = f"{base} — {it['summary']}"
    else:
        text = base
    sents = re.split(r"(?<=[.!?])\s+", text)
    if len(sents) >= 2:
        text = " ".join(sents[:2])
    return text

def uniq_key(it):
    raw = (it["title"] or "") + (it["link"] or "")
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]

items_prev_world, items_prev_czsk = [], []
reddit_prev = []
all_refs, ref_map = [], {}

def add_ref(url, label):
    if not url:
        url = "about:blank"
    if url in ref_map: return ref_map[url]
    idx = len(all_refs) + 1
    ref_map[url] = idx
    all_refs.append((label, url))
    return idx

def harvest_sites(sites, start_date, end_date):
    out = []
    for label, domain in sites:
        feed_url = google_news_feed(domain, when_days=28)
        feed = fetch_feed(feed_url)
        if not feed or not feed.entries:
            continue
        for e in feed.entries:
            it = entry_to_item(e, label)
            if not it["date"]:
                continue
            if not within(it["date"], start_date, end_date):
                continue
            if not is_dnb_related(it["title"], it["summary"], it["link"]):
                continue
            it["section"] = "world"
            out.append(it)
    return out

def dedupe(lst, maxn=None):
    seen, out = set(), []
    for it in sorted(lst, key=lambda x: x["date"], reverse=True):
        k = uniq_key(it)
        if k in seen: continue
        seen.add(k); out.append(it)
        if maxn and len(out) >= maxn: break
    return out

# ---------------------------------------------------------------------------
# DnBHeard: Eventy ČR/SK (jen DnBHeard zdroj)
# ---------------------------------------------------------------------------
CZECH_MONTHS = {
    1: "leden", 2: "únor", 3: "březen", 4: "duben", 5: "květen", 6: "červen",
    7: "červenec", 8: "srpen", 9: "září", 10: "říjen", 11: "listopad", 12: "prosinec"
}
RE_DAYMONTH = re.compile(r"(?P<d>\d{1,2})\.\s*(?P<m>\d{1,2})\.", re.U)
EVENT_KEYWORDS = [
    "hospitality", "rampage", "liquicity", "dnb allstars", "allstars",
    "darkshire", "beats for love", "hoofbeats", "roxy", "epic", "korsakov",
    "hybrid minds", "imanu", "dimension", "etherwood", "sigma",
    "sub focus", "andy c", "netsky", "friction",
    "black sun empire", "camo & krooked", "bou", "sota",
    "kanine", "k-motionz", "merikan", "alix perez", "phace", "venjent", "akov"
]

def event_is_priority(title: str, foreign_guest: bool = False) -> bool:
    if foreign_guest:
        return True
    t = title.lower()
    return any(k in t for k in EVENT_KEYWORDS)

def cz_month_h2(soup, month_num: int):
    label = CZECH_MONTHS[month_num]
    for h in soup.find_all(["h2","h3"]):
        txt = (h.get_text(" ", strip=True) or "").strip().lower()
        if txt == label:
            return h
    return None

def parse_dnbeheard_lines(container_tag, year: int):
    """
    Projde sourozence za nadpisem měsíce až do dalšího H2/H3.
    """
    out = []
    ptr = container_tag.next_sibling
    while ptr:
        if getattr(ptr, "name", None) in ("h2","h3"):
            break
        text = ""
        if getattr(ptr, "name", None):
            text = ptr.get_text(" ", strip=True)
        else:
            text = str(ptr).strip()
        text = unescape(re.sub(r"\s+", " ", text or ""))
        if not text:
            ptr = ptr.next_sibling
            continue

        dates = list(RE_DAYMONTH.finditer(text))
        if dates:
            link = ""
            if getattr(ptr, "find", None):
                a = ptr.find("a")
                if a and a.has_attr("href"):
                    link = a["href"]
            m_city = re.search(r"#([A-Za-zÁ-ž]+)", text)
            city = m_city.group(1) if m_city else ""

            after = text[dates[-1].end():].strip()
            foreign_guest = "👑" in after
            after = re.sub(r"^#\S+\s+", "", after)
            after = after.split(" ~ ")[0].strip()
            title = after.replace("👑", "").strip() if after else ""
            title = title if title else "(bez názvu)"

            for dm in dates:
                d = int(dm.group("d")); m = int(dm.group("m"))
                try:
                    dt = datetime(year, m, d, tzinfo=TZ)
                except ValueError:
                    continue
                out.append({
                    "title": title,
                    "date": dt,
                    "link": link,
                    "city": city,
                    "foreign_guest": foreign_guest,
                })
        ptr = ptr.next_sibling
    return out

def scrape_dnbeheard_window(start_date: date, end_date: date):
    """Stáhne stránku a vrátí položky spadající do intervalu."""
    url = "https://dnbeheard.cz/kalendar-akci/"
    try:
        html = fetch(url, headers=HEADERS, timeout=30).text
    except Exception:
        return []
    soup = BS(html, "html.parser")

    items = []
    current_month = date(start_date.year, start_date.month, 1)
    end_month = date(end_date.year, end_date.month, 1)
    while current_month <= end_month:
        h = cz_month_h2(soup, current_month.month)
        if h:
            items += parse_dnbeheard_lines(h, year=current_month.year)
        if current_month.month == 12:
            current_month = date(current_month.year + 1, 1, 1)
        else:
            current_month = date(current_month.year, current_month.month + 1, 1)

    picked = []
    for it in items:
        d = it["date"].date()
        if start_date <= d <= end_date:
            picked.append(it)

    seen = set()
    unique = []
    for it in sorted(picked, key=lambda x: x["date"]):
        k = (it["title"].lower(), it["date"].date().isoformat())
        if k in seen:
            continue
        seen.add(k)
        unique.append(it)

    pri = [x for x in unique if event_is_priority(x["title"], x.get("foreign_guest", False))]
    return pri if pri else unique

# ---------------------------------------------------------------------------
# Eventy svět — scrapery (multi-RA + promotéři)
# ---------------------------------------------------------------------------

ANNOUNCE_KEYS = (
    "datePublished", "published", "publishDate", "publishedAt",
    "dateCreated", "created", "createdAt", "created_time",
    "updatedAt", "modified", "lastModified"
)

EVENT_NAME_KEYS = (
    "name","title","eventName","headline","event_title",
    "shortTitle","nameRaw","displayName","eventTitle",
)
EVENT_START_KEYS = (
    "startDate","start_date","start","start_time","startTime",
    "startAt","start_at","startLocal","start_local","startUTC","startUtc",
    "startTimestamp","startsAt","date","eventStart","eventStartDate",
    "event_start","eventDate","event_date","eventDateTime","event_date_time",
    "dateStart","date_start","startDateTime","start_date_time","localDate","dateTime",
)
EVENT_END_KEYS = (
    "endDate","end_date","end","end_time","endTime","endAt","end_at",
    "endLocal","end_local","endUTC","endUtc","endTimestamp","endsAt",
    "eventEnd","eventEndDate","event_end","eventEndTime","eventEndDateTime",
    "dateEnd","date_end","endDateTime","end_date_time",
)
EVENT_URL_KEYS = (
    "url","link","ticket_url","tickets","website","permalink","slug",
    "eventUrl","eventURL","event_url","shareUrl","shareURL","share_url",
    "shareLink","path","href","webpage",
)

def ensure_date_value(value, _visited=None):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if _visited is None:
        _visited = set()

    if isinstance(value, dict):
        obj_id = id(value)
        if obj_id in _visited:
            return None
        _visited.add(obj_id)

        if all(key in value for key in ("year", "month", "day")):
            try:
                def parse_part(key, default=None):
                    if key not in value:
                        if default is None: raise ValueError
                        return default
                    raw = value[key]
                    if raw is None or (isinstance(raw, str) and not raw.strip()):
                        if default is None: raise ValueError
                        return default
                    if isinstance(raw, str): raw = raw.strip()
                    return int(raw)
                year = parse_part("year")
                month = parse_part("month")
                day = parse_part("day")
                hour = parse_part("hour", 0)
                minute = parse_part("minute", 0)
                dt_candidate = datetime(year, month, day, hour, minute, tzinfo=TZ)
                return dt_candidate.date()
            except Exception:
                pass

        candidate_keys = (
            "start","startDate","start_date","from","date","dateStart","date_start",
            "iso","isoDate","iso8601","isoDateTime","iso_datetime","@value","value",
            "datetime","dateTime","time","timestamp","end","endDate","end_date","to","until",
        )
        for key in candidate_keys:
            if key in value and value[key]:
                result = ensure_date_value(value[key], _visited)
                if result:
                    return result
        for v in value.values():
            result = ensure_date_value(v, _visited)
            if result:
                return result
        return None

    if isinstance(value, (list, tuple, set)):
        for item in value:
            result = ensure_date_value(item, _visited)
            if result:
                return result
        return None

    dt = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        try:
            if value > 1_000_000_000_000:
                value = value / 1000.0
            dt = datetime.fromtimestamp(value, tz=timezone.utc)
        except Exception:
            return None
    elif isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            dt = dtparse(value)
        except Exception:
            return None
    elif isinstance(value, date):
        return value
    else:
        return None

    if not dt:
        return None
    if dt.tzinfo is None:
        try:
            dt = TZ.localize(dt)
        except Exception:
            dt = dt.replace(tzinfo=TZ)
    else:
        dt = dt.astimezone(TZ)
    return dt.date()

def extract_location(value):
    if not value:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        parts = []
        for key in ("name", "venue", "label", "title", "venueName", "locationName"):
            if value.get(key):
                parts.append(str(value[key]))
        address = value.get("address")
        if isinstance(address, dict):
            for key in (
                "addressLocality","addressRegion","addressCountry","postalCode",
                "city","country","state","region",
            ):
                if address.get(key):
                    parts.append(str(address[key]))
        elif isinstance(address, str):
            parts.append(address)
        location_obj = value.get("location")
        if isinstance(location_obj, dict):
            loc = extract_location(location_obj)
            if loc:
                parts.append(loc)
        for key in (
            "city","country","addressLocality","addressRegion","addressCountry",
            "locality","region","state","shortAddress",
        ):
            if value.get(key):
                parts.append(str(value[key]))
        if parts:
            return ", ".join([p.strip() for p in parts if p])
    if isinstance(value, (list, tuple)):
        for item in value:
            loc = extract_location(item)
            if loc:
                return loc
    return ""

def first_value(obj, keys):
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if key in obj:
            val = obj[key]
            if isinstance(val, (list, tuple)):
                for item in val:
                    if item:
                        return item
            elif isinstance(val, dict) and "url" in val:
                return val["url"]
            elif val:
                return val
    return None

# --------- STRIKTNĚJŠÍ DETEKTOR EVENTŮ (odmítá články) ---------
def is_event_dict(obj):
    if not isinstance(obj, dict):
        return False

    bad_types = {"newsarticle", "article", "blogposting"}
    def type_normalized(x):
        if isinstance(x, str):
            return {x.lower()}
        if isinstance(x, (list, tuple, set)):
            return {str(t).lower() for t in x if t}
        return set()

    typ = type_normalized(obj.get("@type"))
    if bad_types & typ:
        return False

    def type_is_event(value):
        types = type_normalized(value)
        return any("event" in t for t in types)

    # 1) JSON-LD: @type obsahuje Event
    if type_is_event(obj.get("@type")):
        return True

    # 2) GraphQL/Next data: jiné klíče s typem
    for type_key in ("modelType", "__typename", "kind", "itemType", "type"):
        if type_is_event(obj.get(type_key)):
            return True

    # 3) Měkké pravidlo: musí být název i nějaký start
    has_name = any(k in obj and obj.get(k) for k in EVENT_NAME_KEYS)
    if not has_name:
        return False

    def has_start(container):
        if not isinstance(container, dict):
            return False
        return any(key in container for key in EVENT_START_KEYS)

    if has_start(obj):
        return True

    for nested_key in ("dates", "dateInfo", "schedule", "eventDates", "timing", "times"):
        nested = obj.get(nested_key)
        if isinstance(nested, dict) and has_start(nested):
            return True
        if isinstance(nested, (list, tuple)):
            for item in nested:
                if isinstance(item, dict) and has_start(item):
                    return True

    return False

def iterate_event_like(obj):
    if isinstance(obj, dict):
        if is_event_dict(obj):
            yield obj
        for key in ("event", "node", "item", "data", "attributes", "content"):
            if key in obj and isinstance(obj[key], dict):
                yield from iterate_event_like(obj[key])
        if "@graph" in obj and isinstance(obj["@graph"], (list, tuple)):
            for item in obj["@graph"]:
                yield from iterate_event_like(item)
        if obj.get("@type") == "ItemList" and isinstance(obj.get("itemListElement"), (list, tuple)):
            for item in obj["itemListElement"]:
                yield from iterate_event_like(item)
        for value in obj.values():
            if isinstance(value, (dict, list, tuple)):
                yield from iterate_event_like(value)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from iterate_event_like(item)

# --------- RA-FILTR uvnitř builderu: jen /events a s lokací ---------
def build_event_from_raw(raw, source, base_url):
    if not isinstance(raw, dict):
        return None
    obj = raw
    changed = True
    while changed:
        changed = False
        for key in ("event", "node", "item", "data", "attributes", "content"):
            val = obj.get(key)
            if isinstance(val, dict) and is_event_dict(val):
                obj = val
                changed = True
                break

    title = first_value(obj, EVENT_NAME_KEYS) or first_value(raw, EVENT_NAME_KEYS)
    if not title:
        return None
    start_val = first_value(obj, EVENT_START_KEYS) or first_value(raw, EVENT_START_KEYS)
    if not start_val:
        for container_key in ("dates", "dateInfo", "schedule", "eventDates", "timing", "times"):
            container = obj.get(container_key) or raw.get(container_key)
            if isinstance(container, dict):
                start_val = first_value(container, EVENT_START_KEYS) or container.get("start")
                if start_val:
                    break
            elif isinstance(container, (list, tuple)):
                for item in container:
                    if isinstance(item, dict):
                        start_val = first_value(item, EVENT_START_KEYS) or item.get("start")
                        if start_val:
                            break
                if start_val:
                    break
    start_date = ensure_date_value(start_val)
    if not start_date:
        return None

    end_val = first_value(obj, EVENT_END_KEYS) or first_value(raw, EVENT_END_KEYS)
    if not end_val and isinstance(start_val, dict):
        for key in ("end", "endDate", "end_date", "to", "until"):
            if start_val.get(key):
                end_val = start_val[key]
                break
    if not end_val:
        for container_key in ("dates", "dateInfo", "schedule", "eventDates", "timing", "times"):
            container = obj.get(container_key) or raw.get(container_key)
            if isinstance(container, dict):
                end_val = first_value(container, EVENT_END_KEYS) or container.get("end")
                if end_val:
                    break
            elif isinstance(container, (list, tuple)):
                for item in container:
                    if isinstance(item, dict):
                        end_val = first_value(item, EVENT_END_KEYS) or item.get("end")
                        if end_val:
                            break
                if end_val:
                    break
    end_date = ensure_date_value(end_val) or start_date
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    location = (
        extract_location(obj.get("location")) or
        extract_location(obj.get("venue")) or
        extract_location(obj.get("place")) or
        extract_location(obj.get("eventLocation")) or
        extract_location(obj.get("club")) or
        extract_location(raw.get("venue")) or
        extract_location(raw.get("location")) or
        extract_location(raw.get("eventLocation")) or
        ", ".join(filter(None, [obj.get("city"), obj.get("country")])) or
        ", ".join(filter(None, [raw.get("city"), raw.get("country")]))
    )
    location = clean_text(location) if location else ""

    raw_url = first_value(obj, EVENT_URL_KEYS) or first_value(raw, EVENT_URL_KEYS)
    if isinstance(raw_url, dict):
        raw_url = raw_url.get("url") or raw_url.get("@id")
    if isinstance(raw_url, (list, tuple)):
        raw_url = next((x for x in raw_url if x), None)
    if raw_url and isinstance(raw_url, str):
        raw_url = raw_url.strip()
    if raw_url:
        if raw_url.startswith("//"):
            parsed = urlparse(base_url)
            url = f"{parsed.scheme}:{raw_url}"
        elif raw_url.startswith("http"):
            url = raw_url
        else:
            url = urljoin(base_url, raw_url)
    else:
        url = base_url

    # RA specifický filtr: jen skutečné eventy
    if source == "Resident Advisor":
        try:
            p = urlparse(url)
            if "/events" not in p.path:  # např. /news, /features ... ven
                return None
        except Exception:
            return None
        if not location:
            return None

    return {
        "title": clean_text(title),
        "location": location,
        "start_date": start_date,
        "end_date": end_date,
        "url": url,
        "source": source,
    }

def extract_events_from_html(html, source, base_url):
    soup = BS(html, "html.parser")
    events = []
    for script in soup.find_all("script"):
        script_type = (script.get("type") or "").lower()
        script_id = script.get("id") or ""
        if "json" not in script_type and script_id != "__NEXT_DATA__":
            continue
        text = script.string or script.text or ""
        text = text.strip()
        if not text:
            continue
        try:
            data = json.loads(text)
        except Exception:
            continue
        for raw in iterate_event_like(data):
            ev = build_event_from_raw(raw, source, base_url)
            if ev:
                events.append(ev)
    return events

# --------- Síto pro světové eventy (RA musí mít lokaci) ---------
def filter_world_events(events, start_date, end_date):
    out = []
    for ev in events:
        start = ev.get("start_date")
        end = ev.get("end_date") or start
        if isinstance(start, datetime):
            start = start.date()
        if isinstance(end, datetime):
            end = end.date()
        if not isinstance(start, date):
            continue
        if not isinstance(end, date):
            end = start
        # interval
        if end < start_date or start > end_date:
            continue
        # název
        if not ev.get("title"):
            continue
        # RA second-pass: musí mít lokaci
        if ev.get("source") == "Resident Advisor" and not ev.get("location"):
            continue

        ev = ev.copy()
        ev["start_date"] = start
        ev["end_date"] = end
        out.append(ev)
    return out

def scrape_world_events_generic(url, source, start_date, end_date, base_url=None):
    base = base_url or url
    html = ""
    try:
        html = fetch(url, headers=HEADERS, timeout=30).text
    except Exception:
        html = ""
    events = []
    if html:
        events = filter_world_events(extract_events_from_html(html, source, base), start_date, end_date)
    return events

# --- RA MULTI-REGION --------------------------------------------------------
RA_LOCATIONS = [
    # UK
    "https://ra.co/events/uk/london/drumandbass",
    "https://ra.co/events/uk/manchester/drumandbass",
    "https://ra.co/events/uk/bristol/drumandbass",
    "https://ra.co/events/uk/all/drumandbass",
    # EU
    "https://ra.co/events/nl/amsterdam/drumandbass",
    "https://ra.co/events/be/all/drumandbass",
    "https://ra.co/events/de/berlin/drumandbass",
    "https://ra.co/events/de/all/drumandbass",
    # US
    "https://ra.co/events/us/newyork/drumandbass",
    "https://ra.co/events/us/losangeles/drumandbass",
    "https://ra.co/events/us/all/drumandbass",
    # Fallback – globální listing
    "https://ra.co/events?genre=drum-and-bass",
]

def scrape_resident_advisor_multi(start_date: date, end_date: date):
    out = []
    for url in RA_LOCATIONS:
        try:
            out.extend(
                scrape_world_events_generic(
                    url=url,
                    source="Resident Advisor",
                    start_date=start_date,
                    end_date=end_date,
                    base_url="https://ra.co/",
                )
            )
        except Exception:
            continue
    return out

# --- Další promotéři --------------------------------------------------------
def scrape_hospitality_events(start_date: date, end_date: date):
    url = "https://hospitalitydnb.com/pages/events"
    return scrape_world_events_generic(url, "Hospitality", start_date, end_date, base_url="https://hospitalitydnb.com/")

def scrape_liquicity_events(start_date: date, end_date: date):
    url = "https://www.liquicity.com/pages/events"
    return scrape_world_events_generic(url, "Liquicity", start_date, end_date, base_url="https://www.liquicity.com/")

def scrape_dnballstars_events(start_date: date, end_date: date):
    url = "https://www.dnballstars.com/pages/events"
    return scrape_world_events_generic(url, "DnB Allstars", start_date, end_date, base_url="https://www.dnballstars.com/")

def scrape_rampage_events(start_date: date, end_date: date):
    url = "https://www.rampage.be/events"
    return scrape_world_events_generic(url, "Rampage", start_date, end_date, base_url="https://www.rampage.be/")

def scrape_korsakov_events(start_date: date, end_date: date):
    url = "https://korsakovmusic.com/pages/events"
    return scrape_world_events_generic(url, "Korsakov", start_date, end_date, base_url="https://korsakovmusic.com/")

def scrape_darkshire_events(start_date: date, end_date: date):
    url = "https://www.darkshire.cz/en/events"
    return scrape_world_events_generic(url, "Darkshire", start_date, end_date, base_url="https://www.darkshire.cz/")

def scrape_beatsforlove_events(start_date: date, end_date: date):
    url = "https://www.beatsforlove.cz/en/events"
    return scrape_world_events_generic(url, "Beats for Love", start_date, end_date, base_url="https://www.beatsforlove.cz/")

def scrape_hoofbeats_events(start_date: date, end_date: date):
    url = "https://www.hoofbeats.cz/events"
    return scrape_world_events_generic(url, "Hoofbeats", start_date, end_date, base_url="https://www.hoofbeats.cz/")

def scrape_roxy_events(start_date: date, end_date: date):
    url = "https://www.roxy.cz/program"
    return scrape_world_events_generic(url, "Roxy", start_date, end_date, base_url="https://www.roxy.cz/")

def scrape_epic_events(start_date: date, end_date: date):
    url = "https://epicprague.com/en/program"
    return scrape_world_events_generic(url, "EPIC", start_date, end_date, base_url="https://epicprague.com/")

def scrape_facebook_events(start_date: date, end_date: date):
    token = FACEBOOK_ACCESS_TOKEN
    pages = load_facebook_pages()
    if not token or not pages:
        return []

    since_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=TZ) - timedelta(days=1)
    until_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=TZ) + timedelta(days=1)
    since_ts = int(since_dt.timestamp())
    until_ts = int(until_dt.timestamp())

    events = []
    for page_id, label in pages.items():
        url = f"https://graph.facebook.com/v17.0/{page_id}/events"
        params = {
            "access_token": token,
            "since": since_ts,
            "until": until_ts,
            "fields": "id,name,start_time,end_time,place",
            "limit": 100,
        }
        next_url = url
        next_params = params
        while next_url:
            try:
                resp = requests.get(next_url, params=next_params, timeout=20)
                resp.raise_for_status()
                payload = resp.json()
            except Exception:
                break

            data_list = payload.get("data") or []
            for ev in data_list:
                name = clean_text(ev.get("name") or "")
                if not name:
                    continue
                start_val = ev.get("start_time")
                end_val = ev.get("end_time") or start_val
                start_date_val = ensure_date_value(start_val)
                end_date_val = ensure_date_value(end_val) or start_date_val
                if not start_date_val:
                    continue
                if end_date_val and end_date_val < start_date:
                    continue
                if start_date_val > end_date:
                    continue
                location = ""
                place = ev.get("place")
                if isinstance(place, dict):
                    location = extract_location(place)
                fb_url = f"https://www.facebook.com/events/{ev.get('id')}" if ev.get("id") else ""
                events.append(
                    {
                        "title": name,
                        "location": location,
                        "start_date": start_date_val,
                        "end_date": end_date_val,
                        "url": fb_url,
                        "source": f"Facebook {label}",
                    }
                )

            paging = payload.get("paging") or {}
            next_url = paging.get("next")
            next_params = None
    return events

def scrape_world_events_window(start_date: date, end_date: date):
    scrapers = (
        scrape_resident_advisor_multi,   # multi-region RA
        scrape_hospitality_events,
        scrape_liquicity_events,
        scrape_dnballstars_events,
        scrape_rampage_events,
        scrape_korsakov_events,
        scrape_darkshire_events,
        scrape_beatsforlove_events,
        scrape_hoofbeats_events,
        scrape_roxy_events,
        scrape_epic_events,
    )
    combined = []
    for fn in scrapers:
        try:
            events = fn(start_date, end_date)
        except Exception:
            events = []
        for ev in events:
            start = ev.get("start_date")
            end = ev.get("end_date") or start
            if isinstance(start, datetime):
                start = start.date()
            if isinstance(end, datetime):
                end = end.date()
            if not isinstance(start, date):
                continue
            if not isinstance(end, date):
                end = start
            ev = ev.copy()
            ev["start_date"] = start
            ev["end_date"] = end
            combined.append(ev)

    # Facebook (pokud je token)
    try:
        fb_events = scrape_facebook_events(start_date, end_date)
    except Exception:
        fb_events = []
    for ev in fb_events:
        start = ev.get("start_date")
        end = ev.get("end_date") or start
        if isinstance(start, datetime):
            start = start.date()
        if isinstance(end, datetime):
            end = end.date()
        if not isinstance(start, date):
            continue
        if not isinstance(end, date):
            end = start
        ev = ev.copy()
        ev["start_date"] = start
        ev["end_date"] = end
        combined.append(ev)

    # dedupe
    seen = set()
    unique = []
    for ev in sorted(combined, key=lambda x: (x["start_date"], (x.get("title") or "").lower())):
        key = (
            (ev.get("title") or "").strip().lower(),
            (ev.get("location") or "").strip().lower(),
            ev["start_date"],
            ev["end_date"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(ev)
    return unique

def fmt_event_span(start: date, end: date) -> str:
    if start == end:
        return f"{start.day}. {start.month}. {start.year}"
    return fmt_date_range(start, end)

def build_events_section(prev_start: date, prev_end: date):
    """Složí bloky pro ČR/SK i svět – recap a aktuální týden."""
    next_start = prev_end + timedelta(days=1)
    next_end = next_start + timedelta(days=EVENT_FUTURE_DAYS - 1)

    cz_prev = scrape_dnbeheard_window(prev_start, prev_end)
    cz_next = scrape_dnbeheard_window(next_start, next_end)
    world_prev = scrape_world_events_window(prev_start, prev_end)
    world_next = scrape_world_events_window(next_start, next_end)

    def format_cz(it):
        idx = add_ref(it.get("link") or "https://dnbeheard.cz/kalendar-akci/", "DnBHeard")
        dstr = fmt_date(it["date"])
        city = f" #{it['city']}" if it.get("city") else ""
        guest = " 👑" if it.get("foreign_guest") else ""
        return f"* {it['title']}{guest}{city} ({dstr}) ([DnBHeard][{idx}])"

    def format_world(it):
        idx = add_ref(it.get("url"), it.get("source", "Event"))
        location = f" – {it['location']}" if it.get("location") else ""
        dstr = fmt_event_span(it["start_date"], it["end_date"])
        label = it.get("source") or "Event"
        return f"* {it['title']}{location} ({dstr}) ([{label}][{idx}])"

    def render_list(items, formatter):
        if items:
            return [formatter(it) for it in items]
        return ["* Žádné relevantní novinky tento týden."]

    lines = []
    lines.append("## Eventy ČR / SK")
    lines.append("")
    lines.append("### Proběhlé akce v minulém týdnu")
    lines.extend(render_list(cz_prev, format_cz))
    lines.append("")
    lines.append("### Chystané akce v aktuálním týdnu")
    lines.extend(render_list(cz_next, format_cz))
    lines.append("")
    lines.append("### Nově oznámené")
    lines.append("* Žádné relevantní novinky tento týden.")
    lines.append("")
    lines.append("## Eventy – svět")
    lines.append("")
    lines.append("### Proběhlé akce v minulém týdnu")
    lines.extend(render_list(world_prev, format_world))
    lines.append("")
    lines.append("### Chystané akce v aktuálním týdnu")
    lines.extend(render_list(world_next, format_world))
    lines.append("")

    return "\n".join(lines) + "\n"

# ---------------------------------------------------------------------------
# Výstup — pouze MINULÝ TÝDEN (Svět / ČR-SK / Reddit / Kuriozita) + Eventy bloky
# ---------------------------------------------------------------------------
def pick(items, need):
    return items[:need] if len(items)>=need else items

def format_news_block(it):
    dstr = fmt_date(it["date"])
    title = it["title"] or "Novinka"
    summary = summarize_item(it)
    ref_idx = add_ref(it["link"], it["source"])
    lines = [f"### {title} ({dstr})", "", summary, "", f"Zdroj: [{it['source']}][{ref_idx}]"]
    return "\n".join(lines)

def build_section(header, period, items, min_needed):
    lines = [f"## {header} ({period})", ""]
    if len(items) < min_needed:
        lines.append("Žádné zásadní novinky za sledované období.")
        lines.append("")
        return "\n".join(lines)
    for idx, it in enumerate(items):
        lines.append(format_news_block(it))
        if idx != len(items) - 1:
            lines.append("")
    lines.append("")
    return "\n".join(lines)

def period_str(a,b):
    return f"{a.day}.–{b.day}. {b.month}. {b.year}"

PER_PREV = period_str(PREV_MON, PREV_SUN)

# Naplnění feed položek za předchozí týden
for f in FEEDS:
    feed = fetch_feed(f["url"])
    if not feed or not feed.entries:
        continue
    for e in feed.entries:
        it = entry_to_item(e, f["source_label"])
        if not it["date"]:
            continue
        if f["section"] == "reddit":
            if within(it["date"], PREV_MON, PREV_SUN):
                reddit_prev.append(it)
            continue
        sec = classify_section(e, f["source_label"], it["link"])
        it["section"] = sec
        if sec == "czsk":
            if not is_czsk_dnb(it["title"], it["summary"]):
                continue
        else:
            if not is_dnb_related(it["title"], it["summary"], it["link"]):
                continue
        if within(it["date"], PREV_MON, PREV_SUN):
            if sec == "czsk":
                items_prev_czsk.append(it)
            else:
                items_prev_world.append(it)

items_prev_world = dedupe(items_prev_world, maxn=20)
items_prev_czsk  = dedupe(items_prev_czsk,  maxn=10)
reddit_prev      = dedupe(reddit_prev,      maxn=8)

world_prev = pick(items_prev_world, MIN_WORLD)
cz_prev    = pick(items_prev_czsk,  MIN_CZSK)
rd_prev    = pick(reddit_prev,      max(MIN_REDDIT, 3))  # ideál 3

def format_reddit_block(it):
    title = it["title"] or "Vlákno"
    summary = clean_text(f"{title}. {it['summary'] or ''}", 260)
    dstr = fmt_date(it["date"])
    ref_idx = add_ref(it["link"], it["source"])
    block = [f"### {title} ({dstr})", "", summary, "", f"Zdroj: [{it['source']}][{ref_idx}]"]
    return "\n".join(block)


def build_reddit_section(period, lst):
    lines = [f"## Reddit vlákna ({period})", ""]
    if len(lst) < MIN_REDDIT:
        lines.append("Žádné zásadní novinky za sledované období.")
        lines.append("")
        return "\n".join(lines)
    for idx, it in enumerate(lst):
        lines.append(format_reddit_block(it))
        if idx != len(lst) - 1:
            lines.append("")
    lines.append("")
    return "\n".join(lines)

def pick_curiosity(cands):
    KEYS = ["AI","uměl","study","rekord","unikátní","rare","prototype","leak","patent","CDJ","controller","hardware"]
    for it in cands:
        blob = (it["title"]+" "+it["summary"]).lower()
        for k in KEYS:
            if k.lower() in blob:
                return it
    return cands[0] if cands else None

cur_prev = pick_curiosity(items_prev_world) or pick_curiosity(items_prev_czsk)

def build_curio(period, it):
    lines = [f"## Kuriozita ({period})", ""]
    if not it:
        lines.append("Žádné zásadní novinky za sledované období.")
        lines.append("")
        return "\n".join(lines)
    lines.append(format_news_block(it))
    lines.append("")
    return "\n".join(lines)

# Markdown skladba
if RUN_MAIN:
    md_parts = []
    md_parts.append(f"# DnB NOVINKY – {fmt_date(datetime.now(TZ))}\n")
    md_parts.append(build_section("Ze světa", PER_PREV, world_prev, MIN_WORLD))
    md_parts.append(build_section("Tuzemsko", PER_PREV, cz_prev, MIN_CZSK))
    md_parts.append(build_reddit_section(PER_PREV, rd_prev))
    md_parts.append(build_curio(PER_PREV, cur_prev))
    md_parts.append(build_events_section(PREV_MON, PREV_SUN))

    # Zdroje
    refs_lines = ["\n## Zdroje\n"]
    for i,(label,url) in enumerate(all_refs, start=1):
        refs_lines.append(f"[{i}]: {url}")
    md_parts.append("\n".join(refs_lines) + "\n")

    markdown_out = "\n".join(md_parts).strip()

    # Ulož MD + HTML (pro GitHub Pages)
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.md", "w", encoding="utf-8") as f:
        f.write(markdown_out + "\n")

    html_template = """<!DOCTYPE html><html lang="cs"><meta charset="utf-8">
    <title>DnB NOVINKY</title>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',Arial,sans-serif;max-width:900px;margin:40px auto;padding:0 16px;line-height:1.55}
    h1{font-size:28px;margin:0 0 16px}
    h2{font-size:20px;margin:24px 0 8px;border-bottom:1px solid #e5e7eb;padding-bottom:4px}
    h3{font-size:16px;margin:18px 0 6px}
    ul{padding-left:22px}
    code,pre{background:#f6f8fa}
    footer{margin-top:24px;font-size:12px;color:#666}
    </style>
    <body>
    <main>
    {CONTENT}
    </main>
    <footer>
    Vygenerováno automaticky. Zdrojové kanály: Google News RSS, Reddit RSS, YouTube channel RSS, RAVE.cz feed, DnBHeard, Resident Advisor (multi-region), Hospitality, Liquicity, DnB Allstars, Rampage, Korsakov, Darkshire, Beats for Love, Hoofbeats, Roxy, EPIC, Facebook Events.
    </footer>
    </body></html>"""
    html_content = md_to_html(markdown_out, output_format="xhtml1")
    html = html_template.replace("{CONTENT}", html_content)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("OK: docs/index.md + docs/index.html")

    # Volitelné: Google Slides webhook
    WEBHOOK = os.environ.get("APPSCRIPT_WEBHOOK_URL", "").strip()
    PRESENTATION_ID = os.environ.get("GOOGLE_SLIDES_PRESENTATION_ID", "").strip()
    if WEBHOOK and PRESENTATION_ID:
        payload = {
            "date": TODAY.strftime("%Y-%m-%d"),
            "period_prev": PER_PREV,
            "sections": {
                "world_prev": [format_news_block(it) for it in world_prev] or ["Žádné zásadní novinky za sledované období."],
                "cz_prev":    [format_news_block(it) for it in cz_prev]    or ["Žádné zásadní novinky za sledované období."],
                "reddit_prev": [format_reddit_block(it) for it in rd_prev] or ["Žádné zásadní novinky za sledované období."],
                "curiosity_prev": [format_news_block(cur_prev)] if cur_prev else ["Žádné zásadní novinky za sledované období."],
            },
            "sources": [f"[{i}]: {u}" for i,(_,u) in enumerate(all_refs, start=1)],
            "presentationId": PRESENTATION_ID
        }
        try:
            r = requests.post(WEBHOOK, json=payload, timeout=25)
            print("AppsScript:", r.status_code, r.text[:200])
        except Exception as ex:
            print("AppsScript error:", ex, file=sys.stderr)
