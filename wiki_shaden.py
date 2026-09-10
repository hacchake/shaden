# -*- coding: utf-8 -*-
"""日本語版 Wikipedia から神社記事の由緒(歴史・沿革)を採る。

CC BY-SA。MediaWiki API を正規の作法(User-Agent明記・maxlag・連続要求を抑制)で叩く。

  python wiki_shaden.py cats      都道府県別カテゴリの記事一覧を集める → wiki_pages.json
  python wiki_shaden.py fetch     各記事の座標と本文(由緒節)を採る    → wiki_shaden.jsonl
  python wiki_shaden.py match     data.json の社に座標+社名で結びつける → wiki_match.json
"""
import json, io, os, re, sys, time, urllib.request, urllib.parse, collections

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "data", "wiki")
API = "https://ja.wikipedia.org/w/api.php"
UA = ("shaden-research/1.0 (academic study of shrine records; "
      "contact hacchake@gmail.com) python-urllib")

PREFS = ["北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県", "茨城県",
         "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県", "新潟県", "富山県",
         "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県", "三重県",
         "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県", "鳥取県", "島根県",
         "岡山県", "広島県", "山口県", "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
         "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"]

# 由緒にあたる節。ここだけ採る(記事全文は採らない)
SEC = re.compile(r"^(歴史|由緒|沿革|概要|歴史・由緒|由緒・歴史|創建|祭神|history)$", re.I)


def api(params, tries=3):
    params = dict(params)
    params.update({"format": "json", "formatversion": "2", "maxlag": "5"})
    u = API + "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            d = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
            if "error" in d and d["error"].get("code") == "maxlag":
                time.sleep(5); continue
            return d
        except Exception:
            time.sleep(2 * (i + 1))
    return {}


def cmd_cats(_):
    os.makedirs(OUT, exist_ok=True)
    pages = {}
    for p in PREFS:
        for cat in ("Category:%sの神社" % p,):
            cont = {}
            got = 0
            while True:
                d = api(dict({"action": "query", "list": "categorymembers",
                              "cmtitle": cat, "cmlimit": "500", "cmnamespace": "0"}, **cont))
                for m in d.get("query", {}).get("categorymembers", []):
                    pages[m["title"]] = p
                    got += 1
                if "continue" in d:
                    cont = d["continue"]; time.sleep(0.4)
                else:
                    break
            print("%-8s %4d 件" % (p, got))
            time.sleep(0.4)
    json.dump(pages, io.open(os.path.join(OUT, "wiki_pages.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("合計 %d 記事" % len(pages))


def strip_wiki(t):
    """節本文をひらたい文にする(注釈・テンプレ・リンク記法を落とす)"""
    t = re.sub(r"__[A-Z]+__", "", t)
    t = re.sub(r"<ref[^>]*/>|<ref.*?</ref>", "", t, flags=re.S)
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\[\[(?:[^\[\]|]*\|)?([^\[\]|]*)\]\]", r"\1", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"^[*#:;]+", "", t, flags=re.M)
    t = re.sub(r"'{2,}", "", t)
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip()


def cmd_fetch(a):
    pages = json.load(io.open(os.path.join(OUT, "wiki_pages.json"), encoding="utf-8"))
    outp = os.path.join(OUT, "wiki_shaden.jsonl")
    done = set()
    if os.path.exists(outp):
        for l in io.open(outp, encoding="utf-8"):
            try:
                done.add(json.loads(l)["title"])
            except Exception:
                pass
    todo = [t for t in pages if t not in done]
    lim = int(a[a.index("--limit") + 1]) if "--limit" in a else None
    if lim:
        todo = todo[:lim]
    f = io.open(outp, "a", encoding="utf-8")
    B = 20
    for i in range(0, len(todo), B):
        batch = todo[i:i + B]
        d = api({"action": "query", "titles": "|".join(batch),
                 "prop": "coordinates|revisions|pageprops",
                 "rvprop": "content", "rvslots": "main", "coprop": "type",
                 "redirects": "1"})
        for pg in d.get("query", {}).get("pages", []):
            if pg.get("missing"):
                continue
            title = pg["title"]
            co = (pg.get("coordinates") or [{}])[0]
            try:
                wt = pg["revisions"][0]["slots"]["main"]["content"]
            except Exception:
                continue
            # 節ごとに分ける
            parts = re.split(r"\n==+\s*([^=\n]+?)\s*==+\n", "\n" + wt)
            body, lead = [], strip_wiki(parts[0])[:600]
            for k in range(1, len(parts) - 1, 2):
                if SEC.match(parts[k].strip()):
                    body.append(strip_wiki(parts[k + 1]))
            txt = "\n".join(body)[:3000]
            if not txt:
                txt = lead
            if not txt:
                continue
            f.write(json.dumps({"title": title, "pref": pages.get(title, ""),
                                "lat": co.get("lat"), "lng": co.get("lon"),
                                "text": txt,
                                "url": "https://ja.wikipedia.org/wiki/" +
                                       urllib.parse.quote(title.replace(" ", "_"))},
                               ensure_ascii=False) + "\n")
        f.flush()
        sys.stderr.write("  %d/%d\n" % (min(i + B, len(todo)), len(todo)))
        time.sleep(0.6)
    f.close()


def cmd_match(_):
    rows = json.load(io.open(os.path.join(BASE, "data/shrinemap/data.json"), encoding="utf-8"))
    W = [json.loads(l) for l in io.open(os.path.join(OUT, "wiki_shaden.jsonl"), encoding="utf-8")]
    NK = str.maketrans("眞淸邊縣靈龍瀨賣濱嶋嶽彥國舊藏齋禰樣爲號權廣豐榮變應會",
                       "真清辺県霊竜瀬売浜島岳彦国旧蔵斎祢様為号権広豊栄変応会")

    def nm(s):
        s = (s or "").translate(NK)
        s = re.sub(r"[〈（(].*?[〉）)]", "", s)
        return re.sub(r"[\s　・･,、]", "", s)

    grid = collections.defaultdict(list)
    for i, r in enumerate(rows):
        la, ln = r.get("lat"), r.get("lng")
        if isinstance(la, (int, float)) and isinstance(ln, (int, float)):
            grid[(round(la, 2), round(ln, 2))].append(i)
    res, byname, bygeo = {}, 0, 0
    for w in W:
        la, ln = w.get("lat"), w.get("lng")
        wn = nm(w["title"])
        best, bd = None, 9e9
        if la is not None:
            for dy in (-0.01, 0, 0.01):
                for dx in (-0.01, 0, 0.01):
                    for i in grid.get((round(la + dy, 2), round(ln + dx, 2)), []):
                        d = (rows[i]["lat"] - la) ** 2 + (rows[i]["lng"] - ln) ** 2
                        if d < bd:
                            bd, best = d, i
        # 500m以内なら座標一致、それ以上なら社名一致を要求
        if best is not None and bd < (0.005 ** 2):
            res[str(best)] = w["title"]; bygeo += 1
        elif best is not None and bd < (0.02 ** 2) and (
                wn in nm(rows[best]["name"]) or nm(rows[best]["name"]) in wn):
            res[str(best)] = w["title"]; byname += 1
    json.dump(res, io.open(os.path.join(OUT, "wiki_match.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print("記事 %d / 結合 %d (座標 %d, 座標+社名 %d)" % (len(W), len(res), bygeo, byname))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    c = sys.argv[1] if len(sys.argv) > 1 else ""
    {"cats": cmd_cats, "fetch": cmd_fetch, "match": cmd_match}.get(
        c, lambda _: print(__doc__))(sys.argv[2:])
