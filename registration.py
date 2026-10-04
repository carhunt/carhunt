"""
Registration state for each listing, so a car registered outside Telangana can be
flagged: re-registering it here costs Telangana lifetime tax on the original
invoice (several lakh on a luxury car), and tax paid in the other state is not
credited.

Cars24, Spinny, Big Boy Toyz and Royal Drive put the RTO in their listing data.
CarWale and CarDekho only show the plate on the car's own page, so those pages
are fetched once per car and the result cached in reg_cache.json. Only the
state + RTO prefix ("MH03") is kept, never the full plate.

Pre-2014 cars from Telangana districts still carry AP codes. Those codes are
Telangana vehicles and owe no re-registration tax, so they count as TS here.
"""
import json
import os
import re

import carhunt as ch

CACHE = os.path.join(ch.HERE, "reg_cache.json")

# Old Andhra Pradesh RTO codes that belong to Telangana districts (pre-June 2014)
AP_TELANGANA = {1, 9, 10, 11, 12, 13, 14, 15, 20, 22, 23, 24, 25, 28, 29, 36}

STATE_NAMES = {
    "TELANGANA": "TS", "ANDHRA PRADESH": "AP", "MAHARASHTRA": "MH",
    "KARNATAKA": "KA", "TAMIL NADU": "TN", "KERALA": "KL", "DELHI": "DL",
    "HARYANA": "HR", "UTTAR PRADESH": "UP", "GUJARAT": "GJ", "RAJASTHAN": "RJ",
    "PUNJAB": "PB", "WEST BENGAL": "WB", "MADHYA PRADESH": "MP",
    "CHANDIGARH": "CH", "GOA": "GA", "JHARKHAND": "JH", "BIHAR": "BR",
    "ODISHA": "OD", "UTTARAKHAND": "UK",
}

PREFIX = re.compile(r"\b([A-Z]{2})[\s-]?(\d{1,2})")


def prefix(text):
    """'MH 04 AB 1234' / 'TG16' / 'Maharashtra' -> 'MH04' / 'TG16' / 'MH'."""
    t = str(text or "").upper().strip()
    if not t:
        return ""
    if t in STATE_NAMES:
        return STATE_NAMES[t]
    m = PREFIX.search(t)
    if m:
        return f"{m.group(1)}{int(m.group(2)):02d}"
    return t[:2] if re.fullmatch(r"[A-Z]{2}", t[:2]) else ""


def classify(code):
    """-> ('ts' | 'other' | 'unknown', short label for the page)."""
    if not code:
        return "unknown", ""
    state = code[:2]
    if state in ("TS", "TG"):
        return "ts", code
    if state == "AP" and code[2:].isdigit() and int(code[2:]) in AP_TELANGANA:
        return "ts", f"{code} (old Telangana code)"
    return "other", code


def _load():
    try:
        return json.load(open(CACHE))
    except (OSError, ValueError):
        return {}


def _from_page(url):
    page = ch.get(url)
    if "carwale.com" in url:
        m = re.search(r'"registrationNumber":"([^"]*)"', ch.rsc(page))
        return prefix(m.group(1)) if m else ""
    if "cardekho.com" in url:
        m = re.search(r'"(?:regNo|registrationNumber|rtoCode|rto|registrationNo)"'
                      r'\s*:\s*"([A-Za-z]{2}[\s-]?\d{1,2}[^"]*)"', page)
        return prefix(m.group(1)) if m else ""
    return ""


def enrich(groups):
    """Fill c['rto'] and c['reg'] for every car in place; fetch what is missing."""
    cache = _load()
    fetched = 0
    for _key, _cfg, cars in groups:
        for c in cars:
            code = prefix(c.get("rto"))
            if not code and c["url"] in cache:
                code = cache[c["url"]]
            if not code and re.search(r"carwale\.com|cardekho\.com", c["url"]):
                try:
                    code = _from_page(c["url"])
                except Exception:                    # noqa: BLE001
                    code = None                      # retry next run
                if code is not None:
                    cache[c["url"]] = code
                    fetched += 1
            c["rto"] = code or ""
            c["reg"], c["reg_label"] = classify(code or "")
    if fetched:
        with open(CACHE, "w") as fh:
            json.dump(cache, fh, indent=0, sort_keys=True)
    return fetched
