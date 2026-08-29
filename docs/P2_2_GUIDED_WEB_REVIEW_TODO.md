# P2-2 Guided Web — レビュー ToDo 正本

更新日: 2026-08-29  
対象: `guided_web/`（Lumina Notes Guided）  
ブランチ: `cursor/p2-2-web-concept-f193` / PR #21  
関連: [`AGENTS.md`](../AGENTS.md) / [`START_NEXT_CONVERSATION.md`](START_NEXT_CONVERSATION.md) / [`P2_2_WEB_APP_CONCEPT.md`](P2_2_WEB_APP_CONCEPT.md) / [`P2_2_GUIDED_MAC_CHECKLIST.md`](P2_2_GUIDED_MAC_CHECKLIST.md) / [`ARCHITECTURE.md`](../ARCHITECTURE.md) / [`P2_2_GUIDED_CRITIQUE_LIFECYCLE.md`](P2_2_GUIDED_CRITIQUE_LIFECYCLE.md)

---

## この文書の位置づけ

「**Guided Web レビュー報告**」（2026-08-29 時点）以降に整理した、**UI/UX・技術・プライバシー**の3軸レビュー結果の正本です。

**2026-08-29 夕方:** Cloud Agent「Guided web review todos」は一区切り。続きは新しい会話。手順は [`START_NEXT_CONVERSATION.md`](START_NEXT_CONVERSATION.md)。貼る文面は [`P2_2_GUIDED_WEB_HANDOFF_PROMPT.md`](P2_2_GUIDED_WEB_HANDOFF_PROMPT.md)。講評ライフサイクル正本: [`P2_2_GUIDED_CRITIQUE_LIFECYCLE.md`](P2_2_GUIDED_CRITIQUE_LIFECYCLE.md)。

### 記号

| 記号 | 意味 |
|------|------|
| `[x]` | 実施済み（コード or テストで確認） |
| `[ ]` | 未対応・要改善 |
| `[~]` | 部分対応（設計上の意図あり／残課題あり） |

### 集計（2026-08-29）

| 軸 | 完了 | 部分 | 未対応 | 合計 |
|----|------|------|--------|------|
| UI/UX（U1–U16） | 16 | 0 | 0 | 16 |
| 技術（T1–T14） | 14 | 0 | 0 | 14 |
| プライバシー（P1–P10） | 9 | 1 | 0 | 10 |

---

## 1. UI/UX レビュー（U1–U16）

オーナー PASS 済みの体験と、レビュー報告以降に挙がった改善案。

| ID | ToDo | 状態 | メモ |
|----|------|------|------|
| U1 | ヘッダー3タブ（選ぶ／読む／振り返る）を自由に行き来できる | [x] | `navigateToScreen`。講評ポーリングはタブ移動で止めない（`ensureCritiqueWatch`） |
| U2 | データ保持ルール（残す・書き出しまで保持／クリアで全消去） | [x] | クリア＝旧「リセット」 |
| U3 | カードプレビューは書き出し時のみ更新（★・一言入力では更新しない） | [x] | `refreshCardPreview` 呼び出し箇所を限定 |
| U4 | 選ぶ・振り返るの入力欄フォントをパラメータ表と揃える（0.9rem） | [x] | `guided.css` |
| U5 | 振り返るカード：★のみ表示・一言は SUMMARY サイズ1行 | [x] | `guided_card.py` |
| U6 | 読む：3プルダウンを Phase2 到着に合わせて順次アクティブ化 | [x] | 観察の輪郭 → １・２・３ → ４・５・６・７ |
| U7 | 読む写真は「言葉にする」後のみ／振り返るカードは「残す」後のみ | [x] | `readPhotoShown` / `prepareReflectScreen` |
| U8 | 「言葉にする」は毎回 `force_restart: true` | [x] | API + クライアント |
| U9 | Mac ネイティブ写真ピッカーでオリジナルフルパスを記録 | [x] | `file_picker.py` / `photo-pick` |
| U10 | 書き出し MD：振り返りブロック・パス行・カンマ区切りメモ・⬜/☑ | [x] | `stock_export.py` |
| U11 | 選ぶ画面に抽象パラメータを表形式表示 | [x] | `parameter_display.py` |
| U12 | Phase2 タイムアウト時に「詳しい言葉を再取得」 | [x] | `guided.js?v=16` |
| U13 | カードプレビューに「書き出しで更新」のヒント文 | [x] | `#card-preview-hint` |
| U14 | 成功・失敗通知を `alert` からトースト等の非モーダルへ | [x] | `showToast` / `#toast-region` |
| U15 | タブ先行遷移時の空状態ガイド（写真未選択・講評未開始等） | [x] | `#read-empty` / `#reflect-empty` + `syncScreenGuides` |
| U16 | 書き出し成功後も振り返るに留まる | [x] | `afterExportSuccess` はトーストのみ（選ぶへ遷移しない。構想 §3 をオーナー判断で上書き） |

---

## 2. 技術レビュー — 起動〜終了のエラーリスク（T1–T14）

| ID | ToDo | 状態 | メモ |
|----|------|------|------|
| T1 | 起動前チェック（python3・依存パッケージ） | [x] | `scripts/run_guided_web.sh` |
| T2 | ポート競合・二重起動の扱い | [x] | 起動スクリプトは既存プロセスを止めて最新で差し替え（単一インスタンス） |
| T3 | サーバ起動失敗時の明確なエラー表示 | [x] | プロセス死亡／タイムアウトでログを出して exit 1 |
| T4 | 写真アップロード／ピッカー失敗の通知 | [x] | トースト。失敗時は既存の写真・パラメータを残す（`adoptPhotoSession` は成功時のみ差し替え） |
| T5 | プレビュー生成失敗時のフォールバック | [x] | 元画像へフォールバック |
| T6 | Phase1 失敗時のエラー表示 | [x] | `status: error` |
| T7 | Phase2 タイムアウト／失敗の復帰 | [x] | `phase2/retry` + UI 再取得 |
| T8 | セッション解放（クリア・写真差し替え） | [x] | `DELETE` / `POST .../release` + `session_cleanup.py` |
| T9 | 講評未完了時のカード生成ガード | [x] | 400 `critique not ready` |
| T10 | 書き出し失敗（★未選択・フォルダ取消） | [x] | クライアント／サーバー双方 |
| T11 | 終了時（Ctrl+C）のクリーンアップ | [x] | FastAPI `lifespan` → `shutdown_sessions`。起動は前面プロセス（Mac で Control+C が効くこと） |
| T12 | クラッシュ時の一時ファイル残存 | [x] | 起動時 `purge_orphan_temp` |
| T13 | 同一セッションへの同時リクエスト制御 | [x] | lock + epoch。正本 [`P2_2_GUIDED_CRITIQUE_LIFECYCLE.md`](P2_2_GUIDED_CRITIQUE_LIFECYCLE.md)。やり直しは `supersede`（`force_restart`）。画面は `/critique/cancel` を呼ばない |
| T14 | タブ閉じ／ポーリング中断後の整理 | [x] | タブ移動・もう一度は `noop`（ポーリング維持）。隠した画面だけ `inert`。タブ閉じは `destroy`（`pagehide` / `release`）。bfcache は触らない |

**主要モジュール:** `guided_web/app.py`, `guided_web/session_cleanup.py`, `guided_web/static/guided.js`

**オフラインテスト:** `test_guided_session_delete_removes_temp_dir`, `test_guided_phase2_retry_restarts_background`, `test_guided_purge_orphan_temp_keeps_live_sessions`, `test_guided_shutdown_sessions_removes_all`, `test_guided_lifespan_purges_orphans_and_shutdown_sessions`, `test_guided_critique_rejects_parallel_without_restart`, `test_guided_phase2_ignores_stale_epoch`, `test_guided_critique_lifecycle_intents_cover_every_operation`, `test_guided_force_restart_supersedes_running_without_cancel`, `test_guided_destroy_bumps_epoch_so_stale_phase2_cannot_complete`

---

## 3. プライバシー監査 — API 処理とデータ管理（P1–P10）

構想 §7（二重経路）と `guided_web/guided_privacy.py` に基づく。

| ID | ToDo | 状態 | メモ |
|----|------|------|------|
| P1 | API 送信画像から EXIF 除去 | [x] | `prepare_vision_image_bytes` |
| P2 | API には抽象パラメータのみ送信 | [x] | `guided_metadata` → `api_params` |
| P3 | プロンプトに個人特定情報を含めない | [x] | `FORBIDDEN_PROMPT_MARKERS` + テスト |
| P4 | 監査ログは許可キーのみ記録 | [x] | `~/.lumina_notes/guided_api_audit.jsonl` |
| P5 | ローカル詳細ログと API 最小化の二重経路 | [~] | メモリセッション + 書き出し MD；永続 `session.json` は未実装 |
| P6 | ユーザー一言は監査でハッシュ化 | [x] | `user_note_sha256` |
| P7 | `image_id` をファイル名と切り離す | [x] | API は UUID（内容ハッシュではない） |
| P8 | 位置情報は都市レベル抽象化（生 GPS 非送信） | [x] | `region` / `time_band` |
| P9 | ローカル設定・キャッシュの管理 | [x] | `guided_settings.json`、ジオコードはローカルのみ |
| P10 | 書き出し MD のフルパス・EXIF はローカルのみ | [x] | API には送らない（設計どおり） |

**オフラインテスト:** `test_guided_privacy_prompts_exclude_identifying_metadata`, `test_guided_privacy_audit_whitelist`, `test_guided_critique_runner_uses_api_params`

**ブラウザ表示の注意:** `original_path` と `meta_block_lines`（先頭12行）は UI 用ローカル表示。OpenAI には送らない。

---

## 4. 優先度付きバックログ（次の実装候補）

上から順に着手する。**T13/T14 の状態機械は 2026-08-29 に正本化。** 次は任意。

1. **P5** — 永続セッションログ（`session.json` 等）（任意）
2. **T4 延長** — アップロードサイズ上限（任意）
3. Mac チェックリスト：オーナー 0–5 と 4i PASS（2026-08-29）。フォルダ選択 Cancel（4f の Cancel）は未確認のまま

---

## 5. Mac 確認（オーナー向け）

```bash
cd ~/photo-critique-bot && git pull origin cursor/p2-2-web-concept-f193
cd ~/photo-critique-bot && bash scripts/run_guided_web.sh
```

ハードリフレッシュ: **⌘ + Shift + R**  
詳細手順: [`P2_2_GUIDED_MAC_CHECKLIST.md`](P2_2_GUIDED_MAC_CHECKLIST.md)

講評の途中でタブを動かす・もう一度・クリア・書き出し Cancel は、Linux の自動テストで状態機械を固定済み。**Mac の写真ピッカー／フォルダ選択／Control+C は未確認**（チェックリスト 3e / 3f / 4b / 4f の Cancel / 5）。

オフライン自動テスト:

```bash
cd ~/photo-critique-bot && python3 test_offline_suite.py
```

---

## 変更履歴

| 日付 | 内容 |
|------|------|
| 2026-08-29 | 初版。レビュー報告以降の UI/UX・技術 T1–T14・プライバシー P1–P10 を正本化 |
| 2026-08-29 | U13–U16 / T3 / T11–T14 を実装。トースト・空状態・終了時 temp 掃除・並行制御・タブ閉じ解放 |
| 2026-08-29 | タブ往復後に選ぶボタンが死ぬ不具合。hidden 画面を inert、ピッカー確定前にセッションを捨てない |
| 2026-08-29 | Mac で書き出しダイアログをキャンセルすると Tk がワーカーで起動しプロセス abort。キャンセルと unavailable を分離 |
| 2026-08-29 | 読むの Phase2 待ち中に選ぶへ行くと講評を cancel してフリーズしていた。タブ移動ではポーリングを維持 |
| 2026-08-29 | 壊れた写真の D&D が既存セッションを先に捨て、プレビューだけ消してパラメータが残っていた。成功時のみ差し替え |
| 2026-08-29 | 「Guided web review todos」を一区切り。T13/T14 を部分対応に戻し、次会話の手順を `AGENTS.md` / `START_NEXT_CONVERSATION.md` に固定 |
| 2026-08-29 | T13/T14 を状態機械で一本化。正本 `P2_2_GUIDED_CRITIQUE_LIFECYCLE.md`。画面は cancel しない。noop / supersede / destroy |
| 2026-08-29 | 「言葉にする」で読むへ移る前に前の講評表示を消す。タブ移動の描き戻しは維持 |
| 2026-08-29 | オーナー Mac：チェック 0–5 と 4i PASS |
