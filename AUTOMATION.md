# Pondělní DnB & Festival Intelligence

Tento dokument je závazná specifikace pro týdenní automatizaci. Automatizace používá veřejný web a již připojený GitHub repozitář. Bez výslovného schválení nesmí připojit novou službu, účet ani datový zdroj vyžadující přihlášení.

## Harmonogram

- Spuštění: každé pondělí v 06:30 `Europe/Prague`.
- Zpracované období: předchozí kalendářní týden od pondělí do neděle.
- Výhled: potvrzené události a strategické změny relevantní pro následujících 30 dní.
- Cíl publikace: nejpozději v 09:00, aby byl briefing připravený na pondělní poradu po obědě.

## Účel

Briefing není hudební magazín. Slouží jako interní podklad pro Let It Roll a Beatworx. Každá položka musí pomáhat rozhodovat o programu, konkurenci, produkci, návštěvnickém zážitku, marketingu, ticketingu nebo strategii značky.

Samostatný hudební release se zařazuje pouze tehdy, pokud mění pozici interpreta, labelu nebo festivalového trendu. Běžné releasy bez strategického dopadu se vynechávají.

## Povinné sekce a pořadí

1. `competition` — Přímá konkurence
2. `festival_industry` — Festivalový průmysl
3. `dnb_scene` — DnB scéna
4. `cz_sk` — ČR a Slovensko
5. `audience_sentiment` — Sentiment publika
6. `strategic_releases` — Strategické releasy
7. `lir_actions` — Doporučené kroky pro LIR

Prázdná sekce zůstává ve výstupu jako prázdné pole `items`.

## Sledovaná konkurence

Prioritně sledovat Rampage, Rampage Open Air, Liquicity Festival, DnB Allstars, Hospitality, Beats for Love, Darkshire, Outlook, SUNANDBASS, Boomtown, Korsakov a další festivaly nebo promotéry s významným DnB programem. Let It Roll sledovat pouze kvůli externímu sentimentu a srovnání, nikoli jako konkurenta.

Zachytit zejména:

- oznámení line-upu, timetable a nové programové formáty;
- změny venue, kapacity, termínu a délky akce;
- cenotvorbu, ticketing, payment plans a vyprodané kategorie;
- stage hostingy, partnerství, sponzoring a obsahové inovace;
- návštěvnický servis, camping, dopravu, cashless a bezpečnost;
- rušení, přesuny, počasí, produkční problémy a krizovou komunikaci;
- recenze a opakující se sentiment publika.

## Zdroje

### DnB a elektronická scéna

Oficiální weby a sociální kanály festivalů, promotérů, labelů a interpretů; DJ Mag; Mixmag; Resident Advisor; UKF; Drum & Bass UK; LoveThatBass; Best Drum & Bass; Drumandbass.nl; Dogs On Acid; Beatportal.

### Festivalový průmysl

Festival Insights; IQ Magazine; Access All Areas; Music Business Worldwide; Pollstar; Event Industry News; oficiální tiskové zprávy pořadatelů, vlastníků, ticketingových platforem a veřejných institucí.

### ČR a Slovensko

DNBe HearD; Hoofbeats; Musicserver; Rave.cz; GoOut; oficiální weby a kanály festivalů, klubů a promotérů.

### Komunitní sentiment

Reddit `r/DnB`, `r/LetItRollFestival`, `r/Rampagefestival` a relevantní veřejná diskusní vlákna. Komunitní zdroj nesmí být jediným důkazem tvrdého faktu.

## Ověření

- Každý tvrdý fakt musí mít primární zdroj nebo dva nezávislé sekundární zdroje.
- Reddit a komentáře dokazují sentiment, nikoli návštěvnost, finance nebo oficiální rozhodnutí.
- Datum publikace patří do `published_at`. Datum konání patří do `event_start` a `event_end`.
- Neověřená tvrzení mají `confidence: unverified` a nesmějí být formulována jako fakta.
- Nepoužívat Wikipedii jako hlavní zdroj nové zprávy.
- Nepoužívat Google image cache, dočasné Instagram CDN adresy ani obrázky bez dohledatelného původu.
- Pokud stabilní vizuál není dostupný, ponechat `media` prázdné.

## Výstup

- Čeština.
- Celkem nejvýše 14 obsahových položek mimo sekci `lir_actions`.
- Jedna položka obsahuje 1 až 4 krátké odstavce.
- `why_it_matters` vysvětluje konkrétní dopad na Let It Roll.
- `recommended_action` obsahuje jeden proveditelný krok nebo explicitní `Bez akce, pouze sledovat`.
- Žádné umělé štítky TOP, MID nebo LOW.
- Žádná výplň, obecné promo formulace ani duplicity z předchozího týdne bez nové informace.

## Publikační postup

1. Přečíst `AUTOMATION.md`, `schemas/briefing.schema.json` a aktuální `news/index.json`.
2. Vytvořit `news/YYYY-week_N.json` ve schématu verze 2. Číslo týdne odpovídá zpracovanému období, nikoli dni spuštění.
3. Přidat nový záznam na začátek `news/index.json`.
4. Zkontrolovat JSON, duplicity, data, odkazy a všechna povinná pole.
5. Vytvořit větev `automation/briefing-YYYY-week-N`.
6. Zapsat pouze nový briefing a manifest.
7. Otevřít nedraftový pull request s názvem `Add DnB briefing YYYY week N`.
8. Workflow `.github/workflows/validate-briefing.yml` zkontroluje celý datový archiv.
9. Pull request zůstane připravený ke sloučení. Automatické sloučení vyžaduje samostatné schválení zápisových oprávnění.
10. Pokud validace selže, nic neobcházet a vrátit přesný seznam chyb.
