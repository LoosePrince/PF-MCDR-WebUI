"""操作审计查询（仅管理员）。"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from guguwebui.dependencies.auth import get_current_admin
from guguwebui.services.operation_audit_service import list_records
from guguwebui.structures.envelope import PageEnvelope, page

router = APIRouter(tags=["audit"])


@router.get("/audit_logs", response_model=PageEnvelope)
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
                # ts 为 epoch 秒（入库 float，转为 int 保证整型契约）
                "ts": int(r.get("ts") or 0),
                "operation_type": r.get("operation_type"),
                "summary": r.get("summary"),
                "detail": r.get("detail"),
                "account": r.get("account"),
            }
        )
    return JSONResponse(page(items=out, total=total, offset=offset, limit=limit))
