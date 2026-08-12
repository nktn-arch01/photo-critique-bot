"""Lumina Notes Console（スクリーニング + Lumina Review の統合 GUI）.

講評バッチ ``app_gui.py`` とは別ウィンドウ・別導線。
- 月／イベントフォルダを選んで M1→M2→M3 を実行
- 進捗・中断・監査ログ自動保存
- DxO（H3）修正後の記録ボタン（pre_h3 / post_h3 / h3_delta）
- Works（確定フォルダ）を指定して Lumina Review（カード／ノート／ログ）（T8・コピーなし）
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from card_theme import DEFAULT_CARD_THEME, normalize_card_theme
from delta_log import (
    DryRunSessionError,
    load_session,
    record_post_h3,
    summarize_session,
)
from desktop_config import load_config as load_shared_config, save_config_merge
from desktop_ui import schedule_on_ui
from library_unit import (
    is_works_month_folder_name,
    list_event_units,
    list_source_jpegs,
    resolve_session_for_unit,
    resolve_unit,
    unit_from_dir,
)
from screening_pipeline import PipelineConfig, PipelineProgress, ScreeningPipeline
from lumina_review import (
    ReviewConfig,
    ReviewProgress,
    LuminaReviewRunner,
    list_works_review_targets,
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
        self.root.geometry("720x860")
        self.root.minsize(640, 720)
        try:
            self.root.tk.call("tk", "scaling", 2.0)
        except Exception:
            pass

        self.is_running = False
        self.pipeline: ScreeningPipeline | None = None
        self.trace_runner: LuminaReviewRunner | None = None
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
            }
        )
        cfg["force_overwrite"] = bool(cfg.get("force_overwrite", False))
        cfg["card_theme"] = normalize_card_theme(cfg.get("card_theme", DEFAULT_CARD_THEME))
        return cfg

    def save_config(self, target_dir: str | None = None, *, works_dir: str | None = None) -> None:
        try:
            updates: dict = {}
            if target_dir:
                updates["shortlist_last_dir"] = target_dir
            if works_dir:
                updates["works_last_dir"] = works_dir
            if not updates:
                return
            self.config = save_config_merge(updates, current=self.config)
        except Exception as e:
            self.log(f"設定の保存に失敗: {e}")

    def setup_ui(self) -> None:
        main = ttk.Frame(self.root, padding="15")
        main.pack(fill=tk.BOTH, expand=True)

        info = ttk.LabelFrame(main, text=" この画面でできること ", padding="8")
        info.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            info,
            text=(
                "1. オリジナルの月（YYYYMM または OM202606 等）／イベント（…DD_名前）を選ぶ\n"
                "2. スクリーニング（M1→M2→M3）を実行 → JPEG に Rating / 説明が付く\n"
                "3. DxO で確認・修正したあと「修正後を記録」で前後比較を残す\n"
                "4. Works の月フォルダ（YYYYMM のみ）を選び、Lumina Review（カード／ノート）を付ける\n\n"
                "Rating の意味（DxO の「出来の星」とは別）:\n"
                "  0=除外 / 1=M1合格 / 2=M2合格 / 3=余白 / 4=上位\n"
                "月フォルダを選んだとき、イベント配下の JPEG は対象外です（別途イベントを指定）。"
            ),
            justify=tk.LEFT,
        ).pack(anchor=tk.W)

        folder = ttk.LabelFrame(main, text=" 対象フォルダ ", padding="10")
        folder.pack(fill=tk.X, pady=(0, 10))
        self.dir_var = tk.StringVar(value=self.config.get("shortlist_last_dir", ""))
        self.dir_entry = ttk.Entry(folder, textvariable=self.dir_var, font=("Helvetica", 11))
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.btn_browse = ttk.Button(folder, text=" 参照... ", command=self.browse_folder)
        self.btn_browse.pack(side=tk.RIGHT)

        opts = ttk.LabelFrame(main, text=" 実行オプション ", padding="8")
        opts.pack(fill=tk.X, pady=(0, 10))
        stage_row = ttk.Frame(opts)
        stage_row.pack(fill=tk.X)
        self.var_m1 = tk.BooleanVar(value=True)
        self.var_m2 = tk.BooleanVar(value=True)
        self.var_m3 = tk.BooleanVar(value=True)
        self.var_dry = tk.BooleanVar(value=False)
        ttk.Checkbutton(stage_row, text="M1 機械", variable=self.var_m1).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(stage_row, text="M2 アンテナ", variable=self.var_m2).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(stage_row, text="M3 多様性", variable=self.var_m3).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(opts, text="ドライラン（JPEGへ書かない／監査は残す）", variable=self.var_dry).pack(
            anchor=tk.W, pady=(6, 0)
        )

        prog = ttk.Frame(main)
        prog.pack(fill=tk.X, pady=(0, 8))
        self.status_label = ttk.Label(prog, text="準備完了", font=("Helvetica", 10))
        self.status_label.pack(anchor=tk.W, pady=(0, 5))
        self.progress = ttk.Progressbar(prog, mode="indeterminate")
        self.progress.pack(fill=tk.X)

        log_frame = ttk.LabelFrame(main, text=" 実行ログ ", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.log_text = tk.Text(
            log_frame, wrap=tk.WORD, font=("Menlo", 10), state=tk.DISABLED, bg="#1e1e1e", fg="#d4d4d4"
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scroll.set)

        actions = ttk.Frame(main)
        actions.pack(fill=tk.X, pady=(0, 8))
        self.btn_start = _action_button(
            actions,
            text="スクリーニングを開始",
            command=self.start_batch_thread,
        )
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.btn_cancel = _action_button(
            actions,
            text="中止",
            command=self.request_cancel,
        )
        self.btn_cancel.state(["disabled"])
        self.btn_cancel.pack(side=tk.RIGHT)

        h3 = ttk.LabelFrame(main, text=" DxO 修正後の記録（判定改善用） ", padding="8")
        h3.pack(fill=tk.X)
        ttk.Label(
            h3,
            text="バッチ後に DxO で Rating／説明を直したら、ここを押して「修正前→修正後」を同じセッションに残します。",
            wraplength=640,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 6))
        h3_btns = ttk.Frame(h3)
        h3_btns.pack(fill=tk.X)
        self.btn_h3 = ttk.Button(h3_btns, text="DxO修正後を記録", command=self.record_h3_after)
        self.btn_h3.pack(side=tk.LEFT)
        self.btn_open_session = ttk.Button(h3_btns, text="監査フォルダを開く", command=self.open_sessions_folder)
        self.btn_open_session.pack(side=tk.LEFT, padx=(8, 0))
        self.session_label = ttk.Label(h3, text="セッション: （まだありません）")
        self.session_label.pack(anchor=tk.W, pady=(6, 0))

        works = ttk.LabelFrame(main, text=" Works Lumina Review（コピーなし） ", padding="8")
        works.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(
            works,
            text=(
                "Works は月フォルダ YYYYMM のみ（例: ~/2026/202606）。"
                "イベント用サブフォルダは使いません。"
                "同一コマは {stem}_dev.jpg を優先し、なければ撮って出し .jpg。"
                "ファイルのコピーはしません。"
            ),
            wraplength=640,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 6))
        works_row = ttk.Frame(works)
        works_row.pack(fill=tk.X)
        self.works_dir_var = tk.StringVar(value=self.config.get("works_last_dir", ""))
        self.works_entry = ttk.Entry(works_row, textvariable=self.works_dir_var, font=("Helvetica", 11))
        self.works_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.btn_browse_works = ttk.Button(works_row, text=" 参照... ", command=self.browse_works_folder)
        self.btn_browse_works.pack(side=tk.RIGHT)

        works_opts = ttk.Frame(works)
        works_opts.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(works_opts, text="モード:").pack(side=tk.LEFT)
        self.trace_mode_var = tk.StringVar(value="full")
        ttk.Radiobutton(works_opts, text="詳細 (full)", variable=self.trace_mode_var, value="full").pack(
            side=tk.LEFT, padx=(4, 8)
        )
        ttk.Radiobutton(works_opts, text="簡易 (compact)", variable=self.trace_mode_var, value="compact").pack(
            side=tk.LEFT, padx=(0, 12)
        )
        self.trace_force_var = tk.BooleanVar(value=bool(self.config.get("force_overwrite", False)))
        ttk.Checkbutton(works_opts, text="処理済みも上書き", variable=self.trace_force_var).pack(side=tk.LEFT)

        theme_row = ttk.Frame(works)
        theme_row.pack(fill=tk.X, pady=(4, 0))
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

        works_btns = ttk.Frame(works)
        works_btns.pack(fill=tk.X, pady=(8, 0))
        self.btn_trace = _action_button(
            works_btns,
            text="Lumina Review を開始",
            small=True,
            command=self.start_trace_thread,
        )
        self.btn_trace.pack(side=tk.LEFT, fill=tk.X, expand=True)

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
                if unit is not None and unit.is_month:
                    events = list_event_units(unit)
                    if events:
                        self.log(
                            f"注意: 月フォルダ直下のみが対象。イベント配下 {len(events)} 件は含めません。"
                        )
            except Exception:
                pass

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
                n = len(list_works_review_targets(works_path))
                hint = works_empty_targets_hint(works_path) if n == 0 else ""
                self.log(f"Works フォルダ: {selected}（Lumina Review 対象 {n} 枚）{hint.strip()}")
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
            self.log("中止リクエストを受け付けました…")
            self.btn_cancel.state(["disabled"])

    def on_closing(self) -> None:
        if self.is_running:
            if messagebox.askyesno("確認", "処理実行中です。終了しますか？"):
                if self.pipeline:
                    self.pipeline.request_cancel()
                if self.trace_runner:
                    self.trace_runner.request_cancel()
                self.root.destroy()
        else:
            self.root.destroy()

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

        jpegs = list_source_jpegs(unit)
        if not jpegs:
            messagebox.showwarning("警告", f"直下に JPEG がありません:\n{target}")
            return

        event_note = ""
        if unit.is_month:
            try:
                events = list_event_units(unit)
            except Exception:
                events = []
            if events:
                event_note = (
                    f"\n注意: イベント配下 {len(events)} 件は今回の対象外です"
                    "（イベントフォルダを別に選んでください）。"
                )

        # M3: 開始時点の UI 値をスナップショット（ワーカーは Tk 変数を読まない）
        opts = {
            "run_m1": bool(self.var_m1.get()),
            "run_m2": bool(self.var_m2.get()),
            "run_m3": bool(self.var_m3.get()),
            "dry": bool(self.var_dry.get()),
        }
        stages = []
        if opts["run_m1"]:
            stages.append("M1")
        if opts["run_m2"]:
            stages.append("M2")
        if opts["run_m3"]:
            stages.append("M3")
        if not messagebox.askyesno(
            "実行確認",
            f"対象: {unit.kind} / {unit.unit_id}"
            + (f"（機種 {unit.camera_code}）" if unit.camera_code else "")
            + f"\nJPEG（直下）: {len(jpegs)} 枚"
            + event_note
            + f"\n段: {', '.join(stages)}\n"
            f"書き込み: {'しない（ドライラン）' if opts['dry'] else 'する'}\n\n"
            "スクリーニングを開始しますか？",
        ):
            return

        self.save_config(str(target))
        self.is_running = True
        _set_action_button_enabled(self.btn_start, False)
        _set_action_button_enabled(self.btn_cancel, True)
        self.btn_browse.config(state=tk.DISABLED)
        self.btn_h3.config(state=tk.DISABLED)
        _set_action_button_enabled(self.btn_trace, False)
        self.btn_browse_works.config(state=tk.DISABLED)
        self.dir_entry.config(state=tk.DISABLED)
        self.works_entry.config(state=tk.DISABLED)
        self.progress.start(12)
        threading.Thread(target=self._run_batch, args=(target, opts), daemon=True).start()

    def _run_batch(self, target: Path, opts: dict) -> None:
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
            self.log(f"スクリーニング開始: {target}")
            result = self.pipeline.run_on_dir(target)
            self.last_session_path = result.session_path
            self.log(f"status: {result.status}")
            self.log(f"counts_hint: {result.counts_by_rating_hint()}")
            if result.session_path:
                self.log(f"監査ログ（DxO修正前を含む）: {result.session_path}")
                try:
                    summary = summarize_session(load_session(result.session_path))
                    self.log(
                        f"pre_h3 counts: {summary.get('pre_h3_counts')} "
                        f"(この時点が DxO 修正前の記録です)"
                    )
                except Exception as e:
                    self.log(f"サマリ読取注意: {e}")
            self.log("=" * 48)

            def _done() -> None:
                self._refresh_session_label(target)
                self.status_label.config(text=f"処理{result.status}")
                status = result.status or "unknown"
                session_name = result.session_path.name if result.session_path else "なし"
                if status == "completed":
                    if opts["dry"]:
                        next_steps = (
                            "今回はドライランのため JPEG には書いていません。\n"
                            "「DxO修正後を記録」は使わず、書き込みありで再実行してください。"
                        )
                    else:
                        next_steps = (
                            "次: DxO で Rating を確認・修正し、\n"
                            "「DxO修正後を記録」を押してください。"
                        )
                    title = "完了"
                    msg = (
                        f"スクリーニングが完了しました。\n\n"
                        f"JPEG: {result.jpeg_count} 枚\n"
                        f"セッション: {session_name}\n\n"
                        f"{next_steps}"
                    )
                elif status == "cancelled":
                    title = "中止"
                    msg = (
                        f"スクリーニングを中止しました。\n\n"
                        f"JPEG: {result.jpeg_count} 枚\n"
                        f"セッション: {session_name}"
                    )
                else:
                    title = "未完了"
                    msg = (
                        f"スクリーニングは完了しませんでした（{status}）。\n\n"
                        f"JPEG: {result.jpeg_count} 枚\n"
                        f"セッション: {session_name}\n"
                        f"エラー: {result.error or '（詳細はログを確認）'}"
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
        self.progress.stop()
        _set_action_button_enabled(self.btn_start, True)
        _set_action_button_enabled(self.btn_cancel, False)
        self.btn_browse.config(state=tk.NORMAL)
        self.btn_h3.config(state=tk.NORMAL)
        _set_action_button_enabled(self.btn_trace, True)
        self.btn_browse_works.config(state=tk.NORMAL)
        self.dir_entry.config(state=tk.NORMAL)
        self.works_entry.config(state=tk.NORMAL)

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
            targets = list_works_review_targets(works)
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

        opts = {
            "mode": self.trace_mode_var.get(),
            "theme": normalize_card_theme(self.trace_theme_var.get()),
            "force": bool(self.trace_force_var.get()),
        }
        if not messagebox.askyesno(
            "Lumina Review の確認",
            f"Works: {works}\n"
            f"対象: {len(targets)} 枚（_dev 優先）\n"
            f"モード: {opts['mode']} / テーマ: {opts['theme']}\n"
            f"上書き: {'する' if opts['force'] else 'しない'}\n\n"
            "ファイルのコピーは行いません。\nLumina Review を開始しますか？",
        ):
            return

        self.config["card_theme"] = opts["theme"]
        self.config["force_overwrite"] = opts["force"]
        self.save_config(works_dir=str(works))
        self.is_running = True
        _set_action_button_enabled(self.btn_start, False)
        _set_action_button_enabled(self.btn_cancel, True)
        self.btn_browse.config(state=tk.DISABLED)
        self.btn_h3.config(state=tk.DISABLED)
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
                messagebox.showinfo(
                    "Lumina Review 完了",
                    f"Lumina Review が {result.status} しました。\n\n"
                    f"対象: {result.targets_found} 枚\n"
                    f"新規: {result.processed}\n"
                    f"スキップ: {result.skipped}\n"
                    f"エラー: {result.errors}\n\n"
                    f"出力先:\n{works}",
                )

            self._ui(_done)
        except Exception as e:
            err_msg = str(e)
            self.log(f"Lumina Review エラー: {err_msg}")
            self._ui(lambda msg=err_msg: messagebox.showerror("エラー", msg))
        finally:
            self._ui(self.reset_ui)

    def record_h3_after(self) -> None:
        if self.is_running:
            messagebox.showwarning("実行中", "別の処理が終わるまでお待ちください。")
            return
        target = Path(self.dir_var.get().strip())
        if not target.is_dir():
            messagebox.showerror("エラー", "先に対象フォルダを選んでください。")
            return
        # M2: 手編集でずれても、必ず当該フォルダ配下のセッションだけを使う
        session = resolve_session_for_unit(target, self.last_session_path)
        if session is None:
            messagebox.showwarning(
                "セッションなし",
                "このフォルダにスクリーニングセッションがありません。\n先にスクリーニングを実行してください。",
            )
            return
        try:
            sess_doc = load_session(session)
        except Exception as e:
            messagebox.showerror("エラー", f"セッションを読めませんでした:\n{e}")
            return
        if sess_doc.get("write_meta") is False:
            messagebox.showwarning(
                "ドライランのセッション",
                "このセッションはドライラン（JPEGへ書いていない）です。\n"
                "偽の差分を避けるため、「DxO修正後を記録」は使えません。\n\n"
                "ドライランを外してスクリーニングを再実行してから記録してください。",
            )
            return

        if not messagebox.askyesno(
            "DxO修正後の記録",
            f"フォルダ:\n{target}\n\n"
            f"セッション:\n{session.name}\n\n"
            "いまの JPEG（DxO で直した内容）を読み取り、\n"
            "修正前（バッチ直後）との差分を記録します。\n"
            "（ファイルのコピーはしません）\n続行しますか？",
        ):
            return

        self.is_running = True
        _set_action_button_enabled(self.btn_start, False)
        _set_action_button_enabled(self.btn_cancel, False)
        self.btn_browse.config(state=tk.DISABLED)
        self.btn_h3.config(state=tk.DISABLED)
        _set_action_button_enabled(self.btn_trace, False)
        self.btn_browse_works.config(state=tk.DISABLED)
        self.dir_entry.config(state=tk.DISABLED)
        self.works_entry.config(state=tk.DISABLED)
        self.progress.start(12)
        self._set_status("DxO修正後を記録中…")
        threading.Thread(
            target=self._run_record_h3, args=(target, session), daemon=True
        ).start()

    def _run_record_h3(self, target: Path, session: Path) -> None:
        try:
            unit = resolve_unit(target)
            self.log(f"DxO修正後を記録開始: {session.name}")
            doc = record_post_h3(session, unit=unit)
            delta = doc.get("h3_delta") or {}
            self.last_session_path = session
            self.log(
                f"DxO修正後を記録: changed={delta.get('changed_count')} "
                f"unchanged={delta.get('unchanged_count')} "
                f"transitions={delta.get('transitions')}"
            )

            def _done() -> None:
                self._refresh_session_label(target)
                self.status_label.config(text="DxO修正後を記録済み")
                messagebox.showinfo(
                    "記録完了",
                    "DxO 修正後を記録しました。\n\n"
                    f"変化した枚数: {delta.get('changed_count', 0)}\n"
                    f"変化なし: {delta.get('unchanged_count', 0)}\n"
                    f"遷移: {delta.get('transitions')}\n\n"
                    f"フォルダ:\n{target}\n"
                    f"ファイル:\n{session}",
                )

            self._ui(_done)
        except DryRunSessionError as e:
            err_msg = str(e)
            self.log(f"H3記録拒否: {err_msg}")
            self._ui(lambda msg=err_msg: messagebox.showwarning("ドライランのセッション", msg))
        except Exception as e:
            err_msg = str(e)
            self.log(f"H3記録エラー: {err_msg}")
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
            subprocess.run(["open", str(sess.resolve())], check=False)
        except Exception:
            try:
                subprocess.run(["xdg-open", str(sess.resolve())], check=False)
            except Exception as e:
                messagebox.showerror("エラー", f"フォルダを開けませんでした:\n{e}")


def main() -> None:
    root = tk.Tk()
    ShortlistApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
