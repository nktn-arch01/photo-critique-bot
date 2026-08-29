"""講評本文【1】〜【7】をセクション単位に分割（Guided UI 用）。"""

from __future__ import annotations

import re

_SECTION_HEAD = re.compile(r"【(\d+)[\.．\s][^】]*】")


def split_critique_sections(body: str) -> list[dict[str, str]]:
    if not (body or "").strip():
        return []

    matches = list(_SECTION_HEAD.finditer(body))
    if not matches:
        return [{"id": "1", "heading": "本文", "text": body.strip()}]

    sections: list[dict[str, str]] = []
    for i, m in enumerate(matches):
        sec_id = m.group(1)
        heading = m.group(0).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        text = body[start:end].strip()
        sections.append({"id": sec_id, "heading": heading, "text": text})
    return sections
