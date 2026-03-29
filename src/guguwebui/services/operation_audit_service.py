"""操作层审计：追加写入 guguwebui_static/audit_log.bin（长度前缀 + UTF-8 JSON）。"""

from __future__ import annotations

import json
import struct
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from guguwebui.constant import AUDIT_LOG_PATH as _AUDIT_CONST
from guguwebui.utils.audit_actor import account_snapshot_from_user

AUDIT_LOG_PATH = _AUDIT_CONST

_LOCK = threading.Lock()
_UINT32_BE = struct.Struct(">I")

# detail 中单字段字符串最大长度，防止异常大对象
_MAX_DETAIL_STR = 8000


def _truncate_detail(detail: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not detail:
        return None
    out: Dict[str, Any] = {}
    for k, v in detail.items():
        if isinstance(v, str) and len(v) > _MAX_DETAIL_STR:
            out[k] = v[:_MAX_DETAIL_STR] + "…"
        else:
            out[k] = v
    return out


def _ensure_parent() -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def append_record(record: Dict[str, Any]) -> None:
    if "id" not in record:
        record["id"] = str(uuid.uuid4())
    payload = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > 4 * 1024 * 1024:
        record = {
            "id": record.get("id"),
            "ts": record.get("ts"),
            "operation_type": record.get("operation_type", "overflow"),
            "summary": (record.get("summary") or "")[:500],
            "detail": {"error": "record too large, omitted"},
            "account": record.get("account"),
        }
        payload = json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    _ensure_parent()
    frame = _UINT32_BE.pack(len(payload)) + payload
    with _LOCK:
        with open(AUDIT_LOG_PATH, "ab") as f:
            f.write(frame)


def record_operation(
    user: dict,
    *,
    operation_type: str,
    summary: str,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    """在业务成功路径调用：写入一条操作审计。"""
    rec = {
        "ts": time.time(),
        "operation_type": operation_type,
        "summary": summary,
        "detail": _truncate_detail(detail),
        "account": account_snapshot_from_user(user),
    }
    append_record(rec)


def _read_all_records_unlocked() -> List[Dict[str, Any]]:
    if not AUDIT_LOG_PATH.is_file():
        return []
    out: List[Dict[str, Any]] = []
    with open(AUDIT_LOG_PATH, "rb") as f:
        data = f.read()
    offset = 0
    n = len(data)
    while offset + 4 <= n:
        (length,) = _UINT32_BE.unpack_from(data, offset)
        offset += 4
        if length > n - offset or length > 32 * 1024 * 1024:
            break
        chunk = data[offset : offset + length]
        offset += length
        try:
            out.append(json.loads(chunk.decode("utf-8")))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return out


def list_records(
    *,
    offset: int = 0,
    limit: int = 50,
    newest_first: bool = True,
) -> tuple[List[Dict[str, Any]], int]:
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    with _LOCK:
        rows = _read_all_records_unlocked()
    total = len(rows)
    rows.sort(key=lambda r: float(r.get("ts") or 0), reverse=newest_first)
    page = rows[offset : offset + limit]
    return page, total
