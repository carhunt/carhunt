"""
All-India Mercedes ML 350 CDI (W166) sources for the "ml350" search.

This is the base car for the facelift project: an ML 350 CDI (OM642 3.0 V6
diesel) converted to the 2015 GLE look. The search is national because the
Hyderabad stock alone is a handful of cars.

Only three portals hold any: CarWale, CarDekho and Cars24. Checked and left out
(Oct 2026): Spinny's API returns no Mercedes at all under Rs 20L, and Big Boy
Toyz and Royal Drive hold no M-Class. They would cost requests for nothing.

Portals spell the car four ways ("M-Class ML 350 CDI", "Ml Class 350 CDI",
"ML350 4MATIC" ...), so every record is renamed "Mercedes-Benz ML 350" with the
portal's own wording kept as the variant. That gives matches(), dedupe() and
the scorer one name to work with.
"""
import json
import re

import bmw
import carhunt as ch

# M-Class pages pad thin results with other models; this keeps only the ML.
IS_ML = re.compile(r"\bM-?\s?CLASS\b|\bML\s?CLASS\b|\bML\s?\d{3}", re.I)
IS_350 = re.compile(r"\b(ML\s?)?350\b", re.I)

NAME = "Mercedes-Benz ML 350"


def _ml350(text):
    return bool(IS_ML.search(text) and IS_350.search(text))


def _variant(text):
    """Portal wording minus the make/model words already in NAME."""
    v = re.sub(r"(?i)mercedes[- ]benz|\bm-?\s?class\b|\bml\s?class\b"
               r"|\b(ml\s?)?350\b", "", text)
    return re.sub(r"\s+", " ", v).strip()


def src_carwale(cfg):
    q = (f"?budget=0-{cfg['max_price'] // 100000}"
         f"&kms=0-{cfg['max_km'] // 1000}")      # kms is in thousands
    out = {}
    seen = {}
    try:
        _, total = bmw._carwale_page(
            f"https://www.carwale.com/used/india/mercedes-benz-m-class/{q}", seen,
            make="MERCEDES")
        bmw._carwale_page(
            f"https://www.carwale.com/used/india/mercedes-benz-m-class/page-2/{q}",
            seen, make="MERCEDES")
    except Exception:                                    # noqa: BLE001
        total = 0
    if total > 50:            # two pages hold ~50; past that, split by city
        for city in bmw.CARWALE_CITIES:
            try:
                bmw._carwale_page(
                    f"https://www.carwale.com/used/{city}/mercedes-benz-m-class/{q}",
                    seen, make="MERCEDES")
            except Exception:                            # noqa: BLE001
                continue
    for pid, r in seen.items():
        if not _ml350(r["name"]):
            continue
        r = dict(r, variant=_variant(r["name"]), name=NAME)
        out[pid] = r
    return list(out.values())


def src_cardekho(cfg):
    out = {}
    for city in bmw.CARDEKHO_CITIES:
        url = f"https://www.cardekho.com/used-mercedes-benz-m-class-cars+in+{city}"
        try:
            blob = ch.brace(ch.get(url), "__INITIAL_STATE__")
            cars = json.loads(blob).get("cars", []) if blob else []
        except Exception:                                # noqa: BLE001
            continue
        for c in cars:
            text = f"{c.get('model', '')} {c.get('variantName', '')}"
            if not _ml350(text):
                continue
            out[c.get("usedCarId")] = ch.rec(
                site="CarDekho", id="cdk-" + str(c.get("usedCarId")),
                year=str(c.get("myear", "")), name=NAME,
                variant=_variant(str(c.get("variantName", ""))),
                km=bmw._num(c.get("km")),
                fuel=str(c.get("ft", "")), gear="Automatic",
                price=int(c.get("price") or 0), was=0,
                owners=str(c.get("owner", "")),
                where=f"{c.get('locality') or ''}, {c.get('city') or ''}".strip(", "),
                url="https://www.cardekho.com" + str(c.get("vlink", "")))
    return list(out.values())


def src_cars24(cfg):
    f = f"odometer:bw:0,{cfg['max_km']};listingPrice:bw:0,{cfg['max_price']}"
    out = {}
    for city in bmw.CARS24_CITIES:
        url = f"https://www.cars24.com/buy-used-mercedes-benz-ml-class-cars-{city}/?f={f}"
        try:
            blob = ch.rsc(ch.get(url))
        except Exception:                                # noqa: BLE001
            continue
        starts = [m.start() for m in re.finditer(r'"appointmentId":"\d+"', blob)]
        for i, st in enumerate(starts):
            s = blob[st:starts[i + 1] if i + 1 < len(starts) else st + 8000]

            def g(p, d=""):
                mm = re.search(p, s)
                return mm.group(1) if mm else d

            variant = g(r'"variant":"([^"]*)"')
            if not _ml350(g(r'"carName":"([^"]*)"') + " " + variant):
                continue
            aid = g(r'"appointmentId":"(\d+)"')
            out[aid] = ch.rec(
                site="Cars24", id="c24-" + aid,
                year=g(r'"year":(\d+)'), name=NAME, variant=_variant(variant),
                km=int(g(r'"odometer":\{"value":(\d+)', "0")),
                fuel=g(r'"fuelType":"([^"]*)"'), gear="Automatic",
                price=int(g(r'"listingPrice":(\d+)', "0")),
                was=int(g(r'"originalPrice":(\d+)', "0")),
                owners=g(r'"ownership":(\d+)'), rto=g(r'"cityRto":"([^"]*)"'),
                where=g(r'"locality":"([^"]*)"'),
                url="https://www.cars24.com/" + g(r'"cdpRelativeUrl":"([^"]*)"'))
    return list(out.values())


SOURCES = [
    ("CarWale", src_carwale),
    ("CarDekho", src_cardekho),
    ("Cars24", src_cars24),
]
