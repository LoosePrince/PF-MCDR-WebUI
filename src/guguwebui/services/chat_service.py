import datetime
import random
import secrets
import string
import time
from typing import Any, Dict, Optional, Tuple

from guguwebui.constant import DEFALUT_CONFIG, user_db
from guguwebui.state import RCON_ONLINE_CACHE, WEB_ONLINE_PLAYERS
from guguwebui.structures import BusinessException
from guguwebui.utils.auth_util import (
    cleanup_chat_verifications,
    hash_password,
    verify_password,
)
from guguwebui.utils.chat_logger import ChatLogger
from guguwebui.utils.mc_util import (
    create_chat_logger_status_rtext,
    create_chat_message_rtext,
    get_bot_list,
    get_java_server_info,
    get_player_uuid,
    get_server_port,
)


class ChatService:
    def __init__(self, server, config_service=None):
        self.server = server
        self.config_service = config_service
        self.chat_logger = ChatLogger()

    def generate_verification_code(self) -> Tuple[str, int]:
        """生成聊天页验证码"""
        config = self.config_service.get_config()
        if not config.get("public_chat_enabled", False):
            raise BusinessException("公开聊天页未启用", status_code=400)

        cleanup_chat_verifications()

        code = "".join(random.choices(string.digits + string.ascii_uppercase, k=6))
        expire_minutes = config.get("chat_verification_expire_minutes", 10)
        expire_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            minutes=expire_minutes
        )

        user_db["chat_verification"][code] = {
            "player_id": None,
            "expire_time": str(expire_time),
            "used": False,
        }
        user_db.save()

        self.server.logger.debug(f"生成聊天页验证码: {code}")
        return code, expire_minutes

    def check_verification_status(self, code: str) -> Dict[str, Any]:
        """检查验证码验证状态"""
        if not code:
            raise BusinessException("验证码不能为空")

        if code not in user_db["chat_verification"]:
            raise BusinessException("验证码不存在")

        verification = user_db["chat_verification"][code]
        expire_time = datetime.datetime.fromisoformat(
            verification["expire_time"].replace("Z", "+00:00")
        )

        if datetime.datetime.now(datetime.timezone.utc) > expire_time:
            del user_db["chat_verification"][code]
            user_db.save()
            raise BusinessException("验证码已过期")

        if verification.get("player_id"):
            return {
                "status": "success",
                "verified": True,
                "player_id": verification["player_id"],
            }

        return {"status": "pending", "message": "验证码尚未在游戏内验证"}

    async def set_user_password(self, code: str, password: str) -> Dict[str, Any]:
        """设置聊天页用户密码"""
        password = password.replace("<", "").replace(">", "")

        if not code or not password:
            raise BusinessException("验证码和密码不能为空")

        if len(password) < 6:
            raise BusinessException("密码长度至少6位")

        if code not in user_db["chat_verification"]:
            raise BusinessException("验证码不存在")

        verification = user_db["chat_verification"][code]
        expire_time = datetime.datetime.fromisoformat(
            verification["expire_time"].replace("Z", "+00:00")
        )

        if datetime.datetime.now(datetime.timezone.utc) > expire_time:
            del user_db["chat_verification"][code]
            user_db.save()
            raise BusinessException("验证码已过期")

        if verification.get("used") and (verification.get("player_id") is None):
            raise BusinessException("验证码已被使用")

        if verification.get("player_id") is None:
            raise BusinessException("验证码尚未在游戏内验证")

        player_id = verification["player_id"]

        user_db["chat_users"][player_id] = {
            "password": hash_password(password),
            "created_time": str(datetime.datetime.now(datetime.timezone.utc)),
        }
        user_db.save()

        try:
            del user_db["chat_verification"][code]
            user_db.save()
        except Exception:
            pass

        self.server.logger.debug(f"聊天页用户 {player_id} 设置密码成功")

        result = {
            "status": "success",
            "message": "密码设置成功",
            "player_id": player_id,
        }
        try:
            uuid_val = await get_player_uuid(player_id, self.server)
            if uuid_val:
                result["uuid"] = uuid_val
        except Exception:
            pass
        return result

    async def login(
        self, player_id: str, password: str, client_ip: str
    ) -> Dict[str, Any]:
        """聊天页用户登录"""
        player_id = player_id.replace("<", "").replace(">", "")
        password = password.replace("<", "").replace(">", "")

        if not player_id or not password:
            raise BusinessException("玩家ID和密码不能为空")

        if player_id not in user_db["chat_users"]:
            raise BusinessException("用户不存在")

        if not verify_password(password, user_db["chat_users"][player_id]["password"]):
            raise BusinessException("密码错误")

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        active_ips = set()
        sessions_to_delete = []
        for sid, sess in list(user_db["chat_sessions"].items()):
            try:
                expire_time = datetime.datetime.fromisoformat(
                    sess["expire_time"].replace("Z", "+00:00")
                )
                if now_utc > expire_time:
                    sessions_to_delete.append(sid)
                    continue
                if sess.get("player_id") == player_id:
                    active_ips.add(sess.get("ip") or "unknown")
            except Exception:
                sessions_to_delete.append(sid)

        for sid in sessions_to_delete:
            try:
                del user_db["chat_sessions"][sid]
            except KeyError:
                pass
        if sessions_to_delete:
            user_db.save()

        if len(active_ips) >= 2 and client_ip not in active_ips:
            raise BusinessException(
                "该账号登录IP已达上限，请先在其他设备退出或等待会话过期"
            )

        session_id = secrets.token_hex(16)
        config = self.config_service.get_config()
        expire_hours = config.get("chat_session_expire_hours", 24)
        expire_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            hours=expire_hours
        )

        user_db["chat_sessions"][session_id] = {
            "player_id": player_id,
            "expire_time": str(expire_time),
            "ip": client_ip,
            "last_sent_ms": 0,
        }
        user_db.save()

        self.server.logger.debug(f"聊天页用户 {player_id} 登录成功")

        result = {
            "status": "success",
            "message": "登录成功",
            "session_id": session_id,
            "player_id": player_id,
        }
        try:
            uuid_val = await get_player_uuid(player_id, self.server)
            if uuid_val:
                result["uuid"] = uuid_val
        except Exception:
            pass
        return result

    async def check_session(self, session_id: str) -> Dict[str, Any]:
        """检查聊天页会话状态"""
        if not session_id:
            raise BusinessException("会话ID不能为空")

        if session_id not in user_db["chat_sessions"]:
            raise BusinessException("会话不存在")

        session = user_db["chat_sessions"][session_id]
        expire_time = datetime.datetime.fromisoformat(
            session["expire_time"].replace("Z", "+00:00")
        )

        if datetime.datetime.now(datetime.timezone.utc) > expire_time:
            del user_db["chat_sessions"][session_id]
            user_db.save()
            raise BusinessException("会话已过期")

        player_id = session["player_id"]
        result = {"status": "success", "valid": True, "player_id": player_id}
        try:
            uuid_val = await get_player_uuid(player_id, self.server)
            if uuid_val:
                result["uuid"] = uuid_val
        except Exception:
            pass
        return result

    def logout(self, session_id: str):
        """聊天页用户退出登录"""
        if session_id in user_db["chat_sessions"]:
            del user_db["chat_sessions"][session_id]
            user_db.save()
        return {"status": "success", "message": "退出登录成功"}

    async def get_messages(
        self,
        limit: int = 50,
        offset: int = 0,
        after_id: Optional[int] = None,
        before_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """获取聊天消息"""
        if after_id is not None:
            messages = self.chat_logger.get_new_messages(after_id)
        elif before_id is not None:
            messages = self.chat_logger.get_messages(limit=limit, before_id=before_id)
        else:
            messages = self.chat_logger.get_messages(limit, offset)

        try:
            uuid_cache = {}
            need_uuid_players = set()
            for m in messages:
                pid = m.get("player_id")
                if pid and not m.get("is_plugin", False) and m.get("uuid") is None:
                    need_uuid_players.add(pid)

            if need_uuid_players:
                for pid in need_uuid_players:
                    uuid_cache[pid] = await get_player_uuid(pid, self.server)

            for m in messages:
                pid = m.get("player_id")
                if pid and m.get("uuid") is None and not m.get("is_plugin", False):
                    if pid in uuid_cache:
                        m["uuid"] = uuid_cache[pid]
        except Exception:
            pass

        return {
            "status": "success",
            "messages": messages,
            "has_more": len(messages) == limit,
        }

    async def get_new_messages(
        self, after_id: int = 0, player_id_heartbeat: str = None
    ) -> Dict[str, Any]:
        """获取新消息（基于最后消息ID）"""
        messages = self.chat_logger.get_new_messages(after_id)

        try:
            uuid_cache = {}
            for m in messages:
                pid = m.get("player_id")
                if not pid:
                    continue
                if pid not in uuid_cache:
                    uuid_cache[pid] = await get_player_uuid(pid, self.server)
                m["uuid"] = uuid_cache[pid]
        except Exception:
            pass

        if player_id_heartbeat:
            WEB_ONLINE_PLAYERS[player_id_heartbeat] = int(time.time()) + 5

        online_web = [
            pid
            for pid, until in WEB_ONLINE_PLAYERS.items()
            if until >= int(time.time())
        ]
        online_game = []

        if self.server.is_rcon_running():
            now_sec = int(time.time())
            if RCON_ONLINE_CACHE["dirty"] or (
                now_sec - int(RCON_ONLINE_CACHE["ts"]) >= 300
            ):
                try:
                    feedback = self.server.rcon_query("list")
                    names = set()
                    if isinstance(feedback, str) and ":" in feedback:
                        names_part = feedback.split(":", 1)[1].strip()
                        if names_part:
                            for name in [
                                n.strip() for n in names_part.split(",") if n.strip()
                            ]:
                                names.add(name)
                    RCON_ONLINE_CACHE["names"] = names
                    RCON_ONLINE_CACHE["ts"] = now_sec
                    RCON_ONLINE_CACHE["dirty"] = False
                except Exception:
                    pass
            online_game = list(RCON_ONLINE_CACHE["names"])

        online_bot = get_bot_list(self.server)

        return {
            "status": "success",
            "messages": messages,
            "last_message_id": self.chat_logger.get_last_message_id(),
            "online": {"web": online_web, "game": online_game, "bot": online_bot},
        }

    def clear_messages(self):
        """清空聊天消息"""
        self.chat_logger.clear_messages()
        status_msg = create_chat_logger_status_rtext("clear", True)
        self.server.logger.info(status_msg)
        return {"status": "success", "message": "聊天消息已清空"}

    def get_status_code_for_result(self, result: Dict[str, Any]) -> int:
        """获取结果对应的 HTTP 状态码"""
        if result.get("status") != "error":
            return 200
        msg = result.get("message", "")
        if "过于频繁" in msg:
            return 429
        if "过期" in msg or "不匹配" in msg:
            return 401
        if "未启用" in msg:
            return 403
        return 400

    async def send_message(
        self, message: str, player_id: str, session_id: str, is_admin: bool = False
    ):
        """发送聊天消息到游戏"""
        if not message:
            raise BusinessException("消息内容不能为空")
        if not player_id:
            raise BusinessException("玩家ID无效")

        if not is_admin:
            if not session_id or session_id not in user_db["chat_sessions"]:
                raise BusinessException("会话无效或已过期，请重新登录")

            session = user_db["chat_sessions"][session_id]
            if session["player_id"] != player_id:
                raise BusinessException("玩家ID与会话不匹配")

            expire_time = datetime.datetime.fromisoformat(
                session["expire_time"].replace("Z", "+00:00")
            )
            if datetime.datetime.now(datetime.timezone.utc) > expire_time:
                del user_db["chat_sessions"][session_id]
                user_db.save()
                raise BusinessException("会话已过期，请重新登录")

            now_ms = int(time.time() * 1000)
            if now_ms - session.get("last_sent_ms", 0) < 2000:
                raise BusinessException("发送过于频繁，请稍后再试")
            session["last_sent_ms"] = now_ms
            user_db.save()

        config = self.config_service.get_config()
        if not config.get("public_chat_to_game_enabled", False):
            raise BusinessException("聊天到游戏功能未启用")

        player_uuid = await get_player_uuid(player_id, self.server) or "未知"
        rtext_message = create_chat_message_rtext(player_id, message, player_uuid)

        # 分发事件
        try:
            from mcdreforged.api.all import LiteralEvent

            event_data = (
                "webui",
                player_id,
                player_uuid,
                message,
                session_id,
                int(time.time()),
            )
            self.server.dispatch_event(
                LiteralEvent("webui.chat_message_sent"), event_data
            )
        except Exception as e:
            self.server.logger.error(f"分发WebUI聊天消息事件失败: {e}")

        # 检查在线人数
        player_count = 0
        try:
            import javaproperties

            from guguwebui.utils.mc_util import get_minecraft_path

            with open(
                get_minecraft_path(self.server, "working_directory")
                + "/server.properties",
                "r",
            ) as f:
                props = javaproperties.load(f)
                mc_port = int(props.get("server-port", 25565))
            info = await get_java_server_info(mc_port)
            player_count = int(info.get("server_player_count", 0))
        except Exception:
            pass

        if player_count <= 0:
            self.chat_logger.add_message(
                player_id,
                message,
                rtext_data=rtext_message.to_json_object(),
                message_type=1,
                server=self.server,
            )
            return {"status": "success", "message": "已记录（当前无在线玩家）"}

        self.server.broadcast(rtext_message)
        WEB_ONLINE_PLAYERS[player_id] = int(time.time()) + 5
        self.chat_logger.add_message(
            player_id,
            message,
            rtext_data=rtext_message.to_json_object(),
            message_type=1,
            server=self.server,
        )

        return {"status": "success", "message": "消息发送成功"}
