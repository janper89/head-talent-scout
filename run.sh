#!/bin/bash
# ============================================================
# HEAD Talent Scout — Quick Start
# ============================================================
# Spustí celou pipeline: scraping → analýza → dashboard
#
# Použití:
#   chmod +x run.sh
#   ./run.sh          # Plný běh
#   ./run.sh test     # Testovací režim (5 turnajů)
# ============================================================

set -e

MODE=${1:-"full"}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "🎾 HEAD Talent Scout Pipeline"
echo "================================"
echo "Režim: $MODE"
echo ""

# Kontrola prerequisites
if ! command -v python3 &> /dev/null; then
    echo "❌ python3 není nainstalován"
    exit 1
fi

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "❌ ANTHROPIC_API_KEY není nastaven"
    echo "   Spusť: export ANTHROPIC_API_KEY='sk-ant-...'"
    exit 1
fi

# Instalace závislostí
echo "📦 Kontroluji závislosti..."
pip3 install -q requests beautifulsoup4 anthropic Pillow pdf2image flask 2>/dev/null

# Vytvoř složky
mkdir -p data/tournaments data/results

if [ "$MODE" == "test" ]; then
    MAX_FLAG="--max 5"
    echo "🧪 Testovací režim — max 5 turnajů per kategorie"
else
    MAX_FLAG=""
    echo "🚀 Plný běh — všechny turnaje"
fi

# 1b. CLUB DIRECTORY (kontakty klubů)
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🏛️  FÁZE 1b: Adresář klubů (kontakty)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 clubs_scraper.py $MAX_FLAG || true

# 1. SCRAPING
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📥 FÁZE 1: Scraping turnajů z cztenis.cz"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 scraper.py --categories babytenis minitenis $MAX_FLAG

# Najdi nejnovější scrape soubor
SCRAPE_FILE=$(ls -t data/scrape_*.json 2>/dev/null | head -1)
if [ -z "$SCRAPE_FILE" ]; then
    echo "❌ Scraping nevytvořil žádný soubor"
    exit 1
fi
echo "📄 Scrape soubor: $SCRAPE_FILE"

# 2. ANALÝZA
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🤖 FÁZE 2: AI analýza výsledků"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 analyzer.py --input "$SCRAPE_FILE" $MAX_FLAG

# 3. DASHBOARD
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌐 FÁZE 3: Dashboard"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✅ Pipeline dokončena!"
echo ""
echo "Otevři dashboard:"
echo "   python3 server.py"
echo "   → http://localhost:8000/"
echo ""
