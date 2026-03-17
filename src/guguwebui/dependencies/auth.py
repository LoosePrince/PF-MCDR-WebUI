import ipaddress

from fastapi import Depends, HTTPException, Request, status

from guguwebui.constant import user_db

async def get_current_user(request: Request):
    """获取当前登录用户，如果未登录则抛出 401 异常"""
    # 1) 常规 cookie 登录（保持现有逻辑）
    token = request.cookies.get("token")
    if token and token in user_db.get("token", {}) and request.session.get("logged_in"):
        return {"username": request.session.get("username"), "token": token}

    # 2) 子服模式：允许主服通过 X-Panel-Token 访问（不依赖 session/cookie）
    config_service = getattr(request.app.state, "config_service", None)
    if config_service is not None:
        server_config = config_service.get_config()
        if server_config.get("panel_role", "master") == "slave":
            panel_token = request.headers.get("X-Panel-Token") or ""
            panel_token = panel_token.strip()
            if panel_token:
                panel_master = server_config.get("panel_master") or {}
                allowed_tokens = panel_master.get("allowed_tokens") or []
                allowed_master_ips = panel_master.get("allowed_master_ips") or []

                # 可选：限制主服来源 IP
                if allowed_master_ips:
                    client_ip = request.client.host if request.client else ""
                    if not _ip_allowed(client_ip, allowed_master_ips):
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Panel token source not allowed",
                        )

                if _panel_token_enabled(panel_token, allowed_tokens):
                    return {"username": "__panel__", "token": panel_token, "auth_via": "panel_token"}

    # token 不存在或 session 无效：清理 session（避免前端误以为已登录）
    if token and token not in user_db.get("token", {}):
        request.session.clear()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="User not logged in",
    )


def _panel_token_enabled(token: str, allowed_tokens: list) -> bool:
    for item in allowed_tokens or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("token", "")).strip() != token:
            continue
        return bool(item.get("enabled", False))
    return False


def _ip_allowed(client_ip: str, allowed_master_ips: list) -> bool:
    """支持精确 IP 或 CIDR 段。"""
    if not client_ip:
        return False
    try:
        ip_obj = ipaddress.ip_address(client_ip)
    except ValueError:
        return False

    for raw in allowed_master_ips or []:
        if not isinstance(raw, str):
            continue
        raw = raw.strip()
        if not raw:
            continue
        try:
            if "/" in raw:
                net = ipaddress.ip_network(raw, strict=False)
                if ip_obj in net:
                    return True
            else:
                if ip_obj == ipaddress.ip_address(raw):
                    return True
        except ValueError:
            continue
    return False

async def get_current_admin(request: Request, current_user: dict = Depends(get_current_user)):
    """获取当前管理员用户，如果不是管理员则抛出 403 异常"""
    # 子服模式的面板 token：权限由主服控制，子服只校验 token 有效性
    if current_user.get("auth_via") == "panel_token":
        return current_user

    config_service = request.app.state.config_service
    server_config = config_service.get_config()
    
    super_admin_account = str(server_config.get("super_admin_account"))
    disable_other_admin = server_config.get("disable_other_admin", False)
    
    username = current_user.get("username")
    
    is_admin = True
    if disable_other_admin and str(username) != super_admin_account:
        is_admin = False
    
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
            
    return current_user
