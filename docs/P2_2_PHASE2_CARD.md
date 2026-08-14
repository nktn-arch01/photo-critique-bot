# P2-2 Phase 2 — カード主役化と問い寄せ

更新日: 2026-08-14  
対象: U1／Q1／Q4  
実装: [`generate_critique_card.py`](../generate_critique_card.py) / [`critique_prompts.py`](../critique_prompts.py) / [`prompt_contracts.py`](../prompt_contracts.py)  
基準: [`P2_2_PUBLIC_UX_CHARTER.md`](P2_2_PUBLIC_UX_CHARTER.md)

---

## 3段階レビュー

### レビュー1（根本）

カードのヒーローが ★ だったのは、SUMMARY と同じ大きさの星が5行続き、CRITIQUE_SUMMARY がロゴ横の小さい3行に押し込まれていたため。条件で星を隠すのではなく、**読み順と面積**を変える。

CRITIQUE_SUMMARY がキャプション止まりだったのは、Phase1 指示が「見所＋好奇心」だけで、憲章の「もう一度見る」が長文【5】にしか無かったため。N-03 の「たのではないでしょうか」定型には戻さない。

### レビュー2（一貫）

Desktop / LINE は同じ `create_critique_card`。パーサーキー（TITLE / SUMMARY / SCORES / CRITIQUE_SUMMARY）は変えない。ログの `(n/5)` は残す（N-06）。N-02 の TITLE 5px 上と余白50px は残す。N-02 の「SCORES＝SUMMARY サイズ」は Q1 が上書きする。

### レビュー3（テスト）

- オフライン: 言葉が★より上・大きい、写真帯＞文字帯、Q4 指示の2拍、定型語尾 fixture
- Mac: 下の PASS/FAIL（API 不要の見本カードで可）

---

## カードの読み順（確定）

```text
写真（いちばん広い）
TITLE
SUMMARY（キャッチ）
CRITIQUE_SUMMARY（見所＋次へ開く言葉）← 主役の文章
★5軸（小さく・下・ロゴ横）← 二次
```

| 要素 | サイズ | 役割 |
|------|--------|------|
| TITLE | 42 | 眼差しの仮説 |
| SUMMARY | 26 | 短いキャッチ |
| CRITIQUE_SUMMARY | 28・全幅3行 | 言葉にする → もう一度見る |
| SCORES | 20 | 観察のスナップショット（採点に見せない） |

N-02 で星を SUMMARY と同じ大きさにしたのは読みにくさ対策。いまは言葉が先なので、星は一段下げる。

---

## Q4 プロンプト（N-03 を踏まえた2拍）

70〜80文字で:

1. **見所**（画面に立ち現れている美しさ）
2. **開き**（もう一度見る／次のシャッター。答えで締めない）

使わない:

- 語尾の固定「たのではないでしょうか」「みませんか」
- 「あなたは〇〇に惹かれたのでは」

句点で閉じても、体言止めでも、たまに問いでもよい。

良い例: 「ガラスの縁が光を二つに割る。次に同じ反射に出会ったら、割れ目のどちらを残すかだけ決めてみる。」

---

## Mac 確認（コピペ）

```bash
cd ~/photo-critique-bot
git fetch origin
git checkout cursor/p2-2-phase2-card-f193
git pull origin cursor/p2-2-phase2-card-f193
python3 test_offline_suite.py
python3 - <<'PY'
from pathlib import Path
from PIL import Image, ImageDraw
from generate_critique_card import create_critique_card

out = Path.home() / "Desktop" / "LuminaPhase2Cards"
out.mkdir(parents=True, exist_ok=True)
src = out / "source.png"
im = Image.new("RGB", (1600, 1067), (48, 72, 96))
d = ImageDraw.Draw(im)
d.rectangle([200, 180, 1400, 820], fill=(180, 140, 70))
d.ellipse([700, 300, 1100, 700], fill=(220, 200, 150))
im.save(src)
sample = """
■TITLE: 沈黙を割る線
■SUMMARY: 金属に宿る眼差しの残像
■SCORES:
・眼差の輪郭 (Contours of the Eyes)  : ★★★★☆ (4/5)
・感情の陰影 (Nuances of Emotion)          : ★★★★★ (5/5)
・物語の気配 (Signs of the Story)      : ★★★☆☆ (3/5)
・表現の意図 (Intent of Expression) : ★★★★★ (5/5)
・感性の兆し (Signs of Sensibility)   : ★★★★☆ (4/5)
■CRITIQUE_SUMMARY: 境界のきらめきと線の陰影が、見所として立ち上がる。次に同じ反射に出会ったら、割れ目のどちらを残すかだけ決めてみる。
"""
create_critique_card(src, sample, out / "card_dark.png", theme="dark")
create_critique_card(src, sample, out / "card_light.png", theme="light")
print(out / "card_dark.png")
print(out / "card_light.png")
PY
open ~/Desktop/LuminaPhase2Cards/card_dark.png
open ~/Desktop/LuminaPhase2Cards/card_light.png
```

| # | 確認 | 結果 |
|---|------|------|
| P2a | `python3 test_offline_suite.py` が OK | |
| P2b | 写真がカードの大半を占める | |
| P2c | タイトルとキャッチの**下**に、長めの言葉（CRITIQUE_SUMMARY）がある | |
| P2d | ★5行は**一番下**で、タイトルより小さい | |
| P2e | ダーク／ライトとも文字が読める | |

実写で見る場合（任意）: Console「対話カード作成」で Rating 3/4 の JPEG からカードを1枚作る。API が必要。

---

## 変更履歴

| 日付 | 内容 |
|------|------|
| 2026-08-14 | Phase 2 実装。読み順・Q4 2拍・Mac 確認を固定 |
