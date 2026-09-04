"""Minecraft 服务端模组与模组配置管理接口。

- 所有成功响应统一 `{status, data, message?}` 外壳（service 自造 status 在路由层剥离）；
- 内联 `_is_super_admin` 收敛为公共依赖 `get_super_admin`（dependencies/auth.py）；
- `/mods/toggle`（POST + body 带 filename）→ `PUT /api/mods/{filename}/enabled`。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from guguwebui.dependencies.auth import get_current_admin, get_super_admin
from guguwebui.services.operation_audit_service import record_operation
from guguwebui.structures import (
    BusinessException,
    ModConfigSaveRequest,
    ModFileRequest,
    ModSettingsRequest,
    ModToggleRequest,
)
from guguwebui.structures.envelope import ApiSuccessEnvelope, PageEnvelope, page, success

router = APIRouter(prefix="/mods", tags=["mods"])

_OPERATION_KEYS = ("server_running", "needs_restart", "effective_after", "warnings")


def _audit(user: dict, operation_type: str, summary: str, detail: dict | None = None) -> None:
    record_operation(user, operation_type=operation_type, summary=summary, detail=detail)


def _operation_state(result: Dict[str, Any]) -> Dict[str, Any]:
    """从 service 结果中提取操作状态负载（剥离自造 status 键）。"""
    return {k: result[k] for k in _OPERATION_KEYS if k in result}


@router.get("", response_model=ApiSuccessEnvelope)
async def list_mods(request: Request, _admin: dict = Depends(get_current_admin)):
    result = await run_in_threadpool(request.app.state.mod_service.list_mods)
    return JSONResponse(
        success(
            {
                "mods": result.get("mods", []),
                "server_running": result.get("server_running", False),
                "mods_path": result.get("mods_path"),
            }
        )
    )


@router.get("/icon")
async def mod_icon(request: Request, filename: str, _admin: dict = Depends(get_current_admin)):
    data, media_type = request.app.state.mod_service.get_icon(filename)
    return Response(content=data, media_type=media_type)


@router.post("/upload", response_model=ApiSuccessEnvelope)
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
    mod_entry = result.get("mod") or {}
    _audit(admin, "mod.upload", f"上传模组: {mod_entry.get('filename', file.filename)}", {
        "filename": mod_entry.get("filename", file.filename),
        "enabled": enabled,
        "size": mod_entry.get("size"),
    })
    data: Dict[str, Any] = _operation_state(result)
    if mod_entry:
        data["mod"] = mod_entry
    return JSONResponse(success(data=data or None, message=result.get("message")))


@router.put("/{filename}/enabled", response_model=ApiSuccessEnvelope)
async def toggle_mod(
    request: Request,
    filename: str,
    body: ModToggleRequest,
    admin: dict = Depends(get_current_admin),
):
    result = request.app.state.mod_service.toggle(
        filename, body.enabled, body.acknowledge_warnings
    )
    _audit(admin, "mod.toggle", f"{'启用' if body.enabled else '禁用'}模组: {filename}", {
        "filename": filename, "enabled": body.enabled,
    })
    data: Dict[str, Any] = _operation_state(result)
    data["filename"] = result.get("filename", filename)
    return JSONResponse(success(data=data, message=result.get("message")))


@router.post("/trash", response_model=ApiSuccessEnvelope)
async def trash_mod(request: Request, body: ModFileRequest, admin: dict = Depends(get_current_admin)):
    result = request.app.state.mod_service.trash(body.filename)
    _audit(admin, "mod.trash", f"删除模组: {body.filename}", {"filename": body.filename})
    data: Dict[str, Any] = _operation_state(result)
    data["trash_id"] = result.get("trash_id")
    return JSONResponse(success(data=data, message=result.get("message")))


@router.get("/trash", response_model=PageEnvelope)
async def list_mod_trash(request: Request, _admin: dict = Depends(get_current_admin)):
    result = request.app.state.mod_service.list_trash()
    items = result.get("items", [])
    # 分页外壳（回收站当前为全量返回，total = 数量）
    return JSONResponse(page(items=items, total=len(items), offset=0, limit=len(items)))


@router.post("/trash/{trash_id}/restore", response_model=ApiSuccessEnvelope)
async def restore_mod(request: Request, trash_id: str, admin: dict = Depends(get_current_admin)):
    result = request.app.state.mod_service.restore(trash_id)
    _audit(admin, "mod.restore", f"恢复模组: {result.get('filename', trash_id)}", {
        "trash_id": trash_id, "filename": result.get("filename"),
    })
    data: Dict[str, Any] = _operation_state(result)
    data["filename"] = result.get("filename")
    return JSONResponse(success(data=data, message=result.get("message")))


@router.delete("/trash/{trash_id}", response_model=ApiSuccessEnvelope)
async def purge_mod(
    request: Request,
    trash_id: str,
    confirm: bool = Query(False),
    admin: dict = Depends(get_super_admin),
):
    if not confirm:
        raise BusinessException(
            "永久删除需要 confirm=true 二次确认", code="confirm_required"
        )
    result = request.app.state.mod_service.purge(trash_id)
    _audit(admin, "mod.purge", f"永久删除回收站模组: {result.get('filename', trash_id)}", {
        "trash_id": trash_id, "filename": result.get("filename"),
    })
    data: Dict[str, Any] = _operation_state(result)
    data["filename"] = result.get("filename")
    return JSONResponse(success(data=data, message=result.get("message")))


@router.get("/configs", response_model=ApiSuccessEnvelope)
async def list_mod_configs(
    request: Request,
    mod_id: str | None = None,
    associated_only: bool = False,
    _admin: dict = Depends(get_current_admin),
):
    result = request.app.state.mod_service.configs_response(mod_id, associated_only)
    return JSONResponse(success({"files": result.get("files", [])}))


@router.get("/config", response_model=ApiSuccessEnvelope)
async def get_mod_config(request: Request, path: str, _admin: dict = Depends(get_current_admin)):
    result = request.app.state.mod_service.load_config(path)
    data: Dict[str, Any] = {}
    for key in ("path", "content", "config_data"):
        if key in result:
            data[key] = result[key]
    return JSONResponse(success(data))


@router.put("/config", response_model=ApiSuccessEnvelope)
async def save_mod_config(request: Request, body: ModConfigSaveRequest, admin: dict = Depends(get_current_admin)):
    result = request.app.state.mod_service.save_config(
        body.path, content=body.content, config_data=body.config_data
    )
    _audit(admin, "mod.config_save", f"保存模组配置: {body.path}", {
        "path": body.path, "content_length": len(body.content or ""),
    })
    data: Dict[str, Any] = _operation_state(result)
    data["path"] = result.get("path", body.path)
    return JSONResponse(success(data=data, message=result.get("message")))


@router.get("/settings", response_model=ApiSuccessEnvelope)
async def get_mod_settings(request: Request, _admin: dict = Depends(get_current_admin)):
    config = request.app.state.config_service.get_config()
    value = int(config.get("mod_upload_max_bytes", 10 * 1024 * 1024))
    return JSONResponse(
        success(
            {
                "upload_max_mib": value // (1024 * 1024),
                "upload_max_bytes": value,
            }
        )
    )


@router.put("/settings", response_model=ApiSuccessEnvelope)
async def save_mod_settings(
    request: Request,
    body: ModSettingsRequest,
    admin: dict = Depends(get_super_admin),
):
    if body.upload_max_mib < 1 or body.upload_max_mib > 4096:
        raise BusinessException("模组上传上限必须在 1–4096 MiB 之间", code="invalid_value")
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
    _audit(admin, "mod.settings_save", "修改模组上传上限", {"upload_max_mib": body.upload_max_mib})
    return JSONResponse(success({"upload_max_mib": body.upload_max_mib}))
