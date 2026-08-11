# IPTC 同期検証（A10 / R1′-A §0.1）

更新日: 2026-08-11  
関連: [`R1_DEEP_LOOP_SPEC.md`](R1_DEEP_LOOP_SPEC.md) §0

## 方針（**運用確定**・2026-08-11）

JPEG メタと DxO の同期は検証 PASS。**`.dop` / `.xmp` は使わない。**

| 用途 | 一次ソース |
|------|------------|
| 短絡 | JPEG 内 Rating + Description（IPTC/XMP） |
| 講評 | 画（JPEG 画素）＋撮影 EXIF |

## 書き込みタグ契約（ファイル側・単一ソース候補）

| 目的 | タグ |
|------|------|
| Rating | `Rating`（XMP-xmp）, `XMP:Rating`, `RatingPercent`（目安: rating×20） |
| 説明 | `ImageDescription`（IFD0）, `XMP-dc:Description`, `IPTC:Caption-Abstract` |

説明文面は `[M2] …` / `[M3] …` の段ラベル付き（仕様 §5.1）。

---

## A. ファイル側ラウンドトリップ（実施済・2026-08-11）

| 項目 | 結果 |
|------|------|
| 環境 | exiftool 12.76 + Pillow |
| 手順 | `scripts/iptc_sync_verify.py` |
| Rating / Description 再読取 | **PASS** |
| 成果物 | `eval/iptc_sync/roundtrip_result.json` |

→ JPEG への書き込み・再読取は問題なし。DxO／プレビュー確認は **§B9 PASS**。

---

## B. DxO PhotoLab UI（手順は下記。結果は B9）

所要: だいたい 10〜15 分。初めてでも上から順に進めてください。

### B0. 事前準備（Mac 想定）

1. このリポジトリを Mac で開く（または検証用にクローン）  
2. Terminal でリポジトリのルートに移動する  
3. `exiftool` があるか確認:

```bash
which exiftool
exiftool -ver
```

無い場合は例: `brew install exiftool`

4. DxO PhotoLab のバージョンをメモ（メニュー **DxO PhotoLab → PhotoLab について**）

### B1. メタデータ同期をオンにする（重要）

DxO 公式: PhotoLab 5 以降、評価は `.dop` ではなく **XMP／ファイルメタ**側を見る。外部書き込みを反映するには同期が必要です。

1. **DxO PhotoLab → 環境設定（Preferences）**  
2. **詳細（Advanced）** または **一般（General）** タブ（バージョンで名称が違うことがあります）  
3. **メタデータの同期 / Metadata synchronization** を探す  
4. **常に同期 / Always synchronize**（文言はバージョンで前後します）を **オン** にする  
5. 環境設定を閉じる  

オフのままだと、昔 DxO が見た内容が DB に残り、今回の書き込みが見えないことがあります。

### B2. 検証用 JPEG を用意する（おすすめ: 実写のコピー）

**本番フォルダは触らない。** コピーで試します。

```bash
# リポジトリルートで実行
# ★ /path/to/your.jpg を、実写 JPEG のパスに書き換える
python3 scripts/iptc_sync_verify.py \
  --prepare-dxo \
  --jpeg /path/to/your.jpg \
  --rating 3 \
  --description '[M2] Lumina sync test reason
[M3] diversity placeholder'
```

成功すると、だいたい次の場所にファイルができます。

- フォルダ: `（リポジトリ）/eval/iptc_sync/dxo_probe/`
- 中の JPEG: 元ファイル名のコピー（メタ書き込み済み）
- Terminal に「期待 Rating」「期待 説明」「DxO で開くフォルダ」が表示されます

実写が手元に無い場合（見た目の確認だけ）:

```bash
python3 scripts/iptc_sync_verify.py --prepare-dxo --rating 3 \
  --description '[M2] Lumina sync test reason
[M3] diversity placeholder'
```

### B3. DxO でフォルダを開く

1. DxO PhotoLab を起動  
2. 左のフォトライブラリ／フォルダから、`eval/iptc_sync/dxo_probe` を開く  
   - まだ見えない場合: Finder でそのフォルダを DxO にドラッグするか、「フォルダを追加」系の操作  
3. **まだ一度も DxO で開いたことがないコピー**を使うのが望ましい（DB の古い Rating とぶつかにくい）

### B4. Rating（星）を確認する — 合否の本命

1. `dxo_probe` 内の JPEG を1枚選択  
2. 画面上の **星評価（Rating）** を見る（サムネ下やインスペクタ）  
3. Terminal に出た **期待 Rating**（例: 3）と一致するか  

| 結果 | 判定 |
|------|------|
| 同じ星数が見える | **一方向 PASS 候補** |
| 星が無い／違う | 下の「見えないとき」へ |

### B5. 説明（Description）を確認する

1. 同じ写真を選択したまま、**メタデータ／IPTC／情報**パネルを開く（バージョンで「メタデータ」パレット）  
2. **説明 / Description / キャプション** 欄を探す  
3. `[M2] Lumina sync test reason` など、書き込んだ文が見えるか  

| 結果 | 意味 |
|------|------|
| 見える | 説明も PASS |
| Rating だけ見えて説明が空 | 部分 PASS。メモに「説明は未表示」と書く（実装でタグ調整の材料） |
| どちらも見えない | FAIL 寄り。同期・再読込を試す |

### B6. 見えないときの対処（この順で）

1. **環境設定の「常に同期」がオンか**再確認  
2. 写真を右クリック（または **ファイル／画像** メニュー）→ **画像からメタデータを読み込む / Read metadata from image** があれば実行  
3. DxO を一度終了し、`dxo_probe` フォルダだけを開き直す  
4. Finder で別フォルダ名にコピーし直し、`--prepare-dxo` を再実行してから、**初めて** DxO で開く  
5. それでもダメなら FAIL。メモに DxO バージョンと試した操作を残す  

### B7. （努力目標）双方向

1. DxO 上で星を別の数（例: 4）に変える  
2. 数十秒待つ（同期オンならファイルへ書かれることがある）  
3. Terminal:

```bash
exiftool -G1 -s -Rating -XMP:Rating -ImageDescription -Description -Caption-Abstract \
  eval/iptc_sync/dxo_probe/（ファイル名）.jpg
```

4. Rating が DxO で変えた値になっていれば双方向 PASS  

### B8. 結果記入用テンプレ（実施前）

| 項目 | 結果 |
|------|------|
| DxO バージョン | |
| OS | |
| 一方向 Rating | 未実施 / PASS / FAIL |
| 一方向 説明 | 未実施 / PASS / FAIL / 部分 |
| 再読込が必要だったか | |
| 双方向（努力） | 未実施 / PASS / FAIL |
| メモ | |

### B9. 実施結果（オーナー・2026-08-11）— **PASS / 運用確定**

| 項目 | 結果 |
|------|------|
| OS | macOS（Mac mini） |
| 一方向 Rating（書込→DxO表示） | **PASS**（レーティング ★★★☆☆ = 3） |
| 一方向 説明（書込→DxO表示） | **PASS**（IPTC コンテンツ「説明」に `[M2]…` / `[M3]…`） |
| クロスチェック | macOS プレビュー IPTC でも StarRating=3・説明同一を確認 **PASS** |
| 双方向（努力） | **PASS**（2026-08-11 追加検証） |
| 証拠 | オーナー提供スクショ（2026-08-11）: **黒バック＝DxO**（レーティング★★★・IPTC説明）、**白バック＝Macプレビュー IPTC**（StarRating=3・同一説明） |

### B10. 双方向追加検証（オーナー・2026-08-11）— **PASS**

H3 想定どおり、DxO 上で Rating 修正とコメント（説明）書き込みを行い、対象 JPEG（例: `P6141347.JPG`）へ**リアルタイム反映**されることを確認。

| 項目 | 結果 |
|------|------|
| DxO → ファイル（Rating） | **PASS** |
| DxO → ファイル（説明／コメント） | **PASS** |
| 反映タイミング | リアルタイム（OK） |

**判定: A PASS かつ B 一方向 PASS かつ双方向 PASS → §0 を運用確定。`.dop` / `.xmp` は使わない。**

実装: [`iptc_rating_io.py`](../iptc_rating_io.py)（T1）、[`library_unit.py`](../library_unit.py)（T2）、[`shortlist_mechanical.py`](../shortlist_mechanical.py)（T3）。次は [`R1A_IMPLEMENTATION_BREAKDOWN.md`](R1A_IMPLEMENTATION_BREAKDOWN.md) の **T4** 以降。

---

## 現行コードとの差分（実装時）

- 現状: メタ書き込みなし。Rating 等は主に `.dop` から読取  
- **同期運用確定（2026-08-11）:** JPEG への書き込み＋JPEG からの読取を正とする。講評の User Intent / Rating 注入も JPEG 側へ移行
