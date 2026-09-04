from __future__ import annotations

import asyncio
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from guguwebui.dependencies.auth import get_current_user
from guguwebui.services.monitor_service import MonitorService
from guguwebui.structures import BusinessException
from guguwebui.structures.envelope import ApiSuccessEnvelope, success

router = APIRouter()

# metric/range 枚举收敛（非法值由 FastAPI 校验为 422 + 统一错误体，不再手写 400 分支）
MetricName = Literal["cpu", "memory", "network", "tps", "mspt", "load", "disk"]
RangeKey = Literal["10m", "30m", "1h", "6h", "12h", "1d", "3d", "7d"]


def _get_service(request: Request) -> Optional[MonitorService]:
    return getattr(request.app.state, "monitor_service", None)


def _require_service(request: Request) -> MonitorService:
    service = _get_service(request)
    if service is None:
        raise BusinessException(
            "Monitor service unavailable",
            status_code=503,
            code="monitor_unavailable",
        )
    return service


@router.get("/monitor/overview", response_model=ApiSuccessEnvelope)
async def api_monitor_overview(
    request: Request,
    _user: dict = Depends(get_current_user),
):
    """获取服务器状态最新快照（TPS/MSPT/CPU/内存/Swap/磁盘/负载/网络）"""
    result = await asyncio.to_thread(_require_service(request).get_overview)
    return JSONResponse(success(result))


@router.get("/monitor/history", response_model=ApiSuccessEnvelope)
async def api_monitor_history(
    request: Request,
    metric: MetricName = Query("cpu"),
    range: RangeKey = Query("1h"),
    _user: dict = Depends(get_current_user),
):
    """获取指定指标的时间序列（含降采样）。

    metric: cpu / memory / network / tps / mspt / load / disk
    range: 10m / 30m / 1h / 6h / 12h / 1d / 3d / 7d
    """
    result = await asyncio.to_thread(
        _require_service(request).get_history, metric, range
    )
    return JSONResponse(success(result))


@router.get("/monitor/table", response_model=ApiSuccessEnvelope)
async def api_monitor_table(
    request: Request,
    range: RangeKey = Query("1h"),
    _user: dict = Depends(get_current_user),
):
    """统计表数据：各指标在当前时间范围内的 avg/min/max"""
    result = await asyncio.to_thread(_require_service(request).get_table, range)
    return JSONResponse(success(result))
