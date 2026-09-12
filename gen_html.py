#!/usr/bin/env python3
"""Render the current carhunt matches as a browsable, scored HTML page."""
import html
import json
import os
import sys
from datetime import datetime

import carhunt as ch
import score as sc

# argv may belong to carhunt (which imports this module), so only take a real
# path, never a flag
_args = [a for a in sys.argv[1:] if not a.startswith("-")]
# resolve beside this file, so the cloud checkout works the same as the Mac
OUT = _args[0] if _args else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "deals.html")

CSS = """
:root{
  --ground:#edf0f3; --surface:#ffffff; --surface-2:#f6f8fa;
  --ink:#0f1418; --muted:#59646f; --line:#d5dbe1;
  --accent:#0b665c;
  --strong:#0f6b52; --strong-bg:#e2f1ea;
  --fair:#8a6212;   --fair-bg:#f6eedd;
  --rich:#a63a2b;   --rich-bg:#f7e6e2;
  --shadow:0 1px 2px rgba(15,20,24,.06), 0 4px 16px rgba(15,20,24,.05);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --ground:#0c1013; --surface:#141a1f; --surface-2:#192127;
    --ink:#e2e7ec; --muted:#8a97a3; --line:#242d34;
    --accent:#3fb9a6;
    --strong:#5cc9a4; --strong-bg:#122c25;
    --fair:#d3a44a;   --fair-bg:#2c2416;
    --rich:#e07764;   --rich-bg:#301a16;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 4px 16px rgba(0,0,0,.3);
  }
}
:root[data-theme="dark"]{
  --ground:#0c1013; --surface:#141a1f; --surface-2:#192127;
  --ink:#e2e7ec; --muted:#8a97a3; --line:#242d34;
  --accent:#3fb9a6;
  --strong:#5cc9a4; --strong-bg:#122c25;
  --fair:#d3a44a;   --fair-bg:#2c2416;
  --rich:#e07764;   --rich-bg:#301a16;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 4px 16px rgba(0,0,0,.3);
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:15px; line-height:1.5;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1120px; margin:0 auto; padding-inline:20px; padding-block:0 64px}

/* masthead ---------------------------------------------------------- */
header{padding-block:40px 22px; border-bottom:1px solid var(--line)}
.eyebrow{
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:11px;
  letter-spacing:.14em; text-transform:uppercase; color:var(--accent);
  margin:0 0 10px;
}
h1{
  font-family:Archivo,system-ui,sans-serif; font-weight:700; font-size:clamp(28px,4.4vw,42px);
  letter-spacing:-.02em; line-height:1.05; margin:0 0 10px; text-wrap:balance;
}
.lede{margin:0; color:var(--muted); max-width:62ch}
.stats{display:flex; flex-wrap:wrap; gap:28px; margin-top:24px}
.stat b{
  display:block; font-family:Archivo,sans-serif; font-size:26px; font-weight:700;
  font-variant-numeric:tabular-nums; line-height:1;
}
.stat span{
  font-family:"IBM Plex Mono",monospace; font-size:10.5px; letter-spacing:.1em;
  text-transform:uppercase; color:var(--muted);
}

/* controls ---------------------------------------------------------- */
.controls{
  position:sticky; top:0; z-index:20; background:var(--ground);
  border-bottom:1px solid var(--line); padding-block:12px;
  display:flex; flex-wrap:wrap; gap:10px; align-items:center;
}
.seg{display:flex; border:1px solid var(--line); border-radius:7px; overflow:hidden}
.seg button{
  font:inherit; font-size:13px; padding:7px 13px; border:0; cursor:pointer;
  background:var(--surface); color:var(--muted); border-right:1px solid var(--line);
}
.seg button:last-child{border-right:0}
.seg button[aria-pressed="true"]{background:var(--accent); color:#fff}
.spacer{flex:1 1 auto}
label.sort{
  font-size:13px; color:var(--muted); display:flex; align-items:center; gap:7px;
}
select{
  font:inherit; font-size:13px; padding:6px 9px; border-radius:7px;
  border:1px solid var(--line); background:var(--surface); color:var(--ink);
}
button:focus-visible, select:focus-visible, summary:focus-visible, a:focus-visible{
  outline:2px solid var(--accent); outline-offset:2px;
}

/* group + rows ------------------------------------------------------ */
.group{margin-top:34px}
.group > h2{
  font-family:Archivo,sans-serif; font-size:15px; font-weight:600; margin:0 0 3px;
  letter-spacing:-.01em;
}
.group .crit{
  font-family:"IBM Plex Mono",monospace; font-size:11.5px; color:var(--muted);
  margin:0 0 14px;
}
.rows{display:flex; flex-direction:column; gap:8px}

.row{
  background:var(--surface); border:1px solid var(--line); border-radius:9px;
  border-left:3px solid var(--tier); box-shadow:var(--shadow); overflow:hidden;
}
.row[data-tier="strong"]{--tier:var(--strong)}
.row[data-tier="fair"]{--tier:var(--fair)}
.row[data-tier="rich"]{--tier:var(--rich)}
.row[data-tier="unrated"]{--tier:var(--line)}

.head{
  display:grid; gap:14px; padding:13px 15px;
  grid-template-columns:52px minmax(0,1fr) auto;
  align-items:center;
}
.score{
  width:52px; height:52px; border-radius:8px; display:grid; place-items:center;
  background:var(--tier-bg); color:var(--tier); line-height:1;
}
.row[data-tier="strong"] .score{--tier-bg:var(--strong-bg)}
.row[data-tier="fair"] .score{--tier-bg:var(--fair-bg)}
.row[data-tier="rich"] .score{--tier-bg:var(--rich-bg)}
.row[data-tier="unrated"] .score{--tier-bg:var(--surface-2); color:var(--muted)}
.score b{font-family:Archivo,sans-serif; font-size:21px; font-weight:700; font-variant-numeric:tabular-nums}
.score span{font-family:"IBM Plex Mono",monospace; font-size:8.5px; letter-spacing:.08em; text-transform:uppercase; margin-top:2px}

.title{min-width:0}
.title h3{
  font-family:Archivo,sans-serif; font-size:15.5px; font-weight:600; margin:0 0 3px;
  letter-spacing:-.01em; overflow-wrap:anywhere;
}
.title .variant{color:var(--muted); font-weight:400}
.meta{
  display:flex; flex-wrap:wrap; gap:4px 12px; font-size:12.5px; color:var(--muted);
  font-family:"IBM Plex Mono",monospace;
}
.meta .plate{
  border:1px solid var(--line); border-radius:3px; padding:0 4px;
  letter-spacing:.03em; color:var(--ink);
}
.price{text-align:right; white-space:nowrap}
.price b{
  font-family:Archivo,sans-serif; font-size:20px; font-weight:700;
  font-variant-numeric:tabular-nums; display:block; letter-spacing:-.01em;
}
.price .was{font-size:12px; color:var(--muted); text-decoration:line-through}
.price .delta{font-size:11.5px; font-family:"IBM Plex Mono",monospace; display:block; margin-top:2px}
.delta.under{color:var(--strong)}
.delta.over{color:var(--rich)}

details{border-top:1px solid var(--line); background:var(--surface-2)}
summary{
  cursor:pointer; padding:9px 15px; font-size:12.5px; color:var(--muted);
  font-family:"IBM Plex Mono",monospace; list-style:none;
}
summary::-webkit-details-marker{display:none}
summary::before{content:"▸ "; color:var(--accent)}
details[open] summary::before{content:"▾ "}
.why{padding:2px 15px 15px; display:flex; flex-direction:column; gap:9px}
.why ul{margin:0; padding-left:17px; display:flex; flex-direction:column; gap:4px; font-size:13px}
.why .conf{font-size:12px; color:var(--muted); font-family:"IBM Plex Mono",monospace}
.actions{display:flex; flex-wrap:wrap; gap:8px; margin-top:2px}
.actions a{
  font-size:12.5px; text-decoration:none; color:var(--accent);
  border:1px solid var(--line); border-radius:6px; padding:5px 10px; background:var(--surface);
}
.actions a:hover{border-color:var(--accent)}
.also{font-size:12px; color:var(--muted)}

.empty{color:var(--muted); font-size:14px; padding:18px 0}
.meta .ev{
  background:var(--accent); color:#fff; border-radius:3px; padding:0 5px;
  font-size:10.5px; letter-spacing:.07em; font-weight:500;
}
.note{
  margin:0 0 14px; padding:11px 13px; border-radius:8px; font-size:13px;
  background:var(--surface-2); border:1px solid var(--line);
  border-left:3px solid var(--fair); color:var(--muted); max-width:74ch;
}

/* method ------------------------------------------------------------ */
.method{
  margin-top:44px; border-top:1px solid var(--line); padding-top:22px;
  color:var(--muted); font-size:13.5px; max-width:70ch;
}
.method h2{
  font-family:Archivo,sans-serif; font-size:14px; color:var(--ink); margin:0 0 10px;
}
.method p{margin:0 0 11px}
.method code{
  font-family:"IBM Plex Mono",monospace; font-size:12.5px;
  background:var(--surface-2); padding:1px 4px; border-radius:3px;
}
.legend{display:flex; flex-wrap:wrap; gap:16px; margin:0 0 14px; font-size:12.5px}
.legend i{
  width:9px; height:9px; border-radius:2px; display:inline-block; margin-right:6px;
}

@media (max-width:640px){
  .head{grid-template-columns:44px minmax(0,1fr); row-gap:10px}
  .score{width:44px; height:44px}
  .price{grid-column:1 / -1; text-align:left; display:flex; align-items:baseline; gap:10px; flex-wrap:wrap}
  .price .delta{margin-top:0}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important; transition:none!important}}
"""

JS = """
const rows = Array.from(document.querySelectorAll('.row'));
const groups = Array.from(document.querySelectorAll('.group'));

function apply(){
  const tier = document.querySelector('.seg[data-role=tier] button[aria-pressed=true]').dataset.tier;
  const sort = document.getElementById('sort').value;
  groups.forEach(g => {
    const list = g.querySelector('.rows');
    const kids = Array.from(list.children);
    kids.forEach(r => {
      r.hidden = !(tier === 'all' || r.dataset.tier === tier);
    });
    kids.sort((a,b) => {
      const n = k => parseFloat(k.dataset[sort] || 0);
      return sort === 'price' || sort === 'km' ? n(a)-n(b) : n(b)-n(a);
    }).forEach(r => list.appendChild(r));
    const shown = kids.filter(r => !r.hidden).length;
    g.querySelector('.empty').hidden = shown > 0;
    g.querySelector('.count').textContent = shown;
  });
}

document.querySelectorAll('.seg button').forEach(b => {
  b.addEventListener('click', () => {
    b.parentElement.querySelectorAll('button')
      .forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    apply();
  });
});
document.getElementById('sort').addEventListener('change', apply);
apply();
"""


HEADINGS = {
    "seven_seater": "Seven-seaters",
    "subcompact": "Sub-compact SUVs",
}
NOTES = {}

# Anything scoring below this is priced badly enough not to be worth your time,
# so it never reaches the page. It still appears in carhunt.log and state.json.
MIN_SCORE = 40


def esc(s):
    return html.escape(str(s or ""))


def row_html(c):
    tier = c.get("tier") or "unrated"
    score = c.get("score")
    meta = []
    if c["km"]:
        meta.append(f"{sc.indian(c['km'])} km")
    if c.get("fuel"):
        meta.append(esc(c["fuel"]).lower())
    if c.get("owners"):
        n = str(c["owners"])
        meta.append(f"{n}{'st' if n=='1' else 'nd' if n=='2' else 'rd' if n=='3' else 'th'} owner")
    if c.get("age") is not None:
        meta.append(f"{c['age']}y old")
    meta_html = ('<span class="ev">EV</span>' if c.get("ev") else "")
    meta_html += "".join(f"<span>{m}</span>" for m in meta)
    if c.get("rto"):
        meta_html += f'<span class="plate">{esc(c["rto"])}</span>'
    if c.get("where"):
        meta_html += f"<span>{esc(c['where'][:34])}</span>"

    delta = ""
    if c.get("value_pct") is not None:
        v = c["value_pct"]
        cls = "under" if v >= 0 else "over"
        word = "under" if v >= 0 else "over"
        delta = (f'<span class="delta {cls}">{abs(v):.0f}% {word} comparables</span>')

    was = (f'<span class="was">{sc.rupees(c["was"])}</span> '
           if c.get("was") and c["was"] > c["price"] else "")

    why_items = "".join(f"<li>{esc(w)}</li>" for w in c.get("why", []))
    also = ""
    if c.get("also"):
        also = (f'<p class="also">Same car also listed on {esc(", ".join(c["also"]))}'
                f' — price spread {sc.rupees(c["spread"])}.</p>')

    label = "deal" if score is not None else "n/a"
    return f"""
<article class="row" data-tier="{tier}" data-score="{score or 0}"
         data-price="{c['price']}" data-km="{c['km']}" data-year="{c['year'] or 0}">
  <div class="head">
    <div class="score"><b>{score if score is not None else '—'}</b><span>{label}</span></div>
    <div class="title">
      <h3>{esc(c['year'])} {esc(c['name'])}
        <span class="variant">{esc(c.get('variant',''))}</span></h3>
      <div class="meta">{meta_html}</div>
    </div>
    <div class="price"><b>{sc.rupees(c['price'])}</b>{was}{delta}</div>
  </div>
  <details>
    <summary>How this scored · {esc(c['site'])}</summary>
    <div class="why">
      <ul>{why_items}</ul>
      <p class="conf">Baseline confidence: {esc(c.get('confidence','—'))}</p>
      {also}
      <div class="actions"><a href="{esc(c['url'])}" target="_blank" rel="noopener">
        Open on {esc(c['site'])} ↗</a></div>
    </div>
  </details>
</article>"""


def collect():
    """Fetch every search from scratch. Used when this script runs standalone."""
    groups = []
    for key, cfg in ch.SEARCHES.items():
        found = {}
        for _, fn in ch.SOURCES:
            try:
                for c in fn(cfg):
                    if ch.matches(c, cfg):
                        found[c["id"]] = c
            except Exception:      # noqa: BLE001 - a dead portal must not kill the page
                continue
        groups.append((key, cfg, ch.dedupe(list(found.values()))))
    return groups


def render(groups, out=OUT):
    """Score already-collected listings and write the page.

    carhunt hands over the cars it has just fetched, so the scheduled run hits
    each portal once per cycle instead of twice.
    """
    total = strong = evs = 0
    cheapest_seven = None
    scored = []
    cut = 0
    for key, cfg, cars in groups:
        cars = sc.score_all(list(cars))
        before = len(cars)
        cars = [c for c in cars if (c.get("score") or 0) >= MIN_SCORE]
        cut += before - len(cars)
        cars.sort(key=lambda x: -(x["score"] or 0))
        total += len(cars)
        strong += sum(1 for c in cars if c.get("tier") == "strong")
        evs += sum(1 for c in cars if c.get("ev"))
        if key == "seven_seater" and cars:
            cheapest_seven = min(c["price"] for c in cars)
        scored.append((key, cfg, cars))
    groups = scored

    body = []
    for key, cfg, cars in groups:
        rows = "".join(row_html(c) for c in cars)
        note = (f'<p class="note">{NOTES[key]}</p>' if key in NOTES else "")
        body.append(f"""
<section class="group" id="{key}">
  <h2>{esc(HEADINGS.get(key, key))} · <span class="count">{len(cars)}</span> listings</h2>
  <p class="crit">{esc(cfg['label'])} · Hyderabad</p>
  {note}
  <div class="rows">{rows}</div>
  <p class="empty" hidden>Nothing in this group matches the current filter.</p>
</section>""")

    stamp = datetime.now().strftime("%-d %b %Y, %-I:%M %p")
    page = f"""<title>Hyderabad Car Hunt</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>{CSS}</style>
<div class="wrap">
  <header>
    <p class="eyebrow">Cars24 · Spinny · CarDekho · CarWale · Droom</p>
    <h1>Hyderabad Car Hunt</h1>
    <p class="lede">Listings matching your two searches, de-duplicated across
      five portals and scored against what comparable cars are actually asking.
      Anything scoring below {MIN_SCORE} is left out. Refreshed {esc(stamp)}.</p>
    <div class="stats">
      <div class="stat"><b>{total}</b><span>listings</span></div>
      <div class="stat"><b>{strong}</b><span>rated strong</span></div>
      <div class="stat"><b>{sc.rupees(cheapest_seven) if cheapest_seven else '—'}</b><span>cheapest 7-seater</span></div>
      <div class="stat"><b>{evs}</b><span>electric</span></div>
      <div class="stat"><b>{cut}</b><span>hidden below {MIN_SCORE}</span></div>
    </div>
  </header>

  <div class="controls">
    <div class="seg" data-role="tier" role="group" aria-label="Filter by deal tier">
      <button data-tier="all" aria-pressed="true">All</button>
      <button data-tier="strong" aria-pressed="false">Strong</button>
      <button data-tier="fair" aria-pressed="false">Fair</button>
      <button data-tier="rich" aria-pressed="false">Rich</button>
    </div>
    <span class="spacer"></span>
    <label class="sort" for="sort">Sort
      <select id="sort">
        <option value="score">Deal score</option>
        <option value="price">Price, low first</option>
        <option value="km">Odometer, low first</option>
        <option value="year">Newest first</option>
      </select>
    </label>
  </div>

  {''.join(body)}

  <section class="method">
    <h2>How the deal score works</h2>
    <p class="legend">
      <span><i style="background:var(--strong)"></i>Strong — 68+</span>
      <span><i style="background:var(--fair)"></i>Fair — 50-67</span>
      <span><i style="background:var(--rich)"></i>Rich — 40-49</span>
    </p>
    <p>Everything here sits inside your budget: ₹20L for a seven-seater, ₹11L
      for a sub-compact, both under 30,000 km. Electric cars are included on the
      same terms rather than in a group of their own — if an EV does not clear
      the cap, it does not appear. Anything scoring under {MIN_SCORE} is dropped
      before the page is written.</p>
    <p>India has no published used-car price index, so the baseline is built,
      not looked up. Each car starts from an approximate on-road-when-new price
      for its model, discounted along a retention curve for age and adjusted for
      whether the odometer runs ahead of or behind the ~12,000 km a year a
      private car here typically covers.</p>
    <p>That estimate carries systematic bias — one curve cannot fit both a Kiger
      and an XUV700. So every car is then re-centred on the <em>median asking
      ratio of its comparables</em>: other listings of the same model where this
      list holds three or more, otherwise the whole search group. What survives
      the re-centring is the only thing worth reading — how this car is priced
      against cars you could buy instead. Ownership count, a visible markdown,
      and unusual km-per-year then adjust the number by a few points each.</p>
    <p>Two honest limits. A score near <code>50</code> means typical for its
      comparables, not good value in absolute terms — the whole segment can be
      expensive at once. And where a group is thin (the 7-seaters especially),
      the baseline is drawn across different models and the number is weak;
      each card names its own confidence.</p>
    <p><strong>Electric cars are scored on their own curve.</strong> They are
      never pooled with their petrol twins — a Nexon EV is compared to other
      Nexon EVs, never to a petrol Nexon — and they run a steeper retention
      curve, because buyers here discount an unknown battery and every new model
      year lands with more range at the same price. Battery health is the whole
      risk and the score cannot see it: get a state-of-health report, check
      whether a Tata's 8-year / 1.6-lakh-km battery warranty transfers, and for
      an MG Windsor confirm it was not sold under BaaS, where the battery is
      rented and the per-km fee continues after you buy.</p>
    <p><strong>The score reads price only.</strong> It knows nothing about
      accident history, service records or hypothecation. Nothing here is a
      valuation or advice — verify on VAHAN, check the insurance NCB for claim
      history, and get an independent inspection before any money moves.</p>
  </section>
</div>
<script>{JS}</script>
"""
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"wrote {out}  ({total} listings, {strong} strong, {evs} EV, "
          f"{cut} below score {MIN_SCORE} hidden)")
    return out


if __name__ == "__main__":
    render(collect())
