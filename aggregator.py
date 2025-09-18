#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, sys, json, time, hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
import requests
import feedparser
from dateutil.parser import parse as dtparse
import pytz
from bs4 import BeautifulSoup as BS
from html import unescape
from markdown import markdown as md_to_html

# ============================== ČAS / OBDOBÍ ===============================

TZ = pytz.timezone("Europe/Prague")
TODAY = datetime.now(TZ).date()

def week_bounds(d: datetime.date):
    mon = d - timedelta(days=d.weekday())
    sun = mon + timedelta(days=6)
    return mon, sun

# Minulý týden = pondělí–neděle bezprostředně před dneškem
PREV_MON, PREV_SUN = week_bounds(TODAY - timedelta(days=7))

def within(date_dt: datetime, start_date, end_date) -> bool:
    if not isinstance(date_dt, datetime):
        return False
    d = date_dt.astimezone(TZ).date()
    return start_date <= d <= end_date

# ============================== UTIL FUNKCE ================================

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
    h = {"User-Agent":"Mozilla/5.0 (DnB-briefing GitHubActions)"}
    if headers: h.update(headers)
    r = requests.get(url, headers=h, timeout=timeout)
    r.raise_for_status()
    return r

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

# ============================== NEWS FEEDY =================================
# Primárně RSS přes Google News, filtr žánru až lokálně

def google_news_feed(site, when_days=14, lang="cs", region="CZ"):
    # víc výsledků z en pro svět, cs pro CZ/SK domény
    if site.endswith(".cz") or site.endswith(".sk") or site in ("rave.cz","musicserver.cz"):
        hl, gl, ceid = "cs", "CZ", "CZ:cs"
    else:
        hl, gl, ceid = "en-US", "US", "US:en"
    query = f"site:{site} when:{when_days}d"
    base = "https://news.google.com/rss/search?q="
    tail = f"&hl={hl}&gl={gl}&ceid={ceid}"
    return base + quote_plus(query) + tail

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
YOUTUBES = ["@Liquicity", "@dnballstars", "@WeAreRampageEvents"]

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
HEADERS = {"User-Agent": "DnB-Novinky/1.0 (+github actions)"}
ALLOWLIST = ("mixmag.net","ra.co","ukf.com","djmag.com","edm.com","dancingastronaut.com",
             "rollingstone.com.au","billboard.com","youtube.com","youtu.be",
             "rave.cz","musicserver.cz","dogsonacid.com")

MIN_WORLD = 5
MIN_CZSK  = 2
MIN_REDDIT= 2

def is_dnb_related(title: str, summary: str, url: str) -> bool:
    t = f"{title} {summary}".lower()
    host = urlparse(url).netloc.lower()
    if any(host.endswith(d) for d in ALLOWLIST):
        return True
    return any(p in t for p in POS) and not any(n in t for n in NEG)

def is_czsk_dnb(title: str, summary: str) -> bool:
    t = f"{title} {summary}".lower()
    return any(x in t for x in CZSK_TOKENS) and not any(n in t for n in NEG)

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

# Build feed list
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
    u = youtube_rss_from_handle(handle)
    if u:
        FEEDS.append({
            "name": f"YouTube:{handle}",
            "kind": "rss",
            "section": "world",
            "url": u,
            "source_label": f"YouTube {handle}"
        })
FEEDS.append({
    "name":"DogsOnAcidForum",
    "kind":"rss",
    "section":"world",
    "url": xenforo_forum_index_rss("https://www.dogsonacid.com"),
    "source_label":"DogsOnAcid Forum"
})

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
    raw = (it.get("title") or "") + (it.get("link") or "")
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]

# Collect
items_prev_world, items_prev_czsk = [], []
reddit_prev = []
all_refs, ref_map = [], {}

def add_ref(url, label):
    if url in ref_map: return ref_map[url]
    idx = len(all_refs) + 1
    ref_map[url] = idx
    all_refs.append((label, url))
    return idx

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
            (items_prev_czsk if sec=="czsk" else items_prev_world).append(it)

# Fallback sekundárních webů pro svět, pokud je málo
def harvest_sites(sites, start_date, end_date):
    out=[]
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

if len(items_prev_world) < MIN_WORLD:
    extra = harvest_sites(SECONDARY_SITES, PREV_MON, PREV_SUN)
    items_prev_world = dedupe(items_prev_world + extra, maxn=20)

items_prev_world = dedupe(items_prev_world, maxn=20)
items_prev_czsk  = dedupe(items_prev_czsk,  maxn=10)
reddit_prev      = dedupe(reddit_prev,      maxn=8)

# ============================== DNBHEARD EVENTY ============================

# „databáze“ již viděných eventů kvůli „Nově oznámené“
if os.path.exists("data") and not os.path.isdir("data"):
    try: os.remove("data")
    except Exception: pass
os.makedirs("data", exist_ok=True)

EVENTS_SEEN_PATH = os.path.join("data", "events_seen.json")
try:
    with open(EVENTS_SEEN_PATH, "r", encoding="utf-8") as f:
        EVENTS_SEEN = json.load(f)
except Exception:
    EVENTS_SEEN = {}

def persist_events_seen():
    try:
        with open(EVENTS_SEEN_PATH, "w", encoding="utf-8") as f:
            json.dump(EVENTS_SEEN, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# Prioritizace
BRANDS = [
    "hospitality","rampage","liquicity","dnb allstars","darkshire","beats for love",
    "hoofbeats","let it roll","korsakov","roxy","epic","cross club","fuchs2",
    "trojhalí","monastery","church","gabriel loci","výstaviště","o2 arena"
]
INTL_HEADLINERS = [
    "hybrid minds","dimension","bou","sub focus","pendulum","friction","camo & krooked",
    "mefjus","noisia","phace","imanu","alix perez","skeptical","merikan","venjent",
    "netsky","dossa & locuzzed","grafix","etherwood","fred v","k motionz","culture shock",
    "calibre","break","spectrasoul","high contrast","s.p.y","wilkinson","bru-c",
    "a little sound","andromedik","kanine","charlie tee","benny l","gladde paling"
]

CZSK_LOC_TOKENS = [
    "praha","prague","brno","ostrava","plzeň","olomouc","hradec králové","pardubice",
    "liberec","zlín","ústí nad labem","bratislava","košice","nitra","žilina",
    "banská bystrica","trnava","trenčín","prešov",".cz",".sk","česko","slovensko"
]

def is_event_czsk(ev: dict) -> bool:
    blob = f"{ev.get('title','')} {ev.get('summary','')} {ev.get('link','')}".lower()
    if any(tok in blob for tok in CZSK_LOC_TOKENS):
        return True
    meta = ev.get("_meta") or {}
    country = (meta.get("countryCode") or meta.get("addressCountry") or "").upper()
    return country in ("CZ","CZE","SK","SVK")

def priority_bucket(title: str) -> str:
    t = (title or "").lower()
    if any(b in t for b in BRANDS) or any(a in t for a in INTL_HEADLINERS):
        return "TOP"
    if any(k in t for k in ["festival","b2b","special guest","headliner","international","tour"]):
        return "MID"
    return "LOW"

def parse_jsonld_events(html: str, base_label: str) -> list:
    out=[]
    soup = BS(html, "html.parser")
    for tag in soup.find_all("script", attrs={"type":"application/ld+json"}):
        try:
            node = json.loads(tag.string.strip()) if tag.string else None
        except Exception:
            node = None
        if not node: 
            continue
        nodes = node if isinstance(node, list) else node.get("@graph") if isinstance(node, dict) and "@graph" in node else [node]
        if not isinstance(nodes, list):
            nodes = [nodes]
        for n in nodes:
            if not isinstance(n, dict): 
                continue
            if n.get("@type") not in ("Event","MusicEvent"): 
                continue
            name = clean_text(n.get("name") or "")
            url  = normalize_url(n.get("url") or "")
            if not name or not url: 
                continue
            start = n.get("startDate") or n.get("start_date")
            start_dt = None
            try:
                if start: start_dt = dtparse(start).astimezone(TZ)
            except Exception:
                start_dt = None
            loc_txt, country = "", ""
            locn = n.get("location")
            if isinstance(locn, dict):
                loc_txt = clean_text(locn.get("name") or "")
                addr = locn.get("address") or {}
                if isinstance(addr, dict):
                    country = (addr.get("addressCountry") or "").upper()
            elif isinstance(locn, list) and locn and isinstance(locn[0], dict):
                loc_txt = clean_text(locn[0].get("name") or "")
                addr = locn[0].get("address") or {}
                if isinstance(addr, dict):
                    country = (addr.get("addressCountry") or "").upper()
            out.append({
                "title": name,
                "summary": loc_txt,
                "link": url,
                "date": start_dt,
                "source": base_label,
                "_meta": {"countryCode": country}
            })
    return out

def parse_dom_events(html: str, base_url: str) -> list:
    out=[]
    soup = BS(html, "html.parser")
    # univerzální heuristika pro karty na dnbeheard.cz/kalendar-akci/
    # hledej odkazy na detail akce + <time>
    cards = soup.select("article a, div a")
    seen = set()
    for a in cards:
        href = a.get("href")
        if not href: 
            continue
        url = normalize_url(href)
        if "dnbeheard" not in urlparse(url).netloc:
            continue
        ttl = clean_text(a.get_text(" ", strip=True))
        if not ttl or len(ttl) < 3:
            continue
        # najdi čas poblíž
        parent = a
        time_dt = None
        for _ in range(3):
            parent = parent.parent
            if not parent: break
            t = parent.find("time")
            if t and (t.get("datetime") or t.get("data-datetime")):
                try:
                    time_dt = dtparse(t.get("datetime") or t.get("data-datetime")).astimezone(TZ)
                except Exception:
                    time_dt = None
                break
        # místo
        loc = ""
        if parent:
            loc_el = parent.find(attrs={"class": re.compile(r"(míst|venue|location|place|city)", re.I)}) or parent.find("small")
            if loc_el:
                loc = clean_text(loc_el.get_text(" ", strip=True))
        key = (ttl, url)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "title": ttl, "summary": loc, "link": url, "date": time_dt, "source": "DnBHeard", "_meta": {}
        })
    return out

def scrape_dnbeheard_cz() -> list:
    url = "https://dnbeheard.cz/kalendar-akci/"
    try:
        html = fetch(url, timeout=25).text
    except Exception:
        return []
    ev = parse_jsonld_events(html, "DnBHeard")
    if not ev:
        ev = parse_dom_events(html, url)
    # CZ/SK + TOP/MID
    out=[]
    for it in ev:
        if not is_event_czsk(it): 
            continue
        prio = priority_bucket(it.get("title",""))
        if prio == "LOW":
            continue
        out.append(it)
    # řazení podle data, TBA dozadu
    def _k(x):
        return x["date"] if isinstance(x.get("date"), datetime) else datetime(1900,1,1,tzinfo=TZ)
    out = sorted(out, key=_k, reverse=True)
    return dedupe(out, maxn=200)

def classify_events(evts: list):
    """Recap = v intervalu PREV_MON..PREV_SUN
       Tento týden = nevyužito teď (reportujeme jen minulý týden), ale nechávám pro konzistenci
       Nově oznámené = první výskyt do 7 dnů zpět.
    """
    recap, thisweek, announced = [], [], []
    for it in (evts or []):
        d = it.get("date")
        url = it.get("link","")
        if isinstance(d, datetime) and within(d, PREV_MON, PREV_SUN):
            recap.append(it)
            if url and url not in EVENTS_SEEN: EVENTS_SEEN[url] = TODAY.isoformat()
            continue
        if url and url not in EVENTS_SEEN:
            EVENTS_SEEN[url] = TODAY.isoformat()
        try:
            first_seen = datetime.fromisoformat(EVENTS_SEEN.get(url, TODAY.isoformat())).date()
        except Exception:
            first_seen = TODAY
        if (TODAY - first_seen).days <= 7:
            announced.append(it)
    persist_events_seen()
    # dedupe
    recap = dedupe(recap, 40)
    announced = [x for x in dedupe(announced, 40) if uniq_key(x) not in {uniq_key(y) for y in recap}]
    return recap, thisweek, announced

def format_event_item(it):
    dstr = it["date"].strftime("%-d. %-m. %Y") if isinstance(it.get("date"), datetime) else "datum TBA"
    ttl = clean_text(it.get("title",""))
    loc = clean_text(it.get("summary",""))
    idx = add_ref(it["link"], it["source"])
    inner = f"{ttl}" + (f" — {loc}" if loc else "")
    return f"* {inner} ({dstr}) ([{it['source']}][{idx}])"

def build_events_block(events_all):
    recap, thisweek, announced = classify_events(events_all)
    parts = ["## Eventy ČR / SK\n"]
    parts.append("### Recap minulý týden\n")
    if recap:
        for it in recap: parts.append(format_event_item(it))
    else:
        parts.append("* Žádné relevantní novinky tento týden.")
    parts.append("\n### Tento týden\n")
    parts.append("* Žádné relevantní novinky tento týden.")  # reportujeme jen minulý týden
    parts.append("\n### Nově oznámené\n")
    if announced:
        for it in announced: parts.append(format_event_item(it))
    else:
        parts.append("* Žádné relevantní novinky tento týden.")
    parts.append("")
    return "\n".join(parts)

# ============================== VÝSTUP =====================================

def pick(items, need):
    return items[:need] if len(items)>=need else items

def format_item(it):
    dstr = it["date"].strftime("%-d. %-m. %Y")
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
    return f"{a.strftime('%-d.')}\u2009–\u2009{b.strftime('%-d. %m. %Y')}"

PER_PREV = period_str(PREV_MON, PREV_SUN)

# Jen minulý týden
world_prev = pick(items_prev_world, MIN_WORLD)
cz_prev    = pick(items_prev_czsk,  MIN_CZSK)
rd_prev    = pick(reddit_prev,      MIN_REDDIT+1)

# Reddit sekce (minulý týden)
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

# Kuriozita z „svět“
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
    dstr = it["date"].strftime("%-d. %-m. %Y")
    idx = add_ref(it["link"], it["source"])
    return f"## Kuriozita ({period})\n\n* {summarize_item(it)} ({dstr}) ([{it['source']}][{idx}])\n"

# Eventy z DnBHeard CZ
events_all = scrape_dnbeheard_cz()

md_parts = []
md_parts.append(f"# DnB NOVINKY – {TODAY.strftime('%-d. %-m. %Y')}\n")
md_parts.append(build_section("Svět", PER_PREV, world_prev, MIN_WORLD))
md_parts.append(build_section("ČR / SK", PER_PREV, cz_prev, MIN_CZSK))
md_parts.append(build_reddit_section(PER_PREV, rd_prev))
md_parts.append(build_curio(PER_PREV, cur_prev))
md_parts.append(build_events_block(events_all))

# Zdroje
refs_lines = ["\n## Zdroje\n"]
for i,(label,url) in enumerate(all_refs, start=1):
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
Vygenerováno automaticky. Zdrojové kanály: Google News RSS, Reddit RSS, YouTube channel RSS, RAVE.cz feed, DJ Mag, DnBHeard.
</footer>
</body></html>"""
html_content = md_to_html(markdown_out, output_format="xhtml1")
html = html_template.replace("{CONTENT}", html_content)
with open("docs/index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("OK: docs/index.md + docs/index.html")
