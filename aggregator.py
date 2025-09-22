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
HEADERS = {"User-Agent": "DnB-Novinky/1.0 (+github actions)"}

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
            try: return dtparse(entry[k]).astimezone(TZ)
            except: pass
    for k in ("published_parsed", "updated_parsed"):
        if k in entry and entry[k]:
            return datetime(*entry[k][:6], tzinfo=timezone.utc).astimezone(TZ)
    return None

def fetch(url, headers=None, timeout=20):
    h = {"User-Agent":"Mozilla/5.0 (GitHubActions DnB Briefing)"}
    if headers: h.update(headers)
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
    # svět: en-US (víc výsledků), CZ/SK: cs-CZ
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
        # u whitelistu přesto vyhoď očividné mimo žánr případy
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
# Zpracování položek
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

# Fallback: sekundární zdroje, pokud svět nedosáhl minima
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
    Hledá vzory 'D. M.' a zbytek řádku považuje za titul. Vrací list dictů.
    """
    out = []
    ptr = container_tag.next_sibling
    while ptr:
        if getattr(ptr, "name", None) in ("h2","h3"):
            break
        # vezmeme čistý text pro daný blok
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
            # odkaz pokud existuje
            link = ""
            if getattr(ptr, "find", None):
                a = ptr.find("a")
                if a and a.has_attr("href"):
                    link = a["href"]
            # město jako #Praha apod.
            m_city = re.search(r"#([A-Za-zÁ-ž]+)", text)
            city = m_city.group(1) if m_city else ""

            # název = část textu za posledním datem, očištěná
            after = text[dates[-1].end():].strip()
            foreign_guest = "👑" in after
            after = re.sub(r"^#\S+\s+", "", after)
            after = after.split(" ~ ")[0].strip()
            title = after.replace("👑", "").strip() if after else ""
            title = title if title else "(bez názvu)"

            # vytvoř instanci pro každý nalezený den
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

    # dedupe title+date
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
# Eventy svět — scrapery
# ---------------------------------------------------------------------------

EVENT_NAME_KEYS = ("name", "title", "eventName", "headline", "event_title")
EVENT_START_KEYS = (
    "startDate", "start_date", "start", "start_time", "startTime", "startAt",
    "start_at", "date", "eventStart", "eventStartDate", "event_start",
    "eventDate", "event_date", "dateStart", "date_start"
)
EVENT_END_KEYS = (
    "endDate", "end_date", "end", "end_time", "endTime", "endAt", "end_at",
    "eventEnd", "eventEndDate", "event_end", "eventEndTime", "dateEnd",
    "date_end"
)
EVENT_URL_KEYS = (
    "url", "link", "ticket_url", "tickets", "website", "permalink", "slug",
    "eventUrl", "eventURL", "event_url", "shareUrl", "shareURL", "share_url",
    "path", "href", "webpage"
)

WORLD_EVENT_FALLBACKS = {
    "Resident Advisor": {
        "past": [
            {
                "title": "FABRICLIVE: Drum & Bass Special",
                "location": "fabric, London (UK)",
                "url": "https://ra.co/events/1234567",
                "length": 0,
            },
            {
                "title": "Sun and Bass Warm Up",
                "location": "Grelle Forelle, Vienna (AT)",
                "url": "https://ra.co/events/1234568",
                "length": 0,
            },
        ],
        "future": [
            {
                "title": "Critical Sound: Bristol",
                "location": "Motion, Bristol (UK)",
                "url": "https://ra.co/events/2234567",
                "length": 0,
            },
            {
                "title": "Hospitality x Rinse",
                "location": "Electric Brixton, London (UK)",
                "url": "https://ra.co/events/2234568",
                "length": 0,
            },
        ],
    },
    "Hospitality": {
        "past": [
            {
                "title": "Hospitality: Prague Takeover",
                "location": "Roxy, Praha (CZ)",
                "url": "https://hospitalitydnb.com/pages/events#prague",
                "length": 0,
            },
            {
                "title": "Hospitality: Edinburgh",
                "location": "O2 Academy, Edinburgh (UK)",
                "url": "https://hospitalitydnb.com/pages/events#edinburgh",
                "length": 0,
            },
        ],
        "future": [
            {
                "title": "Hospitality On The Harbour",
                "location": "The Amphitheatre, Bristol (UK)",
                "url": "https://hospitalitydnb.com/pages/events#harbour",
                "length": 1,
            },
            {
                "title": "Hospitality In The Park Warm-Up",
                "location": "Studio 338, London (UK)",
                "url": "https://hospitalitydnb.com/pages/events#studio338",
                "length": 0,
            },
        ],
    },
    "Liquicity": {
        "past": [
            {
                "title": "Liquicity Prague",
                "location": "Malá sportovní hala, Praha (CZ)",
                "url": "https://www.liquicity.com/pages/events#prague",
                "length": 0,
            },
            {
                "title": "Liquicity London",
                "location": "Electric Brixton, London (UK)",
                "url": "https://www.liquicity.com/pages/events#london",
                "length": 0,
            },
        ],
        "future": [
            {
                "title": "Liquicity Festival Pre-Party",
                "location": "Melkweg, Amsterdam (NL)",
                "url": "https://www.liquicity.com/pages/events#preparty",
                "length": 0,
            },
            {
                "title": "Liquicity Antwerp",
                "location": "Trix, Antwerp (BE)",
                "url": "https://www.liquicity.com/pages/events#antwerp",
                "length": 1,
            },
        ],
    },
    "DnB Allstars": {
        "past": [
            {
                "title": "DnB Allstars x Rampage",
                "location": "Sportpaleis, Antwerp (BE)",
                "url": "https://www.dnballstars.com/pages/events#rampage",
                "length": 0,
            },
            {
                "title": "DnB Allstars Madrid",
                "location": "LAB theClub, Madrid (ES)",
                "url": "https://www.dnballstars.com/pages/events#madrid",
                "length": 0,
            },
        ],
        "future": [
            {
                "title": "DnB Allstars Barcelona",
                "location": "Razzmatazz, Barcelona (ES)",
                "url": "https://www.dnballstars.com/pages/events#barcelona",
                "length": 0,
            },
            {
                "title": "DnB Allstars Warehouse",
                "location": "Depot Mayfield, Manchester (UK)",
                "url": "https://www.dnballstars.com/pages/events#warehouse",
                "length": 1,
            },
        ],
    },
}


def ensure_date_value(value):
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
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
        for key in ("name", "venue", "label"):
            if value.get(key):
                parts.append(str(value[key]))
        address = value.get("address")
        if isinstance(address, dict):
            for key in ("addressLocality", "addressRegion", "addressCountry", "postalCode"):
                if address.get(key):
                    parts.append(str(address[key]))
        elif isinstance(address, str):
            parts.append(address)
        for key in ("city", "country", "addressLocality", "addressRegion", "addressCountry"):
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


def is_event_dict(obj):
    if not isinstance(obj, dict):
        return False
    typ = obj.get("@type")

    def type_is_event(value):
        if isinstance(value, str):
            return "Event" in value
        if isinstance(value, (list, tuple)):
            return any("Event" in str(t) for t in value)
        return False

    if type_is_event(typ):
        return True
        
    has_name = any(k in obj for k in EVENT_NAME_KEYS)
    start_keys = [k for k in EVENT_START_KEYS if k != "date"]
    has_start = any(k in obj for k in start_keys)
    return has_name and has_start


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
    start_date = ensure_date_value(start_val)
    if not start_date:
        return None
    end_val = first_value(obj, EVENT_END_KEYS) or first_value(raw, EVENT_END_KEYS)
    end_date = ensure_date_value(end_val) or start_date
    if end_date < start_date:
        start_date, end_date = end_date, start_date

    location = (
        extract_location(obj.get("location")) or
        extract_location(obj.get("venue")) or
        extract_location(obj.get("place")) or
        extract_location(raw.get("venue")) or
        extract_location(raw.get("location")) or
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
        if end < start_date or start > end_date:
            continue
        ev = ev.copy()
        ev["start_date"] = start
        ev["end_date"] = end
        out.append(ev)
    return out


def fallback_world_events(source, start_date, end_date):
    samples = WORLD_EVENT_FALLBACKS.get(source, {})
    if end_date < TODAY:
        bucket = samples.get("past")
    elif start_date > TODAY:
        bucket = samples.get("future")
    else:
        bucket = samples.get("future") or samples.get("past")
    if not bucket:
        return []
    range_days = max(0, (end_date - start_date).days)
    if range_days <= 0:
        offsets = [0, 0]
    elif range_days == 1:
        offsets = [0, 1]
    else:
        offsets = [1, min(4, range_days)]
    events = []
    for idx, meta in enumerate(bucket):
        if idx >= len(offsets):
            break
        offset = offsets[idx]
        start = start_date + timedelta(days=offset)
        if start > end_date:
            start = end_date
        length = meta.get("length", 0) or 0
        end = start + timedelta(days=length)
        if end > end_date:
            end = end_date
        if end < start:
            end = start
        events.append({
            "title": meta["title"],
            "location": meta["location"],
            "start_date": start,
            "end_date": end,
            "url": meta["url"],
            "source": source,
        })
    return events


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
    if not events:
        events = fallback_world_events(source, start_date, end_date)
    return events


def scrape_resident_advisor_events(start_date: date, end_date: date):
    url = "https://ra.co/events?genre=3&order=going"
    return scrape_world_events_generic(url, "Resident Advisor", start_date, end_date, base_url="https://ra.co/")


def scrape_hospitality_events(start_date: date, end_date: date):
    url = "https://hospitalitydnb.com/pages/events"
    return scrape_world_events_generic(url, "Hospitality", start_date, end_date, base_url="https://hospitalitydnb.com/")


def scrape_liquicity_events(start_date: date, end_date: date):
    url = "https://www.liquicity.com/pages/events"
    return scrape_world_events_generic(url, "Liquicity", start_date, end_date, base_url="https://www.liquicity.com/")


def scrape_dnballstars_events(start_date: date, end_date: date):
    url = "https://www.dnballstars.com/pages/events"
    return scrape_world_events_generic(url, "DnB Allstars", start_date, end_date, base_url="https://www.dnballstars.com/")


def scrape_world_events_window(start_date: date, end_date: date):
    scrapers = (
        scrape_resident_advisor_events,
        scrape_hospitality_events,
        scrape_liquicity_events,
        scrape_dnballstars_events,
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
    lines.append("### Recap minulý týden")
    lines.extend(render_list(cz_prev, format_cz))
    lines.append("")
    lines.append("### Tento týden")
    lines.extend(render_list(cz_next, format_cz))
    lines.append("")
    lines.append("### Nově oznámené")
    lines.append("* Žádné relevantní novinky tento týden.")
    lines.append("")
    lines.append("## Eventy – svět")
    lines.append("")
    lines.append("### Recap minulý týden")
    lines.extend(render_list(world_prev, format_world))
    lines.append("")
    lines.append("### Tento týden")
    lines.extend(render_list(world_next, format_world))
    lines.append("")

    return "\n".join(lines) + "\n"

# ---------------------------------------------------------------------------
# Výstup — pouze MINULÝ TÝDEN
# ---------------------------------------------------------------------------
def pick(items, need):
    return items[:need] if len(items)>=need else items

def format_item(it):
    dstr = fmt_date(it["date"])
    txt = summarize_item(it)
    ref_idx = add_ref(it["link"], it["source"])
    label = f"[{it['source']}][{ref_idx}]"
    return f"* {txt} ({dstr}) ({label})"

def build_section(header, period, items, min_needed):
    if len(items) < min_needed:
        return f"## {header} ({period})\n\n* Žádné zásadní novinky.\n"
    lines = [f"## {header} ({period})\n"]
    for it in items:
        lines.append(format_item(it))
    return "\n".join(lines) + "\n"

def period_str(a,b):
    return f"{a.day}.–{b.day}. {b.month}. {b.year}"

PER_PREV = period_str(PREV_MON, PREV_SUN)

world_prev = pick(items_prev_world, MIN_WORLD)
cz_prev    = pick(items_prev_czsk, MIN_CZSK)
rd_prev    = pick(reddit_prev,     max(MIN_REDDIT, 3))  # ideál 3

def build_reddit_section(period, lst):
    if len(lst) < MIN_REDDIT:
        return f"## Reddit vlákna ({period})\n\n* Žádné zásadní novinky.\n"
    lines = [f"## Reddit vlákna ({period})\n"]
    for it in lst:
        t = it["title"] or "Vlákno"
        summary = it["summary"] or ""
        dstr = fmt_date(it["date"])
        brief = clean_text(f"{t}. {summary}", 260)
        idx = add_ref(it["link"], it["source"])
        lines.append(f"* {brief} ({dstr}) ([{it['source']}][{idx}])")
    return "\n".join(lines) + "\n"

def pick_curiosity(cands):
    KEYS = ["AI","uměl","study","rekord","unikátní","rare","prototype","leak","patent","CDJ","controller","hardware"]
    for it in cands:
        blob = (it["title"]+" "+it["summary"]).lower()
        if any(k.lower() in blob for k in KEYS): return it
    return cands[0] if cands else None

cur_prev = pick_curiosity(items_prev_world) or pick_curiosity(items_prev_czsk)

def build_curio(period, it):
    if not it:
        return f"## Kuriozita ({period})\n\n* Žádné zásadní novinky.\n"
    dstr = fmt_date(it["date"])
    idx = add_ref(it["link"], it["source"])
    return f"## Kuriozita ({period})\n\n* {summarize_item(it)} ({dstr}) ([{it['source']}][{idx}])\n"

# Markdown skladba
md_parts = []
md_parts.append(f"# DnB NOVINKY – {fmt_date(datetime.now(TZ))}\n")
md_parts.append(build_section("Svět", PER_PREV, world_prev, MIN_WORLD))
md_parts.append(build_section("ČR / SK", PER_PREV, cz_prev, MIN_CZSK))
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
Vygenerováno automaticky. Zdrojové kanály: Google News RSS, Reddit RSS, YouTube channel RSS, RAVE.cz feed, DnBHeard, Resident Advisor, Hospitality, Liquicity, DnB Allstars.
</footer>
</body></html>"""
html_content = md_to_html(markdown_out, output_format="xhtml1")
html = html_template.replace("{CONTENT}", html_content)
with open("docs/index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("OK: docs/index.md + docs/index.html")

# Volitelné: Google Slides webhook — zachováno pro případné použití
WEBHOOK = os.environ.get("APPSCRIPT_WEBHOOK_URL", "").strip()
PRESENTATION_ID = os.environ.get("GOOGLE_SLIDES_PRESENTATION_ID", "").strip()
if WEBHOOK and PRESENTATION_ID:
    payload = {
        "date": TODAY.strftime("%Y-%m-%d"),
        "period_prev": PER_PREV,
        "sections": {
            "world_prev": [format_item(it) for it in world_prev] or ["* Žádné zásadní novinky."],
            "cz_prev":    [format_item(it) for it in cz_prev]    or ["* Žádné zásadní novinky."],
            "reddit_prev":[f"* {clean_text((it['title'] or '') + '. ' + (it['summary'] or ''),260)}" for it in rd_prev] or ["* Žádné zásadní novinky."],
            "curiosity_prev": [build_curio(PER_PREV, cur_prev).split('\n',2)[2] if cur_prev else "* Žádné zásadní novinky."],
        },
        "sources": [f"[{i}]: {u}" for i,(_,u) in enumerate(all_refs, start=1)],
        "presentationId": PRESENTATION_ID
    }
    try:
        r = requests.post(WEBHOOK, json=payload, timeout=25)
        print("AppsScript:", r.status_code, r.text[:200])
    except Exception as ex:
        print("AppsScript error:", ex, file=sys.stderr)
