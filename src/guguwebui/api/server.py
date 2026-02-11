"""
服务器管理相关的API函数
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from guguwebui.structures import ServerControl


async def get_server_status(request: Request) -> JSONResponse:
    """获取服务器状态"""
    server_service = request.app.state.server_service
    result = await server_service.get_server_status()
    return JSONResponse(result)


async def control_server(request: Request, control_info: ServerControl) -> JSONResponse:
    """控制Minecraft服务器"""
    server_service = request.app.state.server_service
    success = server_service.execute_action(control_info.action)
    
    if not success:
        return JSONResponse(
            {"status": "error", "message": f"无效的操作: {control_info.action}"},
            status_code=400
        )

    messages = {
        "start": "服务器启动命令已发送",
        "stop": "服务器停止命令已发送",
        "restart": "服务器重启命令已发送"
    }
    return JSONResponse({
        "status": "success",
        "message": messages.get(control_info.action, "命令已发送")
    })


async def get_server_logs(request: Request, max_lines: int = 100) -> JSONResponse:
    """获取服务器日志"""
    server_service = request.app.state.server_service
    result = server_service.get_logs(max_lines)
    
    if result is None:
        return JSONResponse({"status": "error", "message": "LogWatcher未初始化"}, status_code=500)
        
    return JSONResponse({
        "status": "success",
        **result
    })


async def get_new_logs(request: Request, last_counter: int = 0, max_lines: int = 100) -> JSONResponse:
    """获取新增日志"""
    server_service = request.app.state.server_service
    result = server_service.get_new_logs(last_counter, max_lines)
    
    if result is None:
        return JSONResponse({"status": "error", "message": "LogWatcher未初始化"}, status_code=500)
        
    return JSONResponse({
        "status": "success",
        **result
    })


async def get_rcon_status(request: Request) -> JSONResponse:
    """获取RCON连接状态"""
    server_service = request.app.state.server_service
    result = await server_service.get_rcon_status()
    return JSONResponse(result)


async def get_command_suggestions(request: Request, input: str = "") -> JSONResponse:
    """获取MCDR命令补全建议"""
    server_service = request.app.state.server_service
    suggestions = server_service.get_command_suggestions(input)
    return JSONResponse({
        "status": "success",
        "suggestions": suggestions,
        "input": input
    })


async def send_command(request: Request) -> JSONResponse:
    """发送命令到MCDR终端"""
    server_service = request.app.state.server_service
    data = await request.json()
    command = data.get("command", "")
    
    result = server_service.send_command(command)
    status_code = 200 if result["status"] == "success" else 400
    if result.get("message") == "该命令已被禁止执行":
        status_code = 403
        
    return JSONResponse(result, status_code=status_code)
