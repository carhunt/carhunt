"""Engine identification and verdict for every listing.

Portals never name the engine, so it is inferred from model, variant and year.
Verdicts:
  rec    recommended - no known design flaw that a checklist cannot cover
  ok     acceptable - known wear items, nothing structural; inspect for them
  avoid  known design fault that is expensive to fix (or likely to be)
  check  cannot tell the engine from the listing - confirm before buying
  ev     electric - no engine; battery health is the risk instead

Researched 18 Nov 2026. India-specific changeover years:
  - B47 (fixed 2.0 diesel) reached India first in the X3 F25 LCI, then the
    320d F30 LCI in Jan 2016 (Autocar India). Before that every 2.0 BMW
    diesel here is the N47 with the rear timing chain.
  - 525d F10 was the 3.0 six (N57, 204 hp) until the 2013 LCI, then a 2.0
    twin-turbo four (N47, 218 hp).
  - BMW India's 2018 EGR-cooler campaign covered 2011-16 diesels (7,900 cars);
    any N47/N57 car should show it done.
"""
import re

LABEL = {"rec": "✓ engine recommended", "ok": "~ engine OK with checks",
         "avoid": "✗ engine: avoid", "check": "? confirm engine", "ev": "EV"}


def _e(code, verdict, detail):
    return {"code": code, "verdict": verdict, "label": LABEL[verdict],
            "detail": detail}


N47 = ("N47 2.0 4-cyl diesel: timing chain sits at the gearbox end and stretches; "
       "fixing it means pulling the engine (₹1.2–2L). Also EGR cooler (recall), "
       "DPF, crank pulley. Only consider with a chain-replacement invoice.")
N57 = ("N57 3.0 inline-6 diesel + ZF 8-speed: the strongest engine in budget. "
       "Known items: EGR cooler (2018 India recall, check done), crank pulley "
       "damper, swirl flaps. Chain failures are rare and mostly 2008-10 builds. "
       "Cold-start listen for rattle anyway.")
B47 = ("B47 2.0 4-cyl diesel: the N47's redesigned successor. Chain problems "
       "largely fixed; EGR cooler recall is the main item - confirm done.")
B57 = ("B57 3.0 inline-6 diesel: very durable. EGR cooler and AdBlue/NOx "
       "sensor faults are the known items.")
B48 = ("B48 2.0 4-cyl turbo petrol: reliable. Plastic oil-filter housing and "
       "coolant leaks around 80-160k km are the known items.")
B38 = ("B38 1.5 3-cyl turbo petrol: no pattern of major failures; modest "
       "pull for an X1. Watch water pump/thermostat like any modern BMW.")
N46 = ("N46 2.0 4-cyl petrol: oil consumption, Valvetronic motor and timing "
       "chain wear once the miles build. Weak engine for the money.")
N63 = ("N63 4.4 V8 twin-turbo: BMW's worst engine of the era - oil burning "
       "(US class-action settlement), valve-stem seals, turbo and coolant-line "
       "failures. Repairs run to lakhs.")
N52 = ("N52 2.5/3.0 inline-6 petrol: sturdy core; oil-filter-housing and "
       "valve-cover gaskets, electric water pump. Car is now very old.")
OM642 = ("OM642 3.0 V6 diesel: durable (often 3-4 lakh km). Known items: "
         "oil-cooler seals (improved Viton seals from 2010, still leak "
         "eventually; labour-heavy), swirl-flap actuator, and the 7G-Tronic "
         "conductor plate. Second choice to the N57 + ZF 8-speed.")
OM654 = ("OM654 2.0 4-cyl diesel: modern and robust; early cars had cam/"
         "rocker wear (Mercedes fitted reinforced rockers). DPF needs highway runs.")
OM651 = ("OM651 2.1 4-cyl diesel: early Delphi piezo injector recalls and "
         "chain stretch on some engines. Acceptable only with records.")
MJD20 = ("2.0 Multijet II diesel (Fiat): robust core. DPF clogs on short city "
         "trips - needs regular highway runs.")
EA888 = ("EA888 Gen 3 2.0 TFSI: oil-consumption problem of Gen 1/2 largely "
         "fixed; plastic water pump/thermostat housing leaks are common.")


def classify(c):
    name = (c.get("name") or "").lower()
    var = (c.get("variant") or "").lower()
    text = f"{name} {var}"
    t = re.sub(r"[\s\-]", "", text)              # "x drive 30 d" -> "xdrive30d"
    year = int(c.get("year") or 0)
    fuel = (c.get("fuel") or "").lower()

    if c.get("ev") or fuel == "electric" or "ix1" in t:
        return _e("electric", "ev", "Electric - no engine. Get a battery "
                  "state-of-health report and check battery warranty transfer.")

    if "bmw" in name:
        if re.search(r"750l?i", t):
            return _e("N63 4.4 V8", "avoid", N63)
        if re.search(r"730l?d", t):
            return _e("N57 3.0 I6", "rec", N57 + " (7 Series: also check rear "
                      "air springs and electronics.)")
        if "530d" in t or re.search(r"5series.*30d|gt530d", t):
            return (_e("B57 3.0 I6", "rec", B57) if year >= 2017
                    else _e("N57 3.0 I6", "rec", N57))
        if "525d" in t:
            if year <= 2012:
                return _e("N57 3.0 I6", "rec", "Pre-2013 India 525d is the 3.0 "
                          "six (204 hp). Confirm 2993 cc on the RC - 1995 cc "
                          "means the N47 four. " + N57)
            return _e("N47 2.0 twin-turbo", "avoid",
                      "2013+ 525d is the 2.0 twin-turbo four, not the six. " + N47)
        if "520d" in t:
            return (_e("B47 2.0", "rec", B47) if year >= 2017
                    else _e("N47 2.0", "avoid", N47))
        if "320d" in t:
            return (_e("B47 2.0", "rec", B47) if year >= 2016
                    else _e("N47 2.0", "avoid", N47))
        if "320i" in t:
            return _e("N46 2.0 (likely)", "check", "A 2012-13 India 320i is most "
                      "likely the E90 with the N46. " + N46)
        if "x1" in t:
            if "20d" in t or "18d" in t:
                if year <= 2015:
                    return _e("N47 2.0", "avoid", N47)
                return _e("B47 2.0", "rec", B47)
            if "18i" in t:
                return (_e("N46 2.0", "avoid", N46) if year <= 2015
                        else _e("B38 1.5 3-cyl", "ok", B38))
            if "20i" in t:
                return _e("B48 2.0", "rec", B48)
        if "x3" in t or "x4" in t:
            if "30d" in t:
                return (_e("B57 3.0 I6", "rec", B57) if year >= 2018
                        else _e("N57 3.0 I6", "rec", N57))
            if "20d" in t:
                if year <= 2014:
                    return _e("N47 2.0", "avoid", N47)
                if year <= 2017:
                    return _e("B47 or N47", "check", "Late F25: B47 reached "
                              "India in the X3 first, but early LCI builds may "
                              "still be N47. Decode the engine number. " + B47)
                return _e("B47 2.0", "rec", B47)
            if "30i" in t:
                return _e("B48 2.0", "rec", B48)
            if "2.5si" in text or "25si" in t or "3.0si" in text:
                return _e("N52 2.5 I6", "ok", N52)
        if "x5" in t and "30d" in t:
            if year >= 2019:
                return _e("B57 3.0 I6", "rec", B57)
            if year >= 2010:
                return _e("N57 3.0 I6", "rec", N57)
            return _e("M57 3.0 I6", "ok", "M57 3.0 six: famously durable, "
                      "but swirl flaps must be removed/blanked; car is old.")
        return _e("unknown BMW", "check", "Engine not identifiable from the "
                  "listing - decode the VIN before going further.")

    if "mercedes" in name:
        if re.search(r"ml ?350|gle ?350|e ?350 ?cdi|s ?350 ?cdi|gl ?350", text):
            return _e("OM642 3.0 V6", "rec", OM642 + (" A 2012 car can be the "
                      "W164 (same engine, no GLE parts) - confirm W166 by VIN."
                      if "ml" in text and year <= 2012 else ""))
        if re.search(r"220d|200d", text) and year >= 2017:
            return _e("OM654 2.0", "rec", OM654)
        if re.search(r"220 ?cdi|250 ?cdi|ml ?250", text):
            return _e("OM651 2.1", "ok", OM651)
        return _e("unknown Mercedes", "check", "Engine not identifiable - "
                  "decode the VIN.")

    if "audi" in name and "tfsi" in text:
        return _e("EA888 2.0 TFSI", "ok", EA888)
    if "jeep" in name:
        return _e("2.0 Multijet II", "ok", MJD20)
    if "tata" in name:
        if "safari" in text or "harrier" in text:
            return _e("2.0 Kryotec (Multijet II)", "ok", MJD20)
        if "nexon" in text:
            if "dca" in text:
                return _e("1.2 Revotron turbo + DCA", "ok", "Engine fine; the "
                          "DCA dual-clutch has owner complaints - test hot.")
            return _e("1.2 Revotron turbo", "ok", "Simple 3-cyl turbo petrol; "
                      "AMT is jerky in traffic but cheap to fix.")
        if "punch" in text:
            return _e("1.2 Revotron NA", "ok", "Simple 3-cyl NA petrol; slow "
                      "but nothing structural reported.")
    if "nissan" in name or "renault" in name:
        if "turbo" in text:
            return _e("1.0 HRA0 turbo", "ok", "Renault-Nissan 1.0 turbo; no "
                      "systematic failures reported, CVT fine in Autocar long-"
                      "termers. Service the turbo-petrol oil on time.")
        return _e("1.0 B4D NA", "ok", "Simple 3-cyl NA petrol with AMT; low "
                  "power, nothing structural reported.")
    if "hyundai" in name:
        return _e("1.2 Kappa", "rec", "Hyundai 1.2 Kappa NA petrol: among the "
                  "most trouble-free small engines sold here.")
    if "mahindra" in name and "3xo" in text:
        return _e("1.2 mStallion turbo", "ok", "Young engine with no proven "
                  "fault yet; the predecessor XUV300 turbo had failure threads.")
    if "kia" in name or "hyundai" in name:
        if "diesel" in text or fuel == "diesel":
            return _e("1.5 CRDi + 6AT", "rec", "1.5 CRDi diesel with a torque-"
                      "converter auto: proven, durable combination.")
        if "dct" in text or "1.4" in text:
            return _e("1.4 T-GDi + 7DCT", "avoid", "DCT overheats and judders "
                      "in stop-go traffic; clutch packs ₹40-60k. Kia patched "
                      "the software, owners still report it.")
    if "honda" in name:
        return _e("Honda i-VTEC", "rec", "Honda 1.2/1.5 i-VTEC NA petrol "
                  "(CVT or manual): consistently the most reliable petrol here.")
    if name.startswith("mg") or " mg " in f" {name} ":
        return _e("1.5 VTi-Tech NA", "ok", "Simple 1.5 NA petrol; CVT "
                  "durability data is thin. Brand's service network is patchy.")
    return _e("unknown", "check", "Engine not classified.")
