import logging
import threading
from typing import TypedDict


class StateType(TypedDict):
    logs: list  # 存储原始字典: {timestamp, level, source, message, counter}
    counter: int
    hashes: set  # 存储 message 的哈希，用于简单去重
    lock: threading.Lock
    intercepted: bool
    original_emit: type[logging.StreamHandler.emit] | None
