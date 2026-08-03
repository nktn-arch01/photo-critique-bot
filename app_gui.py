import os
import sys
import json
import re
import threading
import subprocess
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ExifTags

from log_manager import DesktopLogManager
from critique_engine import generate_critique, get_openai_client
from generate_critique_card import create_critique_card

CONFIG_FILE = Path.home() / ".photo_ai_config.json"


def get_exiftool_path() -> str:
    """ExifToolの実行パスを取得します"""
    base_dir = Path(__file__).parent
    local_exiftool = base_dir / "tools" / "exiftool"
    if local_exiftool.exists():
        return str(local_exiftool)
    return "exiftool"


def extract_metadata_and_dop(image_path: Path) -> tuple[dict, dict, str]:
    """
    ExifToolまたは内蔵PILを使用してメタデータと.dop情報を抽出します。
    """
    exiftool_bin = get_exiftool_path()
    meta_raw = {}
    
    # 1. ExifToolによる抽出の試行
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

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
        if res.returncode == 0 and res.stdout:
            data = json.loads(res.stdout)
            if data and isinstance(data, list):
                meta_raw = data[0]
    except Exception:
        pass

    # 2. ExifToolが失敗した場合のPIL（Python内蔵）フォールバック
    date_time = meta_raw.get("DateTimeOriginal") or meta_raw.get("CreateDate") or meta_raw.get("ModifyDate")
    camera_model = meta_raw.get("Model")
    lens_model = meta_raw.get("LensModel")
    f_number = f"f/{meta_raw.get('FNumber')}" if meta_raw.get('FNumber') else None
    shutter_speed = f"{meta_raw.get('ExposureTime')}s" if meta_raw.get('ExposureTime') else None
    iso = f"ISO {meta_raw.get('ISO')}" if meta_raw.get('ISO') else None
    focal_length = f"{meta_raw.get('FocalLength')}mm" if meta_raw.get('FocalLength') else None
    user_intent = meta_raw.get("Caption-Abstract") or meta_raw.get("Description") or meta_raw.get("UserComment") or ""

    if not date_time or camera_model is None:
        try:
            with Image.open(image_path) as img:
                exif = img._getexif()
                if exif:
                    exif_data = {ExifTags.TAGS.get(k, k): v for k, v in exif.items() if k in ExifTags.TAGS}
                    date_time = date_time or str(exif_data.get("DateTimeOriginal", exif_data.get("DateTime", "不明")))
                    camera_model = camera_model or str(exif_data.get("Model", "不明"))
                    lens_model = lens_model or str(exif_data.get("LensModel", "不明"))
                    if not f_number and "FNumber" in exif_data:
                        f_number = f"f/{float(exif_data['FNumber']):.1f}"
                    if not shutter_speed and "ExposureTime" in exif_data:
                        shutter_speed = f"1/{int(1/float(exif_data['ExposureTime']))}s"
                    if not iso and "ISOSpeedRatings" in exif_data:
                        iso = f"ISO {exif_data['ISOSpeedRatings']}"
                    if not focal_length and "FocalLength" in exif_data:
                        focal_length = f"{int(exif_data['FocalLength'])}mm"
                    user_intent = user_intent or str(exif_data.get("ImageDescription", ""))
        except Exception:
            pass

    date_time = date_time or "不明"
    camera_model = camera_model or "不明"
    lens_model = lens_model or "不明"
    f_number = f_number or "不明"
    shutter_speed = shutter_speed or "不明"
    iso = iso or "不明"
    focal_length = focal_length or "不明"

    # 時間帯判定
    time_zone_fact = "日中・明るい時間帯"
    if date_time != "不明" and " " in date_time:
        try:
            time_str = date_time.split(" ")[1]
            hour = int(time_str.split(":")[0])
            if 4 <= hour < 7:
                time_zone_fact = "早朝・黎明（日の出前後）"
            elif 7 <= hour < 11:
                time_zone_fact = "午前（順光・斜光）"
            elif 11 <= hour < 14:
                time_zone_fact = "昼間（トップライト・高コントラスト）"
            elif 14 <= hour < 17:
                time_zone_fact = "午後（斜光・長シャドウ）"
            elif 17 <= hour < 19:
                time_zone_fact = "夕方・マジックアワー（日の入り前後）"
            else:
                time_zone_fact = "夜間・暗所（人工光・長時間露光）"
        except Exception:
            pass

    extracted_metadata = {
        "date_time": date_time,
        "time_zone_fact": time_zone_fact,
        "camera_model": camera_model,
        "lens_model": lens_model,
        "f_number": f_number,
        "shutter_speed": shutter_speed,
        "iso": iso,
        "focal_length": focal_length,
        "user_intent": user_intent
    }

    # .dop ファイルの検索と解析
    dop_path = image_path.parent / f"{image_path.stem}.dop"
    if not dop_path.exists():
        dop_path = image_path.parent / f"{image_path.name}.dop"

    dop_info = {
        "rating_str": "なし",
        "preset_name": "標準/未指定",
        "content_headline": meta_raw.get("Headline", ""),
        "category": meta_raw.get("Category", ""),
        "other_categories": meta_raw.get("SupplementalCategories", ""),
        "keywords": meta_raw.get("Keywords", "")
    }

    if dop_path.exists():
        try:
            content = dop_path.read_text(encoding="utf-8", errors="ignore")
            rank_m = re.search(r'Rank\s*=\s*(\d+)', content)
            if rank_m:
                r = int(rank_m.group(1))
                dop_info["rating_str"] = "★" * r + "☆" * (5 - r) + f" ({r}/5)"

            preset_m = re.search(r'PresetName\s*=\s*"([^"]+)"', content)
            if preset_m:
                dop_info["preset_name"] = preset_m.group(1)

            if not dop_info["content_headline"]:
                hl_m = re.search(r'Headline\s*=\s*"([^"]+)"', content)
                if hl_m: dop_info["content_headline"] = hl_m.group(1)

            if not extracted_metadata["user_intent"]:
                cap_m = re.search(r'Caption\s*=\s*\[\[(.*?)\]\]', content, re.DOTALL)
                if cap_m: extracted_metadata["user_intent"] = cap_m.group(1).strip()

            if not dop_info["category"]:
                cat_m = re.search(r'Category\s*=\s*"([^"]+)"', content)
                if cat_m: dop_info["category"] = cat_m.group(1)

            if not dop_info["other_categories"]:
                supp_m = re.search(r'SupplementalCategories\s*=\s*\{([^\}]+)\}', content)
                if supp_m:
                    cats = re.findall(r'"([^"]+)"', supp_m.group(1))
                    dop_info["other_categories"] = ", ".join(cats)

            if not dop_info["keywords"]:
                kw_m = re.search(r'Keywords\s*=\s*\{([^\}]+)\}', content)
                if kw_m:
                    kws = re.findall(r'"([^"]+)"', kw_m.group(1))
                    dop_info["keywords"] = ", ".join(kws)

        except Exception:
            pass

    dop_status = f"あり [評価: {dop_info['rating_str']}] [Preset: {dop_info['preset_name']}]" if dop_path.exists() else "なし"

    metadata_block = f"""file_name: {image_path.name}
date_time: {extracted_metadata['date_time']}
time_zone_fact: {extracted_metadata['time_zone_fact']}
camera_model: {extracted_metadata['camera_model']}
lens_model: {extracted_metadata['lens_model']}
f_number: {extracted_metadata['f_number']}
shutter_speed: {extracted_metadata['shutter_speed']}
iso: {extracted_metadata['iso']}
focal_length: {extracted_metadata['focal_length']}
dxo_dop_sidecar: {dop_status}
contentHeadline: {dop_info['content_headline']}
user_intent: {extracted_metadata['user_intent']}
Category: {dop_info['category']}
OtherCategories: {dop_info['other_categories']}
Keywords: {dop_info['keywords']}"""

    return extracted_metadata, dop_info, metadata_block


class PhotoAICritiqueApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Photo AI 写真講評バッチ処理システム")
        self.root.geometry("700x580")
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
            self.log(f"🚀 講評バッチ処理を開始します: {target_dir.name}")
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

                # 1枚ごとに独立した try...except を設定
                try:
                    self.log("   └─ EXIF / .dop メタデータ抽出中...")
                    exif_meta, dop_info, metadata_block = extract_metadata_and_dop(img_path)

                    self.log("   └─ AI講評生成中 (CritiqueEngine)...")
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
        self.btn_start.config(state=tk.NORMAL, bg="#007aff")
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