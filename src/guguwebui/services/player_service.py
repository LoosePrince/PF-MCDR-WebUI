"""
玩家管理服务。

- 汇总所有进过本服的玩家（usercache.json + playerdata + WebUI 自身会话记录）
- 假人识别：真实玩家有 IP 记录，Carpet 假人没有 IP（与 player_ip_logger 判定一致）
- 白名单 / OP / 封禁管理：读取服务端 json 文件，动作通过 RCON 或 MCDR 转发执行
- 解封通过直接修改 banned-*.json 文件完成（需要重启服务器生效）
"""

from __future__ import annotations

import datetime
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import javaproperties

from guguwebui.constant import PLAYER_STATS_PATH
from guguwebui.utils.api_cache import api_cache
from guguwebui.utils.mc_util import format_uuid, get_minecraft_path
from guguwebui.utils.nbt_util import read_playerdata

# 内存中的玩家上线时间（会话时长统计）
_JOIN_TIMES: Dict[str, float] = {}
_STATS_LOCK = threading.Lock()

_POS_RE = re.compile(r"\[([^\]]*)\]")
_DIM_RE = re.compile(r'"([^"]+)"')

_DEFAULT_STATS: Dict[str, Any] = {"players": {}}


def _parse_pos_feedback(feedback: Optional[str]) -> Optional[Dict[str, float]]:
    """解析 `data get entity <name> Pos` 的反馈，如 `[... [12.0d, 64.0d, -34.0d]]`。"""
    if not feedback:
        return None
    m = _POS_RE.search(feedback)
    if not m:
        return None
    parts = [p.strip() for p in m.group(1).split(",") if p.strip()]
    if len(parts) < 3:
        return None
    coords = []
    for part in parts[:3]:
        try:
            coords.append(round(float(part.rstrip("dDfF")), 2))
        except ValueError:
            return None
    return {"x": coords[0], "y": coords[1], "z": coords[2]}


def _parse_dimension_feedback(feedback: Optional[str]) -> Optional[str]:
    """解析 `data get entity <name> Dimension` 的反馈。"""
    if not feedback:
        return None
    m = _DIM_RE.search(feedback)
    if m:
        return m.group(1)
    return None


def _parse_expires_on(expires_on: Optional[str]) -> Optional[float]:
    """usercache expiresOn 解析为时间戳（约 30 天前为最后在线时间）。"""
    if not expires_on:
        return None
    text = str(expires_on).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.astimezone()
            return dt.timestamp() - 30 * 86400
        except ValueError:
            continue
    return None


class PlayerService:
    def __init__(self, server, config_service=None):
        self.server = server
        self.config_service = config_service

    # ------------------------------------------------------------------ #
    # 路径与文件读取
    # ------------------------------------------------------------------ #

    def _working_dir(self) -> Path:
        return Path(get_minecraft_path(self.server, "working_directory"))

    def _server_properties(self) -> Dict[str, Any]:
        try:
            props_path = self._working_dir() / "server.properties"
            if props_path.exists():
                with open(props_path, "r", encoding="UTF-8") as f:
                    return dict(javaproperties.load(f))
        except Exception:
            pass
        return {}

    def _level_name(self) -> str:
        return self._server_properties().get("level-name", "world") or "world"

    def _load_json(self, path: Path, default: Any) -> Any:
        try:
            if path.exists():
                with open(path, "r", encoding="UTF-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return default

    def _save_json(self, path: Path, data: Any) -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            with open(tmp, "w", encoding="UTF-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
            return True
        except Exception as e:
            self.server.logger.error(f"写入文件失败 {path}: {e}")
            return False

    def _load_usercache(self) -> List[Dict[str, Any]]:
        data = self._load_json(self._working_dir() / "usercache.json", [])
        return data if isinstance(data, list) else []

    def _list_playerdata(self) -> Dict[str, str]:
        """返回 {uuid: 文件路径}，来自 world/playerdata/*.dat。"""
        result: Dict[str, str] = {}
        try:
            playerdata_dir = self._working_dir() / self._level_name() / "playerdata"
            if playerdata_dir.exists():
                for f in playerdata_dir.glob("*.dat"):
                    uuid = format_uuid(f.stem)
                    if uuid:
                        result[uuid] = str(f)
        except Exception:
            pass
        return result

    def _uuid_from_usercache(self, name: str) -> Optional[str]:
        for entry in self._load_usercache():
            if entry.get("name") == name:
                return format_uuid(entry.get("uuid") or "")
        return None

    def _name_for_uuid(self, uuid: str) -> Optional[str]:
        target = uuid.lower().replace("-", "")
        for entry in self._load_usercache():
            if format_uuid(entry.get("uuid") or "").lower().replace("-", "") == target:
                return entry.get("name")
        # ops / whitelist 中可能带 name
        for path, key in (
            (self._working_dir() / "ops.json", "uuid"),
            (self._working_dir() / "whitelist.json", "uuid"),
        ):
            data = self._load_json(path, [])
            if isinstance(data, list):
                for item in data:
                    if format_uuid(item.get("uuid") or "").lower().replace("-", "") == target:
                        return item.get("name")
        return None

    # ------------------------------------------------------------------ #
    # 会话 / IP 记录（PLAYER_JOINED / PLAYER_LEFT 事件驱动）
    # ------------------------------------------------------------------ #

    def _load_stats(self) -> Dict[str, Any]:
        with _STATS_LOCK:
            return self._load_json(PLAYER_STATS_PATH, _DEFAULT_STATS) or _DEFAULT_STATS

    def _save_stats(self, stats: Dict[str, Any]) -> None:
        with _STATS_LOCK:
            self._save_json(PLAYER_STATS_PATH, stats)

    def on_player_joined(self, server, player: str, info=None) -> None:
        """记录上线时间与 IP（真实玩家有 IP，Carpet 假人没有）。"""
        try:
            now = time.time()
            _JOIN_TIMES[player] = now
            stats = self._load_stats()
            entry = stats.setdefault("players", {}).setdefault(player, {})
            if not entry.get("first_seen"):
                entry["first_seen"] = now
            entry["last_seen"] = now

            ip = None
            try:
                ip = server.get_player_ip(player)
            except Exception:
                pass
            if ip:
                entry.setdefault("ips", [])
                if ip not in entry["ips"]:
                    entry["ips"].append(ip)
                entry["last_ip"] = ip

            if not entry.get("uuid"):
                try:
                    info_obj = server.get_player_info(player)
                    if info_obj and getattr(info_obj, "uuid", None):
                        entry["uuid"] = format_uuid(info_obj.uuid)
                except Exception:
                    entry["uuid"] = self._uuid_from_usercache(player)

            self._save_stats(stats)
        except Exception as e:
            self.server.logger.debug(f"记录玩家上线数据失败: {e}")

    def on_player_left(self, server, player: str) -> None:
        """玩家下线：累计本次会话时长。"""
        try:
            join_time = _JOIN_TIMES.pop(player, None)
            if join_time is None:
                return
            duration = time.time() - join_time
            if duration <= 0:
                return
            stats = self._load_stats()
            entry = stats.setdefault("players", {}).setdefault(player, {})
            entry["total_playtime"] = entry.get("total_playtime", 0) + duration
            entry["last_seen"] = time.time()
            self._save_stats(stats)
        except Exception as e:
            self.server.logger.debug(f"记录玩家下线数据失败: {e}")

    # ------------------------------------------------------------------ #
    # 在线玩家 / IP 查询
    # ------------------------------------------------------------------ #

    def _get_online_players(self) -> List[str]:
        try:
            if self.server.is_rcon_running():
                feedback = self.server.rcon_query("list")
                if isinstance(feedback, str) and ":" in feedback:
                    names_part = feedback.split(":", 1)[1].strip()
                    if names_part:
                        return [
                            n.strip()
                            for n in names_part.split(",")
                            if n.strip()
                        ]
            return list(self.server.get_player_list() or [])
        except Exception:
            return []

    def _get_player_ip(self, name: str) -> Optional[str]:
        """在线玩家的 IP（假人通常返回 None）。"""
        try:
            return self.server.get_player_ip(name)
        except Exception:
            return None

    def _merge_player_logger_ips(self, roster: Dict[str, Dict[str, Any]]) -> None:
        """补充 player_ip_logger 插件记录的历史 IP（如果已安装）。"""
        try:
            plugin = self.server.get_plugin_instance("player_ip_logger")
            if not plugin or not hasattr(plugin, "get_player_ips"):
                return
            for rec in roster.values():
                name = rec.get("name")
                if not name:
                    continue
                try:
                    extra = plugin.get_player_ips(name)
                    if isinstance(extra, list):
                        for ip in extra:
                            if isinstance(ip, str) and ip and ip not in rec["ips"]:
                                rec["ips"].append(ip)
                except Exception:
                    continue
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 名单数据
    # ------------------------------------------------------------------ #

    def _ops_names(self) -> set:
        data = self._load_json(self._working_dir() / "ops.json", [])
        names = set()
        if isinstance(data, list):
            for item in data:
                if item.get("name"):
                    names.add(item["name"])
        return names

    def _whitelist_names(self) -> set:
        data = self._load_json(self._working_dir() / "whitelist.json", [])
        names = set()
        if isinstance(data, list):
            for item in data:
                if item.get("name"):
                    names.add(item["name"])
        return names

    def _banned_names(self) -> Dict[str, Dict[str, Any]]:
        data = self._load_json(self._working_dir() / "banned-players.json", [])
        result: Dict[str, Dict[str, Any]] = {}
        if isinstance(data, list):
            for item in data:
                name = item.get("name") or item.get("uuid") or ""
                if name:
                    result[name] = item
        return result

    def _banned_ips(self) -> List[str]:
        data = self._load_json(self._working_dir() / "banned-ips.json", [])
        ips = []
        if isinstance(data, list):
            for item in data:
                if item.get("ip"):
                    ips.append(item["ip"])
        return ips

    def _is_whitelist_enabled(self) -> bool:
        value = str(self._server_properties().get("white-list", "false")).strip().lower()
        return value in ("true", "1", "yes", "on")

    # ------------------------------------------------------------------ #
    # 玩家列表
    # ------------------------------------------------------------------ #

    def _build_roster(self) -> Dict[str, Dict[str, Any]]:
        """构建全量名单（按名称或 uuid 索引），不包含坐标（懒加载）。"""
        roster: Dict[str, Dict[str, Any]] = {}

        # usercache.json：所有进过服的玩家
        usercache = self._load_usercache()
        for entry in usercache:
            name = entry.get("name")
            uuid = format_uuid(entry.get("uuid") or "")
            key = name or uuid
            if not key:
                continue
            rec = roster.setdefault(
                key,
                {"name": name, "uuid": uuid, "ips": [], "online": False},
            )
            if name:
                rec["name"] = name
            if uuid:
                rec["uuid"] = uuid
            if entry.get("expiresOn"):
                rec["usercache_expires"] = entry["expiresOn"]

        # playerdata：usercache 之外的历史玩家（UUID 为主键）
        playerdata = self._list_playerdata()
        known_uuids = {r.get("uuid") for r in roster.values()}
        for uuid, path in playerdata.items():
            if uuid in known_uuids:
                continue
            name = self._name_for_uuid(uuid)
            key = name or uuid
            rec = roster.setdefault(
                key,
                {"name": name, "uuid": uuid, "ips": [], "online": False},
            )
            if name:
                rec["name"] = name
            if uuid and not rec.get("uuid"):
                rec["uuid"] = uuid
            rec["playerdata_path"] = path

        # WebUI 自身会话记录
        stats = self._load_stats()
        for name, entry in stats.get("players", {}).items():
            rec = roster.setdefault(
                name, {"name": name, "uuid": None, "ips": [], "online": False}
            )
            rec["ips"] = list(
                dict.fromkeys(rec.get("ips", []) + list(entry.get("ips", [])))
            )
            if entry.get("uuid") and not rec.get("uuid"):
                rec["uuid"] = format_uuid(entry["uuid"])
            if entry.get("last_ip") and not rec.get("ip"):
                rec["last_ip"] = entry["last_ip"]
            if entry.get("total_playtime"):
                rec["total_playtime"] = entry["total_playtime"]
            if entry.get("last_seen"):
                rec["last_seen"] = entry["last_seen"]

        # 在线玩家（含在线 IP 实时查询，用于假人判定）
        online = self._get_online_players()
        for name in online:
            rec = roster.setdefault(
                name, {"name": name, "uuid": None, "ips": [], "online": True}
            )
            rec["online"] = True
            ip = self._get_player_ip(name)
            if ip:
                rec.setdefault("ips", [])
                if ip not in rec["ips"]:
                    rec["ips"].append(ip)
                rec["last_ip"] = ip
            if not rec.get("uuid"):
                try:
                    info_obj = self.server.get_player_info(name)
                    if info_obj and getattr(info_obj, "uuid", None):
                        rec["uuid"] = format_uuid(info_obj.uuid)
                except Exception:
                    pass

        # player_ip_logger 历史 IP 补充
        self._merge_player_logger_ips(roster)

        # 标记字段
        ops_names = self._ops_names()
        whitelist_names = self._whitelist_names()
        banned_players = self._banned_names()
        banned_ips = self._banned_ips()
        now = time.time()

        for rec in roster.values():
            name = rec.get("name")
            uuid = rec.get("uuid")
            ips = rec.get("ips", [])
            rec["online"] = bool(rec.get("online"))
            if not name and uuid:
                rec["name"] = uuid
                rec["uuid_only"] = True
            rec["is_op"] = bool(name and name in ops_names)
            rec["whitelisted"] = bool(name and name in whitelist_names)
            rec["banned"] = bool(
                (name and name in banned_players)
                or (uuid and uuid in banned_players)
                or any(ip in banned_ips for ip in ips)
            )
            rec["is_bot"] = len(ips) == 0
            rec["ip"] = rec.get("last_ip") or (ips[0] if ips else None)

            if not rec.get("last_seen"):
                last_seen = _parse_expires_on(rec.get("usercache_expires"))
                if last_seen:
                    rec["last_seen"] = last_seen
                elif rec.get("playerdata_path"):
                    try:
                        rec["last_seen"] = os.path.getmtime(rec["playerdata_path"])
                    except OSError:
                        pass

            if rec["online"]:
                join_time = _JOIN_TIMES.get(name)
                rec["session_seconds"] = (
                    max(0, now - join_time) if join_time is not None else None
                )
            else:
                rec["session_seconds"] = None

        return roster

    def _enrich_position(self, rec: Dict[str, Any]) -> None:
        """填充坐标 / 维度：在线用 RCON data get，离线读 playerdata NBT。"""
        name = rec.get("name")
        uuid = rec.get("uuid")

        if rec.get("online") and name:
            pos = self._rcon_entity_data(name, "Pos")
            dim = self._rcon_entity_data(name, "Dimension")
            if pos is not None:
                rec["position"] = pos
            if dim is not None:
                rec["dimension"] = dim
            if pos is not None or dim is not None:
                return

        if uuid:
            data = self._playerdata_cached(uuid)
            if data.get("pos"):
                rec["position"] = data["pos"]
            if data.get("dimension"):
                rec["dimension"] = data["dimension"]

    def _rcon_entity_data(self, name: str, path: str):
        """通过 RCON 查询实体 NBT 数据（带 30s 缓存）。"""
        cache_key = f"player_entity:{name}:{path}"
        cached = api_cache.get(cache_key, ttl=30)
        if cached is not None:
            return cached
        value = None
        try:
            if self.server.is_rcon_running():
                feedback = self.server.rcon_query(f"data get entity {name} {path}")
                if path == "Pos":
                    value = _parse_pos_feedback(feedback)
                else:
                    value = _parse_dimension_feedback(feedback)
        except Exception:
            value = None
        api_cache.set(cache_key, value, ttl=30)
        return value

    def _playerdata_cached(self, uuid: str) -> Dict[str, Any]:
        cache_key = f"player_playerdata:{uuid}"
        cached = api_cache.get(cache_key, ttl=60)
        if cached is not None:
            return cached
        data: Dict[str, Any] = {}
        path = self._working_dir() / self._level_name() / "playerdata" / f"{uuid}.dat"
        if path.exists():
            data = read_playerdata(path)
        api_cache.set(cache_key, data, ttl=60)
        return data

    def get_players(
        self,
        search: str = "",
        filter_: str = "all",
        offset: int = 0,
        limit: int = 50,
        exclude_bots: bool = False,
    ) -> Dict[str, Any]:
        """汇总玩家列表，支持搜索与筛选；exclude_bots 排除假人（仅列出真实玩家）。"""
        limit = max(1, min(int(limit or 50), 200))
        offset = max(0, int(offset or 0))
        search = (search or "").strip().lower()

        roster = self._build_roster()
        players = list(roster.values())

        if search:
            players = [
                p
                for p in players
                if search in (p.get("name") or "").lower()
                or search in (p.get("uuid") or "").lower()
                or any(search in ip for ip in p.get("ips", []))
            ]

        if filter_ == "online":
            players = [p for p in players if p.get("online")]
        elif filter_ == "offline":
            players = [p for p in players if not p.get("online")]
        elif filter_ == "bot":
            players = [p for p in players if p.get("is_bot")]
        elif filter_ == "op":
            players = [p for p in players if p.get("is_op")]

        if exclude_bots:
            players = [p for p in players if not p.get("is_bot")]

        # 排序：在线优先，其次按最后在线时间倒序
        players.sort(
            key=lambda p: (
                0 if p.get("online") else 1,
                -(p.get("last_seen") or 0),
                (p.get("name") or "").lower(),
            )
        )

        total = len(players)
        page = players[offset : offset + limit]
        for rec in page:
            self._enrich_position(rec)

        online_count = sum(1 for p in players if p.get("online"))
        bot_count = sum(1 for p in players if p.get("is_bot"))

        return {
            "players": page,
            "total": total,
            "offset": offset,
            "limit": limit,
            "online_count": online_count,
            "bot_count": bot_count,
            "server_running": self.server.is_server_running(),
        }

    def get_bots(self) -> Dict[str, Any]:
        """识别出的假人列表（无 IP 记录的玩家 + 在线假人）。"""
        roster = self._build_roster()
        bots = [rec for rec in roster.values() if rec.get("is_bot")]
        bots.sort(
            key=lambda p: (
                0 if p.get("online") else 1,
                -(p.get("last_seen") or 0),
                (p.get("name") or "").lower(),
            )
        )
        for rec in bots:
            self._enrich_position(rec)
        return {
            "bots": bots,
            "total": len(bots),
            "server_running": self.server.is_server_running(),
        }

    # ------------------------------------------------------------------ #
    # 命令执行
    # ------------------------------------------------------------------ #

    def _run_mc_command(self, command: str) -> Dict[str, Any]:
        """执行 MC 原生命令：优先 RCON（可获取反馈），否则走 MCDR 命令转发。"""
        try:
            if self.server.is_rcon_running():
                try:
                    feedback = self.server.rcon_query(command)
                    return {"ok": True, "feedback": feedback}
                except Exception as e:
                    self.server.logger.debug(
                        f"RCON 执行失败，回退到 MCDR 转发: {command} ({e})"
                    )
        except Exception:
            pass
        try:
            self.server.execute_command("/" + command)
            return {"ok": True, "feedback": None}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _server_running(self) -> bool:
        try:
            return self.server.is_server_running()
        except Exception:
            return False

    def _not_running(self) -> Dict[str, Any]:
        return {
            "status": "error",
            "message": "服务器未运行，无法执行该命令",
            "server_running": False,
        }

    # ------------------------------------------------------------------ #
    # 白名单
    # ------------------------------------------------------------------ #

    def get_whitelist(self) -> Dict[str, Any]:
        data = self._load_json(self._working_dir() / "whitelist.json", [])
        members = []
        usercache_uuid = {
            format_uuid(e.get("uuid") or ""): e.get("name")
            for e in self._load_usercache()
        }
        if isinstance(data, list):
            for item in data:
                uuid = format_uuid(item.get("uuid") or "")
                name = item.get("name") or usercache_uuid.get(uuid) or ""
                members.append({"name": name, "uuid": uuid})
        return {
            "status": "success",
            "enabled": self._is_whitelist_enabled(),
            "members": members,
            "server_running": self._server_running(),
        }

    def set_whitelist_enabled(self, enabled: bool) -> Dict[str, Any]:
        if not self._server_running():
            return self._not_running()
        result = self._run_mc_command(f"whitelist {'on' if enabled else 'off'}")
        if not result.get("ok"):
            return {"status": "error", "message": result.get("error", "命令执行失败")}
        return {
            "status": "success",
            "message": "白名单已开启" if enabled else "白名单已关闭",
            "enabled": enabled,
        }

    def reload_whitelist(self) -> Dict[str, Any]:
        if not self._server_running():
            return self._not_running()
        result = self._run_mc_command("whitelist reload")
        if not result.get("ok"):
            return {"status": "error", "message": result.get("error", "命令执行失败")}
        return {"status": "success", "message": "白名单已重载"}

    def whitelist_add(self, name: str) -> Dict[str, Any]:
        if not self._server_running():
            return self._not_running()
        result = self._run_mc_command(f"whitelist add {name}")
        if not result.get("ok"):
            return {"status": "error", "message": result.get("error", "命令执行失败")}
        # 更新后自动触发白名单重载
        self._run_mc_command("whitelist reload")
        return {"status": "success", "message": f"已将 {name} 加入白名单"}

    def whitelist_remove(self, name: str) -> Dict[str, Any]:
        if not self._server_running():
            return self._not_running()
        result = self._run_mc_command(f"whitelist remove {name}")
        if not result.get("ok"):
            return {"status": "error", "message": result.get("error", "命令执行失败")}
        self._run_mc_command("whitelist reload")
        return {"status": "success", "message": f"已将 {name} 移出白名单"}

    # ------------------------------------------------------------------ #
    # OP 管理
    # ------------------------------------------------------------------ #

    def get_ops(self) -> Dict[str, Any]:
        data = self._load_json(self._working_dir() / "ops.json", [])
        ops = []
        if isinstance(data, list):
            for item in data:
                ops.append(
                    {
                        "name": item.get("name") or "",
                        "uuid": format_uuid(item.get("uuid") or ""),
                        "level": item.get("level"),
                        "bypassesPlayerLimit": item.get("bypassesPlayerLimit", False),
                    }
                )
        return {
            "status": "success",
            "ops": ops,
            "server_running": self._server_running(),
        }

    def op_player(self, name: str) -> Dict[str, Any]:
        if not self._server_running():
            return self._not_running()
        result = self._run_mc_command(f"op {name}")
        if not result.get("ok"):
            return {"status": "error", "message": result.get("error", "命令执行失败")}
        return {"status": "success", "message": f"已将 {name} 设为 OP"}

    def deop_player(self, name: str) -> Dict[str, Any]:
        if not self._server_running():
            return self._not_running()
        result = self._run_mc_command(f"deop {name}")
        if not result.get("ok"):
            return {"status": "error", "message": result.get("error", "命令执行失败")}
        return {"status": "success", "message": f"已取消 {name} 的 OP"}

    # ------------------------------------------------------------------ #
    # 封禁
    # ------------------------------------------------------------------ #

    def get_bans(self) -> Dict[str, Any]:
        players_data = self._load_json(
            self._working_dir() / "banned-players.json", []
        )
        players = []
        if isinstance(players_data, list):
            for item in players_data:
                players.append(
                    {
                        "uuid": format_uuid(item.get("uuid") or ""),
                        "name": item.get("name") or "",
                        "reason": item.get("reason") or "",
                        "created": item.get("created") or "",
                        "expires": item.get("expires") or "",
                        "source": item.get("source") or "",
                    }
                )
        ips_data = self._load_json(self._working_dir() / "banned-ips.json", [])
        ips = []
        if isinstance(ips_data, list):
            for item in ips_data:
                ips.append(
                    {
                        "ip": item.get("ip") or "",
                        "reason": item.get("reason") or "",
                        "created": item.get("created") or "",
                        "expires": item.get("expires") or "",
                        "source": item.get("source") or "",
                    }
                )
        return {
            "status": "success",
            "players": players,
            "ips": ips,
            "server_running": self._server_running(),
        }

    def _vanilla_timestamp(self) -> str:
        return datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")

    def ban_player(self, name: str, reason: str = "") -> Dict[str, Any]:
        if self._server_running():
            cmd = f"ban {name}"
            if reason:
                cmd += f" {reason}"
            result = self._run_mc_command(cmd)
            if not result.get("ok"):
                return {
                    "status": "error",
                    "message": result.get("error", "命令执行失败"),
                }
            return {
                "status": "success",
                "message": f"已封禁玩家 {name}",
                "needs_restart": False,
            }

        # 服务器离线：直接修改 banned-players.json（重启后生效）
        path = self._working_dir() / "banned-players.json"
        entries = self._load_json(path, [])
        if not isinstance(entries, list):
            entries = []
        entries = [e for e in entries if (e.get("name") or "") != name]
        entries.append(
            {
                "uuid": self._uuid_from_usercache(name) or "",
                "name": name,
                "created": self._vanilla_timestamp(),
                "source": "WebUI",
                "expires": "forever",
                "reason": reason or "由 WebUI 封禁",
            }
        )
        if not self._save_json(path, entries):
            return {"status": "error", "message": "写入 banned-players.json 失败"}
        return {
            "status": "success",
            "message": f"已通过文件封禁玩家 {name}（重启服务器后生效）",
            "needs_restart": True,
        }

    def ban_ip(self, ip: str, reason: str = "") -> Dict[str, Any]:
        if self._server_running():
            cmd = f"ban-ip {ip}"
            if reason:
                cmd += f" {reason}"
            result = self._run_mc_command(cmd)
            if not result.get("ok"):
                return {
                    "status": "error",
                    "message": result.get("error", "命令执行失败"),
                }
            return {
                "status": "success",
                "message": f"已封禁 IP {ip}",
                "needs_restart": False,
            }

        path = self._working_dir() / "banned-ips.json"
        entries = self._load_json(path, [])
        if not isinstance(entries, list):
            entries = []
        entries = [e for e in entries if (e.get("ip") or "") != ip]
        entries.append(
            {
                "ip": ip,
                "created": self._vanilla_timestamp(),
                "source": "WebUI",
                "expires": "forever",
                "reason": reason or "由 WebUI 封禁",
            }
        )
        if not self._save_json(path, entries):
            return {"status": "error", "message": "写入 banned-ips.json 失败"}
        return {
            "status": "success",
            "message": f"已通过文件封禁 IP {ip}（重启服务器后生效）",
            "needs_restart": True,
        }

    def unban_player(self, name: str) -> Dict[str, Any]:
        """解封玩家：仅通过修改 banned-players.json，重启服务器后生效。"""
        path = self._working_dir() / "banned-players.json"
        entries = self._load_json(path, [])
        if not isinstance(entries, list):
            entries = []
        target = name.strip().lower()
        remaining = []
        removed = False
        for e in entries:
            match_name = (e.get("name") or "").lower() == target
            match_uuid = (
                format_uuid(e.get("uuid") or "").lower()
                == format_uuid(name).lower()
            )
            if match_name or match_uuid:
                removed = True
                continue
            remaining.append(e)
        if not removed:
            return {"status": "error", "message": f"未找到玩家 {name} 的封禁记录"}
        if not self._save_json(path, remaining):
            return {"status": "error", "message": "写入 banned-players.json 失败"}
        return {
            "status": "success",
            "message": f"已解封玩家 {name}（重启服务器后生效）",
            "needs_restart": True,
        }

    def unban_ip(self, ip: str) -> Dict[str, Any]:
        """解封 IP：仅通过修改 banned-ips.json，重启服务器后生效。"""
        path = self._working_dir() / "banned-ips.json"
        entries = self._load_json(path, [])
        if not isinstance(entries, list):
            entries = []
        target = ip.strip()
        remaining = [e for e in entries if (e.get("ip") or "") != target]
        if len(remaining) == len(entries):
            return {"status": "error", "message": f"未找到 IP {ip} 的封禁记录"}
        if not self._save_json(path, remaining):
            return {"status": "error", "message": "写入 banned-ips.json 失败"}
        return {
            "status": "success",
            "message": f"已解封 IP {ip}（重启服务器后生效）",
            "needs_restart": True,
        }

    # ------------------------------------------------------------------ #
    # 踢出
    # ------------------------------------------------------------------ #

    def kick_player(self, name: str, reason: str = "") -> Dict[str, Any]:
        if not self._server_running():
            return self._not_running()
        cmd = f"kick {name}"
        if reason:
            cmd += f" {reason}"
        result = self._run_mc_command(cmd)
        if not result.get("ok"):
            return {"status": "error", "message": result.get("error", "命令执行失败")}
        return {"status": "success", "message": f"已将 {name} 踢出服务器"}
