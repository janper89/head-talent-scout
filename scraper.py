"""
CTS Tournament Scraper
======================
Scrapuje turnaje z cztenis.cz pro kategorie minitenis, babytenis a mladší žactvo.
Pro každý turnaj stahuje:
  1. Seznam přihlášených hráčů (HTML tabulka z /informace)
  2. Výsledkové soubory (JPG/PDF z /vysledky)

Spuštění:
    pip3 install requests beautifulsoup4 anthropic Pillow pdf2image
    brew install poppler  # macOS
    export ANTHROPIC_API_KEY="sk-ant-..."
    python3 scraper.py
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re
import time
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin, unquote

# ============================================================
# KONFIGURACE
# ============================================================

BASE_URL = "https://www.cztenis.cz"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

CATEGORIES = {
    "minitenis": {
        "url": f"{BASE_URL}/minitenis/jednotlivci",
        "label": "Mini tenis",
        "age_range": "do 8 let",
    },
    "babytenis": {
        "url": f"{BASE_URL}/babytenis/jednotlivci",
        "label": "Baby tenis + střední",
        "age_range": "8-10 let",
    },
    "mladsi_zactvo": {
        "url": f"{BASE_URL}/mladsi-zactvo/jednotlivci",
        "label": "Mladší žactvo",
        "age_range": "10-12 let",
    },
}

DATA_DIR = Path("data")
TOURNAMENTS_DIR = DATA_DIR / "tournaments"
RESULTS_DIR = DATA_DIR / "results"

# ============================================================
# SCRAPING FUNCTIONS
# ============================================================

def get_page(url: str, retries: int = 3):
    """Stáhne stránku a vrátí BeautifulSoup objekt."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            print(f"     ⚠️  Pokus {attempt+1}/{retries} selhal: {e}")
            time.sleep(2)
    return None


def scrape_tournament_list(category, season="Z2526"):
    """
    Scrapuje seznam turnajů z dané kategorie a sezóny.
    Vrací seznam turnajů s kódem, datem, pořadatelem a URL.
    """
    cat_info = CATEGORIES[category]
    url = cat_info["url"]
    
    print(f"\n📋 Scrapuji seznam turnajů: {cat_info['label']} ({season})")
    
    soup = get_page(url)
    if not soup:
        print("   ❌ Nepodařilo se načíst stránku")
        return []
    
    tournaments = []
    
    # Najdi tabulku s turnaji
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            
            # Extrahuj data z řádku
            datum = cells[0].get_text(strip=True)
            kod = cells[1].get_text(strip=True)
            poradatel = cells[2].get_text(strip=True)
            
            # Najdi odkazy na informace a výsledky
            info_link = None
            results_link = None
            for link in row.find_all("a"):
                href = link.get("href", "")
                text = link.get_text(strip=True)
                if "informace" in href:
                    info_link = urljoin(BASE_URL, href)
                elif "vysledky" in href:
                    results_link = urljoin(BASE_URL, href)
            
            if kod and datum:
                tournaments.append({
                    "kod": kod,
                    "datum": datum,
                    "poradatel": poradatel,
                    "kategorie": category,
                    "sezona": season,
                    "info_url": info_link,
                    "results_url": results_link,
                })
    
    print(f"   ✅ Nalezeno {len(tournaments)} turnajů")
    # Kolik má výsledky
    with_results = sum(1 for t in tournaments if t["results_url"])
    print(f"   📊 Z toho {with_results} s nahranými výsledky")
    
    return tournaments


def scrape_player_roster(tournament):
    """
    Scrapuje seznam přihlášených hráčů z informační stránky turnaje.
    Vrací seznam hráčů s jménem, rokem narození, klubem atd.
    """
    if not tournament.get("info_url"):
        return []
    
    soup = get_page(tournament["info_url"])
    if not soup:
        return []
    
    players = []
    current_section = "hlavni"  # hlavni / nahradnici / odstraneni
    
    # Hledáme všechny tabulky na stránce
    for table in soup.find_all("table"):
        # Zjisti sekci podle nadpisu nad tabulkou
        prev = table.find_previous(["h2", "h3", "h4", "b", "strong"])
        if prev:
            section_text = prev.get_text(strip=True).lower()
            if "náhrad" in section_text:
                current_section = "nahradnici"
            elif "odstraněn" in section_text or "odhlášen" in section_text:
                current_section = "odstraneni"
            elif "hlavní" in section_text:
                current_section = "hlavni"
        
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            
            # Typická struktura: # | Jméno | nar. | klub | poznámka | datum přihlášení
            poradi = cells[0].get_text(strip=True)
            jmeno = cells[1].get_text(strip=True)
            narozeni = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            klub = cells[3].get_text(strip=True) if len(cells) > 3 else ""
            poznamka = cells[4].get_text(strip=True) if len(cells) > 4 else ""
            
            # Filtruj hlavičky a prázdné řádky
            if not jmeno or jmeno.lower() in ("příjmení a jméno", "jméno", "#"):
                continue
            if not re.match(r"\d", poradi) and poradi != "":
                continue
                
            players.append({
                "jmeno": jmeno,
                "rok_narozeni": narozeni,
                "klub": klub,
                "sekce": current_section,
                "poznamka": poznamka,
                "turnaj_kod": tournament["kod"],
            })
    
    return players


def scrape_result_files(tournament):
    """
    Stáhne výsledkové soubory (JPG/PDF) z výsledkové stránky turnaje.
    """
    if not tournament.get("results_url"):
        return []
    
    soup = get_page(tournament["results_url"])
    if not soup:
        return []
    
    files = []
    
    # Najdi všechny odkazy na soubory výsledků
    for link in soup.find_all("a"):
        href = link.get("href", "")
        if "/soubor/" in href:
            file_url = urljoin(BASE_URL, href)
            filename = unquote(href.split("/soubor/")[-1])
            label = link.get_text(strip=True)
            
            files.append({
                "url": file_url,
                "filename": filename,
                "label": label,
                "turnaj_kod": tournament["kod"],
            })
    
    return files


def download_file(url, filepath):
    """Stáhne soubor z URL."""
    if filepath.exists():
        return True
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"     ❌ Stahování selhalo: {e}")
        return False


# ============================================================
# MAIN PIPELINE
# ============================================================

def run_scraper(categories=None, season="Z2526", max_tournaments=None):
    """
    Hlavní scraping pipeline.
    
    Args:
        categories: Seznam kategorií ke scrapování (default: všechny)
        season: Sezóna (Z2526 = zima 2025/26, L2025 = léto 2025)
        max_tournaments: Omezení počtu turnajů (pro testování)
    """
    if categories is None:
        categories = list(CATEGORIES.keys())
    
    DATA_DIR.mkdir(exist_ok=True)
    TOURNAMENTS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    all_tournaments = []
    all_players = []
    all_files = []
    
    print("=" * 70)
    print("🎾 CTS SCRAPER — Sběr turnajových dat z cztenis.cz")
    print(f"   Sezóna: {season}")
    print(f"   Kategorie: {', '.join(categories)}")
    print("=" * 70)
    
    for cat in categories:
        # 1. Scrape tournament list
        tournaments = scrape_tournament_list(cat, season)
        
        if max_tournaments:
            tournaments = tournaments[:max_tournaments]
        
        for i, t in enumerate(tournaments):
            if not t.get("info_url") and not t.get("results_url"):
                continue
                
            print(f"\n   [{i+1}/{len(tournaments)}] {t['kod']} — {t['poradatel']}")
            
            # 2. Scrape player roster
            players = scrape_player_roster(t)
            hlavni = [p for p in players if p["sekce"] == "hlavni"]
            print(f"      👥 Hráči: {len(hlavni)} v hlavní soutěži")
            t["players"] = players
            all_players.extend(players)
            
            # 3. Scrape result file links
            files = scrape_result_files(t)
            print(f"      📄 Výsledkové soubory: {len(files)}")
            
            # 4. Download result files
            for f in files:
                fpath = RESULTS_DIR / t["kod"] / f["filename"]
                if download_file(f["url"], fpath):
                    f["local_path"] = str(fpath)
                    print(f"         📥 {f['filename']}")
            
            t["result_files"] = files
            all_files.extend(files)
            all_tournaments.append(t)
            
            # Rate limiting
            time.sleep(0.5)
    
    # Uložení dat
    output = {
        "scraped_at": datetime.now().isoformat(),
        "season": season,
        "categories": categories,
        "stats": {
            "tournaments": len(all_tournaments),
            "players": len(all_players),
            "result_files": len(all_files),
        },
        "tournaments": all_tournaments,
    }
    
    output_file = DATA_DIR / f"scrape_{season}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_file.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    
    print(f"\n{'=' * 70}")
    print(f"✅ SCRAPING DOKONČEN")
    print(f"   Turnajů: {len(all_tournaments)}")
    print(f"   Hráčů (přihlášky): {len(all_players)}")
    print(f"   Výsledkových souborů: {len(all_files)}")
    print(f"   Data uložena: {output_file}")
    print(f"{'=' * 70}")
    
    return output


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="CTS Tournament Scraper")
    parser.add_argument("--categories", nargs="+", 
                       choices=list(CATEGORIES.keys()),
                       help="Kategorie ke scrapování")
    parser.add_argument("--season", default="Z2526",
                       help="Sezóna (Z2526, L2025...)")
    parser.add_argument("--max", type=int, default=None,
                       help="Max počet turnajů per kategorie (pro test)")
    
    args = parser.parse_args()
    
    run_scraper(
        categories=args.categories,
        season=args.season,
        max_tournaments=args.max,
    )
