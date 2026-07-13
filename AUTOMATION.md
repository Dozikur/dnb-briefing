# Pondělní DnB News

Tento dokument je závazná specifikace pro týdenní automatizaci. Automatizace používá veřejný web a již připojený GitHub repozitář. Bez výslovného schválení nesmí připojit novou službu, účet ani datový zdroj vyžadující přihlášení.

## Harmonogram

- Spuštění: každé pondělí v 06:30 `Europe/Prague`.
- Zpracované období: předchozí kalendářní týden od pondělí do neděle.
- Výhled: potvrzené události a strategické změny relevantní pro následujících 30 dní.
- Cíl publikace: nejpozději v 09:00, aby byl briefing připravený na pondělní poradu po obědě.

## Účel

Briefing je čistě informační týdenní přehled drum and bass scény, komunitních diskusí, přímé festivalové konkurence a širšího festivalového průmyslu. Web tvoří jeden souvislý proud zpráv bez viditelného dělení na scénu, sentiment nebo doporučení.

Scénová zpráva nemusí mít okamžitý provozní dopad na LIR. Musí ale pomáhat chápat, kteří interpreti a labely rostou, jak se mění zvuk a publikum, jaké nové projekty nebo formáty vznikají a co se v komunitě skutečně řeší. U položek z `dnb_scene`, `audience_sentiment` a `strategic_releases` se dopad posuzuje také z pohledu bookingu, dramaturgie, labelu, obsahu a dlouhodobého vývoje scény.

Běžný samostatný release se nezařazuje automaticky. Výběr má zachytit nejdůležitější alba, EP, spolupráce, návraty, labelové přesuny a kampaně, které ukazují posun interpreta, labelu nebo subžánru. Festivalová témata nesmějí vytlačit povinné pokrytí DnB scény a Redditu.

## Poučení z historických briefingů

Největší hodnotu pro poradu měly zprávy, které ukázaly změnu konkurenčního formátu nebo konkrétní provozní a obchodní riziko. Patřily sem například reakce návštěvníků na prostor a produkci Rampage, nový imerzivní formát Section 63, lineupová strategie Liquicity, přesun WORSHIP do severoamerických arén, FestProtect od StubHubu, rušení akcí kvůli vedru, kolaps festivalové stage a problémy s odpadem v kempech.

Nízkou hodnotu měly rutinní releasy, běžné rozhovory k albům, jednotlivé klubové pozvánky, nostalgické výroční zprávy a kuriozity bez dopadu na festivalové rozhodování. Tyto položky se nesmějí používat jako výplň.

Před každým během přečíst nejméně čtyři poslední briefingy. Novou položku zařadit jen tehdy, pokud obsahuje skutečný posun oproti již publikované informaci. Opakované téma musí výslovně popsat, co se změnilo.

## Povinné sekce a pořadí

1. `competition` — Přímá konkurence
2. `festival_industry` — Festivalový průmysl
3. `dnb_scene` — DnB scéna
4. `cz_sk` — ČR a Slovensko
5. `audience_sentiment` — Sentiment publika
6. `strategic_releases` — Strategické releasy
7. `lir_actions` — Doporučené kroky pro LIR

Sekce `competition`, `cz_sk` a `strategic_releases` mohou zůstat prázdné, pokud nejsou doložené relevantní změny. Od týdne 29 roku 2026 nesmějí být prázdné sekce `dnb_scene` a `audience_sentiment`. Nedostupnost povinného zdroje je chyba sběru a důvod běh zastavit, nikoli důvod publikovat degradovaný briefing.

## Sledovaná konkurence

### Přímí konkurenti

Prioritně sledovat Rampage, Rampage Open Air, Liquicity Festival, DnB Allstars, Hospitality, Beats for Love, Darkshire, Outlook, SUNANDBASS, Boomtown a Korsakov. Doplňovat další festivaly nebo promotéry, pokud soutěží o stejné DnB publikum, stejné umělce, podobný termín, podobnou destinaci nebo podobný rozpočet návštěvníka.

### Strategické benchmarky

WORSHIP a velké DnB arénové projekty; významné multižánrové festivaly s hlavním DnB programem; sportovní a kulturní akce, které umisťují DnB na hlavní stage; nové destination festivaly a festivalové formáty využitelné jako benchmark pro Let It Roll.

Let It Roll sledovat pouze kvůli externímu sentimentu, reputaci a srovnání. Nevydávat vlastní oznámení jako konkurenční novinku.

Zachytit zejména:

- nové termíny, překryvy s LIR, změny délky akce a vstup na nové trhy;
- venue, kapacitu, počet stages, hlavní produkční prvky a změny areálu;
- nové programové koncepty, exkluzivní sety, stage hostingy a práci s headlinery;
- lineup pouze tehdy, pokud ukazuje strategii, překryv s LIR, změnu žánrového směru nebo konkurenční tlak na booking;
- cenu vstupenek, cenové vlny, payment plans, VIP, camping a vyprodané kategorie;
- návštěvnický servis, dopravu, cashless, vodu, toalety, camping, crowd flow a bezpečnost;
- marketingovou kampaň, positioning, partnerství, sponzoring, livestream a práci s obsahem;
- reakce publika na zvuk, stage design, kapacitu, lineup, ceny a zázemí;
- rušení, přesuny, počasí, produkční problémy, refundace a krizovou komunikaci.

Každá položka v `competition` musí odpovědět:

1. Co se tento týden změnilo.
2. Kterého konkurenta se změna týká.
3. Jaký konkrétní důkaz nebo měřitelný údaj ji podporuje.
4. Jaký trend nebo konkurenční tah změna představuje.
5. Jaký je dopad na Let It Roll.
6. Jaký jeden krok má LIR udělat nebo co má dále sledovat.

## Festivalový průmysl

Sekce `festival_industry` neslouží pro obecné hudební novinky. Hledat pouze změny, které ovlivňují ekonomiku, provoz, riziko nebo budoucí podobu festivalů.

Povinné tematické okruhy:

- ekonomika festivalů, náklady, marže, prodeje, pozdní nákup vstupenek a spotřebitelská důvěra;
- ticketing, refundace, pojištění, dynamické ceny, sekundární trh a nové prodejní platformy;
- vlastnictví, akvizice, konsolidace a kroky Live Nation, Superstruct, AEG, CTS Eventim, Ticketmaster a See Tickets;
- rušení festivalů, insolvence, uzavírání venue a problémy dodavatelského řetězce;
- extrémní počasí, klimatická odolnost, bezpečnost, regulace a povolovací procesy;
- stage technologie, zvuk, crowd management, cashless, festivalové aplikace a provozní inovace;
- camping, doprava, voda, odpady, udržitelnost a návštěvnický komfort;
- nové příjmy, partnerství, sponzoring a rozšiřování festivalu mimo samotný hudební program.

Zprávu zařadit pouze tehdy, pokud lze vysvětlit konkrétní dopad na rozpočet, produkci, marketing, ticketing, bezpečnost nebo návštěvnický zážitek LIR.

## DnB scéna

Sekce `dnb_scene` je povinný redakční blok, nikoli doplněk festivalových zpráv. Každý týden projít zdroje napříč mainstreamem, undergroundem a hlavními subžánry a vybrat nejméně dvě nejsilnější scénové změny.

Zachytit zejména:

- významné kariérní posuny interpretů, nové projekty, návraty, rozpady a změny sestav;
- nové labely, přesuny mezi labely, akvizice, distribuční změny a nové kurátorské směry;
- alba, EP a spolupráce, pokud představují výrazný kreativní, komerční nebo subžánrový posun;
- nové live show, tour koncepty, AV formáty, významné crossover momenty a růst DnB na nových trzích;
- rozhovory a profily obsahující skutečné informace o fungování scény, tvorbě, kreditech, zastoupení nebo ekonomice;
- změny vkusu, nástup nových jmen, návrat staršího zvuku a témata, která se opakují napříč médii, sety a komunitou.

Pouhá vazba na festival není podmínkou. `why_it_matters` může vysvětlovat dopad na booking, dramaturgii, LIR Recordings, marketing, obsah nebo orientaci ve scéně.

## Reddit r/DnB

Při každém běhu povinně projít veřejné přehledy Redditu `r/DnB` v režimech Hot a Top za poslední týden. Doplnit kontrolu nových vláken z reportovacího období, aby pozdě publikované diskuse nebyly znevýhodněné.

Z kandidátů vybrat nejméně dvě nejsilnější diskuse podle kombinace:

- počtu a kvality komentářů;
- skóre a relativní viditelnosti vůči ostatním vláknům daného týdne;
- novosti tématu a šíře názorů;
- významu pro hudební vkus, subžánry, interprety, produkci, chování publika nebo fungování scény.

Vyřadit prosté identifikace tracku, izolované meme, vlastní promo bez diskuse, duplicitní příspěvky a otázky s několika povrchními odpověďmi. Každá zařazená položka musí odkázat přímo na vlákno, uvést stav skóre a počtu komentářů v době sběru a shrnout hlavní názorové proudy. Reddit dokládá existenci a intenzitu debaty, nikoli tvrdá fakta.

Pokud nelze získat alespoň dvě kvalifikované diskuse nebo je Reddit nedostupný, běh se nesmí publikovat. Výstup musí vrátit chybu pokrytí.

## Výběrový filtr

Každého kandidáta interně posoudit podle tří společných kritérií a jednoho kritéria podle sekce. Hodnocení se na webu nezobrazuje.

Společná kritéria:

- novost oproti posledním čtyřem briefingům: 0 až 2 body;
- síla důkazů: 0 až 2 body;
- rozsah nebo význam změny: 0 až 2 body.

Sekční kritérium:

- `competition` a `festival_industry`: konkrétní dopad na Let It Roll, 0 až 3 body;
- `dnb_scene` a `strategic_releases`: význam pro vývoj DnB scény, booking, dramaturgii, label nebo obsah, 0 až 3 body;
- `audience_sentiment`: relativní engagement, kvalita diskuse a šíře názorů, 0 až 3 body;
- `cz_sk`: význam pro lokální scénu nebo obchodní prostředí, 0 až 3 body.

Zařadit položky se součtem nejméně 5 bodů. Scénové a komunitní zprávy se nesmějí vyřadit jen proto, že nemají okamžitý provozní dopad na LIR. Výjimkou z bodového prahu je bezprostřední bezpečnostní, reputační nebo termínové riziko.

Nezařazovat:

- běžný release bez širšího významu pro interpreta, label, subžánr, booking nebo publikum;
- rozhovor, který pouze opakuje promo tvrzení k novému albu a nepřináší scénovou informaci;
- rutinní klubovou pozvánku nebo lokální seznam akcí;
- samotný lineup bez analýzy strategie a konkurenčního dopadu;
- recyklované oznámení bez nové informace;
- jeden izolovaný komentář vydávaný za sentiment celé komunity;
- kuriozitu bez použitelného závěru pro festival.

## Zdroje

### DnB a elektronická scéna

Povinný týdenní sweep: UKF; Drum & Bass UK; DJ Mag; Mixmag; Resident Advisor; Beatportal; Data Transmission DnB; LoveThatBass; Dogs On Acid; Drumandbass.nl; Best Drum & Bass. Doplnit oficiální weby a veřejné sociální kanály relevantních labelů a interpretů. Nespoléhat jen na obecné zpravodajské vyhledávání, protože zvýhodňuje festivaly a mainstreamová média.

### Festivalový průmysl

Festival Insights; IQ Magazine; Access All Areas; Music Business Worldwide; Pollstar; Event Industry News; oficiální tiskové zprávy pořadatelů, vlastníků, ticketingových platforem a veřejných institucí.

### ČR a Slovensko

DNBe HearD; Hoofbeats; Musicserver; Rave.cz; GoOut; oficiální weby a kanály festivalů, klubů a promotérů.

### Komunitní sentiment

Reddit `r/DnB` je povinný každý týden. Do `sources_scanned` zapsat `Reddit r/DnB: hot + top/week`. Pro festivalový sentiment dále sledovat `r/LetItRollFestival`, `r/Rampagefestival` a další relevantní veřejná diskusní vlákna. Komunitní zdroj nesmí být jediným důkazem tvrdého faktu.

U obecných DnB debat shrnout hlavní názorové proudy, míru shody, sporné body a význam pro scénu. U festivalového sentimentu uvést, co lidé chválí, co kritizují, zda jsou názory rozdělené a jaká provozní nebo obchodní lekce z toho plyne. Jednotlivý virální komentář nestačí.

## Ověření

- Každý tvrdý fakt musí mít primární zdroj nebo dva nezávislé sekundární zdroje.
- Reddit a komentáře dokazují sentiment, nikoli návštěvnost, finance nebo oficiální rozhodnutí.
- Datum publikace patří do `published_at`. Datum konání patří do `event_start` a `event_end`.
- Neověřená tvrzení mají `confidence: unverified` a nesmějí být formulována jako fakta.
- Nepoužívat Wikipedii jako hlavní zdroj nové zprávy.
- Nepoužívat Google image cache, dočasné Instagram CDN adresy ani obrázky bez dohledatelného původu.
- Pokud stabilní vizuál není dostupný, ponechat `media` prázdné.

## Mediální přílohy

U každé vybrané zprávy aktivně zkontrolovat oficiální Instagram interpreta, labelu, festivalu nebo organizátora a relevantní YouTube kanál. Pokud příspěvek nebo video přímo dokládá popsanou novinku, přidat jej do `media` jako `instagram` nebo `youtube`.

- Preferovat původní oznámení, trailer, ukázku nové live show, relevantní rozhovor, oficiální video nebo příspěvek, který je předmětem zprávy.
- Nepřidávat obecný profil, nesouvisející promo, fanouškovský reupload ani video pouze kvůli vizuálnímu zaplnění karty.
- Instagram a YouTube používat jako vložené médium; důležité tvrdé tvrzení musí stále splnit běžný důkazní standard.
- Pokud relevantní stabilní Instagram nebo YouTube odkaz neexistuje, ponechat `media` prázdné.

## Výstup

- Čeština.
- Tón je neutrální, stručný a informační. Text neoslovuje LIR, nepřikazuje další kroky a nevystupuje jako poradenský dokument.
- Celkem nejvýše 14 obsahových položek mimo sekci `lir_actions`.
- Položky se řadí podle významu, ale nepoužívají štítky TOP, MID ani LOW.
- Titulek jasně a věcně popisuje novinku; nepoužívá interní ani poradenské formulace.
- `summary` obsahuje 3 až 5 informačních vět rozdělených do nejvýše 4 krátkých odstavců: co se stalo, konkrétní důkaz nebo měřítko a nutný kontext.
- `why_it_matters`, `recommended_action` a `executive_summary` zůstávají pouze jako strojová pole kvůli kompatibilitě schématu a na webu se nezobrazují.
- `recommended_action` má neutrální hodnotu `Bez akce, pouze informační přehled`, pokud není potřeba interní technická poznámka pro automatizaci.
- `executive_summary` obsahuje 3 až 5 věcných informačních bodů bez doporučení.
- `competition` obsahuje zpravidla 2 až 5 položek.
- `festival_industry` obsahuje zpravidla 1 až 4 položky.
- `dnb_scene` obsahuje 2 až 4 nejsilnější scénové položky.
- `cz_sk` obsahuje 0 až 3 položky podle skutečné relevance.
- `audience_sentiment` obsahuje 2 až 3 položky; nejméně dvě musí vycházet z kvalifikovaných diskusí na `r/DnB`.
- `strategic_releases` obsahuje 0 až 2 položky.
- `lir_actions` zůstává prázdná; web tuto technickou sekci nezobrazuje.
- Od týdne 29 roku 2026 se vynucuje minimální pokrytí `dnb_scene` a `r/DnB`. Nedostatečný sběr je chyba běhu, ne omluva pro prázdnou sekci.
- Žádná výplň, obecné promo formulace ani duplicity z předchozího týdne bez nové informace.

## Publikační postup

1. Přečíst `AUTOMATION.md`, `schemas/briefing.schema.json`, aktuální `news/index.json` a nejméně čtyři poslední briefingy.
2. Vytvořit `news/YYYY-week_N.json` ve schématu verze 2. Číslo týdne odpovídá zpracovanému období, nikoli dni spuštění.
3. Přidat nový záznam na začátek `news/index.json`.
4. Zkontrolovat JSON, duplicity, data, odkazy a všechna povinná pole.
5. Provést kontrolu pokrytí: nejméně 2 položky v `dnb_scene`, nejméně 2 přímé odkazy na kvalifikované diskuse z `r/DnB` v `audience_sentiment` a záznam `Reddit r/DnB: hot + top/week` v `sources_scanned`.
6. Vytvořit větev `automation/briefing-YYYY-week-N`.
7. Zapsat pouze nový briefing a manifest.
8. Otevřít nedraftový pull request s názvem `Add DnB briefing YYYY week N`.
9. Workflow `.github/workflows/validate-briefing.yml` zkontroluje celý datový archiv.
10. Pull request zůstane připravený ke sloučení. Automatické sloučení vyžaduje samostatné schválení zápisových oprávnění.
11. Pokud validace selže, nic neobcházet a vrátit přesný seznam chyb.
