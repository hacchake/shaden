# -*- coding: utf-8 -*-
"""社伝点描図のHTMLを組み立てる。data/shaden/*.jsonl を随時取り込めるよう分離した。

  python build_tenbyo.py
"""
import json, io, os, re, glob, collections

BASE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(BASE, "tenbyo.tpl.html")
OUT = os.path.join(BASE, "tenbyo.html")

SHAKAKU_ORD = ["別格官幣社", "官幣大社", "官幣中社", "官幣小社",
               "国幣大社", "国幣中社", "国幣小社", "県社", "郷社", "村社", "無格社"]


def clean(s, n=None):
    s = (s or "").replace("\r", "")
    s = re.sub(r"[ \t　]+", " ", s)
    s = re.sub(r"\n{2,}", "\n", s).strip()
    return s[:n] if n else s


def main():
    rows = json.load(io.open(os.path.join(BASE, "data/shrinemap/data.json"), encoding="utf-8"))
    ov = json.load(io.open(os.path.join(BASE, "data/shrinemap/overlay.json"), encoding="utf-8"))

    # ── 採取した社伝を source_url で引けるようにする
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

    out, remap, JJ = [], {}, {}
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
                fd = clean(f["date_str"], 30); break
        ad = clean(r.get("address"), 40)
        for p in PREFS:
            if ad.startswith(p):
                ad = ad[len(p):]; break
        ni = len(out)
        remap[oi] = ni
        out.append([clean(r["name"], 26), pi[r["pref"]], round(la, 4), round(ln, 4),
                    clean(ad, 22), clean(r.get("deity"), 46), ms, clean(fd, 18),
                    si[r["source"]], 1 if r.get("type") == "temple" else 0])

        sc = scraped.get(r.get("source_url") or "")
        if sc:
            memo = []
            if sc.get("shitei"):  memo.append("指定: " + clean(sc["shitei"], 160))
            if sc.get("keidai"):  memo.append("境内: " + clean(sc["keidai"], 60))
            if sc.get("ujiko"):   memo.append("氏子: " + clean(sc["ujiko"], 60))
            if sc.get("massha"):  memo.append("摂末社: " + clean(sc["massha"], 160))
            if sc.get("sonota"):  memo.append(clean(sc["sonota"], 240))
            if sc.get("shaden"):  memo.append("社殿沿革: " + clean(sc["shaden"], 240))
            e = {}
            sk = sc.get("shakaku") or ""
            if sk == "式内社" or sk == "式內社":
                e["ik"] = 1
            elif sk:
                e["sk"] = sk
            if "式内" in (sc.get("shakaku_raw") or "") or "式内" in (sc.get("shitei") or ""):
                e["ik"] = 1
            sd = clean(sc.get("yuisho"), 150)
            if sd and not re.fullmatch(r"[　\s]*", sd):
                e["sd"] = sd
            if memo:
                e["memo"] = clean("／".join(memo), 85)
            if sc.get("yomi"):
                e["yomi"] = clean(sc["yomi"], 30)
            if e:
                if e.get("sd"):
                    e["u"] = sc.get("source_url", "")   # 表から神社庁の元頁へ飛ぶため
                JJ[str(ni)] = e

    OV = {str(remap[int(k)]): v for k, v in ov.items() if int(k) in remap}

    # ── 由緒板の翻刻を座標で最も近い社に結びつける
    BDS = {}
    bp = os.path.join(BASE, "data/boards/boards.json")
    if os.path.exists(bp):
        for br in json.load(io.open(bp, encoding="utf-8")):
            if not br.get("text"):
                continue
            la, ln = br.get("lat"), br.get("lng")
            best, bd = None, 9e9
            for ni, rec in enumerate(out):
                if la is None:
                    break
                if br.get("pref") and PREFS[rec[1]] != br["pref"]:
                    continue
                d = (rec[2] - la) ** 2 + (rec[3] - ln) ** 2
                if d < bd:
                    bd = d; best = ni
            # 約300m以内、かつ社名が一致するものに限る
            if best is not None and bd < (0.003 ** 2) * 2:
                nm = re.sub(r"[（(].*?[)）]", "", br.get("name") or "")
                if not nm or nm in out[best][0] or out[best][0] in nm:
                    BDS[str(best)] = {"t": clean(br["text"], 2400), "at": br.get("at", "")}
                else:
                    print("  近傍社の社名が合わないため未接続:", br.get("name"), "→", out[best][0])
            else:
                print("  近傍に該当社なし:", br.get("name"))

    # ── 戦前の神社誌 / Wikipedia
    GZ, WK, gaz_full, WKFULL = {}, {}, {}, {}
    VOLIX = {}
    gp = os.path.join(BASE, "data/jinjashi/best.json")
    if os.path.exists(gp):
        gaz_full = json.load(io.open(gp, encoding="utf-8"))
        for k, v in gaz_full.items():
            ni = remap.get(int(k))
            if ni is not None:
                mm = re.search(r"/pid/(\d+)/1/(\d+)", v["u"] or "")
                GZ[str(ni)] = {"v": VOLIX.setdefault(v["v"], len(VOLIX)),
                               "p": int(mm.group(1)) if mm else 0,
                               "k": int(mm.group(2)) if mm else 0,
                               "r": v.get("r", ""), "c": v.get("c", "B")}
                if v.get("k"): GZ[str(ni)]["kw"] = v["k"][:5]   # "k" はコマ番号。語は kw に分ける
                if v.get("e"): GZ[str(ni)]["e"] = v["e"][:3]
                if v.get("kj"): GZ[str(ni)]["kj"] = v["kj"][:20]
    wm = os.path.join(BASE, "data/wiki/wiki_match.json")
    ws = os.path.join(BASE, "data/wiki/wiki_shaden.jsonl")
    if os.path.exists(wm) and os.path.exists(ws):
        wtext = {}
        for l in io.open(ws, encoding="utf-8"):
            w = json.loads(l)
            wtext[w["title"]] = w
        for k, title in json.load(io.open(wm, encoding="utf-8")).items():
            ni = remap.get(int(k))
            w = wtext.get(title)
            if ni is not None and w:
                WK[str(ni)] = {"t": clean(w["text"], 150), "n": title}
                WKFULL[str(ni)] = {"t": w["text"], "n": title, "u": w["url"]}

    # ── 全文は別ファイルに出す(アーティファクトは抜粋+原典リンクに留める)
    cp = io.open(os.path.join(BASE, "data/shaden_corpus.jsonl"), "w", encoding="utf-8")
    nfull = 0
    for oi, r in enumerate(rows):
        ni = remap.get(oi)
        if ni is None:
            continue
        recs = []
        sc2 = scraped.get(r.get("source_url") or "")
        if sc2 and sc2.get("yuisho"):
            recs.append({"src": "神社庁", "site": sc2["source"],
                         "text": sc2["yuisho"], "url": sc2["source_url"],
                         "shakaku": sc2.get("shakaku", "")})
        g2 = gaz_full.get(str(oi))
        if g2:
            recs.append({"src": "戦前神社誌", "vol": g2["v"], "text": g2["t"],
                         "url": g2["u"], "shakaku": g2.get("r", "")})
        w2 = WKFULL.get(str(ni))
        if w2:
            recs.append({"src": "Wikipedia", "title": w2["n"], "text": w2["t"],
                         "url": w2["u"], "license": "CC BY-SA 4.0"})
        b2 = BDS.get(str(ni))
        if b2:
            recs.append({"src": "由緒板", "text": b2["t"], "url": ""})
        if recs:
            nfull += 1
            cp.write(json.dumps({"name": r["name"], "pref": r["pref"],
                                 "address": r.get("address", ""),
                                 "lat": r.get("lat"), "lng": r.get("lng"),
                                 "shaden": recs}, ensure_ascii=False) + "\n")
    cp.close()
    print("全文コーパス data/shaden_corpus.jsonl に %d 社" % nfull)

    esc = lambda t: t.replace("</script>", "<" + chr(92) + "/script>")
    j = lambda o: esc(json.dumps(o, ensure_ascii=False, separators=(",", ":")))
    tpl = io.open(TPL, encoding="utf-8").read()
    html = (tpl.replace("__DATA__", j({"p": PREFS, "s": SRCS, "r": out}))
               .replace("__OVER__", j(OV))
               .replace("__JINJA__", j(JJ))
               .replace("__BOARDS__", j(BDS))
               .replace("__GAZ__", j(GZ))
               .replace("__WIKI__", j(WK))
               .replace("__VOLS__", j([k for k, _ in sorted(VOLIX.items(), key=lambda x: x[1])])))
    io.open(OUT, "w", encoding="utf-8").write(html)

    nsd = sum(1 for v in JJ.values() if v.get("sd"))
    nsk = sum(1 for v in JJ.values() if v.get("sk"))
    nmm = sum(1 for v in JJ.values() if v.get("memo"))
    rc = collections.Counter(v["sk"] for v in JJ.values() if v.get("sk"))
    allsd = set(GZ) | set(WK) | set(BDS) | {k for k, v in JJ.items() if v.get("sd")}
    print("社 %d / 社伝あり %d = 神社庁 %d + 戦前神社誌 %d + Wikipedia %d + 由緒板 %d"
          % (len(out), len(allsd), nsd, len(GZ), len(WK), len(BDS)))
    print("社格 %d / メモ %d / HTML %.2f MB"
          % (nsk, nmm, len(html.encode()) / 1048576))
    print("社格内訳:", ", ".join("%s %d" % (k, n) for k, n in
          sorted(rc.items(), key=lambda x: SHAKAKU_ORD.index(x[0])
                 if x[0] in SHAKAKU_ORD else 99)))


if __name__ == "__main__":
    main()
