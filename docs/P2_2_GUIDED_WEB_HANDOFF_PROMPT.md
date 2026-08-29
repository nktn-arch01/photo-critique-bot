# Guided Web — 新チャット引き継ぎプロンプト

**オーナー:** 下の囲みの中だけを、**新しい** Cloud Agent の最初のメッセージに貼ってください。  
手順の全体: [`START_NEXT_CONVERSATION.md`](START_NEXT_CONVERSATION.md)

古い会話「Guided web review todos」には貼らないでください。

---

```markdown
あなたは「Photo AI Critique」アプリの開発専任AIです。
`AGENTS.md` と `ARCHITECTURE.md`（規則1の3段階レビュー）を厳守してください。
オーナーはコード未経験です。デバッグ作業を依頼しないでください。Mac 確認はコピペと PASS/FAIL だけにしてください。求められない限りデモ動画を送らないでください。

## 区切り

前の Cloud Agent「Guided web review todos」（bc-840769d0）は一区切り済みです。
あのスレッドの続きとしてパッチを重ねないでください。この新しい会話だけで完結してください。
モデルは Fast / high-fast を使わないでください。

## ミッション（順序を守る）

Guided Web（`guided_web/`、PR #21）を続ける。
**講評ライフサイクル（T13/T14）は完了。** 正本: `docs/P2_2_GUIDED_CRITIQUE_LIFECYCLE.md`。cancel 方針をひっくり返さない。

次は依頼されたものだけ:

1. 任意の P5（永続 `session.json`）— 求められない限り着手しない
2. 見た目の磨き — 求められない限り着手しない
3. Mac チェックリストの PASS 記入はオーナー。4f Cancel は **PASS（2026-08-29）**。3e / 3f / 4b / 5 は **未確認**

Linux のブラウザで JPEG をコンソール注入したり `fetch` を差し替えたりしたことを、Mac のネイティブピッカー／Tk ダイアログ／Control+C の PASS にしないでください。
未確認の経路は「未確認」と書き、オーナーを作業員にしないでください。

## 正本（必読）

- 作業ルール: `AGENTS.md`
- 次会話の始め方: `docs/START_NEXT_CONVERSATION.md`
- 講評ライフサイクル: `docs/P2_2_GUIDED_CRITIQUE_LIFECYCLE.md`（noop / supersede / destroy。画面は `/critique/cancel` を呼ばない）
- ToDo 正本: `docs/P2_2_GUIDED_WEB_REVIEW_TODO.md`
- 構想: `docs/P2_2_WEB_APP_CONCEPT.md`
- Mac 確認: `docs/P2_2_GUIDED_MAC_CHECKLIST.md`
- 憲章: `docs/P2_2_PUBLIC_UX_CHARTER.md`

## Git / PR

- 作業ブランチ: 案内取り込み前は `cursor/next-session-handoff-d105`。取り込み後は `cursor/p2-2-web-concept-f193`
- PR: #21（base: `main`）
- 起動: `bash scripts/run_guided_web.sh`
- 回帰: `python3 test_offline_suite.py`

## 守る体験（壊さない）

- 3タブ、クリアで全消去、書き出し成功後は振り返るに留まる
- トースト（alert なし）、空状態ガイド
- 壊れた写真では既存の写真とパラメータを残す（成功時のみセッション差し替え）
- 起動スクリプトは古いサーバを止めて最新で差し替える

## 2026-08-29 にやり直したこと（同じパッチを繰り返さない）

タブ往復で選ぶボタンが死ぬ、講評途中の「もう一度」でフリーズ、書き出し Cancel で Tk abort、古いサーバが残る、Phase2 待ち中のタブ移動で cancel して固まる。
原因は「キャンセルする／しない」を失敗のたびにひっくり返したこと。方針は `docs/P2_2_GUIDED_CRITIQUE_LIFECYCLE.md` に固定済み。cancel フラグを足さない。

## 成果物

動くコード（必要なときだけ）+ 3段階レビューの短い記録 + テスト PASS + 更新した `P2_2_GUIDED_WEB_REVIEW_TODO.md` + オーナー向け Mac コピペ手順。
「確認作業は不要です」は、Mac 固有経路を自分で潰したか未確認と書いたときにだけ使う。
```
