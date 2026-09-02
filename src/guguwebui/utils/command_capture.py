"""
直接执行命令并获取执行结果（输出捕获）
========================================

在不依赖 RCON 的前提下，于 MCDR 进程内执行命令并捕获命令的真实输出。
实现原理参考 mcdr_mcp_service/tool/command_logger.py：

- MCDR 命令（以 ``!`` 开头）：
  通过 ``server.execute_command(command, source=捕获源)`` 以自定义
  :class:`~mcdreforged.command.command_source.CommandSource`（权限等级 4）执行。
  插件命令的回复会回调到该捕获源的 ``reply`` 方法，因此可以直接在进程内收集
  回复文本，无需解析日志文件，也不需要服务器开启 RCON。

- Minecraft 服务器命令：
  通过 ``server.execute(command)`` 把命令写入服务器的标准输入；服务器打印的输出
  经 MCDR 的 ``GENERAL_INFO`` 事件（``info.is_from_server``）回传。每次执行会注册
  一个临时“静默窗口”监听：收到输出后若在静默时长内没有新输出，则认为本次命令的
  结果输出结束；超时则返回当前已收集到的输出作为兜底。

与 RCON 相比：这里是 MCDR 进程内的直连通道，服务器无需启用 RCON，只要 MCDR
能正常向服务器写入命令 / 读取服务器标准输出即可使用。调用方（如 send_command）
应保持 RCON 的优先级高于本功能，仅在 RCON 不可用时回退到本模块。

线程模型：
- ``execute_command`` / ``execute`` 与等待循环运行在 ``asyncio.to_thread`` 的工作线程；
- MCDR 事件回调运行在 MCDR 的 executor 线程，只做加锁追加，不阻塞；
- 每个等待器是独立的，支持并发多次执行。
"""

import asyncio
import threading
import time
from typing import Dict, List, Optional

from mcdreforged.api.all import *  # noqa: F401,F403  CommandSource / MCDRPluginEvents / RTextBase 等

# 等待与静默窗口参数（秒）
MCDR_COMMAND_TIMEOUT = 2.5  # MCDR 命令最大等待时长
MCDR_COMMAND_QUIET = 0.4  # MCDR 命令收到回复后，静默多久视为结束（兼容异步回复）
MCDR_COMMAND_IDLE_NO_OUTPUT = 0.7  # MCDR 命令无任何回复时的提前结束时长
SERVER_COMMAND_TIMEOUT = 3.0  # 服务器命令最大等待时长
SERVER_COMMAND_QUIET = 0.5  # 服务器命令收到输出后，静默多久视为结束
# 单次执行的总硬超时：命令回调本身执行过久（如网络/重载类命令）时兜底，避免 HTTP 请求悬挂
EXECUTION_MAX_WAIT = 10.0

# 返回内容上限，避免一次抓取过多输出撑爆响应
MAX_CAPTURED_LINES = 200
MAX_CAPTURED_CHARS = 12000


def _to_plain_text(message) -> str:
    """把回复消息转成纯文本，兼容 RTextBase / str 等类型。"""
    if hasattr(message, "to_plain_text"):
        try:
            return message.to_plain_text()
        except Exception:
            pass
    return str(message)


class CapturingCommandSource(CommandSource):
    """自定义命令源：把命令回复收集到等待器中，而不是输出到控制台。"""

    def __init__(self, server, waiter: "_OutputWaiter"):
        super().__init__()
        self.server = server
        self.waiter = waiter

    def get_server(self):
        return self.server

    def get_permission_level(self) -> int:
        # 与 MCDR 控制台一致的权限等级
        return 4

    def reply(self, message, **kwargs) -> None:
        plain_text = _to_plain_text(message)
        self.waiter.append(plain_text)
        # 保留旧行为：把回复同时打印到 MCDR 控制台/日志，使终端日志流中仍能看到回复
        # （这与控制台执行命令时插件的 reply 行为一致，仅额外做了一次捕获）
        try:
            self.server.logger.info(message)
        except Exception:
            try:
                self.server.logger.info(plain_text)
            except Exception:
                pass


class _OutputWaiter:
    """单个执行任务的输出收集器，可被 MCDR 线程安全写入。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.lines: List[str] = []
        self.received = False
        self.last_output_time: Optional[float] = None

    def append(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        with self.lock:
            if len(self.lines) >= MAX_CAPTURED_LINES:
                return
            self.lines.append(text)
            self.received = True
            self.last_output_time = time.monotonic()

    def snapshot(self) -> List[str]:
        with self.lock:
            return list(self.lines)


# 模块级共享状态：命令输出捕获器的等待器与监听注册在所有实例间共享。
# 这样即使插件在同一加载周期内多次 init_app / 重建 ServerService，
# 命令输出也只会（也只可能）被分发到同一个等待器池。
_shared_lock = threading.Lock()
_shared_waiters: Dict[int, "_OutputWaiter"] = {}
_registered_server_ids = set()


class CommandCapture:
    """
    命令输出捕获器。

    一个 MCDR server 实例上只注册一次 ``GENERAL_INFO`` 监听（以模块级集合去重，
    避免插件在同一加载周期内多次 init_app / 重建服务时重复注册），捕获到的输出
    统一分发到模块级等待器池，因此创建多个 CommandCapture 实例也是安全的。
    """

    def __init__(self, server):
        self.server = server
        self.logger = getattr(server, "logger", None)
        self._ensure_listener()

    # ---------------------------------------------------------------- #
    # 监听注册与事件分发
    # ---------------------------------------------------------------- #
    def _ensure_listener(self) -> None:
        with _shared_lock:
            if id(self.server) in _registered_server_ids:
                return
            try:
                self.server.register_event_listener(
                    MCDRPluginEvents.GENERAL_INFO, self._on_server_output
                )
                _registered_server_ids.add(id(self.server))
            except Exception as e:
                if self.logger is not None:
                    self.logger.warning(f"注册命令输出监听失败，无法捕获服务器命令输出: {e}")
                _registered_server_ids.add(id(self.server))

    def _register_waiter(self, waiter: "_OutputWaiter") -> int:
        with _shared_lock:
            token = id(waiter)
            _shared_waiters[token] = waiter
            return token

    def _unregister_waiter(self, token: int) -> None:
        with _shared_lock:
            _shared_waiters.pop(token, None)

    def _on_server_output(self, server, info) -> None:
        """MCDR GENERAL_INFO 回调：仅关注来自 Minecraft 服务器的输出。"""
        try:
            if info is None or not getattr(info, "is_from_server", False):
                return
            content = getattr(info, "content", None)
            if not content:
                content = getattr(info, "raw_content", None)
            if not content:
                return
            with _shared_lock:
                waiters = list(_shared_waiters.values())
            for waiter in waiters:
                waiter.append(str(content))
        except Exception:
            pass

    # ---------------------------------------------------------------- #
    # 对外接口
    # ---------------------------------------------------------------- #
    async def execute_mcdr_command(self, command: str, *, timeout: float = MCDR_COMMAND_TIMEOUT) -> Dict:
        """
        直接执行 MCDR 命令（``!`` 开头）并捕获其回复。

        :return: {"success", "responses", "output", "captured", "timed_out"}
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._execute_mcdr_command_blocking, command, timeout),
                timeout=EXECUTION_MAX_WAIT,
            )
        except asyncio.TimeoutError:
            return self._timeout_result("MCDR 命令执行超时")

    async def execute_server_command(
        self, command: str, *, timeout: float = SERVER_COMMAND_TIMEOUT
    ) -> Dict:
        """
        直接执行 Minecraft 服务器命令（已去掉 ``/`` 前缀）并捕获服务器输出。

        :return: {"success", "responses", "output", "captured", "timed_out"}
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._execute_server_command_blocking, command, timeout),
                timeout=EXECUTION_MAX_WAIT,
            )
        except asyncio.TimeoutError:
            return self._timeout_result("服务器命令执行超时")

    @staticmethod
    def _timeout_result(reason: str) -> Dict:
        return {
            "success": False,
            "error": reason,
            "responses": [],
            "output": "",
            "captured": False,
            "timed_out": True,
        }

    # ---------------------------------------------------------------- #
    # 同步实现（在 to_thread 工作线程中运行）
    # ---------------------------------------------------------------- #
    def _execute_mcdr_command_blocking(self, command: str, timeout: float) -> Dict:
        waiter = _OutputWaiter()
        token = self._register_waiter(waiter)
        try:
            source = CapturingCommandSource(self.server, waiter)
            # 同步执行：命令回调产生的回复会进入 waiter
            self.server.execute_command(command, source=source)
            timed_out = self._wait_for_output(
                waiter,
                timeout=timeout,
                quiet=MCDR_COMMAND_QUIET,
                idle_no_output=MCDR_COMMAND_IDLE_NO_OUTPUT,
            )
            return self._finalize(waiter, timed_out)
        except Exception as e:
            if self.logger is not None:
                self.logger.error(f"执行 MCDR 命令失败: {command} -> {e}")
            return {
                "success": False,
                "error": str(e),
                "responses": [],
                "output": "",
                "captured": False,
                "timed_out": False,
            }
        finally:
            self._unregister_waiter(token)

    def _execute_server_command_blocking(self, command: str, timeout: float) -> Dict:
        waiter = _OutputWaiter()
        token = self._register_waiter(waiter)
        try:
            # 写入服务器标准输入
            self.server.execute(command)
            timed_out = self._wait_for_output(
                waiter,
                timeout=timeout,
                quiet=SERVER_COMMAND_QUIET,
                idle_no_output=timeout,
            )
            return self._finalize(waiter, timed_out)
        except Exception as e:
            if self.logger is not None:
                self.logger.error(f"执行服务器命令失败: {command} -> {e}")
            return {
                "success": False,
                "error": str(e),
                "responses": [],
                "output": "",
                "captured": False,
                "timed_out": False,
            }
        finally:
            self._unregister_waiter(token)

    def _wait_for_output(
        self,
        waiter: "_OutputWaiter",
        *,
        timeout: float,
        quiet: float,
        idle_no_output: float,
    ) -> bool:
        """
        阻塞等待命令输出结束。

        - 已收到输出：最近一次输出后静默超过 ``quiet`` 视为结束；
        - 未收到输出：MCDR 命令等待 ``idle_no_output`` 后提前结束；
          服务器命令一直等到 ``timeout``。
        - 无论哪种情况，最长不超过 ``timeout``。

        :return: 是否“超时兜底”（True 表示一直等到硬超时仍未安静；
          False 表示输出已静默结束或提前无输出结束）
        """
        start = time.monotonic()
        while True:
            now = time.monotonic()
            with waiter.lock:
                received = waiter.received
                last_output_time = waiter.last_output_time
            if received and last_output_time is not None:
                if now - last_output_time >= quiet:
                    return False  # 输出已安静下来，正常结束
            else:
                if now - start >= idle_no_output:
                    return False  # 一直没有输出，提前结束
            if now - start >= timeout:
                return True  # 超时兜底
            time.sleep(0.02)

    def _finalize(self, waiter: "_OutputWaiter", timed_out: bool) -> Dict:
        responses = waiter.snapshot()
        captured = bool(responses)
        output = ""
        if responses:
            joined = "\n".join(responses)
            if len(joined) > MAX_CAPTURED_CHARS:
                output = joined[:MAX_CAPTURED_CHARS]
                output += f"\n…(输出过长，已截断，共 {len(responses)} 行)"
            else:
                output = joined
        return {
            "success": True,
            "responses": responses,
            "output": output,
            "captured": captured,
            "timed_out": timed_out,
        }
