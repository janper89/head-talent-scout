"""
CTS OCR Test — Testování extrakce dat z turnajových výsledků cztenis.cz
========================================================================
Tento skript stáhne reálné výsledkové soubory (JPG + PDF) z webu ČTS
a pošle je do Claude API s vision, aby ověřil, zda dokáže spolehlivě
přečíst jména hráčů, výsledky a umístění.

Spuštění:
    pip install anthropic requests pdf2image Pillow
    export ANTHROPIC_API_KEY="sk-ant-..."
    python test_ocr_cts.py

(Na macOS pro pdf2image potřebuješ: brew install poppler)
"""

import anthropic
import base64
import requests
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# ============================================================
# KONFIGURACE — testovací turnaje
# ============================================================

TEST_TOURNAMENTS = {
    "babytenis_jpg": {
        "name": "Babytenis zima 2025 — Renáta Voráčová akademie",
        "category": "babytenis",
        "files": [
            {
                "url": "https://www.cztenis.cz/turnaj/906500/sezona/Z2526/soubor/20251129_175613.jpg",
                "filename": "skupina_ab.jpg",
                "description": "Skupiny A a B"
            },
            {
                "url": "https://www.cztenis.cz/turnaj/906500/sezona/Z2526/soubor/20251129_175533.jpg",
                "filename": "pavouk.jpg",
                "description": "Pavouk hlavní soutěž"
            },
        ]
    },
    "babytenis_pdf": {
        "name": "O POHÁR SK JC SPORT OPAVA — oranžový kurt",
        "category": "babytenis",
        "files": [
            {
                "url": "https://www.cztenis.cz/turnaj/906517/sezona/Z2526/soubor/TABULKA_A_V%C3%9DSLEDKY.pdf",
                "filename": "skupina_a.pdf",
                "description": "Skupina A — PDF"
            },
            {
                "url": "https://www.cztenis.cz/turnaj/906517/sezona/Z2526/soubor/KONE%C4%8CN%C3%81%20TABULKA%20TENIS%20(BODOV%C3%81N%C3%8D).pdf",
                "filename": "konecna_tabulka.pdf",
                "description": "Konečná tabulka s bodováním — PDF"
            },
        ]
    },
}

# ============================================================
# FUNKCE
# ============================================================

def download_file(url: str, filepath: Path) -> bool:
    """Stáhne soubor z URL."""
    try:
        print(f"  📥 Stahuji: {filepath.name} ...")
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        resp.raise_for_status()
        filepath.write_bytes(resp.content)
        size_kb = len(resp.content) / 1024
        print(f"     ✅ Staženo ({size_kb:.0f} KB)")
        return True
    except Exception as e:
        print(f"     ❌ Chyba: {e}")
        return False


def encode_image_to_base64(filepath: Path) -> str:
    """Zakóduje obrázek do base64."""
    return base64.standard_b64encode(filepath.read_bytes()).decode("utf-8")


def pdf_to_images(filepath: Path) -> list[Path]:
    """Převede PDF na PNG obrázky (jedna stránka = jeden obrázek)."""
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(str(filepath), dpi=200)
        image_paths = []
        for i, img in enumerate(images):
            img_path = filepath.parent / f"{filepath.stem}_page{i+1}.png"
            img.save(str(img_path), "PNG")
            image_paths.append(img_path)
            print(f"     📄 PDF stránka {i+1} → {img_path.name}")
        return image_paths
    except ImportError:
        print("     ⚠️  pdf2image není nainstalován. Spusť: pip install pdf2image")
        print("        Na macOS taky: brew install poppler")
        return []


def analyze_with_claude(client: anthropic.Anthropic, image_paths: list[Path], tournament_name: str) -> dict:
    """
    Pošle obrázky turnajových výsledků do Claude API a extrahuje strukturovaná data.
    """
    
    # Připrav content s obrázky
    content = []
    for img_path in image_paths:
        suffix = img_path.suffix.lower()
        if suffix in (".jpg", ".jpeg"):
            media_type = "image/jpeg"
        elif suffix == ".png":
            media_type = "image/png"
        else:
            print(f"     ⚠️  Přeskakuji neznámý formát: {suffix}")
            continue
            
        b64 = encode_image_to_base64(img_path)
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": b64,
            }
        })
    
    # Přidej textový prompt
    content.append({
        "type": "text",
        "text": f"""Analyzuj tyto výsledky z českého tenisového turnaje: "{tournament_name}"

Jedná se o kategorii babytenis nebo minitenis (děti cca 6-10 let).

ÚKOL: Extrahuj z obrázků všechna dostupná data ve strukturovaném JSON formátu.

Pro KAŽDÉHO hráče, kterého najdeš, vrať:
- "jmeno": celé jméno hráče (příjmení + křestní jméno, jak je v tabulce)
- "klub": název klubu (pokud je uveden)
- "skupina": ve které skupině hrál (A, B, C...)
- "umisteni_skupina": pořadí ve skupině (1., 2., 3....)
- "umisteni_celkove": celkové umístění v turnaji (pokud je dostupné)
- "zapasy": seznam zápasů ve formátu [{{"protivnik": "...", "vysledek": "...", "vyhra": true/false}}]

Vrať POUZE validní JSON, žádný další text. Formát:
{{
  "turnaj": "{tournament_name}",
  "pocet_hracu": číslo,
  "hraci": [
    {{
      "jmeno": "...",
      "klub": "...",
      "skupina": "...",
      "umisteni_skupina": číslo,
      "umisteni_celkove": číslo nebo null,
      "zapasy": [
        {{"protivnik": "...", "vysledek": "...", "vyhra": true/false}}
      ]
    }}
  ]
}}

DŮLEŽITÉ:
- Přepiš jména PŘESNĚ jak jsou v tabulce, včetně diakritiky
- Pokud je něco nečitelné, napiš "NEČITELNÉ" místo vymýšlení
- Nedomýšlej data která v obrázcích nejsou
"""
    })
    
    print(f"\n  🤖 Posílám do Claude API ({len(image_paths)} obrázků)...")
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[
            {"role": "user", "content": content}
        ]
    )
    
    # Parsuj odpověď
    raw_text = response.content[0].text
    
    # Zkus parsovat JSON
    try:
        # Odstraň případné markdown backticky
        clean = raw_text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
            clean = clean.rsplit("```", 1)[0]
        data = json.loads(clean)
        return {
            "success": True,
            "data": data,
            "raw_response": raw_text,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"JSON parse error: {e}",
            "raw_response": raw_text,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }


# ============================================================
# HLAVNÍ PROGRAM
# ============================================================

def main():
    print("=" * 70)
    print("🎾 CTS OCR TEST — Extrakce turnajových výsledků přes Claude API")
    print("=" * 70)
    
    # Ověř API klíč
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("\n❌ ANTHROPIC_API_KEY není nastaven!")
        print("   Spusť: export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)
    
    client = anthropic.Anthropic(api_key=api_key)
    
    # Vytvoř pracovní adresář
    work_dir = Path("cts_ocr_test_data")
    work_dir.mkdir(exist_ok=True)
    
    results = {}
    
    for test_id, tournament in TEST_TOURNAMENTS.items():
        print(f"\n{'─' * 60}")
        print(f"📋 TURNAJ: {tournament['name']}")
        print(f"   Kategorie: {tournament['category']}")
        print(f"{'─' * 60}")
        
        # 1. Stáhni soubory
        downloaded_files = []
        for file_info in tournament["files"]:
            filepath = work_dir / file_info["filename"]
            if filepath.exists():
                print(f"  ✅ {filepath.name} již existuje, přeskakuji stahování")
                downloaded_files.append((filepath, file_info))
            elif download_file(file_info["url"], filepath):
                downloaded_files.append((filepath, file_info))
        
        if not downloaded_files:
            print("  ❌ Žádné soubory se nepodařilo stáhnout, přeskakuji")
            continue
        
        # 2. Připrav obrázky (PDF → PNG konverze)
        image_paths = []
        for filepath, file_info in downloaded_files:
            if filepath.suffix.lower() == ".pdf":
                print(f"\n  🔄 Konvertuji PDF → PNG: {filepath.name}")
                png_paths = pdf_to_images(filepath)
                image_paths.extend(png_paths)
            else:
                image_paths.append(filepath)
        
        if not image_paths:
            print("  ❌ Žádné obrázky k analýze")
            continue
        
        # 3. Pošli do Claude API
        result = analyze_with_claude(client, image_paths, tournament["name"])
        results[test_id] = result
        
        # 4. Zobraz výsledky
        print(f"\n  📊 VÝSLEDKY:")
        print(f"     Tokeny: {result['input_tokens']} input + {result['output_tokens']} output")
        
        if result["success"]:
            data = result["data"]
            print(f"     ✅ JSON úspěšně parsován!")
            print(f"     Počet nalezených hráčů: {data.get('pocet_hracu', '?')}")
            
            # Výpis prvních 5 hráčů jako ukázka
            hraci = data.get("hraci", [])
            print(f"\n     {'─' * 50}")
            print(f"     Ukázka prvních {min(5, len(hraci))} hráčů:")
            for i, hrac in enumerate(hraci[:5]):
                jmeno = hrac.get("jmeno", "?")
                klub = hrac.get("klub", "?")
                sk = hrac.get("skupina", "?")
                um = hrac.get("umisteni_celkove") or hrac.get("umisteni_skupina", "?")
                print(f"     {i+1}. {jmeno} ({klub}) — sk. {sk}, umístění: {um}")
        else:
            print(f"     ⚠️  JSON parsing selhal: {result['error']}")
            print(f"     Raw odpověď (prvních 500 znaků):")
            print(f"     {result['raw_response'][:500]}")
    
    # 5. Ulož kompletní výsledky
    output_file = work_dir / f"ocr_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    # Serializuj výsledky (bez raw_response pro čitelnost)
    export_data = {}
    for test_id, result in results.items():
        export_data[test_id] = {
            "success": result["success"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "data": result.get("data"),
            "error": result.get("error"),
        }
    
    output_file.write_text(json.dumps(export_data, ensure_ascii=False, indent=2))
    print(f"\n{'=' * 70}")
    print(f"💾 Kompletní výsledky uloženy: {output_file}")
    print(f"{'=' * 70}")
    
    # 6. Souhrn
    print(f"\n📈 SOUHRN TESTU:")
    total_players = 0
    for test_id, result in results.items():
        status = "✅" if result["success"] else "❌"
        players = len(result.get("data", {}).get("hraci", []))
        total_players += players
        cost_input = result["input_tokens"] * 0.003 / 1000  # Sonnet pricing
        cost_output = result["output_tokens"] * 0.015 / 1000
        cost_total = cost_input + cost_output
        print(f"   {status} {test_id}: {players} hráčů, ${cost_total:.4f}")
    
    print(f"\n   Celkem hráčů extrahováno: {total_players}")
    print(f"\n   💡 Pokud test uspěl, máme základ pro automatický ranking pipeline!")


if __name__ == "__main__":
    main()
