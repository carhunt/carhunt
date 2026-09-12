#!/usr/bin/env python3
"""
Hyderabad used-car watcher across Cars24, Spinny, CarDekho, CarWale and Droom.

Runs over plain HTTP with no browser, so laptop sleep can't break it: launchd
re-fires on wake and state.json carries the diff across runs.

  ./carhunt.py           # fetch, diff vs last run, report changes
  ./carhunt.py --all     # print every current match
  ./carhunt.py --debug   # show per-source fetch counts and failures
  ./carhunt.py --html    # also write deals.html from the same fetch
"""
import json, os, re, ssl, sys, time, urllib.error
from datetime import datetime
from urllib.request import Request, urlopen

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
LOG = os.path.join(HERE, "carhunt.log")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
DEBUG = "--debug" in sys.argv
GRACE = 3   # runs a listing must be absent before it counts as sold
CTX = ssl.create_default_context()

# ---------------------------------------------------------------- searches

SEVEN = ["XUV700", "SAFARI", "ALCAZAR", "SCORPIO-N", "SCORPIO N", "INNOVA",
         "CARENS", "HECTOR PLUS", "FORTUNER", "MARAZZO", "XL6", "ERTIGA",
         "KODIAQ", "CARNIVAL", "TRIBER", "RUMION",
         # 7-seat EVs - none in Hyderabad yet, listed so the watcher catches
         # the first one that appears
         "CLAVIS", "EMAX", "EQB", "IX7"]
SUB = ["NEXON", "SONET", "VENUE", "BREZZA", "PUNCH", "MAGNITE", "KIGER",
       "XUV300", "XUV 3XO", "XUV3XO", "EXTER", "TAISOR", "SYROS", "FRONX",
       "ECOSPORT", "WR-V", "CURVV",
       # sub-compact SUV EVs (Nexon EV / Punch EV already match above)
       "XUV400", "WINDSOR", "EC3", "ZS EV"]

SEARCHES = {
    "seven_seater": {
        "label": "7-seater, diesel, automatic, <=30k km, <=20.0L",
        "models": SEVEN, "fuel": {"diesel", "electric"}, "gear": {"automatic"},
        "max_km": 30000, "max_price": 2000000,
        "cd": ["mahindra-xuv700", "tata-safari", "hyundai-alcazar",
               "mahindra-scorpio-n", "toyota-innova-crysta", "kia-carens",
               "mg-hector-plus", "skoda-kodiaq", "kia-carnival",
               "kia-carens-clavis", "byd-emax-7"],
        "cw": ["mahindra-xuv700", "tata-safari", "hyundai-alcazar",
               "mahindra-scorpio-n", "toyota-innova-crysta", "kia-carens",
               "mg-hector-plus", "skoda-kodiaq", "kia-carnival",
               "kia-carens-clavis", "byd-emax-7"],
    },
    "subcompact": {
        # diesel+AT does not exist in this class (see README) -> petrol allowed
        "label": "sub-compact SUV, automatic, <=30k km, <=11.0L",
        "models": SUB, "fuel": None, "gear": {"automatic"},
        "max_km": 30000, "max_price": 1100000,
        "cd": ["tata-nexon", "kia-sonet", "hyundai-venue", "maruti-brezza",
               "tata-punch", "nissan-magnite", "renault-kiger",
               "mahindra-xuv300", "mahindra-xuv-3xo", "hyundai-exter",
               "tata-nexon-ev", "tata-punch-ev", "mahindra-xuv400",
               "mg-windsor-ev", "citroen-ec3"],
        "cw": ["tata-nexon", "kia-sonet", "hyundai-venue",
               "maruti-suzuki-brezza", "tata-punch", "nissan-magnite",
               "renault-kiger", "mahindra-xuv300", "mahindra-xuv-3xo",
               "hyundai-exter", "tata-nexon-ev", "tata-punch-ev",
               "mahindra-xuv400", "mg-windsor-ev", "citroen-ec3"],
    },
}

# ---------------------------------------------------------------- helpers


def get(url, tries=2):
    last = None
    for _ in range(tries):
        try:
            req = Request(url, headers={"User-Agent": UA,
                                        "Accept-Language": "en-IN,en;q=0.9"})
            with urlopen(req, timeout=45, context=CTX) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:          # noqa: BLE001 - any transport error
            last = e
            time.sleep(2)
    raise last


def rsc(html):
    """Decode a Next.js flight stream into one searchable string."""
    parts = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
    return "".join(parts).encode().decode("unicode_escape", "replace")


def brace(raw, marker):
    """Extract the balanced {...} object that follows marker."""
    i = raw.find(marker)
    if i < 0:
        return None
    j = raw.find("{", i)
    depth, instr, esc = 0, False, False
    for k in range(j, len(raw)):
        c = raw[k]
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            instr = not instr
            continue
        if instr:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return raw[j:k + 1]
    return None


AT_HINT = re.compile(r'\b(AT|AMT|CVT|DCT|DCA|IVT|TC|AUTO(MATIC)?)\b', re.I)


def gear_from_text(s):
    return "automatic" if AT_HINT.search(s or "") else ""


def rec(**kw):
    kw.setdefault("gear", "")
    kw.setdefault("fuel", "")
    kw.setdefault("owners", "")
    kw.setdefault("rto", "")
    kw.setdefault("where", "")
    return kw


def matches(c, cfg):
    name = f"{c['name']} {c.get('variant','')}".upper()
    if not any(m in name for m in cfg["models"]):
        return False
    if not (0 < c["price"] <= cfg["max_price"]):
        return False
    if not (0 < c["km"] <= cfg["max_km"]):
        return False
    if cfg["fuel"] and c["fuel"].lower() not in cfg["fuel"]:
        return False
    if cfg["gear"] and c["gear"].lower() not in cfg["gear"]:
        return False
    return True


# ---------------------------------------------------------------- sources


def src_cars24(cfg):
    # filter grammar: field:op:value joined by LITERAL ';'  (encoding breaks it)
    base = [f"transmission:=:automatic", f"odometer:bw:0,{cfg['max_km']}",
            f"listingPrice:bw:0,{cfg['max_price']}"]
    # the grammar takes one value per field, so a multi-fuel search is one
    # request per fuel rather than one request with an OR
    fuels = sorted(cfg["fuel"]) if cfg["fuel"] else [None]
    blob = ""
    for fuel in fuels:
        f = ([f"fuelType:=:{fuel}"] if fuel else []) + base
        blob += rsc(get("https://www.cars24.com/buy-used-cars-hyderabad/?f=" + ";".join(f)))
    starts = [m.start() for m in re.finditer(r'"appointmentId":"\d+"', blob)]
    out = []
    for i, st in enumerate(starts):
        s = blob[st:(starts[i + 1] if i + 1 < len(starts) else st + 8000)]

        def g(p, d=""):
            m = re.search(p, s)
            return m.group(1) if m else d

        out.append(rec(
            site="Cars24", id="c24-" + g(r'"appointmentId":"(\d+)"'),
            year=g(r'"year":(\d+)'), name=g(r'"carName":"([^"]*)"'),
            variant=g(r'"variant":"([^"]*)"'),
            km=int(g(r'"odometer":\{"value":(\d+)', "0")),
            fuel=g(r'"fuelType":"([^"]*)"'),
            gear=g(r'"transmissionType":\{"value":"([^"]*)"'),
            price=int(g(r'"listingPrice":(\d+)', "0")),
            was=int(g(r'"originalPrice":(\d+)', "0")),
            owners=g(r'"ownership":(\d+)'), rto=g(r'"cityRto":"([^"]*)"'),
            where=g(r'"locality":"([^"]*)"'),
            url="https://www.cars24.com/" + g(r'"cdpRelativeUrl":"([^"]*)"')))
    return out


def src_spinny(cfg):
    base = (f"https://api.spinny.com/v3/api/listing/v3/?city=hyderabad&page=1&size=100"
            f"&transmission=automatic&max_mileage={cfg['max_km']}")
    results = []
    for fuel in (sorted(cfg["fuel"]) if cfg["fuel"] else [None]):
        q = base + (f"&fuel_type={fuel}" if fuel else "")
        results += json.loads(get(q)).get("results", [])
    out = []
    for r in results:
        out.append(rec(
            site="Spinny", id="spn-" + str(r["id"]), year=str(r.get("make_year", "")),
            name=f"{r.get('make','')} {r.get('model','')}".strip(),
            variant=r.get("variant", ""), km=int(r.get("mileage") or 0),
            fuel=r.get("fuel_type", ""), gear=r.get("transmission", ""),
            price=int(r.get("price") or 0), was=0,
            owners=str(r.get("no_of_owners", "")), rto=r.get("rto", ""),
            where=(r.get("hub") or {}).get("name", "") if isinstance(r.get("hub"), dict) else "",
            url="https://www.spinny.com" + (r.get("permanent_url") or "")))
    return out


def src_cardekho(cfg):
    out = []
    for slug in cfg["cd"]:
        url = f"https://www.cardekho.com/used-{slug}-cars+in+hyderabad"
        try:
            blob = brace(get(url), "__INITIAL_STATE__")
            cars = json.loads(blob).get("cars", []) if blob else []
        except Exception as e:                       # noqa: BLE001
            if DEBUG:
                print(f"   cardekho {slug}: {e}")
            continue
        for c in cars:
            # model pages spill over into nearby cities (Warangal, Vijayawada)
            if str(c.get("city", "")).strip().lower() not in ("", "hyderabad"):
                continue
            km = int(re.sub(r"\D", "", str(c.get("km") or "0")) or 0)
            out.append(rec(
                site="CarDekho", id="cdk-" + str(c.get("usedCarId")),
                year=str(c.get("myear", "")), name=str(c.get("model", "")),
                variant=str(c.get("variantName", "")), km=km,
                fuel=str(c.get("ft", "")), gear=str(c.get("tt", "")),
                price=int(c.get("price") or 0), was=0,
                owners=str(c.get("owner", "")), rto="",
                where=str(c.get("locality", "")),
                url="https://www.cardekho.com" + str(c.get("vlink", ""))))
    return out


def src_carwale(cfg):
    out = []
    for slug in cfg["cw"]:
        url = f"https://www.carwale.com/used/hyderabad/{slug}/"
        try:
            blob = rsc(get(url))
        except Exception as e:                        # noqa: BLE001
            if DEBUG:
                print(f"   carwale {slug}: {e}")
            continue
        for m in re.finditer(r'"profileId":"([A-Za-z0-9]+)"', blob):
            s = blob[m.start():m.start() + 2500]

            def g(p, d=""):
                mm = re.search(p, s)
                return mm.group(1) if mm else d

            name = g(r'"carName":"([^"]*)"')
            owner = g(r'valuationUrl":"[^"]*?owner=(\d+)')
            out.append(rec(
                site="CarWale", id="cwl-" + m.group(1),
                year=g(r'"makeYear":(\d+)'), name=name, variant="",
                km=int(g(r'"kmNumeric":"?(\d+)', "0")),
                fuel=g(r'"fuel":"([^"]*)"'),
                gear=gear_from_text(name),   # list payload omits transmission
                price=int(g(r'"priceNumeric":"?(\d+)', "0")), was=0,
                owners=owner, rto="", where=g(r'"areaName":"([^"]*)"'),
                url="https://www.carwale.com" + g(r'"url":"([^"]*)"')))
    return out


DROOM_PAGES = 6


def src_droom(cfg):
    blob = ""
    for p in range(1, DROOM_PAGES + 1):
        url = "https://droom.in/cars/used/hyderabad" + (f"/page/{p}" if p > 1 else "")
        try:
            blob += rsc(get(url))
        except Exception as e:                        # noqa: BLE001
            if DEBUG:
                print(f"   droom p{p}: {e}")
            break
    out = []
    for m in re.finditer(r'"listing_id":"([a-f0-9]+)"', blob):
        s = blob[m.start():m.start() + 2500]

        def g(p, d=""):
            mm = re.search(p, s)
            return mm.group(1) if mm else d

        trim = g(r'"trim":"([^"]*)"')
        out.append(rec(
            site="Droom", id="drm-" + m.group(1), year=g(r'"year":(\d+)'),
            name=f'{g(chr(34)+"make"+chr(34)+r":"+chr(34)+"([^"+chr(34)+"]*)")} '
                 f'{g(chr(34)+"model"+chr(34)+r":"+chr(34)+"([^"+chr(34)+"]*)")}'.title().strip(),
            variant=trim.upper(),
            km=int(g(r'"kms_driven":"?(\d+)', "0")),
            fuel=g(r'"fuel_type":"([^"]*)"'),
            gear=gear_from_text(trim),
            price=int(g(r'"selling_price":(\d+)', "0")), was=0,
            url="https://droom.in/o/" + g(r'"listing_alias":"([^"]*)"')))
    return out


SOURCES = [("Cars24", src_cars24), ("Spinny", src_spinny),
           ("CarDekho", src_cardekho), ("CarWale", src_carwale),
           ("Droom", src_droom)]

# ---------------------------------------------------------------- reporting


MODEL_WORD = re.compile(r"[A-Z0-9]+")


def fingerprint(c):
    """Same physical car across portals: year + model token + odometer.

    Odometer is the strong signal - portals copy it exactly from the RC/
    inspection, and two different cars of the same model/year landing on the
    same kilometre is rare enough to accept the odd false merge.
    """
    name = f"{c['name']} {c.get('variant','')}".upper()
    tok = ""
    for m in MODEL_WORD.finditer(name):
        w = m.group()
        if w in {"THE", "NEW", "BSVI", "BS6"} or len(w) < 3:
            continue
        tok = w
        break
    return (c["year"], tok, c["km"])


def dedupe(cars):
    """Collapse cross-portal duplicates, keeping the cheapest listing."""
    groups = {}
    for c in cars:
        groups.setdefault(fingerprint(c), []).append(c)
    out = []
    for g in groups.values():
        g.sort(key=lambda x: x["price"])
        best = dict(g[0])
        others = [x["site"] for x in g[1:]]
        if others:
            spread = max(x["price"] for x in g) - g[0]["price"]
            best["also"] = others
            best["spread"] = spread
        out.append(best)
    return out


def lakh(n):
    return f"{n/100000:.2f}L"


def line(c):
    drop = f"  (was {lakh(c['was'])})" if c.get("was") and c["was"] > c["price"] else ""
    bits = [f"{c['km']:,} km", c["fuel"] or "?", c["gear"] or "?"]
    if c.get("owners"):
        bits.append(f"{c['owners']} owner")
    if c.get("rto"):
        bits.append(c["rto"])
    if c.get("where"):
        bits.append(c["where"])
    return (f"  [{c['site']}] {c['year']} {c['name']} {c.get('variant','')}".rstrip() +
            f"\n    Rs {lakh(c['price'])}{drop} | " + " | ".join(bits) +
            (f"\n    also on {', '.join(c['also'])}"
             f" (spread {lakh(c['spread'])})" if c.get("also") else "") +
            f"\n    {c['url']}")


def main():
    show_all = "--all" in sys.argv
    old = json.load(open(STATE)) if os.path.exists(STATE) else {}
    new_state, report = {}, []
    collected = []

    for key, cfg in SEARCHES.items():
        found, notes = {}, []
        for label, fn in SOURCES:
            try:
                got = fn(cfg)
            except Exception as e:                    # noqa: BLE001
                notes.append(f"{label}: FAILED ({type(e).__name__})")
                continue
            keep = [c for c in got if matches(c, cfg)]
            notes.append(f"{label}: {len(keep)}/{len(got)}")
            for c in keep:
                found[c["id"]] = c

        cars = sorted(dedupe(list(found.values())), key=lambda x: x["price"])
        collected.append((key, cfg, cars))
        prev = old.get(key, {})
        seen = {c["id"] for c in cars}

        # Portals rotate which listings land on page 1, so a car missing from
        # one run is usually churn, not a sale. Only call it gone after it has
        # been absent GRACE runs in a row.
        st = {}
        for c in cars:
            st[c["id"]] = {"price": c["price"], "misses": 0}
        really_gone = []
        for cid, rec_ in prev.items():
            if cid in seen:
                continue
            rec_ = rec_ if isinstance(rec_, dict) else {"price": rec_, "misses": 0}
            misses = rec_.get("misses", 0) + 1
            if misses >= GRACE:
                really_gone.append(cid)
            else:
                st[cid] = {"price": rec_["price"], "misses": misses}
        new_state[key] = st

        def prev_price(cid):
            r = prev.get(cid)
            return r.get("price") if isinstance(r, dict) else r

        report.append(f"\n=== {cfg['label']} — {len(cars)} match(es) ===")
        if DEBUG:
            report.append("    scanned -> " + ", ".join(notes))

        if show_all or not prev:
            report += [line(c) for c in cars]
        else:
            fresh = [c for c in cars if c["id"] not in prev]
            cheaper = [c for c in cars
                       if prev_price(c["id"]) and c["price"] < prev_price(c["id"])]
            gone = really_gone
            if fresh:
                report.append("  NEW:")
                report += [line(c) for c in fresh]
            if cheaper:
                report.append("  PRICE DROP:")
                for c in cheaper:
                    report.append(line(c) + f"\n    was Rs {lakh(prev_price(c['id']))}")
            if gone:
                report.append(f"  SOLD/REMOVED: {len(gone)}")
            if not (fresh or cheaper or gone):
                report.append("  no change")

    json.dump(new_state, open(STATE, "w"), indent=1)
    text = f"[{datetime.now():%Y-%m-%d %H:%M}] carhunt" + "\n".join(report)
    print(text)
    with open(LOG, "a") as fh:
        fh.write(text + "\n")

    if "--html" in sys.argv:
        # imported here, not at module scope: gen_html imports this module
        from gen_html import render
        try:
            render(collected)
        except Exception as e:                        # noqa: BLE001
            print(f"html render failed: {type(e).__name__}: {e}")

    if any("NEW:" in r or "PRICE DROP:" in r for r in report):
        os.system('osascript -e \'display notification "New match or price drop" '
                  'with title "Car hunt" sound name "Glass"\' >/dev/null 2>&1')


if __name__ == "__main__":
    main()
