"""统一 API 响应外壳（契约基建）。

目标基线（见 docs/api_review.md §2.3）：
- 成功（2xx）：{"status": "success", "message"?: str, "data"?: any}
- 失败（4xx/5xx）：{"status": "error", "message": str, "code": str, "data"?: any}
- 分页列表：data = {"items": [...], "total": int, "offset": int, "limit": int}

说明：业务负载从顶层字段迁入 data 随各路由改写逐步推进；
本模块只提供统一的构造/判定原语，供各路由在改写时复用。
"""

from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiSuccessBody(TypedDict, total=False):
    status: Literal["success"]
    message: Optional[str]
    data: Optional[Any]


class ApiErrorBody(TypedDict, total=False):
    status: Literal["error"]
    message: str
    code: str
    data: Optional[Any]


def success(data: Any = None, message: Optional[str] = None) -> ApiSuccessBody:
    """构造统一成功体。未提供 message 时不带该键，避免噪音。"""
    body: ApiSuccessBody = {"status": "success"}
    if data is not None:
        body["data"] = data
    if message:
        body["message"] = message
    return body


def error(
    message: str,
    code: str = "error",
    data: Any = None,
) -> ApiErrorBody:
    """构造统一错误体（与 HTTP 非 2xx 状态码配套使用）。"""
    body: ApiErrorBody = {"status": "error", "message": message, "code": code}
    if data is not None:
        body["data"] = data
    return body


def page(
    items: list,
    total: int,
    offset: int = 0,
    limit: Optional[int] = None,
) -> ApiSuccessBody:
    """构造统一分页成功体：data = {items, total, offset, limit}。"""
    return success(
        {
            "items": items,
            "total": int(total),
            "offset": int(offset),
            "limit": limit,
        }
    )


# ------------------------------------------------------------ #
# 路由 response_model（OpenAPI 可导出契约，出错路径不校验，仅成功模型）


class ApiSuccessEnvelope(BaseModel):
    """统一成功外壳（2.3）：status/message?/data?。"""
    status: Literal["success"] = "success"
    message: Optional[str] = None
    data: Optional[Any] = None


class PageData(BaseModel):
    """统一分页负载（2.3）：data = {items, total, offset, limit}。"""
    items: list
    total: int
    offset: int
    limit: Optional[int] = None


class PageEnvelope(ApiSuccessEnvelope):
    """分页成功外壳。"""
    data: Optional[PageData] = None
