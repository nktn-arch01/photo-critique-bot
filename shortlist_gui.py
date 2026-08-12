"""Lumina Notes Console（スクリーニング + Lumina Review の統合 GUI）.

講評バッチ ``app_gui.py`` とは別ウィンドウ・別導線。
- タブ「スクリーニング」: 月／イベントで M1→M2→M3、任意で「カード」生成。H3 は終了時自動
- タブ「Lumina Review」: Works 月フォルダへカード／ノート／ログ（コピーなし・単独実行可）
- 進捗・中断・監査ログ。両タブは必須の前後関係ではない
"""

from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from card_theme import DEFAULT_CARD_THEME, normalize_card_theme
from delta_log import (
    DryRunSessionError,
    list_pending_h3_sessions,
    load_session,
    record_post_h3,
    summarize_session,
)
from desktop_config import load_config as load_shared_config, save_config_merge
from desktop_ui import open_in_file_manager, schedule_on_ui
from library_unit import (
    is_works_month_folder_name,
    list_event_units,
    list_source_jpegs,
    plan_screening_units,
    resolve_session_for_unit,
    unit_from_dir,
)
from ai_vision import get_openai_client
from screening_pipeline import (
    PipelineConfig,
    PipelineProgress,
    ScreeningPipeline,
    overall_multi_unit_status,
)
from screening_cards import ScreeningCardConfig, ScreeningCardRunner
from lumina_review import (
    ReviewConfig,
    ReviewProgress,
    LuminaReviewRunner,
    summarize_review_errors,
    summarize_works_review_selection,
    works_empty_targets_hint,
)


# 主要アクションボタン（macOS では tk.Button の bg が無視されるため ttk+clam）
BTN_DARK_BLUE = "#003d82"
BTN_DARK_BLUE_ACTIVE = "#002655"
BTN_DARK_BLUE_DISABLED = "#5a6d7d"
BTN_FG = "#ffffff"
ACTION_STYLE = "ConsoleAction.TButton"
ACTION_SMALL_STYLE = "ConsoleActionSmall.TButton"


def _configure_console_button_theme(root: tk.Tk) -> ttk.Style:
    """白文字＋ダークブルーの ttk ボタンスタイル（macOS 対応）。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    for style_name, font_size, padding in (
        (ACTION_STYLE, 12, (16, 10)),
        (ACTION_SMALL_STYLE, 11, (16, 8)),
    ):
        style.configure(
            style_name,
            font=("Helvetica", font_size, "bold"),
            foreground=BTN_FG,
            background=BTN_DARK_BLUE,
            padding=padding,
            borderwidth=0,
            focusthickness=0,
            focuscolor=BTN_DARK_BLUE,
        )
        style.map(
            style_name,
            foreground=[("disabled", "#e8eef5"), ("active", BTN_FG), ("pressed", BTN_FG)],
            background=[
                ("disabled", BTN_DARK_BLUE_DISABLED),
                ("active", BTN_DARK_BLUE_ACTIVE),
                ("pressed", BTN_DARK_BLUE_ACTIVE),
            ],
        )
    return style


def _action_button(parent: tk.Misc, *, small: bool = False, **kwargs: object) -> ttk.Button:
    """白文字＋ダークブルーの主要ボタン（ttk）。"""
    for key in ("bg", "activebackground", "fg", "activeforeground", "disabledforeground", "pady", "padx"):
        kwargs.pop(key, None)
    style_name = ACTION_SMALL_STYLE if small else ACTION_STYLE
    return ttk.Button(parent, style=style_name, **kwargs)


def _set_action_button_enabled(btn: ttk.Button, enabled: bool) -> None:
    btn.state(["!disabled"] if enabled else ["disabled"])


class ShortlistApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Lumina Notes Console")
        self.root.geometry("720x820")
        self.root.minsize(640, 700)
        try:
            self.root.tk.call("tk", "scaling", 2.0)
        except Exception:
            pass

        self.is_running = False
        self.pipeline: ScreeningPipeline | None = None
        self.trace_runner: LuminaReviewRunner | None = None
        self.card_runner: ScreeningCardRunner | None = None
        self.last_session_path: Path | None = None
        self.config = self.load_config()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        _configure_console_button_theme(self.root)
        self.setup_ui()

    def load_config(self) -> dict:
        cfg = load_shared_config(
            defaults={
                "force_overwrite": False,
                "card_theme": DEFAULT_CARD_THEME,
                "console_last_tab": "screening",
            }
        )
        cfg["force_overwrite"] = bool(cfg.get("force_overwrite", False))
        cfg["card_theme"] = normalize_card_theme(cfg.get("card_theme", DEFAULT_CARD_THEME))
        tab = str(cfg.get("console_last_tab") or "screening").strip().lower()
        cfg["console_last_tab"] = "review" if tab == "review" else "screening"
        return cfg

    def save_config(
        self,
        target_dir: str | None = None,
        *,
        works_dir: str | None = None,
        console_tab: str | None = None,
    ) -> None:
        try:
            updates: dict = {}
            if target_dir:
                updates["shortlist_last_dir"] = target_dir
            if works_dir:
                updates["works_last_dir"] = works_dir
            if console_tab:
                updates["console_last_tab"] = (
                    "review" if console_tab == "review" else "screening"
                )
            if not updates:
                return
            self.config = save_config_merge(updates, current=self.config)
        except Exception as e:
            self.log(f"設定の保存に失敗: {e}")

    def setup_ui(self) -> None:
        main = ttk.Frame(self.root, padding="15")
        main.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.tab_screening = ttk.Frame(self.notebook, padding="8")
        self.tab_review = ttk.Frame(self.notebook, padding="8")
        self.notebook.add(self.tab_screening, text=" スクリーニング ")
        self.notebook.add(self.tab_review, text=" Lumina Review ")

        self._build_screening_tab(self.tab_screening)
        self._build_review_tab(self.tab_review)
        self._build_shared_status(main)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        if self.config.get("console_last_tab") == "review":
            self.notebook.select(self.tab_review)

    def _build_screening_tab(self, parent: ttk.Frame) -> None:
        info = ttk.LabelFrame(parent, text=" このタブでできること ", padding="8")
        info.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            info,
            text=(
                "流れ（このタブだけ）: 候補付け →（任意）DxO記録\n"
                "Lumina Review は隣のタブ（独立・必須ではありません）\n\n"
                "オリジナルの月／イベントを選び、候補の Rating を付けます。\n"
                "月の配下イベントは既定で対象外。必要なときだけ下のチェックをON。\n\n"
                "Rating（DxO の「出来の星」とは別）:\n"
                "  0=除外 / 1=M1 / 2=M2 / 3=余白 / 4=上位"
            ),
            justify=tk.LEFT,
        ).pack(anchor=tk.W)

        folder = ttk.LabelFrame(parent, text=" 対象フォルダ ", padding="10")
        folder.pack(fill=tk.X, pady=(0, 10))
        self.dir_var = tk.StringVar(value=self.config.get("shortlist_last_dir", ""))
        self.dir_entry = ttk.Entry(folder, textvariable=self.dir_var, font=("Helvetica", 11))
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.btn_browse = ttk.Button(folder, text=" 参照... ", command=self.browse_folder)
        self.btn_browse.pack(side=tk.RIGHT)

        opts = ttk.LabelFrame(parent, text=" 実行オプション ", padding="8")
        opts.pack(fill=tk.X, pady=(0, 10))
        stage_row = ttk.Frame(opts)
        stage_row.pack(fill=tk.X)
        self.var_m1 = tk.BooleanVar(value=True)
        self.var_m2 = tk.BooleanVar(value=True)
        self.var_m3 = tk.BooleanVar(value=True)
        self.var_dry = tk.BooleanVar(value=False)
        self.var_include_events = tk.BooleanVar(value=False)
        ttk.Checkbutton(stage_row, text="M1 機械", variable=self.var_m1).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(stage_row, text="M2 アンテナ", variable=self.var_m2).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(stage_row, text="M3 多様性", variable=self.var_m3).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(opts, text="ドライラン（JPEGへ書かない／監査は残す）", variable=self.var_dry).pack(
            anchor=tk.W, pady=(6, 0)
        )
        self.chk_include_events = ttk.Checkbutton(
            opts,
            text="配下イベントも順に実行（月フォルダのとき）",
            variable=self.var_include_events,
        )
        self.chk_include_events.pack(anchor=tk.W, pady=(4, 0))
        self.event_option_label = ttk.Label(opts, text="")
        self.event_option_label.pack(anchor=tk.W, pady=(2, 0))

        actions = ttk.Frame(parent)
        actions.pack(fill=tk.X, pady=(0, 10))
        self.btn_start = _action_button(
            actions,
            text="スクリーニングを開始",
            command=self.start_batch_thread,
        )
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True)

        h3 = ttk.LabelFrame(parent, text=" 監査・カード ", padding="8")
        h3.pack(fill=tk.X)
        ttk.Label(
            h3,
            text=(
                "DxO で Rating を直したあとの差分は、ウィンドウを閉じるときに自動で残します"
                "（手動操作は不要）。\n"
                "「カード」は Rating 3/4 の JPEG に Phase1 カードを付け、説明欄へ TITLE 等を書き込みます。"
            ),
            wraplength=640,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 6))
        h3_btns = ttk.Frame(h3)
        h3_btns.pack(fill=tk.X)
        self.btn_screening_card = _action_button(
            h3_btns, text="カード生成", command=self.start_screening_card_thread, small=True
        )
        self.btn_screening_card.pack(side=tk.LEFT)
        self.card_force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            h3_btns, text="処理済みも上書き", variable=self.card_force_var
        ).pack(side=tk.LEFT, padx=(10, 0))
        self.btn_open_session = ttk.Button(h3_btns, text="監査フォルダを開く", command=self.open_sessions_folder)
        self.btn_open_session.pack(side=tk.LEFT, padx=(8, 0))
        self.session_label = ttk.Label(h3, text="セッション: （まだありません）")
        self.session_label.pack(anchor=tk.W, pady=(6, 0))

        # 起動時の対象フォルダがあればイベント選択肢を更新
        try:
            initial = Path(self.dir_var.get().strip())
            if initial.is_dir():
                self._refresh_event_option(unit_from_dir(initial))
            else:
                self._refresh_event_option(None)
        except Exception:
            self._refresh_event_option(None)

    def _build_review_tab(self, parent: ttk.Frame) -> None:
        info = ttk.LabelFrame(parent, text=" このタブでできること ", padding="8")
        info.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            info,
            text=(
                "Works 月フォルダの JPEG に対話ノート／カードを付けます。\n"
                "スクリーニング無しでも、ここに画像があれば単独で実行できます。\n"
                "ファイルのコピーはしません。\n\n"
                "Works は YYYYMM のみ（例: ~/2026/202606）。\n"
                "同一コマは {stem}_dev.jpg を優先（撮って出し除外は確認時に表示）。"
            ),
            justify=tk.LEFT,
        ).pack(anchor=tk.W)

        works = ttk.LabelFrame(parent, text=" Works 月フォルダ ", padding="8")
        works.pack(fill=tk.X, pady=(0, 10))
        works_row = ttk.Frame(works)
        works_row.pack(fill=tk.X)
        self.works_dir_var = tk.StringVar(value=self.config.get("works_last_dir", ""))
        self.works_entry = ttk.Entry(works_row, textvariable=self.works_dir_var, font=("Helvetica", 11))
        self.works_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.btn_browse_works = ttk.Button(works_row, text=" 参照... ", command=self.browse_works_folder)
        self.btn_browse_works.pack(side=tk.RIGHT)

        works_opts = ttk.Frame(works)
        works_opts.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(works_opts, text="深さ:").pack(side=tk.LEFT)
        self.trace_mode_var = tk.StringVar(value="full")
        ttk.Radiobutton(
            works_opts, text="詳細（カード＋長文）", variable=self.trace_mode_var, value="full"
        ).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Radiobutton(
            works_opts, text="簡易（カードのみ）", variable=self.trace_mode_var, value="compact"
        ).pack(side=tk.LEFT, padx=(0, 12))
        self.trace_force_var = tk.BooleanVar(value=bool(self.config.get("force_overwrite", False)))
        ttk.Checkbutton(works_opts, text="処理済みも上書き", variable=self.trace_force_var).pack(side=tk.LEFT)

        theme_row = ttk.Frame(works)
        theme_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(theme_row, text="カード背景:").pack(side=tk.LEFT)
        self.trace_theme_var = tk.StringVar(
            value=normalize_card_theme(self.config.get("card_theme", DEFAULT_CARD_THEME))
        )
        ttk.Radiobutton(theme_row, text="ダーク", variable=self.trace_theme_var, value="dark").pack(
            side=tk.LEFT, padx=(4, 8)
        )
        ttk.Radiobutton(theme_row, text="ライト", variable=self.trace_theme_var, value="light").pack(
            side=tk.LEFT
        )

        works_btns = ttk.Frame(parent)
        works_btns.pack(fill=tk.X, pady=(0, 4))
        self.btn_trace = _action_button(
            works_btns,
            text="Lumina Review を開始",
            command=self.start_trace_thread,
        )
        self.btn_trace.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _build_shared_status(self, parent: ttk.Frame) -> None:
        prog = ttk.Frame(parent)
        prog.pack(fill=tk.X, pady=(10, 8))
        top = ttk.Frame(prog)
        top.pack(fill=tk.X)
        self.status_label = ttk.Label(top, text="準備完了", font=("Helvetica", 10))
        self.status_label.pack(side=tk.LEFT, anchor=tk.W)
        self.btn_cancel = _action_button(
            top,
            text="中止",
            small=True,
            command=self.request_cancel,
        )
        self.btn_cancel.state(["disabled"])
        self.btn_cancel.pack(side=tk.RIGHT)
        self.progress = ttk.Progressbar(prog, mode="indeterminate")
        self.progress.pack(fill=tk.X, pady=(5, 0))

        log_frame = ttk.LabelFrame(parent, text=" 実行ログ（両タブ共通） ", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(
            log_frame, wrap=tk.WORD, font=("Menlo", 10), state=tk.DISABLED, bg="#1e1e1e", fg="#d4d4d4"
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scroll.set)

    def _current_tab_id(self) -> str:
        try:
            current = self.notebook.select()
            if current == str(self.tab_review):
                return "review"
        except Exception:
            pass
        return "screening"

    def _on_tab_changed(self, _event=None) -> None:
        tab_id = self._current_tab_id()
        if self.config.get("console_last_tab") == tab_id:
            return
        self.save_config(console_tab=tab_id)

    def _refresh_event_option(self, unit) -> None:
        """月＋イベントがあるときだけ「配下イベントも順に」を有効化（B2）。"""
        if unit is not None and getattr(unit, "is_month", False):
            try:
                events = list_event_units(unit)
            except Exception:
                events = []
            if events:
                self.chk_include_events.state(["!disabled"])
                self.event_option_label.config(
                    text=f"配下イベント: {len(events)} 件（ON にすると月のあと順に実行）"
                )
                return
        self.var_include_events.set(False)
        self.chk_include_events.state(["disabled"])
        if unit is not None and getattr(unit, "is_event", False):
            self.event_option_label.config(text="イベント単位のため、このフォルダのみ実行します")
        else:
            self.event_option_label.config(text="")

    def browse_folder(self) -> None:
        current = self.dir_var.get()
        initial = current if Path(current).exists() else str(Path.home())
        selected = filedialog.askdirectory(
            initialdir=initial, title="月またはイベントフォルダを選択"
        )
        if selected:
            self.dir_var.set(selected)
            self.save_config(selected)
            self.log(f"対象フォルダ: {selected}")
            self._refresh_session_label(Path(selected))
            try:
                unit = unit_from_dir(Path(selected))
                self._refresh_event_option(unit)
                if unit is not None and unit.is_month:
                    events = list_event_units(unit)
                    if events and not self.var_include_events.get():
                        self.log(
                            f"注意: 既定は月直下のみ。イベント配下 {len(events)} 件は"
                            "「配下イベントも順に実行」で含められます。"
                        )
            except Exception:
                self._refresh_event_option(None)

    def browse_works_folder(self) -> None:
        current = self.works_dir_var.get()
        initial = current if Path(current).exists() else str(Path.home())
        selected = filedialog.askdirectory(
            initialdir=initial, title="Works 月フォルダ（YYYYMM）を選択"
        )
        if selected:
            self.works_dir_var.set(selected)
            self.save_config(works_dir=selected)
            name = Path(selected).name
            if not is_works_month_folder_name(name):
                self.log(
                    f"Works フォルダ: {selected}（注意: 名前が YYYYMM ではありません: {name}）"
                )
            try:
                works_path = Path(selected)
                summary = summarize_works_review_selection(works_path)
                n = len(summary["targets"])
                skipped = len(summary["sooc_skipped"])
                hint = works_empty_targets_hint(works_path) if n == 0 else ""
                skip_note = f"／_dev優先で撮って出し除外 {skipped}" if skipped else ""
                self.log(
                    f"Works フォルダ: {selected}"
                    f"（対象 {n} 枚＝_dev {summary['dev_count']}＋撮って出し {summary['sooc_count']}"
                    f"{skip_note}）{hint.strip()}"
                )
            except Exception as e:
                self.log(f"Works フォルダ: {selected}（列挙注意: {e}）")

    def _ui(self, fn) -> None:
        """ワーカー→UI。ウィンドウ破棄後は何もしない（L1）。"""
        schedule_on_ui(self.root, fn)

    def log(self, message: str) -> None:
        def _append() -> None:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            n = int(self.log_text.index("end-1c").split(".")[0])
            if n > 1000:
                self.log_text.delete("1.0", f"{n - 1000}.0")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

        self._ui(_append)

    def _set_status(self, text: str) -> None:
        self._ui(lambda: self.status_label.config(text=text))

    def _refresh_session_label(self, unit_dir: Path) -> None:
        """表示用: この unit 配下の最新セッション。"""
        latest = resolve_session_for_unit(unit_dir, self.last_session_path)
        self.last_session_path = latest
        if latest:
            self.session_label.config(text=f"セッション: {latest.name}")
        else:
            self.session_label.config(text="セッション: （まだありません）")

    def request_cancel(self) -> None:
        if self.is_running:
            if self.pipeline:
                self.pipeline.request_cancel()
            if self.trace_runner:
                self.trace_runner.request_cancel()
            if self.card_runner:
                self.card_runner.request_cancel()
            self.log("中止リクエストを受け付けました…")
            self.btn_cancel.state(["disabled"])

    def _ensure_openai_ready(self) -> bool:
        """M2/M3 または Lumina Review の開始前に API キーを確認（§2.5 / Wave A1）。"""
        try:
            get_openai_client()
            return True
        except Exception as e:
            messagebox.showerror(
                "APIキーがありません",
                "OpenAI APIキーを用意してから実行してください。\n\n"
                "置き場所: ~/.openai_api_key\n"
                "または環境変数 OPENAI_API_KEY\n\n"
                f"詳細: {e}",
            )
            return False

    def _pending_h3_session(self) -> Path | None:
        """互換: 対象フォルダ（＋月ならイベント）の未記録のうち先頭。"""
        pending = self._pending_h3_list()
        return pending[0][1] if pending else None

    def _pending_h3_list(self) -> list[tuple[str, Path]]:
        """いまの対象フォルダ基準の未記録 H3（月なら配下イベントも含む）。"""
        target = Path(self.dir_var.get().strip())
        if not target.is_dir():
            return []
        return list_pending_h3_sessions(target)

    def on_closing(self) -> None:
        if self.is_running:
            if messagebox.askyesno("確認", "処理実行中です。終了しますか？"):
                if self.pipeline:
                    self.pipeline.request_cancel()
                if self.trace_runner:
                    self.trace_runner.request_cancel()
                if self.card_runner:
                    self.card_runner.request_cancel()
                self.root.destroy()
            return

        # Wave C: 未記録 H3 は終了時に自動記録（ユーザー作業ではない）
        self._auto_record_pending_h3_on_close()
        self.root.destroy()

    def _auto_record_pending_h3_on_close(self) -> None:
        """コンソール終了時に未記録 H3 を静かに記録する。失敗はログのみ。"""
        pending = self._pending_h3_list()
        if not pending:
            return
        self._set_status("終了前: DxO修正後を自動記録中…")
        for label, session in pending:
            try:
                sess_doc = load_session(session)
                if sess_doc.get("write_meta") is False:
                    self.log(f"H3自動スキップ（ドライラン）: {label} / {session.name}")
                    continue
                unit_path_raw = sess_doc.get("library_unit_path")
                unit_dir = Path(unit_path_raw) if unit_path_raw else None
                unit = unit_from_dir(unit_dir) if unit_dir and unit_dir.is_dir() else None
                if unit is None:
                    self.log(f"H3自動スキップ（単位不明）: {session.name}")
                    continue
                doc = record_post_h3(session, unit=unit)
                delta = doc.get("h3_delta") or {}
                self.log(
                    f"H3自動記録: {label} changed={delta.get('changed_count')} "
                    f"unchanged={delta.get('unchanged_count')}"
                )
            except DryRunSessionError as e:
                self.log(f"H3自動スキップ: {e}")
            except Exception as e:
                self.log(f"H3自動記録エラー ({label}): {e}")
        self._set_status("終了します…")

    def start_batch_thread(self) -> None:
        if self.is_running:
            return
        target = Path(self.dir_var.get().strip())
        if not target.is_dir():
            messagebox.showerror("エラー", f"フォルダがありません:\n{target}")
            return
        unit = unit_from_dir(target)
        if unit is None:
            messagebox.showerror(
                "フォルダ名エラー",
                "月（YYYYMM または OM202606 等の XXYYYYMM）か、\n"
                "イベント（YYYYMMDD_名前 または OM20260615_旅行 等）を選んでください。\n"
                f"現在: {target.name}",
            )
            return
        if not (self.var_m1.get() or self.var_m2.get() or self.var_m3.get()):
            messagebox.showwarning("警告", "M1 / M2 / M3 のいずれかを選んでください。")
            return

        needs_api = bool(self.var_m2.get() or self.var_m3.get())
        if needs_api and not self._ensure_openai_ready():
            return

        include_events = bool(self.var_include_events.get()) and unit.is_month
        planned = plan_screening_units(unit, include_child_events=include_events)
        jpeg_total = sum(len(list_source_jpegs(u)) for u in planned)
        if jpeg_total <= 0:
            messagebox.showwarning("警告", f"対象 JPEG がありません:\n{target}")
            return

        # M3: 開始時点の UI 値をスナップショット（ワーカーは Tk 変数を読まない）
        opts = {
            "run_m1": bool(self.var_m1.get()),
            "run_m2": bool(self.var_m2.get()),
            "run_m3": bool(self.var_m3.get()),
            "dry": bool(self.var_dry.get()),
            "include_events": include_events,
        }
        stages = []
        if opts["run_m1"]:
            stages.append("M1")
        if opts["run_m2"]:
            stages.append("M2")
        if opts["run_m3"]:
            stages.append("M3")

        if include_events:
            event_count = max(0, len(planned) - 1)
            scope_note = (
                f"\n実行単位: 月 1 ＋ イベント {event_count} ＝ {len(planned)} 単位"
                f"（月直下 → イベント順）"
            )
        elif unit.is_month:
            try:
                events = list_event_units(unit)
            except Exception:
                events = []
            scope_note = (
                f"\n注意: イベント配下 {len(events)} 件は今回の対象外"
                "（必要なときは「配下イベントも順に実行」）"
                if events
                else ""
            )
        else:
            scope_note = ""

        if not messagebox.askyesno(
            "実行確認",
            f"対象: {unit.kind} / {unit.unit_id}"
            + (f"（機種 {unit.camera_code}）" if unit.camera_code else "")
            + f"\nJPEG: {jpeg_total} 枚"
            + scope_note
            + f"\n段: {', '.join(stages)}\n"
            f"書き込み: {'しない（ドライラン）' if opts['dry'] else 'する'}\n\n"
            "スクリーニングを開始しますか？",
        ):
            return

        unit_paths = [u.path for u in planned]
        self.save_config(str(target))
        self.is_running = True
        _set_action_button_enabled(self.btn_start, False)
        _set_action_button_enabled(self.btn_cancel, True)
        self.btn_browse.config(state=tk.DISABLED)
        self.btn_screening_card.config(state=tk.DISABLED)
        _set_action_button_enabled(self.btn_trace, False)
        self.btn_browse_works.config(state=tk.DISABLED)
        self.dir_entry.config(state=tk.DISABLED)
        self.works_entry.config(state=tk.DISABLED)
        self.chk_include_events.state(["disabled"])
        self.progress.start(12)
        threading.Thread(target=self._run_batch, args=(unit_paths, opts), daemon=True).start()

    def _run_batch(self, unit_paths: list[Path], opts: dict) -> None:
        primary = unit_paths[0] if unit_paths else Path(".")
        try:
            def on_progress(p: PipelineProgress) -> None:
                self.log(f"[{p.stage}] {p.message}")
                self._set_status(p.message)

            self.pipeline = ScreeningPipeline(
                PipelineConfig(
                    write=not opts["dry"],
                    run_m1=opts["run_m1"],
                    run_m2=opts["run_m2"],
                    run_m3=opts["run_m3"],
                    persist_session=True,
                ),
                on_progress=on_progress,
            )
            self.log("=" * 48)
            self.log(
                f"スクリーニング開始: {len(unit_paths)} 単位"
                + ("（イベント含む）" if opts.get("include_events") else "")
            )

            results = []
            stopped_before_next_unit = False
            for idx, target in enumerate(unit_paths, 1):
                if self.pipeline.is_cancel_requested():
                    stopped_before_next_unit = True
                    break
                self.log(f"--- ({idx}/{len(unit_paths)}) {target.name} ---")
                result = self.pipeline.run_on_dir(target)
                results.append(result)
                self.last_session_path = result.session_path
                self.log(f"status: {result.status}")
                self.log(f"counts_hint: {result.counts_by_rating_hint()}")
                if result.session_path:
                    self.log(f"監査ログ: {result.session_path}")
                    try:
                        summary = summarize_session(load_session(result.session_path))
                        self.log(
                            f"pre_h3 counts: {summary.get('pre_h3_counts')} "
                            f"(この時点が DxO 修正前の記録です)"
                        )
                    except Exception as e:
                        self.log(f"サマリ読取注意: {e}")
                if result.status == "cancelled" or result.cancelled:
                    break
                if result.status == "failed":
                    break

            self.log("=" * 48)
            jpeg_sum = sum(r.jpeg_count for r in results)
            overall = overall_multi_unit_status(
                planned_count=len(unit_paths),
                statuses=[r.status for r in results],
                cancelled_flags=[bool(r.cancelled) for r in results],
                stopped_before_next_unit=stopped_before_next_unit,
            )
            last = results[-1] if results else None
            fail_err = next((r.error for r in results if r.error), None)
            event_h3_note = ""
            if opts.get("include_events") and not opts.get("dry") and overall == "completed":
                event_h3_note = (
                    "\n配下イベントの DxO 差分も、コンソール終了時にまとめて自動記録します。"
                )

            def _done() -> None:
                self._refresh_session_label(primary)
                self.status_label.config(text=f"処理{overall}")
                session_name = (
                    last.session_path.name if last and last.session_path else "なし"
                )
                units_done = len(results)
                planned = len(unit_paths)
                if overall == "completed":
                    if opts["dry"]:
                        next_steps = (
                            "今回はドライランのため JPEG には書いていません。\n"
                            "書き込みありで再実行してください。"
                            "（ドライラン分は終了時の自動記録対象外です）"
                        )
                    else:
                        next_steps = (
                            "DxO で Rating を直したら、このままコンソールを閉じてください"
                            "（修正後の差分は自動記録されます）。"
                            f"{event_h3_note}\n"
                            "任意: 同じタブの「カード生成」で Rating 3/4 にカードを付けられます。\n"
                            "Lumina Review は別タブです（Works に画像があれば単独で可）。"
                        )
                    title = "完了"
                    msg = (
                        f"スクリーニングが完了しました。\n\n"
                        f"単位: {units_done}/{planned} / JPEG: {jpeg_sum} 枚\n"
                        f"対象フォルダのセッション表示: 月側を優先\n"
                        f"最後に処理したセッション: {session_name}\n\n"
                        f"{next_steps}"
                    )
                elif overall == "cancelled":
                    title = "中止"
                    msg = (
                        f"スクリーニングを中止しました。\n\n"
                        f"処理した単位: {units_done}/{planned}\n"
                        f"JPEG: {jpeg_sum} 枚\n"
                        f"最後に処理したセッション: {session_name}"
                    )
                else:
                    title = "未完了"
                    msg = (
                        f"スクリーニングは完了しませんでした（{overall}）。\n\n"
                        f"単位: {units_done}/{planned} / JPEG: {jpeg_sum} 枚\n"
                        f"最後に処理したセッション: {session_name}\n"
                        f"エラー: {fail_err or '（詳細はログを確認）'}"
                    )
                messagebox.showinfo(title, msg)

            self._ui(_done)
        except Exception as e:
            err_msg = str(e)
            self.log(f"エラー: {err_msg}")
            self._ui(lambda msg=err_msg: messagebox.showerror("エラー", msg))
        finally:
            self._ui(self.reset_ui)

    def reset_ui(self) -> None:
        self.is_running = False
        self.pipeline = None
        self.trace_runner = None
        self.card_runner = None
        self.progress.stop()
        _set_action_button_enabled(self.btn_start, True)
        _set_action_button_enabled(self.btn_cancel, False)
        self.btn_browse.config(state=tk.NORMAL)
        self.btn_screening_card.config(state=tk.NORMAL)
        _set_action_button_enabled(self.btn_trace, True)
        self.btn_browse_works.config(state=tk.NORMAL)
        self.dir_entry.config(state=tk.NORMAL)
        self.works_entry.config(state=tk.NORMAL)
        try:
            unit = unit_from_dir(Path(self.dir_var.get().strip()))
        except Exception:
            unit = None
        self._refresh_event_option(unit)

    def start_trace_thread(self) -> None:
        if self.is_running:
            return
        works = Path(self.works_dir_var.get().strip())
        if not works.is_dir():
            messagebox.showerror("エラー", f"Works フォルダがありません:\n{works}")
            return
        if not is_works_month_folder_name(works.name):
            messagebox.showerror(
                "フォルダ名エラー",
                "Works Lumina Review の対象は月フォルダ YYYYMM のみです。\n"
                f"例: ~/2026/202606\n現在: {works.name}",
            )
            return
        try:
            selection = summarize_works_review_selection(works)
            targets = selection["targets"]
        except Exception as e:
            messagebox.showerror("エラー", str(e))
            return
        if not targets:
            messagebox.showwarning(
                "対象なし",
                "Lumina Review 対象の JPEG がありません。\n"
                "{stem}_dev.jpg または撮って出し .jpg を月フォルダ直下に置いてください。"
                + works_empty_targets_hint(works),
            )
            return

        if not self._ensure_openai_ready():
            return

        opts = {
            "mode": self.trace_mode_var.get(),
            "theme": normalize_card_theme(self.trace_theme_var.get()),
            "force": bool(self.trace_force_var.get()),
        }
        skipped = selection["sooc_skipped"]
        skip_note = ""
        if skipped:
            names = ", ".join(p.name for p in skipped[:5])
            more = f" 他{len(skipped) - 5}件" if len(skipped) > 5 else ""
            skip_note = (
                f"\n_dev 優先で撮って出し除外: {len(skipped)} 枚"
                f"（{names}{more}）"
            )
        depth_label = "詳細（カード＋長文）" if opts["mode"] == "full" else "簡易（カードのみ）"
        if not messagebox.askyesno(
            "Lumina Review の確認",
            f"Works: {works}\n"
            f"対象: {len(targets)} 枚"
            f"（_dev {selection['dev_count']}／撮って出し {selection['sooc_count']}）"
            f"{skip_note}\n"
            f"深さ: {depth_label} / テーマ: {opts['theme']}\n"
            f"上書き: {'する' if opts['force'] else 'しない'}\n\n"
            "コピーはしません。対話ノート／カードを付けますか？",
        ):
            return

        self.config["card_theme"] = opts["theme"]
        self.config["force_overwrite"] = opts["force"]
        self.save_config(works_dir=str(works))
        self.is_running = True
        _set_action_button_enabled(self.btn_start, False)
        _set_action_button_enabled(self.btn_cancel, True)
        self.btn_browse.config(state=tk.DISABLED)
        self.btn_screening_card.config(state=tk.DISABLED)
        _set_action_button_enabled(self.btn_trace, False)
        self.btn_browse_works.config(state=tk.DISABLED)
        self.dir_entry.config(state=tk.DISABLED)
        self.works_entry.config(state=tk.DISABLED)
        self.progress.start(12)
        threading.Thread(target=self._run_trace, args=(works, opts), daemon=True).start()

    def _run_trace(self, works: Path, opts: dict) -> None:
        try:
            def on_progress(p: ReviewProgress) -> None:
                self.log(f"[review/{p.stage}] {p.message}")
                self._set_status(p.message)

            self.trace_runner = LuminaReviewRunner(
                ReviewConfig(
                    mode=opts["mode"],
                    force_overwrite=opts["force"],
                    card_theme=opts["theme"],
                    pixel_priority=True,
                ),
                on_progress=on_progress,
            )
            self.log("=" * 48)
            self.log(f"Works Lumina Review 開始: {works}")
            result = self.trace_runner.run(works)
            self.log(
                f"status={result.status} processed={result.processed} "
                f"skipped={result.skipped} errors={result.errors}"
            )
            self.log("=" * 48)

            def _done() -> None:
                self.status_label.config(text=f"Lumina Review {result.status}")
                status = result.status or "unknown"
                err_block = summarize_review_errors(result)
                err_note = f"\n\nエラー詳細:\n{err_block}" if err_block else ""
                if status == "completed":
                    msg = (
                        "対話痕跡ができました。\n\n"
                        f"対象: {result.targets_found} 枚\n"
                        f"新規: {result.processed}\n"
                        f"スキップ: {result.skipped}\n"
                        f"エラー: {result.errors}"
                        f"{err_note}\n\n"
                        f"出力先:\n{works}\n\n"
                        "Works フォルダを開きますか？"
                    )
                    if messagebox.askyesno("Lumina Review", msg):
                        try:
                            open_in_file_manager(works)
                        except Exception as e:
                            self.log(f"フォルダを開けませんでした: {e}")
                            messagebox.showwarning("注意", f"フォルダを開けませんでした:\n{e}")
                elif status == "cancelled":
                    msg = (
                        "Lumina Review を中止しました。\n\n"
                        f"新規: {result.processed} / スキップ: {result.skipped}\n"
                        f"エラー: {result.errors}"
                        f"{err_note}\n\n"
                        f"出力先:\n{works}"
                    )
                    messagebox.showinfo("Lumina Review", msg)
                else:
                    msg = (
                        f"Lumina Review は完了しませんでした（{status}）。\n\n"
                        f"新規: {result.processed}\n"
                        f"エラー: {result.errors}"
                        f"{err_note}\n\n"
                        f"出力先:\n{works}"
                    )
                    messagebox.showinfo("Lumina Review", msg)

            self._ui(_done)
        except Exception as e:
            err_msg = str(e)
            self.log(f"Lumina Review エラー: {err_msg}")
            self._ui(lambda msg=err_msg: messagebox.showerror("エラー", msg))
        finally:
            self._ui(self.reset_ui)

    def start_screening_card_thread(self) -> None:
        if self.is_running:
            messagebox.showwarning("実行中", "別の処理が終わるまでお待ちください。")
            return
        target = Path(self.dir_var.get().strip())
        if not target.is_dir():
            messagebox.showerror("エラー", "先に対象フォルダを選んでください。")
            return
        unit = unit_from_dir(target)
        if unit is None:
            messagebox.showerror(
                "フォルダ名エラー",
                "月またはイベントフォルダを選んでください。\n"
                f"現在: {target.name}",
            )
            return
        if not self._ensure_openai_ready():
            return

        force = bool(self.card_force_var.get())
        theme = normalize_card_theme(self.config.get("card_theme", DEFAULT_CARD_THEME))
        if not messagebox.askyesno(
            "カード生成",
            f"対象フォルダ:\n{target}\n\n"
            "Rating 3 または 4 の JPEG にカード（Phase1）を付け、\n"
            "説明欄へ TITLE / SUMMARY / SCORES / CRITIQUE_SUMMARY を書き込みます。\n"
            f"処理済み上書き: {'する' if force else 'しない'}\n"
            f"カード背景: {theme}\n\n"
            "開始しますか？",
        ):
            return

        self.is_running = True
        _set_action_button_enabled(self.btn_start, False)
        _set_action_button_enabled(self.btn_cancel, True)
        self.btn_browse.config(state=tk.DISABLED)
        self.btn_screening_card.config(state=tk.DISABLED)
        _set_action_button_enabled(self.btn_trace, False)
        self.btn_browse_works.config(state=tk.DISABLED)
        self.dir_entry.config(state=tk.DISABLED)
        self.works_entry.config(state=tk.DISABLED)
        self.progress.start(12)
        self._set_status("カード生成中…")
        threading.Thread(
            target=self._run_screening_cards,
            args=(target, force, theme),
            daemon=True,
        ).start()

    def _run_screening_cards(self, target: Path, force: bool, theme: str) -> None:
        try:
            def on_progress(event: str, message: str) -> None:
                self.log(f"[card/{event}] {message}")
                self._set_status(message)

            self.card_runner = ScreeningCardRunner(
                ScreeningCardConfig(force_overwrite=force, card_theme=theme),
                on_progress=on_progress,
            )
            self.log("=" * 48)
            self.log(f"スクリーニング カード生成開始: {target}")
            result = self.card_runner.run_on_dir(target)
            self.log(
                f"status={result.status} processed={result.processed} "
                f"skipped={result.skipped} errors={result.errors}"
            )
            self.log("=" * 48)

            def _done() -> None:
                self.status_label.config(text=f"カード生成 {result.status}")
                messagebox.showinfo(
                    "カード生成",
                    f"ステータス: {result.status}\n"
                    f"新規: {result.processed}\n"
                    f"スキップ: {result.skipped}\n"
                    f"エラー: {result.errors}\n\n"
                    f"カード出力: {target.name}Luminaカード/\n"
                    "JPEG 説明欄にも TITLE 等が書き込まれます（DxO で一覧可）。",
                )

            self._ui(_done)
        except Exception as e:
            err_msg = str(e)
            self.log(f"カード生成エラー: {err_msg}")
            self._ui(lambda msg=err_msg: messagebox.showerror("エラー", msg))
        finally:
            self._ui(self.reset_ui)

    def open_sessions_folder(self) -> None:
        """監査フォルダを開く。未作成なら mkdir せず案内のみ（L2）。"""
        from delta_log import sessions_dir

        target = Path(self.dir_var.get().strip())
        if not target.is_dir():
            messagebox.showerror("エラー", "先に対象フォルダを選んでください。")
            return
        sess = sessions_dir(target)
        if not sess.is_dir():
            messagebox.showinfo(
                "監査フォルダなし",
                "まだスクリーニングセッションがありません。\n"
                "先にスクリーニングを実行すると、次の場所に作られます。\n\n"
                f"{sess}",
            )
            return
        try:
            open_in_file_manager(sess)
        except Exception as e:
            messagebox.showerror("エラー", f"フォルダを開けませんでした:\n{e}")


def main() -> None:
    root = tk.Tk()
    ShortlistApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
