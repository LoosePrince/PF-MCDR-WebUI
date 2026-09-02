"""Minecraft 服务端模组与模组配置管理接口。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from guguwebui.dependencies.auth import get_current_admin
from guguwebui.services.operation_audit_service import record_operation
from guguwebui.structures import (
    ModConfigSaveRequest,
    ModFileRequest,
    ModSettingsRequest,
    ModToggleRequest,
)

router = APIRouter(prefix="/mods", tags=["mods"])


def _is_super_admin(request: Request, user: dict) -> bool:
    if user.get("auth_via") == "panel_token":
        return True
    config = request.app.state.config_service.get_config()
    return str(user.get("username")) == str(config.get("super_admin_account"))


def _audit(user: dict, operation_type: str, summary: str, detail: dict | None = None) -> None:
    record_operation(user, operation_type=operation_type, summary=summary, detail=detail)


@router.get("")
async def list_mods(request: Request, _admin: dict = Depends(get_current_admin)):
    result = await run_in_threadpool(request.app.state.mod_service.list_mods)
    return JSONResponse(result)


@router.get("/icon")
async def mod_icon(request: Request, filename: str, _admin: dict = Depends(get_current_admin)):
    data, media_type = request.app.state.mod_service.get_icon(filename)
    return Response(content=data, media_type=media_type)


@router.post("/upload")
async def upload_mod(
    request: Request,
    file: UploadFile = File(...),
    enabled: bool = Form(True),
    acknowledge_warnings: bool = Form(False),
    admin: dict = Depends(get_current_admin),
):
    config = request.app.state.config_service.get_config()
    max_bytes = int(config.get("mod_upload_max_bytes", 10 * 1024 * 1024))
    result = await request.app.state.mod_service.upload(file, enabled, max_bytes, acknowledge_warnings)
    _audit(admin, "mod.upload", f"上传模组: {result.get('mod', {}).get('filename', file.filename)}", {
        "filename": result.get("mod", {}).get("filename", file.filename),
        "enabled": enabled,
        "size": result.get("mod", {}).get("size"),
    })
    return JSONResponse(result)


@router.post("/toggle")
async def toggle_mod(request: Request, body: ModToggleRequest, admin: dict = Depends(get_current_admin)):
    result = request.app.state.mod_service.toggle(
        body.filename, body.enabled, body.acknowledge_warnings
    )
    if result.get("status") == "success":
        _audit(admin, "mod.toggle", f"{'启用' if body.enabled else '禁用'}模组: {body.filename}", {
            "filename": body.filename, "enabled": body.enabled,
        })
    return JSONResponse(result)


@router.post("/trash")
async def trash_mod(request: Request, body: ModFileRequest, admin: dict = Depends(get_current_admin)):
    result = request.app.state.mod_service.trash(body.filename)
    _audit(admin, "mod.trash", f"删除模组: {body.filename}", {"filename": body.filename})
    return JSONResponse(result)


@router.get("/trash")
async def list_mod_trash(request: Request, _admin: dict = Depends(get_current_admin)):
    return JSONResponse(request.app.state.mod_service.list_trash())


@router.post("/trash/{trash_id}/restore")
async def restore_mod(request: Request, trash_id: str, admin: dict = Depends(get_current_admin)):
    result = request.app.state.mod_service.restore(trash_id)
    _audit(admin, "mod.restore", f"恢复模组: {result.get('filename', trash_id)}", {
        "trash_id": trash_id, "filename": result.get("filename"),
    })
    return JSONResponse(result)


@router.delete("/trash/{trash_id}")
async def purge_mod(
    request: Request,
    trash_id: str,
    confirm: bool = Query(False),
    admin: dict = Depends(get_current_admin),
):
    if not _is_super_admin(request, admin):
        from guguwebui.structures import ForbiddenException
        raise ForbiddenException("只有超级管理员可以永久清理模组")
    if not confirm:
        from guguwebui.structures import BusinessException
        raise BusinessException("永久删除需要 confirm=true 二次确认")
    result = request.app.state.mod_service.purge(trash_id)
    _audit(admin, "mod.purge", f"永久删除回收站模组: {result.get('filename', trash_id)}", {
        "trash_id": trash_id, "filename": result.get("filename"),
    })
    return JSONResponse(result)


@router.get("/configs")
async def list_mod_configs(
    request: Request,
    mod_id: str | None = None,
    associated_only: bool = False,
    _admin: dict = Depends(get_current_admin),
):
    return JSONResponse(request.app.state.mod_service.configs_response(mod_id, associated_only))


@router.get("/config")
async def get_mod_config(request: Request, path: str, _admin: dict = Depends(get_current_admin)):
    return JSONResponse(request.app.state.mod_service.load_config(path))


@router.put("/config")
async def save_mod_config(request: Request, body: ModConfigSaveRequest, admin: dict = Depends(get_current_admin)):
    result = request.app.state.mod_service.save_config(
        body.path, content=body.content, config_data=body.config_data
    )
    _audit(admin, "mod.config_save", f"保存模组配置: {body.path}", {
        "path": body.path, "content_length": len(body.content or ""),
    })
    return JSONResponse(result)


@router.get("/settings")
async def get_mod_settings(request: Request, _admin: dict = Depends(get_current_admin)):
    config = request.app.state.config_service.get_config()
    value = int(config.get("mod_upload_max_bytes", 10 * 1024 * 1024))
    return JSONResponse({
        "status": "success",
        "upload_max_mib": value // (1024 * 1024),
        "upload_max_bytes": value,
    })


@router.put("/settings")
async def save_mod_settings(
    request: Request,
    body: ModSettingsRequest,
    admin: dict = Depends(get_current_admin),
):
    if not _is_super_admin(request, admin):
        from guguwebui.structures import ForbiddenException
        raise ForbiddenException("只有超级管理员可以修改模组上传上限")
    if body.upload_max_mib < 1 or body.upload_max_mib > 4096:
        from guguwebui.structures import BusinessException
        raise BusinessException("模组上传上限必须在 1–4096 MiB 之间")
    config_service = request.app.state.config_service
    config = config_service.get_config()
    config["mod_upload_max_bytes"] = body.upload_max_mib * 1024 * 1024
    config_path = Path(request.app.state.server_interface.get_data_folder()) / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=str(config_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(config, fp, ensure_ascii=False, indent=4)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(temp_name, config_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    result = {"status": "success", "upload_max_mib": body.upload_max_mib}
    _audit(admin, "mod.settings_save", "修改模组上传上限", {"upload_max_mib": body.upload_max_mib})
    return JSONResponse(result)
