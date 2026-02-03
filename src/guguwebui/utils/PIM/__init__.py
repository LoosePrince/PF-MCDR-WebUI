from .pim_helper import PIMHelper
from .pim_helper.models import PluginData, ReleaseData
from .pim_helper.registry import MetaRegistry
from .pim_helper.installer import PluginInstaller
from .pim_helper.tasks import TaskManager

# 统一导出接口
def create_installer(server):
    return PIMHelper(server).installer

def initialize_pim(server):
    helper = PIMHelper(server)
    return helper, helper.installer

__all__ = [
    'PIMHelper',
    'PluginInstaller',
    'MetaRegistry',
    'TaskManager',
    'create_installer',
    'initialize_pim'
]
