# -*- coding: utf-8 -*-
"""神社庁サイトの詳細ページから 社格・社殿・由緒 を採る汎用スクレイパー。

data.json が全社の source_url を持っているので一覧クロールは不要。
各ページを text に潰し「ラベル行 → 次の非空行」で値を拾う。
神社庁サイトは table/dl の別はあってもこの形に落ちるものが多い。

  python scrape_shaden.py <source名> [--limit N] [--out FILE] [--sleep 秒]
  python scrape_shaden.py --list            出典ごとの件数を表示
  python scrape_shaden.py --probe <source名> 先頭5件の抽出結果だけ見る

robots.txt で全面拒否のサイト(神奈川県神社庁)は DENY に入れて弾く。
"""
import json, io, os, re, sys, time, urllib.request, urllib.error, collections

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data", "shrinemap", "data.json")
OUTDIR = os.path.join(BASE, "data", "shaden")
UA = ("shaden-research/1.0 (academic study of shrine records; "
      "contact hacchake@gmail.com)")

# robots.txt が User-agent:* に Disallow:/ を出しているサイト
DENY = {"kanagawa_jinjacho"}

# 拾いたいラベル(表記ゆれを含む)。値は正規化後のキー名。
LABELS = [
    (r"^(旧社格|舊社格|社格|旧社格等)$",           "shakaku"),
    (r"^(各種指定|指定|文化財|指定文化財)$",        "shitei"),
    (r"^(社殿|本殿|社殿等|建物|社殿の様式|様式)$",  "shaden_f"),
    (r"^(境内地|境内|境内坪数|敷地)$",             "keidai"),
    (r"^(氏子|氏子数|氏子戸数)$",                  "ujiko"),
    (r"^(由緒|由緒沿革|由緒・沿革|沿革|御由緒|由来|由緒書)$", "yuisho"),
    (r"^(その他|備考|特記事項|摘要)$",             "sonota"),
    (r"^(祭神|御祭神|主祭神)$",                    "saijin2"),
    (r"^(祭祀|例祭|祭礼|主な祭礼|年中行事)$",       "saishi"),
    (r"^(よみ|読み|ふりがな|かな)$",               "yomi"),
    (r"^(摂社|末社|境内神社|摂末社)$",             "massha"),
    (r"^(宮司|神職)$",                             "guji"),
]
LABELS = [(re.compile(p), k) for p, k in LABELS]

# 由緒本文から社殿に関する文を抜く
SHADEN_SENT = re.compile(
    r"[^。\n]*?(本殿|拝殿|拜殿|幣殿|神殿|社殿|鳥居|神門|随神門|隨神門|"
    r"流造|神明造|春日造|権現造|權現造|入母屋|切妻|檜皮葺|銅板葺|茅葺|瓦葺|"
    r"造営|造營|建立|再建|改築|新築|修造|遷宮|焼失|燒失|焼亡|類焼|類燒)"
    r"[^。\n]*。")
# 社格の語(本文中から拾う保険)
SHAKAKU_WORD = re.compile(
    r"(別格官幣社|官幣大社|官幣中社|官幣小社|国幣大社|國幣大社|国幣中社|國幣中社|"
    r"国幣小社|國幣小社|別表神社|県社|縣社|郷社|鄕社|村社|無格社|式内社|式內社)")



# 値の切れ目(サイト共通のナビゲーション・定型文)
STOP = re.compile(
    r"^(地図|印刷|大きな地図|トップページ|Contact|検索|ページの先頭|前へ|次へ|一覧|閉じる"
    r"|前の写真|次の写真|基本情報|神社コード|関連リンク|Links|パスワード"
    r"|.*に戻る$|.*一覧$|▲|△|◀|▶|Copyright|All Rights|お問い合わせ|アクセス"
    r"|サイトマップ|プライバシー|利用規約|ホーム|HOME|MENU|メニュー"
    r"|神社庁|県神社庁|都神社庁|府神社庁|〒[0-9\-]+|TEL|FAX|電話)")


def to_lines(html):
    """HTML を行の列に潰す"""
    h = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", html, flags=re.S | re.I)
    h = re.sub(r"<(br|/tr|/p|/div|/li|/dd|/dt|/td|/th|/h[1-6])[^>]*>", "\n", h, flags=re.I)
    h = re.sub(r"<[^>]+>", "\n", h)
    h = (h.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
          .replace("&gt;", ">").replace("&quot;", '"').replace("&#039;", "'"))
    out = []
    for ln in h.split("\n"):
        ln = re.sub(r"[ \t　]+", " ", ln).strip()
        if ln:
            out.append(ln)
    return out


def fetch(url, timeout=40, tries=2):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            raw = urllib.request.urlopen(req, timeout=timeout).read()
            for enc in ("utf-8", "cp932", "euc-jp"):
                try:
                    return raw.decode(enc)
                except Exception:
                    pass
            return raw.decode("utf-8", "ignore")
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def extract(lines):
    """ラベル行の直後を値とみなす。値が複数行続くものは連結する。"""
    got = {}
    n = len(lines)
    for i, ln in enumerate(lines):
        if len(ln) > 12:
            continue                      # ラベルは短い
        key = None
        for pat, k in LABELS:
            if pat.match(ln):
                key = k
                break
        if not key or key in got:
            continue
        vals, j = [], i + 1
        while j < n and len(vals) < 14:
            v = lines[j]
            if any(p.match(v) for p, _ in LABELS):
                break                     # 次のラベルに当たったら終わり
            if STOP.match(v):
                break
            vals.append(v)
            j += 1
            if key not in ("yuisho", "sonota", "massha", "saishi"):
                break                     # 単値の欄は1行だけ
        if vals:
            got[key] = "\n".join(vals).strip()
    return got


def refine(g):
    """社格・社殿を確定させる"""
    out = dict(g)
    body = "\n".join([g.get("yuisho", ""), g.get("sonota", ""), g.get("shaden_f", "")])
    # 社格
    sk = g.get("shakaku", "")
    m = SHAKAKU_WORD.search(sk) or SHAKAKU_WORD.search(body)
    out["shakaku_n"] = m.group(1) if m else ""
    # 社殿: 専用欄があればそれ、なければ由緒から社殿文を抜く
    if g.get("shaden_f"):
        out["shaden"] = g["shaden_f"][:400]
    else:
        s = [m.group(0).strip() for m in SHADEN_SENT.finditer(body)]
        out["shaden"] = "／".join(s)[:600]
    return out


def load_targets(source):
    rows = json.load(io.open(DATA, encoding="utf-8"))
    return [r for r in rows
            if r.get("source") == source and (r.get("source_url") or "").startswith("http")]


def main():
    a = sys.argv[1:]
    if not a or a[0] == "--list":
        rows = json.load(io.open(DATA, encoding="utf-8"))
        c = collections.Counter()
        for r in rows:
            if (r.get("source_url") or "").startswith("http"):
                c[r["source"]] += 1
        for k, n in c.most_common():
            print("%-24s %6d %s" % (k, n, "← robots拒否" if k in DENY else ""))
        return
    probe = False
    if a[0] == "--probe":
        probe = True
        a = a[1:]
    source = a[0]
    if source in DENY:
        print("robots.txt が全面拒否のサイト。中止:", source)
        return
    limit = None
    sleep = 1.0
    out = os.path.join(OUTDIR, source + ".jsonl")
    for i, x in enumerate(a):
        if x == "--limit":
            limit = int(a[i + 1])
        if x == "--out":
            out = a[i + 1]
        if x == "--sleep":
            sleep = float(a[i + 1])
    if probe:
        limit = limit or 5

    targets = load_targets(source)
    if limit:
        targets = targets[:limit]
    os.makedirs(OUTDIR, exist_ok=True)

    done = set()
    if not probe and os.path.exists(out):
        for l in io.open(out, encoding="utf-8"):
            try:
                done.add(json.loads(l)["source_url"])
            except Exception:
                pass
    f = None if probe else io.open(out, "a", encoding="utf-8")
    ok = ng = 0
    for i, r in enumerate(targets, 1):
        u = r["source_url"]
        if u in done:
            continue
        try:
            g = refine(extract(to_lines(fetch(u))))
        except Exception as e:
            ng += 1
            sys.stderr.write("ERR %s %s\n" % (u, str(e)[:60]))
            time.sleep(sleep)
            continue
        rec = {"name": r["name"], "pref": r["pref"], "source": source, "source_url": u,
               "shakaku": g.get("shakaku_n", ""), "shakaku_raw": g.get("shakaku", ""),
               "shaden": g.get("shaden", ""), "shitei": g.get("shitei", ""),
               "keidai": g.get("keidai", ""), "ujiko": g.get("ujiko", ""),
               "massha": g.get("massha", ""), "yomi": g.get("yomi", ""),
               "yuisho": (g.get("yuisho", "") or "")[:1200],
               "sonota": (g.get("sonota", "") or "")[:400]}
        ok += 1
        if probe:
            print("── %s (%s)" % (rec["name"], u))
            for k in ("shakaku", "shaden", "shitei", "keidai", "ujiko", "yomi"):
                if rec[k]:
                    print("   %-9s %s" % (k, rec[k][:150].replace("\n", " / ")))
            if rec["yuisho"]:
                print("   yuisho    %s…" % rec["yuisho"][:110].replace("\n", " "))
        else:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            if ok % 50 == 0:
                sys.stderr.write("  %d/%d ok=%d ng=%d\n" % (i, len(targets), ok, ng))
        time.sleep(sleep)
    if f:
        f.close()
    sys.stderr.write("done %s ok=%d ng=%d\n" % (source, ok, ng))


if __name__ == "__main__":
    main()
