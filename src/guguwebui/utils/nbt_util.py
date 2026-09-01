"""
轻量 NBT 读取器。

仅用于解析 gzip 压缩的 Minecraft playerdata .dat 文件（提取坐标 / 维度等），
避免为这个功能引入额外的 NBT 依赖库。

NBT 格式（Java 版，大端序）：
    根标签: 类型(1字节) + 名称(2字节长度 + UTF-8)
    复合标签: 子标签循环，直到 TAG_End
    列表: 元素类型(1字节) + 长度(4字节) + 元素
"""

from __future__ import annotations

import gzip
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

_TAG_END = 0
_TAG_BYTE = 1
_TAG_SHORT = 2
_TAG_INT = 3
_TAG_LONG = 4
_TAG_FLOAT = 5
_TAG_DOUBLE = 6
_TAG_BYTE_ARRAY = 7
_TAG_STRING = 8
_TAG_LIST = 9
_TAG_COMPOUND = 10
_TAG_INT_ARRAY = 11
_TAG_LONG_ARRAY = 12


class _Reader:
    """大端序二进制读取器。"""

    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def read_byte(self) -> int:
        value = self.data[self.offset]
        self.offset += 1
        return value

    def read_short(self) -> int:
        value = struct.unpack_from(">h", self.data, self.offset)[0]
        self.offset += 2
        return value

    def read_ushort(self) -> int:
        value = struct.unpack_from(">H", self.data, self.offset)[0]
        self.offset += 2
        return value

    def read_int(self) -> int:
        value = struct.unpack_from(">i", self.data, self.offset)[0]
        self.offset += 4
        return value

    def read_long(self) -> int:
        value = struct.unpack_from(">q", self.data, self.offset)[0]
        self.offset += 8
        return value

    def read_float(self) -> float:
        value = struct.unpack_from(">f", self.data, self.offset)[0]
        self.offset += 4
        return value

    def read_double(self) -> float:
        value = struct.unpack_from(">d", self.data, self.offset)[0]
        self.offset += 8
        return value

    def read_string(self) -> str:
        length = self.read_ushort()
        value = self.data[self.offset : self.offset + length].decode(
            "utf-8", errors="replace"
        )
        self.offset += length
        return value


def _parse_payload(reader: _Reader, tag_type: int) -> Any:
    if tag_type == _TAG_END:
        return None
    if tag_type == _TAG_BYTE:
        return reader.read_byte()
    if tag_type == _TAG_SHORT:
        return reader.read_short()
    if tag_type == _TAG_INT:
        return reader.read_int()
    if tag_type == _TAG_LONG:
        return reader.read_long()
    if tag_type == _TAG_FLOAT:
        return reader.read_float()
    if tag_type == _TAG_DOUBLE:
        return reader.read_double()
    if tag_type == _TAG_BYTE_ARRAY:
        length = reader.read_int()
        value = reader.data[reader.offset : reader.offset + length]
        reader.offset += length
        return list(value)
    if tag_type == _TAG_STRING:
        return reader.read_string()
    if tag_type == _TAG_LIST:
        element_type = reader.read_byte()
        length = reader.read_int()
        items: List[Any] = []
        for _ in range(length):
            items.append(_parse_payload(reader, element_type))
        return items
    if tag_type == _TAG_COMPOUND:
        compound: Dict[str, Any] = {}
        while True:
            child_type = reader.read_byte()
            if child_type == _TAG_END:
                break
            name = reader.read_string()
            compound[name] = _parse_payload(reader, child_type)
        return compound
    if tag_type == _TAG_INT_ARRAY:
        length = reader.read_int()
        items = [reader.read_int() for _ in range(length)]
        return items
    if tag_type == _TAG_LONG_ARRAY:
        length = reader.read_int()
        items = [reader.read_long() for _ in range(length)]
        return items
    raise ValueError(f"未知 NBT 标签类型: {tag_type}")


def parse_nbt(data: bytes) -> Optional[Dict[str, Any]]:
    """解析未压缩的 NBT 数据，返回根 Compound 字典；失败返回 None。"""
    try:
        reader = _Reader(data)
        root_type = reader.read_byte()
        if root_type != _TAG_COMPOUND:
            return None
        reader.read_ushort()  # 根标签名（忽略）
        return _parse_payload(reader, root_type)
    except Exception:
        return None


def read_compressed_nbt(path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """读取 .dat 文件（gzip 压缩，兼容未压缩），返回 NBT 字典或 None。"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
        try:
            data = gzip.decompress(raw)
        except OSError:
            # 部分版本的 .dat 可能未压缩
            data = raw
        return parse_nbt(data)
    except Exception:
        return None


# 旧版本 Dimension 为数字 id，映射为命名空间 id
_LEGACY_DIMENSION_MAP = {
    0: "minecraft:overworld",
    -1: "minecraft:the_nether",
    1: "minecraft:the_end",
}


def read_playerdata(path: Union[str, Path]) -> Dict[str, Any]:
    """读取玩家数据文件，提取坐标与维度等常用字段。"""
    nbt = read_compressed_nbt(path) or {}
    result: Dict[str, Any] = {}

    pos = nbt.get("Pos")
    if isinstance(pos, list) and len(pos) >= 3:
        coords = []
        for v in pos[:3]:
            try:
                coords.append(round(float(v), 2))
            except (TypeError, ValueError):
                coords = []
                break
        if len(coords) == 3:
            result["pos"] = {"x": coords[0], "y": coords[1], "z": coords[2]}

    dimension = nbt.get("Dimension")
    if isinstance(dimension, str):
        result["dimension"] = dimension
    elif isinstance(dimension, int):
        mapped = _LEGACY_DIMENSION_MAP.get(dimension)
        if mapped:
            result["dimension"] = mapped

    return result
