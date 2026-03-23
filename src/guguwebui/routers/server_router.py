from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from guguwebui.dependencies.auth import get_current_admin, get_current_user
from guguwebui.services.server_service import ServerService
from guguwebui.structures import ServerControl

router = APIRouter()


@router.get("/get_server_status")
async def api_get_server_status(
    request: Request,
    _user: dict = Depends(get_current_user),
):
    """获取服务器状态"""
    return JSONResponse(
        {
            "status": "success",
            **await request.app.state.server_service.get_server_status(),
        }
    )


@router.post("/control_server")
async def api_control_server(
    request: Request,
    control_info: ServerControl,
    _admin: dict = Depends(get_current_admin),
):
    """控制Minecraft服务器"""
    server_service: ServerService = request.app.state.server_service
    result = server_service.control_server(control_info.action)
    status_code = 200 if result.get("status") == "success" else 400
    return JSONResponse(result, status_code=status_code)


@router.get("/server_logs")
async def api_get_server_logs(
    request: Request,
    start_line: int = 0,
    max_lines: int = 100,
    _user: dict = Depends(get_current_user),
):
    """获取服务器日志"""
    return JSONResponse(
        {"status": "success", **request.app.state.server_service.get_logs(max_lines)}
    )


@router.get("/new_logs")
async def api_get_new_logs(
    request: Request,
    last_counter: int = 0,
    max_lines: int = 100,
    _user: dict = Depends(get_current_user),
):
    """获取新增日志"""
    return JSONResponse(
        {
            "status": "success",
            **request.app.state.server_service.get_new_logs(last_counter, max_lines),
        }
    )


@router.get("/command_suggestions")
async def api_get_command_suggestions(
    request: Request,
    input: str = "",
    _user: dict = Depends(get_current_user),
):
    """获取MCDR命令补全建议"""
    suggestions = await request.app.state.server_service.get_command_suggestions(input)
    return JSONResponse(
        {"status": "success", "suggestions": suggestions, "input": input}
    )


@router.post("/send_command")
async def api_send_command(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """发送命令到MCDR终端"""
    data = await request.json()
    server_service: ServerService = request.app.state.server_service
    result = await server_service.send_command(data.get("command", ""))
    status_code = (
        403
        if result.get("message") == "该命令已被禁止执行"
        else (200 if result.get("status") == "success" else 400)
    )
    return JSONResponse(result, status_code=status_code)


@router.get("/get_rcon_status")
async def api_get_rcon_status(
    request: Request,
    _user: dict = Depends(get_current_user),
):
    """获取RCON连接状态"""
    return JSONResponse(await request.app.state.server_service.get_rcon_status())

