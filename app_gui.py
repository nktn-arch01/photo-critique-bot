import sys
import os
import json
import re
import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from critique_engine import generate_critique
from generate_critique_card import create_critique_card
from log_manager import DesktopLogManager

CONFIG_FILE = Path.home() / ".photo_ai_config.json"


def get_exiftool_path() -> str:
    base_dir = Path(__file__).parent
    local_exiftool = base_dir / "tools" / "exiftool"
    if local_exiftool.exists():
        return str(local_exiftool)
    return "exiftool"


def extract_metadata_and_dop(image_path: Path) -> tuple[dict, dict, str]:
    exiftool_bin = get_exiftool_path()
    
    cmd = [
        exiftool_bin,
        "-j",
        "-DateTimeOriginal",
        "-CreateDate",
        "-ModifyDate",
        "-Model",
        "-LensModel",
        "-FNumber",
        "-ExposureTime",
        "-ISO",
        "-FocalLength",
        "-Headline",
        "-Caption-Abstract",
        "-Description",
        "-UserComment",
        "-Category",
        "-SupplementalCategories",
        "-Keywords",
        str(image_path)
    ]

    meta = {}
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
        if res.returncode == 0 and res.stdout:
            data = json.loads(res.stdout)
            if data and isinstance(data, list):
                meta = data[0]
    except Exception as e:
        print(f"[ExifTool Warning] {e}")

    date_time = meta.get("DateTimeOriginal") or meta.get("CreateDate") or meta.get("ModifyDate") or "不明"
    
    time_zone_fact = "日中（標準光）"
    if date_time != "不明" and " " in date_time:
        try:
            time_str = date_time.split(" ")[1]
            hour = int(time_str.split(":")[0])
            if 4 <= hour < 7:
                time_zone_fact = "早朝・黎明（日の出前後）"
            elif 7 <= hour < 16:
                time_zone_fact = "日中・明るい時間帯"
            elif 16 <= hour < 19:
                time_zone_fact = "夕方・マジックアワー（日の入り前後）"
            else:
                time_zone_fact = "夜間・暗所（人工光・長時間露光）"
        except Exception:
            pass

    user_intent = (
        meta.get("Caption-Abstract") or 
        meta.get("Description") or 
        meta.get("UserComment") or 
        ""
    )

    extracted_metadata = {
        "date_time": date_time,
        "time_zone_fact": time_zone_fact,
        "camera_model": meta.get("Model", "不明"),
        "lens_model": meta.get("LensModel", "不明"),
        "f_number": f"f/{meta.get('FNumber')}" if meta.get('FNumber') else "不明",
        "shutter_speed": f"{meta.get('ExposureTime')}s" if meta.get('ExposureTime') else "不明",
        "iso": f"ISO {meta.get('ISO')}" if meta.get('ISO') else "不明",
        "focal_length": f"{meta.get('FocalLength')}mm" if meta.get('FocalLength') else "不明",
        "user_intent": user_intent
    }

    dop_path = image_path.with_name(image_path.name + ".dop")
    dop_info = {
        "content_headline": meta.get("Headline", ""),
        "category": meta.get("Category", ""),
        "other_categories": meta.get("SupplementalCategories", ""),
        "keywords": meta.get("Keywords", ""),
        "preset_name": "標準/未指定"
    }

    if dop_path.exists():
        try:
            content = dop_path.read_text(encoding="utf-8", errors="ignore")
            preset_m = re.search(r'PresetName\s*=\s*"([^"]+)"', content)
            if preset_m:
                dop_info["preset_name"] = preset_m.group(1)
        except Exception:
            pass

    metadata_block = f"""file_name: {image_path.name}
date_time: {extracted_metadata['date_time']}
time_zone_fact: {extracted_metadata['time_zone_fact']}
camera_model: {extracted_metadata['camera_model']}
lens_model: {extracted_metadata['lens_model']}
f_number: {extracted_metadata['f_number']}
shutter_speed: {extracted_metadata['shutter_speed']}
iso: {extracted_metadata['iso']}
focal_length: {extracted_metadata['focal_length']}
dxo_dop_sidecar: {'あり' if dop_path.exists() else 'なし'} [Preset: {dop_info['preset_name']}]
contentHeadline: {dop_info['content_headline']}
user_intent: {extracted_metadata['user_intent']}
Category: {dop_info['category']}
OtherCategories: {dop_info['other_categories']}
Keywords: {dop_info['keywords']}"""

    return extracted_metadata, dop_info, metadata_block


class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Photo AI Critique - デスクトップ分析ツール")
        self.geometry("700x460")
        self.resizable(False, False)

        self.target_dir = None
        self.overwrite_var = tk.BooleanVar(value=False)

        self.create_widgets()
        self.load_last_directory()

    def create_widgets(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        lbl_title = ttk.Label(frame, text="写真講評 AI 一括生成システム", font=("Helvetica", 16, "bold"))
        lbl_title.pack(anchor=tk.W, pady=(0, 15))

        # フォルダ選択セクション
        dir_frame = ttk.Frame(frame)
        dir_frame.pack(fill=tk.X, pady=5)

        self.btn_select = ttk.Button(dir_frame, text="対象フォルダを選択", command=self.select_directory)
        self.btn_select.pack(side=tk.LEFT)

        self.lbl_dir_path = ttk.Label(dir_frame, text="未選択", foreground="gray", wraplength=480)
        self.lbl_dir_path.pack(side=tk.LEFT, padx=10)

        # オプション設定
        chk_overwrite = ttk.Checkbutton(frame, text="既存の分析結果を上書き再生成する (処理済みファイルをスキップしない)", variable=self.overwrite_var)
        chk_overwrite.pack(anchor=tk.W, pady=15)

        # 実行ボタン
        self.btn_run = ttk.Button(frame, text="一括分析・生成を実行", command=self.confirm_and_start_processing, state=tk.DISABLED)
        self.btn_run.pack(fill=tk.X, pady=10)

        # プログレスバー
        self.progress_bar = ttk.Progressbar(frame, mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=10)

        # ステータス表示
        self.lbl_status = ttk.Label(frame, text="フォルダを選択して実行してください。", foreground="black", font=("Helvetica", 11))
        self.lbl_status.pack(anchor=tk.W, pady=5)

        # 成果物オープンボタンフレーム
        open_frame = ttk.Frame(frame)
        open_frame.pack(fill=tk.X, pady=(10, 0))
        self.btn_open_folder = ttk.Button(open_frame, text="📂 成果物フォルダを開く", command=self.open_output_folder, state=tk.DISABLED)
        self.btn_open_folder.pack(side=tk.RIGHT)

    def load_last_directory(self):
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                last_path = Path(data.get("last_dir", ""))
                if last_path.exists() and last_path.is_dir():
                    self.target_dir = last_path
                    self.lbl_dir_path.config(text=str(last_path), foreground="black")
                    self.btn_run.config(state=tk.NORMAL)
                    self.btn_open_folder.config(state=tk.NORMAL)
                    self.lbl_status.config(text="前回の選択フォルダを復元しました。実行準備完了。")
            except Exception:
                pass

    def save_last_directory(self, path: Path):
        try:
            CONFIG_FILE.write_text(json.dumps({"last_dir": str(path)}, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def select_directory(self):
        selected = filedialog.askdirectory()
        if selected:
            path = Path(selected)
            valid_exts = {".jpg", ".jpeg", ".png"}
            has_images = any(f.is_file() and f.suffix.lower() in valid_exts for f in path.iterdir())
            
            if has_images or re.search(r'\d{6}', path.name):
                self.target_dir = path
                self.lbl_dir_path.config(text=str(path), foreground="black")
                self.btn_run.config(state=tk.NORMAL)
                self.btn_open_folder.config(state=tk.NORMAL)
                self.lbl_status.config(text="実行準備完了。")
                self.save_last_directory(path)
            else:
                messagebox.showerror("エラー", "選択したフォルダ内に画像ファイル (.jpg, .png) が見つかりませんでした。")

    def confirm_and_start_processing(self):
        if not self.target_dir or not self.target_dir.exists():
            messagebox.showerror("エラー", "有効なフォルダが選択されていません。")
            return

        msg = f"以下のフォルダに対してAI講評の一括生成を開始します。\n\n対象: {self.target_dir}\n上書きモード: {'ON' if self.overwrite_var.get() else 'OFF'}"
        if not messagebox.askyesno("実行確認", msg):
            return

        self.btn_select.config(state=tk.DISABLED)
        self.btn_run.config(state=tk.DISABLED)
        self.progress_bar['value'] = 0
        threading.Thread(target=self.process_batch, daemon=True).start()

    def process_batch(self):
        try:
            log_mgr = DesktopLogManager(self.target_dir)
            valid_extensions = {".jpg", ".jpeg", ".png"}
            image_files = [f for f in self.target_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_extensions]

            if not image_files:
                self.update_status("対象画像が見つかりませんでした。")
                self.reset_buttons()
                return

            total = len(image_files)
            processed_count = 0

            for idx, img_path in enumerate(image_files, 1):
                file_name = img_path.name
                
                if not self.overwrite_var.get() and log_mgr.is_processed(file_name):
                    self.update_status(f"[{idx}/{total}] スキップ (処理済): {file_name}")
                    continue

                self.update_status(f"[{idx}/{total}] AI講評生成中: {file_name}...")
                
                metadata, dop_info, metadata_block = extract_metadata_and_dop(img_path)
                critique_text = generate_critique(img_path, metadata=metadata, dop_info=dop_info, mode="full")

                log_mgr.save_analysis_result(file_name, metadata_block, critique_text)
                
                card_path = log_mgr.get_card_output_path(file_name)
                create_critique_card(img_path, critique_text, card_path)

                processed_count += 1
                self.progress_bar['value'] = (idx / total) * 100

            self.update_status(f"処理完了: {processed_count} 件の画像を分析しました。")
            
            if messagebox.askyesno("完了", f"すべての処理が完了しました（成功: {processed_count} 件）。\n処理対象フォルダを開きますか？"):
                self.open_output_folder()

        except Exception as e:
            self.update_status(f"エラー発生: {e}")
            messagebox.showerror("エラー", f"処理中にエラーが発生しました:\n{e}")
        finally:
            self.reset_buttons()

    def open_output_folder(self):
        # 処理対象として選択しているフォルダ(self.target_dir)を直接開くように変更
        if self.target_dir and self.target_dir.exists():
            try:
                subprocess.run(["open", str(self.target_dir)])
            except Exception:
                pass

    def update_status(self, text: str):
        self.lbl_status.config(text=text)
        self.update_idletasks()

    def reset_buttons(self):
        self.btn_select.config(state=tk.NORMAL)
        self.btn_run.config(state=tk.NORMAL)


if __name__ == "__main__":
    app = Application()
    app.mainloop()
