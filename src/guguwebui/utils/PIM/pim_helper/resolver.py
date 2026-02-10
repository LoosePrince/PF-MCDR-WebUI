import json
import logging
import os
import sys
import zipfile
from typing import Any, Dict

from mcdreforged.plugin.meta.version import Version, VersionRequirement

from .registry import MetaRegistry


class PluginDependencyResolver:
    """插件依赖解析器"""
    def __init__(self, server, pim_helper):
        self.server = server
        self.pim_helper = pim_helper
        self.logger = logging.getLogger('PIM.Resolver')

    def resolve(self, plugin_id: str, cata_meta: MetaRegistry, downloaded_file: str = None) -> Dict[str, Any]:
        """
        解析依赖，包括插件依赖、Python 依赖和环境要求
        返回: {
            'missing_plugins': [],
            'outdated_plugins': {},
            'python_requirements': [],
            'environment_issues': []
        }
        """
        plugin_data = cata_meta.get_plugin_data(plugin_id)
        installed_plugins = {pid: self.server.get_plugin_instance(pid) for pid in self.server.get_plugin_list()}

        results = {
            'missing_plugins': [],
            'outdated_plugins': {},
            'python_requirements': [],
            'environment_issues': []
        }

        # 1. 检查元数据中的插件依赖
        if plugin_data and plugin_data.dependencies:
            for dep_id, version_req in plugin_data.dependencies.items():
                self._check_plugin_dep(dep_id, str(version_req), installed_plugins, results)

        # 2. 检查下载文件中的详细元数据 (mcdr_plugin.json / mcdreforged.plugin.json)
        if downloaded_file and os.path.exists(downloaded_file) and zipfile.is_zipfile(downloaded_file):
            try:
                with zipfile.ZipFile(downloaded_file, 'r') as z:
                    meta_file = next((f for f in z.namelist() if f.endswith(('mcdr_plugin.json', 'mcdreforged.plugin.json'))), None)
                    if meta_file:
                        meta = json.loads(z.read(meta_file).decode('utf-8'))

                        # 检查插件依赖
                        deps = meta.get('dependencies', {})
                        for dep_id, version_req in deps.items():
                            if dep_id.lower() == 'mcdreforged':
                                self._check_mcdr_version(str(version_req), results)
                            elif dep_id.lower() == 'python':
                                self._check_python_version(str(version_req), results)
                            else:
                                self._check_plugin_dep(dep_id, str(version_req), installed_plugins, results)

                        # 检查 Python 包依赖 (requirements.txt 等)
                        # 某些插件可能在元数据中直接声明，或者我们需要扫描包内文件
                        # 这里先处理元数据中可能的自定义字段，或者记录需要扫描
                        if 'python_requirements' in meta:
                            results['python_requirements'].extend(meta['python_requirements'])
            except Exception as e:
                self.logger.error(f"解析文件依赖失败: {e}")

        return results

    def _check_plugin_dep(self, dep_id: str, version_req: str, installed_plugins: Dict, results: Dict):
        # 排除核心环境依赖
        if dep_id.lower() in ('mcdreforged', 'python'):
            return

        if dep_id not in installed_plugins:
            if dep_id not in results['missing_plugins']:
                results['missing_plugins'].append(dep_id)
        else:
            p_meta = self.server.get_plugin_metadata(dep_id)
            ver = str(p_meta.version) if p_meta else 'unknown'
            try:
                if not VersionRequirement(version_req).accept(Version(ver)):
                    results['outdated_plugins'][dep_id] = version_req
            except:
                pass

    def _check_mcdr_version(self, version_req: str, results: Dict):
        try:
            from mcdreforged.constants.core_constant import VERSION as MCDR_VERSION
            if not VersionRequirement(version_req).accept(Version(MCDR_VERSION)):
                results['environment_issues'].append(f"MCDReforged 版本不符: 需要 {version_req}, 当前 {MCDR_VERSION}")
        except:
            pass

    def _check_python_version(self, version_req: str, results: Dict):
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        try:
            if not VersionRequirement(version_req).accept(Version(py_ver)):
                results['environment_issues'].append(f"Python 版本不符: 需要 {version_req}, 当前 {py_ver}")
        except:
            pass
