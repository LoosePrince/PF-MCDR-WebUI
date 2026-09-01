import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from guguwebui.dependencies.auth import get_current_user
from guguwebui.services.monitor_service import RANGE_MAP, MonitorService

router = APIRouter()

METRICS = {"cpu", "memory", "network", "tps", "mspt", "load", "disk"}


def _get_service(request: Request) -> Optional[MonitorService]:
    return getattr(request.app.state, "monitor_service", None)


@router.get("/monitor/overview")
async def api_monitor_overview(
    request: Request,
    _user: dict = Depends(get_current_user),
):
    """获取服务器状态最新快照（TPS/MSPT/CPU/内存/Swap/磁盘/负载/网络）"""
    service = _get_service(request)
    if service is None:
        return JSONResponse(
            {"status": "error", "message": "Monitor service unavailable"},
            status_code=503,
        )
    result = await asyncio.to_thread(service.get_overview)
    return JSONResponse(result)


@router.get("/monitor/history")
async def api_monitor_history(
    request: Request,
    metric: str = "cpu",
    range: str = "1h",
    _user: dict = Depends(get_current_user),
):
    """获取指定指标的时间序列（含降采样）。

    metric: cpu / memory / network / tps / mspt / load / disk
    range: 10m / 30m / 1h / 6h / 12h / 1d / 3d / 7d
    """
    service = _get_service(request)
    if service is None:
        return JSONResponse(
            {"status": "error", "message": "Monitor service unavailable"},
            status_code=503,
        )
    if metric not in METRICS:
        return JSONResponse(
            {"status": "error", "message": f"Unknown metric: {metric}"},
            status_code=400,
        )
    if range not in RANGE_MAP:
        return JSONResponse(
            {"status": "error", "message": f"Unknown range: {range}"},
            status_code=400,
        )
    result = await asyncio.to_thread(service.get_history, metric, range)
    return JSONResponse(result)


@router.get("/monitor/table")
async def api_monitor_table(
    request: Request,
    range: str = "1h",
    _user: dict = Depends(get_current_user),
):
    """统计表数据：各指标在当前时间范围内的 avg/min/max"""
    service = _get_service(request)
    if service is None:
        return JSONResponse(
            {"status": "error", "message": "Monitor service unavailable"},
            status_code=503,
        )
    if range not in RANGE_MAP:
        return JSONResponse(
            {"status": "error", "message": f"Unknown range: {range}"},
            status_code=400,
        )
    result = await asyncio.to_thread(service.get_table, range)
    return JSONResponse(result)