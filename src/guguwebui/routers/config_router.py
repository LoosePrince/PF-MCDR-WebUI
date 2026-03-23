from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from guguwebui.dependencies.auth import get_current_admin, get_current_user
from guguwebui.services.config_service import ConfigService
from guguwebui.structures import ConfigData, SaveContent, SaveConfig

router = APIRouter()


@router.get("/config/icp-records")
async def api_get_icp_records(request: Request):
    """获取ICP备案信息"""
    state = request.app.state
    return JSONResponse(state.file_service.get_icp_records(state.config_service))


@router.get("/get_web_config")
async def api_get_web_config(
    request: Request,
    _user: dict = Depends(get_current_user),
):
    """获取Web配置"""
    return JSONResponse(await request.app.state.config_service.get_web_config())


@router.post("/save_web_config")
async def api_save_web_config(
    request: Request,
    config: SaveConfig,
    _admin: dict = Depends(get_current_admin),
):
    """保存Web配置"""
    return JSONResponse(request.app.state.config_service.save_web_config(config))


@router.get("/load_config")
async def api_load_config(
    request: Request,
    path: str,
    translation: bool = False,
    type: str = "auto",
    _user: dict = Depends(get_current_user),
):
    """加载配置文件"""
    return JSONResponse(
        request.app.state.config_service.load_config(path, translation, type)
    )


@router.post("/save_config")
async def api_save_config(
    request: Request,
    config_data: ConfigData,
    _admin: dict = Depends(get_current_admin),
):
    """保存配置文件"""
    config_service: ConfigService = request.app.state.config_service
    return JSONResponse(
        config_service.save_config(config_data.file_path, config_data.config_data)
    )


@router.post("/setup_rcon")
async def api_setup_rcon(
    request: Request,
    _admin: dict = Depends(get_current_admin),
):
    """一键启用RCON配置"""
    return JSONResponse(request.app.state.config_service.setup_rcon())


@router.get("/load_file")
async def load_file(
    request: Request,
    file: str,
    _user: dict = Depends(get_current_user),
):
    """load overall.js / overall.css"""
    return PlainTextResponse(request.app.state.file_service.load_custom_file(file))


@router.post("/save_file")
async def save_file(
    request: Request,
    data: SaveContent,
    _admin: dict = Depends(get_current_admin),
):
    """save overall.js / overall.css"""
    return JSONResponse(request.app.state.file_service.save_custom_file(data.action, data.content))


@router.get("/load_config_file")
async def load_config_file(
    request: Request,
    path: str,
    _user: dict = Depends(get_current_user),
):
    """load config file"""
    return PlainTextResponse(request.app.state.config_service.load_config_file_raw(path))


@router.post("/save_config_file")
async def save_config_file(
    request: Request,
    data: SaveContent,
    _admin: dict = Depends(get_current_admin),
):
    """save config file"""
    config_service: ConfigService = request.app.state.config_service
    return JSONResponse(config_service.save_config_file_raw(data.action, data.content))

