"""
命令直接执行 + 输出捕获（无需 RCON）相关测试

覆盖：
- CommandCapture：MCDR 命令回复捕获与“同时打印到 MCDR 日志”；
  服务器命令输出的静默窗口捕获；无回复命令的快速返回；监听不重复注册。
- ServerService.send_command：RCON 优先级高于直接执行；RCON 失败/未启用时
  回退直接执行捕获；MCDR 命令无需 RCON；换行注入与服务器未运行的边界处理。
"""

import asyncio
import threading
import time
import unittest

from guguwebui.services.server_service import ServerService
from guguwebui.utils.command_capture import CommandCapture


class FakeInfo:
    def __init__(self, content, from_server=True):
        self.content = content
        self.raw_content = content
        self.is_from_server = from_server


class FakeLogger:
    def __init__(self):
        self.prints = []

    def info(self, message, *args, **kwargs):
        self.prints.append(str(message))

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class FakeRText:
    """模拟 RTextBase：回复时应转换为纯文本供捕获。"""

    def to_plain_text(self):
        return "plain-text-answer"


class FakeServer:
    def __init__(self):
        self.listeners = {}
        self.logger = FakeLogger()
        self.running = True
        self.rcon_running = False
        self.rcon_calls = []

    def register_event_listener(self, event, callback):
        self.listeners[event] = callback

    def fire(self, info):
        for callback in list(self.listeners.values()):
            callback(self, info)

    def execute_command(self, command, source=None):
        if source is None:
            return
        if command == "!!MCDR status":
            source.reply("MCDR status line")
        elif command == "!!MCDR rtext":
            source.reply(FakeRText())
        # 其余命令不回复

    def execute(self, command):
        def echo():
            time.sleep(0.1)
            self.fire(FakeInfo(f"[00:00:00] [Server thread/INFO]: answer of {command}"))

        threading.Thread(target=echo, daemon=True).start()

    def is_server_running(self):
        return self.running

    def is_rcon_running(self):
        return self.rcon_running

    def rcon_query(self, command):
        self.rcon_calls.append(command)
        if command == "boom":
            raise RuntimeError("rcon error")
        return f"RCON-ANSWER:{command}"


def run(coro):
    return asyncio.run(coro)


class CommandCaptureTest(unittest.TestCase):
    def setUp(self):
        # 每个用例使用新的 FakeServer 对象，清理模块级注册记录避免对象 id 复用
        from guguwebui.utils import command_capture as command_capture_module

        command_capture_module._registered_server_ids.clear()
        self.server = FakeServer()
        self.capture = CommandCapture(self.server)

    def test_mcdr_command_reply_captured_and_echoed_to_logger(self):
        result = run(self.capture.execute_mcdr_command("!!MCDR status"))
        self.assertTrue(result["success"])
        self.assertTrue(result["captured"])
        self.assertIn("MCDR status line", result["output"])
        # 回复同时写入 MCDR 日志，保留终端日志流
        self.assertIn("MCDR status line", self.server.logger.prints)

    def test_mcdr_reply_rtext_converted_to_plain_text(self):
        result = run(self.capture.execute_mcdr_command("!!MCDR rtext"))
        self.assertTrue(result["captured"])
        self.assertIn("plain-text-answer", result["output"])

    def test_silent_mcdr_command_returns_quickly_without_output(self):
        start = time.monotonic()
        result = run(self.capture.execute_mcdr_command("!!MCDR silent"))
        elapsed = time.monotonic() - start
        self.assertTrue(result["success"])
        self.assertFalse(result["captured"])
        # 无回复命令应提前返回（idle 窗口），而非等满硬超时
        self.assertLess(elapsed, 2.0)

    def test_server_command_output_captured_after_quiet_window(self):
        result = run(self.capture.execute_server_command("list"))
        self.assertTrue(result["success"])
        self.assertTrue(result["captured"])
        self.assertIn("answer of list", result["output"])

    def test_listener_registered_only_once(self):
        self.assertEqual(len(self.server.listeners), 1)
        CommandCapture(self.server)
        self.assertEqual(len(self.server.listeners), 1)


class SendCommandFlowTest(unittest.TestCase):
    def setUp(self):
        from guguwebui.utils import command_capture as command_capture_module

        command_capture_module._registered_server_ids.clear()
        self.server = FakeServer()
        self.service = ServerService(self.server)

    def test_rcon_has_higher_priority_than_direct_capture(self):
        self.server.rcon_running = True
        result = run(self.service.send_command("/list"))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["feedback"], "RCON-ANSWER:list")
        self.assertIn("via RCON", result["message"])
        # 普通文本命令同样视为服务器命令，RCON 优先
        result = run(self.service.send_command("list"))
        self.assertEqual(result["feedback"], "RCON-ANSWER:list")
        self.assertEqual(self.server.rcon_calls, ["list", "list"])

    def test_fallback_to_direct_capture_when_rcon_fails(self):
        self.server.rcon_running = True
        result = run(self.service.send_command("/boom"))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result.get("capture"), "direct")
        self.assertIn("answer of boom", result["feedback"])

    def test_direct_capture_when_rcon_disabled(self):
        result = run(self.service.send_command("/list"))
        self.assertEqual(result.get("capture"), "direct")
        self.assertIn("answer of list", result["feedback"])

    def test_mcdr_command_executed_without_rcon(self):
        result = run(self.service.send_command("!!MCDR status"))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result.get("capture"), "direct")
        self.assertIn("MCDR status line", result["feedback"])

    def test_newline_injection_rejected(self):
        result = run(
            self.service.send_command("/say hi\n!!MCDR plugin unload guguwebui")
        )
        self.assertEqual(result["status"], "error")

    def test_stopped_server_returns_without_capture(self):
        self.server.running = False
        start = time.monotonic()
        result = run(self.service.send_command("/list"))
        elapsed = time.monotonic() - start
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["feedback"], "")
        self.assertIn("服务器未运行", result.get("note", ""))
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
