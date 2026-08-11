"""Lumina Notes 短絡バッチ GUI（必須実行口）.

講評バッチ ``app_gui.py`` とは別ウィンドウ・別導線。
- 月／イベントフォルダを選んで M1→M2→M3 を実行
- 進捗・中断・監査ログ自動保存
- DxO（H3）修正後の記録ボタン（pre_h3 / post_h3 / h3_delta）
- Works（確定フォルダ）を指定して対話痕跡（カード／ノート／ログ）を生成（T8・コピーなし）
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from card_theme import DEFAULT_CARD_THEME, normalize_card_theme
from delta_log import (
    latest_session_path,
    list_session_paths,
    load_session,
    record_post_h3,
    summarize_session,
)
from desktop_config import load_config as load_shared_config, save_config_merge
from library_unit import list_source_jpegs, resolve_unit, unit_from_dir
from shortlist_pipeline import PipelineConfig, PipelineProgress, ShortlistPipeline
from trace_from_works import TraceConfig, TraceProgress, WorksTraceRunner, list_works_trace_targets


class ShortlistApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Lumina Notes 短絡バッチ")
        self.root.geometry("720x860")
        self.root.minsize(640, 720)
        try:
            self.root.tk.call("tk", "scaling", 2.0)
        except Exception:
            pass

        self.is_running = False
        self.pipeline: ShortlistPipeline | None = None
        self.trace_runner: WorksTraceRunner | None = None
        self.last_session_path: Path | None = None
        self.config = self.load_config()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
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
                "1. 月（YYYYMM）またはイベント（YYYYMMDD_名前）フォルダを選ぶ\n"
                "2. 短絡バッチ（M1→M2→M3）を実行 → JPEG に Rating / 説明が付く\n"
                "3. DxO で確認・修正したあと「修正後を記録」で前後比較を残す\n"
                "4. DxO から Works へ書き出したあと、下の「痕跡生成」でカード／ノートを付ける"
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
        self.btn_start = tk.Button(
            actions,
            text="短絡バッチを開始",
            font=("Helvetica", 12, "bold"),
            bg="#007aff",
            fg="white",
            activebackground="#005bb5",
            activeforeground="white",
            pady=8,
            command=self.start_batch_thread,
        )
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.btn_cancel = tk.Button(
            actions,
            text="中止",
            font=("Helvetica", 12),
            bg="#ff3b30",
            fg="white",
            activebackground="#c72c23",
            activeforeground="white",
            state=tk.DISABLED,
            pady=8,
            command=self.request_cancel,
        )
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

        works = ttk.LabelFrame(main, text=" Works 痕跡生成（コピーなし） ", padding="8")
        works.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(
            works,
            text=(
                "DxO 等が書き出した確定フォルダを指定します。"
                "同一コマは {stem}_dev.jpg を優先し、なければ撮って出し .jpg を使います。"
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
        self.btn_trace = tk.Button(
            works_btns,
            text="痕跡生成を開始",
            font=("Helvetica", 11, "bold"),
            bg="#34c759",
            fg="white",
            activebackground="#248a3d",
            activeforeground="white",
            pady=6,
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

    def browse_works_folder(self) -> None:
        current = self.works_dir_var.get()
        initial = current if Path(current).exists() else str(Path.home())
        selected = filedialog.askdirectory(
            initialdir=initial, title="Works（確定 JPEG）フォルダを選択"
        )
        if selected:
            self.works_dir_var.set(selected)
            self.save_config(works_dir=selected)
            try:
                n = len(list_works_trace_targets(Path(selected)))
                self.log(f"Works フォルダ: {selected}（痕跡対象 {n} 枚）")
            except Exception as e:
                self.log(f"Works フォルダ: {selected}（列挙注意: {e}）")

    def log(self, message: str) -> None:
        def _append() -> None:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            n = int(self.log_text.index("end-1c").split(".")[0])
            if n > 1000:
                self.log_text.delete("1.0", f"{n - 1000}.0")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

        self.root.after(0, _append)

    def _set_status(self, text: str) -> None:
        self.root.after(0, lambda: self.status_label.config(text=text))

    def _refresh_session_label(self, unit_dir: Path) -> None:
        latest = latest_session_path(unit_dir)
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
            self.btn_cancel.config(state=tk.DISABLED)

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
                "月（YYYYMM）またはイベント（YYYYMMDD_名前）のフォルダを選んでください。\n"
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

        stages = []
        if self.var_m1.get():
            stages.append("M1")
        if self.var_m2.get():
            stages.append("M2")
        if self.var_m3.get():
            stages.append("M3")
        dry = self.var_dry.get()
        if not messagebox.askyesno(
            "実行確認",
            f"対象: {unit.kind} / {unit.unit_id}\n"
            f"JPEG: {len(jpegs)} 枚\n"
            f"段: {', '.join(stages)}\n"
            f"書き込み: {'しない（ドライラン）' if dry else 'する'}\n\n"
            "短絡バッチを開始しますか？",
        ):
            return

        self.save_config(str(target))
        self.is_running = True
        self.btn_start.config(state=tk.DISABLED, bg="#8e8e93")
        self.btn_cancel.config(state=tk.NORMAL)
        self.btn_browse.config(state=tk.DISABLED)
        self.btn_h3.config(state=tk.DISABLED)
        self.btn_trace.config(state=tk.DISABLED, bg="#8e8e93")
        self.btn_browse_works.config(state=tk.DISABLED)
        self.dir_entry.config(state=tk.DISABLED)
        self.works_entry.config(state=tk.DISABLED)
        self.progress.start(12)
        threading.Thread(target=self._run_batch, args=(target,), daemon=True).start()

    def _run_batch(self, target: Path) -> None:
        try:
            def on_progress(p: PipelineProgress) -> None:
                self.log(f"[{p.stage}] {p.message}")
                self._set_status(p.message)

            self.pipeline = ShortlistPipeline(
                PipelineConfig(
                    write=not self.var_dry.get(),
                    run_m1=self.var_m1.get(),
                    run_m2=self.var_m2.get(),
                    run_m3=self.var_m3.get(),
                    persist_session=True,
                ),
                on_progress=on_progress,
            )
            self.log("=" * 48)
            self.log(f"短絡バッチ開始: {target}")
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
                msg = (
                    f"短絡バッチが {result.status} しました。\n\n"
                    f"JPEG: {result.jpeg_count} 枚\n"
                    f"セッション: {result.session_path.name if result.session_path else 'なし'}\n\n"
                    "次: DxO で Rating を確認・修正し、\n"
                    "「DxO修正後を記録」を押してください。"
                )
                messagebox.showinfo("完了", msg)

            self.root.after(0, _done)
        except Exception as e:
            err_msg = str(e)
            self.log(f"エラー: {err_msg}")
            self.root.after(0, lambda msg=err_msg: messagebox.showerror("エラー", msg))
        finally:
            self.root.after(0, self.reset_ui)

    def reset_ui(self) -> None:
        self.is_running = False
        self.pipeline = None
        self.trace_runner = None
        self.progress.stop()
        self.btn_start.config(state=tk.NORMAL, bg="#007aff")
        self.btn_cancel.config(state=tk.DISABLED)
        self.btn_browse.config(state=tk.NORMAL)
        self.btn_h3.config(state=tk.NORMAL)
        self.btn_trace.config(state=tk.NORMAL, bg="#34c759")
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
        try:
            targets = list_works_trace_targets(works)
        except Exception as e:
            messagebox.showerror("エラー", str(e))
            return
        if not targets:
            messagebox.showwarning(
                "対象なし",
                "痕跡対象の JPEG がありません。\n"
                "{stem}_dev.jpg または撮って出し .jpg を置いてください。",
            )
            return

        mode = self.trace_mode_var.get()
        theme = normalize_card_theme(self.trace_theme_var.get())
        force = self.trace_force_var.get()
        if not messagebox.askyesno(
            "痕跡生成の確認",
            f"Works: {works}\n"
            f"対象: {len(targets)} 枚（_dev 優先）\n"
            f"モード: {mode} / テーマ: {theme}\n"
            f"上書き: {'する' if force else 'しない'}\n\n"
            "ファイルのコピーは行いません。\n痕跡生成を開始しますか？",
        ):
            return

        self.config["card_theme"] = theme
        self.config["force_overwrite"] = force
        self.save_config(works_dir=str(works))
        self.is_running = True
        self.btn_start.config(state=tk.DISABLED, bg="#8e8e93")
        self.btn_cancel.config(state=tk.NORMAL)
        self.btn_browse.config(state=tk.DISABLED)
        self.btn_h3.config(state=tk.DISABLED)
        self.btn_trace.config(state=tk.DISABLED, bg="#8e8e93")
        self.btn_browse_works.config(state=tk.DISABLED)
        self.dir_entry.config(state=tk.DISABLED)
        self.works_entry.config(state=tk.DISABLED)
        self.progress.start(12)
        threading.Thread(target=self._run_trace, args=(works,), daemon=True).start()

    def _run_trace(self, works: Path) -> None:
        try:
            def on_progress(p: TraceProgress) -> None:
                self.log(f"[trace/{p.stage}] {p.message}")
                self._set_status(p.message)

            self.trace_runner = WorksTraceRunner(
                TraceConfig(
                    mode=self.trace_mode_var.get(),
                    force_overwrite=self.trace_force_var.get(),
                    card_theme=self.trace_theme_var.get(),
                    pixel_priority=True,
                ),
                on_progress=on_progress,
            )
            self.log("=" * 48)
            self.log(f"Works 痕跡生成開始: {works}")
            result = self.trace_runner.run(works)
            self.log(
                f"status={result.status} processed={result.processed} "
                f"skipped={result.skipped} errors={result.errors}"
            )
            self.log("=" * 48)

            def _done() -> None:
                self.status_label.config(text=f"痕跡{result.status}")
                messagebox.showinfo(
                    "痕跡生成完了",
                    f"痕跡生成が {result.status} しました。\n\n"
                    f"対象: {result.targets_found} 枚\n"
                    f"新規: {result.processed}\n"
                    f"スキップ: {result.skipped}\n"
                    f"エラー: {result.errors}\n\n"
                    f"出力先:\n{works}",
                )

            self.root.after(0, _done)
        except Exception as e:
            err_msg = str(e)
            self.log(f"痕跡エラー: {err_msg}")
            self.root.after(0, lambda msg=err_msg: messagebox.showerror("エラー", msg))
        finally:
            self.root.after(0, self.reset_ui)

    def record_h3_after(self) -> None:
        target = Path(self.dir_var.get().strip())
        if not target.is_dir():
            messagebox.showerror("エラー", "先に対象フォルダを選んでください。")
            return
        session = self.last_session_path or latest_session_path(target)
        if session is None or not session.is_file():
            paths = list_session_paths(target)
            if not paths:
                messagebox.showwarning(
                    "セッションなし",
                    "このフォルダに短絡セッションがありません。\n先に短絡バッチを実行してください。",
                )
                return
            session = paths[-1]

        if not messagebox.askyesno(
            "DxO修正後の記録",
            f"セッション:\n{session.name}\n\n"
            "いまの JPEG（DxO で直した内容）を読み取り、\n"
            "修正前（バッチ直後）との差分を記録します。\n続行しますか？",
        ):
            return

        try:
            unit = resolve_unit(target)
            doc = record_post_h3(session, unit=unit)
            delta = doc.get("h3_delta") or {}
            self.last_session_path = session
            self._refresh_session_label(target)
            self.log(
                f"DxO修正後を記録: changed={delta.get('changed_count')} "
                f"unchanged={delta.get('unchanged_count')} "
                f"transitions={delta.get('transitions')}"
            )
            messagebox.showinfo(
                "記録完了",
                "DxO 修正後を記録しました。\n\n"
                f"変化した枚数: {delta.get('changed_count', 0)}\n"
                f"変化なし: {delta.get('unchanged_count', 0)}\n"
                f"遷移: {delta.get('transitions')}\n\n"
                f"ファイル:\n{session}",
            )
        except Exception as e:
            messagebox.showerror("エラー", str(e))
            self.log(f"H3記録エラー: {e}")

    def open_sessions_folder(self) -> None:
        target = Path(self.dir_var.get().strip())
        sess = target / "_lumina" / "sessions"
        sess.mkdir(parents=True, exist_ok=True)
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
