import os
import sys
import subprocess
from mcdreforged.api.all import *

PLUGIN_METADATA = {
    'id': 'pip_installer',
    'version': '1.0.0',
    'name': 'Pip安装器',
    'description': '通过!!pip install命令在MCDR中安装pip包',
    'author': 'LoosePrince',
    'link': 'https://github.com/PFingan-Code/PF-MCDR-WebUI',
    'dependencies': {}
}

# 权限等级
PERMISSION_LEVEL_INSTALL = 4  # 使用 !!pip install 的最低权限
PERMISSION_LEVEL_UNINSTALL = 4  # 使用 !!pip uninstall 的最低权限
PERMISSION_LEVEL_LIST = 4  # 使用 !!pip list 的最低权限

def on_load(server: PluginServerInterface, old):
    server.register_help_message('!!pip', '使用pip安装/卸载/查询Python包')
    server.register_command(
        Literal('!!pip').runs(lambda src: show_help(src, server))
        .then(
            Literal('install')
            .requires(lambda src: src.has_permission(PERMISSION_LEVEL_INSTALL))
            .then(
                GreedyText('package_name')
                .runs(lambda src, ctx: install_package(src, server, ctx['package_name']))
            )
        )
        .then(
            Literal('uninstall')
            .requires(lambda src: src.has_permission(PERMISSION_LEVEL_UNINSTALL))
            .then(
                GreedyText('package_name')
                .runs(lambda src, ctx: uninstall_package(src, server, ctx['package_name']))
            )
        )
        .then(
            Literal('list')
            .requires(lambda src: src.has_permission(PERMISSION_LEVEL_LIST))
            .runs(lambda src: list_packages(src, server))
        )
    )

def show_help(source: CommandSource, server: PluginServerInterface):
    source.reply('§6Pip安装器§r 帮助：')
    source.reply('§7!!pip install <包名>§r - 安装指定的Python包')
    source.reply('§7!!pip uninstall <包名>§r - 卸载指定的Python包')
    source.reply('§7!!pip list§r - 列出已安装的Python包')

def install_package(source: CommandSource, server: PluginServerInterface, package_name: str):
    server.logger.info(f'开始安装Python包: {package_name}')
    source.reply(f'§6开始安装包: §b{package_name}§r')
    
    try:
        # 使用当前运行MCDR的Python解释器安装
        python_executable = sys.executable
        process = subprocess.Popen(
            [python_executable, '-m', 'pip', 'install', package_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate()
        
        if process.returncode == 0:
            source.reply(f'§a成功安装包: §b{package_name}§r')
            source.reply(f'§7安装信息: {stdout.strip()}§r')
            server.logger.info(f'成功安装Python包: {package_name}')
        else:
            source.reply(f'§c安装包失败: §b{package_name}§r')
            source.reply(f'§7错误信息: {stderr.strip()}§r')
            server.logger.error(f'安装Python包失败: {package_name}, 错误: {stderr.strip()}')
    except Exception as e:
        source.reply(f'§c执行安装命令时出错: §b{str(e)}§r')
        server.logger.error(f'执行安装命令时出错: {str(e)}')

def uninstall_package(source: CommandSource, server: PluginServerInterface, package_name: str):
    server.logger.info(f'开始卸载Python包: {package_name}')
    source.reply(f'§6开始卸载包: §b{package_name}§r')
    
    try:
        # 使用当前运行MCDR的Python解释器卸载
        python_executable = sys.executable
        process = subprocess.Popen(
            [python_executable, '-m', 'pip', 'uninstall', '-y', package_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate()
        
        if process.returncode == 0:
            source.reply(f'§a成功卸载包: §b{package_name}§r')
            source.reply(f'§7卸载信息: {stdout.strip()}§r')
            server.logger.info(f'成功卸载Python包: {package_name}')
        else:
            source.reply(f'§c卸载包失败: §b{package_name}§r')
            source.reply(f'§7错误信息: {stderr.strip()}§r')
            server.logger.error(f'卸载Python包失败: {package_name}, 错误: {stderr.strip()}')
    except Exception as e:
        source.reply(f'§c执行卸载命令时出错: §b{str(e)}§r')
        server.logger.error(f'执行卸载命令时出错: {str(e)}')

def list_packages(source: CommandSource, server: PluginServerInterface):
    server.logger.info('列出已安装的Python包')
    source.reply('§6正在获取已安装的Python包列表...§r')
    
    try:
        # 使用当前运行MCDR的Python解释器列出已安装的包
        python_executable = sys.executable
        process = subprocess.Popen(
            [python_executable, '-m', 'pip', 'list'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate()
        
        if process.returncode == 0:
            source.reply('§a已安装的Python包:§r')
            for line in stdout.strip().split('\n'):
                if 'Package' not in line and '------' not in line:  # 跳过标题行
                    source.reply(f'§7{line}§r')
            server.logger.info('成功列出已安装的Python包')
        else:
            source.reply(f'§c获取包列表失败§r')
            source.reply(f'§7错误信息: {stderr.strip()}§r')
            server.logger.error(f'获取包列表失败, 错误: {stderr.strip()}')
    except Exception as e:
        source.reply(f'§c执行列表命令时出错: §b{str(e)}§r')
        server.logger.error(f'执行列表命令时出错: {str(e)}')
