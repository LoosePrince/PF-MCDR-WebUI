import datetime
import logging
import re
import sys
import threading
import time

from guguwebui.utils.types import StateType


def clean_color_codes(text):
    """清理 Minecraft 颜色代码和 ANSI 转义序列"""
    # 清理 Minecraft 颜色代码（§ 后面跟着一个字符）
    text = re.sub(r'§[0-9a-fk-or]', '', text)

    # 清理 ANSI 颜色代码
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', text)

    # 清理类似 [37m, [2m, [0m 等形式的 ANSI 代码
    text = re.sub(r'\[\d+m', '', text)

    # 清理其他形式的ANSI代码，包括组合形式如[37m[2m
    text = re.sub(r'\[\d+(?:;\d+)*m', '', text)
    text = re.sub(r'\[0m', '', text)

    # 清理可能残留的其他ANSI代码格式
    text = re.sub(r'(?<!\[)\[\d*[a-z](?!\])', '', text)

    return text

class LogHandler(logging.Handler):
    """自定义日志处理器，用于捕获MCDR和服务器日志"""

    def __init__(self, log_watcher):
        super().__init__()
        self.log_watcher = log_watcher
        self.setLevel(logging.DEBUG)

    def emit(self, record: logging.LogRecord):
        """处理日志记录"""
        try:
            # 直接添加到共享日志，利用 record 的元数据
            self.log_watcher._add_raw_log(
                message=record.getMessage(),
                level=record.levelname,
                source=record.name,
                timestamp=record.created
            )
        except Exception:
            self.handleError(record)

class MCServerLogCapture(threading.Thread):
    """专门用于捕获Minecraft服务器日志的线程"""

    def __init__(self, log_watcher):
        super().__init__(name="MC-Log-Capture")
        self.daemon = True
        self.running = True
        self.log_watcher = log_watcher

    def stop(self):
        """停止捕获线程"""
        self.running = False

    def on_info(self, server, info):
        """处理新收到的服务器信息"""
        # 获取内容并清理颜色代码
        content = getattr(info, 'content', '')
        if not content:
            return

        source = getattr(info, 'source', 'Unknown')

        # 添加到共享日志
        self.log_watcher._add_raw_log(
            message=content,
            level="INFO",
            source=str(source)
        )

    def run(self):
        """线程主循环"""
        while self.running:
            time.sleep(0.1)

class StdoutInterceptor:
    """拦截标准输出和标准错误流的类"""

    def __init__(self, log_watcher):
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.log_watcher = log_watcher
        self.buffer = ""
        self.lock = threading.Lock()
        self.enabled = False

    def start_interception(self):
        if self.enabled: return
        self.enabled = True

        class InterceptedStream:
            def __init__(self, original_stream, interceptor):
                self.original_stream = original_stream
                self.interceptor = interceptor

            def write(self, message):
                self.original_stream.write(message)
                if self.interceptor.enabled:
                    self.interceptor.process_output(message)

            def flush(self):
                self.original_stream.flush()

            def __getattr__(self, name):
                return getattr(self.original_stream, name)

        sys.stdout = InterceptedStream(self.original_stdout, self)
        sys.stderr = InterceptedStream(self.original_stderr, self)

    def stop_interception(self):
        self.enabled = False
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr

    def process_output(self, message):
        with self.lock:
            self.buffer += message
            if '\n' in self.buffer:
                lines = self.buffer.split('\n')
                for line in lines[:-1]:
                    if line.strip():
                        self.log_watcher._add_raw_log(
                            message=line,
                            level="INFO",
                            source="STDOUT"
                        )
                self.buffer = lines[-1]

class LogWatcher:
    # 使用 sys 模块存储共享状态，确保在插件重载时日志不会丢失
    @staticmethod
    def _get_shared_state() -> StateType:
        if not hasattr(sys, '_guguwebui_log_state'):
            sys._guguwebui_log_state = {
                'logs': [], # 存储原始字典: {timestamp, level, source, message, counter}
                'counter': 0,
                'hashes': set(), # 存储 message 的哈希，用于简单去重
                'lock': threading.Lock(),
                'intercepted': False,
                'original_emit': None
            }
        return sys._guguwebui_log_state

    def __init__(self, server_interface=None):
        self.server_interface = server_interface
        self._patterns = []
        self._result = {}
        self._watching = False

        state = self._get_shared_state()
        self._shared_lock = state['lock']

        # 实例专用的处理器
        self.mcdr_log_handler = LogHandler(self)
        self.mc_log_capture = MCServerLogCapture(self)
        self.stdout_interceptor = StdoutInterceptor(self)

        # 初始化捕获
        self._setup_intercepted_emit()
        self.stdout_interceptor.start_interception()
        self.mc_log_capture.start()

    def _setup_intercepted_emit(self):
        state = self._get_shared_state()
        if state['intercepted']: return
        state['intercepted'] = True

        state['original_emit'] = logging.StreamHandler.emit

        def intercepted_emit(self_handler, record):
            try:
                result = state['original_emit'](self_handler, record)
                # 仅拦截非 MCDR 核心的日志，或者根据需要筛选
                # MCDR 核心日志通常会通过 on_mcdr_info 捕获，这里拦截可以捕获其他插件或库的日志
                name = record.name.lower()
                if 'mcdreforged' in name or 'mcdr' in name or 'fastapi' in name or 'uvicorn' in name:
                    self._add_raw_log(
                        message=record.getMessage(),
                        level=record.levelname,
                        source=record.name,
                        timestamp=record.created
                    )
                return result
            except Exception:
                return state['original_emit'](self_handler, record)

        logging.StreamHandler.emit = intercepted_emit

    def _add_raw_log(self, message, level="INFO", source="Unknown", timestamp=None):
        """添加原始日志数据，带去重和容量限制"""
        if not message or not message.strip():
            return False

        message = clean_color_codes(message)
        # 简单的基于内容和时间的去重（1秒内相同的消息视为重复）
        now = timestamp or time.time()
        log_hash = hash((message, int(now)))

        state = self._get_shared_state()
        with state['lock']:
            if log_hash in state['hashes']:
                return False

            state['hashes'].add(log_hash)
            if len(state['hashes']) > 10000:
                state['hashes'].clear()

            state['counter'] += 1
            log_entry = {
                "counter": state['counter'],
                "timestamp": now,
                "level": level,
                "source": str(source),
                "message": message
            }
            state['logs'].append(log_entry)

            if len(state['logs']) > 5000:
                state['logs'].pop(0)
            return True

    @staticmethod
    def _format_log_entry(entry):
        """在返回时动态格式化日志"""
        dt = datetime.datetime.fromtimestamp(entry["timestamp"])
        ts_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        # 构建类似 MCDR 的标准格式
        return f"[#{entry['counter']}] [{ts_str}] [{entry['source']}/{entry['level']}] {entry['message']}"

    def get_merged_logs(self, max_lines=500):
        state = self._get_shared_state()
        with state['lock']:
            total_lines = len(state['logs'])
            start_idx = max(0, total_lines - max_lines)

            log_entries = []
            for i in range(start_idx, total_lines):
                entry = state['logs'][i]
                formatted_content = self._format_log_entry(entry)

                log_entries.append({
                    "line_number": i,
                    "counter": entry["counter"],
                    "timestamp": datetime.datetime.fromtimestamp(entry["timestamp"]).strftime("%Y-%m-%d %H:%M:%S"),
                    "content": formatted_content + '\n',
                    "source": "all",
                    "is_command": "InfoSource.CONSOLE" in entry["source"] and "!!" in entry["message"]
                })

            return {
                "logs": log_entries,
                "total_lines": total_lines,
                "start_line": start_idx,
                "end_line": total_lines
            }

    def get_logs_since_counter(self, last_counter=0, max_lines=100):
        state = self._get_shared_state()
        with state['lock']:
            new_logs = []
            for i, entry in enumerate(state['logs']):
                if entry["counter"] > last_counter:
                    formatted_content = self._format_log_entry(entry)
                    new_logs.append({
                        "line_number": i,
                        "counter": entry["counter"],
                        "timestamp": datetime.datetime.fromtimestamp(entry["timestamp"]).strftime("%Y-%m-%d %H:%M:%S"),
                        "content": formatted_content + '\n',
                        "source": "all",
                        "is_command": "InfoSource.CONSOLE" in entry["source"] and "!!" in entry["message"]
                    })
                    if len(new_logs) >= max_lines:
                        break

            return {
                "logs": new_logs,
                "total_lines": len(state['logs']),
                "last_counter": new_logs[-1]["counter"] if new_logs else last_counter,
                "new_logs_count": len(new_logs)
            }

    def on_mcdr_info(self, server, info):
        if hasattr(info, 'content'):
            source = getattr(info, 'source', 'MCDR')
            self._add_raw_log(
                message=info.content,
                level="INFO",
                source=source
            )

    def on_server_output(self, server, info):
        if hasattr(info, 'content'):
            source = getattr(info, 'source', 'Server')
            self._add_raw_log(
                message=info.content,
                level="INFO",
                source=source
            )

    def _setup_log_capture(self):
        """手动触发 MCDR 日志钩子"""
        try:
            from .mcdr_adapter import MCDRAdapter
            if self.server_interface:
                mcdr_logger = MCDRAdapter.get_mcdr_logger(self.server_interface)
                if mcdr_logger and self.mcdr_log_handler not in mcdr_logger.handlers:
                    mcdr_logger.addHandler(self.mcdr_log_handler)
        except Exception:
            pass

    def stop(self):
        self.stdout_interceptor.stop_interception()
        self.mc_log_capture.stop()
        try:
            from .mcdr_adapter import MCDRAdapter
            if self.server_interface:
                mcdr_logger = MCDRAdapter.get_mcdr_logger(self.server_interface)
                if mcdr_logger:
                    mcdr_logger.removeHandler(self.mcdr_log_handler)
        except Exception:
            pass
