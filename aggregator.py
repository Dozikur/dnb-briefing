#!/usr/bin/env python3
import os, re, sys, json, time, hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
import requests
import feedparser
from dateutil import tz
from dateutil.parser import parse as dtparse
import pytz
from bs4 import BeautifulSoup as BS
from html import unescape
from markdown import markdown as md_to_html

# ---------------------------------------------------------------------------
# Čas a období
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
# Pomocné funkce
# ---------------------------------------------------------------------------
def within(date_dt, start_date, end_date):
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
            except:
                pass
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

# ---------------------------------------------------------------------------
# Dotazy / Feedy
# ---------------------------------------------------------------------------
def google_news_feed(site, when_days=14, lang="cs", region="CZ"):
    # Pouze site:, filtr až heuristikou
    query = f"site:{site} when:{when_days}d"
    base = "https://news.google.com/rss/search?q="
    tail = f"&hl={lang}-{region}&gl={region}&ceid={region}:{lang}"
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
    if not cid: return None
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"

def xenforo_forum_index_rss(base):
    return base.rstrip("/") + "/forums/index.rss"

# ---------------------------------------------------------------------------
# Konfigurace zdrojů a heuristik
# ---------------------------------------------------------------------------
PRIMARY_SITES = [
    ("Mixmag", "mixmag.net"),
    ("Resident Advisor", "ra.co"),
    ("UKF", "ukf.com"),
    ("Musicserver.cz", "musicserver.cz"),
    ("Rave.cz", "rave.cz"),
    ("PM Studio", "pmstudio.com"),
    ("DogsOnAcid", "dogsonacid.com"),
]
REDDITS = [("r/DnB","DnB"), ("r/LetItRollFestival","LetItRollFestival")]
YOUTUBES = ["@Liquicity", "@dnballstars", "@WeAreRampageEvents"]

# sekundární zdroje pro fallback
SECONDARY_SITES = [
    ("EDM.com", "edm.com"),
    ("Dancing Astronaut", "dancingastronaut.com"),
    ("Rolling Stone Australia", "rollingstone.com.au"),
    ("Billboard", "billboard.com"),
]

# klíčová slova pro drum & bass
POS = [
    "drum and bass","drum’n’bass","drum n bass","dnb","dn'b","jungle",
    "neurofunk","liquid","jump up","rollers","ukf","hospital records",
    "let it roll","ram records","blackout music","shogun audio",
]
# klíčová slova, která chceme vyřadit
NEG = [
    "techno","tech house","house","trance","edm pop","electro house",
    "hardstyle","psytrance","deep house","progressive house",
]

CZSK_TOKENS = [
    "dnb","drum and bass","drum’n’bass","drum n bass","neuro","liquid","jump up","let it roll"
]

HEADERS = {"User-Agent": "DnB-Novinky/1.0 (+github actions)"}
ALLOWLIST = ("mixmag.net", "ra.co", "ukf.com")

MIN_WORLD = 5
MIN_CZSK  = 2
MIN_REDDIT= 2

def is_dnb_related(title: str, summary: str, url: str) -> bool:
    t = f"{title} {summary}".lower()
    if any(d in url for d in ALLOWLIST):
        return not any(n in t for n in NEG)
    return any(p in t for p in POS) and not any(n in t for n in NEG)

def is_czsk_dnb(title: str, summary: str) -> bool:
    t = f"{title} {summary}".lower()
    return any(x in t for x in CZSK_TOKENS) and not any(n in t for n in NEG)

# ---------------------------------------------------------------------------
# Feedy
# ---------------------------------------------------------------------------
FEEDS = []
# Google News pro vybrané weby
for name, domain in PRIMARY_SITES:
    FEEDS.append({
        "name": f"GoogleNews:{name}",
        "kind": "rss",
        "section": "world",
        "url": google_news_feed(domain, when_days=14, lang="cs", region="CZ"),
        "source_label": name
    })
# Přímý RSS Rave.cz
FEEDS.append({
    "name":"Rave.cz",
    "kind":"rss",
    "section":"czsk",
    "url":"https://www.rave.cz/feed/",
    "source_label":"RAVE.cz"
})
# Reddit
for label, sub in REDDITS:
    FEEDS.append({
        "name": f"Reddit:{label}",
        "kind": "rss",
        "section": "reddit",
        "url": reddit_rss(sub),
        "source_label": f"Reddit {label}"
    })
# YouTube kanály
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
# DogsOnAcid XenForo RSS (best-effort)
FEEDS.append({
    "name":"DogsOnAcidForum",
    "kind":"rss",
    "section":"world",
    "url": xenforo_forum_index_rss("https://www.dogsonacid.com"),
    "source_label":"DogsOnAcid Forum"
})

# ---------------------------------------------------------------------------
# Zpracování
# ---------------------------------------------------------------------------
def classify_section(entry, src_label, link):
    host = re.sub(r"^www\.", "", (re.findall(r"https?://([^/]+)", link) or [""])[0])
    tld = host.split(".")[-1] if host else ""
    if tld in ("cz","sk") or "rave.cz" in host or "musicserver.cz" in host:
        return "czsk"
    return "world"

def entry_to_item(entry, source_label):
    link = entry.get("link") or ""
    title = clean_text(entry.get("title") or "")
    desc = clean_text(entry.get("summary") or entry.get("description") or "")
    dt = get_best_date(entry)
    return {
        "title": title,
        "summary": desc,
        "link": link,
        "date": dt,
        "source": source_label
    }

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
all_refs = []  # pro číslované zdroje
ref_map = {}   # url -> idx

def add_ref(url, label):
    if url in ref_map:
        return ref_map[url]
    idx = len(all_refs) + 1
    ref_map[url] = idx
    all_refs.append((label, url))
    return idx

# Stáhni a roztřiď
for f in FEEDS:
    feed = fetch_feed(f["url"])
    if not feed or not feed.entries:
        continue
    for e in feed.entries:
        it = entry_to_item(e, f["source_label"])
        if not it["date"]:
            continue

        # Reddit zvlášť
        if f["section"] == "reddit":
            if within(it["date"], PREV_MON, PREV_SUN):
                reddit_prev.append(it)
            elif within(it["date"], CUR_MON, CUR_SUN):
                reddit_cur.append(it)
            continue

        # Klasifikace CZ/SK vs svět
        sec = classify_section(e, f["source_label"], it["link"])
        it["section"] = sec

        # žánrový filtr
        if sec == "czsk":
            if not is_czsk_dnb(it["title"], it["summary"]):
                continue
        else:
            if not is_dnb_related(it["title"], it["summary"], it["link"]):
                continue

        # Týdenní rozdělení
        if within(it["date"], PREV_MON, PREV_SUN):
            (items_prev_czsk if sec=="czsk" else items_prev_world).append(it)
        elif within(it["date"], CUR_MON, CUR_SUN):
            (items_cur_czsk if sec=="czsk" else items_cur_world).append(it)

# Fallback: sekundární zdroje, pokud svět nedosáhl minima
def harvest_sites(sites, start_date, end_date):
    out = []
    for label, domain in sites:
        feed_url = google_news_feed(domain, when_days=14, lang="cs", region="CZ")
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

if len(items_prev_world) < MIN_WORLD:
    extra_prev = harvest_sites(SECONDARY_SITES, PREV_MON, PREV_SUN)
    items_prev_world = topup_to_min(items_prev_world, MIN_WORLD, extra_prev)

if len(items_cur_world) < MIN_WORLD:
    extra_cur = harvest_sites(SECONDARY_SITES, CUR_MON, CUR_SUN)
    items_cur_world = topup_to_min(items_cur_world, MIN_WORLD, extra_cur)

# Deduplikace
def dedupe(lst, maxn=None):
    seen, out = set(), []
    for it in sorted(lst, key=lambda x: x["date"], reverse=True):
        k = uniq_key(it)
        if k in seen: continue
        seen.add(k); out.append(it)
        if maxn and len(out) >= maxn: break
    return out

items_prev_world = dedupe(items_prev_world, maxn=20)
items_cur_world  = dedupe(items_cur_world,  maxn=20)
items_prev_czsk  = dedupe(items_prev_czsk,  maxn=10)
items_cur_czsk   = dedupe(items_cur_czsk,   maxn=10)
reddit_prev      = dedupe(reddit_prev,      maxn=8)
reddit_cur       = dedupe(reddit_cur,       maxn=8)

# ---------------------------------------------------------------------------
# Stavba výstupu
# ---------------------------------------------------------------------------
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
PER_CUR  = period_str(CUR_MON, CUR_SUN)

world_prev = pick(items_prev_world, MIN_WORLD)
world_cur  = pick(items_cur_world,  MIN_WORLD)
cz_prev    = pick(items_prev_czsk,  MIN_CZSK)
cz_cur     = pick(items_cur_czsk,   MIN_CZSK)
rd_prev    = pick(reddit_prev,      MIN_REDDIT+1)  # ideál 3–4
rd_cur     = pick(reddit_cur,       MIN_REDDIT+1)

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

# Kuriozita
def pick_curiosity(cands):
    KEYS = ["AI", "uměl", "study", "rekord", "unikátní", "rare", "prototype", "leak", "patent"]
    for it in cands:
        blob = (it["title"]+" "+it["summary"]).lower()
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

# Markdown
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

# Zdroje
refs_lines = ["\n## Zdroje\n"]
for i,(label,url) in enumerate(all_refs, start=1):
    refs_lines.append(f"[{i}]: {url}")
md_parts.append("\n".join(refs_lines) + "\n")

markdown_out = "\n".join(md_parts).strip()

# ---------------------------------------------------------------------------
# Výstup: MD + HTML
# ---------------------------------------------------------------------------
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
Vygenerováno automaticky. Zdrojové kanály: Google News RSS, Reddit RSS, YouTube channel RSS, RAVE.cz feed.
</footer>
</body></html>"""
html_content = md_to_html(markdown_out, output_format="xhtml1")
html = html_template.replace("{CONTENT}", html_content)
with open("docs/index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("OK: docs/index.md + docs/index.html")

# ---------------------------------------------------------------------------
# Volitelně: Google Slides webhook
# ---------------------------------------------------------------------------
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
            "curiosity_prev": [build_curio(PER_PREV, cur_prev).split("\n",2)[2] if cur_prev else "* Žádné zásadní novinky."],
            "curiosity_cur":  [build_curio(PER_CUR,  cur_cur ).split("\n",2)[2] if cur_cur  else "* Žádné zásadní novinky."],
        },
        "sources": [f"[{i}]: {u}" for i,(_,u) in enumerate(all_refs, start=1)],
        "presentationId": PRESENTATION_ID
    }
    try:
        r = requests.post(WEBHOOK, json=payload, timeout=25)
        print("AppsScript:", r.status_code, r.text[:200])
    except Exception as ex:
        print("AppsScript error:", ex, file=sys.stderr)
