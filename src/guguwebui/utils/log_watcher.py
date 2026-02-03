import re
import time
import threading
import os
import logging
import sys
from io import StringIO
from typing import List, Dict, Set, Optional, Any
import queue
import datetime

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
    
    def __init__(self):
        super().__init__()
        self.setLevel(logging.DEBUG)
        self.log_queue = queue.Queue()
        self.formatter = logging.Formatter(
            '[%(name)s] [%(asctime)s.%(msecs)03d] [%(threadName)s/%(levelname)s]: %(message)s', 
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 设置已处理的记录ID集合，避免重复处理
        self._handled_records: Set[int] = set()
        # 记录处理锁，保证线程安全
        self._lock = threading.Lock()
        
    def emit(self, record: logging.LogRecord):
        """处理日志记录"""
        # 使用记录ID避免重复处理同一条日志
        record_id = id(record)
        with self._lock:
            if record_id in self._handled_records:
                return
            self._handled_records.add(record_id)
            
            # 限制已处理记录集合大小，避免内存泄漏
            if len(self._handled_records) > 10000:
                self._handled_records.clear()
                
        try:
            # 格式化日志消息
            msg = self.formatter.format(record)
            # 清理颜色代码
            msg = clean_color_codes(msg)
            # 将日志放入队列
            self.log_queue.put(msg)
        except Exception:
            self.handleError(record)
    
    def get_logs(self, max_count=100) -> List[str]:
        """获取捕获的日志，最多返回max_count条"""
        logs = []
        try:
            # 非阻塞获取所有可用的日志
            while len(logs) < max_count:
                try:
                    log = self.log_queue.get_nowait()
                    logs.append(log)
                except queue.Empty:
                    break
        except Exception as e:
            logs.append(f"获取日志出错: {str(e)}")
        return logs
    
    def clear_logs(self):
        """清空日志队列"""
        try:
            while not self.log_queue.empty():
                self.log_queue.get_nowait()
        except Exception:
            pass

class MCServerLogCapture(threading.Thread):
    """专门用于捕获Minecraft服务器日志的线程"""
    
    def __init__(self):
        super().__init__(name="MC-Log-Capture")
        self.daemon = True  # 设为守护线程，不阻止程序退出
        self.running = True
        self.log_queue = queue.Queue()
        
        # 存储上一次收到的信息
        self._last_info = None
        self._lock = threading.Lock()
        
        # 父 LogWatcher 的引用
        self.log_watcher = None
        
    def set_log_watcher(self, log_watcher):
        """设置父 LogWatcher 的引用"""
        self.log_watcher = log_watcher
        
    def stop(self):
        """停止捕获线程"""
        self.running = False
        
    def on_info(self, server, info):
        """处理新收到的服务器信息"""
        with self._lock:
            # 获取日志类型和来源
            source = getattr(info, 'source', 'Unknown')
            is_user = getattr(info, 'is_user', False)
            is_player = hasattr(info, 'player') and info.player
            
            # 根据不同类型构建不同格式的日志
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # 获取内容并清理颜色代码
            content = clean_color_codes(info.content) if hasattr(info, 'content') else ''

            log_line = f"[{timestamp}] [{str(source)}/INFO] {content}"

            # MCDR格式的日志 - 将 source 转换为字符串
            mcdr_log_line = f"[{timestamp}] [{str(source)}/INFO] {content}"
            
            # 如果有父 LogWatcher，使用它的去重方法添加两种格式
            if self.log_watcher and hasattr(self.log_watcher, '_add_log_line'):
                # 添加普通格式日志
                self.log_watcher._add_log_line(log_line)
                # 添加MCDR格式日志
                self.log_watcher._add_log_line(mcdr_log_line)
            else:
                # 否则直接加入队列
                self.log_queue.put(log_line)
                self.log_queue.put(mcdr_log_line)
            
    def get_logs(self, max_count=100) -> List[str]:
        """获取捕获的日志，最多返回max_count条"""
        logs = []
        try:
            # 非阻塞获取所有可用的日志
            while len(logs) < max_count:
                try:
                    log = self.log_queue.get_nowait()
                    logs.append(log)
                except queue.Empty:
                    break
        except Exception as e:
            logs.append(f"获取日志出错: {str(e)}")
        return logs
    
    def clear_logs(self):
        """清空日志队列"""
        try:
            while not self.log_queue.empty():
                self.log_queue.get_nowait()
        except Exception:
            pass
            
    def run(self):
        """线程主循环"""
        while self.running:
            # 短暂休眠以减少CPU占用
            time.sleep(0.05)

# 标准输出拦截器
class StdoutInterceptor:
    """拦截标准输出和标准错误流的类"""
    
    def __init__(self, log_watcher):
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.log_watcher = log_watcher
        self.buffer = ""
        self.lock = threading.Lock()
        self.enabled = True
        
    def start_interception(self):
        """开始拦截标准输出和标准错误"""
        # 创建拦截器实例
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
                
            # 确保其他属性传递到原始流
            def __getattr__(self, name):
                return getattr(self.original_stream, name)
                
        # 替换标准输出和标准错误
        sys.stdout = InterceptedStream(self.original_stdout, self)
        sys.stderr = InterceptedStream(self.original_stderr, self)
        
        # 打印调试信息
        if self.log_watcher.server_interface:
            self.log_watcher.server_interface.logger.debug("标准输出和标准错误拦截器已启动")
        
    def stop_interception(self):
        """停止拦截并恢复原始流"""
        self.enabled = False
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        if self.log_watcher.server_interface:
            self.log_watcher.server_interface.logger.debug("标准输出和标准错误拦截器已停止")
        
    def process_output(self, message):
        """处理拦截到的输出"""
        with self.lock:
            # 累积缓冲区
            self.buffer += message
            
            # 检查是否有完整的行
            if '\n' in self.buffer:
                lines = self.buffer.split('\n')
                # 最后一行可能不完整，保留在缓冲区
                self.buffer = lines[-1]

class LogWatcher:
    def __init__(self, server_interface=None):
        self._lock = threading.Lock()
        self._patterns = []
        self._result = {}
        self._watching = False
        
        # 保存服务器接口
        self.server_interface = server_interface
        
        # 创建日志捕获器
        self.mcdr_log_handler = LogHandler()
        self.mc_log_capture = MCServerLogCapture()
        
        # 设置互相引用
        self.mc_log_capture.set_log_watcher(self)
        
        # 存储捕获的日志
        if not hasattr(self, 'captured_logs'):
            self.captured_logs = []
        self.mcdr_loggers = []
        
        # 跟踪日志行号和去重
        self.log_counter = 0
        self._handled_log_hashes = set()
        
        # 拦截标准 logging.StreamHandler 的 emit 方法，捕获所有日志
        self.original_stream_handler_emit = logging.StreamHandler.emit
        def intercepted_emit(self_handler, record):
            try:
                # 调用原始方法
                result = self.original_stream_handler_emit(self_handler, record)
                
                # 捕获日志记录
                if 'mcdreforged' in record.name.lower() or 'mcdr' in record.name.lower():
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    formatter = logging.Formatter('%(message)s')
                    message = formatter.format(record)
                    log_line = f"[{timestamp}] [{record.name}/{record.levelname}] {message}"
                    self._add_log_line(log_line)
                    
                return result
            except Exception as e:
                if self.server_interface:
                    self.server_interface.logger.error(f"拦截日志emit出错: {e}")
                return self.original_stream_handler_emit(self_handler, record)
                
        logging.StreamHandler.emit = intercepted_emit
        if self.server_interface:
            self.server_interface.logger.debug("已拦截 logging.StreamHandler.emit 方法，可以捕获所有日志输出")
        
        # 创建并启动标准输出拦截器
        self.stdout_interceptor = StdoutInterceptor(self)
        self.stdout_interceptor.start_interception()
        
        # 启动MC日志捕获线程
        self.mc_log_capture.start()
        
    def capture_stdout_line(self, line):
        """捕获标准输出中的日志行"""
        if not line.strip():
            return
            
        # 清理颜色代码
        line = clean_color_codes(line)
            
        # 更智能地检测和处理不同的日志格式
        is_mcdr_log = '[MCDR]' in line
        is_server_log = '[Server]' in line
        is_task_log = '[Task' in line and 'Executor' in line
        
        # 如果是 MCDR 日志，尝试提取时间戳
        if is_mcdr_log or is_server_log or is_task_log:
            # 提取时间戳
            timestamp_match = re.search(r'\[(\d{2}:\d{2}:\d{2})\]', line)
            if timestamp_match:
                timestamp = timestamp_match.group(1)
                # 构建完整的时间戳
                today = time.strftime("%Y-%m-%d")
                full_timestamp = f"{today} {timestamp}"
                # 重新格式化为标准格式
                if is_mcdr_log:
                    log_line = f"[{full_timestamp}] {line}"
                elif is_server_log:
                    log_line = f"[{full_timestamp}] [SERVER/INFO] {line}"
                else:
                    log_line = f"[{full_timestamp}] [TaskExecutor/INFO] {line}"
                    
                # 添加到日志队列
                self._add_log_line(log_line)
                return
        
        # 如果没有找到时间戳或不是标准格式，尝试解析一般格式
        if '[' in line and ']' in line:
            # 添加一个通用时间戳
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            log_line = f"[{timestamp}] [STDOUT/INFO] {line}"
            self._add_log_line(log_line)
        else:
            # 未识别的格式，添加为控制台输出
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            log_line = f"[{timestamp}] [CONSOLE/INFO] {line}"
            self._add_log_line(log_line)
            
    def _setup_log_capture(self):
        """设置日志捕获"""
        # 找到所有MCDR相关的日志记录器
        # self.mcdr_loggers = self._find_mcdr_loggers()
        
        # 添加处理器到所有MCDR相关的日志记录器
        # for logger in self.mcdr_loggers:
        #     logger.addHandler(self.mcdr_log_handler)
            
        # 尝试直接获取MCDR内部日志系统
        try:
            from .mcdr_adapter import MCDRAdapter
            if self.server_interface:
                mcdr_logger = MCDRAdapter.get_mcdr_logger(self.server_interface)
                if mcdr_logger is not None:
                    mcdr_logger.addHandler(self.mcdr_log_handler)
                    if self.server_interface:
                        self.server_interface.logger.debug(f"已添加日志处理器到MCDR内部日志记录器: {mcdr_logger}")
                    
                    # 直接添加处理器到控制台处理器
                    console_handler = getattr(mcdr_logger, "console_handler", None)
                    if console_handler is not None:
                        # SyncStdoutStreamHandler 没有 addHandler 方法，不能直接添加处理器
                        # 可以尝试拦截其 emit 方法
                        try:
                            original_emit = console_handler.emit
                            # 保存原始方法以便后续恢复
                            console_handler._original_emit = original_emit
                            def intercepted_console_emit(record):
                                try:
                                    # 调用原始方法
                                    original_emit(record)
                                    # 同时用我们的处理器处理
                                    self.mcdr_log_handler.emit(record)
                                except Exception as e:
                                    if self.server_interface:
                                        self.server_interface.logger.error(f"控制台处理器拦截出错: {e}")
                                    original_emit(record)
                            # 替换方法
                            console_handler.emit = intercepted_console_emit
                            if self.server_interface:
                                self.server_interface.logger.debug(f"已拦截MCDR控制台处理器的emit方法: {console_handler}")
                        except Exception as e:
                            if self.server_interface:
                                self.server_interface.logger.error(f"拦截控制台处理器emit方法失败: {e}")
                        
                        # 获取MCDR日志文件处理器
                        file_handler = getattr(mcdr_logger, "file_handler", None)
                        if file_handler is not None and hasattr(file_handler, "baseFilename"):
                            if self.server_interface:
                                self.server_interface.logger.debug(f"MCDR日志文件路径: {file_handler.baseFilename}")
                
                # 尝试获取控制台处理器
                try:
                    from mcdreforged.minecraft.rtext import RTextBase
                    # 拦截 RTextBase 的控制台输出
                    original_print = RTextBase.print
                    # 保存原始方法以便恢复
                    RTextBase._original_print = original_print
                    def intercepted_print(self, *args, **kwargs):
                        result = original_print(self, *args, **kwargs)
                        # 捕获输出到日志
                        text = str(self)
                        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                        log_line = f"[{timestamp}] [RText/INFO] {text}"
                        self._add_log_line(log_line)
                        return result
                    RTextBase.print = intercepted_print
                    if self.server_interface:
                        self.server_interface.logger.debug("已拦截RTextBase.print方法")
                except ImportError:
                    if self.server_interface:
                        self.server_interface.logger.debug("无法导入RTextBase，跳过拦截")
                except Exception as e:
                    if self.server_interface:
                        self.server_interface.logger.error(f"拦截RTextBase.print失败: {e}")
        except Exception as e:
            if self.server_interface:
                self.server_interface.logger.error(f"获取MCDR内部日志系统失败: {e}")
                import traceback
                self.server_interface.logger.error(traceback.format_exc())
    
    def _find_mcdr_loggers(self) -> List[logging.Logger]:
        """找到所有MCDR相关的日志记录器"""
        result = []
        
        # 获取根记录器和它的所有子记录器
        root_logger = logging.getLogger()
        result.append(root_logger)
        
        # 找到常用的MCDR子记录器
        mcdr_logger_names = [
            'mcdreforged',
            'mcdreforged.plugin',
            'mcdreforged.handler',
            'mcdreforged.command',
            'mcdreforged.executor',
            'mcdreforged.info_reactor',
            'mcdreforged.utils',
            'mcdreforged.api',
            'plugin_manager',
            'task_executor',
            'console_handler',
            'server_handler',
            'watchdog'
        ]
        
        for name in mcdr_logger_names:
            result.append(logging.getLogger(name))
            
        # 获取已经存在的所有记录器
        for logger_name in logging.root.manager.loggerDict:
            if (
                'mcdreforged' in logger_name.lower() or
                'mcdr' in logger_name.lower() or
                'minecraft' in logger_name.lower() or
                'server' in logger_name.lower()
            ):
                result.append(logging.getLogger(logger_name))
                
        return list(set(result))  # 去重
    
    def _read_new_logs(self):
        """获取新的日志内容"""
        # 获取MCDR日志
        mcdr_logs = self.mcdr_log_handler.get_logs()
        
        # 获取MC服务器日志
        mc_logs = self.mc_log_capture.get_logs()
        
        # 合并日志
        new_logs = []
        
        # 处理MCDR日志，使用去重机制
        for log in mcdr_logs:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            log_line = f"[{timestamp}] [LogHandler/INFO] {log}"
            if self._add_log_line(log_line):
                new_logs.append(log_line)
        
        return new_logs

    def _process_lines(self, lines):
        """处理读取的日志行，更新匹配状态。"""
        with self._lock:
            for line in lines:
                for pattern in self._patterns:
                    if re.search(pattern, line):
                        self._result[pattern] = True

    def get_result(self, timeout=10, match_all=True) -> dict:
        """
        获取日志匹配结果。

        Args:
            timeout (int): 获取结果的最大超时时间，单位：秒。
            match_all (bool): 是否要求所有模式都匹配才返回 `True`，否则只要匹配任意一个就返回 `True`。

        Returns:
            dict: 每个模式的匹配状态，`True`表示匹配成功，`False`表示未匹配。
        """
        start_time = time.time()
        end_time = start_time + timeout

        while time.time() < end_time:
            new_lines = self._read_new_logs()
            self._process_lines(new_lines)

            with self._lock:
                if not self._watching:
                    break
                
                if match_all:
                    if all(self._result.values()):
                        self._watching = False
                        return self._result
                else:
                    if any(self._result.values()):
                        self._watching = False
                        return self._result

            time.sleep(0.1)

        self._watching = False
        return self._result

    def _cleanup(self):
        """清理资源，释放状态。"""
        self._patterns = []
        self._result = {}
        self.captured_logs = []
        
        # 清空日志队列
        self.mcdr_log_handler.clear_logs()
        self.mc_log_capture.clear_logs()
        
    def get_recent_logs(self, lines_count=100):
        """
        获取最近的日志内容
        
        Args:
            lines_count (int): 要获取的日志行数，默认100行
            
        Returns:
            list: 最近的日志行列表
        """
        # 首先获取最新日志
        self._read_new_logs()
        
        # 返回最近的日志行
        if len(self.captured_logs) > lines_count:
            return self.captured_logs[-lines_count:]
        else:
            return self.captured_logs
            
    def get_logs_after_line(self, start_line=0, max_lines=100):
        """
        获取指定行之后的日志内容
        
        Args:
            start_line (int): 开始行号（从0开始计数）
            max_lines (int): 最大返回行数，防止返回过多数据
            
        Returns:
            dict: 包含日志行和当前总行数的字典
        """
        try:
            # 首先获取最新日志
            self._read_new_logs()
            
            # 获取日志总行数
            total_lines = len(self.captured_logs)
            
            # 如果start_line超出范围，从最后返回max_lines行
            if start_line >= total_lines:
                start_line = max(0, total_lines - max_lines)
                
            # 确保不超过最大行数限制
            end_line = min(total_lines, start_line + max_lines)
            
            # 清理颜色代码并添加换行符，保持与原实现的一致性
            logs_with_newline = [clean_color_codes(log) + '\n' for log in self.captured_logs[start_line:end_line]]
            
            return {
                "logs": logs_with_newline,
                "total_lines": total_lines,
                "start_line": start_line,
                "end_line": end_line
            }
        except Exception as e:
            return {
                "logs": [f"读取日志出错: {str(e)}\n"],
                "total_lines": 1,
                "start_line": 0,
                "end_line": 1
            }

    def get_logs_since_counter(self, last_counter=0, max_lines=100):
        """
        获取指定日志计数器ID之后的新日志
        
        Args:
            last_counter (int): 上次获取的最后一条日志的计数器ID
            max_lines (int): 最大返回行数，防止返回过多数据
            
        Returns:
            dict: 包含新日志行、当前总行数和最新日志计数器的字典
        """
        try:
            # 首先获取最新日志
            # self._read_new_logs()
            
            # 获取日志总行数
            total_lines = len(self.captured_logs)
            
            # 查找从last_counter之后的日志
            new_logs = []
            current_counter = last_counter
            
            for log in self.captured_logs:
                # 从日志行中提取计数器ID，格式如 [#123]
                counter_match = re.search(r'\[#(\d+)\]', log)
                if counter_match:
                    log_counter = int(counter_match.group(1))
                    # 只添加ID更大的日志
                    if log_counter > last_counter:
                        # 清理颜色代码
                        cleaned_log = clean_color_codes(log)
                        
                        # 尝试解析时间戳
                        timestamp_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\]', log)
                        timestamp = None
                        timestamp_value = 0
                        if timestamp_match:
                            try:
                                timestamp_str = timestamp_match.group(1)
                                if '.' in timestamp_str:
                                    timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                                    timestamp_value = timestamp.timestamp()
                                else:
                                    timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                                    timestamp_value = timestamp.timestamp()
                            except Exception:
                                pass
                        
                        # 检查是否是用户命令
                        is_command = "InfoSource.CONSOLE/INFO" in log and "!!" in log
                        
                        # 添加日志条目
                        new_logs.append({
                            "line_number": self.captured_logs.index(log),
                            "counter": log_counter,
                            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else None,
                            "timestamp_value": timestamp_value,
                            "content": cleaned_log + '\n',
                            "source": "all",
                            "is_command": is_command
                        })
                        
                        # 更新当前计数器
                        current_counter = max(current_counter, log_counter)
                        
                        # 限制返回日志数量
                        if len(new_logs) >= max_lines:
                            break
            
            return {
                "logs": new_logs,
                "total_lines": total_lines,
                "last_counter": current_counter,
                "new_logs_count": len(new_logs)
            }
        except Exception as e:
            import traceback
            error_msg = f"获取新日志出错: {str(e)}\n{traceback.format_exc()}"
            if self.server_interface:
                self.server_interface.logger.error(error_msg)
            return {
                "logs": [{"content": error_msg + '\n', "timestamp": None, "source": "error", "line_number": 0, "counter": last_counter + 1}],
                "total_lines": 1,
                "last_counter": last_counter + 1,
                "new_logs_count": 1
            }

    def get_latest_logs(self, max_lines=500):
        """
        获取最新的日志内容（从文件末尾向前读取）
        
        Args:
            max_lines (int): 要获取的最大日志行数，默认500行
            
        Returns:
            dict: 包含最新日志行和总行数的字典
        """
        try:
            # 首先获取最新日志
            self._read_new_logs()
            
            # 获取日志总行数
            total_lines = len(self.captured_logs)
            
            # 从末尾开始读取指定行数
            start_line = max(0, total_lines - max_lines)
            
            # 清理颜色代码并添加换行符，保持与原实现的一致性
            logs_with_newline = [clean_color_codes(log) + '\n' for log in self.captured_logs[start_line:total_lines]]
            
            return {
                "logs": logs_with_newline,
                "total_lines": total_lines,
                "start_line": start_line,
                "end_line": total_lines
            }
        except Exception as e:
            return {
                "logs": [f"读取日志出错: {str(e)}\n"],
                "total_lines": 1,
                "start_line": 0,
                "end_line": 1
            }

    def parse_log_timestamp(self, log_line, log_type="mcdr"):
        """
        解析日志行中的时间戳
        
        Args:
            log_line (str): 日志行内容
            log_type (str): 日志类型，mcdr或minecraft
            
        Returns:
            datetime: 解析后的时间戳，如果解析失败则返回None
        """
        import datetime
        import re
        
        try:
            # 判断是否是接续行（前面有空格或制表符）
            if log_line.startswith((' ', '\t')):
                return None
            
            if log_type == "mcdr":
                # MCDR格式: [2025-04-03 22:45:53.14] [TaskExecutor/INFO] xxxx
                match = re.search(r'\[MCDR\] \[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]', log_line)
                if match:
                    timestamp_str = match.group(1)
                    return datetime.datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                
                # 尝试匹配其他可能的MCDR日志格式
                match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\]', log_line)
                if match:
                    timestamp_str = match.group(1)
                    try:
                        if '.' in timestamp_str:
                            return datetime.datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        else:
                            return datetime.datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        pass
            else:
                # MC格式: [22:46:13] [Server thread/INFO]: xxxx
                match = re.search(r'^\[(\d{2}:\d{2}:\d{2})\]', log_line)
                if match:
                    timestamp_str = match.group(1)
                    today = datetime.datetime.now().strftime('%Y-%m-%d')
                    return datetime.datetime.strptime(f"{today} {timestamp_str}", '%Y-%m-%d %H:%M:%S')
        except Exception as e:
            if self.server_interface:
                self.server_interface.logger.error(f"解析日志时间戳出错: {e}, 日志: {log_line[:50]}...")
        
        return None

    def get_merged_logs(self, max_lines=500):
        """
        获取所有日志（不再合并或排序）
        
        Args:
            mcdr_log_path (str): MCDR日志文件路径（不再使用，保留参数兼容性）
            mc_log_path (str): Minecraft日志文件路径（不再使用，保留参数兼容性）
            max_lines (int): 要获取的最大日志行数，默认500行
            
        Returns:
            dict: 包含所有日志行和总行数的字典
        """
        try:
            # 先获取最新日志
            # self._read_new_logs()
            
            # 获取日志总行数
            total_lines = len(self.captured_logs)
            
            # 从末尾开始读取指定行数
            start_line = max(0, total_lines - max_lines)
            end_line = total_lines
            
            # 准备日志列表
            logs = []
            
            # 读取日志行并解析时间戳
            log_entries = []
            for i in range(start_line, end_line):
                log_line = self.captured_logs[i]
                # 清理颜色代码
                cleaned_log = clean_color_codes(log_line)
                
                # 尝试解析时间戳以便排序 - 首先尝试带毫秒的格式
                timestamp_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\]', log_line)
                timestamp = None
                timestamp_value = 0
                if timestamp_match:
                    try:
                        timestamp_str = timestamp_match.group(1)
                        if '.' in timestamp_str:
                            # 包含毫秒
                            timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                            timestamp_value = timestamp.timestamp()
                        else:
                            # 不包含毫秒
                            timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                            timestamp_value = timestamp.timestamp()
                    except Exception:
                        pass
                
                # 检查是否是用户命令，MCDR命令通常以!!开头
                is_command = "InfoSource.CONSOLE/INFO" in log_line and "!!" in log_line
                
                # 尝试从行号中提取顺序信息（格式如 [#123]）以作为次要排序依据
                sequence_match = re.search(r'\[#(\d+)\]', log_line)
                sequence_num = float('inf')
                if sequence_match:
                    try:
                        sequence_num = int(sequence_match.group(1))
                    except:
                        pass
                
                # 添加日志条目，包含解析的时间戳和命令标记
                log_entries.append({
                    "line_number": i,
                    "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S") if timestamp else None,
                    "timestamp_value": timestamp_value,
                    "sequence_num": sequence_num,
                    "content": cleaned_log + '\n',
                    "source": "all",
                    "is_command": is_command
                })
            
            # 转换回简单格式
            logs = log_entries
            
            return {
                "logs": logs,
                "total_lines": total_lines,
                "start_line": start_line,
                "end_line": end_line
            }
        except Exception as e:
            import traceback
            error_msg = f"获取日志出错: {str(e)}\n{traceback.format_exc()}"
            if self.server_interface:
                self.server_interface.logger.error(error_msg)
            return {
                "logs": [{"content": error_msg + '\n', "timestamp": None, "source": "error", "line_number": 0}],
                "total_lines": 1,
                "start_line": 0,
                "end_line": 1
            }

    def _add_log_line(self, log_line):
        """添加日志行，避免重复"""
        # 计算日志内容的哈希值用于去重
        log_hash = hash(log_line)
        
        with self._lock:
            # 如果日志已经存在，不添加
            if log_hash in self._handled_log_hashes:
                return False
                
            # 添加到已处理集合
            self._handled_log_hashes.add(log_hash)
            
            # 限制集合大小，避免内存泄漏
            if len(self._handled_log_hashes) > 10000:
                self._handled_log_hashes.clear()
            
            # 增加计数器并添加带序号的日志
            self.log_counter += 1
            numbered_log = f"[#{self.log_counter}] {log_line}"
            self.captured_logs.append(numbered_log)
            
            return True

    def on_mcdr_info(self, server, info):
        """当MCDR信息事件触发时调用此方法"""
        # 将日志添加到日志队列
        if hasattr(info, 'content'):
            # 使用带毫秒的时间戳格式
            now = datetime.datetime.now()
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")  # 只保留3位毫秒数
            
            # 修复：使用 info.source 属性而不是 get 方法，并确保转换为字符串
            source = getattr(info, 'source', 'Unknown')
            # 确保日志格式与 MCDR 格式一致，将 source 转换为字符串
            # 清理颜色代码
            content = clean_color_codes(info.content)
            log_line = f"[{timestamp}] [{str(source)}/INFO] {content}"
            
            # 添加日志并避免重复
            if self._add_log_line(log_line):
                # 同时处理模式匹配，仅当日志是新的时才处理
                with self._lock:
                    if self._watching:
                        for pattern in self._patterns:
                            if re.search(pattern, log_line):
                                self._result[pattern] = True

    def on_server_output(self, server, info):
        """当服务器输出事件触发时调用此方法"""
        # 将日志传递给MC日志捕获器
        # self.mc_log_capture.on_info(server, info)
        
        # # 直接添加到捕获的日志中，确保用户命令也能被记录
        # if hasattr(info, 'content'):
        #     # 检查是否是用户输入的命令
        #     is_user = getattr(info, 'is_user', False)
            
        #     # 使用带毫秒的时间戳格式
        #     now = datetime.datetime.now()
        #     timestamp = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 只保留3位毫秒数
            
        #     # 安全地获取 source 属性
        #     source = getattr(info, 'source', 'Unknown')
        #     # 创建字符串版本的 source
        #     str_source = str(source)
        #     # 清理颜色代码
        #     content = clean_color_codes(info.content)
            
        #     # 构建日志行
        #     log_line = f"[{timestamp}] [{str_source}/INFO] {content}"
            
        #     # 使用去重机制添加日志
        #     self._add_log_line(log_line)
            
        #     # 处理模式匹配
        #     with self._lock:
        #         if self._watching:
        #             for pattern in self._patterns:
        #                 if re.search(pattern, info.content):
        #                     self._result[pattern] = True
        pass
                    
    def stop(self):
        """停止监控并释放资源"""
        # 停止标准输出拦截
        if hasattr(self, 'stdout_interceptor') and self.stdout_interceptor:
            self.stdout_interceptor.stop_interception()
            
        # 停止MC日志捕获线程
        if self.mc_log_capture and self.mc_log_capture.running:
            self.mc_log_capture.stop()
            
        # 移除日志处理器
        for logger in self.mcdr_loggers:
            if logger.handlers and self.mcdr_log_handler in logger.handlers:
                logger.removeHandler(self.mcdr_log_handler)
                
        # 恢复 logging.StreamHandler.emit 方法
        if hasattr(self, 'original_stream_handler_emit'):
            logging.StreamHandler.emit = self.original_stream_handler_emit
            if self.server_interface:
                self.server_interface.logger.info("已恢复 logging.StreamHandler.emit 方法")
            
        # 恢复控制台处理器的 emit 方法
        try:
            from .mcdr_adapter import MCDRAdapter
            if self.server_interface:
                mcdr_logger = MCDRAdapter.get_mcdr_logger(self.server_interface)
                if mcdr_logger is not None:
                    console_handler = getattr(mcdr_logger, "console_handler", None)
                    if console_handler is not None and hasattr(console_handler, '_original_emit'):
                        console_handler.emit = console_handler._original_emit
                        if self.server_interface:
                            self.server_interface.logger.info("已恢复控制台处理器的 emit 方法")
        except Exception as e:
            if self.server_interface:
                self.server_interface.logger.error(f"恢复控制台处理器 emit 方法失败: {e}")
            
        # 恢复 RTextBase.print 方法
        try:
            from mcdreforged.minecraft.rtext import RTextBase
            original_print = getattr(RTextBase, '_original_print', None)
            if original_print:
                RTextBase.print = original_print
                if self.server_interface:
                    self.server_interface.logger.info("已恢复 RTextBase.print 方法")
        except ImportError:
            pass
        except Exception as e:
            if self.server_interface:
                self.server_interface.logger.error(f"恢复 RTextBase.print 方法失败: {e}")
        
        # 清理状态
        self._cleanup()
        self._watching = False
