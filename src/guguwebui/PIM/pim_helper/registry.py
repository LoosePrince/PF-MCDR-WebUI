import hashlib
import json
import logging
import lzma
import os
import threading
import time
import uuid
from typing import Dict, List, Optional

import requests

from guguwebui.constant import MCDR_OFFICIAL_CATALOGUE_URL
from guguwebui.utils.github_proxy import build_github_fallback_urls

from .models import ExtendedVersionRequirement, PluginData, ReleaseData

# 进程内目录元数据缓存（P1）：url -> {loaded_at, registry}，与磁盘缓存 TTL(2h) 对齐；
# 同一进程内所有 RegistryManager 共享，避免每次请求都重新反序列化整份仓库 JSON
_registry_mem_cache: Dict[str, Dict] = {}
_registry_cache_locks: Dict[str, threading.Lock] = {}
_registry_lock_guard = threading.Lock()


class EmptyMetaRegistry:
    """空元数据注册表"""

    def __init__(self):
        self.plugins = {}

    def get_plugin_data(self, plugin_id: str) -> Optional[PluginData]:
        return None

    def has_plugin(self, plugin_id: str) -> bool:
        return False

    def get_plugins(self) -> Dict[str, PluginData]:
        return {}


class MetaRegistry:
    """元数据注册表类"""

    def __init__(self, data: Dict = None, source_url: str = None):
        self.data = data or {}
        self.source_url = source_url
        self.plugins = {}
        self.logger = logging.getLogger('PIM.MetaRegistry')

        try:
            self._parse_data()
        except Exception as e:
            self.logger.error(f"解析元数据失败: {e}")

        plugins_count = len(self.plugins)
        plugin_ids = list(self.plugins.keys())
        source_info = f" from {self.source_url}" if self.source_url else ""
        self.logger.debug(
            f"已加载 {plugins_count} 个插件{source_info}: {', '.join(plugin_ids[:5])}{'...' if plugins_count > 5 else ''}")

    def get_registry_data(self) -> Dict:
        """获取元数据注册表的原始数据"""
        return self.data

    def _parse_data(self):
        """解析数据为插件数据对象"""
        if not self.data:
            return

        self.plugins = {}

        if isinstance(self.data, list):
            # 数组格式的简化仓库
            for plugin_info in self.data:
                if not isinstance(plugin_info, dict) or 'id' not in plugin_info:
                    continue

                plugin_id = plugin_info.get('id')
                if not plugin_id:
                    continue

                dependencies = {}
                dependencies_dict = plugin_info.get('dependencies') or {}
                if isinstance(dependencies_dict, dict):
                    for dep_id, dep_req in dependencies_dict.items():
                        dependencies[dep_id] = ExtendedVersionRequirement(dep_req)

                repos_owner = ""
                repos_name = ""
                if plugin_info.get('repository_url') and 'github.com' in plugin_info.get('repository_url'):
                    try:
                        parts = plugin_info['repository_url'].split('github.com/')[1].split('/')
                        if len(parts) >= 2:
                            repos_owner = parts[0]
                            repos_name = parts[1]
                    except:
                        pass

                release = None
                if plugin_info.get('latest_version'):
                    release = ReleaseData(
                        name=f"v{plugin_info.get('latest_version')}",
                        tag_name=f"v{plugin_info.get('latest_version')}",
                        created_at=plugin_info.get('last_update_time', ''),
                        description='',
                        prerelease=False,
                        url='',
                        browser_download_url='',
                        download_count=plugin_info.get('downloads', 0),
                        size=0,
                        file_name=f"{plugin_id}.mcdr"
                    )

                plugin_data = PluginData(
                    id=plugin_id,
                    name=plugin_info.get('name', plugin_id),
                    version=plugin_info.get('version', ''),
                    description=plugin_info.get('description', {}),
                    author=plugin_info.get('authors', []),
                    link=plugin_info.get('repository_url', ''),
                    dependencies=dependencies,
                    requirements=plugin_info.get('requirements', []),
                    releases=[release] if release else [],
                    repos_owner=repos_owner,
                    repos_name=repos_name
                )
                self.plugins[plugin_id] = plugin_data

        elif isinstance(self.data, dict) and 'plugins' in self.data:
            # 标准格式的仓库
            for plugin_id, plugin_info in self.data['plugins'].items():
                if not isinstance(plugin_info, dict):
                    continue

                meta = plugin_info.get('meta') or {}
                release_info = plugin_info.get('release') or {}

                if not isinstance(meta, dict): meta = {}
                if not isinstance(release_info, dict): release_info = {}

                releases = []
                releases_list = release_info.get('releases', [])
                if not isinstance(releases_list, list): releases_list = []

                for rel in releases_list:
                    if not isinstance(rel, dict): continue

                    asset = rel.get('asset') or {}
                    if not isinstance(asset, dict): asset = {}

                    release_data = ReleaseData(
                        name=rel.get('name', ''),
                        tag_name=rel.get('tag_name', ''),
                        created_at=rel.get('created_at', ''),
                        description=rel.get('description', ''),
                        prerelease=rel.get('prerelease', False),
                        url=rel.get('url', ''),
                        browser_download_url=asset.get('browser_download_url', ''),
                        download_count=asset.get('download_count', 0),
                        size=asset.get('size', 0),
                        file_name=asset.get('name', '')
                    )
                    releases.append(release_data)

                dependencies = {}
                dependencies_dict = meta.get('dependencies', {})
                if isinstance(dependencies_dict, dict):
                    for dep_id, dep_req in dependencies_dict.items():
                        dependencies[dep_id] = ExtendedVersionRequirement(dep_req)

                plugin_data = PluginData(
                    id=meta.get('id', plugin_id),
                    name=meta.get('name', plugin_id),
                    version=meta.get('version', ''),
                    description=meta.get('description', {}),
                    author=meta.get('authors', []),
                    link=meta.get('link', ''),
                    dependencies=dependencies,
                    requirements=meta.get('requirements', []),
                    releases=releases
                )
                self.plugins[plugin_id] = plugin_data

    def get_plugin_data(self, plugin_id: str) -> Optional[PluginData]:
        return self.plugins.get(plugin_id)

    def has_plugin(self, plugin_id: str) -> bool:
        return plugin_id in self.plugins

    def get_plugins(self) -> Dict[str, PluginData]:
        return self.plugins


class RegistryManager:
    """元数据注册表管理器"""
    _download_failure_cache = {}
    _failure_cooldown = 15 * 60  # 15分钟

    def __init__(self, server, cache_dir: str):
        self.server = server
        self.cache_dir = cache_dir
        self.logger = logging.getLogger('PIM.RegistryManager')
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_with_fallback(self, url: str, headers: Dict[str, str], timeout: int) -> Optional[requests.Response]:
        """对 GitHub 文件地址启用 ghfast 代理回退。"""
        candidate_urls = build_github_fallback_urls(url)
        for index, candidate_url in enumerate(candidate_urls):
            try:
                resp = requests.get(candidate_url, timeout=timeout, headers=headers)
                if resp.status_code == 200:
                    return resp
                if index + 1 < len(candidate_urls):
                    self.logger.warning(
                        f"拉取元数据返回 {resp.status_code}，准备切换备用地址: {candidate_url}"
                    )
            except Exception as e:
                if index + 1 < len(candidate_urls):
                    self.logger.warning(
                        f"拉取元数据失败，准备切换备用地址: {candidate_url}, error: {e}"
                    )
                else:
                    self.logger.error(f"下载元数据失败: {e}, URL: {candidate_url}")
        return None

    def _get_url_lock(self, url: str) -> threading.Lock:
        """同一 URL 的互斥锁（P1/P2：防止并发重复下载与重复解析）"""
        with _registry_lock_guard:
            if url not in _registry_cache_locks:
                _registry_cache_locks[url] = threading.Lock()
            return _registry_cache_locks[url]

    def get_meta(self, url: str, ignore_ttl: bool = False) -> MetaRegistry:
        """获取元数据（磁盘 TTL 2h + 进程内缓存 + 单仓库并发锁 + 原子写，P1/P2）"""
        if url == MCDR_OFFICIAL_CATALOGUE_URL:
            cache_file = os.path.join(self.cache_dir, "everything_slim.json")
        else:
            cache_name = hashlib.md5(url.encode()).hexdigest()
            cache_file = os.path.join(self.cache_dir, f"repo_{cache_name}.json")

        with self._get_url_lock(url):
            return self._get_meta_locked(url, cache_file, ignore_ttl)

    def _get_meta_locked(self, url: str, cache_file: str, ignore_ttl: bool = False) -> MetaRegistry:
        """get_meta 加锁后的实现，复用进程内缓存避免重复反序列化"""
        current_time = time.time()
        mem_entry = _registry_mem_cache.get(url)

        # 1. 进程内缓存命中（与磁盘 TTL 一致，2 小时）
        if not ignore_ttl and mem_entry and current_time - mem_entry["loaded_at"] < 7200:
            return mem_entry["registry"]

        # 2. 检查失败冷却（15 分钟，连续失败 2 次后进入）
        if url in self._download_failure_cache:
            fail_info = self._download_failure_cache[url]
            if current_time - fail_info['failed_at'] < self._failure_cooldown and fail_info['attempt_count'] >= 2:
                if mem_entry:
                    return mem_entry["registry"]
                if os.path.exists(cache_file):
                    registry = self._load_from_file(cache_file, url)
                    _registry_mem_cache[url] = {"loaded_at": current_time, "registry": registry}
                    return registry
                return EmptyMetaRegistry()

        # 3. 磁盘缓存 TTL (2小时)
        if not ignore_ttl and os.path.exists(cache_file):
            if current_time - os.path.getmtime(cache_file) < 7200:
                registry = self._load_from_file(cache_file, url)
                _registry_mem_cache[url] = {"loaded_at": current_time, "registry": registry}
                return registry

        # 4. 下载新数据（临时文件 + os.replace 原子写，避免写出一半的损坏缓存）
        try:
            headers = {'User-Agent': 'MCDR-PIM-Registry/1.0'}
            response = self._get_with_fallback(url, timeout=10, headers=headers)
            if response and response.status_code == 200:
                self._write_cache_atomic(cache_file, response.content, url.endswith('.xz'))
                if url in self._download_failure_cache:
                    del self._download_failure_cache[url]
                registry = self._load_from_file(cache_file, url)
                _registry_mem_cache[url] = {"loaded_at": time.time(), "registry": registry}
                return registry
            self._record_failure(url)
        except Exception as e:
            self.logger.error(f"下载元数据失败: {e}, URL: {url}")
            self._record_failure(url)

        # 5. 下载失败回退到磁盘缓存（尽力而为）
        if os.path.exists(cache_file):
            registry = self._load_from_file(cache_file, url)
            if not mem_entry:
                _registry_mem_cache[url] = {"loaded_at": current_time, "registry": registry}
            return registry
        return EmptyMetaRegistry()

    @staticmethod
    def _write_cache_atomic(cache_file: str, content: bytes, is_xz: bool) -> None:
        """原子写缓存：先写临时文件再 os.replace；.xz 内容在内存解压后落盘 json"""
        tmp_path = f"{cache_file}.tmp{uuid.uuid4().hex[:8]}"
        try:
            data = lzma.decompress(content) if is_xz else content
            with open(tmp_path, 'wb') as f:
                f.write(data)
            os.replace(tmp_path, cache_file)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            raise

    def _load_from_file(self, path: str, url: str) -> MetaRegistry:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return MetaRegistry(json.load(f), url)
        except Exception as e:
            self.logger.error(f"加载缓存文件失败: {e}, Path: {path}")
            return EmptyMetaRegistry()

    def _record_failure(self, url: str):
        current_time = time.time()
        if url not in self._download_failure_cache:
            self._download_failure_cache[url] = {'failed_at': current_time, 'attempt_count': 1}
        else:
            self._download_failure_cache[url]['failed_at'] = current_time
            self._download_failure_cache[url]['attempt_count'] += 1


class PluginCatalogueAccess:
    """插件目录访问实现"""

    @staticmethod
    def filter_sort(plugins: List[PluginData], keyword: str = None) -> List[PluginData]:
        if not keyword:
            return list(plugins)

        keyword = keyword.lower()
        result = []
        for plugin in plugins:
            if (keyword in plugin.id.lower() or
                    keyword in plugin.name.lower() or
                    any(keyword in str(desc).lower() for desc in plugin.description.values())):
                result.append(plugin)
        return result

    @staticmethod
    def list_plugin(meta: MetaRegistry, replier, keyword: str = None) -> int:
        plugins = list(meta.get_plugins().values())
        filtered_plugins = PluginCatalogueAccess.filter_sort(plugins, keyword)

        if not filtered_plugins:
            replier.reply(f"没有找到包含关键词 '{keyword}' 的插件")
            return 0

        replier.reply(f"找到 {len(filtered_plugins)} 个插件:")
        for plugin in filtered_plugins:
            desc = plugin.description.get('zh_cn', plugin.description.get('en_us', '无描述'))
            replier.reply(f"{plugin.id} | {plugin.name} | {plugin.version} | {desc}")
        return len(filtered_plugins)
