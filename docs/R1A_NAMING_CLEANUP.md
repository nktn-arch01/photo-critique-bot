# 命名・ブランド語彙の整理リスト（改修案）

更新日: 2026-08-11  
位置づけ: 第三者がコードを読んだときに引っかかりそうな **旧名・混在・ブランド語** の棚卸しと改修案。  
実装は別 PR で段階的に行う（本ファイルは契約メモ）。

関連: [`R1A_DESKTOP_OPS_POLICY.md`](R1A_DESKTOP_OPS_POLICY.md) / [`ARCHITECTURE.md`](../ARCHITECTURE.md)

---

## 0. いまの公式語彙（ユーザー向け）

| 概念 | 公式名 | 意味 |
|------|--------|------|
| 統合ウィンドウ | **Lumina Notes Console** | スクリーニング + Lumina Review |
| 選別パイプライン | **スクリーニング** | M1→M2→M3、JPEG に Rating／説明 |
| Works 上のカード等 | **Lumina Review** | 確定 JPEG へのノート／カード／ログ |
| 旧講評バッチ | **Photo AI 講評**（暫定） | `app_gui`。将来は Console に吸収かブランド整理 |

コード・ファイル・設定キーはまだ旧語が残っている。

---

## 1. 引っかかるポイント一覧

### A. ランチャー／ウィンドウ（ユーザーが最初に見る）

| 現状 | 問題 | 改修案（推奨） | リスク |
|------|------|----------------|--------|
| `LuminaShortlist.command` | ウィンドウは Console なのに Shortlist | **`LuminaNotesConsole.command`** に改名。旧ファイルは互換スタブで新を呼ぶ | Finder のお気に入りが切れる → スタブ残しで緩和 |
| `PhotoAICritique.command` | 「Photo AI」と Lumina Notes が並立 | 当面そのまま。中長期で `LuminaNotesCritique.command` か Console 一本化 | 運用習慣 |
| `shortlist_gui.py` のクラス `ShortlistApp` | ファイル／クラスが shortlist | `console_gui.py` + `ConsoleApp`（段階リネーム） | import 多数 |

### B. モジュール／CLI 名（開発者が読む）

| 現状 | 問題 | 改修案 | リスク |
|------|------|--------|--------|
| `shortlist_*.py` 一式 | 製品語はスクリーニング | **パッケージ化** `screening/` に移すか、ファイルを `screening_*.py` にリネーム | 大。テスト・docs 全更新 |
| `run_shortlist.py` | CLI 名が旧 | `run_screening.py`（旧は薄いラッパ） | 低〜中 |
| `trace_from_works.py` / `run_trace_works.py` | 「trace」＝旧痕跡 | `lumina_review.py` / `run_lumina_review.py` | 中 |
| `WorksTraceRunner` / `list_works_trace_targets` | クラス・関数が trace | `LuminaReviewRunner` / `list_works_review_targets`（エイリアス残す） | 中 |
| `iptc_rating_io.ShortlistMeta` / `write_shortlist_decision` / `read_shortlist_meta` | shortlist 語 | `ScreeningMeta` / `write_screening_decision` 等＋旧名 alias | 中（多用） |
| `is_shortlist_jpeg` | 同上 | `is_screening_jpeg` | 低 |
| schema `lumina.shortlist_session.v1` | JSON 永続 | **v1 は維持**（互換）。v2 で `lumina.screening_session.v2` | 高（既存セッション） |
| ログ prefix `[trace/…]` | GUI ログが旧語 | `[review/…]` に変更 | 低 |

### C. 設定キー（`~/.photo_ai_config.json`）

| 現状 | 問題 | 改修案 | リスク |
|------|------|--------|--------|
| ファイル名 `.photo_ai_config.json` | Photo AI 時代 | 当面維持。将来 `.lumina_notes_config.json` へ移行＋旧読込 | 中 |
| `shortlist_last_dir` | 旧語 | 新キー `screening_last_dir` を追加し、読込時は旧→新フォールバック | 低 |
| `last_dir`（講評） | 意味が曖昧 | `critique_last_dir` に寄せる（任意） | 低 |
| `works_last_dir` | 問題小 | 維持でよい | — |

### D. 出力フォルダ名（ユーザーの Finder）

| 現状 | 問題 | 改修案 | リスク |
|------|------|--------|--------|
| `{ym}評価カード` | 「評価」がブランド原則と衝突 | **`{ym}Luminaカード`** または `{ym}対話カード` | **既存フォルダとの二重化**。読込側は新旧両方探す必要あり |
| `{ym}写真分析ノート` | 「分析」が採点寄り | `{ym}Luminaノート` 等 | 同上 |
| `{ym}写真分析ログ.txt` / 年次 `写真分析ログ_{year}.txt` | 同上 | `{ym}Luminaログ.txt` 等 | 同上 |
| `{ym}処理ステータス.txt` | 問題小 | 維持可 | — |

**推奨方針（出力）:** 一括リネームより、**新出力は新名／読込は新旧両対応**の移行期間を置く。

### E. 画面・ドキュメントの残りカス

| 現状 | 改修案 |
|------|--------|
| `R1_DEEP_LOOP_SPEC` の「対話Lumina Review」「書き込みなし→実装で追加」 | 用語修正＋§0 を現状に合わせて更新 |
| バックログ「評価カード」言及 | 出力改名とセットで更新 |
| `app_gui` ログ「評価カード画像生成中」 | 「カード画像生成中」等 |
| `critique_lens` display_name は既に Lumina Notes | 維持 |

### F. 二製品の並立（設計判断）

| 現状 | 引っかかり | 改修案（段階） |
|------|------------|----------------|
| Console と Photo AI 講評が別 `.command` | 初心者がどっちか分からない | ① ドキュメントで役割表 ② Console に「講評は Works 専用」案内 ③ 将来は講評を Console の Review に一本化 |
| 共有設定 `force_overwrite` / `card_theme` | 意図的共有だが驚き | キー名・UI 注記で「両アプリ共有」と明示（コード分離はしない＝M5） |

---

## 2. 改修の優先順（提案）

### Wave 1 — 低リスク・見た目／入口（**完了 2026-08-11**）

1. ✅ `LuminaNotesConsole.command` 追加 + `LuminaShortlist.command` を互換スタブ化  
2. ✅ GUI／CLI ログの `[trace/` → `[review/`  
3. ✅ docs（SPEC §0・§7.2、ARCHITECTURE）の用語カス掃除  
4. ✅ `app_gui` のユーザー向け「評価カード」文言を弱める（フォルダ名は Wave 2）

### Wave 2 — 出力フォルダ名（データ互換が要る）

1. `DesktopLogManager` で新名に出力  
2. 処理済み判定・カードパス解決は **旧名も探索**  
3. 移行メモを OPS_POLICY に追記  

### Wave 3 — コード識別子（大きな diff）

1. 公開関数に新名＋旧名 alias（1リリース据え置き）  
2. テスト・docs を新名に切替  
3. alias 削除  
4. （任意）`screening/` パッケージ化  

**schema `lumina.shortlist_session.v1` は Wave 3 でも無理に変えない。** 変えるなら専用マイグレーション。

### やらない／後回し

- 既存 Works 内フォルダの自動リネーム（ユーザー資産）  
- Photo AI 講評の即時廃止  
- `.photo_ai_config.json` の強制リネーム（読込フォールバックなし）

---

## 3. 目標マップ（完成形のイメージ）

```text
ユーザー向け:
  LuminaNotesConsole.command  →  Lumina Notes Console
    ├─ スクリーニング（M1–M3）
    └─ Lumina Review（Works）

開発向け（目標）:
  console_gui.py / screening_*.py / lumina_review.py
  run_screening.py / run_lumina_review.py
  ScreeningMeta / write_screening_decision
  schema: lumina.shortlist_session.v1（当面）→ 将来 v2

出力（目標）:
  {ym}Luminaカード / {ym}Luminaノート / {ym}Luminaログ.txt
  （読込は旧「評価カード」「写真分析*」も可）
```

---

## 4. 変更履歴

| 日付 | 内容 |
|------|------|
| 2026-08-11 | 初版。ウォークスルー再確認後の棚卸し |
| 2026-08-11 | Wave 1 完了（ランチャー・ログ prefix・SPEC/ARCHITECTURE・app_gui 文言） |
