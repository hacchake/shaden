# -*- coding: utf-8 -*-
"""戦前の神社誌・郡誌などを NDL から取得し、vols.json に登録する。

  python fetch_vols.py seed              既知の神社誌を登録(取得はしない)
  python fetch_vols.py add <pid> [ラベル]  1冊を登録
  python fetch_vols.py bulk [N]          candidates.json の上位 N 冊を登録
  python fetch_vols.py get [--limit N]   未取得の巻を落とす
  python fetch_vols.py stat              登録・取得状況
"""
import json, io, os, sys, time, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
JD = os.path.join(BASE, "data", "jinjashi")
REG = os.path.join(JD, "vols.json")
UA = "shaden-research/1.0 (academic study of shrine records; contact hacchake@gmail.com)"

SEED = {
    "1088244": "明治神社誌料 府県郷社 上", "1088278": "明治神社誌料 府県郷社 中",
    "1088313": "明治神社誌料 府県郷社 下",
    "943709": "三重県神社誌 1", "943710": "三重県神社誌 2",
    "943711": "三重県神社誌 3", "943712": "三重県神社誌 4",
    "1050476": "鳥取県神社誌", "1227836": "香川県神社誌 1", "1227849": "香川県神社誌 2",
    "1040130": "福岡県神社誌 1", "1040137": "福岡県神社誌 2", "1040147": "福岡県神社誌 3",
    "1214439": "宮崎県神社誌", "971197": "佐渡神社誌", "1035221": "壱岐国神社誌",
    "1214266": "参河国額田郡神社誌", "1031342": "大里郡神社誌", "1049148": "北豊島郡神社誌",
    # 追加分
    "1040131": "島根県神社概説", "1105182": "大日本神社大鑑",
    "1234756": "大日本神社誌写真大鑑", "1120905": "岩手県神社事務提要",
    "1033002": "児玉郡神社一覧", "943713": "大野郡祭神記", "909821": "佐波郡神社誌",
    "956266": "愛媛県管内神社一覧", "1052900": "富士郡神社銘鑑",
    "1022804": "長崎神社巡り", "951174": "大日本神名辞書",
    "815432": "下野神社沿革誌 1", "815433": "下野神社沿革誌 2",
    "815434": "下野神社沿革誌 3", "815435": "下野神社沿革誌 4",
    "815436": "下野神社沿革誌 5", "815437": "下野神社沿革誌 6",
    "815439": "下野神社沿革誌 7",
}


def load():
    return json.load(io.open(REG, encoding="utf-8")) if os.path.exists(REG) else {}


def save(v):
    os.makedirs(JD, exist_ok=True)
    json.dump(v, io.open(REG, "w", encoding="utf-8"), ensure_ascii=False, indent=0)


def cmd_seed(_):
    v = load()
    for pid, lab in SEED.items():
        v.setdefault(pid, {"label": lab, "pref": "auto"})
    save(v)
    print("登録 %d 巻" % len(v))


def cmd_bulk(a):
    n = int(a[0]) if a else 300
    cand = json.load(io.open(os.path.join(JD, "candidates.json"), encoding="utf-8"))
    v = load()
    added = 0
    for c in cand[:n]:
        pid = str(c["pid"])
        if pid in v:
            continue
        v[pid] = {"label": "%s(%s)" % (c["title"][:26], c["year"]), "pref": "auto"}
        added += 1
    save(v)
    print("追加 %d 巻 / 登録計 %d 巻" % (added, len(v)))


def cmd_add(a):
    v = load()
    v[str(a[0])] = {"label": a[1] if len(a) > 1 else str(a[0]), "pref": "auto"}
    save(v)
    print("登録", a[0])


def cmd_get(a):
    lim = int(a[a.index("--limit") + 1]) if "--limit" in a else None
    v = load()
    todo = [p for p in v if not os.path.exists(os.path.join(JD, "%s.json" % p))]
    if lim:
        todo = todo[:lim]
    print("未取得 %d 巻" % len(todo))
    ok = ng = chars = 0
    for i, pid in enumerate(todo, 1):
        u = "https://lab.ndl.go.jp/dl/api/book/fulltext-json/%s" % pid
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            d = json.loads(urllib.request.urlopen(req, timeout=300).read().decode("utf-8"))
        except Exception as e:
            ng += 1
            sys.stderr.write("ERR %s %s\n" % (pid, str(e)[:50]))
            time.sleep(1.0)
            continue
        L = [{"page": x.get("page"), "contents": x.get("contents") or ""}
             for x in d.get("list", [])]
        c = sum(len(x["contents"]) for x in L)
        json.dump({"pid": int(pid), "label": v[pid]["label"], "list": L},
                  io.open(os.path.join(JD, "%s.json" % pid), "w", encoding="utf-8"),
                  ensure_ascii=False)
        ok += 1
        chars += c
        if ok % 20 == 0:
            sys.stderr.write("  %d/%d ok=%d ng=%d %.1f百万字\n"
                             % (i, len(todo), ok, ng, chars / 1e6))
        time.sleep(0.4)
    print("取得 %d 巻 / 失敗 %d / 計 %.1f 百万字" % (ok, ng, chars / 1e6))


def cmd_stat(_):
    v = load()
    have = [p for p in v if os.path.exists(os.path.join(JD, "%s.json" % p))]
    print("登録 %d 巻 / 取得済み %d 巻" % (len(v), len(have)))


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else ""
    {"seed": cmd_seed, "bulk": cmd_bulk, "add": cmd_add,
     "get": cmd_get, "stat": cmd_stat}.get(c, lambda _: print(__doc__))(sys.argv[2:])
