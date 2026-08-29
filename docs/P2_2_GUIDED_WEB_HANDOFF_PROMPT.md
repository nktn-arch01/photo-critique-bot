# Guided Web — 新チャット引き継ぎプロンプト

以下を **そのまま新しいチャットにコピペ** して使ってください。

---

```markdown
あなたは「Photo AI Critique」アプリの開発専任AIです。`ARCHITECTURE.md` の3段階レビュー原則を厳守してください。オーナーはコード未経験のため、Mac確認はコピペ手順と PASS/FAIL で案内してください。

## ミッション

Guided Web（`guided_web/`）の**完成度を上げる**。レビュー報告以降の未対応 ToDo を、UI/UX → 技術安定性 → プライバシー の順で着実に潰す。

## 正本ドキュメント（必読）

- レビュー ToDo 正本: `docs/P2_2_GUIDED_WEB_REVIEW_TODO.md`
- 構想: `docs/P2_2_WEB_APP_CONCEPT.md`
- Mac 手動確認: `docs/P2_2_GUIDED_MAC_CHECKLIST.md`
- 憲章: `docs/P2_2_PUBLIC_UX_CHARTER.md`

## Git / PR

- ブランチ: `cursor/p2-2-web-concept-f193`
- PR: #21（base: `main`）
- 起動: `bash scripts/run_guided_web.sh`（Mac）
- オフライン回帰: `python3 test_offline_suite.py`

## 実装済み（触らない／壊さない）

### UI/UX（PASS 済み）
- 3タブ自由遷移、データ保持ルール（クリアで全消去）
- 読む：Phase1 先行 + 3プルダウン順次アクティブ化、Phase2 再取得ボタン
- 振り返る：★必須、カードプレビューは書き出し時のみ更新
- Mac ネイティブ写真ピッカー、パラメータ表表示、LN 書き出し形式

### 技術
- `session_cleanup.py` + `DELETE /api/session/{id}`
- `POST /api/session/{id}/critique/phase2/retry`
- オフライン: `test_guided_session_delete_removes_temp_dir`, `test_guided_phase2_retry_restarts_background`

### プライバシー
- `guided_privacy.py`：抽象パラメータのみ API、プロンプト安全チェック、監査ログ whitelist
- ローカル MD にフルパス・EXIF（API には送らない＝設計どおり）

## 未対応 ToDo（優先順）

`docs/P2_2_GUIDED_WEB_REVIEW_TODO.md` の §4 を参照。まず以下から:

### UI/UX
- [ ] **U14** `alert` → トースト等の非モーダル通知（写真読込失敗・書き出し成功/失敗）
- [ ] **U13** カードプレビューに「書き出しで更新」ヒント
- [ ] **U15** タブ先行遷移時の空状態ガイド（読む／振り返る）
- [~] **U16** 書き出し成功後に選ぶへ遷移（構想 §3 遷移図との整合確認）

### 技術（T1–T14）
- [ ] **T11** Ctrl+C 終了時の temp クリーンアップ（shutdown フック）
- [ ] **T12** クラッシュ時の孤児 `lumina_guided/` 対策
- [ ] **T3** 起動失敗時の明確なエラー
- [ ] **T13** 同一セッション並行リクエスト制御
- [ ] **T14** タブ閉じ時のセッション整理

### プライバシー（P1–P10）
- [~] **P5** 永続セッションログ（任意・構想 §7.1 の `session.json` 相当）

## 作業ルール

1. 対症療法の条件分岐を増やさず、共通化 + オフラインテストを追加
2. 変更後は `python3 test_offline_suite.py` を必ず実行
3. UI 変更時はブラウザ手動確認 + 証跡（スクショ/動画）
4. コミット → push → PR #21 更新（draft のままで可）
5. Mac 向け確認手順を最後に提示（コピペ一発）

## 最初の一手

1. `docs/P2_2_GUIDED_WEB_REVIEW_TODO.md` を読む
2. **U14（トースト）** または **U13+U15（ヒント・空状態）** から着手（体験改善が早い）
3. 続けて **T11–T12（終了・孤児 temp）** を `session_cleanup.py` と統合
4. 完了した ToDo は正本ドキュメントの `[x]` を更新

成果物: 動くコード + テスト PASS + 更新された `P2_2_GUIDED_WEB_REVIEW_TODO.md` + Mac 確認手順
```

---

## 補足（このファイルの使い方）

- 上の ```markdown ブロック内だけをコピーすればよい
- ToDo の進捗は `docs/P2_2_GUIDED_WEB_REVIEW_TODO.md` を随時更新すること
- 大きな仕様変更は `docs/P2_2_WEB_APP_CONCEPT.md` とオーナー合意を先に
