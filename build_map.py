# -*- coding: utf-8 -*-
"""地理院タイルに重ねる地図(map.html)用のデータを書き出す。

アーティファクトと違い GitHub Pages には外部取得の制限がないので、
データは HTML に埋め込まず JSON として置き、fetch で読ませる。
Pages は JSON を gzip で配信するため、10MB 級でも実転送は 1/3 程度になる。
"""
import json, io, os, re, glob

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "data", "map.json")


def clean(s, n=None):
    s = (s or "").replace("\r", "")
    s = re.sub(r"[ \t　]+", " ", s)
    s = re.sub(r"\n{2,}", "\n", s).strip()
    return s[:n] if n else s


def main():
    rows = json.load(io.open(os.path.join(BASE, "data/shrinemap/data.json"), encoding="utf-8"))
    ov = json.load(io.open(os.path.join(BASE, "data/shrinemap/overlay.json"), encoding="utf-8"))

    scraped = {}
    for p in sorted(glob.glob(os.path.join(BASE, "data/shaden/*.jsonl"))):
        for l in io.open(p, encoding="utf-8"):
            try:
                r = json.loads(l)
            except Exception:
                continue
            scraped[r["source_url"]] = r

    PREFS = sorted({r["pref"] for r in rows})
    SRCS = sorted({r["source"] for r in rows})
    pi = {p: i for i, p in enumerate(PREFS)}
    si = {s: i for i, s in enumerate(SRCS)}

    pts, remap, JJ = [], {}, {}
    for oi, r in enumerate(rows):
        la, ln = r.get("lat"), r.get("lng")
        if not (isinstance(la, (int, float)) and isinstance(ln, (int, float))):
            continue
        ms = sorted({f["month"] for f in (r.get("festivals") or [])
                     if isinstance(f, dict) and isinstance(f.get("month"), int)
                     and 1 <= f["month"] <= 12})
        fd = ""
        for f in (r.get("festivals") or []):
            if isinstance(f, dict) and f.get("date_str"):
                fd = clean(f["date_str"], 40); break
        ad = clean(r.get("address"), 48)
        for p in PREFS:
            if ad.startswith(p):
                ad = ad[len(p):]; break
        ni = len(pts)
        remap[oi] = ni
        pts.append([clean(r["name"], 34), pi[r["pref"]], round(la, 5), round(ln, 5), ad,
                    clean(r.get("deity"), 90), ms, fd, si[r["source"]],
                    1 if r.get("type") == "temple" else 0,
                    clean(r.get("source_url"), 120)])

        sc = scraped.get(r.get("source_url") or "")
        if sc:
            memo = []
            if sc.get("shitei"):  memo.append("指定: " + clean(sc["shitei"], 200))
            if sc.get("keidai"):  memo.append("境内: " + clean(sc["keidai"], 60))
            if sc.get("massha"):  memo.append("摂末社: " + clean(sc["massha"], 200))
            if sc.get("sonota"):  memo.append(clean(sc["sonota"], 300))
            e = {}
            sk = sc.get("shakaku") or ""
            if sk in ("式内社", "式內社"):
                e["ik"] = 1
            elif sk:
                e["sk"] = sk
            if "式内" in (sc.get("shakaku_raw") or "") or "式内" in (sc.get("shitei") or ""):
                e["ik"] = 1
            sd = clean(sc.get("yuisho"), 1400)   # 外部ファイルなので全文に近い長さで持てる
            if sd:
                e["sd"] = sd
            if memo:
                e["memo"] = clean("／".join(memo), 500)
            if sc.get("yomi"):
                e["yomi"] = clean(sc["yomi"], 30)
            if e:
                JJ[str(ni)] = e

    OV = {str(remap[int(k)]): v for k, v in ov.items() if int(k) in remap}

    # 由緒板
    BDS = {}
    bp = os.path.join(BASE, "data/boards/boards.json")
    if os.path.exists(bp):
        for br in json.load(io.open(bp, encoding="utf-8")):
            if not br.get("text"):
                continue
            la, ln = br.get("lat"), br.get("lng")
            if la is None:
                continue
            best, bd = None, 9e9
            for ni, rec in enumerate(pts):
                if br.get("pref") and PREFS[rec[1]] != br["pref"]:
                    continue
                d = (rec[2] - la) ** 2 + (rec[3] - ln) ** 2
                if d < bd:
                    bd, best = d, ni
            if best is not None and bd < (0.003 ** 2) * 2:
                nm = re.sub(r"[（(].*?[)）]", "", br.get("name") or "")
                if not nm or nm in pts[best][0] or pts[best][0] in nm:
                    BDS[str(best)] = {"t": clean(br["text"], 3000), "at": br.get("at", "")}

    # 戦前地誌(書誌とリンクのみ。本文は NDL 側で読む)
    GZ, VOLIX = {}, {}
    gp = os.path.join(BASE, "data/jinjashi/best.json")
    if os.path.exists(gp):
        for k, v in json.load(io.open(gp, encoding="utf-8")).items():
            ni = remap.get(int(k))
            if ni is None:
                continue
            mm = re.search(r"/pid/(\d+)/1/(\d+)", v.get("u") or "")
            g = {"v": VOLIX.setdefault(v["v"], len(VOLIX)),
                 "p": int(mm.group(1)) if mm else 0,
                 "k": int(mm.group(2)) if mm else 0,
                 "r": v.get("r", ""), "c": v.get("c", "B")}
            for a, b in (("k", "kw"), ("e", "e"), ("kj", "kj")):
                if v.get(a):
                    g[b] = v[a][:5] if isinstance(v[a], list) else v[a]
            GZ[str(ni)] = g

    # Wikipedia
    WK = {}
    wm = os.path.join(BASE, "data/wiki/wiki_match.json")
    ws = os.path.join(BASE, "data/wiki/wiki_shaden.jsonl")
    if os.path.exists(wm) and os.path.exists(ws):
        wt = {}
        for l in io.open(ws, encoding="utf-8"):
            w = json.loads(l)
            wt[w["title"]] = w
        for k, title in json.load(io.open(wm, encoding="utf-8")).items():
            ni = remap.get(int(k))
            w = wt.get(title)
            if ni is not None and w:
                WK[str(ni)] = {"t": clean(w["text"], 1400), "n": title}

    vols = [k for k, _ in sorted(VOLIX.items(), key=lambda x: x[1])]
    payload = {"p": PREFS, "s": SRCS, "vols": vols,
               "r": pts, "jj": JJ, "gz": GZ, "wk": WK, "bd": BDS, "ov": OV}
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    n = os.path.getsize(OUT)
    print("map.json %.2f MB / 点 %d / 神社庁 %d / 地誌 %d / Wikipedia %d / 由緒板 %d / 饒速日 %d"
          % (n / 1048576, len(pts), len(JJ), len(GZ), len(WK), len(BDS), len(OV)))


if __name__ == "__main__":
    main()
