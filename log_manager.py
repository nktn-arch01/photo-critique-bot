import re
from pathlib import Path


class DesktopLogManager:
    """
    出力順序の完全保証：
    ファイル名 ➔ ■TITLE ➔ ■SUMMARY ➔ ■SCORES ➔ 講評要約(CRITIQUE_SUMMARY) ➔ 講評本文（【1】〜【7】） ➔ === メタデータ ===
    """
    def __init__(self, target_dir: Path):
        self.target_dir = target_dir
        self.ym_str = target_dir.name  # 例: 202607
        self.year_str = self.ym_str[:4] if len(self.ym_str) >= 4 else "2026"

        self.notes_dir = target_dir / f"{self.ym_str}写真分析ノート"
        self.cards_dir = target_dir / f"{self.ym_str}評価カード"
        self.status_file_path = target_dir / f"{self.ym_str}処理ステータス.txt"
        self.monthly_log_path = target_dir / f"{self.ym_str}写真分析ログ.txt"
        self.annual_log_path = target_dir.parent / f"写真分析ログ_{self.year_str}.txt"

        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.cards_dir.mkdir(parents=True, exist_ok=True)

    def is_processed(self, file_name: str) -> bool:
        if self.status_file_path.exists():
            status_text = self.status_file_path.read_text(encoding="utf-8")
            if file_name in status_text:
                return True
        stem = Path(file_name).stem
        return (self.notes_dir / f"{stem}.md").exists()

    def get_card_output_path(self, file_name: str) -> Path:
        stem = Path(file_name).stem
        return self.cards_dir / f"{stem}_card.png"

    def _format_structured_content(self, file_name: str, metadata_block: str, critique_text: str) -> str:
        title_m = re.search(r'(■TITLE:\s*.+)', critique_text)
        summary_m = re.search(r'(■SUMMARY:\s*.+)', critique_text)
        
        scores_m = re.search(r'(■SCORES:\s*\n(?:・[^\n]+\n)+)', critique_text)
        if not scores_m:
            scores_m = re.search(r'(■SCORES:[\s\S]*?)(?=■CRITIQUE_SUMMARY|##|---|$)', critique_text)

        crit_sum_m = re.search(r'(■CRITIQUE_SUMMARY:\s*.+)', critique_text)
        
        # 講評本文（## 【1】〜最後まで）を確実に取りこぼさず取得
        body_m = re.search(r'(##\s*【1[\s\S]*)', critique_text)

        title_str = title_m.group(1).strip() if title_m else "■TITLE: 写真分析講評"
        summary_str = summary_m.group(1).strip() if summary_m else "■SUMMARY: 分析完了"
        scores_str = scores_m.group(1).strip() if scores_m else "■SCORES:"
        crit_sum_str = crit_sum_m.group(1).strip() if crit_sum_m else "■CRITIQUE_SUMMARY: 優れた瞬間を切り取った作品。"
        body_str = body_m.group(1).strip() if body_m else critique_text

        header_str = f"==================================================\n📷 ファイル名: {file_name}\n=================================================="
        
        structured_critique = f"{title_str}\n\n{summary_str}\n\n{scores_str}\n\n{crit_sum_str}\n\n---\n\n{body_str}"
        full_content = f"{header_str}\n{structured_critique}\n\n---\n\n{metadata_block}"
        return full_content

    def _update_or_append_log(self, log_file_path: Path, file_name: str, log_entry: str):
        if not log_file_path.exists():
            log_file_path.write_text(log_entry, encoding="utf-8")
            return

        content = log_file_path.read_text(encoding="utf-8")
        header_marker = f"==================================================\n📷 ファイル名: {file_name}\n=================================================="

        if header_marker in content:
            # 既存のエントリが存在する場合は、該当ブロックを最新データで置換更新
            start_idx = content.find(header_marker)
            next_marker_idx = content.find("==================================================\n📷 ファイル名:", start_idx + len(header_marker))
            
            if next_marker_idx != -1:
                new_content = content[:start_idx] + log_entry + content[next_marker_idx:]
            else:
                new_content = content[:start_idx] + log_entry
            
            log_file_path.write_text(new_content, encoding="utf-8")
        else:
            # 存在しない場合は末尾に追記
            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(log_entry)

    def save_analysis_result(self, file_name: str, metadata_block: str, critique_text: str):
        stem = Path(file_name).stem
        note_file = self.notes_dir / f"{stem}.md"

        formatted_content = self._format_structured_content(file_name, metadata_block, critique_text)

        # 1. 個別 Markdown ノート
        note_file.write_text(formatted_content, encoding="utf-8")

        # 2. ログエントリ
        log_entry = f"{formatted_content}\n\n"

        # 3. 月間テキストログ (置換または追記)
        self._update_or_append_log(self.monthly_log_path, file_name, log_entry)

        # 4. 年間統合テキストログ (置換または追記)
        self._update_or_append_log(self.annual_log_path, file_name, log_entry)

        # 5. ステータスファイル更新
        if self.status_file_path.exists():
            status_text = self.status_file_path.read_text(encoding="utf-8")
            if file_name not in status_text:
                with open(self.status_file_path, "a", encoding="utf-8") as f:
                    f.write(f"[PROCESSED] {file_name}\n")
        else:
            with open(self.status_file_path, "a", encoding="utf-8") as f:
                f.write(f"[PROCESSED] {file_name}\n")
