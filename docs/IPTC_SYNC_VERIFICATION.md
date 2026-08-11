# IPTC 同期検証（A10 / R1′-A §0.1）

更新日: 2026-08-11  
関連: [`R1_DEEP_LOOP_SPEC.md`](R1_DEEP_LOOP_SPEC.md) §0

## 方針（オーナー確定）

JPEG メタと DxO の同期が成立すれば **`.dop` / `.xmp` は使わない**。

| 用途 | 一次ソース |
|------|------------|
| 短絡 | JPEG 内 Rating + Description（IPTC/XMP） |
| 講評 | 画（JPEG 画素）＋撮影 EXIF |

## 書き込みタグ契約（ファイル側・単一ソース候補）

短絡バッチ／検証スクリプトが JPEG に書くタグ:

| 目的 | タグ |
|------|------|
| Rating | `Rating`（XMP-xmp）, `XMP:Rating`, `RatingPercent`（目安: rating×20） |
| 説明 | `ImageDescription`（IFD0）, `XMP-dc:Description`, `IPTC:Caption-Abstract` |

説明文面は `[M2] …` / `[M3] …` の段ラベル付き（仕様 §5.1）。

検証コマンド:

```bash
python3 scripts/iptc_sync_verify.py
# 既存ファイルを壊さずコピー検証:
python3 scripts/iptc_sync_verify.py --jpeg /path/to/photo.jpg --rating 3 --description '[M2] test'
```

## 検証結果

### A. ファイル側ラウンドトリップ（エージェント実施・2026-08-11）

| 項目 | 結果 |
|------|------|
| 環境 | exiftool 12.76 + Pillow |
| 手順 | `scripts/iptc_sync_verify.py`（サンプル JPEG 生成→書き込み→再読取） |
| Rating 再読取 | **PASS**（`Rating=4`） |
| Description 再読取 | **PASS**（ImageDescription / Description / Caption-Abstract 一致） |
| 成果物 | `eval/iptc_sync/roundtrip_result.json`（JPEG 本体は `.gitignore`） |

→ **アプリが JPEG に書いた Rating／説明を、標準ツールで再読できることは確認済み。**

### B. DxO PhotoLab UI（オーナー手動・未実施）

最低限の合格（仕様 §0.1）:

1. [ ] 上記スクリプトまたは同等の exiftool で、実撮影 JPEG に Rating と説明を書く  
2. [ ] DxO でフォルダを開き、同じ Rating／説明が一覧またはインスペクタに見える（再読込手順があれば記録）  
3. [ ] （努力）DxO で Rating を変更 → ファイルを exiftool で再読して残っている  

| 項目 | 結果（オーナー記入） |
|------|----------------------|
| DxO バージョン | |
| OS | |
| 一方向（書込→DxO表示） | 未実施 / PASS / FAIL |
| 双方向（DxO変更→再読） | 未実施 / PASS / FAIL |
| 再読込が必要だったか | はい / いいえ（手順: ） |
| メモ | |

**判定ルール**

- A PASS かつ B 一方向 PASS → **§0 を運用確定**（`.dop` / `.xmp` 不使用）  
- B FAIL → `.dop` フォールバック要否を再検討（本方針の例外）

## 現行コードとの差分（実装時）

- 現状: メタ書き込みなし。Rating 等は主に `.dop` から読取  
- 同期運用確定後: JPEG への書き込み＋JPEG からの読取を正とする。講評の User Intent / Rating 注入も JPEG 側へ移行
