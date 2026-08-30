# Photo AI Critique — エージェント作業ルール

このリポジトリでコードを書く AI（Cloud Agent 含む）は、作業開始時に本ファイルと [`ARCHITECTURE.md`](ARCHITECTURE.md) を読む。オーナーはコード未経験。確認は **コピペ手順と PASS/FAIL** だけにする。デバッグ作業をオーナーに依頼しない。

---

## 必読（この順）

1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — 規則1の **3段階レビュー**（対症療法の条件分岐は禁止）
2. いまの入口の地図: [`docs/CURRENT_APP_MAP.md`](docs/CURRENT_APP_MAP.md)
3. Guided Web を続けるとき: [`docs/START_NEXT_CONVERSATION.md`](docs/START_NEXT_CONVERSATION.md) と [`docs/P2_2_GUIDED_WEB_HANDOFF_PROMPT.md`](docs/P2_2_GUIDED_WEB_HANDOFF_PROMPT.md)

---

## 新しい会話の始め方

- **長いやり直しが続いたスレッドは続けない。** 区切りを宣言したら、必ず新しい会話で再開する。
- Guided Web（PR #21）を続けるときは、ブランチ `cursor/p2-2-web-concept-f193`（またはそれを追跡する最新枝）を使う。`main` だけから始めると Guided のコードが無い。
- 見た目の磨きと、読み込み中・キャンセル・タブ・Mac ダイアログの不具合は **別の依頼** にする。混ぜない。
- モデルは Guided の状態・Mac 固有バグでは **Fast を使わない**（例: Grok 4.6 なら high。high-fast 禁止）。

---

## 完了の定義（「動画を撮った」は完了ではない）

次を満たすまで「直しました／確認不要です」と書かない。

1. 規則1の3段階を、短い文章で残す（根本の不正状態 → 共通化 → 自動テスト）。
2. `python3 test_offline_suite.py` が通る。
3. 変更した経路について、**Cloud Agent の Linux ブラウザだけでは足りないもの** を [`docs/P2_2_GUIDED_MAC_CHECKLIST.md`](docs/P2_2_GUIDED_MAC_CHECKLIST.md) の該当番号で明示する。足りないならテストを足すか、未確認と書く。
4. Mac でサーバーが古いまま残らない（`.app` / `scripts/run_guided_web.sh` が既存プロセスを止めて差し替える前提を壊さない）。画面が無いのにサーバだけ残る状態も「直した」とは言わない。

---

## Guided 単独起動・終了（完了・再開しない）

オーナー宣言 **2026-08-30**: アプリケーションの `Lumina Notes Guided` から選ぶが開く（A1 / A5）、画面の「終了」（A2）、タブ／ブラウザを閉じるとサーバも止まる（A4）までを **完了** とする。Dock アイコン・WebKit・applet・「本物の Mac アプリに見せる」作業は、**新しい依頼がない限り再開しない**。A3（演算中スリープ止めの観察）は任意のまま。

## Guided Mac 起動でやらないこと（2026-08-30 のやり直しから）

`.app` の前に、寿命を一文で書く。**誰が消えたらプロセスが終わるか。** Console は「窓＝プログラム」。Guided の画面はブラウザなので、画面が無ければサーバも止まる、が正本。Dock に出ることはシェル `.app` では約束しない。

一度失敗した描画・Dock ホストを、別の種類に積み替えない。

- WebKit / pywebview / Tk の常駐窓 / JXA / `osacompile` stay-open applet / `task.launch`
- `NSPrincipalClass=NSApplication` を bash に付ける
- オーナーにログ・強制終了・ダイアログ解読を頼んで次のホストを試す

満たせないのは「bash が Cocoa アプリになること」。解けるのは arm64 の python3・ログイン殻・ポートの差し替え・画面の有無に合わせた寿命。Dock が必要なら、それは Mac 上で作る署名済みネイティブが別依頼。

3段階レビューを文章で書いただけでは適用していない。提案が「本物のアプリに見せる別の方法」なら却下する。

---

## Cursor Cloud 固有の注意

Cloud Agent は **Linux VM** で動く。オーナーの本番確認は **Mac**（Tk ダイアログ、標準の写真ピッカー、ターミナルの Control+C、長時間残る uvicorn）である。

やってはいけないこと:

- コンソールから JPEG を流し込んだ・`fetch` を差し替えた・Esc でダイアログを閉じた、だけで Mac のピッカー／書き出し／キャンセルを PASS とする
- 自分で撮ったデモ動画をオーナーに見せて「確認してください」とする（オーナーから映像を求められない限り送らない）
- Linux で Tk が止まる／使えないことを無視して、Mac の書き出し Cancel を未検証のまま完了とする
- 古いサーバーが残っているのに「プログラムを直した」と書く
- CI が緑なことを、フリーズやネイティブダイアログの証明にする

Guided の講評ライフサイクル（言葉にする／もう一度／タブ移動／クリア／書き出し Cancel）は、キャンセル方針をパッチでひっくり返さない。先に「不正な状態を表せない」設計を書いてからコードを変える。正本: [`docs/P2_2_GUIDED_CRITIQUE_LIFECYCLE.md`](docs/P2_2_GUIDED_CRITIQUE_LIFECYCLE.md)。

---

## テスト

- オフライン必須: `python3 test_offline_suite.py`
- Guided 起動（Mac）: アプリケーションの `Lumina Notes Guided`（初回は `bash scripts/install_guided_app.sh`。保険: リポジトリ内 `.app` / `bash scripts/run_guided_web.sh`）
- Console 日常: `LuminaNotesConsole.command`
- OpenAI 実呼び出しは CI では行わない
