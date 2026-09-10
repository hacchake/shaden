"""
NDL次世代デジタルライブラリー API パイロット
  1) キーワードで本文検索 → ヒット資料(PID)と書誌を収集
  2) 各PIDの全文JSONを取得
  3) キーワードを含むコマだけ前後文脈つきで切り出し → JSONL
使い方:
  python ndl_pilot.py search 饒速日 磐船 十種神宝 --size 50 --max 200
  python ndl_pilot.py extract --terms 饒速日 磐船 --ctx 400 --limit 60
"""
import argparse, json, sys, time, re
from pathlib import Path
import requests

BASE = "https://lab.ndl.go.jp/dl/api"
OUT = Path("data"); OUT.mkdir(exist_ok=True)
HITS = OUT / "hits.jsonl"
FULL = OUT / "fulltext"; FULL.mkdir(exist_ok=True)
UNITS = OUT / "units.jsonl"
S = requests.Session(); S.headers["User-Agent"] = "shaden-pilot/0.1 (personal research)"

def get(url, **kw):
    for i in range(3):
        r = S.get(url, timeout=90, **kw)
        if r.ok: return r
        if 400 <= r.status_code < 500: break   # 403(非公開)等はリトライしない
        time.sleep(2 * (i + 1))
    r.raise_for_status()

def search(keywords, size, classic, maxn, ndc=None, field="contentonly"):
    # 既出は pid+検索条件 で重複排除（追記運用のため utf-8 明示）
    seen = set()
    if HITS.exists():
        for l in HITS.read_text(encoding="utf-8").splitlines():
            if not l.strip(): continue
            d = json.loads(l)
            seen.add((d["pid"], d["keyword"], d.get("via", "contentonly/-")))
    via = f"{field}/{ndc or '-'}"
    with HITS.open("a", encoding="utf-8") as f:
        for kw in keywords:
            frm = 0
            while frm < maxn:
                p = {"keyword": kw, "searchfield": field,
                     "size": min(size, maxn - frm), "from": frm}
                if classic is not None: p["fc-isClassic"] = str(classic).lower()
                if ndc: p["f-ndc"] = ndc
                j = get(f"{BASE}/book/search", params=p).json()
                items = j.get("list") or []
                if frm == 0: print(f"[{kw}|{via}] total hit={j.get('hit')}", file=sys.stderr)
                if not items: break
                for it in items:
                    pid = str(it.get("id") or "")
                    key = (pid, kw, via)
                    if not pid or key in seen: continue
                    seen.add(key)
                    f.write(json.dumps({"pid": pid, "keyword": kw, "via": via,
                        "title": it.get("title"), "author": it.get("responsibility"),
                        "pub": it.get("publisher"), "year": it.get("publishyear") or it.get("published"),
                        "ndc": it.get("ndc"), "classic": it.get("isClassic"),
                        "pages": it.get("page"), "snippets": it.get("highlights"),
                        }, ensure_ascii=False) + "\n")
                print(f"[{kw}|{via}] from={frm} got={len(items)}", file=sys.stderr)
                frm += len(items)
                if len(items) < p["size"]: break
                time.sleep(0.5)

def fetch_fulltext(pid):
    fp = FULL / f"{pid}.json"
    if fp.exists(): return json.loads(fp.read_text(encoding="utf-8"))
    j = get(f"{BASE}/book/fulltext-json/{pid}").json()
    # coordjson(文字座標)は本文解析に不要で巨大。落としてから保存
    for p in j.get("list") or []:
        if isinstance(p, dict): p.pop("coordjson", None)
    fp.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.5)
    return j

def pages_of(j):
    """全文JSONから (コマ番号, テキスト) を列挙。形式差に緩く対応"""
    pages = j.get("pages") or j.get("list") or j.get("contents") or []
    if isinstance(pages, dict): pages = list(pages.values())
    for i, p in enumerate(pages):
        if isinstance(p, str): yield i + 1, p; continue
        txt = p.get("contents") or p.get("text") or ""
        if isinstance(txt, list): txt = "".join(txt)
        yield p.get("page") or p.get("koma") or i + 1, txt

def extract(terms, ctx, limit):
    pat = re.compile("|".join(map(re.escape, terms)))
    pids = {}
    for l in HITS.read_text(encoding="utf-8").splitlines():
        if not l.strip(): continue
        d = json.loads(l); pids.setdefault(d["pid"], d)
    if limit:  # キーワード間で偏らないよう交互取り
        by_kw = {}
        for pid, d in pids.items(): by_kw.setdefault(d["keyword"], []).append(pid)
        order, qs = [], list(by_kw.values())
        for i in range(max(len(q) for q in qs)):
            for q in qs:
                if i < len(q): order.append(q[i])
        pids = {p: pids[p] for p in order[:limit]}
    n = 0
    with UNITS.open("w", encoding="utf-8") as f:
        for i, (pid, meta) in enumerate(pids.items(), 1):
            try: j = fetch_fulltext(pid)
            except Exception as e:
                print(f"skip {pid}: {e}", file=sys.stderr); continue
            for koma, txt in pages_of(j):
                txt = re.sub(r"\s+", "", txt)
                for m in pat.finditer(txt):
                    a, b = max(0, m.start() - ctx), min(len(txt), m.end() + ctx)
                    f.write(json.dumps({"pid": pid, "koma": koma, "term": m.group(),
                        "title": meta.get("title"), "year": meta.get("year"),
                        "url": f"https://dl.ndl.go.jp/pid/{pid}/1/{koma}",
                        "text": txt[a:b]}, ensure_ascii=False) + "\n")
                    n += 1
            print(f"  [{i}/{len(pids)}] {pid} units={n}", file=sys.stderr)
    print(f"→ {UNITS} ({n} units)", file=sys.stderr)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search"); s.add_argument("keywords", nargs="+")
    s.add_argument("--size", type=int, default=50); s.add_argument("--classic", default=None)
    s.add_argument("--max", type=int, default=200, dest="maxn", help="1キーワードあたりの取得上限")
    s.add_argument("--ndc", default=None, help="NDC前方一致で絞る(例 175=神社・神職)")
    s.add_argument("--field", default="contentonly", choices=["contentonly", "metaonly"],
                   help="contentonly=本文検索 / metaonly=書誌(書名)検索")
    e = sub.add_parser("extract"); e.add_argument("--terms", nargs="+", required=True)
    e.add_argument("--ctx", type=int, default=400)
    e.add_argument("--limit", type=int, default=0, help="処理するPID数の上限(0=全部)")
    a = ap.parse_args()
    if a.cmd == "search": search(a.keywords, a.size, a.classic, a.maxn, a.ndc, a.field)
    else: extract(a.terms, a.ctx, a.limit)
