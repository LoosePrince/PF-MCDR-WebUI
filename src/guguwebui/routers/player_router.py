"""玩家管理 API（仅管理员）：玩家列表、假人、白名单、OP、封禁、踢出。

- 读接口保持资源路径，统一 `data` 外壳（service 返回体中的自造 status 键在路由层剥离）；
- 动作迁到子资源：ban/unban/kick → POST /players/{target}/ban|unban|kick，
  op → PUT/DELETE /players/{name}/op，白名单成员 → PUT/DELETE /players/whitelist/{name}，
  开关 → PUT /players/whitelist、重载 → POST /players/whitelist/reload；
- 目标类型（player|ip）未知值 → 400 `invalid_type`（不再静默按玩家处理）。
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from guguwebui.dependencies.auth import get_current_admin
from guguwebui.services.operation_audit_service import record_operation
from guguwebui.services.player_service import PlayerService
from guguwebui.structures import (
    BusinessException,
    PlayerBanRequest,
    PlayerKickRequest,
    PlayerUnbanRequest,
    WhitelistSetRequest,
)
from guguwebui.structures.envelope import ApiSuccessEnvelope, success

router = APIRouter(tags=["players"])

_PLAYER_TYPES = ("player", "ip")

# 在线统计时间范围（与服务器状态页 RANGE_MAP 一致）
StatsRangeKey = Literal["10m", "30m", "1h", "6h", "12h", "1d", "3d", "7d"]

# service 动作失败返回 {status:"error", code: ...} → HTTP 状态映射
_FAILURE_STATUS: Dict[str, int] = {
    "server_not_running": 400,
    "command_failed": 400,
    "ban_not_found": 404,
    "file_write_failed": 500,
}


def _get_service(request: Request) -> PlayerService:
    return request.app.state.player_service


def _audit(admin: dict, operation_type: str, summary: str, detail: dict | None = None) -> None:
    try:
        record_operation(
            admin,
            operation_type=operation_type,
            summary=summary,
            detail=detail,
        )
    except Exception:
        pass


def _ensure_ok(result: Dict[str, Any], default_message: str) -> None:
    """service 动作结果非 success → 抛统一 BusinessException。"""
    if result.get("status") == "success":
        return
    code = str(result.get("code") or "action_failed")
    status_code = _FAILURE_STATUS.get(code, 400)
    raise BusinessException(
        str(result.get("message") or default_message),
        status_code=status_code,
        code=code,
    )


def _validate_type(raw_type: str) -> str:
    typ = (raw_type or "").strip().lower()
    if typ not in _PLAYER_TYPES:
        raise BusinessException(
            f"Unsupported type: {raw_type}",
            status_code=400,
            code="invalid_type",
        )
    return typ


def _pick(result: Dict[str, Any], keys: tuple) -> Dict[str, Any]:
    return {k: result[k] for k in keys if k in result}


@router.get("/players", response_model=ApiSuccessEnvelope)
async def api_get_players(
    request: Request,
    search: str = "",
    filter: str = "all",
    offset: int = 0,
    limit: int = 50,
    exclude_bots: bool = False,
    _admin: dict = Depends(get_current_admin),
):
    """汇总玩家列表（支持搜索与筛选，exclude_bots 时仅列出真实玩家）"""
    result = await asyncio.to_thread(
        _get_service(request).get_players, search, filter, offset, limit, exclude_bots
    )
    # 分页列表统一 items 键（保留统计/状态扩展字段）
    return JSONResponse(
        success(
            {
                "items": result.get("players", []),
                "total": result.get("total", 0),
                "offset": result.get("offset", 0),
                "limit": result.get("limit", 0),
                "online_count": result.get("online_count", 0),
                "bot_count": result.get("bot_count", 0),
                "server_running": result.get("server_running", False),
            }
        )
    )


@router.get("/players/bots", response_model=ApiSuccessEnvelope)
async def api_get_bots(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """识别出的无IP玩家/假人列表"""
    result = await asyncio.to_thread(_get_service(request).get_bots)
    return JSONResponse(success(result))


@router.get("/players/stats/overview", response_model=ApiSuccessEnvelope)
async def api_get_player_stats_overview(
    request: Request,
    range: StatsRangeKey = Query("1h"),
    exclude_bots: bool = Query(False),
    _admin: dict = Depends(get_current_admin),
):
    """在线情况摘要：当前/平均/峰值在线、活跃玩家、会话数（exclude_bots 排除无IP玩家/假人）"""
    result = await asyncio.to_thread(
        _get_service(request).get_stats_overview, range, exclude_bots
    )
    return JSONResponse(success(result))


@router.get("/players/stats/online-history", response_model=ApiSuccessEnvelope)
async def api_get_player_stats_online_history(
    request: Request,
    range: StatsRangeKey = Query("1h"),
    exclude_bots: bool = Query(False),
    _admin: dict = Depends(get_current_admin),
):
    """在线人数曲线（按分钟分桶，exclude_bots 排除无IP玩家/假人）"""
    result = await asyncio.to_thread(
        _get_service(request).get_stats_online_history, range, exclude_bots
    )
    return JSONResponse(success(result))


@router.get("/players/stats/daily", response_model=ApiSuccessEnvelope)
async def api_get_player_stats_daily(
    request: Request,
    range: StatsRangeKey = Query("7d"),
    exclude_bots: bool = Query(False),
    _admin: dict = Depends(get_current_admin),
):
    """每日活跃统计（唯一玩家/会话数/在线时长）"""
    result = await asyncio.to_thread(
        _get_service(request).get_stats_daily, range, exclude_bots
    )
    return JSONResponse(success(result))


@router.get("/players/stats/players", response_model=ApiSuccessEnvelope)
async def api_get_player_stats_players(
    request: Request,
    exclude_bots: bool = Query(False),
    limit: int = Query(50),
    _admin: dict = Depends(get_current_admin),
):
    """玩家在线时长排行（累计时长 + 会话次数 / 平均每次）"""
    result = await asyncio.to_thread(
        _get_service(request).get_stats_players, exclude_bots, limit
    )
    return JSONResponse(success(result))


@router.get("/players/whitelist", response_model=ApiSuccessEnvelope)
async def api_get_whitelist(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """白名单状态与成员"""
    result = await asyncio.to_thread(_get_service(request).get_whitelist)
    return JSONResponse(success(_pick(result, ("enabled", "members", "server_running"))))


@router.put("/players/whitelist", response_model=ApiSuccessEnvelope)
async def api_set_whitelist(
    request: Request,
    body: WhitelistSetRequest,
    admin: dict = Depends(get_current_admin),
):
    """开关白名单"""
    result = await asyncio.to_thread(_get_service(request).set_whitelist_enabled, body.enabled)
    _ensure_ok(result, "切换白名单失败")
    _audit(admin, "whitelist.set", "开关白名单", {"enabled": body.enabled})
    return JSONResponse(success(message=result.get("message")))


@router.post("/players/whitelist/reload", response_model=ApiSuccessEnvelope)
async def api_reload_whitelist(
    request: Request,
    admin: dict = Depends(get_current_admin),
):
    """重载白名单"""
    result = await asyncio.to_thread(_get_service(request).reload_whitelist)
    _ensure_ok(result, "重载白名单失败")
    _audit(admin, "whitelist.reload", "重载白名单")
    return JSONResponse(success(message=result.get("message")))


@router.put("/players/whitelist/{name}", response_model=ApiSuccessEnvelope)
async def api_whitelist_add(
    request: Request,
    name: str,
    admin: dict = Depends(get_current_admin),
):
    """添加白名单成员（自动触发重载）"""
    result = await asyncio.to_thread(_get_service(request).whitelist_add, name.strip())
    _ensure_ok(result, "添加白名单成员失败")
    _audit(admin, "whitelist.add", "添加白名单成员", {"name": name.strip()})
    return JSONResponse(success(message=result.get("message")))


@router.delete("/players/whitelist/{name}", response_model=ApiSuccessEnvelope)
async def api_whitelist_remove(
    request: Request,
    name: str,
    admin: dict = Depends(get_current_admin),
):
    """移除白名单成员（自动触发重载）"""
    result = await asyncio.to_thread(_get_service(request).whitelist_remove, name.strip())
    _ensure_ok(result, "移除白名单成员失败")
    _audit(admin, "whitelist.remove", "移除白名单成员", {"name": name.strip()})
    return JSONResponse(success(message=result.get("message")))


@router.get("/players/ops", response_model=ApiSuccessEnvelope)
async def api_get_ops(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """OP 列表"""
    result = await asyncio.to_thread(_get_service(request).get_ops)
    return JSONResponse(success(_pick(result, ("ops", "server_running"))))


@router.put("/players/{name}/op", response_model=ApiSuccessEnvelope)
async def api_op_player(
    request: Request,
    name: str,
    admin: dict = Depends(get_current_admin),
):
    """设为 OP"""
    result = await asyncio.to_thread(_get_service(request).op_player, name.strip())
    _ensure_ok(result, "设置 OP 失败")
    _audit(admin, "player.op", "设为 OP", {"name": name.strip()})
    return JSONResponse(success(message=result.get("message")))


@router.delete("/players/{name}/op", response_model=ApiSuccessEnvelope)
async def api_deop_player(
    request: Request,
    name: str,
    admin: dict = Depends(get_current_admin),
):
    """取消 OP"""
    result = await asyncio.to_thread(_get_service(request).deop_player, name.strip())
    _ensure_ok(result, "取消 OP 失败")
    _audit(admin, "player.deop", "取消 OP", {"name": name.strip()})
    return JSONResponse(success(message=result.get("message")))


@router.get("/players/bans", response_model=ApiSuccessEnvelope)
async def api_get_bans(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """封禁列表（玩家与 IP）"""
    result = await asyncio.to_thread(_get_service(request).get_bans)
    return JSONResponse(success(_pick(result, ("players", "ips", "server_running"))))


@router.post("/players/{target}/ban", response_model=ApiSuccessEnvelope)
async def api_ban(
    request: Request,
    target: str,
    body: PlayerBanRequest,
    admin: dict = Depends(get_current_admin),
):
    """封禁玩家 / IP（可填理由）"""
    typ = _validate_type(body.type)
    target = target.strip()
    reason = (body.reason or "").strip()
    if typ == "ip":
        result = await asyncio.to_thread(_get_service(request).ban_ip, target, reason)
    else:
        result = await asyncio.to_thread(_get_service(request).ban_player, target, reason)
    _ensure_ok(result, "封禁失败")
    _audit(
        admin,
        "player.ban_ip" if typ == "ip" else "player.ban",
        "封禁 IP" if typ == "ip" else "封禁玩家",
        {"target": target, "reason": reason, "needs_restart": result.get("needs_restart", False)},
    )
    return JSONResponse(success(message=result.get("message")))


@router.post("/players/{target}/unban", response_model=ApiSuccessEnvelope)
async def api_unban(
    request: Request,
    target: str,
    body: PlayerUnbanRequest,
    admin: dict = Depends(get_current_admin),
):
    """解封玩家 / IP（通过修改文件，重启后生效）"""
    typ = _validate_type(body.type)
    target = target.strip()
    if typ == "ip":
        result = await asyncio.to_thread(_get_service(request).unban_ip, target)
    else:
        result = await asyncio.to_thread(_get_service(request).unban_player, target)
    _ensure_ok(result, "解封失败")
    _audit(
        admin,
        "player.unban_ip" if typ == "ip" else "player.unban",
        "解封 IP" if typ == "ip" else "解封玩家",
        {"target": target, "needs_restart": True},
    )
    return JSONResponse(success(message=result.get("message")))


@router.post("/players/{name}/kick", response_model=ApiSuccessEnvelope)
async def api_kick(
    request: Request,
    name: str,
    body: PlayerKickRequest,
    admin: dict = Depends(get_current_admin),
):
    """踢出玩家"""
    name = name.strip()
    reason = (body.reason or "").strip()
    result = await asyncio.to_thread(_get_service(request).kick_player, name, reason)
    _ensure_ok(result, "踢出玩家失败")
    _audit(admin, "player.kick", "踢出玩家", {"name": name, "reason": reason})
    return JSONResponse(success(message=result.get("message")))
