import asyncio
import ipaddress
import socket
import threading
import time

import uvicorn
from fastapi import Request, status
from fastapi.responses import RedirectResponse
from mcdreforged.api.all import PluginServerInterface as ServerInterface


# 辅助函数：根据当前应用路径生成正确的重定向URL
def get_redirect_url(request, path: str) -> str:
    """根据当前应用路径生成正确的重定向URL"""
    root_path = request.scope.get("root_path", "")
    if root_path:
        return f"{root_path}{path}"
    else:
        return path


def format_host_for_url(host: str) -> str:
    """将 host 格式化为 URL 中可用的形式，IPv6 地址需加方括号。"""
    if not host:
        return host
    try:
        ip = ipaddress.ip_address(host)
        return f"[{host}]" if ip.version == 6 else host
    except ValueError:
        return host


from .constant import *

# Github: https://github.com/zauberzeug/nicegui/issues/1956
class ThreadedUvicorn:
    def __init__(self, server: ServerInterface, config: uvicorn.Config):
        self.mcdr_server = server
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(daemon=True, target=self.server.run)
        self._retry_count = 0
        self._max_retries = 3

    def start(self):
        try:
            self.thread.start()
            try:
                asyncio.run(self.wait_for_started())
            except ConnectionResetError as e:
                self.mcdr_server.logger.warning(f"启动过程中连接重置: {e}")
                if self._retry_count < self._max_retries:
                    self._retry_count += 1
                    self.stop()
                    self.start()
                else:
                    self.mcdr_server.logger.error(f"重试次数已达上限({self._max_retries}次)，无法恢复")
                    raise
        except Exception as e:
            self.mcdr_server.logger.error(f"启动服务器时发生异常: {e}")
            raise

    async def wait_for_started(self):
        try:
            while not self.server.started:
                await asyncio.sleep(0.1)
        except ConnectionResetError:
            self.mcdr_server.logger.warning("等待服务器启动时连接被重置")
            raise

    def stop(self):
        try:
            self.mcdr_server.logger.debug("正在停止Web服务器...")
            if self.thread.is_alive():
                # 设置退出标志
                self.server.should_exit = True
                self.mcdr_server.logger.debug("已设置服务器退出标志")

                try:
                    # 尝试关闭SSL连接（如果有）
                    self._close_ssl_connections()

                    # 使用超时机制等待线程终止
                    max_wait_time = 5  # 最多等待5秒
                    start_time = time.time()
                    self.mcdr_server.logger.debug("等待服务器线程退出...")

                    while self.thread.is_alive():
                        if time.time() - start_time > max_wait_time:
                            self.mcdr_server.logger.warning("服务器线程超时未能正常退出，准备强制终止")
                            break
                        time.sleep(0.1)  # 小间隔检查，减少CPU使用率

                    # 如果线程还活着，尝试更强硬的方式处理
                    if self.thread.is_alive():
                        self.mcdr_server.logger.warning("尝试强制终止服务器线程")
                        self._force_thread_termination()
                except ConnectionResetError:
                    self.mcdr_server.logger.warning("关闭服务器时连接被重置，强制终止线程")
                    self._force_thread_termination()
                except Exception as e:
                    self.mcdr_server.logger.error(f"等待线程终止时发生异常: {e}")
                    self._force_thread_termination()
        except Exception as e:
            self.mcdr_server.logger.error(f"停止服务器时发生异常: {e}")
        finally:
            # 确保即使出现异常也不会阻塞主进程
            self.mcdr_server.logger.debug("Web服务器停止流程完成")

    def _close_ssl_connections(self):
        """尝试关闭所有SSL连接"""
        try:
            # 检查是否是SSL模式
            if hasattr(self.server.config, 'ssl_certfile') and self.server.config.ssl_certfile:
                self.mcdr_server.logger.debug("检测到SSL模式，尝试关闭SSL连接...")

                # 尝试通过关闭服务器的socket来释放端口
                try:
                    if hasattr(self.server, 'servers'):
                        for server in self.server.servers:
                            if hasattr(server, 'sockets') and server.sockets:
                                for sock in server.sockets:
                                    try:
                                        self.mcdr_server.logger.debug(f"关闭服务器socket: {sock}")
                                        sock.close()
                                    except Exception as e:
                                        self.mcdr_server.logger.debug(f"关闭socket时出错: {e}")

                    # 作为最后手段，尝试通过创建新连接来关闭旧连接
                    host = self.server.config.host
                    port = self.server.config.port
                    # 若绑定为 0.0.0.0 / ::，连接本机时使用 127.0.0.1 / ::1
                    connect_host = "::1" if host == "::" else ("127.0.0.1" if host == "0.0.0.0" else host)

                    try:
                        import ssl
                        context = ssl._create_unverified_context()
                        s = socket.create_connection((connect_host, port), timeout=1)
                        ssl_sock = context.wrap_socket(s)
                        ssl_sock.close()
                    except Exception as e:
                        self.mcdr_server.logger.debug(f"创建SSL连接时出错: {e}")
                except Exception as e:
                    self.mcdr_server.logger.debug(f"关闭服务器socket时出错: {e}")

                self.mcdr_server.logger.debug("SSL连接关闭尝试完成")
        except Exception as e:
            self.mcdr_server.logger.error(f"关闭SSL连接时发生错误: {e}")

    def _force_thread_termination(self):
        """强制终止服务器线程的最后手段"""
        try:
            # 记录警告信息
            self.mcdr_server.logger.warning("执行强制线程终止操作")

            # 尝试通过socket方式关闭服务器
            try:
                host = self.server.config.host
                port = self.server.config.port
                connect_host = "::1" if host == "::" else ("127.0.0.1" if host == "0.0.0.0" else host)
                try:
                    ip = ipaddress.ip_address(connect_host)
                    family = socket.AF_INET6 if ip.version == 6 else socket.AF_INET
                except ValueError:
                    family = socket.AF_INET
                for _ in range(3):
                    try:
                        s = socket.socket(family, socket.SOCK_STREAM)
                        s.settimeout(1)
                        s.connect((connect_host, port))
                        s.close()
                    except Exception:
                        break

                self.mcdr_server.logger.debug("已发送关闭触发连接")
            except Exception as e:
                self.mcdr_server.logger.debug(f"发送关闭触发连接失败: {e}")

            # 尝试直接访问和清理uvicorn服务器内部对象
            try:
                if hasattr(self.server, 'servers'):
                    for server in self.server.servers:
                        # 尝试关闭server
                        try:
                            if hasattr(server, 'close'):
                                server.close()
                            if hasattr(server, 'shutdown'):
                                server.shutdown()
                        except Exception:
                            pass
            except Exception as e:
                self.mcdr_server.logger.debug(f"清理uvicorn服务器对象失败: {e}")

            # 替换线程对象
            self.thread = threading.Thread(daemon=True)
            self.mcdr_server.logger.debug("线程对象已替换")

            # 强制收集垃圾
            import gc
            gc.collect()

        except Exception as e:
            self.mcdr_server.logger.error(f"强制终止线程时发生错误: {e}")

# 添加一个修复ConnectionResetError的工具函数
def patch_asyncio(server: ServerInterface):
    """
    为asyncio添加异常处理补丁，防止ConnectionResetError导致程序崩溃
    """
    # 保存原始的_ProactorBasePipeTransport._call_connection_lost方法
    try:
        import asyncio.proactor_events as proactor_events
        original_call_connection_lost = proactor_events._ProactorBasePipeTransport._call_connection_lost

        def patched_call_connection_lost(self, exc):
            try:
                original_call_connection_lost(self, exc)
            except ConnectionResetError:
                # 忽略连接重置错误
                pass

        # 替换原方法
        proactor_events._ProactorBasePipeTransport._call_connection_lost = patched_call_connection_lost
        server.logger.debug("已应用asyncio连接重置错误修复补丁")
    except Exception as e:
        server.logger.error(f"应用asyncio补丁失败: {e}")

# token verification
def verify_token(request: Request):
    token = request.cookies.get("token")  # get token from cookie

    # 检查是否为 API 请求
    # 兼容挂载模式，检查路径是否包含 /api/
    path = request.url.path
    is_api = "/api/" in path

    if not token:  # token not exists
        request.session.clear()  # 与 db 保持一致：token 无效时清除 session
        if is_api:
            from fastapi import HTTPException
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not logged in")
        return RedirectResponse(url=get_redirect_url(request, "/login"), status_code=status.HTTP_302_FOUND)

    if token not in user_db['token']:  # check token in user_db (e.g. db.json 被清空或 token 已过期)
        request.session.clear()  # 与 db 保持一致：token 无效时清除 session
        if is_api:
            from fastapi import HTTPException
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not logged in")
        return RedirectResponse(url=get_redirect_url(request, "/login"), status_code=status.HTTP_302_FOUND)

    return True
