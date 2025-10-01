# aggregator.py
from __future__ import annotations
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import os

# --- Formátování dat (portable Windows/Linux) -------------------------------

def _fmt_dmy(d: date) -> str:
    return f"{d.day}. {d.month}. {d.year}"

def _fmt_dm(d: date) -> str:
    return f"{d.day}. {d.month}."

def _ensure_date(x) -> date:
    if isinstance(x, date):
        return x
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, str):
        # Podpora "YYYY-MM-DD" i "YYYY-MM-DDTHH:MM:SS"
        try:
            return datetime.fromisoformat(x).date()
        except ValueError:
            return datetime.strptime(x, "%Y-%m-%d").date()
    raise TypeError(f"Unsupported date type: {type(x)}")

def period_str(a, b) -> str:
    a = _ensure_date(a)
    b = _ensure_date(b)
    return f"{_fmt_dm(a)}\u2009–\u2009{_fmt_dmy(b)}"

# --- Týdenní okno ------------------------------------------------------------

def week_range(anchor: Optional[str] = None) -> tuple[date, date, str]:
    """
    Vrátí (pondělí, neděle, 'YYYY-WW').
    anchor=None nebo 'latest' -> dnešní týden.
    anchor='YYYY-MM-DD' -> týden obsahující zadané datum.
    """
    if anchor and anchor != "latest":
        d = _ensure_date(anchor)
    else:
        d = date.today()
    start = d - timedelta(days=d.weekday())   # pondělí
    end = start + timedelta(days=6)           # neděle
    label = f"{start.isocalendar().year}-W{start.isocalendar().week:02d}"
    return start, end, label

# --- Šablona a render --------------------------------------------------------

BUILTIN_TEMPLATE_MD = """# DnB Monday Briefing — týden {{ week_label }}
**Období:** {{ period_from }}–{{ period_to }}

## Tuzemsko
{% for i in items.cz %}- **{{ i.title }}** — {{ i.summary }}{% if i.proof_links %} [zdroj]({{ i.proof_links[0] }}){% endif %}
{% else %}_bez položek_
{% endfor %}

## Ze světa
{% for i in items.world %}- **{{ i.title }}** — {{ i.summary }}{% if i.proof_links %} [zdroj]({{ i.proof_links[0] }}){% endif %}
{% else %}_bez položek_
{% endfor %}

## Reddit
{% for i in items.reddit %}- **{{ i.title }}** — {{ i.summary }}{% if i.proof_links %} [vlákno]({{ i.proof_links[0] }}){% endif %}
{% else %}_bez položek_
{% endfor %}

## Kuriozita
{% for i in items.curiosum %}- **{{ i.title }}** — {{ i.summary }}{% if i.proof_links %} [zdroj]({{ i.proof_links[0] }}){% endif %}
{% else %}_bez položek_
{% endfor %}

---
### Zdroje
{% for s in sources %}- {{ s }}
{% else %}_neuvedeno_
{% endfor %}
"""

def load_template_md() -> str:
    p = Path("templates/briefing.md.j2")
    if p.exists():
        return p.read_text(encoding="utf-8")
    return BUILTIN_TEMPLATE_MD

def render_md(payload: Dict[str, Any], week_label: str) -> Path:
    from jinja2 import Template  # jediná povinná závislost
    tpl = Template(load_template_md())
    md = tpl.render(**payload)
    out_dir = Path("docs")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{week_label}.md"
    out_path.write_text(md, encoding="utf-8")
    return out_path

# --- Jednoduchý ingestor pro CC.cz (volitelný) ------------------------------

def fetch_cccz(urls: List[str]) -> List[Dict[str, Any]]:
    """
    Volitelné. Vyžaduje: pip install requests beautifulsoup4
    Pokud knihovny nejsou, vrátí prázdný list.
    """
    try:
        import requests
        from bs4 import BeautifulSoup
    except Exception:
        return []

    out: List[Dict[str, Any]] = []
    for u in urls:
        try:
            r = requests.get(u, timeout=15)
            r.raise_for_status()
            s = BeautifulSoup(r.text, "html.parser")
            title_el = s.find("h1")
            title = title_el.get_text(strip=True) if title_el else u
            perex_el = s.select_one(".article__perex")
            perex = perex_el.get_text(strip=True) if perex_el else ""
            out.append({
                "title": title,
                "summary": perex or "Bez perexu",
                "proof_links": [u],
                "date": date.today().isoformat(),
                "region": "cz",
                "type": "news",
                "source": "cc.cz",
                "sentiment": 0.0,
                "tags": []
            })
        except Exception:
            # Tichý skip kusu, ať pipeline doběhne
            continue
    return out

# --- Deduplikace a payload ---------------------------------------------------

def dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for it in items:
        key = (it.get("source", ""), (it.get("title") or "").strip().lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def payload_for_week(start: date, end: date, label: str) -> Dict[str, Any]:
    # 1) Načti odkazy z env proměnných (volitelné)
    #   Příklad: set CCZ_URLS="https://cc.cz/a https://cc.cz/b"
    ccz_urls = os.environ.get("CCZ_URLS", "").split()

    # 2) Stáhni data
    cz_items = fetch_cccz(ccz_urls)[:5] if ccz_urls else []

    # 3) Fallback, ať máš něco k vyzkoušení bez závislostí
    if not cz_items:
        cz_items = [{
            "title": "Test CZ položka",
            "summary": "Krátké shrnutí testu. Nahraď reálnými odkazy.",
            "proof_links": ["https://example.com"],
            "date": start.isoformat(),
            "region": "cz",
            "type": "news",
            "source": "manual",
            "sentiment": 0.0,
            "tags": []
        }]

    all_items = dedupe(cz_items)

    payload = {
        "week_label": label,
        "period_from": period_str(start, end).split("–")[0].strip(),  # jen pro zobrazení jako v šabloně
        "period_to": period_str(start, end).split("–")[-1].strip(),
        "items": {
            "cz": [i for i in all_items if i.get("region") == "cz"][:5],
            "world": [i for i in all_items if i.get("region") != "cz"][:5],
            "reddit": [i for i in all_items if i.get("type") == "opinion"][:2],
            "curiosum": [i for i in all_items if i.get("type") == "curiosum"][:1],
        },
        "sources": sorted({i.get("source", "unknown") for i in all_items})
    }
    return payload

# --- CLI --------------------------------------------------------------------

def main():
    # Podpora: python aggregator.py --week latest | --week YYYY-MM-DD
    import sys
    anchor = "latest"
    if "--week" in sys.argv:
        i = sys.argv.index("--week")
        if i + 1 < len(sys.argv):
            anchor = sys.argv[i + 1]

    start, end, label = week_range(anchor)
    payload = payload_for_week(start, end, label)
    out_path = render_md(payload, label)
    print(f"[OK] Vygenerováno: {out_path}")

if __name__ == "__main__":
    main()
