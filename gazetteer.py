# -*- coding: utf-8 -*-
"""戦前の神社誌(NDL)から、各社の由緒を社名で引き当てて切り出す。

明治神社誌料のように表組みのOCRが列崩れしている本は完全な構造化ができない。
そこで「社名で検索し、住所語が同じコマにあるものを採り、前後を窓で切る」方式にする。
これは既存の units.jsonl と同じ考え方で、原文の所在(pid/koma)を必ず残す。

  python gazetteer.py index          巻ごとにコマ本文を正規化して索引を作る
  python gazetteer.py match [県名]   data.json の社に引き当てる → data/jinjashi/match.jsonl
"""
import json, io, os, re, sys, glob, collections

BASE = os.path.dirname(os.path.abspath(__file__))
JD = os.path.join(BASE, "data", "jinjashi")

VOLREG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jinjashi", "vols.json")

PREF_NAMES = ["北海道","青森","岩手","宮城","秋田","山形","福島","茨城","栃木","群馬","埼玉",
 "千葉","東京","神奈川","新潟","富山","石川","福井","山梨","長野","岐阜","静岡","愛知","三重",
 "滋賀","京都","大阪","兵庫","奈良","和歌山","鳥取","島根","岡山","広島","山口","徳島","香川",
 "愛媛","高知","福岡","佐賀","長崎","熊本","大分","宮崎","鹿児島","沖縄"]
PREF_FULL = {p: (p if p in ("北海道","東京","京都","大阪") else p + "県") for p in PREF_NAMES}
PREF_FULL["東京"] = "東京都"; PREF_FULL["京都"] = "京都府"; PREF_FULL["大阪"] = "大阪府"


def load_vols():
    if os.path.exists(VOLREG):
        return json.load(io.open(VOLREG, encoding="utf-8"))
    return {}


def guess_pref(text, title=""):
    """本文と書名から、その巻が扱う都道府県を推定する。全国ものは None。"""
    cnt = {}
    for p in PREF_NAMES:
        n = text.count(p)
        if n:
            cnt[p] = n
    if not cnt:
        return None
    top = sorted(cnt.items(), key=lambda x: -x[1])
    # 書名に県名があればそれを優先
    for p in PREF_NAMES:
        if p in title:
            return PREF_FULL[p]
    # 一位が二位の3倍以上あればその県のものと見なす
    if len(top) == 1 or top[0][1] >= max(3 * top[1][1], 40):
        return PREF_FULL[top[0][0]]
    return None


NK = str.maketrans("眞淸邊縣靈龍瀨賣濱嶋嶽彥國舊藏齋禰樣爲號權廣豐榮變應會鹽澤鬪擧與豫",
                   "真清辺県霊竜瀬売浜島岳彦国旧蔵斎祢様為号権広豊栄変応会塩沢闘挙与予")
RANK = re.compile(r"(別格官幣社|官幣大社|官幣中社|官幣小社|国幣大社|国幣中社|国幣小社|"
                  r"県社|郷社|村社|無格社)")


def norm(s):
    s = (s or "").translate(NK)
    s = re.sub(r"[〈（(].*?[〉）)]", "", s)
    return re.sub(r"[\s　・･,、。〓\-—―]", "", s)


def cmd_index(_):
    vols = load_vols()
    idx = {}
    for pid, meta in vols.items():
        p = os.path.join(JD, "%s.json" % pid)
        if not os.path.exists(p):
            continue
        d = json.load(io.open(p, encoding="utf-8"))
        komas = [{"k": x["page"], "t": norm(x["contents"])} for x in d["list"]
                 if len(x["contents"]) > 200]
        if not komas:
            continue
        pref = meta.get("pref")
        if pref == "auto" or not pref:
            sample = "".join(k["t"] for k in komas[:80])
            pref = guess_pref(sample, meta.get("label", ""))
        idx[str(pid)] = {"label": meta.get("label", pid), "pref": pref, "komas": komas}
    json.dump(idx, io.open(os.path.join(JD, "index.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    npref = sum(1 for v in idx.values() if v["pref"])
    print("索引 %d 巻 / 県を特定できた巻 %d" % (len(idx), npref))


_CITY2GUN = None


def city2gun():
    """現在の市町村名 → 明治期の郡名。戦前の地誌は郡+村で書くので橋渡しに要る。"""
    global _CITY2GUN
    if _CITY2GUN is None:
        _CITY2GUN = collections.defaultdict(set)
        p = os.path.join(JD, "gun2city.json")
        if os.path.exists(p):
            for gun, cities in json.load(io.open(p, encoding="utf-8")).items():
                if not (2 <= len(gun) <= 5):
                    continue
                for c in cities:
                    c = re.sub(r"[市町村]$", "", c)
                    if 2 <= len(c) <= 6:
                        _CITY2GUN[c].add(gun)
    return _CITY2GUN


def addr_tokens(r):
    """住所から照合語を取り出す。

    現代表記「君津市旅名132番地」の「旅名」は、戦前の「望陀郡◯◯村大字旅名」の
    大字がそのまま残ったもの。郡名より当てになるので必ず拾う。
    """
    a = norm(r.get("address") or "")
    t = set()
    for m in re.finditer(r"([^\d]{1,6}?)(郡|市|町|村)", a):
        w = m.group(1)
        if 1 < len(w) <= 5:
            t.add(w)
    # 市町村の直後(=旧大字)
    m = re.search(r"(?:市|町|村)(?:大字)?([^\d字]{2,6})", a)
    if m:
        t.add(m.group(1))
        if len(m.group(1)) > 2:
            t.add(m.group(1)[:-1])      # 「賀露町北」→「賀露町」も許す
    # 字名
    m = re.search(r"字([^\d]{2,5})", a)
    if m:
        t.add(m.group(1))
    # 現市町村名から明治期の郡名を足す(「君津市」→「望陀」「周淮」など)
    c2g = city2gun()
    for w in list(t):
        for gun in c2g.get(w, ()):
            t.add(gun)
    return {x for x in t if len(x) >= 2}


def cmd_match(a):
    only = a[0] if a else None
    idx = json.load(io.open(os.path.join(JD, "index.json"), encoding="utf-8"))
    rows = json.load(io.open(os.path.join(BASE, "data/shrinemap/data.json"), encoding="utf-8"))
    byp = collections.defaultdict(list)
    for i, r in enumerate(rows):
        byp[r["pref"]].append(i)

    NAMEPAT = re.compile(r"[一-鿿]{2,8}(?:神社|神宮|大社|八幡宮|天満宮|宮)")
    out = io.open(os.path.join(JD, "match.jsonl"), "w", encoding="utf-8")
    hit = 0
    for pid, v in idx.items():
        pref = v["pref"]
        if only and pref and pref != only:
            continue
        if pref:
            targets = byp[pref]
        elif only:
            targets = byp[only]
        else:
            targets = [i for p_ in byp for i in byp[p_]]

        joined, pos, off = [], [], 0
        for km in v["komas"]:
            joined.append(km["t"])
            pos.append((off, off + len(km["t"]), km["k"]))
            off += len(km["t"])
        big = "".join(joined)

        # 社名辞書(正規化 → 該当する社の添字)
        name2idx = collections.defaultdict(list)
        for i in targets:
            nm0 = re.sub(r"[〈《].*$", "", norm(rows[i]["name"]))
            if len(nm0) >= 3:
                name2idx[nm0].append(i)

        # 本文から社名らしい語を拾い、辞書に当たるものだけ位置を記録する
        occ = collections.defaultdict(list)
        for m in NAMEPAT.finditer(big):
            w = m.group(0)
            for L in range(min(len(w), 8), 2, -1):
                cand = w[-L:]
                if cand in name2idx:
                    occ[cand].append(m.end() - L)
                    break

        vhit = 0
        for nm, positions in occ.items():
            for i in name2idx[nm]:
                r = rows[i]
                toks = addr_tokens(r)
                pn = norm(r["pref"])
                base_ = pn[:-1] if pn[-1] in "県府都" else pn
                best = None
                for s in positions:
                    e = s + len(nm)
                    win = big[max(0, s - 120):min(len(big), e + 560)]
                    ah = sum(1 for t in toks if t in win)
                    sc = ah * 2
                    if re.search(r"(鎮座|鎭座|祭神|由緒|由緖)", big[e:e + 60]):
                        sc += 2
                    if not re.search(r"(由緒|由緖|祭神)", win):
                        sc -= 3
                    if len(re.findall(r"(元年|二年|三年|四年|五年)", win)) >= 6:
                        sc -= 3
                    if pref is None and base_ not in win:
                        sc -= 6
                    if best is None or (ah > 0, sc) > (best[4] > 0, best[0]):
                        best = (sc, s, e, win, ah)
                if not best:
                    continue
                sc, s, e, win, ah = best
                # A = 郡・町村・大字まで一致 / B = 社名と見出し位置のみ
                conf = "A" if ah > 0 and sc >= 3 else ("B" if sc >= 2 else "")
                if not conf:
                    continue
                k = next((kk for a_, b_, kk in pos if a_ <= s < b_), None)
                rk = RANK.search(big[max(0, s - 60):e + 40])
                out.write(json.dumps({
                    "i": i, "name": r["name"], "pref": r["pref"],
                    "vol": v["label"], "pid": int(pid), "koma": k, "score": sc,
                    "conf": conf,
                    "rank": rk.group(1) if rk else "",
                    "text": win,
                    "url": "https://dl.ndl.go.jp/pid/%s/1/%s" % (pid, k),
                }, ensure_ascii=False) + "\n")
                hit += 1; vhit += 1
        print("%-24s 対象 %6d / 引当 %5d" % (v["label"], len(targets), vhit))
    out.close()
    print("合計 引当 %d 件" % hit)


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else ""
    {"index": cmd_index, "match": cmd_match}.get(c, lambda _: print(__doc__))(sys.argv[2:])
