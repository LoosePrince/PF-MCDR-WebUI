"""操作审计查询（仅管理员）。"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from guguwebui.dependencies.auth import get_current_admin
from guguwebui.services.operation_audit_service import list_records

router = APIRouter(tags=["audit"])


@router.get("/audit_logs")
async def get_audit_logs(
    offset: int = 0,
    limit: int = 50,
    _admin: dict = Depends(get_current_admin),
):
    rows, total = list_records(offset=offset, limit=limit, newest_first=True)
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.get("id"),
                "ts": r.get("ts"),
                "operation_type": r.get("operation_type"),
                "summary": r.get("summary"),
                "detail": r.get("detail"),
                "account": r.get("account"),
            }
        )
    return JSONResponse(
        {
            "status": "success",
            "total": total,
            "offset": offset,
            "limit": limit,
            "records": out,
        }
    )
