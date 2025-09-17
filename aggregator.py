#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, sys, json, time, hashlib
from datetime import datetime, timedelta, timezone, date
from urllib.parse import urlparse, parse_qs, unquote, quote_plus
import requests
import feedparser
from dateutil.parser import parse as dtparse
import pytz
from bs4 import BeautifulSoup as BS
from html import unescape
from markdown import markdown as md_to_html

# =========================
# ČAS A OBDOBÍ
# =========================
TZ = pytz.timezone("Europe/Prague")
TODAY_DT = datetime.now(TZ)
TODAY = TODAY_DT.date()

def week_bounds(d: date):
    mon = d - timedelta(days=d.weekday())
    sun = mon + timedelta(days=6)
    return mon, sun

# jen minulý týden v hlavních sekcích
PREV_MON, PREV_SUN = week_bounds(TODAY - timedelta(days=7))
CUR_MON, CUR_SUN = week_bounds(TODAY)  # pro blok „Eventy: Tento týden“

def within(dt: datetime, a: date, b: date) -> bool:
    if not dt: return False
    d = dt.astimezone(TZ).date()
    return a <= d <= b

# =========================
# UTIL
# =========================
HEADERS = {"User-Agent": "DnB-Novinky/1.3 (+github actions)"}

def fetch(url, timeout=25, headers=None):
    h = dict(HEADERS)
    if headers: h.update(headers)
    r = requests.get(url, headers=h, timeout=timeout)
    r.raise_for_status()
    return r

def clean_text(s: str, limit=400) -> str:
    if not s: return ""
    s = unescape(BS(s, "html.parser").get_text(" ", strip=True))
    s = re.sub(r"\s+", " ", s).strip()
    if limit and len(s) > limit:
        s = s[:limit].rstrip()
    return s

def get_best_date(entry) -> datetime|None:
    for k in ("published", "updated", "created"):
        if entry.get(k):
            try: return dtparse(entry[k]).astimezone(TZ)
            except: pass
    for k in ("published_parsed", "updated_parsed"):
        if entry.get(k):
            return datetime(*entry[k][:6], tzinfo=timezone.utc).astimezone(TZ)
    return None

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
        if not p.scheme or not p.netloc: return u
        junk = ("utm_", "fbclid", "gclid")
        q = parse_qs(p.query)
        q2 = {k: v for k, v in q.items() if not any(k.lower().startswith(j) for j in junk)}
        base = f"{p.scheme}://{p.netloc}{p.path}"
        if q2:
            pairs = []
            for k, v in q2.items():
                if v: pairs.append(f"{k}={quote_plus(v[0])}")
            if pairs:
                return f"{base}?{'&'.join(pairs)}"
        return base
    except Exception:
        return u

def uniq_key_from(it: dict) -> str:
    raw = (it.get("title") or "") + (it.get("link") or "")
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]

def summarize_item(it: dict) -> str:
    base = it.get("title") or ""
    desc = it.get("summary") or ""
    if desc and not desc.lower().startswith(base.lower()):
        text = f"{base} — {desc}"
    else:
        text = base
    sents = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(sents[:2]) if sents else text

# =========================
# KONFIG
# =========================
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
    "let it roll","ram records","blackout music","shogun audio","alpha theta","cdj",
]
NEG = [
    "techno","tech house","house","trance","edm pop","electro house",
    "hardstyle","psytrance","deep house","progressive house"
]
CZSK_TOKENS = ["dnb","drum and bass","drum’n’bass","drum n bass","neuro","liquid","jump up","let it roll"]
ALLOWLIST = (
    "mixmag.net","ra.co","ukf.com","djmag.com","edm.com","dancingastronaut.com",
    "rollingstone.com.au","billboard.com","youtube.com","youtu.be","rave.cz","musicserver.cz","dogsonacid.com"
)

# Eventy – značky a zahraniční jména pro TOP/MID
BIG_BRANDS = [
    "hospitality","rampage","liquicity","dnb allstars","darkshire","beats for love",
    "hoofbeats","korsakov"
]
INTL_HEADLINERS = [
    "dimension","hybrid minds","bou","imanu","subfocus","and y c","andy c","noisia",
    "netksy","netsky","camo & krooked","calibre","k-motionz","skepsis","bensley","ace aura",
    "venjent","akel","tc","wilkinson","monrroe","polaris","etherwood","alix perez",
    "black sun empire","phace","misanthrop","matrix & futurebound","sub zero","dillinja","break"
]
ANNOUNCE_HINTS = ["announce", "announced", "oznámen", "line-up", "lineup", "přidáv", "added to the bill"]

MIN_WORLD = 5
MIN_CZSK  = 2
MIN_REDDIT= 2

# =========================
# RSS / FEED BUILDER
# =========================
def google_news_feed(site: str, when_days=14):
    # EN feed pro svět, CS pro CZ/SK domény
    if site.endswith(".cz") or site.endswith(".sk") or site in ("rave.cz","musicserver.cz"):
        hl, gl, ceid = "cs", "CZ", "CZ:cs"
    else:
        hl, gl, ceid = "en-US", "US", "US:en"
    q = f"site:{site} when:{when_days}d"
    return f"https://news.google.com/rss/search?q={quote_plus(q)}&hl={hl}&gl={gl}&ceid={ceid}"

def reddit_rss(sub: str) -> str:
    return f"https://old.reddit.com/r/{sub}/.rss"

def youtube_channel_id_from_handle(handle: str) -> str|None:
    url = handle if handle.startswith("http") else ("https://www.youtube.com/@" + handle.lstrip("@"))
    try:
        html = fetch(url).text
        m = re.search(r'"channelId"\s*:\s*"([A-Za-z0-9_-]{20,})"', html)
        return m.group(1) if m else None
    except Exception:
        return None

def youtube_rss_from_handle(handle: str) -> str|None:
    cid = youtube_channel_id_from_handle(handle)
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}" if cid else None

def xenforo_forum_index_rss(base: str) -> str:
    return base.rstrip("/") + "/forums/index.rss"

# =========================
# REDDIT FILTR
# =========================
SELF_PROMO_BAD = [
    "first dnb song","my new track","check out my","self promo","self-promo",
    "mixcloud","soundcloud","spotify","my mix","mashup","id this track","track id","promo"
]
RELEVANT_GOOD = [
    "album","ep","lp","release","set","festival","line-up","lineup","alpha theta","cdj","allstars","liquicity","hospitality","rampage"
]

def reddit_is_signal(title: str, summary: str) -> bool:
    t = f"{title} {summary}".lower()
    if any(bad in t for bad in SELF_PROMO_BAD):
        return False
    # slušně přísný: musí být nějaké klíčové slovo
    return any(g in t for g in RELEVANT_GOOD) or any(p in t for p in POS)

# =========================
# FEEDS DEFINICE
# =========================
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

# =========================
# FETCH FEED ITEMS
# =========================
def classify_section(link: str) -> str:
    host = re.sub(r"^www\.", "", (re.findall(r"https?://([^/]+)", link) or [""])[0])
    tld = host.split(".")[-1] if host else ""
    if tld in ("cz","sk") or "rave.cz" in host or "musicserver.cz" in host:
        return "czsk"
    return "world"

def entry_to_item(entry, source_label: str) -> dict:
    raw = entry.get("link") or ""
    link = normalize_url(resolve_news_url(raw))
    title = clean_text(entry.get("title") or "")
    desc = clean_text(entry.get("summary") or entry.get("description") or "")
    dt  = get_best_date(entry)
    return {"title": title, "summary": desc, "link": link, "date": dt, "source": source_label}

def feed_parse(url: str):
    try:
        resp = fetch(url)
        return feedparser.parse(resp.text)
    except Exception:
        try:
            return feedparser.parse(url)
        except Exception:
            return None

items_world_prev, items_cz_prev = [], []
reddit_prev = []
refs, ref_map = [], {}

def add_ref(url: str, label: str) -> int:
    if url in ref_map: return ref_map[url]
    idx = len(refs) + 1
    ref_map[url] = idx
    refs.append((label, url))
    return idx

for f in FEEDS:
    fp = feed_parse(f["url"])
    if not fp or not fp.entries: 
        continue
    for e in fp.entries:
        it = entry_to_item(e, f["source_label"])
        if not it["date"]: 
            continue
        # jen MINULÝ týden do hlavních sekcí
        if not within(it["date"], PREV_MON, PREV_SUN):
            continue

        if f["section"] == "reddit":
            if reddit_is_signal(it["title"], it["summary"]):
                reddit_prev.append(it)
            continue

        sec = classify_section(it["link"])
        # žánrové filtrování
        txt = f"{it['title']} {it['summary']}".lower()
        is_dnb = (any(p in txt for p in POS) and not any(n in txt for n in NEG)) or any(urlparse(it["link"]).netloc.endswith(d) for d in ALLOWLIST)
        if not is_dnb:
            continue

        if sec == "czsk":
            if not any(x in txt for x in CZSK_TOKENS): 
                continue
            items_cz_prev.append(it)
        else:
            items_world_prev.append(it)

def _sort_key_dt(it):
    dt = it.get("date")
    if isinstance(dt, datetime):
        return dt
    # fallback pro položky bez data
    return datetime(1900, 1, 1, tzinfo=TZ)

def dedupe(items, maxn=None):
    seen, out = set(), []
    for it in sorted(items or [], key=_sort_key_dt, reverse=True):
        k = uniq_key_from(it)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
        if maxn and len(out) >= maxn:
            break
    return out


items_world_prev = dedupe(items_world_prev, 20)
items_cz_prev    = dedupe(items_cz_prev, 10)
reddit_prev      = dedupe(reddit_prev, 8)

# doplnění svět MIN_WORLD ze SECONDARY_SITES pokud je málo
def harvest_secondary_for_period(sites, a: date, b: date):
    out=[]
    for label, domain in sites:
        u = google_news_feed(domain, when_days=14)
        fp = feed_parse(u)
        if not fp or not fp.entries: continue
        for e in fp.entries:
            it = entry_to_item(e, label)
            if not it["date"]: continue
            if not within(it["date"], a, b): continue
            txt = f"{it['title']} {it['summary']}".lower()
            if not (any(p in txt for p in POS) and not any(n in txt for n in NEG)):
                continue
            out.append(it)
    return dedupe(out, 20)

if len(items_world_prev) < MIN_WORLD:
    extra = harvest_secondary_for_period(SECONDARY_SITES, PREV_MON, PREV_SUN)
    for it in extra:
        k = uniq_key_from(it)
        if all(k != uniq_key_from(x) for x in items_world_prev):
            items_world_prev.append(it)
            if len(items_world_prev) >= MIN_WORLD:
                break

# =========================
# CZ/SK EVENTY (RA, GoOut, DnBHeard)
# =========================
DATA_DIR = "data"
SEEN_FILE = os.path.join(DATA_DIR, "events_seen.json")
os.makedirs(DATA_DIR, exist_ok=True)
try:
    EVENTS_SEEN = json.load(open(SEEN_FILE, "r", encoding="utf-8"))
except Exception:
    EVENTS_SEEN = {}  # url -> first_seen ISO

def parse_jsonld_events(html: str, base_label: str) -> list[dict]:
    out=[]
    soup = BS(html, "html.parser")
    # 1) standardní JSON-LD
    for tag in soup.find_all("script", attrs={"type":"application/ld+json"}):
        try:
            node = json.loads(tag.string.strip())
        except Exception:
            continue
        nodes = node if isinstance(node, list) else node.get("@graph") if isinstance(node, dict) and "@graph" in node else [node]
        if not isinstance(nodes, list): nodes=[nodes]
        for n in nodes:
            if not isinstance(n, dict): 
                continue
            if n.get("@type") not in ("Event","MusicEvent"):
                continue
            name = clean_text(n.get("name") or "")
            url  = normalize_url(n.get("url") or "")
            if not name or not url: 
                continue
            # datumy
            start = n.get("startDate") or n.get("start_date")
            start_dt = None
            try:
                if start: start_dt = dtparse(start).astimezone(TZ)
            except Exception:
                start_dt = None
            # místo
            loc = ""
            locn = n.get("location")
            if isinstance(locn, dict):
                loc = clean_text(locn.get("name") or "")
            elif isinstance(locn, list) and locn and isinstance(locn[0], dict):
                loc = clean_text(locn[0].get("name") or "")
            out.append({
                "title": name,
                "summary": clean_text(loc),
                "link": url,
                "date": start_dt,
                "source": base_label
            })
    return out
    EVENT_LINK_RE = re.compile(r"/events?/\d+|/akce/|/event/", re.I)

def extract_event_links(html: str, domain: str, max_links: int = 30) -> list[str]:
    soup = BS(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = f"https://{domain}{href}"
        try:
            u = urlparse(href)
        except Exception:
            continue
        if u.netloc and domain.split(":")[0] in u.netloc and EVENT_LINK_RE.search(u.path):
            n = normalize_url(href)
            if n not in links:
                links.append(n)
        if len(links) >= max_links:
            break
    return links

def fetch_events_from_detail_pages(urls: list[str], label: str, max_pages: int = 30) -> list[dict]:
    out=[]
    for i, u in enumerate(urls[:max_pages]):
        try:
            html = fetch(u, timeout=20).text
        except Exception:
            continue
        # nejprve z detailu přímo JSON-LD
        evs = parse_jsonld_events(html, label)
        if evs:
            out.extend(evs)
            continue
        # fallback: vytvoř aspoň položku s názvem z <title>
        try:
            soup = BS(html, "html.parser")
            title = clean_text(soup.title.get_text()) if soup.title else ""
        except Exception:
            title = ""
        if title:
            out.append({"title": title, "summary": "", "link": u, "date": None, "source": label})
    return out

def scrape_ra_cz() -> list[dict]:
    listings = [
        "https://ra.co/events/cz/all/drumandbass",
        "https://ra.co/events/cz/prague/drumandbass",
    ]
    domain = "ra.co"
    detail_urls = []
    for lu in listings:
        try:
            html = fetch(lu).text
            detail_urls += extract_event_links(html, domain, max_links=40)
        except Exception:
            continue
    out = fetch_events_from_detail_pages(dedupe([{"link":u} for u in detail_urls], None) and list(dict.fromkeys(detail_urls)), "Resident Advisor", max_pages=35)
    return dedupe(out, 120)

def scrape_goout_cz() -> list[dict]:
    listings = [
        "https://goout.net/cs/cesko/akce/lezfymfti/?genres=party_drum_and_bass",
        "https://goout.net/cs/praha/parties/leznyvlkkzj/?genres=party_drum_and_bass",
    ]
    domain = "goout.net"
    detail_urls = []
    for lu in listings:
        try:
            html = fetch(lu).text
            detail_urls += extract_event_links(html, domain, max_links=60)
        except Exception:
            continue
    out = fetch_events_from_detail_pages(list(dict.fromkeys(detail_urls)), "GoOut", max_pages=40)
    return dedupe(out, 160)


def scrape_dnbeheard() -> list[dict]:
    # fallback: prostý výpis linků z textu
    u = "https://dnbeheard.cz/kalendar-akci/"
    out=[]
    try:
        html = fetch(u).text
        soup = BS(html, "html.parser")
        body = soup.find("main") or soup
        for a in body.find_all("a", href=True):
            t = clean_text(a.get_text())
            href = normalize_url(a["href"])
            if not t or not href: continue
            # heuristicky jen větší brandy nebo zahr. jména
            txt = t.lower()
            if any(b in txt for b in BIG_BRANDS) or any(h in txt for h in INTL_HEADLINERS):
                out.append({"title": t, "summary":"", "link": href, "date": None, "source":"DnBHeard"})
    except Exception:
        pass
    return dedupe(out, 60)

def priority_bucket(title: str) -> str:
    tl = title.lower()
    if any(b in tl for b in BIG_BRANDS): return "TOP"
    if any(h in tl for h in INTL_HEADLINERS): return "MID"
    return "LOW"

def remember_seen(url: str):
    if url not in EVENTS_SEEN:
        EVENTS_SEEN[url] = TODAY.isoformat()

classify_events

# stáhni vše a ulož „seen“
events_all = scrape_ra_cz() + scrape_goout_cz() + scrape_dnbeheard()
json.dump(EVENTS_SEEN, open(SEEN_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

events_recap, events_thisweek, events_new = classify_events(events_all)

# =========================
# VÝSTUP
# =========================
def add_and_format(it: dict) -> str:
    dstr = it["date"].strftime("%-d. %-m. %Y") if it.get("date") else TODAY.strftime("%-d. %-m. %Y")
    txt = summarize_item(it)
    ref = add_ref(it["link"], it["source"])
    return f"* {txt} ({dstr}) ([{it['source']}][{ref}])"

def period_str(a,b):
    return f"{a.strftime('%-d.')}–{b.strftime('%-d. %m. %Y')}"

PER_PREV = period_str(PREV_MON, PREV_SUN)

parts = []
parts.append(f"# DnB NOVINKY – {TODAY.strftime('%-d. %-m. %Y')}\n")

# Svět – jen minulý týden
parts.append(f"## Svět ({PER_PREV})\n")
world = items_world_prev[:MIN_WORLD] if len(items_world_prev) >= MIN_WORLD else items_world_prev
if world:
    for it in world: parts.append(add_and_format(it))
else:
    parts.append("* Žádné zásadní novinky.")
parts.append("")

# ČR / SK – jen minulý týden (z feedů)
parts.append(f"## ČR / SK ({PER_PREV})\n")
cz = items_cz_prev[:MIN_CZSK] if len(items_cz_prev) >= MIN_CZSK else items_cz_prev
if cz:
    for it in cz: parts.append(add_and_format(it))
else:
    parts.append("* Žádné zásadní novinky.")
parts.append("")

# Reddit – jen minulý týden
parts.append(f"## Reddit vlákna ({PER_PREV})\n")
rd = reddit_prev[:max(MIN_REDDIT, 3)] if len(reddit_prev) >= MIN_REDDIT else reddit_prev
if rd:
    for it in rd: parts.append(add_and_format(it))
else:
    parts.append("* Žádné zásadní novinky.")
parts.append("")

# Kuriozita – z minulého týdne; heuristika na „AI, rekord, hardware…“
def pick_curio(cands):
    KEYS = ["AI","uměl","rekord","prototype","leak","patent","cdj","controller","hardware","documentary"]
    for it in cands:
        blob = (it["title"] + " " + it.get("summary","")).lower()
        if any(k.lower() in blob for k in KEYS):
            return it
    return cands[0] if cands else None

curio = pick_curio(items_world_prev) or pick_curio(items_cz_prev)
parts.append(f"## Kuriozita ({PER_PREV})\n")
if curio:
    parts.append(add_and_format(curio))
else:
    parts.append("* Žádné zásadní novinky.")
parts.append("")

# Eventy CZ/SK – 3 bloky dle zadání
def fmt_event_block(title, lst):
    out=[f"### {title}\n"]
    if not lst:
        out.append("* Žádné relevantní novinky tento týden.")
        return "\n".join(out)
    for it in lst:
        out.append(add_and_format(it))
    return "\n".join(out)

parts.append("## Eventy ČR / SK\n")
parts.append(fmt_event_block("Recap minulý týden", events_recap))
parts.append("")
parts.append(fmt_event_block("Tento týden", events_thisweek))
parts.append("")
parts.append(fmt_event_block("Nově oznámené", [x for x in events_new if x not in events_recap and x not in events_thisweek]))
parts.append("")

# Zdroje
parts.append("## Zdroje\n")
for i,(label,url) in enumerate(refs, start=1):
    parts.append(f"[{i}]: {url}")

markdown_out = "\n".join(parts).strip()

# Uložení
os.makedirs("docs", exist_ok=True)
with open("docs/index.md", "w", encoding="utf-8") as f:
    f.write(markdown_out + "\n")

HTML_TMPL = """<!DOCTYPE html><html lang="cs"><meta charset="utf-8">
<title>DnB NOVINKY</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',Arial,sans-serif;max-width:900px;margin:40px auto;padding:0 16px;line-height:1.55}
h1{font-size:28px;margin:0 0 16px}
h2{font-size:20px;margin:24px 0 8px;border-bottom:1px solid #e5e7eb;padding-bottom:4px}
h3{font-size:17px;margin:18px 0 6px}
ul{padding-left:22px}
footer{margin-top:24px;font-size:12px;color:#666}
</style>
<body>
<main>
{CONTENT}
</main>
<footer>
Vygenerováno automaticky. Zdrojové kanály: Google News RSS, Reddit RSS, YouTube channel RSS, RAVE.cz feed, RA, GoOut, DnBHeard.
</footer>
</body></html>"""
html = HTML_TMPL.replace("{CONTENT}", md_to_html(markdown_out, output_format="xhtml1"))
with open("docs/index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("OK: docs/index.md + docs/index.html + Eventy CZ/SK")
