import datetime
import json
import secrets
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse

from guguwebui.dependencies.auth import get_current_admin, get_current_user
from guguwebui.panel_merge.state import get_pairing_state, now_utc
from guguwebui.services.config_service import ConfigService


router = APIRouter()


@router.get("/servers")
async def api_list_servers(request: Request, user: dict = Depends(get_current_user)):
    """获取可用的服务器列表（主服 + 子服）"""
    config_service: ConfigService = request.app.state.config_service
    cfg = config_service.get_config()
    servers: List[Dict[str, Any]] = [
        {"id": "local", "name": "local", "enabled": True, "isLocal": True}
    ]
    for s in (cfg.get("panel_slaves") or []):
        if not isinstance(s, dict):
            continue
        servers.append(
            {
                "id": str(s.get("id", "")).strip(),
                "name": s.get("name") or s.get("id") or "",
                "enabled": bool(s.get("enabled", True)),
                "isLocal": False,
            }
        )
    servers = [x for x in servers if x.get("id")]
    return JSONResponse({"status": "success", "servers": servers})


@router.get("/panel_merge_config")
async def api_get_panel_merge_config(
    request: Request, admin: dict = Depends(get_current_admin)
):
    config_service: ConfigService = request.app.state.config_service
    cfg = config_service.get_config()
    return JSONResponse(
        {
            "status": "success",
            "panel_role": cfg.get("panel_role", "master"),
            "panel_slaves": cfg.get("panel_slaves") or [],
            "panel_master": cfg.get("panel_master")
            or {"allowed_tokens": [], "allowed_master_ips": []},
        }
    )


@router.post("/panel_merge_config")
async def api_save_panel_merge_config(
    request: Request, admin: dict = Depends(get_current_admin)
):
    body = await request.json()
    panel_role = body.get("panel_role", "master")
    panel_slaves = body.get("panel_slaves") or []
    panel_master = body.get("panel_master") or {}

    # 最小校验与归一化
    panel_role = panel_role if panel_role in {"master", "slave"} else "master"
    if not isinstance(panel_slaves, list):
        panel_slaves = []
    if not isinstance(panel_master, dict):
        panel_master = {"allowed_tokens": [], "allowed_master_ips": []}

    config_service: ConfigService = request.app.state.config_service
    cfg = config_service.get_config()
    cfg["panel_role"] = panel_role
    cfg["panel_slaves"] = panel_slaves
    cfg["panel_master"] = panel_master

    try:
        config_dir = request.app.state.server_interface.get_data_folder()
        Path(config_dir).mkdir(parents=True, exist_ok=True)
        config_path = Path(config_dir) / "config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"保存配置失败: {str(e)}"},
            status_code=500,
        )

    return JSONResponse({"status": "success", "message": "配置已保存"})


# ============================================================#
# Pairing APIs (Quick Mode)


@router.post("/pairing/enable")
async def api_pairing_enable(request: Request, admin: dict = Depends(get_current_admin)):
    cfg = request.app.state.config_service.get_config()
    if cfg.get("panel_role", "master") != "slave":
        return JSONResponse(
            {"status": "error", "message": "仅子服模式可开启接受连接"},
            status_code=400,
        )
    st = get_pairing_state(request.app)
    expires = now_utc() + datetime.timedelta(minutes=5)
    st["enabled_until"] = expires
    return JSONResponse({"status": "success", "expires_at": expires.isoformat()})


@router.post("/pairing/disable")
async def api_pairing_disable(request: Request, admin: dict = Depends(get_current_admin)):
    cfg = request.app.state.config_service.get_config()
    if cfg.get("panel_role", "master") != "slave":
        return JSONResponse(
            {"status": "error", "message": "仅子服模式可停止接受连接"},
            status_code=400,
        )
    st = get_pairing_state(request.app)
    st["enabled_until"] = None
    st["pending"] = {}
    return JSONResponse({"status": "success"})


@router.post("/pairing/request")
async def api_pairing_request(request: Request):
    """
    主服 -> 子服：发起连接请求
    - 不需要登录（仅在 enable 窗口内有效）
    - 收到第一个请求后关闭窗口
    """
    cfg = request.app.state.config_service.get_config()
    if cfg.get("panel_role", "master") != "slave":
        return JSONResponse(
            {"status": "error", "message": "仅子服模式可接受连接请求"},
            status_code=400,
        )

    st = get_pairing_state(request.app)
    enabled_until = st.get("enabled_until")
    if not enabled_until or now_utc() > enabled_until:
        return JSONResponse(
            {"status": "error", "message": "当前未开启接受连接或已超时"},
            status_code=403,
        )

    # 收到第一个请求后关闭窗口
    st["enabled_until"] = None

    body = await request.json()
    master_name = str(body.get("master_name", "")).strip()
    client_ip = request.client.host if request.client else ""

    request_id = uuid.uuid4().hex
    st["pending"][request_id] = {
        "ip": client_ip,
        "master_name": master_name,
        "created_at": now_utc().isoformat(),
    }
    return JSONResponse({"status": "pending", "request_id": request_id})


@router.get("/pairing/pending")
async def api_pairing_pending(request: Request, admin: dict = Depends(get_current_admin)):
    st = get_pairing_state(request.app)
    pending = st.get("pending") or {}
    items = []
    for rid, rec in pending.items():
        if not isinstance(rec, dict):
            continue
        items.append(
            {
                "request_id": rid,
                "ip": rec.get("ip") or "",
                "master_name": rec.get("master_name") or "",
            }
        )
    return JSONResponse({"status": "success", "pending": items})


@router.post("/pairing/deny")
async def api_pairing_deny(request: Request, admin: dict = Depends(get_current_admin)):
    st = get_pairing_state(request.app)
    body = await request.json()
    request_id = str(body.get("request_id", "")).strip()
    st.get("pending", {}).pop(request_id, None)
    st.get("results", {})[request_id] = {"status": "denied"}
    return JSONResponse({"status": "success"})


@router.post("/pairing/accept")
async def api_pairing_accept(request: Request, admin: dict = Depends(get_current_admin)):
    cfg = request.app.state.config_service.get_config()
    if cfg.get("panel_role", "master") != "slave":
        return JSONResponse(
            {"status": "error", "message": "仅子服模式可接受连接"},
            status_code=400,
        )
    st = get_pairing_state(request.app)
    body = await request.json()
    request_id = str(body.get("request_id", "")).strip()
    rec = (st.get("pending") or {}).pop(request_id, None)
    if not rec:
        return JSONResponse({"status": "error", "message": "Request not found"}, status_code=404)

    token = secrets.token_urlsafe(24)
    st.get("results", {})[request_id] = {"status": "accepted", "token": token}

    # 写入子服配置：panel_master.allowed_tokens 追加
    panel_master = cfg.get("panel_master") or {"allowed_tokens": [], "allowed_master_ips": []}
    allowed = panel_master.get("allowed_tokens") or []
    if not isinstance(allowed, list):
        allowed = []
    allowed.append({"name": rec.get("master_name") or "master", "token": token, "enabled": True})
    panel_master["allowed_tokens"] = allowed
    cfg["panel_master"] = panel_master

    try:
        config_dir = request.app.state.server_interface.get_data_folder()
        Path(config_dir).mkdir(parents=True, exist_ok=True)
        config_path = Path(config_dir) / "config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"保存子服配置失败: {str(e)}"},
            status_code=500,
        )

    return JSONResponse({"status": "success"})


@router.get("/pairing/status")
async def api_pairing_status(request: Request, request_id: str):
    st = get_pairing_state(request.app)
    result = (st.get("results") or {}).get(request_id)
    if not result:
        return JSONResponse({"status": "pending"})
    return JSONResponse(result)


@router.post("/pairing/connect_request")
async def api_pairing_connect_request(
    request: Request, admin: dict = Depends(get_current_admin)
):
    """
    主服：对外提供“连接子服”的统一入口
    - 由主服本地调用（不代理）
    - 发起对目标子服 /api/pairing/request 的请求
    """
    cfg = request.app.state.config_service.get_config()
    if cfg.get("panel_role", "master") != "master":
        return JSONResponse(
            {"status": "error", "message": "仅主服模式可发起连接"},
            status_code=400,
        )

    body = await request.json()
    slave_name = str(body.get("slave_name", "")).strip()
    base_url = str(body.get("base_url", "")).strip().rstrip("/")
    if not slave_name or not base_url:
        return JSONResponse({"status": "error", "message": "Missing slave_name/base_url"}, status_code=400)

    session = getattr(request.app.state, "http_session", None)
    if session is None:
        return JSONResponse({"status": "error", "message": "HTTP session not ready"}, status_code=500)

    connect_id = uuid.uuid4().hex
    async with session.post(
        f"{base_url}/api/pairing/request",
        json={"master_name": "master"},
        ssl=True,
    ) as resp:
        data = await resp.json(content_type=None)
        if resp.status >= 400:
            return JSONResponse({"status": "error", "message": data.get("message") if isinstance(data, dict) else "request failed"}, status_code=400)
        if isinstance(data, dict) and data.get("status") == "pending":
            request_id = str(data.get("request_id", "")).strip()
            st = get_pairing_state(request.app)
            st.get("connects", {})[connect_id] = {
                "base_url": base_url,
                "request_id": request_id,
                "slave_name": slave_name,
                "created_at": now_utc().isoformat(),
            }
            return JSONResponse({"status": "pending", "connect_id": connect_id})

    return JSONResponse({"status": "error", "message": "request failed"}, status_code=400)


@router.get("/pairing/connect_status")
async def api_pairing_connect_status(
    request: Request, connect_id: str, admin: dict = Depends(get_current_admin)
):
    st = get_pairing_state(request.app)
    rec = (st.get("connects") or {}).get(connect_id)
    if not rec:
        return JSONResponse({"status": "error", "message": "connect_id not found"}, status_code=404)

    base_url = str(rec.get("base_url", "")).rstrip("/")
    request_id = str(rec.get("request_id", "")).strip()
    if not base_url or not request_id:
        return JSONResponse({"status": "error", "message": "invalid connect record"}, status_code=500)

    session = getattr(request.app.state, "http_session", None)
    if session is None:
        return JSONResponse({"status": "error", "message": "HTTP session not ready"}, status_code=500)

    async with session.get(
        f"{base_url}/api/pairing/status", params={"request_id": request_id}, ssl=True
    ) as resp:
        data = await resp.json(content_type=None)

    if not isinstance(data, dict):
        return JSONResponse({"status": "pending"})

    if data.get("status") == "accepted":
        token = str(data.get("token", "")).strip()
        if not token:
            return JSONResponse({"status": "error", "message": "missing token"}, status_code=500)

        # 保存到主服配置：panel_slaves 追加/更新
        config_service: ConfigService = request.app.state.config_service
        cfg = config_service.get_config()
        slaves = cfg.get("panel_slaves") or []
        if not isinstance(slaves, list):
            slaves = []

        # 生成 id：基于名称，保证唯一（与旧实现一致）
        base_id = (
            "".join([c.lower() if c.isalnum() else "_" for c in str(rec.get("slave_name", ""))])
            .strip("_")
            or "slave"
        )
        existing_ids = {str(s.get("id")) for s in slaves if isinstance(s, dict)}
        sid = base_id
        i = 1
        while sid in existing_ids:
            i += 1
            sid = f"{base_id}_{i}"
        slaves.append(
            {
                "id": sid,
                "name": rec.get("slave_name") or sid,
                "base_url": base_url,
                "token": token,
                "enabled": True,
                "verify_tls": True,
            }
        )
        cfg["panel_slaves"] = slaves

        try:
            config_dir = request.app.state.server_interface.get_data_folder()
            Path(config_dir).mkdir(parents=True, exist_ok=True)
            config_path = Path(config_dir) / "config.json"
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=4)
        except Exception as e:
            return JSONResponse(
                {"status": "error", "message": f"保存主服配置失败: {str(e)}"},
                status_code=500,
            )

        st.get("connects", {}).pop(connect_id, None)
        return JSONResponse(
            {
                "status": "accepted",
                "server": {"id": sid, "name": rec["slave_name"], "base_url": base_url},
            }
        )

    if data.get("status") == "denied":
        st.get("connects", {}).pop(connect_id, None)
        return JSONResponse({"status": "denied"})

    return JSONResponse({"status": "pending"})

