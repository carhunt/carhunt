# carhunt — Hyderabad used-car watcher

Polls five portals every 2 hours, diffs against the previous run, and posts a
macOS notification on a new match or a price drop. Pure HTTP, no browser, so
laptop sleep cannot break it: launchd re-fires on wake and `state.json` carries
the diff across the gap.

```
python3 carhunt.py            # fetch, diff, report changes
python3 carhunt.py --all      # print every current match
python3 carhunt.py --debug    # per-source scanned/matched counts and failures
python3 carhunt.py --html     # also regenerate deals.html from the same fetch
./refresh.sh                  # what launchd runs: refresh, check, commit, push
python3 gen_html.py           # page only, fetching independently
tail -f carhunt.log
```

## How the two halves fit together

Scraping has to happen on the Mac. The Claude cloud sandbox routes all traffic
through a proxy that allowlists github.com and pypi.org and refuses every car
portal (`curl` exit 56, connection reset before any HTTP response), so a cloud
agent cannot fetch listings. The work is split accordingly:

| Where | What | How often |
|---|---|---|
| Mac, launchd | `refresh.sh` - scrape, score, render, sanity-check, commit and push `deals.html` | every 2h |
| Cloud routine | clone, re-verify, read the live artifact, publish only if changed | every 4h |

`refresh.sh` runs `carhunt.py --html`, so each cycle hits every portal once and
both the diff and the page come out of that single fetch. It refuses to commit a
page under 20KB or with zero listing rows, and the cloud routine repeats those
checks before publishing - a bad page has to pass two independent gates. The
consequence of the split is that the published page tracks the newest local run:
if this Mac is off for a day, the routine keeps publishing yesterday's page and
says so in its report.

Routine: `trig_01YHa11hFdNkRnKkm33zxfdC`, artifact
`https://claude.ai/code/artifact/4eba3377-ccd0-4292-86a6-18c724c4ade3`.
Note that creating a routine silently attaches every connected MCP connector -
Robinhood, Gmail, Calendar, Drive - so clear them unless they are actually
needed.

Running `gen_html.py` standalone re-fetches everything, which is why nothing
scheduled uses it.

Scheduling lives in `~/Library/LaunchAgents/com.rp.carhunt.plist`
(`StartInterval` 7200, `RunAtLoad`). Reload after editing:

```
launchctl unload ~/Library/LaunchAgents/com.rp.carhunt.plist
launchctl load   ~/Library/LaunchAgents/com.rp.carhunt.plist
```

## Sources

| Portal | Access | Filtering | Notes |
|---|---|---|---|
| Cars24 | SSR Next.js flight stream | server-side | richest fields: RTO, masked reg, owners, original price |
| Spinny | `api.spinny.com` JSON | server-side | clean API, `max_mileage` + `fuel_type` + `transmission` |
| CarDekho | `window.__INITIAL_STATE__` | **client-side** | its own filter params are broken — see below |
| CarWale | SSR Next.js flight stream | client-side | list payload has no transmission field — inferred from variant text |
| Droom | SSR Next.js flight stream | client-side | 6 pages; mostly old high-km stock, rarely matches |
| OLX | **not covered** | — | returns nothing to a plain client (bot wall / geo) |

Fuel filters take one value per request, so a search covering both diesel and
electric costs one request per fuel on Cars24 and Spinny.

### Portal quirks worth remembering

**Cars24 filter grammar.** `field:op:value`, joined by *literal* semicolons:

```
?f=fuelType:=:diesel;transmission:=:automatic;odometer:bw:0,30000
```

URL-encoding the `:` or `;` makes the server silently ignore the filter and
return an unfiltered page — no error, just wrong results. Learned the hard way.

**CarDekho filters don't work.** `?fuelType=Diesel&transmission=Automatic`
returns petrol manuals. So carhunt fetches per-model SEO pages
(`/used-<make>-<model>-cars+in+hyderabad`) and filters locally. The model slug
lists are the `cd` key in `SEARCHES`.

**CarWale** has no listing API — everything is server-rendered. Per-model pages
live at `/used/hyderabad/<make-model>/`. Owner count is scraped out of the
`valuationUrl` query string. Transmission is *inferred* from the variant name
(`AT|AMT|CVT|DCT|DCA|IVT`), so a car whose variant string omits the gearbox is
missed. This is the one known false-negative source.

**Page-1 rotation.** CarDekho and CarWale return a slightly different page-1 set
on every request. Naively diffing produced phantom "SOLD" reports minutes apart.
`GRACE = 3` fixes it: a listing must be absent three consecutive runs before it
counts as gone.

**Cross-portal duplicates.** The same physical car appears on up to four sites.
`dedupe()` fingerprints on `(year, model token, odometer)` and keeps the cheapest
listing, noting the others plus the price spread. The spread is useful on its
own — the same car has shown up ~0.1L apart across portals.

## Searches

Edit `SEARCHES` at the top of `carhunt.py` to retune.

- `seven_seater` — diesel or electric, automatic, ≤20.0L
- `subcompact` — automatic, ≤11.0L, **fuel unrestricted**
- `subcompact_ev` — electric only, ≤15.0L, ≤60,000 km, **deliberately above
  budget**: nothing electric clears the ₹11L cap under 30,000 km, so this group
  exists to show what the segment actually costs. The page labels it as such.

Deal scoring lives in `score.py`; `gen_html.py` renders the page. EVs are never
pooled with their petrol twins and run a steeper retention curve — see the
methodology section on the page itself.

The subcompact search deliberately does not filter on diesel. Sub-compact SUV +
diesel + automatic barely exists as a build combination: Venue diesel is
manual/iMT only, Brezza diesel died in 2020, and Punch / Magnite / Kiger / Exter
have no diesel at all. Only the Sonet 1.5D AT, Nexon AMT and XUV300 AMT were
ever made, and every Hyderabad example is an ex-fleet car at 1.1–1.5 lakh km.
Restricting to diesel returns an empty list.

## Verification (nothing here automates this)

India has no Carfax. "No accident history" on any portal is that portal's own
inspection, not a title record — treat it as zero evidence.

The best accident proxy that actually exists is the **insurance NCB**: ask for
the current and previous policy. NCB 50% means five straight claim-free years;
0–20% on a three-year-old car means it was claimed on.

Once you have the unmasked registration number (portals mask it until you book):

1. VAHAN `vahan.parivahan.gov.in` — owner serial, RC status, hypothecation, blacklist, fitness
2. mParivahan app — same data, OTP-based
3. eChallan `echallan.parivahan.gov.in` — unpaid fines transfer with the car
4. If hypothecation shows: demand bank NOC + Form 35 before paying
5. VIN plate vs RC vs listing — any mismatch, walk away
6. Service history at an OEM dealer by VIN — the real odometer cross-check
7. Independent pre-purchase inspection before money moves

These portals are geo-fenced to India and return nothing from outside.
