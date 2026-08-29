# 次の会話の始め方（オーナー向け）

更新日: 2026-08-29  
対象: コードを書かないオーナー。**ターミナルの難しい操作は不要**です。

LINE のプライバシー整理（全文オフ・匿名分析テーブル・白カード固定・`user_settings` 空）は **ここで一区切り** です。続きは **必ず新しい会話** で始めます。同じスレッドに追加すると、文脈が長くなりやり直しが増えます。

追いかけ用の1枚: [Guided Web — いまの位置](https://app.notion.com/p/3cb5c9f25aba81f9bf29d859363559eb)

---

## 1. いま開いている会話は使わない

次には「もう一点」を書かないでください。

- この LINE プライバシー整理の会話（区切り済み）
- 古い Guided「Guided web review todos」  
  https://cursor.com/agents/bc-840769d0-6290-4c85-9f58-f42fbb122c34

---

## 2. 新しい Cloud Agent を作る

1. Cursor で **新しい Cloud Agent** を開始する  
2. リポジトリ: `nktn-arch01/photo-critique-bot`  
3. **ブランチ（依頼の種類で選ぶ）**
   - **LINE / プライバシー / Render** → `main`
   - **Guided Web（選ぶ／読む／振り返る）** → `cursor/p2-2-web-concept-f193`  
     （`main` だけから始めると Guided のコードが無い）
4. **モデル**: Fast や high-fast は選ばない。**high（通常のしっかりめ）** にする  
5. 最初のメッセージに、[`NEXT_CHAT_HANDOFF_PROMPT.md`](NEXT_CHAT_HANDOFF_PROMPT.md) の **囲みの中だけ** を貼る  
6. その下に、今回やってほしいことを **一つだけ** 書く

---

## 3. 依頼の出し方

一度のメッセージに混ぜないでください。

- 見た目（色・位置）と、動作バグ
- LINE と Guided Web
- 「方針の相談」と「コードを載せる」

確認は **コピペと PASS/FAIL** だけ。デバッグ作業は頼まない。

---

## 4. Mac で動かすとき（必要な場合だけ）

**Guided Web**（新しい会話がコードを push したあと）:

```bash
cd ~/photo-critique-bot
git fetch origin
git checkout cursor/p2-2-web-concept-f193
git pull origin cursor/p2-2-web-concept-f193
bash scripts/run_guided_web.sh
```

**LINE 本番**は Render が `main` をデプロイします。ローカルで LINE サーバーを起動する必要はありません。
