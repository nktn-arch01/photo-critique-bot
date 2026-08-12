# R1′-A 実装タスク分解

更新日: 2026-08-11  
前提仕様: [`R1_DEEP_LOOP_SPEC.md`](R1_DEEP_LOOP_SPEC.md)  
メタ検証: [`IPTC_SYNC_VERIFICATION.md`](IPTC_SYNC_VERIFICATION.md)

第一波の本アプリ範囲: **JPEG へのスクリーニング（M1→M2→M3）＋監査ログ＋Works 上のLumina Review**。  
H3 / Works コピー / RAW 現像は DxO 等（実装しない）。

---

## 依存関係（推奨順）

```text
T0 検証ゲート（IPTC）
  → T1 JPEG Rating/Description I/O
  → T2 library_unit
  → T3 M1 mechanical
  → T4 M2 antenna（軽量）
  → T5 M3 diversity
  → T6 pipeline + CLI/最小UI
  → T7 監査ログ
  → T8 Lumina Review（Works 指定）
  → T9 scanner/講評の JPEG 正への移行
  → T10 オフラインテスト拡充
```

---

## タスク一覧

### T0 — IPTC 同期ゲート

| 項目 | 内容 |
|------|------|
| 内容 | [`IPTC_SYNC_VERIFICATION.md`](IPTC_SYNC_VERIFICATION.md) の A＋B |
| 状態 | **完了（2026-08-11）** — ファイル側 PASS、DxO／プレビュー一方向 PASS、双方向 PASS（§B10）。§0 運用確定 |
| 完了条件 | B 一方向 PASS で §0 運用確定（達成）。双方向も追加で PASS |
| 依存 | なし |

### T1 — `iptc_rating_io`（単一ソース）

| 項目 | 内容 |
|------|------|
| モジュール | [`iptc_rating_io.py`](../iptc_rating_io.py) |
| 内容 | 仕様どおり Rating / Description を JPEG に読み書き。タグ集合は検証ドキュメントと同一。`[M2]`/`[M3]` はブロック置換 |
| 状態 | **完了（2026-08-11）** |
| 完了条件 | ラウンドトリップの自動テスト。説明の `[M2]`/`[M3]` ブロック追記 API（達成。`test_offline_suite`） |
| 依存 | T0 のタグ契約 |

### T2 — `library_unit`

| 項目 | 内容 |
|------|------|
| モジュール | [`library_unit.py`](../library_unit.py) |
| 内容 | 月 `YYYYMM` / イベント `YYYYMMDD_短い名前` の識別と画像列挙 |
| 状態 | **完了（2026-08-11）** |
| 完了条件 | オフラインで規則テスト。パターン外サブフォルダはイベントにしない（達成） |
| 依存 | なし（T1 と並列可） |

### T3 — M1 機械選別

| 項目 | 内容 |
|------|------|
| モジュール | [`shortlist_mechanical.py`](../shortlist_mechanical.py) |
| 内容 | 明らかな失敗の足切り＋意図保護（低速 SS・開放・意図的アンダー等）。合格 Rating=1、不合格=0 |
| 状態 | **完了（2026-08-11）** |
| 完了条件 | 閾値は設定化。枚数目安（約80%+）はガイド。画素非破壊（達成。オフラインテスト） |
| 依存 | T1, T2 |
| 詳細 | ブレ指標は Laplacian 分散（Pillow）。OpenCV 非依存 |
| 使用注意 | 星空・流し撮り等の誤って 0 になりうるケースは仕様 §6.4.1。H3 で回収 |

### T4 — M2 アンテナ

| 項目 | 内容 |
|------|------|
| モジュール | [`shortlist_antenna.py`](../shortlist_antenna.py) |
| 内容 | 5軸相対熱量。合格に Rating=2 と説明 `[M2]`。★絶対ゲート禁止 |
| 状態 | **完了（2026-08-11）** |
| 完了条件 | 軽量 Vision。フル Phase2 を走らせない（達成。相対選抜＋オフラインテスト） |
| 依存 | T1, T3（入力は Rating≥1） |

### T5 — M3 多様性

| 項目 | 内容 |
|------|------|
| モジュール | [`shortlist_diversity.py`](../shortlist_diversity.py) |
| 内容 | 余白=3、上位=4、説明 `[M3]`。偏り抑制・執着優先 |
| 状態 | **完了（2026-08-11）** |
| 完了条件 | 最終 roughly 10% ガイド。タグ語彙は設定／実装詳細（達成） |
| 依存 | T1, T4 |

### T6 — パイプライン＋実行口

| 項目 | 内容 |
|------|------|
| モジュール | [`screening_pipeline.py`](../screening_pipeline.py)（実装 [`shortlist_pipeline.py`](../shortlist_pipeline.py)）/ **必須GUI** [`console_gui.py`](../console_gui.py) / CLI [`run_screening.py`](../run_screening.py) |
| 内容 | M1→M2→M3 オーケストレーション、進捗、中断、1枚失敗で全体停止しない |
| 状態 | **完了（GUI必須化 2026-08-11）** |
| 完了条件 | 既存 `app_gui` 講評バッチを壊さない（別導線）。**スクリーニングの主実行口は GUI** |
| 依存 | T3–T5 |

### T7 — 監査ログ

| 項目 | 内容 |
|------|------|
| モジュール | [`delta_log.py`](../delta_log.py) |
| 内容 | `_lumina/sessions/{id}.json` にファイルごとの Rating／説明／段／時刻。**pre_h3 / post_h3 / h3_delta**（DxO前後・判定改善用） |
| 状態 | **完了（前後記録強化 2026-08-11）** |
| 完了条件 | セッション再読・サマリ件数。H3後記録と差分（達成） |
| 依存 | T6 |

### T8 — Lumina Review（Works）

| 項目 | 内容 |
|------|------|
| 仮モジュール | `lumina_review.py`（旧 `trace_from_works.py` は互換再エクスポート） |
| 内容 | ユーザー指定フォルダ上の `{stem}_dev.jpg` 優先（なければ撮って出し）に既存講評カード／ノート／ログ |
| 完了条件 | コピー機能なし。既存コア再利用。画優先の注記をプロンプトへ（必要なら T9 と同時） |
| 実装 | **完了** — `LuminaReviewRunner` / `list_works_review_targets`（旧名 alias あり）。GUI: Console の「Works Lumina Review」。補助 CLI: `run_lumina_review.py`。プロンプトに画優先注記（`pixel_priority`） |
| 依存 | T1（読取）, 既存 critique コア |

### T9 — scanner / 講評の JPEG 正への移行

| 項目 | 内容 |
|------|------|
| 内容 | `user_intent` / Rating 表示を JPEG Description / Rating から取得。`.dop` 優先を廃止またはフォールバックのみ |
| 完了条件 | Phase2 注入が JPEG 一次ソースと一致。オフライン／手動で確認 |
| 依存 | T0 PASS, T1 |
| 実装 | **完了** — `scanner.extract_file_metadata` が `iptc_rating_io` 経由で JPEG 正。衝突 `.dop` より JPEG 優先。空欄時のみ dop フォールバック。`[M2]`/`[M3]` は講評意図から除外。`CritiquePromptContext` も metadata 優先 |

### T10 — オフラインテスト

| 項目 | 内容 |
|------|------|
| 内容 | フォルダ規則、Rating 状態、説明ブロック、pipeline の失敗継続、`iptc_sync_verify` 相当の I/O |
| 完了条件 | `test_offline_suite.py` 拡充または専用テスト。既存スイート非回帰 |
| 依存 | T1–T7 |
| 実装 | **完了** — T10 追加: 画素非破壊(A5)、1枚失敗継続、dry-run 非書き込み、Works 無 dop、`iptc_sync_verify` 呼出、コピー API 不在(A6)、A1–A10 対応表。CI に exiftool を追加 |

---

## 明示的にやらない（第一波）

- H1/H2/H3 の自前レビュー UI  
- Works へのファイルコピー／RAW 現像  
- `.dop` / `.xmp` への書き込み  
- 現像パラメータの講評入力  

---

## 受け入れとの対応

| 仕様受け入れ | 主タスク |
|--------------|----------|
| A1 | T2, T6 |
| A2 | T3 |
| A3 | T4 |
| A4 | T5 |
| A5 | T1, T6（画素非破壊） |
| A6 | （機能を作らないことで満たす） |
| A7 | T8 |
| A8 | T7 |
| A9 | T6 回帰 |
| A10 | T0 |

---

## 次の開発スプリント提案

1. ~~T0-B オーナー DxO 確認（一方向＋双方向）~~ **完了**  
2. ~~T1 `iptc_rating_io`~~ **完了**  
3. ~~T2 `library_unit`~~ **完了**  
4. ~~T3 `shortlist_mechanical`（M1）~~ **完了**  
5. ~~T4 `shortlist_antenna`（M2）~~ **完了**  
6. ~~T5 `shortlist_diversity`（M3）~~ **完了**  
7. ~~T6 `shortlist_pipeline` + `run_shortlist.py`~~ **完了**  
8. ~~T7 `delta_log`~~ **完了**  
9. ~~**T8 Lumina Review（Works）**~~ **完了**  
10. ~~**T9** scanner/講評の JPEG 正への移行~~ **完了**  
11. ~~**T10** オフラインテスト総仕上げ~~ **完了**  

R1′-A 第一波（T0–T10）は実装完了。次は **Mac 手動確認**（[`R1A_MAC_MANUAL_CHECKLIST.md`](R1A_MAC_MANUAL_CHECKLIST.md)）と R1′-B/C。

```bash
python3 prepare_mac_manual_fixtures.py   # ~/Desktop/LuminaManualCheck を生成
open LuminaNotesConsole.command             # またはダブルクリック（旧 LuminaShortlist.command も可）
# チェックリストに PASS/FAIL を記入
```
