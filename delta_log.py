"""スクリーニングの監査ログ（DecisionDelta / BatchSession）.

保存先（仕様 §10）:
  {library_unit}/_lumina/sessions/{session_id}.json

内容:
- セッション識別・状態・時刻
- ファイルごとの段（M1/M2/M3）判定・Rating・説明要点
- **pre_h3**: DxO 修正前（バッチ直後）のスナップショット
- **post_h3**: DxO 修正後の JPEG 再スキャン
- **h3_delta**: 前後差分（運用開始後の判定改善用）

GUI から ``record_post_h3``（互換: ``append_h3_rescan``）で後記録する。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from iptc_rating_io import read_shortlist_meta
from library_unit import LibraryUnit, list_source_jpegs

if TYPE_CHECKING:
    from shortlist_pipeline import PipelineResult

LUMINA_DIRNAME = "_lumina"
SESSIONS_DIRNAME = "sessions"


def sessions_dir(unit_path: Path | str) -> Path:
    return Path(unit_path) / LUMINA_DIRNAME / SESSIONS_DIRNAME


def session_path(unit_path: Path | str, session_id: str) -> Path:
    return sessions_dir(unit_path) / f"{session_id}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel_name(unit_path: Path, file_path: Path) -> str:
    try:
        return str(file_path.resolve().relative_to(unit_path.resolve()))
    except Exception:
        return file_path.name


def build_file_deltas(result: PipelineResult) -> list[dict[str, Any]]:
    """PipelineResult からファイル単位の DecisionDelta 一覧を作る。"""
    unit_path = result.unit.path
    by_key: dict[str, dict[str, Any]] = {}

    def bucket(path: Path) -> dict[str, Any]:
        key = str(path.resolve()) if path.exists() else str(path)
        if key not in by_key:
            by_key[key] = {
                "file_name": path.name,
                "relative_path": _rel_name(unit_path, path),
                "path": str(path),
                "stages": [],
                "final_rating": None,
                "description_blocks": {},
                "errors": [],
            }
        return by_key[key]

    if result.m1:
        for d in result.m1.decisions:
            rec = bucket(Path(d.path))
            rec["stages"].append(
                {
                    "stage": "M1",
                    "rating": d.rating,
                    "passed": d.passed,
                    "reason_codes": list(d.reason_codes),
                    "intent_protected": d.intent_protected,
                    "error": d.error,
                }
            )
            if d.error:
                rec["errors"].append(f"M1: {d.error}")
            else:
                rec["final_rating"] = d.rating

    if result.m2:
        for d in result.m2.decisions:
            rec = bucket(Path(d.path))
            entry = {
                "stage": "M2",
                "rating": d.rating,
                "passed": d.passed,
                "skipped": d.skipped,
                "reason_brief": d.reason_brief,
                "heat": d.heat,
                "rank": d.rank,
                "scores": d.score.scores if d.score else None,
                "error": d.error,
            }
            rec["stages"].append(entry)
            if d.error:
                rec["errors"].append(f"M2: {d.error}")
            elif d.skipped:
                continue
            else:
                rec["final_rating"] = d.rating
                if d.passed and d.reason_brief:
                    rec["description_blocks"]["M2"] = d.reason_brief

    if result.m3:
        for d in result.m3.decisions:
            rec = bucket(Path(d.path))
            entry = {
                "stage": "M3",
                "rating": d.rating,
                "passed": d.passed,
                "skipped": d.skipped,
                "slot": d.slot,
                "reason_brief": d.reason_brief,
                "keep_rank": d.keep_rank,
                "tags": list(d.feature.tags) if d.feature else None,
                "error": d.error,
            }
            rec["stages"].append(entry)
            if d.error:
                rec["errors"].append(f"M3: {d.error}")
            elif d.skipped:
                continue
            else:
                rec["final_rating"] = d.rating
                if d.passed and d.reason_brief:
                    rec["description_blocks"]["M3"] = d.reason_brief

    # 安定順: 相対パス
    return sorted(by_key.values(), key=lambda r: r["relative_path"])


def count_ratings_from_deltas(files: list[dict[str, Any]]) -> dict[str, int]:
    out = {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "unknown": 0}
    for rec in files:
        r = rec.get("final_rating")
        if r is None:
            out["unknown"] += 1
            continue
        key = str(r)
        if key in out:
            out[key] += 1
        else:
            out["unknown"] += 1
    return out


def rescan_counts_by_rating(unit: LibraryUnit) -> dict[str, int]:
    """単位内 JPEG を読み直し、現在の Rating 件数を返す（H3 後確認用）。"""
    out = {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "none": 0, "other": 0}
    for path in list_source_jpegs(unit):
        try:
            meta = read_shortlist_meta(path)
        except Exception:
            out["other"] += 1
            continue
        if meta.rating is None:
            out["none"] += 1
        elif 0 <= meta.rating <= 4:
            out[str(meta.rating)] += 1
        else:
            out["other"] += 1
    return out


def _compact_file_snapshot(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """前後比較用の薄いファイル一覧。"""
    out = []
    for f in files:
        out.append(
            {
                "file_name": f.get("file_name"),
                "relative_path": f.get("relative_path"),
                "rating": f.get("final_rating", f.get("rating")),
                "description_blocks": dict(f.get("description_blocks") or {}),
            }
        )
    return out


def snapshot_unit_jpeg_state(unit: LibraryUnit) -> list[dict[str, Any]]:
    """単位内 JPEG の現在 Rating／説明ブロックを列挙。"""
    file_ratings: list[dict[str, Any]] = []
    for jpeg in list_source_jpegs(unit):
        try:
            meta = read_shortlist_meta(jpeg)
            file_ratings.append(
                {
                    "file_name": jpeg.name,
                    "relative_path": _rel_name(unit.path, jpeg),
                    "rating": meta.rating,
                    "description_blocks": {
                        k: v
                        for k, v in (
                            ("M2", meta.stage_reason("M2")),
                            ("M3", meta.stage_reason("M3")),
                        )
                        if v
                    },
                }
            )
        except Exception as exc:
            file_ratings.append(
                {
                    "file_name": jpeg.name,
                    "relative_path": jpeg.name,
                    "rating": None,
                    "error": str(exc),
                    "description_blocks": {},
                }
            )
    return file_ratings


def build_h3_delta(
    pre_files: list[dict[str, Any]],
    post_files: list[dict[str, Any]],
) -> dict[str, Any]:
    """DxO 修正前/後の差分（判定改善用）。"""
    pre_map = {f.get("file_name"): f for f in pre_files if f.get("file_name")}
    post_map = {f.get("file_name"): f for f in post_files if f.get("file_name")}
    changes: list[dict[str, Any]] = []
    transitions: dict[str, int] = {}
    unchanged = 0

    for name, pre in sorted(pre_map.items()):
        post = post_map.get(name)
        if post is None:
            continue
        br, ar = pre.get("rating"), post.get("rating")
        bb = pre.get("description_blocks") or {}
        ab = post.get("description_blocks") or {}
        if br == ar and bb == ab:
            unchanged += 1
            continue
        key = f"{br}->{ar}"
        transitions[key] = transitions.get(key, 0) + 1
        changes.append(
            {
                "file_name": name,
                "before_rating": br,
                "after_rating": ar,
                "before_blocks": bb,
                "after_blocks": ab,
            }
        )

    only_pre = sorted(set(pre_map) - set(post_map))
    only_post = sorted(set(post_map) - set(pre_map))
    return {
        "at": _now_iso(),
        "purpose": "judgment_improvement",
        "changed_count": len(changes),
        "unchanged_count": unchanged,
        "transitions": dict(sorted(transitions.items())),
        "changes": changes,
        "only_in_pre": only_pre,
        "only_in_post": only_post,
    }


def build_session_document(
    result: PipelineResult,
    *,
    include_jpeg_rescan: bool = True,
) -> dict[str, Any]:
    """BatchSession + DecisionDelta を1つの JSON 文書にする。"""
    files = build_file_deltas(result)
    counts = count_ratings_from_deltas(files)
    pre_files = _compact_file_snapshot(files)
    pre_h3 = {
        "at": result.finished_at or _now_iso(),
        "source": "batch_pre_dxo",
        "label": "DxO修正前（バッチ直後）",
        "counts_by_rating": counts,
        "files": pre_files,
    }
    doc: dict[str, Any] = {
        "schema": "lumina.shortlist_session.v1",
        "id": result.session_id,
        "library_unit_id": result.unit.unit_id,
        "library_unit_kind": result.unit.kind,
        "library_unit_path": str(result.unit.path),
        "status": result.status,
        "created_at": result.created_at,
        "finished_at": result.finished_at,
        "cancelled": result.cancelled,
        "error": result.error,
        "jpeg_count": result.jpeg_count,
        "write_meta": None,  # 呼び出し側で埋めてもよい
        "counts_by_rating": counts,
        "counts_by_rating_hint": result.counts_by_rating_hint(),
        "stage_summary": {
            "m1": result.m1.to_dict() if result.m1 else None,
            "m2": {
                "pass_count": result.m2.pass_count,
                "skipped": result.m2.skipped,
                "errors": result.m2.errors,
                "cancelled": result.m2.cancelled,
            }
            if result.m2
            else None,
            "m3": {
                "pass_count": result.m3.pass_count,
                "top_count": result.m3.top_count,
                "margin_count": result.m3.margin_count,
                "skipped": result.m3.skipped,
                "errors": result.m3.errors,
                "cancelled": result.m3.cancelled,
            }
            if result.m3
            else None,
        },
        "files": files,
        "pre_h3": pre_h3,
        "post_h3": None,
        "h3_delta": None,
        # 後方互換（旧フィールド名）
        "h3_rescan": None,
    }
    if include_jpeg_rescan and result.unit.path.is_dir():
        try:
            doc["jpeg_rescan_counts"] = rescan_counts_by_rating(result.unit)
            doc["jpeg_rescan_at"] = _now_iso()
        except Exception as exc:
            doc["jpeg_rescan_counts"] = None
            doc["jpeg_rescan_error"] = str(exc)
    return doc


def write_session_document(unit_path: Path | str, document: dict[str, Any]) -> Path:
    """セッション JSON を書き込む。"""
    session_id = str(document.get("id") or "unknown")
    path = session_path(unit_path, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def save_pipeline_session(
    result: PipelineResult,
    *,
    write_meta: bool | None = None,
    include_jpeg_rescan: bool = True,
) -> Path:
    """PipelineResult から監査ログを保存し、パスを返す。"""
    doc = build_session_document(result, include_jpeg_rescan=include_jpeg_rescan)
    if write_meta is not None:
        doc["write_meta"] = write_meta
    return write_session_document(result.unit.path, doc)


def load_session(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid session JSON: {p}")
    return data


def list_session_paths(unit_path: Path | str) -> list[Path]:
    root = sessions_dir(unit_path)
    if not root.is_dir():
        return []
    return sorted(root.glob("*.json"), key=lambda p: p.name)


def summarize_session(document: dict[str, Any]) -> dict[str, Any]:
    """再読用の短いサマリ。"""
    files = document.get("files") or []
    pre = document.get("pre_h3") or {}
    post = document.get("post_h3") or document.get("h3_rescan") or {}
    delta = document.get("h3_delta") or {}
    return {
        "id": document.get("id"),
        "library_unit_id": document.get("library_unit_id"),
        "status": document.get("status"),
        "created_at": document.get("created_at"),
        "finished_at": document.get("finished_at"),
        "jpeg_count": document.get("jpeg_count"),
        "file_delta_count": len(files),
        "counts_by_rating": document.get("counts_by_rating"),
        "jpeg_rescan_counts": document.get("jpeg_rescan_counts"),
        "stage_summary": document.get("stage_summary"),
        "pre_h3_counts": pre.get("counts_by_rating"),
        "post_h3_counts": post.get("counts_by_rating"),
        "h3_changed_count": delta.get("changed_count"),
        "h3_transitions": delta.get("transitions"),
        "h3_rescan": document.get("h3_rescan"),
        "has_post_h3": bool(post),
    }


def record_post_h3(session_file: Path | str, unit: LibraryUnit | None = None) -> dict[str, Any]:
    """DxO（H3）修正後の状態を記録し、修正前との差分を残す。

    - ``pre_h3``: バッチ直後（無ければ files から復元）
    - ``post_h3``: いまの JPEG 再スキャン
    - ``h3_delta``: 前後差分（判定改善用）
    """
    path = Path(session_file)
    doc = load_session(path)
    if unit is None:
        unit_path = Path(doc["library_unit_path"])
        from library_unit import unit_from_dir

        unit = unit_from_dir(unit_path)
        if unit is None:
            raise ValueError(f"library unit を解釈できません: {unit_path}")

    # pre_h3 が無い古いセッション向けに補完
    if not doc.get("pre_h3"):
        doc["pre_h3"] = {
            "at": doc.get("finished_at") or doc.get("created_at") or _now_iso(),
            "source": "batch_pre_dxo_backfill",
            "label": "DxO修正前（バッチ直後・補完）",
            "counts_by_rating": doc.get("counts_by_rating"),
            "files": _compact_file_snapshot(doc.get("files") or []),
        }

    post_files = snapshot_unit_jpeg_state(unit)
    counts = rescan_counts_by_rating(unit)
    post_h3 = {
        "at": _now_iso(),
        "source": "jpeg_rescan_after_dxo",
        "label": "DxO修正後",
        "counts_by_rating": counts,
        "files": post_files,
    }
    delta = build_h3_delta(doc["pre_h3"].get("files") or [], post_files)

    doc["post_h3"] = post_h3
    doc["h3_delta"] = delta
    # 後方互換
    doc["h3_rescan"] = {
        "at": post_h3["at"],
        "counts_by_rating": counts,
        "files": post_files,
    }
    write_session_document(unit.path, doc)
    return doc


def append_h3_rescan(session_file: Path | str, unit: LibraryUnit | None = None) -> dict[str, Any]:
    """互換エイリアス: ``record_post_h3`` と同じ。"""
    return record_post_h3(session_file, unit=unit)


def latest_session_path(unit_path: Path | str) -> Path | None:
    paths = list_session_paths(unit_path)
    if not paths:
        return None
    # 更新時刻が新しいものを優先
    return max(paths, key=lambda p: p.stat().st_mtime)


@dataclass(frozen=True)
class SessionSummary:
    path: Path
    summary: dict[str, Any]


def load_unit_session_summaries(unit_path: Path | str) -> list[SessionSummary]:
    out: list[SessionSummary] = []
    for path in list_session_paths(unit_path):
        try:
            doc = load_session(path)
            out.append(SessionSummary(path=path, summary=summarize_session(doc)))
        except Exception:
            continue
    return out
