"""
Penny corporate-fundamentals fetcher (promoter holding % + P/B ratio).

[PENNY-CORP-FETCHER 2026-07-16] Kite Connect does not expose corporate
fundamentals (get_corporate_actions() returns [] by design), and the operator-
curated penny_company_data.json had never been populated -- so every penny
universe refresh produced 100/100 null promoter_holding_pct and pb_ratio,
corp_source="missing". Because the promoter (>25% & <75%) and P/B (<=2.0) gates
in penny_universe.eligible_tickers() are null-tolerant, penny breakouts were
being accepted with those two safety gates silently bypassed.

This fetcher populates the tier-2/tier-3 corp-data file that
penny_universe.refresh_from_kite() reads (corp_json_path). Source is
screener.in, which aggregates promoter holding from BSE/NSE quarterly
shareholding filings and carries current price + book value (P/B is derived
price / book, or read directly when present).

Output schema (matches corp_by_sym = {c["symbol"]: c} in penny_universe.py):

    {
      "as_of": "YYYY-MM-DD",
      "source": "screener.in",
      "records": [
        {"symbol": "PCJEWELLER", "promoter_holding_pct": 38.5, "pb_ratio": 1.1},
        ...
      ]
    }

Run as a DRY RUN first (default): writes to the --out path and prints a
coverage report. It NEVER touches live gating on its own -- an operator points
PENNY_CORP_DATA_JSON_PATH at the reviewed file (or drops it at the repo seed)
and the next penny_universe_refresh picks it up.

Usage:
    python penny_corp_fetcher.py --universe /data/penny_static.json \
        --out /data/penny_company_data.json [--delay 1.5] [--limit N]
"""
import argparse
import json
import re
import sys
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def _num(text):
    """First numeric token in a string, as float, or None."""
    if not text:
        return None
    m = re.search(r"-?[\d,]+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def fetch_one(symbol, session, timeout=15, max_retries=3, backoff=15.0):
    """Fetch {promoter_holding_pct, pb_ratio} for one NSE symbol.

    Returns (record, note). `record` always has the two keys (value or None);
    `note` is a short string for the coverage log ("ok", "no_page",
    "neg_book_value", "no_book", "no_promoter", ...).
    """
    rec = {"symbol": symbol, "promoter_holding_pct": None, "pb_ratio": None}
    notes = []
    resp = None
    # screener uses the raw symbol; a few names only exist under /consolidated/.
    for suffix in ("", "/consolidated/"):
        url = f"https://www.screener.in/company/{symbol}{suffix}"
        # 429 backoff: screener.in throttles aggressive sequential scraping.
        # Respect Retry-After when present, otherwise exponential backoff.
        for attempt in range(max_retries + 1):
            try:
                r = session.get(url, headers=HEADERS, timeout=timeout)
            except requests.RequestException as e:
                notes.append(f"req_error:{type(e).__name__}")
                break
            if r.status_code == 200:
                resp = r
                break
            if r.status_code == 429 and attempt < max_retries:
                wait = float(r.headers.get("Retry-After") or 0) or (backoff * (2 ** attempt))
                time.sleep(min(wait, 120))
                continue
            notes.append(f"http_{r.status_code}")
            break
        if resp is not None:
            break
    if resp is None:
        return rec, "no_page(" + ",".join(notes) + ")"

    soup = BeautifulSoup(resp.text, "html.parser")

    # --- Promoter holding: latest quarter in the shareholding table ---
    sh = soup.find("section", id="shareholding")
    if sh:
        for row in sh.find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if cells and re.match(r"promoter", cells[0], re.I):
                pcts = [c for c in cells[1:] if re.match(r"^[0-9.]+\s*%?$", c)]
                if pcts:
                    rec["promoter_holding_pct"] = _num(pcts[-1])  # latest quarter
                break
    if rec["promoter_holding_pct"] is None:
        # Fallback: the "Promoter Holding: NN%" inline text.
        m = re.search(r"Promoter[^0-9%]{0,20}([0-9]{1,3}(?:\.[0-9]+)?)\s*%", resp.text)
        if m:
            rec["promoter_holding_pct"] = float(m.group(1))
    p = rec["promoter_holding_pct"]
    if p is None:
        notes.append("no_promoter")
    elif not (0 <= p <= 100):
        rec["promoter_holding_pct"] = None
        notes.append(f"promoter_out_of_range:{p}")

    # --- P/B: read Book Value + Current Price from top-ratios, derive P/B ---
    price = book = pb_direct = None
    top = soup.find("ul", id="top-ratios")
    if top:
        for li in top.find_all("li"):
            name_el = li.find("span", class_="name")
            val_el = li.find("span", class_="value") or li.find("span", class_="number")
            if not name_el:
                continue
            name = name_el.get_text(" ", strip=True).lower()
            val = val_el.get_text(" ", strip=True) if val_el else ""
            if "current price" in name:
                price = _num(val)
            elif "book value" in name:
                book = _num(val)
            elif "price to book" in name or name.strip() in ("p/b", "pb"):
                pb_direct = _num(val)
    if pb_direct is not None:
        rec["pb_ratio"] = pb_direct
    elif price is not None and book is not None:
        if book <= 0:
            # Negative/zero book value (e.g. IDEA) makes P/B meaningless AND
            # dangerous: a naive negative ratio would PASS the pb<=2.0 gate.
            # Leave null so the gate treats it as unknown, and flag it loudly.
            notes.append(f"neg_book_value:{book}")
        else:
            rec["pb_ratio"] = round(price / book, 2)
    else:
        notes.append("no_book" if book is None else "no_price")

    return rec, ("ok" if not notes else ",".join(notes))


def load_symbols(universe_path):
    with open(universe_path) as f:
        d = json.load(f)
    tickers = d.get("tickers", d) if isinstance(d, dict) else d
    return [t["symbol"] for t in tickers if isinstance(t, dict) and t.get("symbol")]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fetch penny corp fundamentals from screener.in")
    ap.add_argument("--universe", default="/data/penny_static.json",
                    help="penny universe JSON with a 'tickers' list of {symbol}")
    ap.add_argument("--out", default="/data/penny_company_data.json",
                    help="output penny_company_data.json path")
    ap.add_argument("--delay", type=float, default=1.5,
                    help="seconds between requests (be polite to screener.in)")
    ap.add_argument("--limit", type=int, default=0, help="only fetch first N (0=all)")
    args = ap.parse_args(argv)

    symbols = load_symbols(args.universe)
    if args.limit:
        symbols = symbols[: args.limit]
    print(f"[penny_corp_fetcher] {len(symbols)} symbols from {args.universe}", file=sys.stderr)

    session = requests.Session()
    records = []
    n_prom = n_pb = 0
    flagged = []
    for i, sym in enumerate(symbols, 1):
        rec, note = fetch_one(sym, session)
        records.append(rec)
        if rec["promoter_holding_pct"] is not None:
            n_prom += 1
        if rec["pb_ratio"] is not None:
            n_pb += 1
        if note != "ok":
            flagged.append((sym, note))
        print(f"  [{i:>3}/{len(symbols)}] {sym:<14} "
              f"prom={rec['promoter_holding_pct']} pb={rec['pb_ratio']} ({note})",
              file=sys.stderr)
        if i < len(symbols):
            time.sleep(args.delay)

    out = {
        "as_of": date.today().isoformat(),
        "source": "screener.in",
        "records": records,
    }
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)

    n = len(symbols)
    print("\n===== COVERAGE =====", file=sys.stderr)
    print(f"  symbols          : {n}", file=sys.stderr)
    print(f"  promoter filled  : {n_prom}/{n} ({100*n_prom//max(n,1)}%)", file=sys.stderr)
    print(f"  pb filled        : {n_pb}/{n} ({100*n_pb//max(n,1)}%)", file=sys.stderr)
    print(f"  flagged/partial  : {len(flagged)}", file=sys.stderr)
    for sym, note in flagged:
        print(f"      {sym:<14} {note}", file=sys.stderr)
    print(f"\n  wrote {args.out} (DRY RUN -- not wired into live gating)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
