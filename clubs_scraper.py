"""
CTS Club Directory Scraper
==========================
Scrapes public club contact details from cztenis.cz club directory.

Output: data/clubs_directory.json
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from utils import normalize_text


BASE = "https://cztenis.cz"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def get_soup(url: str, retries: int = 3):
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            r.encoding = "utf-8"
            return BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print(f"   ⚠️  {url} attempt {attempt+1}/{retries} failed: {e}")
            time.sleep(1.5)
    return None


def extract_mailto(a_tag):
    href = a_tag.get("href", "") if a_tag else ""
    if href.startswith("mailto:"):
        return href.split("mailto:", 1)[1].strip()
    return ""


def parse_club_detail(url: str) -> dict:
    soup = get_soup(url)
    if not soup:
        return {}

    text = soup.get_text("\n", strip=True)

    # Best-effort extraction from page structure
    name = ""
    h = soup.find(["h1", "h2"])
    if h:
        name = h.get_text(strip=True)

    email = ""
    mail = soup.select_one('a[href^="mailto:"]')
    if mail:
        email = extract_mailto(mail)

    phone = ""
    tel = soup.select_one('a[href^="tel:"]')
    if tel:
        phone = tel.get("href", "").split("tel:", 1)[1].strip()

    web = ""
    # find a plausible external link
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if href.startswith("http") and "cztenis" not in href:
            web = href
            break

    address = ""
    # heuristic: look for lines that contain street + city patterns
    for line in text.split("\n"):
        if any(ch.isdigit() for ch in line) and ("," in line or " " in line) and len(line) > 10:
            address = line
            break

    return {
        "club_name": name,
        "email": email,
        "phone": phone,
        "web": web,
        "address": address,
        "detail_url": url,
        "club_name_norm": normalize_text(name),
    }


def scrape_directory(max_clubs: int | None = None) -> dict:
    index_url = f"{BASE}/adresar-klubu"
    print(f"🏛️  Scraping adresáře klubů: {index_url}")

    soup = get_soup(index_url)
    if not soup:
        raise RuntimeError("Failed to load club directory index")

    # collect detail links (e.g. /adresar-klubu/52)
    links = []
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if not href:
            continue
        m = re.match(r"^/adresar-klubu/\d+", href)
        if m:
            full = urljoin(BASE, href)
            links.append(full)

    # dedupe while keeping order
    seen = set()
    unique_links = []
    for l in links:
        if l in seen:
            continue
        seen.add(l)
        unique_links.append(l)

    if max_clubs:
        unique_links = unique_links[:max_clubs]

    clubs = []
    for i, url in enumerate(unique_links, 1):
        print(f"   [{i}/{len(unique_links)}] {url}")
        d = parse_club_detail(url)
        if d and d.get("club_name"):
            clubs.append(d)
        time.sleep(0.3)

    # map by normalized club name for fast lookup
    by_name_norm = {c["club_name_norm"]: c for c in clubs if c.get("club_name_norm")}

    return {
        "generated_at": datetime.now().isoformat(),
        "source": index_url,
        "total_clubs": len(clubs),
        "clubs": clubs,
        "by_name_norm": by_name_norm,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="CTS club directory scraper")
    parser.add_argument("--out", default="data/clubs_directory.json")
    parser.add_argument("--max", type=int, default=None)
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = scrape_directory(max_clubs=args.max)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"✅ Uloženo: {out_path}")


if __name__ == "__main__":
    main()

