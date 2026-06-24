# DnB briefing

Statický briefing drum & bass novinek. Web se publikuje z adresáře `docs/` přes GitHub Pages.

## Webová adresa

Po zapnutí GitHub Pages pro repozitář bude briefing dostupný na:

<https://dozikur.github.io/dnb-briefing/>

Stránka obsahuje service worker, takže po první online návštěvě zůstane poslední načtená verze dostupná i offline ve stejném prohlížeči a na stejné adrese.

## Publikace na GitHub Pages

Workflow `.github/workflows/pages.yml` nasazuje obsah složky `docs/` na GitHub Pages při pushi do větví `main`, `master` nebo `work`, případně ručním spuštěním z GitHub Actions.
