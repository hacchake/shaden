# -*- coding: utf-8 -*-
"""4つの地図をひとつにまとめた「社伝地図」(atlas.html) 用のデータを書き出す。

社伝マップ(map.json)と同じ中身に、次を足す。
  - 例祭の日付表記  近くの神社まつり と同じく、次回の開催日をページ側で計算する
  - 公式サイト
  - 饒速日鎮座録 825 件  座標のある社には地図上の点を結び付ける(at)

  python build_atlas.py   → data/atlas.json
"""
import json, io, os, re
import build_map

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "data", "atlas.json")
clean = build_map.clean


def nk(s):
    return re.sub(r"[（(〈<].*?[)）〉>]|\s|　", "", s or "")


def main():
    payload, rows, remap = build_map.build()
    pts = payload["r"]
    inv = {ni: oi for oi, ni in remap.items()}

    # r[11] 例祭 [[日付表記, 祭名, 月], ...]   r[12] 公式サイト
    nf = 0
    for ni, p in enumerate(pts):
        r = rows[inv[ni]]
        fs = []
        for f in (r.get("festivals") or []):
            if not isinstance(f, dict) or not (f.get("date_str") or f.get("month")):
                continue
            m = f["month"] if isinstance(f.get("month"), int) else 0
            fs.append([clean(f.get("date_str"), 60), clean(f.get("name"), 20), m])
            if len(fs) >= 6:
                break
        nf += len(fs)
        p.append(fs)
        p.append(clean(r.get("official_url"), 120))

    # 饒速日鎮座録。ユニット番号で地図上の点(overlay)と結ぶ
    D = json.load(io.open(os.path.join(BASE, "data/shrines.json"), encoding="utf-8"))
    u2 = {}
    for k, v in payload["ov"].items():
        for u in v["u"]:
            u2.setdefault(u, []).append(int(k))
    CH, loc = [], 0
    for r in D["rows"]:
        at = u2.get(r["unit"], [])
        if len(at) > 1:
            # 一つのユニットが複数の社に掛かるときは社名の合うものに絞る
            key = nk(r.get("name_key") or r["name"])
            near = [i for i in at if key and (key in nk(pts[i][0]) or nk(pts[i][0]) in key)]
            if near:
                at = near
        e = {"n": r["name"], "ku": r.get("kuni") or "", "gu": r.get("gun") or "",
             "pl": r.get("place") or "", "sj": r.get("saijin") or [], "rk": r.get("rank") or "",
             "si": 1 if r.get("shikinai") else 0, "de": r.get("den") or "",
             "dt": r.get("den_terms") or [], "st": r.get("shintai") or "",
             "sz": r.get("size") or [], "no": r.get("note") or "", "ly": r.get("layer") or "",
             "ti": r.get("title") or "", "yr": r.get("year") or 0, "url": r.get("url") or "",
             "ci": r.get("cites") or [], "cl": r.get("clans") or [], "kj": r.get("kanjo") or "",
             "dp": r.get("dep") or "", "un": r["unit"], "at": sorted(set(at))}
        # 空の欄は落として軽くする
        e = {k: v for k, v in e.items() if k in ("n", "un", "at") or v not in ("", [], 0)}
        loc += 1 if at else 0
        CH.append(e)
    payload["ch"] = CH

    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    print("atlas.json %.2f MB / 点 %d / 例祭 %d / 鎮座録 %d 件(地図上 %d)"
          % (os.path.getsize(OUT) / 1048576, len(pts), nf, len(CH), loc))


if __name__ == "__main__":
    main()
