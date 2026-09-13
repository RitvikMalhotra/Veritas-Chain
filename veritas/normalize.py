"""Canonical-key functions. Two mentions with the same key become the same node (exact-match entity resolution)."""

import re
import unicodedata

# Leading titles dropped from person names, so "Shri Rajesh Kumar" == "Rajesh Kumar".
_HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "shri", "sri", "smt"}

# Only these company suffix variants are unified; everything else must match exactly.
_ORG_TOKEN_MAP = {"private": "pvt", "limited": "ltd"}

_INDIAN_MOBILE = re.compile(r"[6-9]\d{9}")
_PLATE_STANDARD = re.compile(r"[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{4}")  # e.g. MH12AB1234, DL3CAB1234
_PLATE_BH_SERIES = re.compile(r"\d{2}BH\d{4}[A-Z]{1,2}")  # e.g. 22BH1234AA
_IFSC = re.compile(r"[A-Z]{4}0[A-Z0-9]{6}")
_ACCOUNT_NUMBER = re.compile(r"\d{9,18}")


def _tokens(text: str) -> list[str]:
    # Unicode-fold, lowercase, split on anything that isn't a letter or digit.
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).lower())


def _join(tokens: list[str], original: str) -> str:
    if not tokens:
        raise ValueError(f"nothing left to build a key from in {original!r}")
    return "_".join(tokens)


def text_key(text: str) -> str:
    """Generic key: 'Hotel Sai-Palace ' -> 'hotel_sai_palace'."""
    return _join(_tokens(text), text)


def person_key(name: str) -> str:
    tokens = _tokens(name)
    while tokens and tokens[0] in _HONORIFICS:  # strip leading titles only
        tokens.pop(0)
    return _join(tokens, name)


def organization_key(name: str) -> str:
    return _join([_ORG_TOKEN_MAP.get(t, t) for t in _tokens(name)], name)


def location_key(name: str, city: str | None) -> str:
    # City is part of the key so "Station Road, Pune" never merges with "Station Road, Nagpur".
    return text_key(name) if not city else f"{text_key(name)}:{text_key(city)}"


def phone_key(raw: str) -> str:
    """Normalize an Indian mobile number to E.164: '098765 43210' -> '+919876543210'."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 14 and digits.startswith("0091"):
        digits = digits[4:]
    elif len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not _INDIAN_MOBILE.fullmatch(digits):
        raise ValueError(f"not a valid Indian mobile number: {raw!r}")
    return "+91" + digits


def plate_key(raw: str) -> str:
    """Normalize a vehicle plate: 'mh-12-ab-1234' -> 'MH12AB1234'."""
    plate = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if not (_PLATE_STANDARD.fullmatch(plate) or _PLATE_BH_SERIES.fullmatch(plate)):
        raise ValueError(f"not a valid Indian registration number: {raw!r}")
    return plate


def ifsc_key(raw: str) -> str:
    code = raw.strip().upper()
    if not _IFSC.fullmatch(code):
        raise ValueError(f"not a valid IFSC code: {raw!r}")
    return code


def account_number_key(raw: str) -> str:
    digits = re.sub(r"[\s-]", "", raw)
    if not _ACCOUNT_NUMBER.fullmatch(digits):
        raise ValueError(f"account number must be 9-18 digits: {raw!r}")
    return digits
