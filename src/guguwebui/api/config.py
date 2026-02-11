"""
配置管理相关的API函数
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from guguwebui.structures import ConfigData, SaveConfig


async def list_config_files(request: Request, plugin_id: str) -> JSONResponse:
    """列出插件的配置文件"""
    config_service = request.app.state.config_service
    files_info = config_service.list_config_files(plugin_id)
    return JSONResponse({"files": files_info})


async def get_web_config(request: Request) -> JSONResponse:
    """获取Web配置"""
    config_service = request.app.state.config_service
    result = await config_service.get_web_config()
    return JSONResponse(result)


async def save_web_config(request: Request, config: SaveConfig) -> JSONResponse:
    """保存Web配置"""
    config_service = request.app.state.config_service
    result = config_service.save_web_config(config)
    status_code = 200 if result["status"] == "success" else 500
    return JSONResponse(result, status_code=status_code)


async def load_config(request: Request, path: str, translation: bool = False, type: str = "auto") -> JSONResponse:
    """加载配置文件"""
    config_service = request.app.state.config_service
    result = config_service.load_config(path, translation, type)
    
    if isinstance(result, dict) and "status" in result and result["status"] == "error":
        return JSONResponse(result, status_code=result.get("code", 500))
        
    return JSONResponse(result)


async def save_config(request: Request, config_data: ConfigData) -> JSONResponse:
    """保存配置文件"""
    config_service = request.app.state.config_service
    result = config_service.save_config(config_data.file_path, config_data.config_data)
    status_code = result.get("code", 200) if result["status"] == "error" else 200
    return JSONResponse(result, status_code=status_code)


async def setup_rcon_config(request: Request) -> JSONResponse:
    """一键启用RCON配置"""
    config_service = request.app.state.config_service
    result = config_service.setup_rcon()
    status_code = 200 if result["status"] == "success" else 500
    return JSONResponse(result, status_code=status_code)
