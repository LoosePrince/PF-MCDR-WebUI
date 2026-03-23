from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from guguwebui.dependencies.auth import get_current_admin, get_current_user
from guguwebui.services.chat_service import ChatService

router = APIRouter()


@router.post("/chat/generate_code")
async def chat_generate_code(request: Request):
    """生成聊天页验证码"""
    code, expire_minutes = request.app.state.chat_service.generate_verification_code()
    return JSONResponse(
        {"status": "success", "code": code, "expire_minutes": expire_minutes}
    )


@router.post("/chat/check_verification")
async def chat_check_verification(request: Request):
    """检查验证码验证状态"""
    data = await request.json()
    chat_service: ChatService = request.app.state.chat_service
    result = chat_service.check_verification_status(data.get("code", ""))
    return JSONResponse(
        result, status_code=(200 if result.get("status") != "error" else 400)
    )


@router.post("/chat/set_password")
async def chat_set_password(request: Request):
    """设置聊天页用户密码"""
    data = await request.json()
    chat_service: ChatService = request.app.state.chat_service
    result = await chat_service.set_user_password(data.get("code", ""), data.get("password", ""))
    return JSONResponse(
        result, status_code=(200 if result.get("status") != "error" else 400)
    )


@router.post("/chat/login")
async def chat_login(request: Request):
    """聊天页用户登录"""
    data, client_ip = await request.json(), (
        request.client.host if request.client else "unknown"
    )
    chat_service: ChatService = request.app.state.chat_service
    result = await chat_service.login(
        data.get("player_id", ""), data.get("password", ""), client_ip
    )
    status_code = 400 if result.get("status") == "error" else 200
    if status_code == 400 and "IP已达上限" in result.get("message", ""):
        status_code = 429
    return JSONResponse(result, status_code=status_code)


@router.post("/chat/check_session")
async def chat_check_session(request: Request):
    """检查聊天页会话状态"""
    data = await request.json()
    chat_service: ChatService = request.app.state.chat_service
    result = await chat_service.check_session(data.get("session_id", ""))
    return JSONResponse(
        result, status_code=(200 if result.get("status") != "error" else 400)
    )


@router.post("/chat/logout")
async def chat_logout(request: Request):
    """聊天页用户退出登录"""
    data = await request.json()
    chat_service: ChatService = request.app.state.chat_service
    result = chat_service.logout(data.get("session_id", ""))
    return JSONResponse(
        result, status_code=(200 if result.get("status") != "error" else 400)
    )


@router.post("/chat/get_messages")
async def get_chat_messages(request: Request):
    """获取聊天消息"""
    data, chat_service = await request.json(), request.app.state.chat_service
    result = await chat_service.get_messages(
        limit=data.get("limit", 50),
        offset=data.get("offset", 0),
        after_id=data.get("after_id"),
        before_id=data.get("before_id"),
    )
    return JSONResponse({"status": "success", **result})


@router.post("/chat/get_new_messages")
async def get_new_chat_messages(request: Request):
    """获取新消息（基于最后消息ID）"""
    data, chat_service = await request.json(), request.app.state.chat_service
    result = await chat_service.get_new_messages(
        after_id=data.get("after_id", 0), player_id_heartbeat=data.get("player_id")
    )
    return JSONResponse({"status": "success", **result})


@router.post("/chat/clear_messages")
async def chat_clear_messages(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """清空聊天消息"""
    return JSONResponse(
        {"status": "success", **request.app.state.chat_service.clear_messages()}
    )


@router.post("/chat/send_message")
async def send_chat_message(request: Request, user: dict = Depends(get_current_user)):
    """发送聊天消息到游戏"""
    data = await request.json()
    player_id = data.get("player_id", "")
    chat_service: ChatService = request.app.state.chat_service
    result = await chat_service.send_message(
        data.get("message", "").strip(),
        player_id,
        data.get("session_id", ""),
        (user and user.get("username") == player_id),
    )
    return JSONResponse(
        result, status_code=chat_service.get_status_code_for_result(result)
    )

