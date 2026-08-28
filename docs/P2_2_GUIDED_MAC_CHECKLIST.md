# P2-2 Guided Web — Mac 起動（コピペ一発）

更新日: 2026-08-28  
対象: オーナー向け。ターミナルに **1行コピペ** で起動できる手順。

---

## いちばん簡単な起動（推奨）

### 方法A: `.command` をダブルクリック

Finder で **`LuminaNotesGuided.command`** をダブルクリック。

---

### 方法B: ターミナルにコピペ一発

**1.** ターミナルを開く（アプリケーション → ユーティリティ → ターミナル）

**2.** 下の1行を **そのまま全部** コピーして、ターミナルに貼り付けて Enter

> `YOUR_REPO_PATH` を、あなたの Mac 上のこのプロジェクトフォルダのパスに置き換えてください。  
> 例: `/Users/あなたの名前/photo-critique-bot`

```bash
cd "YOUR_REPO_PATH" && bash scripts/run_guided_web.sh
```

**具体例**（ユーザー名が `tanaka`、デスクトップに置いた場合）:

```bash
cd "/Users/tanaka/Desktop/photo-critique-bot" && bash scripts/run_guided_web.sh
```

**3.** ブラウザが自動で開き、「選ぶ」画面が出れば OK

**4.** 終了するときは、ターミナルで **Ctrl + C**

---

## 初回だけ（API キー）

講評を動かすときは、ホームフォルダに OpenAI キーを置きます（Console と同じ）:

```bash
echo "sk-あなたのキー" > ~/.openai_api_key && chmod 600 ~/.openai_api_key
```

（`sk-...` は実際のキーに置き換え）

---

## PASS / FAIL

| 確認 | PASS の目安 |
|------|-------------|
| 起動 | ターミナルに `=== Lumina Notes Guided ===` と URL が表示される |
| ブラウザ | 「選ぶ」画面が開く |
| 写真 | 「写真を選ぶ」で画像を選び、下にパラメータ JSON が出る |

---

## うまくいかないとき

| 症状 | 対処（コピペ一発） |
|------|-------------------|
| `python3 が見つかりません` | [python.org](https://www.python.org/downloads/) から Python 3 をインストール |
| ポート使用中 | `GUIDED_WEB_PORT=8766 bash scripts/run_guided_web.sh`（`cd` 付きで実行） |
| ブラウザが開かない | ターミナルに表示された `http://127.0.0.1:8765/` を手動で開く |

関連: [`P2_2_WEB_APP_CONCEPT.md`](P2_2_WEB_APP_CONCEPT.md)
