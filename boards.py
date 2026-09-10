# -*- coding: utf-8 -*-
"""由緒板の写真を取り込み、翻刻を溜める道具。

Google マップの自動巡回はしない(利用規約が禁じている)。
人が集めた URL を渡す半自動運用を前提とする。

  python boards.py add <URL...>          URL から画像を取得して未翻刻として登録
  python boards.py add --file urls.txt   1行1URLのファイルから一括取得
  python boards.py todo                  未翻刻の一覧(画像パスを表示。これを読んで翻刻する)
  python boards.py set <id> --text-file t.txt [--name 白山神社] [--pref 岡山県]
  python boards.py list                  登録済み一覧
  python boards.py export                data/boards/boards.json に集約(地図に載せる用)

受け付ける URL:
  - https://www.google.com/maps/place/... (中に埋まった lh3 の画像URLを取り出す)
  - https://lh3.googleusercontent.com/... (直接)
"""
import json, io, os, re, sys, time, hashlib, urllib.request, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
BD = os.path.join(BASE, "data", "boards")
IMG = os.path.join(BD, "img")
DB = os.path.join(BD, "index.jsonl")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) shaden-research/1.0 "
      "(academic study of shrine records; contact hacchake@gmail.com)")

LH3 = re.compile(r"https?://lh\d+\.googleusercontent\.com/[^!&\s\"']+")
LATLNG = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")
PLACE = re.compile(r"/maps/place/([^/@]+)")


def load():
    if not os.path.exists(DB):
        return []
    return [json.loads(l) for l in io.open(DB, encoding="utf-8") if l.strip()]


def save(rows):
    with io.open(DB, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def pull_image_urls(u):
    """maps の URL から画像URLを取り出す。lh3 が直接来たらそのまま。"""
    u = urllib.parse.unquote(u)
    if "lh3.googleusercontent.com" in u and "/maps/" not in u:
        return [u.split("!")[0]]
    return [m.group(0) for m in LH3.finditer(u)]


def fetch_img(url):
    base = url.rsplit("=", 1)[0] if re.search(r"=[a-z0-9\-]+$", url) else url
    last = None
    for suf in ("=w2400-h1400", "=s2048", ""):
        try:
            req = urllib.request.Request(base + suf, headers={"User-Agent": UA})
            b = urllib.request.urlopen(req, timeout=90).read()
            if len(b) > 20000:
                return b, base + suf
        except Exception as e:
            last = e
    raise last or RuntimeError("取得できない")


def cmd_add(args):
    urls = []
    if args and args[0] == "--file":
        for l in io.open(args[1], encoding="utf-8"):
            l = l.strip()
            if l and not l.startswith("#"):
                urls.append(l)
    else:
        urls = list(args)
    os.makedirs(IMG, exist_ok=True)
    rows = load()
    have = {r["image_url"] for r in rows}
    added = 0
    for u in urls:
        name = ""
        m = PLACE.search(urllib.parse.unquote(u))
        if m:
            name = urllib.parse.unquote(m.group(1)).replace("+", " ")
        ll = LATLNG.search(u)
        for iu in pull_image_urls(u):
            if iu in have:
                print("既登録:", iu[:70]); continue
            try:
                b, used = fetch_img(iu)
            except Exception as e:
                print("失敗:", str(e)[:60], iu[:60]); continue
            i = hashlib.sha1(iu.encode()).hexdigest()[:10]
            p = os.path.join(IMG, i + ".jpg")
            open(p, "wb").write(b)
            rows.append({"id": i, "name": name, "pref": "",
                         "lat": float(ll.group(1)) if ll else None,
                         "lng": float(ll.group(2)) if ll else None,
                         "maps_url": u if "/maps/" in u else "",
                         "image_url": iu, "fetched": used,
                         "path": os.path.relpath(p, BASE).replace("\\", "/"),
                         "bytes": len(b), "text": "", "at": ""})
            have.add(iu)
            added += 1
            print("取得 %s %7.0f KB %s" % (i, len(b) / 1024, name or "(社名不明)"))
            time.sleep(1.0)
    save(rows)
    print("追加 %d 件 / 総 %d 件" % (added, len(rows)))


def cmd_todo(_):
    rows = load()
    t = [r for r in rows if not r["text"]]
    if not t:
        print("未翻刻なし"); return
    print("未翻刻 %d 件。下の画像を読んで翻刻し boards.py set で登録する" % len(t))
    for r in t:
        print("  %s  %-16s %s" % (r["id"], r["name"] or "-",
                                  os.path.join(BASE, r["path"]).replace("\\", "/")))


def cmd_set(args):
    i = args[0]
    txt = None
    name = pref = None
    for k, x in enumerate(args):
        if x == "--text-file":
            txt = io.open(args[k + 1], encoding="utf-8").read().strip()
        if x == "--name":
            name = args[k + 1]
        if x == "--pref":
            pref = args[k + 1]
    rows = load()
    for r in rows:
        if r["id"] == i:
            if txt is not None:
                r["text"] = txt
                r["at"] = time.strftime("%Y-%m-%d")
            if name:
                r["name"] = name
            if pref:
                r["pref"] = pref
            save(rows)
            print("登録 %s %s (%d字)" % (i, r["name"], len(r["text"])))
            return
    print("見つからない id:", i)


def cmd_list(_):
    for r in load():
        print("%s %-14s %-6s %5d字 %s" % (r["id"], r["name"] or "-", r["pref"] or "-",
                                          len(r["text"]), r["image_url"][:48]))


def cmd_export(_):
    rows = [r for r in load() if r["text"]]
    json.dump(rows, io.open(os.path.join(BD, "boards.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("boards.json に %d 件" % len(rows))


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    c, a = sys.argv[1], sys.argv[2:]
    os.makedirs(BD, exist_ok=True)
    {"add": cmd_add, "todo": cmd_todo, "set": cmd_set,
     "list": cmd_list, "export": cmd_export}.get(c, lambda _: print(__doc__))(a)


if __name__ == "__main__":
    main()
