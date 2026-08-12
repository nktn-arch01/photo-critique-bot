"""互換モジュール: 正式名は ``lumina_review``（Wave 3）。

旧 ``from trace_from_works import …`` を維持するための再エクスポート。
"""

from __future__ import annotations

from lumina_review import *  # noqa: F403
from lumina_review import (  # noqa: F401 — 明示（IDE / 星 import 補助）
    DEV_STEM_SUFFIX,
    JPEG_SUFFIXES,
    CritiqueFn,
    LuminaReviewRunner,
    ProgressFn,
    ReviewBatchResult,
    ReviewConfig,
    ReviewItemResult,
    ReviewProgress,
    ReviewStatus,
    TraceBatchResult,
    TraceConfig,
    TraceItemResult,
    TraceProgress,
    TraceStatus,
    WorksTraceRunner,
    count_jpegs_in_immediate_subdirs,
    is_dev_export,
    list_works_review_targets,
    list_works_trace_targets,
    works_base_stem,
    works_empty_targets_hint,
)
