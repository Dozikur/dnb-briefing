#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# DnB NOVINKY – aggregator.py
# - Generuje briefing za MINULÝ týden (Po–Ne) v češtině
# - Zdroje: Google News RSS (site: + DnB dotazy) pro vybrané weby, Rave.cz RSS, Reddit RSS, YouTube channel RSS, DogsOnAcid forum RSS (s žánrovým filtrem)
# - Eventy: výhradně z DnBHeard (JSON-LD), řízeno env DNBHEARD_URLS="https://...,https://..."
# - Výstup: docs/index.md + docs/index.html
# - Persist: data/events_seen.json pro sekci „Nově oznámené“

import os, re, sys, json, hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
import requests
import feedparser
from dateutil.parser import parse as dtparse
import pytz
from bs4 import BeautifulSoup as BS
from html import unescape
from markdown import markdown as md_to_html

# ============================== ČAS / OBDOBÍ ================================

TZ = pytz.timezone("Europe/Prague")
TODAY = datetime.now(TZ).date()

def week_bounds(d):
    mon = d - timedelta(days=d.weekday())      # pondělí
    sun = mon + timedelta(days=6)              # neděle
    return mon, sun

# Pouze minulý týden
PREV_MON, PREV_SUN = week_bounds(TODAY - timedelta(days=7))
PERIOD_PREV = f"{PREV_MON.strftime('%-d.')}\u2009–\u2009{PREV_SUN.strftime('%-d. %m. %Y')}"

def within(date_dt, start_date, end_date):
    if not isinstance(date_dt, datetime):
        return False
    d = date_dt.astimezone(TZ).date()
    return start_date <= d <= end_date

# =============================== POMOCNÉ ====================================

def clean_text(s, limit=400):
    if not s: return ""
    s = unescape(BS(s, "html.parser").get_text(" ", strip=True))
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > limit:
        s = s[:limit].rstrip()
    return s

def get_best_date(entry):
    for k in ("published", "updated", "created"):
        if k in entry and entry[k]:
            try:
                return dtparse(entry[k]).astimezone(TZ)
            except Exception:
                pass
    for k in ("published_parsed", "updated_parsed"):
        if k in entry and entry[k]:
            try:
                return datetime(*entry[k][:6], tzinfo=timezone.utc).astimezone(TZ)
            except Exception:
                pass
    return None

def fetch(url, headers=None, timeout=20):
    h = {"User-Agent":"Mozilla/5.0 (DnBBriefing; +github-actions)"}
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
        qs = {k:v for k,v in qs.items() if not k.lower().startswith("utm_")}
        base = f"{p.scheme}://{p.netloc}{p.path}"
        if qs:
            q = "&".join(f"{k}={quote_plus(v[0])}" for k,v in qs.items() if v)
            return f"{base}?{q}"
        return base
    except Exception:
        return u

# ============================ RSS / DOTAZY ==================================

def google_news_feed(site, when_days=14):
    # International weby → en/US, CZ/SK domény → cs/CZ
    if site.endswith(".cz") or site.endswith(".sk") or site in ("rave.cz","musicserver.cz"):
        hl, gl, ceid = "cs", "CZ", "CZ:cs"
    else:
        hl, gl, ceid = "en", "US", "US:en"
    terms = '("drum and bass" OR "drum & bass" OR dnb OR jungle)'
    query = f"site:{site} {terms} when:{when_days}d"
    base = "https://news.google.com/rss/search?q="
    tail = f"&hl={hl}&gl={gl}&ceid={ceid}"
    return base + quote_plus(query) + tail

def reddit_rss(sub):
    return f"https://old.reddit.com/r/{sub}/.rss"

def youtube_channel_id_from_handle(handle):
    if handle.startswith("http"):
        url = handle
    else:
        h = handle.lstrip('@')
        url = f"https://www.youtube.com/@{h}"
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

# ============================= ZDROJE / HEURISTIKY ==========================

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

SECONDARY_SITES = [
    ("EDM.com", "edm.com"),
    ("Dancing Astronaut", "dancingastronaut.com"),
    ("Rolling Stone Australia", "rollingstone.com.au"),
    ("Billboard", "billboard.com"),
]

REDDITS = [("r/DnB","DnB"), ("r/LetItRollFestival","LetItRollFestival")]
YOUTUBES = ["@Liquicity", "@dnballstars", "@WeAreRampageEvents", "@UKFDrumandBass"]

POS = [
    "drum and bass","drum’n’bass","drum n bass","dnb","dn'b","jungle",
    "neurofunk","liquid","jump up","roller","rollers","ukf","hospital records",
    "let it roll","ram records","blackout music","shogun audio",
]
NEG = [
    "techno","tech house","house","trance","edm pop","electro house",
    "hardstyle","psytrance","deep house","progressive house",
]
HEADERS = {"User-Agent": "DnB-Novinky/1.0 (+github-actions)"}

# BYPASS_POS: domény, kde DnB je nativní obsah → stačí neobsahovat NEG
# FORCE_POS: domény, kde chceme DnB klíčová slova povinně
BYPASS_POS = (
    "mixmag.net","ra.co","ukf.com","djmag.com",
    "edm.com","dancingastronaut.com","rollingstone.com.au","billboard.com",
    "youtube.com","youtu.be"
)
FORCE_POS = ("rave.cz","musicserver.cz")

MIN_WORLD = 5
MIN_CZSK  = 2
MIN_REDDIT= 2

def is_dnb_related(title: str, summary: str, url: str) -> bool:
    t = f"{title} {summary}".lower()
    host = urlparse(url).netloc.lower()
    if any(host.endswith(d) for d in FORCE_POS):
        return any(p in t for p in POS) and not any(n in t for n in NEG)
    if any(host.endswith(d) for d in BYPASS_POS):
        return not any(n in t for n in NEG)
    return any(p in t for p in POS) and not any(n in t for n in NEG)

def is_czsk_link(link: str) -> bool:
    host = re.sub(r"^www\.", "", (re.findall(r"https?://([^/]+)", link) or [""])[0])
    tld = host.split(".")[-1] if host else ""
    return bool(tld in ("cz","sk") or "rave.cz" in host or "musicserver.cz" in host)

# ============================ FEED SEZNAM ===================================

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

for label, sub in READDITS := REDDITS if False else REDDITS:
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

# ============================= ZPRACOVÁNÍ RSS ===============================

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
    text = base
    if it["summary"] and it["summary"][:len(base)].lower() != base.lower():
        text = f"{base} — {it['summary']}"
    sents = re.split(r"(?<=[.!?])\s+", text)
    if len(sents) >= 2:
        text = " ".join(sents[:2])
    return text

def uniq_key(it):
    raw = (it.get("title") or "") + (it.get("link") or "")
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]

def _sort_key_dt(it):
    dtv = it.get("date")
    return dtv if isinstance(dtv, datetime) else datetime(1900, 1, 1, tzinfo=TZ)

def dedupe(items, maxn=None):
    seen, out = set(), []
    for it in sorted(items or [], key=_sort_key_dt, reverse=True):
        k = uniq_key(it)
        if k in seen: 
            continue
        seen.add(k); out.append(it)
        if maxn and len(out) >= maxn:
            break
    return out

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
        # pouze MINULÝ TÝDEN
        if not within(it["date"], PREV_MON, PREV_SUN):
            continue
        if f["section"] == "reddit":
            reddit_prev.append(it)
            continue
        # CZ/SK vs svět
        if f["section"] == "czsk" or is_czsk_link(it["link"]):
            if is_dnb_related(it["title"], it["summary"], it["link"]):
                items_prev_czsk.append(it)
        else:
            if is_dnb_related(it["title"], it["summary"], it["link"]):
                items_prev_world.append(it)

# Fallback sekundární zdroje, když „Svět“ nedá min. 5
def harvest_sites(sites, start_date, end_date):
    out = []
    for label, domain in sites:
        feed_url = google_news_feed(domain, when_days=14)
        feed = fetch_feed(feed_url)
        if not feed or not feed.entries:
            continue
        for e in feed.entries:
            it = entry_to_item(e, label)
            if not it["date"] or not within(it["date"], start_date, end_date):
                continue
            if is_dnb_related(it["title"], it["summary"], it["link"]):
                out.append(it)
    return out

if len(items_prev_world) < MIN_WORLD:
    extra_prev = harvest_sites(SECONDARY_SITES, PREV_MON, PREV_SUN)
    need = MIN_WORLD - len(items_prev_world)
    if need > 0:
        extra_prev = dedupe(extra_prev, maxn=20)
        seen = {uniq_key(x) for x in items_prev_world}
        for it in extra_prev:
            k = uniq_key(it)
            if k in seen: 
                continue
            seen.add(k)
            items_prev_world.append(it)
            if len(items_prev_world) >= MIN_WORLD:
                break

# Deduplikace finální
items_prev_world = dedupe(items_prev_world, maxn=20)
items_prev_czsk  = dedupe(items_prev_czsk,  maxn=20)
reddit_prev      = dedupe(reddit_prev,      maxn=20)

# ============================== EVENTY (DnBHeard only) ======================

# Bezpečné vytvoření složky data/ (pokud je 'data' soubor, smaž ho)
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

BRANDS = [
    "hospitality","rampage","liquicity","dnb allstars","darkshire","beats for love",
    "hoofbeats","let it roll","roxy","epic","cross club","fuchs2","trojhalí",
    "monastery","church","gabriel loci","výstaviště","o2 arena","brněnské výstaviště"
]
INTL_HEADLINERS = [
    "hybrid minds","dimension","bou","sub focus","pendulum","friction","camo & krooked",
    "mefjus","noisia","phace","imanu","charlie tee","alix perez","skeptical","merikan",
    "venjent","netsky","dossa & locuzzed","grafix","etherwood","fred v","k motionz",
    "culture shock","bcee","calibre","break","spectra soul","high contrast","s.p.y","spy",
    "wilkinson","bru-c","a little sound","andromedik","kanine"
]
ANNOUNCE_HINTS = ["announce","announced","oznámen","oznamuje","line-up","lineup","přidán","added to the bill"]

CZSK_LOC_TOKENS = [
    "praha","prague","brno","ostrava","plzeň","olomouc","hradec králové",
    "pardubice","liberec","zlín","ústí nad labem","bratislava","košice",
    "nitra","žilina","banská bystrica","trnava","trenčín","prešov",".cz",".sk",
    "czech","česko","slovakia","slovensko","výstaviště","trojhalí","gabriel loci","sacre coeur",
]

def is_event_czsk(ev: dict) -> bool:
    blob = f"{ev.get('title','')} {ev.get('summary','')} {ev.get('link','')}".lower()
    return any(tok in blob for tok in CZSK_LOC_TOKENS)

def remember_seen(url: str):
    if url and url not in EVENTS_SEEN:
        EVENTS_SEEN[url] = TODAY.isoformat()

def priority_bucket(title: str) -> str:
    t = (title or "").lower()
    if any(b in t for b in BRANDS) or any(a in t for a in INTL_HEADLINERS):
        return "TOP"
    if any(k in t for k in ["festival","live","tour","b2b","special guest","headliner"]):
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
            if not isinstance(n, dict): continue
            if n.get("@type") not in ("Event","MusicEvent"): continue
            name = clean_text(n.get("name") or "")
            url  = normalize_url(n.get("url") or "")
            if not name or not url: continue
            start = n.get("startDate") or n.get("start_date")
            start_dt = None
            try:
                if start: start_dt = dtparse(start).astimezone(TZ)
            except Exception:
                start_dt = None
            loc = ""
            locn = n.get("location")
            if isinstance(locn, dict):
                loc = clean_text(locn.get("name") or "")
            elif isinstance(locn, list) and locn and isinstance(locn[0], dict):
                loc = clean_text(locn[0].get("name") or "")
            out.append({
                "title": name,
                "summary": loc,
                "link": url,
                "date": start_dt,
                "source": base_label
            })
    return out

def scrape_dnbeheard() -> list:
    """
    DnBHeard zdroje definuj v env DNBHEARD_URLS jako CSV (např. https://dnbeheard.com/cz,https://dnbeheard.com/sk).
    """
    urls_env = os.environ.get("DNBHEARD_URLS", "").strip()
    if not urls_env:
        return []
    urls = [u.strip() for u in urls_env.split(",") if u.strip()]
    out=[]
    for u in urls:
        try:
            html = fetch(u, timeout=25).text
        except Exception:
            continue
        out.extend(parse_jsonld_events(html, "DnBHeard"))
    # filtrování DnB + CZ/SK + priorita (LOW pryč)
    ev = []
    for it in out:
        if not is_event_czsk(it): 
            continue
        if priority_bucket(it["title"]) == "LOW":
            continue
        ev.append(it)
    return dedupe(ev, maxn=200)

def classify_events(evts: list):
    """Rozděl DnBHeard eventy: recap minulý týden, tento týden, nově oznámené."""
    recap, thisweek, announced = [], [], []
    cur_mon, cur_sun = week_bounds(TODAY)
    for it in (evts or []):
        d = it.get("date")
        url = it.get("link","")
        ttl = (it.get("title") or "").lower()

        if isinstance(d, datetime):
            if within(d, PREV_MON, PREV_SUN):
                recap.append(it); remember_seen(url); 
                continue
            if within(d, cur_mon, cur_sun):
                thisweek.append(it); remember_seen(url); 
                continue

        remember_seen(url)
        try:
            first_seen = datetime.fromisoformat(EVENTS_SEEN.get(url, TODAY.isoformat())).date()
        except Exception:
            first_seen = TODAY
        if (TODAY - first_seen).days <= 7 and any(h in ttl for h in ANNOUNCE_HINTS):
            announced.append(it)

    persist_events_seen()
    return (dedupe(recap, 12), dedupe(thisweek, 12), dedupe(announced, 12))

# ============================== VÝSTUP ======================================

def format_news_item(it):
    dstr = it["date"].strftime("%-d. %-m. %Y")
    txt = summarize_item(it)
    ref_idx = add_ref(it["link"], it["source"])
    return f"* {txt} ({dstr}) ([{it['source']}][{ref_idx}])"

def build_section_news(header, period, items, min_needed):
    if len(items) < min_needed:
        return f"## {header} ({period})\n\n* Žádné zásadní novinky.\n"
    lines = [f"## {header} ({period})\n"]
    for it in items:
        lines.append(format_news_item(it))
    return "\n".join(lines) + "\n"

def build_reddit_section(period, lst, min_needed=MIN_REDDIT):
    if len(lst) < min_needed:
        return f"## Reddit vlákna ({period})\n\n* Žádné zásadní novinky.\n"
    lines = [f"## Reddit vlákna ({period})\n"]
    for it in lst:
        dstr = it["date"].strftime("%-d. %-m. %Y")
        title = (it["title"] or "")
        title = re.sub(r"\s*submitted by.*$", "", title, flags=re.I)
        brief = clean_text(f"{title}. {it.get('summary','')}", 260)
        idx = add_ref(it["link"], it["source"])
        lines.append(f"* {brief} ({dstr}) ([{it['source']}][{idx}])")
    return "\n".join(lines) + "\n"

def pick_curiosity(cands):
    KEYS = ["AI","uměl","study","rekord","unikátní","rare","prototype","leak","patent","CDJ","controller","hardware"]
    for it in cands:
        blob = (it["title"]+" "+it["summary"]).lower()
        if any(k.lower() in blob for k in KEYS):
            return it
    return cands[0] if cands else None

def build_curio(period, it):
    if not it:
        return f"## Kuriozita ({period})\n\n* Žádné zásadní novinky.\n"
    dstr = it["date"].strftime("%-d. %-m. %Y")
    idx = add_ref(it["link"], it["source"])
    return f"## Kuriozita ({period})\n\n* {summarize_item(it)} ({dstr}) ([{it['source']}][{idx}])\n"

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
    # Recap minulý týden
    parts.append("### Recap minulý týden\n")
    if recap:
        for it in recap: parts.append(format_event_item(it))
    else:
        parts.append("* Žádné relevantní novinky tento týden.")
    # Tento týden
    parts.append("\n### Tento týden\n")
    if thisweek:
        for it in thisweek: parts.append(format_event_item(it))
    else:
        parts.append("* Žádné relevantní novinky tento týden.")
    # Nově oznámené
    parts.append("\n### Nově oznámené\n")
    dup = {uniq_key(x) for x in (recap + thisweek)}
    announced = [x for x in announced if uniq_key(x) not in dup]
    if announced:
        for it in announced: parts.append(format_event_item(it))
    else:
        parts.append("* Žádné relevantní novinky tento týden.")
    parts.append("")
    return "\n".join(parts)

# ============================== GENERACE ====================================

world_prev = items_prev_world[:MIN_WORLD] if len(items_prev_world) >= MIN_WORLD else items_prev_world
cz_prev    = items_prev_czsk[:MIN_CZSK]   if len(items_prev_czsk)   >= MIN_CZSK   else items_prev_czsk
# Víc vláken z Redditu (cíluj 4, ale respektuj minimum)
rd_prev    = reddit_prev[:max(MIN_REDDIT, 4)] if len(reddit_prev) >= MIN_REDDIT else reddit_prev

cur_prev = pick_curiosity(items_prev_world) or pick_curiosity(items_prev_czsk)

md_parts = []
md_parts.append(f"# DnB NOVINKY – {TODAY.strftime('%-d. %-m. %Y')}\n")
md_parts.append(build_section_news("Svět", PERIOD_PREV, world_prev, MIN_WORLD))
md_parts.append(build_section_news("ČR / SK", PERIOD_PREV, cz_prev, MIN_CZSK))
md_parts.append(build_reddit_section(PERIOD_PREV, rd_prev))
md_parts.append(build_curio(PERIOD_PREV, cur_prev))

events_all = scrape_dnbeheard()
md_parts.append(build_events_block(events_all))

refs_lines = ["\n## Zdroje\n"]
for i,(label,url) in enumerate(all_refs, start=1):
    refs_lines.append(f"[{i}]: {url}")
md_parts.append("\n".join(refs_lines) + "\n")

markdown_out = "\n".join(md_parts).strip()

# =============================== ULOŽENÍ ====================================

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
h3{font-size:16px;margin:16px 0 6px}
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
