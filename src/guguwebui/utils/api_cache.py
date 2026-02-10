"""
API缓存模块
用于缓存耗时但变化不频繁的API响应
"""

import time
from functools import wraps
from typing import Any, Callable, Dict, Optional


class APICache:
    """API响应缓存管理器"""

    def __init__(self):
        # 缓存存储：{key: {"data": ..., "timestamp": ..., "ttl": ...}}
        self._cache: Dict[str, Dict[str, Any]] = {}
        # 永久缓存（直到插件重启）：{key: data}
        self._permanent_cache: Dict[str, Any] = {}

    def get(self, key: str, ttl: Optional[float] = None) -> Optional[Any]:
        """
        获取缓存数据

        Args:
            key: 缓存键
            ttl: 缓存生存时间（秒），None表示使用永久缓存

        Returns:
            缓存的数据，如果不存在或已过期则返回None
        """
        if ttl is None:
            # 永久缓存
            return self._permanent_cache.get(key)

        # 临时缓存
        if key not in self._cache:
            return None

        cache_item = self._cache[key]
        elapsed = time.time() - cache_item["timestamp"]

        if elapsed > cache_item["ttl"]:
            # 缓存已过期，删除
            del self._cache[key]
            return None

        return cache_item["data"]

    def set(self, key: str, data: Any, ttl: Optional[float] = None):
        """
        设置缓存数据

        Args:
            key: 缓存键
            data: 要缓存的数据
            ttl: 缓存生存时间（秒），None表示永久缓存
        """
        if ttl is None:
            # 永久缓存
            self._permanent_cache[key] = data
        else:
            # 临时缓存
            self._cache[key] = {
                "data": data,
                "timestamp": time.time(),
                "ttl": ttl
            }

    def invalidate(self, key: str):
        """
        使缓存失效

        Args:
            key: 缓存键
        """
        if key in self._cache:
            del self._cache[key]
        if key in self._permanent_cache:
            del self._permanent_cache[key]

    def clear(self):
        """清空所有缓存"""
        self._cache.clear()
        self._permanent_cache.clear()

    def clear_temporary(self):
        """清空临时缓存，保留永久缓存"""
        self._cache.clear()


# 全局缓存实例
api_cache = APICache()


def cached(ttl: Optional[float] = None, key_prefix: str = ""):
    """
    缓存装饰器

    Args:
        ttl: 缓存生存时间（秒），None表示永久缓存
        key_prefix: 缓存键前缀

    Usage:
        @cached(ttl=60)  # 缓存60秒
        async def my_api():
            return {"data": "value"}

        @cached(ttl=None)  # 永久缓存
        async def rcon_status():
            return {"enabled": True}
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix}:{func.__name__}"
            if args:
                cache_key += f":{str(args)}"
            if kwargs:
                cache_key += f":{str(sorted(kwargs.items()))}"

            # 尝试从缓存获取
            cached_data = api_cache.get(cache_key, ttl)
            if cached_data is not None:
                return cached_data

            # 缓存未命中，执行函数
            result = await func(*args, **kwargs)

            # 存储到缓存
            api_cache.set(cache_key, result, ttl)

            return result

        return wrapper
    return decorator


def invalidate_cache(key: str):
    """
    使指定缓存失效

    Args:
        key: 缓存键或键前缀
    """
    api_cache.invalidate(key)
