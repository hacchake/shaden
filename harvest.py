# -*- coding: utf-8 -*-
"""地誌の本文から社伝そのものを刈り取る。

これまでは「現存する70,393社の社名」を鍵に引いていた。
その方式では、合祀で消えた社・郡誌にしか出てこない小社・そもそも社名の
表記が違う社を取りこぼす。

ここでは逆に、社伝に特徴的な語(勧請・遷座・創祀・鎮座…)を鍵にして
本文から項目を切り出す。社名リストに依存しないので、
現存社かどうかに関わらず社伝が採れる。

  python harvest.py run [--limit N]   全巻から刈り取り → data/jinjashi/harvest.jsonl
  python harvest.py stat              採れた社伝の統計
"""
import json, io, os, re, sys, collections

BASE = os.path.dirname(os.path.abspath(__file__))
JD = os.path.join(BASE, "data", "jinjashi")

# 社伝を示す語。これが社名の近くにあれば「その社の由緒を語っている」とみなす。
MARK = re.compile(
    r"(勸請|勧請|遷座|遷坐|奉遷|創祀|創建|創立|鎭座|鎮座|由緒|由緖|祭神|"
    r"分靈|分霊|合祀|合祭|再建|造營|造営|社領|神階|式內|式内|舊社格|旧社格)")
# 特に価値の高い語(社伝の型そのもの)
KEY = ["勧請", "遷座", "創祀", "創建", "合祀", "分霊", "社領", "神階", "式内"]
KEYPAT = re.compile("(" + "|".join(
    ["勸請|勧請", "遷座|遷坐|奉遷", "創祀", "創建|創立", "合祀|合祭",
     "分靈|分霊", "社領", "神階", "式內|式内"]) + ")")

# 社名。地誌は「◯◯神社」「◯◯社」「◯◯宮」「◯◯大明神」など多様に書く
NAME = re.compile(
    r"[一-鿿]{2,10}?(神社|神宮|大社|八幡宮|天満宮|天滿宮|大明神|明神社|權現|権現|稻荷社|稲荷社|宮)")
# 年号(社伝の年代を拾う)
ERA = re.compile(
    r"(大化|白雉|朱鳥|大宝|大寶|慶雲|和銅|霊亀|靈龜|養老|神亀|神龜|天平|天応|天應|延暦|延曆|"
    r"大同|弘仁|天長|承和|嘉祥|仁寿|仁壽|斉衡|齊衡|天安|貞観|貞觀|元慶|仁和|寛平|寬平|昌泰|"
    r"延喜|延長|承平|天慶|天暦|天曆|応和|應和|康保|安和|天禄|天祿|天延|貞元|天元|永観|永觀|"
    r"寛和|寬和|永延|永祚|正暦|正曆|長徳|長德|長保|寛弘|寬弘|長和|寛仁|寬仁|治安|万寿|萬壽|"
    r"長元|長暦|長曆|長久|寛徳|寬德|永承|天喜|康平|治暦|治曆|延久|承保|承暦|承曆|永保|応徳|應德|"
    r"寛治|寬治|嘉保|永長|承徳|承德|康和|長治|嘉承|天仁|天永|永久|元永|保安|天治|大治|天承|"
    r"長承|保延|永治|康治|天養|久安|仁平|久寿|久壽|保元|平治|永暦|永曆|応保|應保|長寛|長寬|"
    r"永万|永萬|仁安|嘉応|嘉應|承安|安元|治承|養和|寿永|壽永|元暦|元曆|文治|建久|正治|建仁|"
    r"元久|建永|承元|建暦|建曆|建保|承久|貞応|貞應|元仁|嘉禄|嘉祿|安貞|寛喜|寬喜|貞永|天福|"
    r"文暦|文曆|嘉禎|暦仁|曆仁|延応|延應|仁治|寛元|寬元|宝治|寶治|建長|康元|正嘉|正元|文応|文應|"
    r"弘長|文永|建治|弘安|正応|正應|永仁|正安|乾元|嘉元|徳治|德治|延慶|応長|應長|正和|文保|"
    r"元応|元應|元亨|正中|嘉暦|嘉曆|元徳|元德|元弘|建武|延元|興国|興國|正平|建徳|建德|文中|"
    r"天授|弘和|元中|暦応|曆應|康永|貞和|観応|觀應|文和|延文|康安|貞治|応安|應安|永和|康暦|康曆|"
    r"永徳|永德|至徳|至德|嘉慶|康応|康應|明徳|明德|応永|應永|正長|永享|嘉吉|文安|宝徳|寶德|"
    r"享徳|享德|康正|長禄|長祿|寛正|寬正|文正|応仁|應仁|文明|長享|延徳|延德|明応|明應|文亀|文龜|"
    r"永正|大永|享禄|享祿|天文|弘治|永禄|永祿|元亀|元龜|天正|文禄|文祿|慶長|元和|寛永|寬永|"
    r"正保|慶安|承応|承應|明暦|明曆|万治|萬治|寛文|寬文|延宝|延寶|天和|貞享|元禄|元祿|宝永|寶永|"
    r"正徳|正德|享保|元文|寛保|寬保|延享|寛延|寬延|宝暦|寶曆|明和|安永|天明|寛政|寬政|享和|文化|"
    r"文政|天保|弘化|嘉永|安政|万延|萬延|文久|元治|慶応|慶應|明治|大正|昭和)"
    r"[元一二三四五六七八九十百]{0,4}年")

NK = str.maketrans("眞淸邊縣靈龍瀨賣濱嶋嶽彥國舊藏齋禰樣爲號權廣豐榮變應會鹽澤鬪擧與豫",
                   "真清辺県霊竜瀬売浜島岳彦国旧蔵斎祢様為号権広豊栄変応会塩沢闘挙与予")
RANK = re.compile(r"(別格官幣社|官幣大社|官幣中社|官幣小社|国幣大社|国幣中社|国幣小社|"
                  r"県社|郷社|村社|無格社)")
KANJO = re.compile(r"(?:より|ヨリ|自)?([一-鿿]{2,12}?(?:神社|神宮|大社|宮|大明神))(?:の|ノ)?"
                   r"(?:御)?(?:分靈|分霊|神霊|靈)?を?(?:勸請|勧請)")


def norm(s):
    s = (s or "").translate(NK)
    return re.sub(r"[\s　・･,、。〓\-—―]", "", s)


def run(a):
    lim = int(a[a.index("--limit") + 1]) if "--limit" in a else None
    idx = json.load(io.open(os.path.join(JD, "index.json"), encoding="utf-8"))
    out = io.open(os.path.join(JD, "harvest.jsonl"), "w", encoding="utf-8")
    pids = list(idx.keys())
    if lim:
        pids = pids[:lim]
    tot = 0
    for n, pid in enumerate(pids, 1):
        v = idx[pid]
        joined, pos, off = [], [], 0
        for km in v["komas"]:
            joined.append(km["t"])
            pos.append((off, off + len(km["t"]), km["k"]))
            off += len(km["t"])
        big = "".join(joined)
        vhit = 0
        seen = set()
        for m in NAME.finditer(big):
            s, e = m.start(), m.end()
            nm = m.group(0)
            if len(nm) < 3:
                continue
            # 社名の直後に社伝の語が来るものだけを項目の見出しとみなす
            head = big[e:e + 70]
            if not MARK.search(head):
                continue
            body = big[e:e + 560]
            keys = sorted(set(KEYPAT.findall(body)))
            if not keys:
                continue                    # 語がないものは一覧表の可能性が高い
            k = next((kk for a_, b_, kk in pos if a_ <= s < b_), None)
            sig = (nm, k)
            if sig in seen:
                continue
            seen.add(sig)
            eras = ERA.findall(body)
            kj = KANJO.search(body)
            rk = RANK.search(big[max(0, s - 40):e + 30])
            out.write(json.dumps({
                "name": nm, "vol": v["label"], "pref": v.get("pref"),
                "pid": int(pid), "koma": k,
                "rank": rk.group(1) if rk else "",
                "keys": keys,
                "eras": sorted(set(eras))[:6],
                "kanjo": kj.group(1) if kj else "",
                "text": big[max(0, s - 30):e + 560],
                "url": "https://dl.ndl.go.jp/pid/%s/1/%s" % (pid, k),
            }, ensure_ascii=False) + "\n")
            vhit += 1
            tot += 1
        if n % 100 == 0:
            sys.stderr.write("  %d/%d 巻 累計 %d 件\n" % (n, len(pids), tot))
    out.close()
    print("刈り取り %d 件 / %d 巻" % (tot, len(pids)))


def stat(_):
    L = [json.loads(l) for l in io.open(os.path.join(JD, "harvest.jsonl"), encoding="utf-8")]
    print("社伝 %d 件 / 異なり社名 %d" % (L and len(L) or 0, len({x["name"] for x in L})))
    kc = collections.Counter(k for x in L for k in x["keys"])
    print("\n語の出現:")
    for k, n in kc.most_common():
        print("  %-8s %6d" % (k, n))
    print("\n社格:", ", ".join("%s %d" % (k, n) for k, n in
          collections.Counter(x["rank"] for x in L if x["rank"]).most_common(8)))
    print("勧請元が読めた %d 件" % sum(1 for x in L if x["kanjo"]))
    print("年号が読めた   %d 件" % sum(1 for x in L if x["eras"]))
    pc = collections.Counter(x["pref"] for x in L if x["pref"])
    print("\n県 上位10:", ", ".join("%s%d" % (k, n) for k, n in pc.most_common(10)))


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else ""
    {"run": run, "stat": stat}.get(c, lambda _: print(__doc__))(sys.argv[2:])
