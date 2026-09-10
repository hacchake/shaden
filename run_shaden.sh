#!/bin/sh
# 社格・社殿の記載が確認できたサイトを価値順に取得する。
# robots.txt 全面拒否の神奈川は scrape_shaden.py 側で弾かれる。
cd "$(dirname "$0")"
mkdir -p data/shaden logs
for s in tottori_jinjacho ishikawa_jinjacho saga_jinjacho ibaraki_jinjacho \
         tochigi_jinjacho tokyo_jinjacho miyagi_jinjacho mie_jinjacho \
         akita_jinjacho fukushima_jinjacho nara_jinjacho shimane_jinjacho \
         okayama_jinjacho ehime_jinjacho; do
  echo "=== $s $(date +%H:%M:%S) ==="
  python scrape_shaden.py "$s" --sleep 0.8 2>&1 | tail -4
  echo "  → $(wc -l < data/shaden/$s.jsonl 2>/dev/null || echo 0) 件"
done
echo "ALL DONE $(date +%H:%M:%S)"
