# 次の会話の始め方（オーナー向け）

更新日: 2026-08-29  
対象: コードを書かないオーナー。**ターミナルの難しい操作は不要**です。

「Guided web review todos」の長い作業は **ここで一区切り** です。続きは **必ず新しい会話** で始めます。同じスレッドに追加すると、またやり直しが増えます。

---

## 1. いま開いている長い会話は使わない

Cursor の Cloud Agent 一覧で、次の名前の作業は **終了（または放置）** してください。

- Guided web review todos  
  https://cursor.com/agents/bc-840769d0-6290-4c85-9f58-f42fbb122c34

ここに「もう一点直して」と書かないでください。

---

## 2. 新しい Cloud Agent を作る

1. Cursor で **新しい Cloud Agent** を開始する  
2. リポジトリ: `nktn-arch01/photo-critique-bot`  
3. **ブランチ（重要）**
   - この案内の PR が Guided Web の枝に取り込まれたあと: `cursor/p2-2-web-concept-f193`
   - 取り込む前に始めるとき: この案内を出した枝（例: `cursor/next-session-handoff-d105`）
4. **モデル**: Fast や high-fast は選ばない。**high（通常のしっかりめ）** にする  
5. 最初のメッセージに、次のファイルの **囲みの中だけ** を貼る  
   - [`P2_2_GUIDED_WEB_HANDOFF_PROMPT.md`](P2_2_GUIDED_WEB_HANDOFF_PROMPT.md)

GitHub の PR #21 を開いたまま「この PR で続ける」としても構いません。その場合も **新しい会話** にしてください。

---

## 3. Mac で動かすとき（今までどおり）

新しい会話がコードを push したあと、ターミナルに次をまとめて貼ります。

```bash
cd ~/photo-critique-bot
git fetch origin
git checkout cursor/p2-2-web-concept-f193
git pull origin cursor/p2-2-web-concept-f193
bash scripts/run_guided_web.sh
```

リポジトリの場所が `~/photo-critique-bot` でないときは、1行目だけ自分のフォルダに変えます。  
詳しい PASS/FAIL 表: [`P2_2_GUIDED_MAC_CHECKLIST.md`](P2_2_GUIDED_MAC_CHECKLIST.md)

---

## 4. 依頼の出し方（やり直しを減らす）

一度のメッセージに、次を混ぜないでください。

- 見た目（文字の位置、色、チェックボックスの並び）
- フリーズ・ボタンが死ぬ・書き出しで落ちる

先に「読み込み中のルールを決めて直す」か「見た目だけ」か、どちらか一方にします。
