"""
Supabase critique_logs と critique-cards Storage の保持期間削除。

分析用の `critique_events` は削除しない（匿名・長期）。

手動: RETENTION_DAYS=30 python retention_purge.py
ドライラン: DRY_RUN=true python retention_purge.py

月次自動実行: .github/workflows/retention-purge.yml（GitHub Secrets 要）
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, List, Optional, Sequence

from privacy_utils import storage_path_from_card_url

BUCKET = "critique-cards"
DATE_COLUMN = os.getenv("CRITIQUE_LOG_DATE_COLUMN", "created_at").strip() or "created_at"
DEFAULT_RETENTION_DAYS = 30
SELECT_PAGE = 500
STORAGE_REMOVE_CHUNK = 100


def retention_days_from_env() -> int:
    raw = os.getenv("RETENTION_DAYS", str(DEFAULT_RETENTION_DAYS)).strip()
    try:
        days = int(raw)
    except ValueError as e:
        raise SystemExit(f"Invalid RETENTION_DAYS: {raw!r}") from e
    if days < 1:
        raise SystemExit("RETENTION_DAYS must be >= 1")
    return days


def is_dry_run() -> bool:
    return os.getenv("DRY_RUN", "false").strip().lower() in ("1", "true", "yes")


def purge_orphan_storage_enabled() -> bool:
    return os.getenv("RETENTION_PURGE_ORPHANS", "true").strip().lower() in ("1", "true", "yes")


def utc_cutoff(retention_days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=retention_days)


def cutoff_iso(cutoff: datetime) -> str:
    return cutoff.replace(microsecond=0).isoformat()


def parse_storage_timestamp(entry: dict[str, Any]) -> Optional[datetime]:
    for key in ("updated_at", "created_at", "last_accessed_at"):
        raw = entry.get(key)
        if not raw:
            continue
        text = str(raw).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    meta = entry.get("metadata") or {}
    if isinstance(meta, dict):
        for key in ("lastModified", "last_modified"):
            raw = meta.get(key)
            if raw:
                text = str(raw).replace("Z", "+00:00")
                try:
                    dt = datetime.fromisoformat(text)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(timezone.utc)
                except ValueError:
                    pass
    return None


def collect_storage_paths_from_rows(rows: Sequence[dict[str, Any]]) -> List[str]:
    seen: set[str] = set()
    paths: List[str] = []
    for row in rows:
        url = row.get("card_image_url") or ""
        path = storage_path_from_card_url(str(url))
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def list_storage_files_recursive(storage_api: Any, bucket: str, prefix: str = "") -> List[dict[str, Any]]:
    """バケット内のファイルエントリ（name はバケットルートからの相対パス）。"""
    files: List[dict[str, Any]] = []
    list_path = prefix.rstrip("/") if prefix else ""
    try:
        entries = storage_api.from_(bucket).list(list_path or None)
    except TypeError:
        entries = storage_api.from_(bucket).list(list_path)
    if not entries:
        return files

    for entry in entries:
        name = entry.get("name") or ""
        if not name:
            continue
        if entry.get("id"):
            rel = f"{prefix}{name}" if prefix else name
            files.append({**entry, "path": rel})
            continue
        sub_prefix = f"{prefix}{name}/" if prefix else f"{name}/"
        files.extend(list_storage_files_recursive(storage_api, bucket, sub_prefix))
    return files


def chunk_list(items: Sequence[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield list(items[i : i + size])


def fetch_expired_log_rows(client: Any, cutoff: datetime) -> List[dict[str, Any]]:
    rows: List[dict[str, Any]] = []
    iso = cutoff_iso(cutoff)
    offset = 0
    while True:
        res = (
            client.table("critique_logs")
            .select("id, card_image_url")
            .lt(DATE_COLUMN, iso)
            .range(offset, offset + SELECT_PAGE - 1)
            .execute()
        )
        batch = res.data or []
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < SELECT_PAGE:
            break
        offset += SELECT_PAGE
    return rows


def delete_storage_paths(storage_api: Any, paths: Sequence[str], dry_run: bool) -> int:
    if not paths:
        return 0
    removed = 0
    for chunk in chunk_list(list(paths), STORAGE_REMOVE_CHUNK):
        if dry_run:
            for p in chunk:
                print(f"[dry-run] storage remove {p}", flush=True)
            removed += len(chunk)
            continue
        try:
            storage_api.from_(BUCKET).remove(chunk)
            removed += len(chunk)
            for p in chunk:
                print(f"[storage removed] {p}", flush=True)
        except Exception as e:
            print(f"[storage remove error] {chunk!r}: {e}", flush=True)
    return removed


def delete_expired_log_rows(client: Any, cutoff: datetime, dry_run: bool) -> int:
    iso = cutoff_iso(cutoff)
    if dry_run:
        count_res = (
            client.table("critique_logs").select("id", count="exact").lt(DATE_COLUMN, iso).limit(1).execute()
        )
        total = count_res.count if count_res.count is not None else len(fetch_expired_log_rows(client, cutoff))
        print(f"[dry-run] would delete critique_logs rows: {total}", flush=True)
        return int(total)

    res = client.table("critique_logs").delete().lt(DATE_COLUMN, iso).execute()
    deleted = len(res.data) if res.data else 0
    print(f"[db deleted] critique_logs rows: {deleted}", flush=True)
    return deleted


def purge_old_storage_by_age(storage_api: Any, cutoff: datetime, dry_run: bool) -> int:
    files = list_storage_files_recursive(storage_api, BUCKET)
    old_paths: List[str] = []
    for entry in files:
        path = entry.get("path") or entry.get("name") or ""
        if not path:
            continue
        ts = parse_storage_timestamp(entry)
        if ts is None or ts >= cutoff:
            continue
        old_paths.append(str(path))

    return delete_storage_paths(storage_api, old_paths, dry_run)


def run_purge(client: Any, *, retention_days: int, dry_run: bool, purge_orphans: bool) -> None:
    cutoff = utc_cutoff(retention_days)
    print(
        f"[retention] days={retention_days} cutoff={cutoff_iso(cutoff)} "
        f"dry_run={dry_run} orphans={purge_orphans}",
        flush=True,
    )

    expired_rows = fetch_expired_log_rows(client, cutoff)
    paths_from_db = collect_storage_paths_from_rows(expired_rows)
    print(f"[plan] expired log rows={len(expired_rows)} storage paths from urls={len(paths_from_db)}", flush=True)

    delete_storage_paths(client.storage, paths_from_db, dry_run)
    delete_expired_log_rows(client, cutoff, dry_run)

    if purge_orphans:
        n = purge_old_storage_by_age(client.storage, cutoff, dry_run)
        print(f"[orphan storage] targets removed or planned: {n}", flush=True)


def main() -> int:
    try:
        from supabase import create_client
    except ImportError:
        print("Install supabase: pip install supabase", file=sys.stderr)
        return 1

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_KEY", "")).strip()
    if not url or not key:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        return 1

    days = retention_days_from_env()
    dry_run = is_dry_run()
    purge_orphans = purge_orphan_storage_enabled()

    client = create_client(url, key)
    try:
        run_purge(client, retention_days=days, dry_run=dry_run, purge_orphans=purge_orphans)
    except Exception as e:
        err = str(e).lower()
        if DATE_COLUMN in err or "column" in err:
            print(
                f"[error] critique_logs.{DATE_COLUMN} が使えない可能性があります。"
                f" CRITIQUE_LOG_DATE_COLUMN を確認してください: {e}",
                file=sys.stderr,
                flush=True,
            )
        else:
            print(f"[error] {e}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
