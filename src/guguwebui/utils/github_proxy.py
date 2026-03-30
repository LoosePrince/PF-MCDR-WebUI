from typing import List
from urllib.parse import urlparse


GHFAST_PROXY_PREFIX = "https://ghfast.top/"


def is_github_related_url(url: str) -> bool:
    """判断 URL 是否属于 GitHub 文件相关地址。"""
    if not isinstance(url, str) or not url.strip():
        return False

    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False

    return host in {
        "github.com",
        "raw.githubusercontent.com",
        "objects.githubusercontent.com",
        "githubusercontent.com",
    } or host.endswith(".githubusercontent.com")


def to_ghfast_url(url: str) -> str:
    """将原始 URL 转换为 ghfast 代理 URL。"""
    raw = (url or "").strip()
    if not raw:
        return raw
    if raw.startswith(GHFAST_PROXY_PREFIX):
        return raw
    return f"{GHFAST_PROXY_PREFIX}{raw}"


def build_github_fallback_urls(url: str) -> List[str]:
    """
    为 GitHub 文件相关 URL 构建请求候选顺序：
    1) 原始 URL
    2) ghfast 代理 URL（仅 GitHub 相关 URL）
    """
    raw = (url or "").strip()
    if not raw:
        return []

    candidates = [raw]
    if is_github_related_url(raw):
        proxy_url = to_ghfast_url(raw)
        if proxy_url != raw:
            candidates.append(proxy_url)
    return candidates
