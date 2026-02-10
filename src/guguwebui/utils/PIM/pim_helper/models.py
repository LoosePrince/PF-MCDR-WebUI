from dataclasses import dataclass, field
from typing import Dict, List, Optional

from mcdreforged.plugin.meta.version import VersionRequirement


# 自定义实现，替代MCDR内部模块
class PluginRequirementSource:
    existing = "existing"
    existing_pinned = "existing_pinned"

# 扩展VersionRequirement类，添加check方法
class ExtendedVersionRequirement(VersionRequirement):
    def check(self, version: str) -> bool:
        """调用accept方法，兼容我们的代码"""
        return self.accept(version)

@dataclass
class PluginRequirement:
    id: str
    requirement: VersionRequirement

    def satisfied_by(self, plugin_id: str, version: str) -> bool:
        return self.id == plugin_id and self.requirement.accept(version)

@dataclass
class ReleaseData:
    """发布数据类"""
    name: str
    tag_name: str
    created_at: str
    description: str
    prerelease: bool
    url: str
    browser_download_url: str
    download_count: int
    size: int
    file_name: str

    @property
    def version(self) -> str:
        """获取版本号，兼容原始接口"""
        return self.tag_name.lstrip('v') if self.tag_name else ""

@dataclass
class PluginData:
    """插件数据类"""
    id: str
    name: str
    version: str
    description: Dict[str, str]
    author: List[str]
    link: str
    dependencies: Dict[str, VersionRequirement]
    requirements: List[str]
    releases: List[ReleaseData] = field(default_factory=list)
    repos_owner: str = ""
    repos_name: str = ""

    def __post_init__(self):
        if self.releases is None:
            self.releases = []

        # 尝试从link中解析仓库信息
        if self.link and 'github.com' in self.link:
            try:
                parts = self.link.split('github.com/')[1].split('/')
                if len(parts) >= 2:
                    self.repos_owner = parts[0]
                    self.repos_name = parts[1]
            except:
                pass

    def get_dependencies(self) -> Dict[str, VersionRequirement]:
        """获取依赖项"""
        return self.dependencies

    def get_latest_release(self) -> Optional[ReleaseData]:
        """获取最新版本"""
        if not self.releases:
            return None
        return self.releases[0]

    @property
    def latest_version(self) -> Optional[str]:
        """获取最新版本号，兼容原始接口"""
        release = self.get_latest_release()
        if release:
            return release.tag_name.lstrip('v') if release.tag_name else self.version
        return self.version
