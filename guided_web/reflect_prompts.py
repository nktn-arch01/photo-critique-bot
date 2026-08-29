"""振り返る画面のチェックボックス項目（構想 PDF 準拠）。"""

from __future__ import annotations

# グループ見出し + チェック項目。
# UI は column で左右2列（左: 気づいた／ふと思った、右: この写真を）。
# 各グループ内の項目は縦1列。
REFLECTION_GROUPS: tuple[dict, ...] = (
    {
        "id": "noticed",
        "label": "気づいたことがある",
        "column": "left",
        "items": (
            {"id": "see", "label": "写真を見て"},
            {"id": "words", "label": "言葉にして"},
        ),
    },
    {
        "id": "thought",
        "label": "ふと思ったことは",
        "column": "left",
        "items": (
            {"id": "scene", "label": "その時の情景"},
            {"id": "memory", "label": "その時の記憶"},
            {"id": "feeling", "label": "自分の気持ち"},
            {"id": "sense", "label": "自分の感性"},
            {"id": "someone", "label": "誰かのこと"},
        ),
    },
    {
        "id": "photo",
        "label": "この写真を",
        "column": "right",
        "items": (
            {"id": "keep", "label": "手元に置いておきたい"},
            {"id": "revisit", "label": "何度も見返したい"},
            {"id": "share", "label": "人に見せたい"},
            {"id": "book", "label": "フォトブックにしたい"},
            {"id": "exhibit", "label": "作品展に出したい"},
        ),
    },
)


def reflection_item_key(group_id: str, item_id: str) -> str:
    return f"{group_id}_{item_id}"


def iter_reflection_items() -> list[tuple[str, str, str]]:
    """(key, group_label, item_label) の一覧。"""
    rows: list[tuple[str, str, str]] = []
    for group in REFLECTION_GROUPS:
        gid = group["id"]
        glabel = group["label"]
        for item in group["items"]:
            rows.append((reflection_item_key(gid, item["id"]), glabel, item["label"]))
    return rows


def selected_reflection_labels(reflections: dict) -> list[str]:
    """チェックされた項目ラベル（テキスト入力があればそちらを優先）。"""
    selected: list[str] = []
    for key, _glabel, default_label in iter_reflection_items():
        entry = reflections.get(key) or {}
        if not entry.get("checked"):
            continue
        text = str(entry.get("text") or "").strip()
        selected.append(text if text else default_label)
    return selected


def format_reflections_block(reflections: dict) -> str:
    """ログ用: グループ見出し + ⬜/☑ 付き項目一覧（「振り返りメモ」ラベルなし）。"""
    lines: list[str] = []
    for group in REFLECTION_GROUPS:
        lines.append(str(group["label"]))
        for item in group["items"]:
            key = reflection_item_key(group["id"], item["id"])
            entry = reflections.get(key) or {}
            mark = "☑" if entry.get("checked") else "⬜"
            lines.append(f"{mark} {item['label']}")
    return "\n".join(lines)
