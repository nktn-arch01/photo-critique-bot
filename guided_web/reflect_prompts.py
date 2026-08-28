"""振り返る画面のチェックボックス項目（構想 PDF 準拠）。"""

from __future__ import annotations

# グループ見出し + チェック項目。UI は 2 列グリッドで表示。
REFLECTION_GROUPS: tuple[dict, ...] = (
    {
        "id": "noticed",
        "label": "気づいたこと",
        "items": (
            {"id": "light", "label": "光・空気"},
            {"id": "color", "label": "色・トーン"},
            {"id": "composition", "label": "構図・距離"},
            {"id": "subject", "label": "主役と背景"},
        ),
    },
    {
        "id": "thought",
        "label": "ふと思ったこと",
        "items": (
            {"id": "first_impression", "label": "撮った直後の印象"},
            {"id": "on_review", "label": "見返して気づいたこと"},
            {"id": "memory", "label": "思い出した場面"},
            {"id": "feeling", "label": "いまの気持ち"},
        ),
    },
    {
        "id": "photo",
        "label": "この写真を",
        "items": (
            {"id": "keep", "label": "残したい"},
            {"id": "retry", "label": "もう一度撮りたい"},
            {"id": "another", "label": "別の切り口で試したい"},
            {"id": "next", "label": "次に活かしたい"},
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
