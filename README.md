# DnB & Festival Intelligence

Interní týdenní briefing pro Let It Roll a Beatworx publikovaný přes GitHub Pages.

## Struktura

- `index.html` — webový přehled a archiv.
- `news/index.json` — dynamický seznam briefingů.
- `news/YYYY-week_N.json` — týdenní výstupy.
- `schemas/briefing.schema.json` — datové schéma verze 2.
- `scripts/validate_briefing.py` — validace manifestu, historie a nových výstupů.
- `AUTOMATION.md` — redakční a publikační pravidla.
- `.github/workflows/validate-briefing.yml` — kontrola manifestu a briefingů bez zápisových oprávnění.

## Lokální kontrola

```bash
python scripts/validate_briefing.py --all
```

Historické soubory ve starém formátu se načítají zpětně kompatibilně. Nové briefingy musí používat schéma verze 2.
