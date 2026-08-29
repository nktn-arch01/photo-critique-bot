# P2-2 Guided Web — レビュー ToDo 正本

更新日: 2026-08-29  
対象: `guided_web/`（Lumina Notes Guided）  
ブランチ: `cursor/p2-2-web-concept-f193` / PR #21  
関連: [`P2_2_WEB_APP_CONCEPT.md`](P2_2_WEB_APP_CONCEPT.md) / [`P2_2_GUIDED_MAC_CHECKLIST.md`](P2_2_GUIDED_MAC_CHECKLIST.md) / [`ARCHITECTURE.md`](../ARCHITECTURE.md)

---

## この文書の位置づけ

「**Guided Web レビュー報告**」（2026-08-29 時点）以降に整理した、**UI/UX・技術・プライバシー**の3軸レビュー結果の正本です。  
新チャットへの引き継ぎは [`P2_2_GUIDED_WEB_HANDOFF_PROMPT.md`](P2_2_GUIDED_WEB_HANDOFF_PROMPT.md) をコピペしてください。

### 記号

| 記号 | 意味 |
|------|------|
| `[x]` | 実施済み（コード or テストで確認） |
| `[ ]` | 未対応・要改善 |
| `[~]` | 部分対応（設計上の意図あり／残課題あり） |

### 集計（2026-08-29）

| 軸 | 完了 | 部分 | 未対応 | 合計 |
|----|------|------|--------|------|
| UI/UX（U1–U16） | 12 | 1 | 3 | 16 |
| 技術（T1–T14） | 9 | 0 | 5 | 14 |
| プライバシー（P1–P10） | 9 | 1 | 0 | 10 |

---

## 1. UI/UX レビュー（U1–U16）

オーナー PASS 済みの体験と、レビュー報告以降に挙がった改善案。

| ID | ToDo | 状態 | メモ |
|----|------|------|------|
| U1 | ヘッダー3タブ（選ぶ／読む／振り返る）を自由に行き来できる | [x] | `guided.js` `navigateToScreen` |
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
| U12 | Phase2 タイムアウト時に「詳しい言葉を再取得」 | [x] | `guided.js?v=15` |
| U13 | カードプレビューに「書き出しで更新」のヒント文 | [ ] | ユーザーがプレビュー不変を誤解しやすい |
| U14 | 成功・失敗通知を `alert` からトースト等の非モーダルへ | [ ] | 写真読込・書き出しで `alert` 使用中 |
| U15 | タブ先行遷移時の空状態ガイド（写真未選択・講評未開始等） | [ ] | 読む／振り返るを先に開いたときの案内不足 |
| U16 | 書き出し成功後に選ぶへ戻る（構想 §3 遷移図） | [~] | 構想は「書き出し完了 → 選ぶ」；現状は alert のみで画面遷移なし |

---

## 2. 技術レビュー — 起動〜終了のエラーリスク（T1–T14）

| ID | ToDo | 状態 | メモ |
|----|------|------|------|
| T1 | 起動前チェック（python3・依存パッケージ） | [x] | `scripts/run_guided_web.sh` |
| T2 | ポート競合・二重起動の扱い | [x] | `/api/health` + 「すでに起動中」 |
| T3 | サーバ起動失敗時の明確なエラー表示 | [ ] | 起動確認タイムアウトは警告のみ |
| T4 | 写真アップロード／ピッカー失敗の通知 | [x] | HTTP エラー + クライアント alert |
| T5 | プレビュー生成失敗時のフォールバック | [x] | 元画像へフォールバック |
| T6 | Phase1 失敗時のエラー表示 | [x] | `status: error` |
| T7 | Phase2 タイムアウト／失敗の復帰 | [x] | `phase2/retry` + UI 再取得 |
| T8 | セッション解放（クリア・写真差し替え） | [x] | `DELETE /api/session/{id}` + `session_cleanup.py` |
| T9 | 講評未完了時のカード生成ガード | [x] | 400 `critique not ready` |
| T10 | 書き出し失敗（★未選択・フォルダ取消） | [x] | クライアント／サーバー双方 |
| T11 | 終了時（Ctrl+C）のクリーンアップ | [ ] | shutdown フックなし |
| T12 | クラッシュ時の一時ファイル残存 | [ ] | 明示 DELETE 時のみ削除 |
| T13 | 同一セッションへの同時リクエスト制御 | [ ] | `ThreadPoolExecutor(2)` のみ |
| T14 | タブ閉じ／ポーリング中断後の整理 | [ ] | サーバー側セッションは残る |

**主要モジュール:** `guided_web/app.py`, `guided_web/session_cleanup.py`, `guided_web/static/guided.js`

**オフラインテスト:** `test_guided_session_delete_removes_temp_dir`, `test_guided_phase2_retry_restarts_background`

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

上から順に着手する想定。

### 高（体験・安定性）

1. **U14** — トースト通知（alert 置換）
2. **U13** — カードプレビューヒント
3. **U15** — タブ空状態ガイド
4. **T11–T12** — 終了時・異常終了時の temp 一括削除
5. **U16** — 書き出し成功後の選ぶへ遷移（構想との整合）

### 中（堅牢性）

6. **T3** — 起動失敗メッセージの改善
7. **T13** — セッションロック（講評二重開始防止）
8. **T14** — `beforeunload` + セッション解放の検討

### 低（構想拡張・任意）

9. **P5** — 永続セッションログ（`session.json` 等）
10. **T4** — アップロードサイズ上限
11. Mac チェックリスト更新（リセット→クリア、フォルダ UI 変更の反映）

---

## 5. Mac 確認（オーナー向け）

```bash
cd ~/photo-critique-bot && git pull origin cursor/p2-2-web-concept-f193
cd ~/photo-critique-bot && bash scripts/run_guided_web.sh
```

ハードリフレッシュ: **⌘ + Shift + R**  
詳細手順: [`P2_2_GUIDED_MAC_CHECKLIST.md`](P2_2_GUIDED_MAC_CHECKLIST.md)

オフライン自動テスト:

```bash
cd ~/photo-critique-bot && python3 test_offline_suite.py
```

---

## 変更履歴

| 日付 | 内容 |
|------|------|
| 2026-08-29 | 初版。レビュー報告以降の UI/UX・技術 T1–T14・プライバシー P1–P10 を正本化 |
