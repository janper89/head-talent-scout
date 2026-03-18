import re
import unicodedata


def normalize_text(value: str) -> str:
    """
    Stable normalization for IDs and matching.
    - lowercase
    - strip diacritics
    - collapse whitespace
    - keep letters/numbers/space only
    """
    if value is None:
        return ""
    value = str(value).strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_name(name: str) -> str:
    return normalize_text(name)


def parse_birth_year(value: str):
    """
    Extracts a 4-digit year if present, else None.
    Accepts inputs like '2018', 'nar. 2018', '18' (ignored), etc.
    """
    if not value:
        return None
    m = re.search(r"(19\d{2}|20\d{2})", str(value))
    if not m:
        return None
    return int(m.group(1))


def make_player_id(name: str, birth_year) -> str:
    by = parse_birth_year(birth_year) if not isinstance(birth_year, int) else birth_year
    if not by:
        return ""
    return f"{normalize_name(name)}_{by}"

