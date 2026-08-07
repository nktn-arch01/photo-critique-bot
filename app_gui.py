import os
import sys
import json
import threading
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from log_manager import DesktopLogManager
from critique_engine import generate_critique, get_openai_client
from generate_critique_card import create_critique_card
from scanner import extract_file_metadata

CONFIG_FILE = Path.home() / ".photo_ai_config.json"


class PhotoAICritiqueApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Photo AI 写真講評バッチ処理システム")
        self.root.geometry("700x610")
        self.root.minsize(620, 500)

        try:
            self.root.tk.call('tk', 'scaling', 2.0)
        except Exception:
            pass

        self.is_running = False
        self.cancel_requested = False

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.config = self.load_config()
        self.setup_ui()

    def load_config(self) -> dict:
        default_dir = str(Path.home() / "Desktop")
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                return {
                    "last_dir": data.get("last_dir", default_dir),
                    "force_overwrite": data.get("force_overwrite", False)
                }
            except Exception:
                pass
        return {"last_dir": default_dir, "force_overwrite": False}

    def save_config(self, target_dir_str: str):
        try:
            self.config["last_dir"] = target_dir_str
            self.config["force_overwrite"] = self.force_overwrite_var.get()
            tmp_file = CONFIG_FILE.with_suffix(".tmp")
            tmp_file.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_file.replace(CONFIG_FILE)
        except Exception as e:
            self.log(f"⚠️ 設定の保存に失敗しました: {e}")

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ---------------------------------------------------------
        # AIモデル情報表示フレーム
        # ---------------------------------------------------------
        model_frame = ttk.LabelFrame(main_frame, text=" AIエンジン設定情報 (OpenAI API) ", padding="8")
        model_frame.pack(fill=tk.X, pady=(0, 10))

        self.lbl_active_model = ttk.Label(model_frame, text="• 使用モデル : gpt-4o-mini (従量後払い・制限なし)", font=("Helvetica", 10, "bold"))
        self.lbl_active_model.pack(anchor=tk.W)

        # ---------------------------------------------------------
        # フォルダ選択フレーム
        # ---------------------------------------------------------
        folder_frame = ttk.LabelFrame(main_frame, text=" 処理対象フォルダの確認・選択 ", padding="10")
        folder_frame.pack(fill=tk.X, pady=(0, 10))

        self.dir_path_var = tk.StringVar(value=self.config.get("last_dir", ""))
        self.dir_entry = ttk.Entry(folder_frame, textvariable=self.dir_path_var, font=("Helvetica", 11))
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        self.btn_browse = ttk.Button(folder_frame, text=" 参照... ", command=self.browse_folder)
        self.btn_browse.pack(side=tk.RIGHT)

        opt_frame = ttk.Frame(main_frame)
        opt_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.force_overwrite_var = tk.BooleanVar(value=self.config.get("force_overwrite", False))
        self.chk_overwrite = ttk.Checkbutton(
            opt_frame, 
            text=" 既存の分析結果を上書き再生成する (処理済みファイルをスキップしない)", 
            variable=self.force_overwrite_var
        )
        self.chk_overwrite.pack(anchor=tk.W)

        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.status_label = ttk.Label(progress_frame, text="準備完了 (実行ボタンを押してください)", font=("Helvetica", 10))
        self.status_label.pack(anchor=tk.W, pady=(0, 5))

        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress_bar.pack(fill=tk.X)

        log_frame = ttk.LabelFrame(main_frame, text=" 実行ログ ", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.log_text = tk.Text(log_frame, wrap=tk.WORD, font=("Menlo", 10), state=tk.DISABLED, bg="#1e1e1e", fg="#d4d4d4")
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X)

        self.btn_start = tk.Button(
            action_frame, 
            text="🚀 講評バッチ処理を開始", 
            font=("Helvetica", 12, "bold"),
            bg="#007aff", 
            fg="white", 
            activebackground="#005bb5", 
            activeforeground="white",
            pady=8,
            command=self.start_processing_thread
        )
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.btn_cancel = tk.Button(
            action_frame, 
            text="⏹ 中止", 
            font=("Helvetica", 12),
            bg="#ff3b30", 
            fg="white", 
            activebackground="#c72c23", 
            activeforeground="white",
            state=tk.DISABLED,
            pady=8,
            command=self.request_cancel
        )
        self.btn_cancel.pack(side=tk.RIGHT, padx=(5, 0))

    def browse_folder(self):
        current_dir = self.dir_path_var.get()
        initial = current_dir if Path(current_dir).exists() else str(Path.home())
        selected = filedialog.askdirectory(initialdir=initial, title="処理対象の写真フォルダを選択してください")
        if selected:
            self.dir_path_var.set(selected)
            self.save_config(selected)
            self.log(f"📁 処理対象フォルダを変更しました: {selected}")

    def log(self, message: str):
        def _append():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, message + "\n")
            
            num_lines = int(self.log_text.index('end-1c').split('.')[0])
            if num_lines > 1000:
                self.log_text.delete('1.0', f'{num_lines - 1000}.0')
                
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.root.after(0, _append)

    def request_cancel(self):
        if self.is_running:
            self.cancel_requested = True
            self.log("⚠️ 中止リクエストを受け付けました。現在の写真処理が完了次第終了します...")
            self.btn_cancel.config(state=tk.DISABLED)

    def on_closing(self):
        if self.is_running:
            if messagebox.askyesno("確認", "バッチ処理が実行中です。途中で終了しますか？"):
                self.cancel_requested = True
                self.root.destroy()
        else:
            self.root.destroy()

    def start_processing_thread(self):
        if self.is_running:
            return

        target_dir = Path(self.dir_path_var.get().strip())

        if not target_dir.exists() or not target_dir.is_dir():
            messagebox.showerror("エラー", f"指定されたフォルダが存在しません:\n{target_dir}")
            return

        if not os.access(target_dir, os.W_OK):
            messagebox.showerror("アクセス権限エラー", f"選択されたフォルダへの書き込み権限がありません (SDカード等):\n{target_dir}")
            return

        try:
            get_openai_client()
        except Exception as e:
            messagebox.showerror("APIキーエラー", f"OpenAI APIキーの初期化に失敗しました:\n{e}")
            return

        image_files = [
            f for f in target_dir.iterdir() 
            if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in [".jpg", ".jpeg", ".png"]
        ]
        if not image_files:
            messagebox.showwarning("警告", f"対象フォルダ内に画像ファイルが見つかりません:\n{target_dir}")
            return

        mode_str = "【上書き再生成モード】" if self.force_overwrite_var.get() else "【通常モード (処理済みスキップ)】"
        if not messagebox.askyesno("実行確認", f"対象フォルダ: {target_dir.name}\n画像ファイル数: {len(image_files)} 件\n動作モード: {mode_str}\n\n処理を開始しますか？"):
            return

        self.save_config(str(target_dir))

        self.is_running = True
        self.cancel_requested = False
        self.btn_start.config(state=tk.DISABLED, bg="#8e8e93")
        self.btn_cancel.config(state=tk.NORMAL)
        self.btn_browse.config(state=tk.DISABLED)
        self.dir_entry.config(state=tk.DISABLED)
        self.chk_overwrite.config(state=tk.DISABLED)

        threading.Thread(target=self.run_batch, args=(target_dir, image_files), daemon=True).start()

    def run_batch(self, target_dir: Path, image_files: list):
        try:
            self.log("=" * 50)
            self.log(f"🚀 講評バッチ処理を開始します (gpt-4o-mini): {target_dir.name}")
            self.log("=" * 50)

            log_mgr = DesktopLogManager(target_dir)
            total = len(image_files)
            processed_count = 0
            skipped_count = 0
            error_count = 0
            force_overwrite = self.force_overwrite_var.get()

            for idx, img_path in enumerate(image_files, 1):
                if self.cancel_requested:
                    self.log("🛑 ユーザーによって処理が安全に中断されました。")
                    break

                file_name = img_path.name
                
                progress_pct = (idx / total) * 100
                self.root.after(0, lambda p=progress_pct, i=idx, t=total, fn=file_name: [
                    self.progress_bar.config(value=p),
                    self.status_label.config(text=f"処理中... ({i}/{t}): {fn}")
                ])

                if not force_overwrite and log_mgr.is_processed(file_name):
                    self.log(f"⏩ スキップ (処理済み): {file_name}")
                    skipped_count += 1
                    continue

                self.log(f"📸 [{idx}/{total}] 処理中: {file_name}")

                try:
                    self.log("   └─ EXIF / .dop メタデータ抽出中 (scanner.py)...")
                    exif_meta, dop_info, metadata_block = extract_file_metadata(img_path)

                    self.log("   └─ AI講評生成中 (OpenAI gpt-4o-mini)...")
                    critique_text = generate_critique(
                        img_path, 
                        metadata=exif_meta, 
                        dop_info=dop_info, 
                        mode="full"
                    )

                    self.log("   └─ 評価カード画像生成中...")
                    card_output_path = log_mgr.get_card_output_path(file_name)
                    create_critique_card(img_path, critique_text, card_output_path)

                    self.log("   └─ Markdownノート・ログ出力中...")
                    log_mgr.save_analysis_result(file_name, metadata_block, critique_text)

                    self.log(f"   ✅ 完了: {file_name}")
                    processed_count += 1

                except Exception as img_err:
                    self.log(f"   ❌ エラー発生 ({file_name}): {img_err}")
                    error_count += 1

            self.log("=" * 50)
            status_text_res = "中断" if self.cancel_requested else "完了"
            self.log(f"🎉 バッチ処理{status_text_res}! (新規処理: {processed_count} / スキップ: {skipped_count} / エラー: {error_count})")
            self.log("=" * 50)

            self.root.after(0, lambda p=processed_count, s=skipped_count, e=error_count, st=status_text_res: [
                self.status_label.config(text=f"処理{st} (新規: {p} 件 / スキップ: {s} 件 / エラー: {e} 件)"),
                self.show_completion_dialog(target_dir, p, s, e, st)
            ])

        finally:
            self.root.after(0, self.reset_ui)

    def reset_ui(self):
        self.is_running = False
        self.cancel_requested = False
        self.btn_start.config(state=tk.DISABLED if self.is_running else tk.NORMAL, bg="#007aff")
        self.btn_cancel.config(state=tk.DISABLED)
        self.btn_browse.config(state=tk.NORMAL)
        self.dir_entry.config(state=tk.NORMAL)
        self.chk_overwrite.config(state=tk.NORMAL)

    def show_completion_dialog(self, target_dir: Path, processed: int, skipped: int, errors: int, status_str: str):
        msg = f"写真分析バッチ処理が{status_str}しました。\n\n・新規処理完了: {processed} 件\n・スキップ(処理済み): {skipped} 件\n・エラー: {errors} 件\n\n出力フォルダーを開きますか？"
        if messagebox.askyesno(f"処理{status_str}", msg):
            try:
                subprocess.run(["open", str(target_dir.resolve())])
            except Exception as e:
                self.log(f"⚠️ フォルダオープンエラー: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = PhotoAICritiqueApp(root)
    root.mainloop()