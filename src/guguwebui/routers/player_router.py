"""玩家管理 API（仅管理员）：玩家列表、假人、白名单、OP、封禁、踢出。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from guguwebui.dependencies.auth import get_current_admin
from guguwebui.services.operation_audit_service import record_operation
from guguwebui.services.player_service import PlayerService
from guguwebui.structures import (
    KickRequest,
    PlayerActionRequest,
    PlayerNameRequest,
    WhitelistSetRequest,
)

router = APIRouter(tags=["players"])


def _get_service(request: Request) -> PlayerService:
    return request.app.state.player_service


def _audit(admin: dict, operation_type: str, summary: str, detail: dict = None) -> None:
    try:
        record_operation(
            admin,
            operation_type=operation_type,
            summary=summary,
            detail=detail,
        )
    except Exception:
        pass


@router.get("/players")
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
    service = _get_service(request)
    result = await asyncio.to_thread(
        service.get_players, search, filter, offset, limit, exclude_bots
    )
    return JSONResponse({"status": "success", **result})


@router.get("/players/bots")
async def api_get_bots(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """识别出的假人列表"""
    service = _get_service(request)
    result = await asyncio.to_thread(service.get_bots)
    return JSONResponse({"status": "success", **result})


@router.get("/players/whitelist")
async def api_get_whitelist(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """白名单状态与成员"""
    service = _get_service(request)
    result = await asyncio.to_thread(service.get_whitelist)
    return JSONResponse(result)


@router.post("/players/whitelist/set")
async def api_set_whitelist(
    request: Request,
    body: WhitelistSetRequest,
    admin: dict = Depends(get_current_admin),
):
    """开关白名单"""
    service = _get_service(request)
    result = await asyncio.to_thread(service.set_whitelist_enabled, body.enabled)
    if result.get("status") == "success":
        _audit(
            admin,
            "whitelist.set",
            "开关白名单",
            {"enabled": body.enabled},
        )
    status_code = 200 if result.get("status") == "success" else 400
    return JSONResponse(result, status_code=status_code)


@router.post("/players/whitelist/reload")
async def api_reload_whitelist(
    request: Request,
    admin: dict = Depends(get_current_admin),
):
    """重载白名单"""
    service = _get_service(request)
    result = await asyncio.to_thread(service.reload_whitelist)
    if result.get("status") == "success":
        _audit(admin, "whitelist.reload", "重载白名单")
    status_code = 200 if result.get("status") == "success" else 400
    return JSONResponse(result, status_code=status_code)


@router.post("/players/whitelist/add")
async def api_whitelist_add(
    request: Request,
    body: PlayerNameRequest,
    admin: dict = Depends(get_current_admin),
):
    """添加白名单成员（自动触发重载）"""
    service = _get_service(request)
    result = await asyncio.to_thread(service.whitelist_add, body.name.strip())
    if result.get("status") == "success":
        _audit(
            admin,
            "whitelist.add",
            "添加白名单成员",
            {"name": body.name.strip()},
        )
    status_code = 200 if result.get("status") == "success" else 400
    return JSONResponse(result, status_code=status_code)


@router.post("/players/whitelist/remove")
async def api_whitelist_remove(
    request: Request,
    body: PlayerNameRequest,
    admin: dict = Depends(get_current_admin),
):
    """移除白名单成员（自动触发重载）"""
    service = _get_service(request)
    result = await asyncio.to_thread(service.whitelist_remove, body.name.strip())
    if result.get("status") == "success":
        _audit(
            admin,
            "whitelist.remove",
            "移除白名单成员",
            {"name": body.name.strip()},
        )
    status_code = 200 if result.get("status") == "success" else 400
    return JSONResponse(result, status_code=status_code)


@router.get("/players/ops")
async def api_get_ops(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """OP 列表"""
    service = _get_service(request)
    result = await asyncio.to_thread(service.get_ops)
    return JSONResponse(result)


@router.post("/players/op")
async def api_op_player(
    request: Request,
    body: PlayerNameRequest,
    admin: dict = Depends(get_current_admin),
):
    """设为 OP"""
    service = _get_service(request)
    result = await asyncio.to_thread(service.op_player, body.name.strip())
    if result.get("status") == "success":
        _audit(
            admin,
            "player.op",
            "设为 OP",
            {"name": body.name.strip()},
        )
    status_code = 200 if result.get("status") == "success" else 400
    return JSONResponse(result, status_code=status_code)


@router.post("/players/deop")
async def api_deop_player(
    request: Request,
    body: PlayerNameRequest,
    admin: dict = Depends(get_current_admin),
):
    """取消 OP"""
    service = _get_service(request)
    result = await asyncio.to_thread(service.deop_player, body.name.strip())
    if result.get("status") == "success":
        _audit(
            admin,
            "player.deop",
            "取消 OP",
            {"name": body.name.strip()},
        )
    status_code = 200 if result.get("status") == "success" else 400
    return JSONResponse(result, status_code=status_code)


@router.get("/players/bans")
async def api_get_bans(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """封禁列表（玩家与 IP）"""
    service = _get_service(request)
    result = await asyncio.to_thread(service.get_bans)
    return JSONResponse(result)


@router.post("/players/ban")
async def api_ban(
    request: Request,
    body: PlayerActionRequest,
    admin: dict = Depends(get_current_admin),
):
    """封禁玩家 / IP（可填理由）"""
    service = _get_service(request)
    target = body.target.strip()
    reason = (body.reason or "").strip()
    if body.type == "ip":
        result = await asyncio.to_thread(service.ban_ip, target, reason)
    else:
        result = await asyncio.to_thread(service.ban_player, target, reason)
    if result.get("status") == "success":
        _audit(
            admin,
            "player.ban_ip" if body.type == "ip" else "player.ban",
            "封禁 IP" if body.type == "ip" else "封禁玩家",
            {"target": target, "reason": reason, "needs_restart": result.get("needs_restart", False)},
        )
    status_code = 200 if result.get("status") == "success" else 400
    return JSONResponse(result, status_code=status_code)


@router.post("/players/unban")
async def api_unban(
    request: Request,
    body: PlayerActionRequest,
    admin: dict = Depends(get_current_admin),
):
    """解封玩家 / IP（通过修改文件，重启后生效）"""
    service = _get_service(request)
    target = body.target.strip()
    if body.type == "ip":
        result = await asyncio.to_thread(service.unban_ip, target)
    else:
        result = await asyncio.to_thread(service.unban_player, target)
    if result.get("status") == "success":
        _audit(
            admin,
            "player.unban_ip" if body.type == "ip" else "player.unban",
            "解封 IP" if body.type == "ip" else "解封玩家",
            {"target": target, "needs_restart": True},
        )
    status_code = 200 if result.get("status") == "success" else 400
    return JSONResponse(result, status_code=status_code)


@router.post("/players/kick")
async def api_kick(
    request: Request,
    body: KickRequest,
    admin: dict = Depends(get_current_admin),
):
    """踢出玩家"""
    service = _get_service(request)
    result = await asyncio.to_thread(
        service.kick_player, body.name.strip(), (body.reason or "").strip()
    )
    if result.get("status") == "success":
        _audit(
            admin,
            "player.kick",
            "踢出玩家",
            {"name": body.name.strip(), "reason": (body.reason or "").strip()},
        )
    status_code = 200 if result.get("status") == "success" else 400
    return JSONResponse(result, status_code=status_code)
