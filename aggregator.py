#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, sys, json, time, hashlib
from datetime import datetime, timedelta, timezone
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

def week_bounds(d):
    mon = d - timedelta(days=d.weekday())
    sun = mon + timedelta(days=6)
    return mon, sun

CUR_MON, CUR_SUN = week_bounds(TODAY)
PREV_MON, PREV_SUN = week_bounds(TODAY - timedelta(days=7))

# ---------------------------------------------------------------------------
# Pomocné
# ---------------------------------------------------------------------------
def within(date_dt, start_date, end_date):
    d = date_dt.astimezone(TZ).date()
    return start_date <= d <= end_date

def clean_text(s, limit=400):
    if not s:
        return ""
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

def fetch(url, headers=None, timeout=20):
    h = {"User-Agent": "Mozilla/5.0 (GitHubActions DnB Briefing)"}
    if headers:
        h.update(headers)
    r = requests.get(url, headers=h, timeout=timeout)
    r.raise_for_status()
    return r

# --- URL normalizace a rozbalení z Google News --------------------------------
def resolve_news_url(link: str) -> str:
    try:
        u = urlparse(link)
        if u.netloc.endswith("news.google.com"):
            qs = parse_qs(u.query)
            if "url" in qs and qs["url"]:
                return unquote(qs["url"][0])
    except Exception:
        pass
    return link

def extract_original_url(entry):
    # 1) z entry.links
    for l in (entry.get("links") or []):
        href = l.get("href")
        if not href:
            continue
        if "news.google.com" in href:
            cand = resolve_news_url(href)
            if cand and "news.google.com" not in cand:
                return cand
        else:
            return href
    # 2) z HTML summary_detail.value / summary
    html = None
    sd = entry.get("summary_detail")
    if sd and isinstance(sd, dict):
        html = sd.get("value")
    if not html:
        html = entry.get("summary")
    if isinstance(html, str):
        m = re.search(r'href=[\'"](?P<u>https?://[^\'"]+)[\'"]', html)
        if m:
            u = resolve_news_url(m.group("u"))
            if "news.google.com" not in u:
                return u
        for m in re.finditer(r"https?://[^\s<>'\"]+", html):
            u = resolve_news_url(m.group(0))
            if "news.google.com" not in u:
                return u
    # 3) fallback
    return entry.get("link")

def normalize_url(u: str) -> str:
    try:
        p = urlparse(u)
        if not p.scheme or not p.netloc:
            return u
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
def google_news_feed(site, when_days=28):
    # svět: en-US; CZ/SK domény: cs-CZ
    if site.endswith(".cz") or site.endswith(".sk") or site in ("rave.cz", "musicserver.cz"):
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
        if m:
            return m.group(1)
    except Exception:
        return None
    return None

def youtube_rss_from_handle(handle):
    cid = youtube_channel_id_from_handle(handle)
    if not cid:
        return None
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
REDDITS = [("r/DnB", "DnB"), ("r/LetItRollFestival", "LetItRollFestival")]
YOUTUBES = ["@Liquicity", "@dnballstars", "@WeAreRampageEvents", "@DJMag", "@UKFDrumandBass"]

SECONDARY_SITES = [
    ("EDM.com", "edm.com"),
    ("Dancing Astronaut", "dancingastronaut.com"),
    ("Rolling Stone Australia", "rollingstone.com.au"),
    ("Billboard", "billboard.com"),
    ("DJ Mag", "djmag.com"),
]

POS = [
    "drum and bass", "drum’n’bass", "drum n bass", "dnb", "dn'b", "jungle",
    "neurofunk", "liquid", "jump up", "rollers", "ukf", "hospital records",
    "let it roll", "ram records", "blackout music", "shogun audio",
]
NEG = [
    "techno", "tech house", "house", "trance", "edm pop", "electro house",
    "hardstyle", "psytrance", "deep house", "progressive house", "hard techno",
]
CZSK_TOKENS = [
    "dnb", "drum and bass", "drum’n’bass", "drum n bass", "drum&bass",
    "neuro", "neurofunk", "liquid", "jump up", "rollers", "let it roll",
    "hospitality", "cross club", "roxy", "perpetuum", "fléda", "storm club",
    "bestiar", "fabric brno"
]
HEADERS = {"User-Agent": "DnB-Novinky/1.0 (+github actions)"}
ALLOWLIST = (
    "mixmag.net", "ra.co", "ukf.com", "djmag.com",
    "edm.com", "dancingastronaut.com", "rollingstone.com.au", "billboard.com",
    "youtube.com", "youtu.be", "rave.cz", "musicserver.cz", "dogsonacid.com"
)

MIN_WORLD = 5
MIN_CZSK = 2
MIN_REDDIT = 2

REDDIT_TITLE_NEG = [
    "track id", "id?", "what is this track", "free download",
    "promo", "my mix", "mixcloud", "out now"
]
def reddit_is_signal(title: str) -> bool:
    t = (title or "").lower()
    return not any(x in t for x in REDDIT_TITLE_NEG)

def is_dnb_related(title: str, summary: str, url: str) -> bool:
    t = f"{title} {summary}".lower()
    host = urlparse(url).netloc.lower()
    if any(host == d or host.endswith("." + d) for d in ALLOWLIST):
        return True
    return any(p in t for p in POS) and not any(n in t for n in NEG)

def is_czsk_dnb(title: str, summary: str) -> bool:
    t = f"{title} {summary}".lower()
    return any(x in t for x in CZSK_TOKENS) and not any(n in t for n in NEG)

def tags_hit(entry):
    try:
        tags = entry.get("tags") or []
        tags = [(t.get("term") or "").lower() for t in tags if isinstance(t, dict)]
        needles = ["dnb", "drum and bass", "drum&bass", "drum n bass", "drum’n’bass", "drumandbass"]
        return any(any(n in tg for n in needles) for tg in tags)
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Build seznam feedů
# ---------------------------------------------------------------------------
FEEDS = []
for name, domain in PRIMARY_SITES:
    FEEDS.append({
        "name": f"GoogleNews:{name}",
        "kind": "rss",
        "section": "world",
        "url": google_news_feed(domain, when_days=28),
        "source_label": name
    })
FEEDS.append({
    "name": "Rave.cz",
    "kind": "rss",
    "section": "czsk",
    "url": "https://www.rave.cz/feed/",
    "source_label": "RAVE.cz"
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
    "name": "DogsOnAcidForum",
    "kind": "rss",
    "section": "world",
    "url": xenforo_forum_index_rss("https://www.dogsonacid.com"),
    "source_label": "DogsOnAcid Forum"
})

# ---------------------------------------------------------------------------
# RA Events scraping (CZ/SK)
# ---------------------------------------------------------------------------
def _jsonld_blocks(html: str):
    out = []
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.S | re.I):
        txt = m.group(1).strip()
        try:
            data = json.loads(txt)
            if isinstance(data, list):
                out.extend([d for d in data if isinstance(d, dict)])
            elif isinstance(data, dict):
                out.append(data)
        except Exception:
            continue
    return out

def _parse_ra_event_page(url: str, html: str, tz=TZ):
    blocks = _jsonld_blocks(html)
    event = None
    for b in blocks:
        if b.get("@type") in ("Event", "MusicEvent"):
            event = b
            break
        if "@graph" in b and isinstance(b["@graph"], list):
            for g in b["@graph"]:
                if isinstance(g, dict) and g.get("@type") in ("Event", "MusicEvent"):
                    event = g
                    break
            if event:
                break
    if not event:
        return None
    name = clean_text(event.get("name") or "")
    start = event.get("startDate") or event.get("start_time") or event.get("start")
    dt = None
    if start:
        try:
            dt = dtparse(start).astimezone(tz)
        except Exception:
            dt = None
    loc_name, city = "", ""
    loc = event.get("location")
    if isinstance(loc, dict):
        loc_name = clean_text(loc.get("name") or "")
        addr = loc.get("address")
        if isinstance(addr, dict):
            city = clean_text(addr.get("addressLocality") or "")
    perf = event.get("performer") or event.get("performers") or []
    if isinstance(perf, dict):
        perf = [perf]
    perf_names = []
    for p in perf:
        if isinstance(p, dict):
            n = p.get("name")
            if n:
                perf_names.append(str(n))
        elif isinstance(p, str):
            perf_names.append(p)
    headliners = ", ".join(perf_names[:4])
    title = name if name else "RA event"
    parts = []
    if city or loc_name:
        parts.append(f"{city or ''}{', ' if city and loc_name else ''}{loc_name or ''}".strip(", "))
    if headliners:
        parts.append(f"headliner: {headliners}")
    summary = clean_text(" – ".join([p for p in parts if p])) or "Drum & bass event."
    return {
        "title": title,
        "summary": summary,
        "link": normalize_url(url),
        "date": dt,
        "source": "Resident Advisor",
        "section": "czsk",
    }

def _extract_ra_event_links_from_list(html: str, base="https://ra.co"):
    urls = set()
    soup = BS(html, "html.parser")
    for a in soup.select('a[href*="/events/"]'):
        href = a.get("href") or ""
        if not href:
            continue
        if href.startswith("/"):
            href = urljoin(base, href)
        if not href.startswith("https://ra.co/events/"):
            continue
        if re.search(r"/events/\d", href) or re.search(r"/events/.+/\d", href):
            urls.add(normalize_url(href))
    return list(urls)

def scrape_ra_czsk_events(max_pages=25):
    out = []
    list_urls = [
        "https://ra.co/events/cz/all/drumandbass",
        "https://ra.co/events/sk/all/drumandbass",
    ]
    try:
        for lu in list_urls:
            html = fetch(lu, headers=HEADERS, timeout=20).text
            ev_links = _extract_ra_event_links_from_list(html)
            for ev in ev_links[:max_pages]:
                try:
                    ev_html = fetch(ev, headers=HEADERS, timeout=20).text
                except Exception:
                    continue
                item = _parse_ra_event_page(ev, ev_html)
                if not item or not item.get("date"):
                    continue
                if not is_czsk_dnb(item["title"], item["summary"]) and not is_dnb_related(item["title"], item["summary"], item["link"]):
                    continue
                out.append(item)
    except Exception:
        pass
    return out

# ---------------------------------------------------------------------------
# DJ Mag scraper (News)
# ---------------------------------------------------------------------------
def scrape_djmag_news(max_articles=30):
    try:
        html = fetch("https://djmag.com/news", headers=HEADERS, timeout=20).text
    except Exception:
        return
    soup = BS(html, "html.parser")
    raw_links = []
    for a in soup.select('a[href*="/news/"]'):
        href = a.get("href")
        if not href:
            continue
        if href.startswith("/"):
            href = "https://djmag.com" + href
        if not href.startswith("https://djmag.com/news/"):
            continue
        raw_links.append(normalize_url(href))
    seen = set()
    urls = []
    for u in raw_links:
        if u in seen:
            continue
        seen.add(u)
        urls.append(u)
    for u in urls[:max_articles]:
        try:
            art = fetch(u, headers=HEADERS, timeout=20).text
        except Exception:
            continue
        s = BS(art, "html.parser")
        title = ""
        ogt = s.find("meta", attrs={"property": "og:title"})
        if ogt and ogt.get("content"):
            title = ogt["content"]
        if not title and s.title:
            title = s.title.string or ""
        title = clean_text(title, 300)
        desc_meta = s.find("meta", attrs={"name": "description"})
        summary = clean_text(desc_meta["content"] if desc_meta and desc_meta.get("content") else "")
        dt = None
        mtime = s.find("meta", attrs={"property": "article:published_time"}) or s.find("meta", attrs={"name": "article:published_time"})
        if mtime and mtime.get("content"):
            try:
                dt = dtparse(mtime["content"]).astimezone(TZ)
            except Exception:
                dt = None
        if not dt:
            for script in s.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string or "")
                    if isinstance(data, dict) and "datePublished" in data:
                        dt = dtparse(data["datePublished"]).astimezone(TZ); break
                    if isinstance(data, list):
                        for obj in data:
                            if isinstance(obj, dict) and "datePublished" in obj:
                                dt = dtparse(obj["datePublished"]).astimezone(TZ); break
                        if dt:
                            break
                except Exception:
                    pass
        if not dt:
            ttag = s.find("time")
            if ttag and (ttag.get("datetime") or ttag.text):
                try:
                    dt = dtparse(ttag.get("datetime") or ttag.text).astimezone(TZ)
                except Exception:
                    dt = None
        if not dt:
            continue
        item = {"title": title, "summary": summary, "link": u, "date": dt, "source": "DJ Mag", "section": "world"}
        if not is_dnb_related(title, summary, u):
            continue
        if within(dt, PREV_MON, PREV_SUN):
            items_prev_world.append(item)
        elif within(dt, CUR_MON, CUR_SUN):
            items_cur_world.append(item)

# ---------------------------------------------------------------------------
# Zpracování položek
# ---------------------------------------------------------------------------
def classify_section(entry, src_label, link):
    host = re.sub(r"^www\.", "", (re.findall(r"https?://([^/]+)", link) or [""])[0])
    tld = host.split(".")[-1] if host else ""
    if tld in ("cz", "sk") or "rave.cz" in host or "musicserver.cz" in host:
        return "czsk"
    return "world"

def entry_to_item(entry, source_label):
    raw_link = entry.get("link") or ""
    orig = extract_original_url(entry)
    if orig:
        link = normalize_url(orig)
    else:
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

items_prev_world, items_cur_world = [], []
items_prev_czsk, items_cur_czsk = [], []
reddit_prev, reddit_cur = [], []
all_refs, ref_map = [], {}

def add_ref(url, label):
    if url in ref_map:
        return ref_map[url]
    idx = len(all_refs) + 1
    ref_map[url] = idx
    all_refs.append((label, url))
    return idx

# 1) Sběr RSS
for f in FEEDS:
    feed = fetch_feed(f["url"])
    if not feed or not feed.entries:
        continue
    for e in feed.entries:
        it = entry_to_item(e, f["source_label"])
        if not it["date"]:
            continue
        if f["section"] == "reddit":
            if not reddit_is_signal(it["title"]):
                continue
            if within(it["date"], PREV_MON, PREV_SUN):
                reddit_prev.append(it)
            elif within(it["date"], CUR_MON, CUR_SUN):
                reddit_cur.append(it)
            continue
        sec = classify_section(e, f["source_label"], it["link"])
        it["section"] = sec
        if sec == "czsk":
            if not (tags_hit(e) or is_czsk_dnb(it["title"], it["summary"])):
                continue
        else:
            if not is_dnb_related(it["title"], it["summary"], it["link"]):
                continue
        if within(it["date"], PREV_MON, PREV_SUN):
            (items_prev_czsk if sec == "czsk" else items_prev_world).append(it)
        elif within(it["date"], CUR_MON, CUR_SUN):
            (items_cur_czsk if sec == "czsk" else items_cur_world).append(it)

# 2) Scrapery navíc
scrape_djmag_news()

# 3) RA CZ/SK eventy → doplň „ČR / SK“ podle data konání
_ra_items = scrape_ra_czsk_events(max_pages=30)
for it in _ra_items:
    if not it.get("date"):
        continue
    if within(it["date"], PREV_MON, PREV_SUN):
        items_prev_czsk.append(it)
    elif within(it["date"], CUR_MON, CUR_SUN):
        items_cur_czsk.append(it)

# ---------------------------------------------------------------------------
# Fallbacky
# ---------------------------------------------------------------------------
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

def topup_to_min(lst, needed, extras):
    if len(lst) >= needed:
        return lst
    room = needed - len(lst)
    seen = {uniq_key(x) for x in lst}
    add = []
    for it in sorted(extras, key=lambda x: x["date"], reverse=True):
        k = uniq_key(it)
        if k in seen:
            continue
        seen.add(k)
        add.append(it)
        if len(add) >= room:
            break
    return lst + add

def harvest_archival(sites, days=28, end_limit=None):
    # Vrátí kandidáty z posledních N dní, ne novější než end_limit (pokud je).
    cutoff = TODAY - timedelta(days=days)
    out = []
    for label, domain in sites:
        feed_url = google_news_feed(domain, when_days=days)
        feed = fetch_feed(feed_url)
        if not feed or not feed.entries:
            continue
        for e in feed.entries:
            it = entry_to_item(e, label)
            if not it["date"]:
                continue
            d = it["date"].date()
            if d < cutoff:
                continue
            if end_limit and d > end_limit:
                continue
            if not is_dnb_related(it["title"], it["summary"], it["link"]):
                continue
            it["section"] = "world"
            it["_archival"] = True
            out.append(it)
    return out

if len(items_prev_world) < MIN_WORLD:
    extra_prev = harvest_sites(SECONDARY_SITES, PREV_MON, PREV_SUN)
    items_prev_world = topup_to_min(items_prev_world, MIN_WORLD, extra_prev)
    if len(items_prev_world) < MIN_WORLD:
        arch_prev = harvest_archival(PRIMARY_SITES + SECONDARY_SITES, days=28, end_limit=PREV_SUN)
        items_prev_world = topup_to_min(items_prev_world, MIN_WORLD, arch_prev)

if len(items_cur_world) < MIN_WORLD:
    extra_cur = harvest_sites(SECONDARY_SITES, CUR_MON, CUR_SUN)
    items_cur_world = topup_to_min(items_cur_world, MIN_WORLD, extra_cur)
    if len(items_cur_world) < MIN_WORLD:
        arch_cur = harvest_archival(PRIMARY_SITES + SECONDARY_SITES, days=28, end_limit=CUR_SUN)
        items_cur_world = topup_to_min(items_cur_world, MIN_WORLD, arch_cur)

# ---------------------------------------------------------------------------
# Deduplikace
# ---------------------------------------------------------------------------
def dedupe(lst, maxn=None):
    seen, out = set(), []
    for it in sorted(lst, key=lambda x: x["date"], reverse=True):
        k = uniq_key(it)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
        if maxn and len(out) >= maxn:
            break
    return out

items_prev_world = dedupe(items_prev_world, maxn=20)
items_cur_world  = dedupe(items_cur_world,  maxn=20)
items_prev_czsk  = dedupe(items_prev_czsk,  maxn=10)
items_cur_czsk   = dedupe(items_cur_czsk,   maxn=10)
reddit_prev      = dedupe(reddit_prev,      maxn=8)
reddit_cur       = dedupe(reddit_cur,       maxn=8)

# ---------------------------------------------------------------------------
# Výstup
# ---------------------------------------------------------------------------
def pick(items, need):
    return items[:need] if len(items) >= need else items

def format_item(it):
    dstr = it["date"].strftime("%-d. %-m. %Y")
    txt = summarize_item(it)
    if it.get("_archival"):
        txt = f"Archivní – {txt}"
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

def period_str(a, b):
    return f"{a.strftime('%-d.')}\u2009–\u2009{b.strftime('%-d. %m. %Y')}"

PER_PREV = period_str(PREV_MON, PREV_SUN)
PER_CUR  = period_str(CUR_MON, CUR_SUN)

world_prev = pick(items_prev_world, MIN_WORLD)
world_cur  = pick(items_cur_world,  MIN_WORLD)
cz_prev    = pick(items_prev_czsk,  MIN_CZSK)
cz_cur     = pick(items_cur_czsk,   MIN_CZSK)
rd_prev    = pick(reddit_prev,      MIN_REDDIT + 1)
rd_cur     = pick(reddit_cur,       MIN_REDDIT + 1)

def build_reddit_section(period, lst):
    if len(lst) < MIN_REDDIT:
        return f"## Reddit vlákna ({period})\n\n* Žádné zásadní novinky.\n"
    lines = [f"## Reddit vlákna ({period})\n"]
    for it in lst:
        t = it["title"] or "Vlákno"
        summary = it["summary"] or ""
        dstr = it["date"].strftime("%-d. %-m. %Y")
        brief = clean_text(f"{t}. {summary}", 260)
        idx = add_ref(it["link"], it["source"])
        lines.append(f"* {brief} ({dstr}) ([{it['source']}][{idx}])")
    return "\n".join(lines) + "\n"

def pick_curiosity(cands):
    KEYS = ["AI", "uměl", "study", "rekord", "unikátní", "rare", "prototype", "leak", "patent", "CDJ", "controller", "hardware"]
    for it in cands:
        blob = (it["title"] + " " + it["summary"]).lower()
        if any(k.lower() in blob for k in KEYS):
            return it
    return cands[0] if cands else None

cur_prev = pick_curiosity(items_prev_world) or pick_curiosity(items_prev_czsk)
cur_cur  = pick_curiosity(items_cur_world)  or pick_curiosity(items_cur_czsk)

def build_curio(period, it):
    if not it:
        return f"## Kuriozita ({period})\n\n* Žádné zásadní novinky.\n"
    dstr = it["date"].strftime("%-d. %-m. %Y")
    idx = add_ref(it["link"], it["source"])
    return f"## Kuriozita ({period})\n\n* {summarize_item(it)} ({dstr}) ([{it['source']}][{idx}])\n"

md_parts = []
md_parts.append(f"# DnB NOVINKY – {TODAY.strftime('%-d. %-m. %Y')}\n")
md_parts.append(build_section("Svět", PER_PREV, world_prev, MIN_WORLD))
md_parts.append(build_section("Svět", PER_CUR,  world_cur,  MIN_WORLD))
md_parts.append(build_section("ČR / SK", PER_PREV, cz_prev, MIN_CZSK))
md_parts.append(build_section("ČR / SK", PER_CUR,  cz_cur,  MIN_CZSK))
md_parts.append(build_reddit_section(PER_PREV, rd_prev))
md_parts.append(build_reddit_section(PER_CUR,  rd_cur))
md_parts.append(build_curio(PER_PREV, cur_prev))
md_parts.append(build_curio(PER_CUR,  cur_cur))

refs_lines = ["\n## Zdroje\n"]
for i, (label, url) in enumerate(all_refs, start=1):
    refs_lines.append(f"[{i}]: {url}")
md_parts.append("\n".join(refs_lines) + "\n")

markdown_out = "\n".join(md_parts).strip()

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
ul{padding-left:22px}
code,pre{background:#f6f8fa}
footer{margin-top:24px;font-size:12px;color:#666}
</style>
<body>
<main>
{CONTENT}
</main>
<footer>
Vygenerováno automaticky. Zdrojové kanály: Google News RSS, Reddit RSS, YouTube channel RSS, RAVE.cz feed, DJ Mag HTML, RA Events.
</footer>
</body></html>"""
html_content = md_to_html(markdown_out, output_format="xhtml1")
html = html_template.replace("{CONTENT}", html_content)
with open("docs/index.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"FEEDS: {len(FEEDS)}")
print(f"Collected prev: world={len(items_prev_world)} czsk={len(items_prev_czsk)} reddit={len(reddit_prev)}")
print(f"Collected cur : world={len(items_cur_world)} czsk={len(items_cur_czsk)} reddit={len(reddit_cur)}")
print("OK: docs/index.md + docs/index.html")

# Volitelně: Google Slides webhook
WEBHOOK = os.environ.get("APPSCRIPT_WEBHOOK_URL", "").strip()
PRESENTATION_ID = os.environ.get("GOOGLE_SLIDES_PRESENTATION_ID", "").strip()
if WEBHOOK and PRESENTATION_ID:
    payload = {
        "date": TODAY.strftime("%Y-%m-%d"),
        "period_prev": PER_PREV,
        "period_cur": PER_CUR,
        "sections": {
            "world_prev": [format_item(it) for it in world_prev] or ["* Žádné zásadní novinky."],
            "world_cur":  [format_item(it) for it in world_cur]  or ["* Žádné zásadní novinky."],
            "cz_prev":    [format_item(it) for it in cz_prev]    or ["* Žádné zásadní novinky."],
            "cz_cur":     [format_item(it) for it in cz_cur]     or ["* Žádné zásadní novinky."],
            "reddit_prev":[f"* {clean_text((it['title'] or '') + '. ' + (it['summary'] or ''),260)}" for it in rd_prev] or ["* Žádné zásadní novinky."],
            "reddit_cur": [f"* {clean_text((it['title'] or '') + '. ' + (it['summary'] or ''),260)}" for it in rd_cur] or ["* Žádné zásadní novinky."],
            "curiosity_prev": [build_curio(PER_PREV, cur_prev).split('\n', 2)[2] if cur_prev else "* Žádné zásadní novinky."],
            "curiosity_cur":  [build_curio(PER_CUR,  cur_cur ).split('\n', 2)[2] if cur_cur  else "* Žádné zásadní novinky."],
        },
        "sources": [f"[{i}]: {u}" for i, (_, u) in enumerate(all_refs, start=1)],
        "presentationId": PRESENTATION_ID
    }
    try:
        r = requests.post(WEBHOOK, json=payload, timeout=25)
        print("AppsScript:", r.status_code, r.text[:200])
    except Exception as ex:
        print("AppsScript error:", ex, file=sys.stderr)
