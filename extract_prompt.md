# 抽出プロンプト v1（units_dedup.jsonl の各行 → narrative_unit）

あなたは社伝・地誌の構造化を行う。入力は郡誌・神社誌等のOCRテキスト断片（誤字あり）。
以下のJSONのみを返す。推測で埋めず、本文にない項目は null。

## v0からの変更点
- `shrine_name`(単数) → `shrines`(配列)。神社覈録・県神社誌は1断片に複数社が現れるため。
- `source_shrine` を新設。資料そのものが特定社の由緒書である場合に資料タイトル由来の社名を入れる
  （本文に社名が無くても入れてよい。本文由来の `shrines` とは区別する）。
- events に `is_quote` / `quote_of` を新設。**依存推定の核心**。
- `variants` を新設。記紀・旧事本紀と食い違う異伝を記述する。

## 制約
- motif は motifs.yaml の語彙からのみ選ぶ。該当なしは "other" とし note に理由。
  - 事績ではなく比定・語釈・典拠比較そのものなら discourse 群（考証／祭神比定／異説否定／引用）を使う。
- **`is_quote`**: その事績が資料自身の叙述なら false、記紀・旧事紀・姓氏録等の本文引用の中の記述なら true。
  判別できなければ null。true のとき `quote_of` に引用元書名を入れる。
  「按ずるに」「連胤按るに」以下の考証部分は資料自身の叙述として false 扱い。
- name_raw は原文表記のまま。name_norm は記紀の標準表記に寄せる
  （例: ニギハヤヒ→饒速日命、天照國照彦火明命→天火明命 ※同一視は canon_alias に記す）。
- era.norm は [神代, 神武, 綏靖, 崇神, 垂仁, 景行, 成務, 仲哀, 応神, 仁徳, 履中, 允恭, 雄略,
  継体, 欽明, 崇峻, 推古, 舒明, 皇極, 天智, 天武, 持統, 奈良, 平安, 中世, 近世, 近代, 不明]
- shrines[].name_raw / place_raw は本文の表記のまま。国郡が書かれていれば kuni, gun に。
- 「〜と伝う」「〜と云う」「一説に」「なるべし」「詳ならず」など伝聞・推量・異説マーカーは hedges に列挙。
- 本文が他文献を引く場合（「旧事紀に曰く」「延喜式に」等）は cites に書名を列挙。
- `variants`: 記紀・旧事本紀の標準形と食い違う点を1件1文で書く。
  例「長髄彦を殺したのを饒速日ではなく可美真手命とする」。無ければ空配列。

## 出力
{
  "source_shrine": str|null,
  "shrines": [{"name_raw": str, "kuni": str|null, "gun": str|null, "place_raw": str|null,
               "saijin": [str], "note": str|null}],
  "actors": [{"name_raw": str, "name_norm": str|null, "canon_alias": [str],
              "role": "saijin|founder|visitor|enemy|ancestor|kanjo_origin|other"}],
  "events": [{"motif": str, "agent": str|null, "patient": str|null, "place_raw": str|null,
              "era": {"raw": str|null, "norm": str}, "objects": [str],
              "is_quote": bool|null, "quote_of": str|null, "note": str|null}],
  "clan_links": [str],
  "kanjo_from": str|null,
  "hedges": [str],
  "cites": [str],
  "variants": [str],
  "confidence": 0.0-1.0
}

出力レコードには pid / koma / url / layer / source_title / source_year / terms を付して保存する。
