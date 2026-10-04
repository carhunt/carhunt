"""
All-India BMW SUV sources for the "bmw" search.

The Hyderabad searches read four portals for one city. This one is national and
reaches past the portals to the sellers who hold most used-BMW stock:

  BMW Premium Selection  bmwusedcars.in - every BMW dealer's certified stock
  Big Boy Toyz           largest luxury pre-owned chain (Delhi, Mumbai, Hyd, Blr, Ahd)
  Royal Drive            largest in Kerala, public JSON API
  Autobest, Car Street   Delhi (Naraina) luxury dealers
  Luxe Cars              Popular Group's luxury arm (Kerala / Bengaluru)
  Motorwagon             Kerala luxury dealer
  Motozite               luxury-dealer marketplace (Mumbai, Delhi, Pune, Jaipur)
  CarWale, CarDekho      national listings - the long tail of small dealers
  Cars24                 its own stock, city by city

Spinny is left out on purpose: its listing API holds no BMW in any metro (checked
Delhi, Mumbai, Bengaluru above Rs 15L), so it would cost 14 requests for nothing.

Each source returns carhunt records; carhunt.matches() applies the limits and
carhunt.dedupe() folds the same car listed by several of these into one row.
"""
import html as _html
import json
import re

import carhunt as ch

# URL slugs per portal. X7/iX/XM never clear Rs 45L with <30k km, but they cost
# a request each and a price cut would otherwise go unseen.
MODELS = ["x1", "x3", "x4", "x5", "x6", "x7", "ix1", "ix"]

CARS24_CITIES = ["new-delhi", "gurgaon", "noida", "mumbai", "bangalore",
                 "hyderabad", "chennai", "pune", "kolkata", "ahmedabad",
                 "jaipur", "chandigarh", "lucknow", "kochi", "indore"]
SPINNY_CITIES = ["delhi-ncr", "mumbai", "bangalore", "hyderabad", "pune",
                 "chennai", "kolkata", "ahmedabad", "jaipur", "chandigarh-tricity",
                 "lucknow", "kochi", "indore", "coimbatore"]
# CarDekho serves 20 cars per page with no working paging or filters, so the
# national page alone would show 20 of ~190 X1s. Splitting by city is what gets
# under that cap for the models that matter.
CARDEKHO_CITIES = ["india", "new-delhi", "gurgaon", "noida", "mumbai",
                   "bangalore", "hyderabad", "chennai", "pune", "kolkata",
                   "ahmedabad", "chandigarh", "jaipur", "kochi", "lucknow"]
CARDEKHO_DEEP = {"x1", "x3", "ix1"}       # city split only where stock is deep

LAKH = re.compile(r"₹\s*([\d.]+)\s*(L|LAKHS?|LAC|CR)\b", re.I)
RUPEE = re.compile(r"₹\s*([\d,]{6,})")
KM = re.compile(r"([\d,]{2,9})\s*kms?\b", re.I)


def _flat(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
    return _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def _num(s):
    return int(re.sub(r"\D", "", str(s or "")) or 0)


def _price(text):
    m = LAKH.search(text)
    if m:
        mult = 10_000_000 if m.group(2).upper() == "CR" else 100_000
        return int(float(m.group(1)) * mult)
    m = RUPEE.search(text)
    return _num(m.group(1)) if m else 0


def _year(text):
    m = re.search(r"\b(20[0-2]\d)\b", text)
    return m.group(1) if m else ""


def _fuel(text):
    m = re.search(r"\b(Petrol|Diesel|Electric|Hybrid)\b", text, re.I)
    return m.group(1).title() if m else ""


def _cards(page, link_re):
    """Split a listing page at each detail link; yield (url, card text)."""
    first = {}
    for m in re.finditer(link_re, page):
        first.setdefault(m.group(1), m.start())
    spots = sorted(first.items(), key=lambda kv: kv[1])
    for i, (url, pos) in enumerate(spots):
        end = spots[i + 1][1] if i + 1 < len(spots) else pos + 6000
        yield url, _flat(page[pos:end])


# ------------------------------------------------------------------ portals


def src_bmw_official(cfg):
    """bmwusedcars.in - BMW India's own certified-used site, all dealers."""
    out = []
    for group in range(40):
        page = ch.post("https://www.bmwusedcars.in/buy-used-cars",
                       f"action=xoxo_fetch_buyusedcars_filtersearch"
                       f"&group_no={group}&city=")
        cards = page.split('id="car_item_')[1:]
        if not cards:
            break
        for card in cards:
            cid = card.split('"', 1)[0]
            link = re.search(r'href="(/buy-used-cars/([a-z-]+)/[^"]+\.html)"', card)
            text = _flat(card)
            m = re.search(r"(BMW [^₹]+?)\s*₹\s?([\d,]+)/-.*?([\d,]+) km (\w+) "
                          r"(\d{4}) (.+?) updated", text)
            if not (m and link):
                continue
            # the card text carries login boilerplate before the car name
            name = m.group(1)[m.group(1).rfind("BMW "):].strip()
            out.append(ch.rec(
                site="BMW Premium Selection", id="bps-" + cid,
                year=m.group(5), name=name, variant="", km=_num(m.group(3)),
                fuel=m.group(4), gear="Automatic", price=_num(m.group(2)),
                was=0, where=m.group(6).strip(),
                url="https://www.bmwusedcars.in" + link.group(1)))
    return out


def src_bigboytoyz(cfg):
    out = {}
    for slug in ["x1", "x3", "x4", "x5", "x6", "x7", "bmw-ix"]:
        try:
            blob = ch.rsc(ch.get(f"https://www.bigboytoyz.com/buy-used-bmw-cars-{slug}"))
        except Exception:                                # noqa: BLE001
            continue
        starts = [m.start() for m in re.finditer(r'\{"id":"\d+","title":"BMW', blob)]
        for i, st in enumerate(starts):
            s = blob[st:starts[i + 1] if i + 1 < len(starts) else st + 6000]

            def g(p, d=""):
                mm = re.search(p, s)
                return mm.group(1) if mm else d

            if g(r'"isSoldOut":(\w+)') == "true" or g(r'"isBooked":(\w+)') == "true":
                continue
            pid = g(r'"id":"(\d+)"')
            # "Unregistered" is a new or demo car: this year's, near-zero km
            unreg = g(r'"registrationYear":"([^"]*)"') == "Unregistered"
            out[pid] = ch.rec(
                site="Big Boy Toyz", id="bbt-" + pid,
                year=str(ch.THIS_YEAR) if unreg else g(r'"registrationYear":"(\d{4})'),
                name=g(r'"title":"([^"]*)"').strip(),
                variant="(unregistered)" if unreg else "",
                km=max(_num(g(r'"kmDriven":"([^"]*)"')), 1 if unreg else 0),
                fuel=g(r'"fuelType":"([^"]*)"'), gear="Automatic",
                price=int(g(r'"price":(\d+)', "0")), was=0,
                owners=_num(g(r'"ownership":"([^"]*)"')) or "",
                rto=g(r'"registrationState":"([^"]*)"'),
                url="https://www.bigboytoyz.com/used-luxury-cars/"
                    + g(r'"slug":"([^"]*)"') + "-detail-page")
    return list(out.values())


def src_cars24(cfg):
    f = f"odometer:bw:0,{cfg['max_km']};listingPrice:bw:0,{cfg['max_price']}"
    out = {}
    for city in CARS24_CITIES:
        try:
            blob = ch.rsc(ch.get(f"https://www.cars24.com/buy-used-bmw-cars-{city}/?f={f}"))
        except Exception:                                # noqa: BLE001
            continue
        starts = [m.start() for m in re.finditer(r'"appointmentId":"\d+"', blob)]
        for i, st in enumerate(starts):
            s = blob[st:starts[i + 1] if i + 1 < len(starts) else st + 8000]

            def g(p, d=""):
                mm = re.search(p, s)
                return mm.group(1) if mm else d

            if g(r'"make":"([^"]*)"').upper() != "BMW":
                continue          # city pages pad thin results with other makes
            rel = g(r'"cdpRelativeUrl":"([^"]*)"')
            where = g(r'"locality":"([^"]*)"')
            out[g(r'"appointmentId":"(\d+)"')] = ch.rec(
                site="Cars24", id="c24-" + g(r'"appointmentId":"(\d+)"'),
                year=g(r'"year":(\d+)'), name=g(r'"carName":"([^"]*)"'),
                variant=g(r'"variant":"([^"]*)"'),
                km=int(g(r'"odometer":\{"value":(\d+)', "0")),
                fuel=g(r'"fuelType":"([^"]*)"'),
                gear=g(r'"transmissionType":\{"value":"([^"]*)"'),
                price=int(g(r'"listingPrice":(\d+)', "0")),
                was=int(g(r'"originalPrice":(\d+)', "0")),
                owners=g(r'"ownership":(\d+)'), rto=g(r'"cityRto":"([^"]*)"'),
                where=where, url="https://www.cars24.com/" + rel)
    return list(out.values())


def src_spinny(cfg):
    out = {}
    for city in SPINNY_CITIES:
        q = (f"https://api.spinny.com/v3/api/listing/v3/?city={city}&page=1"
             f"&size=100&min_price=1500000&max_price={cfg['max_price']}"
             f"&max_mileage={cfg['max_km']}")
        try:
            results = json.loads(ch.get(q)).get("results", [])
        except Exception:                                # noqa: BLE001
            continue
        for r in results:
            if str(r.get("make", "")).upper() != "BMW":
                continue
            hub = r.get("hub") if isinstance(r.get("hub"), dict) else {}
            out[r["id"]] = ch.rec(
                site="Spinny", id="spn-" + str(r["id"]),
                year=str(r.get("make_year", "")),
                name=f"BMW {r.get('model','')}".strip(),
                variant=r.get("variant", ""), km=int(r.get("mileage") or 0),
                fuel=r.get("fuel_type", ""), gear=r.get("transmission", ""),
                price=int(r.get("price") or 0), was=0,
                owners=str(r.get("no_of_owners", "")), rto=r.get("rto", ""),
                where=hub.get("name", "") or city,
                url="https://www.spinny.com" + (r.get("permanent_url") or ""))
    return list(out.values())


def src_cardekho(cfg):
    out = {}
    for model in MODELS:
        cities = CARDEKHO_CITIES if model in CARDEKHO_DEEP else ["india"]
        for city in cities:
            url = f"https://www.cardekho.com/used-bmw-{model}-cars+in+{city}"
            try:
                blob = ch.brace(ch.get(url), "__INITIAL_STATE__")
                cars = json.loads(blob).get("cars", []) if blob else []
            except Exception:                            # noqa: BLE001
                continue
            for c in cars:
                if str(c.get("oem", "")).upper() != "BMW":
                    continue
                out[c.get("usedCarId")] = ch.rec(
                    site="CarDekho", id="cdk-" + str(c.get("usedCarId")),
                    year=str(c.get("myear", "")), name=str(c.get("model", "")),
                    variant=str(c.get("variantName", "")), km=_num(c.get("km")),
                    fuel=str(c.get("ft", "")), gear=str(c.get("tt", "")),
                    price=int(c.get("price") or 0), was=0,
                    owners=str(c.get("owner", "")),
                    where=f"{c.get('locality') or ''}, {c.get('city') or ''}".strip(", "),
                    seller=("dealer" if c.get("dealerId") else
                            str(c.get("utype") or "").lower()),
                    url="https://www.cardekho.com" + str(c.get("vlink", "")))
    return list(out.values())


CARWALE_CITIES = ["delhi", "gurgaon", "noida", "mumbai", "navi-mumbai",
                  "thane", "bangalore", "hyderabad", "chennai", "pune",
                  "kolkata", "ahmedabad", "chandigarh", "jaipur", "kochi",
                  "lucknow", "surat", "indore", "coimbatore"]


def _carwale_page(url, out, make="BMW"):
    """Parse one CarWale listing page into out; return (new cars, totalCount)."""
    blob = ch.rsc(ch.get(url))
    total = int((re.findall(r'"totalCount":"?(\d+)', blob) or ["0"])[0])
    fresh = 0
    for m in re.finditer(r'"profileId":"([A-Za-z0-9]+)"', blob):
        s = blob[m.start():m.start() + 2500]

        def g(p, d=""):
            mm = re.search(p, s)
            return mm.group(1) if mm else d

        name = g(r'"carName":"([^"]*)"')
        if make not in name.upper() or m.group(1) in out:
            continue
        fresh += 1
        city = g(r'"cityName":"([^"]*)"')
        area = g(r'"areaName":"([^"]*)"')
        out[m.group(1)] = ch.rec(
            site="CarWale", id="cwl-" + m.group(1),
            year=g(r'"makeYear":(\d+)'), name=name, variant="",
            km=int(g(r'"kmNumeric":"?(\d+)', "0")),
            fuel=g(r'"fuel":"([^"]*)"'), gear="Automatic",
            price=int(g(r'"priceNumeric":"?(\d+)', "0")), was=0,
            owners=g(r'valuationUrl":"[^"]*?owner=(\d+)'),
            where=", ".join(x for x in (area, city) if x),
            url="https://www.carwale.com" + g(r'"url":"([^"]*)"'))
    return fresh, total


def src_carwale(cfg):
    """CarWale, filtered server-side to the budget and odometer.

    Its listing pages stop at page 2 - page 3 onward repeats page 2, in a real
    browser as well - so ~55 cars is the most one URL can show. Where a model's
    filtered national count is over that, the model is re-read city by city.
    """
    q = (f"?budget=0-{cfg['max_price'] // 100000}"
         f"&kms=0-{cfg['max_km'] // 1000}")      # kms is in thousands
    out = {}
    for model in MODELS:
        try:
            _, total = _carwale_page(f"https://www.carwale.com/used/india/bmw-{model}/{q}", out)
            _carwale_page(f"https://www.carwale.com/used/india/bmw-{model}/page-2/{q}", out)
        except Exception:                                # noqa: BLE001
            continue
        if total <= 50:
            continue
        for city in CARWALE_CITIES:
            try:
                _, n = _carwale_page(f"https://www.carwale.com/used/{city}/bmw-{model}/{q}", out)
                if n > 24:
                    _carwale_page(f"https://www.carwale.com/used/{city}/bmw-{model}/page-2/{q}", out)
            except Exception:                            # noqa: BLE001
                continue
    return list(out.values())


# ------------------------------------------------------------------ dealers


def src_royaldrive(cfg):
    data = json.loads(ch.get(
        "https://api-cust.royaldrive.in/api/allvehicles?page=1&limit=1000"))
    out = []
    for v in data.get("data", {}).get("items", []):
        if v.get("brdTitle") != "BMW" or v.get("isSold") or v.get("isBooked"):
            continue
        title = v.get("title") or ""
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        pid = re.sub(r"[^a-z0-9]", "", str(v.get("prdId")), flags=re.I)[-6:]
        out.append(ch.rec(
            site="Royal Drive", id="rdv-" + str(v.get("prdId")),
            year=str(v.get("yop", "")), name=f"BMW {v.get('modelTitle','')}",
            variant=v.get("variantName", ""), km=_num(v.get("traveled")),
            fuel=v.get("fuelType", ""), gear=v.get("transmission", ""),
            price=int(v.get("price") or 0), was=0,
            owners=str(v.get("ownership", "")), rto=v.get("reg_state", ""),
            where=v.get("availableLocation", ""),
            url=f"https://www.royaldrive.in/used-bmw-cars/{slug}-{pid}"))
    return out


# (label, listing page, detail-link regex, base for relative links, where)
# Each of these renders its stock server-side as cards; the card text is read
# field by field rather than through a site-specific parser.
CARD_DEALERS = [
    ("Autobest", "https://autobest.co.in/pre-owned-cars/brand-bmw",
     r'href="(https://autobest\.co\.in/pre-owned-cars/bmw-[^"]+)"', "", "Delhi"),
    ("Car Street", "https://www.carstreetindia.com/",
     r'href="(https://www\.carstreetindia\.com/car/bmw-[^"]+)"', "", "Delhi"),
    ("Luxe Cars", "https://luxecars.co.in/catalog/used-luxury-cars-brand-bmw",
     r'href="(/catalog/used-luxury-cars/bmw-[^"]+)"', "https://luxecars.co.in",
     "Kerala / Bengaluru"),
    ("Motorwagon", "https://motorwagon.co/",
     r'href="(https://motorwagon\.co/car/bmw-[^"]+)"', "", "Kerala"),
    ("Motozite", "https://motozite.com/pre-owned/bmw/all",
     r'href="(/pre-owned-cars/\d+/bmw-[^"]+)"', "https://motozite.com", ""),
]


def _card_record(label, url, text, where):
    if re.search(r"\bSOLD\b|\bBOOKED\b", text[:60], re.I):
        return None
    name = re.search(r"\b(BMW (?:BMW )?[A-Za-z0-9][^₹|]{2,60}?)(?= \d| ₹| Market|"
                     r" REG| Petrol| Diesel| Electric| AT\b| A/T| \.\.\.|$)", text)
    km = re.search(r"KMS COVERED ([\d,]+)", text) or KM.search(text)
    # Car Street shows a "market price" beside its own - the second is the ask
    fixed = re.search(r"Fixed Price : (₹[\d,]+)", text)
    if not name:
        return None
    return ch.rec(
        site=label, id=f"{label[:3].lower()}-" + re.sub(r"\W+", "", url)[-40:],
        year=_year(text), name=name.group(1).replace("BMW BMW", "BMW").strip(),
        variant="", km=_num(km.group(1)) if km else 0, fuel=_fuel(text),
        gear="Automatic", price=_price(fixed.group(1) if fixed else text),
        was=0, where=where, url=url)


def make_card_source(label, page_url, link_re, base, where):
    def src(cfg):
        page = ch.get(page_url)
        out = []
        for url, text in _cards(page, link_re):
            r = _card_record(label, base + url, text, where)
            if r:
                out.append(r)
        return out
    src.__name__ = "src_" + re.sub(r"\W", "", label.lower())
    return src


SOURCES = [
    ("BMW Premium Selection", src_bmw_official),
    ("Big Boy Toyz", src_bigboytoyz),
    ("Royal Drive", src_royaldrive),
    *[(d[0], make_card_source(*d)) for d in CARD_DEALERS],
    ("Cars24", src_cars24),
    ("CarDekho", src_cardekho),
    ("CarWale", src_carwale),
]
