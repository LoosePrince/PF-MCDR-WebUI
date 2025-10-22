import importlib.util
import subprocess
import sys
from mcdreforged.api.all import PluginServerInterface

# 插件依赖包列表
REQUIRED_PACKAGES = [
    'fastapi>=0.68.0',
    'javaproperties',
    'mcdreforged>=2.3.0',
    'passlib',
    'pydantic',
    'requests',
    'ruamel.yaml',
    'starlette',
    'uvicorn>=0.15.0',
    'itsdangerous',
    'jinja2',
    'argon2_cffi',
    'python-multipart',
    'typing-extensions',
    'aiohttp'
]


def is_package_installed(package_name: str) -> bool:
    """
    检查指定的包是否已安装
    """
    try:
        # 尝试导入包
        spec = importlib.util.find_spec(package_name)
        return spec is not None
    except (ImportError, ModuleNotFoundError, AttributeError):
        return False


def install_package(package: str) -> bool:
    """
    使用pip安装指定的包
    返回True表示安装成功，False表示安装失败
    """
    try:
        # 构造pip安装命令
        cmd = [sys.executable, '-m', 'pip', 'install', package, '--quiet', '--no-warn-script-location']
        
        # 执行安装命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        
        if result.returncode == 0:
            return True
        else:
            # 如果安装失败，尝试升级pip后重试
            if 'pip' in result.stderr.lower() or 'upgrade' in result.stderr.lower():
                try:
                    # 尝试升级pip
                    upgrade_cmd = [sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip', '--quiet']
                    upgrade_result = subprocess.run(
                        upgrade_cmd,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    
                    if upgrade_result.returncode == 0:
                        # pip升级成功，重试安装包
                        retry_result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            timeout=300
                        )
                        return retry_result.returncode == 0
                except Exception:
                    pass
            
            return False
        
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def check_and_install_dependencies(server: PluginServerInterface):
    """
    检查并安装缺失的依赖包
    """
    server.logger.info("正在检查插件依赖...")
    missing_packages = []
    
    # 包名映射表，用于处理pip包名与导入名不一致的情况
    package_import_mapping = {
        'requests': 'requests',
        'ruamel.yaml': 'ruamel',
        'python-multipart': 'multipart',
        'argon2_cffi': 'argon2',
        'typing-extensions': 'typing_extensions',
        'mcdreforged': 'mcdreforged',
        'fastapi': 'fastapi',
        'javaproperties': 'javaproperties',
        'passlib': 'passlib',
        'pydantic': 'pydantic',
        'starlette': 'starlette',
        'uvicorn': 'uvicorn',
        'itsdangerous': 'itsdangerous',
        'jinja2': 'jinja2',
        'aiohttp': 'aiohttp',
        'mcstatus': 'mcstatus'
    }
    
    for package_spec in REQUIRED_PACKAGES:
        # 提取包名（去除版本限制）
        package_name = package_spec.split('>=')[0].split('==')[0].split('[')[0].lower()
        
        # 获取实际的导入名
        import_name = package_import_mapping.get(package_name, package_name)
        
        # 检查包是否已安装
        if not is_package_installed(import_name):
            missing_packages.append(package_spec)
            server.logger.warning(f"缺少依赖包: {package_spec}")
    
    if missing_packages:
        server.logger.info(f"发现 {len(missing_packages)} 个缺失的依赖包，正在自动安装...")
        
        success_count = 0
        failed_packages = []
        
        for package in missing_packages:
            try:
                server.logger.info(f"正在安装: {package}")
                result = install_package(package)
                
                if result:
                    success_count += 1
                    server.logger.info(f"成功安装: {package}")
                else:
                    failed_packages.append(package)
                    server.logger.error(f"安装失败: {package}")
                    
            except Exception as e:
                failed_packages.append(package)
                server.logger.error(f"安装 {package} 时发生异常: {e}")
        
        # 安装结果总结
        if success_count > 0:
            server.logger.info(f"成功安装 {success_count} 个依赖包")
        
        if failed_packages:
            server.logger.error(f"{len(failed_packages)} 个包安装失败:")
            for pkg in failed_packages:
                server.logger.error(f"  - {pkg}")
            server.logger.error("请手动安装失败的包或检查网络连接")
            server.logger.error("插件可能无法正常工作，直到所有依赖都安装完成")
        else:
            server.logger.info("所有依赖包检查完成")
    else:
        server.logger.info("所有必需的依赖包都已安装") 