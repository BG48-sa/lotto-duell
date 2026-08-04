#!/usr/bin/env python3
"""Fetch official German lottery results from cleverlotto.de into results.json.

Used by the Lotto-Duell app (index.html) to auto-fill draw results and official
prize quotas. Covers: 6aus49 (+ Superzahl), Spiel 77, Super 6 (Wed + Sat draws)
and Gluecksspirale (Sat). Incremental: dates already present are skipped.
"""
import datetime
import json
import os
import re
import time
import urllib.request

BASE = "https://www.cleverlotto.de"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.json")
DAYS_BACK = 21


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")


def visible(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", h)


def deamount(s):
    return float(s.replace(".", "").replace(",", "."))


def parse_quotas(block, n_classes):
    """'Klasse 1 0 x 6 Richtige + SZ Unbesetzt Klasse 2 ...' -> {klasse: amount|None}"""
    q = {}
    for m in re.finditer(r"Klasse (\d+) [\d.,]+ x [^K€]*?(Unbesetzt|[\d.]+,\d\d) ?€?", block):
        k = int(m.group(1))
        if 1 <= k <= n_classes:
            q[k] = None if m.group(2) == "Unbesetzt" else deamount(m.group(2))
    return q


def check_date(text, iso):
    dd = ".".join(reversed(iso.split("-")))
    return f"Ziehungsdatum" in text and dd in text[: max(text.find("Archiv"), 400)]


def fetch_lotto(iso):
    t = visible(get(f"{BASE}/lotto-zahlen?date={iso}"))
    if not check_date(t, iso):
        return None
    m = re.search(r"((?:\d{1,2} ){6})SZ (\d) (\d{7}) (\d{6})", t)
    if not m:
        return None
    nums = sorted(int(x) for x in m.group(1).split())
    blocks = [b for b in t.split("Gewinnquoten") if re.search(r"Klasse 1 ", b)]
    q49 = parse_quotas(blocks[0], 9) if len(blocks) > 0 else {}
    qs77_raw = parse_quotas(blocks[1], 7) if len(blocks) > 1 else {}
    qs6_raw = parse_quotas(blocks[2], 6) if len(blocks) > 2 else {}
    # page Klasse k -> matched trailing digits: Spiel77 t=8-k, Super6 t=7-k
    qs77 = {8 - k: v for k, v in qs77_raw.items()}
    qs6 = {7 - k: v for k, v in qs6_raw.items()}
    return {"nums": nums, "sz": int(m.group(2)), "s77": m.group(3), "s6": m.group(4),
            "quotas49": q49, "quotasS77": qs77, "quotasS6": qs6}


GS_PAT = re.compile(
    r"GK 7 (\d{7})(?: GK 7 (\d{7}))? GK 6 I I (\d{6}) GK 6 I (\d{6}) GK 5 (\d{5}) "
    r"GK 4 (\d{4}) GK 3 (\d{3}) GK 2 (\d{2}) GK 1 (\d)"
)


def fetch_gs(iso):
    t = visible(get(f"{BASE}/gluecksspirale-zahlen?date={iso}"))
    if not check_date(t, iso):
        return None
    m = GS_PAT.search(t)
    if not m:
        return None
    return {"k7a": m.group(1), "k7b": m.group(2) or "", "k6a": m.group(4), "k6b": m.group(3),
            "k5": m.group(5), "k4": m.group(6), "k3": m.group(7), "k2": m.group(8), "k1": m.group(9)}


def main():
    data = {"updated": None, "lotto": {}, "gs": {}}
    if os.path.exists(OUT):
        try:
            with open(OUT) as f:
                old = json.load(f)
            data["lotto"] = old.get("lotto", {})
            data["gs"] = old.get("gs", {})
        except Exception:
            pass

    today = datetime.date.today()
    fetched = 0
    for back in range(DAYS_BACK, -1, -1):
        d = today - datetime.timedelta(days=back)
        iso = d.isoformat()
        wd = d.weekday()  # Mon=0 .. Wed=2 .. Sat=5
        try:
            if wd in (2, 5) and iso not in data["lotto"]:
                r = fetch_lotto(iso)
                if r:
                    data["lotto"][iso] = r
                    fetched += 1
                    print(f"lotto {iso}: {r['nums']} SZ {r['sz']} S77 {r['s77']} S6 {r['s6']}")
                time.sleep(0.4)
            if wd == 5 and iso not in data["gs"]:
                r = fetch_gs(iso)
                if r:
                    data["gs"][iso] = r
                    fetched += 1
                    print(f"gs    {iso}: GK7 {r['k7a']}")
                time.sleep(0.4)
        except Exception as e:
            print(f"{iso}: FAILED {e}")

    data["updated"] = datetime.datetime.now().isoformat(timespec="minutes")
    with open(OUT, "w") as f:
        json.dump(data, f)
    print(f"DONE: {fetched} new draws, {len(data['lotto'])} lotto / {len(data['gs'])} gs total -> {OUT}")


if __name__ == "__main__":
    main()
