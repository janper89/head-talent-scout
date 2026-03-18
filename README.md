# HEAD Talent Scout (CZ) — mini/baby/U12 scouting z cztenis.cz

Lokální pipeline pro scouting talentů v mini tenisu, baby tenisu a (sekundárně) U12 na základě veřejných výsledků z `cztenis.cz`.

- **Zdroj dat**: `cztenis.cz` (web scraping, žádné oficiální API)
- **Extrakce výsledků**: Claude API (vision) — OCR + strukturovaný JSON výstup
- **Výstup**: lokální JSON data + HTML dashboard na `localhost`

> Projekt je navržený pro MVP běh **lokálně** (na notebooku), s plánem rozšíření na automatické běhy a alerty (Tier 1/2/3), ELO rating a workflow „schválit/zamítnout/odesláno“.

---

## Rychlý start

### 1) Požadavky

- **Python 3**
- **ANTHROPIC_API_KEY** (Claude API)
- Pro analýzu PDF (`pdf2image`): **Poppler**
  - macOS: `brew install poppler`

### 2) Spuštění celé pipeline

```bash
chmod +x run.sh
export ANTHROPIC_API_KEY="sk-ant-..."

./run.sh        # plný běh
./run.sh test   # test mód (omezení na 5 turnajů / kategorii)
```

### 3) Otevření dashboardu

Po doběhnutí pipeline:

```bash
python3 server.py
```

Otevři `http://localhost:8000/`.

Poznámka: běh přes `server.py` je důležitý pro sekci **Tipy** (umožní ukládat úpravy textů, zamítat a označovat „odesláno“ a zapisovat změny do JSON).

---

## Co pipeline dělá (dnes)

### Fáze 1 — Scraper (`scraper.py`)

Scrapuje seznam turnajů a pro každý turnaj:

- **Přihlášky hráčů** z HTML (`/informace`)
  - jméno, ročník narození, klub, sekce (hlavní / náhradníci / odstranění)
- **Výsledkové soubory** (`/vysledky`)
  - JPG/PDF (stahuje lokálně)

Výstup: `data/scrape_<SEASON>_<YYYYMMDD_HHMMSS>.json` + stažené soubory v `data/results/<KOD_TURNAJE>/...`

### Fáze 2 — AI Analyzer (`analyzer.py`)

- Načte `scrape_*.json`
- Pro každý turnaj pošle výsledkové soubory do Claude (vision)
- Použije **roster** (přihlášky) jako cross‑referenci pro přesnější přiřazení jmen
- Očekává od modelu validní JSON s `konecne_poradi`
- Z těchto dat sestaví **žebříček** (aktuálně bodový systém)

Výstupy:

- `data/analysis_<YYYYMMDD_HHMMSS>.json` (raw výsledky z AI pro každý turnaj)
- `data/ranking.json` (agregovaný žebříček)
- `data/dashboard_data.json` (data pro dashboard)

### Fáze 3 — Dashboard (`dashboard.html`)

Statický HTML dashboard, který načítá `data/dashboard_data.json` a zobrazuje:

- žebříček hráčů
- filtry (kategorie / region / search)
- detail hráče (modal) + historie turnajů

---

## Konfigurace (důležité vědět)

- **Sezóna** je v kódu defaultně `Z2526` (zima 2025/26). (V `scraper.py` je parametr `--season`.)
- `run.sh` v plném běhu scrapuje kategorie: `babytenis` + `minitenis` (U12 je v `scraper.py` připravené jako `mladsi_zactvo`).
- `run.sh` při každém běhu zkusí doinstalovat závislosti přes `pip3 install ...` (rychlé MVP řešení).

---

## Architektura dat (MVP)

### `data/scrape_*.json`

- metadata (`scraped_at`, `season`, `categories`, `stats`)
- `tournaments[]`: pro každý turnaj `kod`, `datum`, `poradatel`, `kategorie`, `info_url`, `results_url`, `players[]`, `result_files[]`

### `data/analysis_*.json`

Seznam výsledků pro turnaje:

- `success` / `error`
- `data`: JSON vrácený modelem (hlavně `konecne_poradi[]`)
- `tokens`: spotřeba tokenů

### `data/ranking.json`

Agregovaný žebříček (aktuálně bodový):

- `ranking[]`: hráč, klub, ročník, `body_celkem`, soupis turnajů, W/L

---

## Bezpečnost, etika, GDPR (MVP)

- Zpracováváme **veřejně dostupná** data z `cztenis.cz`.
- **Rodiče nekontaktujeme** (kontakty nejsou k dispozici a nebudou scrapované).
- Oslovení jde přes **kontakt klubu/trenéra** z veřejného adresáře klubů (plánovaná část).
- V MVP se maily pouze **generují jako návrh** a šéf je **odesílá ručně** ze svého Gmailu.

---

## Roadmap (nejbližší implementace)

### 1) ELO rating (mini/baby bez oficiálního žebříčku)

- Přechod z bodového žebříčku na **ELO** (nebo paralelně: body + ELO).
- Váha turnajů (koeficienty): **MČR > A > B > C > D**.
- Umět fungovat i bez detailního skóre (fallback přes pořadí / odvozené „zápasy“).

### 2) Alert systém (2× měsíčně)

Běh v termínech **1. a 3. pondělí v měsíci**:

- **Tier 1 (Top talent)**: 2× 1.–2. místo v posledních 60 dnech (+ win rate, pokud je)
- **Tier 2 (Rising star)**: 2× 1.–4. místo / nebo „porazil Tier 1“
- **Tier 3 (Na radaru)**: 5+ turnajů v sezóně + konzistence v horní polovině

Výstup: seznam tipů + návrh mailu pro klub/trenéra.

### 3) Kontakty klubů (scraping adresáře)

- Scraper pro `cztenis.cz` adresář klubů → mapa `klub → email/telefon/kontakt`.
- Doplnění příjemce do návrhů mailů.

### 4) Schvalovací workflow v dashboardu

- Tipy: **pending / rejected / sent**
- Tlačítka: **Schválit / Zamítnout / Upravit text / Označit odesláno**
- Persistovat `tips_sent.json`, aby nedošlo k dvojímu oslovení v rámci sezóny.

### 5) Fáze 2: poloautomatické odesílání (Gmail)

- Integrace přes Gmail API (OAuth) až po právním ok.

### 6) Multi‑brand (white‑label)

Základní data (turnaje, hráči, ELO, tipy) držet brand‑agnostic a texty / podpisy / benefity řešit přes konfig.

---

## Pro šéfa: checklist 1. a 3. pondělí

1) Spusť pipeline:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
./run.sh
```

2) Otevři dashboard:

```bash
python3 server.py
```

3) V dashboardu otevři **Tipy**:
- uprav text (pokud chceš)
- **Zamítnout** nebo **Odesláno**

Systém si pamatuje „odesláno“ v `data/tips_sent.json`, takže další běh už stejného hráče nenabídne.

### Automatizace (volitelné, lokálně přes cron)

Wrapper, který pustí pipeline jen v **1. a 3. pondělí**:

```bash
python3 scheduled_run.py
```

---

## Troubleshooting

### `ANTHROPIC_API_KEY není nastaven`

Nastav env proměnnou:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### PDF analýza nefunguje

`pdf2image` vyžaduje Poppler:

```bash
brew install poppler
```

---

## Soubory v repu

- `scraper.py` — scraping turnajů, přihlášek, výsledků (JPG/PDF download)
- `clubs_scraper.py` — scraping adresáře klubů (kontakty) → `data/clubs_directory.json`
- `analyzer.py` — Claude vision extrakce + žebříček + ELO + tipy → JSON výstupy v `data/`
- `dashboard.html` — statický dashboard (načítá `data/dashboard_data.json`)
- `server.py` — lokální server + API pro workflow tipů (persistuje změny do JSON)
- `scheduled_run.py` — wrapper pro běh v 1. a 3. pondělí
- `run.sh` — „one‑command“ pipeline pro MVP
- `data/` — výstupy pipeline
- `cts_ocr_test_data/`, `test_ocr_cts.py` — testovací data pro OCR/vision (pokud používané)

