"""Deal scoring for carhunt listings.

The score answers one question: is this car cheap for what it is?

There is no public price index for Indian used cars, so the baseline is built
from two anchors and the answer is deliberately shown with its working:

  1. an approximate on-road-when-new price per model (APPROX_NEW, in rupees),
  2. a retention curve for age, adjusted for whether the odometer is ahead of
     or behind the ~12,000 km/year an Indian private car typically covers.

The anchor alone carries systematic bias, so the result is then recentred on
the median asking ratio of comparable listings - per model where the list holds
three or more of that model, otherwise across the search group. That recentring
is what makes the number mean "cheap relative to its real comparables".

Everything is a heuristic over listed asking prices. It ranks; it does not value.
"""

THIS_YEAR = 2026
TYPICAL_KM_PER_YEAR = 12000

# Approximate on-road Hyderabad price when new, in rupees. Top-of-range trims
# sit higher, so VARIANT_BUMP nudges the anchor for variants we can recognise.
APPROX_NEW = {
    "XUV700": 2700000, "SAFARI": 2650000, "ALCAZAR": 2250000,
    "SCORPIO-N": 2600000, "INNOVA": 3000000, "CARENS": 2200000,
    "HECTOR": 2400000, "KODIAQ": 4500000, "CARNIVAL": 3800000,
    "FORTUNER": 4800000, "MARAZZO": 1700000, "XL6": 1600000, "ERTIGA": 1500000,
    "NEXON": 1450000, "SONET": 1500000, "VENUE": 1400000, "BREZZA": 1450000,
    "PUNCH": 1100000, "MAGNITE": 1200000, "KIGER": 1150000,
    "XUV300": 1300000, "XUV3XO": 1350000, "EXTER": 1200000,
    "TAISOR": 1200000, "SYROS": 1500000, "FRONX": 1300000, "CURVV": 1900000,
    # EVs - anchors are the on-road price of the battery-owned version
    "NEXON EV": 1750000, "PUNCH EV": 1400000, "XUV400": 1800000,
    "TIAGO EV": 1150000, "WINDSOR": 1500000, "COMET": 900000,
    "ZS EV": 2600000, "EC3": 1300000, "EV6": 6500000, "CLAVIS": 2300000,
}
VARIANT_BUMP = [
    ("AX 7 LUXURY", 1.10), ("AX7 LUXURY", 1.10), ("SIGNATURE", 1.10),
    ("XZA PLUS O", 1.06), ("PRESTIGE", 0.94), ("AX 5", 0.86), ("AX5", 0.86),
    ("SX(O)", 1.06), ("GTX", 1.06), ("CREATIVE+", 1.04), ("RXZ", 1.04),
    ("XV PREMIUM", 1.04), ("W6", 0.90), ("XE", 0.84), ("XM", 0.86),
]


def _norm(s):
    """Strip spaces and hyphens so multi-word keys match multi-word names."""
    return s.upper().replace("-", "").replace(" ", "")


def _anchor(car):
    name = f"{car['name']} {car.get('variant','')}".upper()
    if is_ev(car) and "EV" not in name.split():
        name += " EV"          # portals sometimes omit EV from the model name
    key_name = _norm(name)
    base = None
    # longest key first, so "NEXON EV" wins over "NEXON"
    for key, val in sorted(APPROX_NEW.items(), key=lambda kv: -len(kv[0])):
        if _norm(key) in key_name:
            base = val
            break
    if base is None:
        return None
    for frag, mult in VARIANT_BUMP:
        if frag in name:
            base = int(base * mult)
            break
    return base


def is_ev(car):
    return "electric" in str(car.get("fuel", "")).lower()


def _retention(age, ev=False):
    """Share of on-road-new price a clean example holds after `age` years.

    EVs fall away far faster here: buyers discount an unknown battery, and each
    new model year lands with more range at the same price, which drags the
    whole used market down behind it.
    """
    if ev:
        return 0.70 if age <= 0 else 0.70 * (0.85 ** (age - 1))
    if age <= 0:
        return 0.92
    return 0.80 * (0.885 ** (age - 1))


def _km_adjust(km, age):
    """Below-average odometer lifts the expected price, above-average cuts it."""
    expected_km = max(TYPICAL_KM_PER_YEAR * max(age, 0.5), 1)
    rel = (expected_km - km) / expected_km
    return max(0.85, min(1.15, 1 + 0.35 * rel))


def model_token(car):
    """Peer-group key. An EV must never share a group with its petrol twin."""
    name = f"{car['name']} {car.get('variant','')}".upper()
    if is_ev(car) and "EV" not in name.split():
        name += " EV"
    key_name = _norm(name)
    for key in sorted(APPROX_NEW, key=lambda k: -len(k)):
        if _norm(key) in key_name:
            return key
    tail = (car["name"].upper().split() or ["?"])[-1]
    return tail + (" EV" if is_ev(car) else "")


def score_all(cars):
    """Attach `expected`, `value_pct`, `score`, `tier` and `why` to each car."""
    # pass 1 - model anchor only
    for c in cars:
        age = max(THIS_YEAR - int(c["year"] or THIS_YEAR), 0)
        c["age"] = age
        anchor = _anchor(c)
        c["_anchor"] = anchor
        c["ev"] = is_ev(c)
        c["expected"] = (int(anchor * _retention(age, c["ev"]) * _km_adjust(c["km"], age))
                         if anchor else None)

    # pass 2 - recentre on what comparable listings actually ask.
    #
    # The anchor+retention curve carries a systematic bias (my new-price guesses
    # are rough and one curve cannot fit both a Kiger and an XUV700). Dividing by
    # the anchor and then comparing to the MEDIAN ratio cancels that bias: what
    # survives is how this car is priced relative to its true comparables, which
    # is the question being asked. Per-model median where the list holds three or
    # more of that model, otherwise the whole search group.
    rated = [c for c in cars if c["expected"]]
    for c in rated:
        c["_ratio"] = c["price"] / c["expected"]

    def median(xs):
        xs = sorted(xs)
        n = len(xs)
        if not n:
            return None
        return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2

    group_med = median([c["_ratio"] for c in rated]) or 1.0
    by_model = {}
    for c in rated:
        by_model.setdefault(model_token(c), []).append(c)

    for c in rated:
        peers = by_model[model_token(c)]
        if len(peers) >= 3:
            c["_baseline"] = median([p["_ratio"] for p in peers])
            c["_peers"] = len(peers)
        else:
            c["_baseline"] = group_med
            c["_peers"] = 0
        # expected price restated on the recentred baseline
        c["expected"] = int(c["expected"] * c["_baseline"])

    for c in cars:
        why = []
        if not c["expected"]:
            c["value_pct"] = None
            c["score"] = None
            c["tier"] = "unrated"
            c["why"] = ["no price anchor for this model"]
            continue

        value = (c["expected"] - c["price"]) / c["expected"] * 100
        c["value_pct"] = value
        s = 50 + 2.2 * value
        basis = (f"{c['_peers']} other {model_token(c).title()} listings"
                 if c.get("_peers") else "comparable listings in this search")
        why.append(f"{abs(value):.0f}% {'below' if value >= 0 else 'above'} the "
                   f"{rupees(c['expected'])} that {basis} imply")

        owners = str(c.get("owners") or "").strip()
        if owners == "1":
            s += 4
            why.append("single owner (+4)")
        elif owners == "2":
            s -= 4
            why.append("second owner (-4)")
        elif owners.isdigit() and int(owners) >= 3:
            s -= 8
            why.append(f"{owners} owners (-8)")

        if c.get("was") and c["was"] > c["price"]:
            s += 3
            why.append(f"marked down from {rupees(c['was'])} (+3)")

        km_per_year = c["km"] / max(c["age"], 0.5)
        if km_per_year < 4000:
            s -= 3
            why.append(f"only {km_per_year:,.0f} km/yr - long idle periods (-3)")
        elif km_per_year > 25000:
            s -= 4
            why.append(f"{km_per_year:,.0f} km/yr - heavy use (-4)")

        if c["age"] >= 5:
            s -= 2
            why.append("5+ years old (-2)")

        if c.get("ev"):
            why.append("EV: score reads price only - get a battery state-of-health "
                       "report before anything else")
            name = f"{c['name']} {c.get('variant','')}".upper()
            if "WINDSOR" in name:
                why.append("MG Windsor: confirm whether this car was sold under "
                           "BaaS - if so the battery is rented and a per-km fee "
                           "continues after you buy")
            if "NEXON" in name or "PUNCH" in name or "TIAGO" in name:
                why.append("Tata EV battery warranty runs 8 years / 1.6 lakh km "
                           "and transfers to you - ask for the warranty card")

        if c.get("_peers"):
            why.append(f"baseline blended with {c['_peers']} peers in this list")

        c["confidence"] = ("model peers" if c.get("_peers") else
                           "thin - baseline drawn across models")
        c["score"] = max(0, min(100, round(s)))
        c["tier"] = ("strong" if c["score"] >= 68 else
                     "fair" if c["score"] >= 50 else "rich")
        c["why"] = why
    return cars


def indian(n):
    """1234567 -> 12,34,567 (lakh grouping, as every Indian listing writes it)."""
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def rupees(n):
    return f"₹{n/100000:.2f}L"
