import hashlib
import json
import logging
import lzma
import os
import time
from typing import Dict, List, Optional

import requests

from .models import ExtendedVersionRequirement, PluginData, ReleaseData


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

    def filter_plugins(self, keyword: str = None) -> List[str]:
        result = []
        if not keyword:
            return list(self.plugins.keys())

        keyword = keyword.lower()
        for plugin_id, plugin_data in self.plugins.items():
            if keyword in plugin_id.lower():
                result.append(plugin_id)
            elif plugin_data.name and keyword in plugin_data.name.lower():
                result.append(plugin_id)
            elif plugin_data.description:
                for desc in plugin_data.description.values():
                    if desc and keyword in desc.lower():
                        result.append(plugin_id)
                        break
        return result


class RegistryManager:
    """元数据注册表管理器"""
    _download_failure_cache = {}
    _failure_cooldown = 15 * 60  # 15分钟

    def __init__(self, server, cache_dir: str):
        self.server = server
        self.cache_dir = cache_dir
        self.logger = logging.getLogger('PIM.RegistryManager')
        os.makedirs(self.cache_dir, exist_ok=True)

    def get_meta(self, url: str, ignore_ttl: bool = False) -> MetaRegistry:
        """获取元数据"""
        official_url = "https://api.mcdreforged.com/catalogue/everything_slim.json.xz"

        if url == official_url:
            cache_file = os.path.join(self.cache_dir, "everything_slim.json")
        else:
            cache_name = hashlib.md5(url.encode()).hexdigest()
            cache_file = os.path.join(self.cache_dir, f"repo_{cache_name}.json")

        cache_xz_file = cache_file + ".xz"

        # 1. 检查失败冷却
        current_time = time.time()
        if url in self._download_failure_cache:
            fail_info = self._download_failure_cache[url]
            if current_time - fail_info['failed_at'] < self._failure_cooldown and fail_info['attempt_count'] >= 2:
                if os.path.exists(cache_file):
                    return self._load_from_file(cache_file, url)
                return EmptyMetaRegistry()

        # 2. 检查缓存过期 (2小时)
        if not ignore_ttl and os.path.exists(cache_file):
            if current_time - os.path.getmtime(cache_file) < 7200:
                return self._load_from_file(cache_file, url)

        # 3. 下载新数据
        try:
            # 增加重试机制和更长的超时时间
            headers = {'User-Agent': 'MCDR-PIM-Registry/1.0'}
            response = requests.get(url, timeout=10, headers=headers)
            if response.status_code == 200:
                if url.endswith('.xz'):
                    with open(cache_xz_file, 'wb') as f:
                        f.write(response.content)
                    with lzma.open(cache_xz_file, 'rb') as f_in:
                        with open(cache_file, 'wb') as f_out:
                            f_out.write(f_in.read())
                    os.remove(cache_xz_file)
                else:
                    with open(cache_file, 'wb') as f:
                        f.write(response.content)

                if url in self._download_failure_cache:
                    del self._download_failure_cache[url]
                return self._load_from_file(cache_file, url)
            else:
                self._record_failure(url)
        except Exception as e:
            self.logger.error(f"下载元数据失败: {e}, URL: {url}")
            self._record_failure(url)

        if os.path.exists(cache_file):
            return self._load_from_file(cache_file, url)
        return EmptyMetaRegistry()

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
