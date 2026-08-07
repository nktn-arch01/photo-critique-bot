import re
from datetime import datetime
from pathlib import Path
from critique_parser import parse_critique_text, is_valid_phase2_content


class DesktopLogManager:
    """
    出力順序の完全保証：
    ファイル名 ➔ ■TITLE ➔ ■SUMMARY ➔ ■SCORES ➔ 講評要約(CRITIQUE_SUMMARY) ➔ 講評本文（【1】〜【7】） ➔ === メタデータ ===
    """
    def __init__(self, target_dir: Path):
        self.target_dir = target_dir
        self.ym_str = target_dir.name
        self.year_str = self.ym_str[:4] if len(self.ym_str) >= 4 else "2026"

        self.notes_dir = target_dir / f"{self.ym_str}写真分析ノート"
        self.cards_dir = target_dir / f"{self.ym_str}評価カード"
        self.status_file_path = target_dir / f"{self.ym_str}処理ステータス.txt"
        self.monthly_log_path = target_dir / f"{self.ym_str}写真分析ログ.txt"
        self.annual_log_path = target_dir.parent / f"写真分析ログ_{self.year_str}.txt"

        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.cards_dir.mkdir(parents=True, exist_ok=True)

    _PROCESSED_STATUS_LINE = re.compile(
        r"^\[PROCESSED\]\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+(?P<file_name>.+?)\s*$",
        re.MULTILINE,
    )

    def _is_in_status_file(self, file_name: str) -> bool:
        if not self.status_file_path.exists():
            return False
        status_text = self.status_file_path.read_text(encoding="utf-8")
        for match in self._PROCESSED_STATUS_LINE.finditer(status_text):
            if match.group("file_name") == file_name:
                return True
        return False

    def is_processed(self, file_name: str) -> bool:
        if self._is_in_status_file(file_name):
            return True
        stem = Path(file_name).stem
        return (self.notes_dir / f"{stem}.md").exists()

    def get_card_output_path(self, file_name: str) -> Path:
        stem = Path(file_name).stem
        return self.cards_dir / f"{stem}_card.png"

    def _format_structured_content(self, file_name: str, metadata_block: str, critique_text: str) -> str:
        # 共通パーサーを使用して安全に抽出
        parsed = parse_critique_text(critique_text)

        title_str = f"■TITLE: {parsed['title']}"
        summary_str = f"■SUMMARY: {parsed['summary']}"
        
        # SCORES ブロックの再構築
        scores_lines = ["■SCORES:"]
        for label, score_info in parsed["scores"].items():
            scores_lines.append(f"・{label:<6}: {score_info['stars']} ({score_info['val']}/5)")
        scores_str = "\n".join(scores_lines)

        crit_sum_str = f"■CRITIQUE_SUMMARY: {parsed['point_text']}"
        body_str = self._resolve_body_for_log(critique_text, parsed)

        header_str = f"==================================================\n📷 ファイル名: {file_name}\n=================================================="
        
        structured_critique = f"{title_str}\n\n{summary_str}\n\n{scores_str}\n\n{crit_sum_str}\n\n---\n\n{body_str}"
        full_content = f"{header_str}\n{structured_critique}\n\n---\n\n{metadata_block}"
        return full_content

    def _resolve_body_for_log(self, critique_text: str, parsed: dict) -> str:
        if parsed.get("body"):
            return parsed["body"]
        if "---" in critique_text:
            tail = critique_text.split("---", 1)[1].strip()
            if tail:
                tail_parsed = parse_critique_text(tail)
                if tail_parsed.get("body"):
                    return tail_parsed["body"]
                if is_valid_phase2_content(tail):
                    return tail
        return critique_text

    def _update_or_append_log(self, log_file_path: Path, file_name: str, log_entry: str):
        if not log_file_path.exists():
            log_file_path.write_text(log_entry, encoding="utf-8")
            return

        content = log_file_path.read_text(encoding="utf-8")
        
        pattern = re.compile(
            r'==================================================\n'
            r'📷 ファイル名:\s*' + re.escape(file_name) + r'\n'
            r'==================================================[\s\S]*?'
            r'(?=\n==================================================\n📷 ファイル名:|$)'
        )

        if pattern.search(content):
            new_content = pattern.sub(log_entry.strip(), content)
            log_file_path.write_text(new_content, encoding="utf-8")
        else:
            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write("\n\n" + log_entry.strip())

    def save_analysis_result(self, file_name: str, metadata_block: str, critique_text: str):
        stem = Path(file_name).stem
        note_file = self.notes_dir / f"{stem}.md"

        formatted_content = self._format_structured_content(file_name, metadata_block, critique_text)

        # 1. 個別 Markdown ノート
        note_file.write_text(formatted_content, encoding="utf-8")

        # 2. ログエントリ
        log_entry = f"{formatted_content}\n\n"

        # 3. 月間テキストログ
        self._update_or_append_log(self.monthly_log_path, file_name, log_entry)

        # 4. 年間統合テキストログ
        self._update_or_append_log(self.annual_log_path, file_name, log_entry)

        # 5. ステータスファイル更新 (日時付き)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_line = f"[PROCESSED] {now_str} {file_name}\n"
        with open(self.status_file_path, "a", encoding="utf-8") as f:
            f.write(status_line)