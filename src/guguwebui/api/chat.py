"""
聊天API模块
包含所有聊天相关的业务逻辑函数
"""

import datetime
import random
import secrets
import string
import time
from typing import Any, Dict, Optional, Tuple

from mcdreforged.api.all import PluginServerInterface

from guguwebui.constant import DEFALUT_CONFIG, user_db
from guguwebui.state import RCON_ONLINE_CACHE, WEB_ONLINE_PLAYERS
from guguwebui.utils.auth_util import cleanup_chat_verifications, hash_password, verify_password
from guguwebui.utils.chat_logger import ChatLogger
from guguwebui.utils.mc_util import create_chat_logger_status_rtext, create_chat_message_rtext, get_bot_list, \
    get_java_server_info, get_player_uuid, get_server_port


# ============================================================#
# 验证码管理功能
def generate_chat_verification_code(server: PluginServerInterface) -> Tuple[str, int]:
    """
    生成聊天页验证码

    Args:
        server: MCDR服务器接口

    Returns:
        Tuple[str, int]: (验证码, 过期分钟数)
    """
    # 检查公开聊天页是否启用
    server_config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
    if not server_config.get("public_chat_enabled", False):
        raise ValueError("公开聊天页未启用")

    # 生成前清理一次
    cleanup_chat_verifications()

    # 生成6位数字+大写字母验证码
    code = ''.join(random.choices(string.digits + string.ascii_uppercase, k=6))
    expire_minutes = server_config.get("chat_verification_expire_minutes", 10)
    expire_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=expire_minutes)

    user_db["chat_verification"][code] = {
        "player_id": None,
        "expire_time": str(expire_time),
        "used": False
    }
    user_db.save()

    server.logger.debug(f"生成聊天页验证码: {code}")
    return code, expire_minutes


def check_chat_verification_status(code: str) -> Dict[str, Any]:
    """
    检查验证码验证状态

    Args:
        code: 验证码

    Returns:
        Dict: 验证结果
    """
    if not code:
        return {"status": "error", "message": "验证码不能为空"}

    # 检查验证码是否存在且未过期
    if code not in user_db["chat_verification"]:
        return {"status": "error", "message": "验证码不存在"}

    verification = user_db["chat_verification"][code]

    # 检查是否已过期
    expire_time = datetime.datetime.fromisoformat(verification["expire_time"].replace('Z', '+00:00'))
    if datetime.datetime.now(datetime.timezone.utc) > expire_time:
        # 删除过期验证码
        del user_db["chat_verification"][code]
        user_db.save()
        return {"status": "error", "message": "验证码已过期"}

    # 若已绑定玩家则视为验证成功（即使used为True）
    if verification.get("player_id"):
        return {
            "status": "success",
            "verified": True,
            "player_id": verification["player_id"]
        }

    # 未绑定则尚未在游戏内验证
    return {"status": "error", "message": "验证码尚未在游戏内验证"}


async def set_chat_user_password(code: str, password: str, server: PluginServerInterface) -> Dict[str, Any]:
    """
    设置聊天页用户密码

    Args:
        code: 验证码
        password: 密码
        server: MCDR服务器接口

    Returns:
        Dict: 设置结果
    """
    # 防呆处理：自动去除密码中可能存在的<>字符
    password = password.replace('<', '').replace('>', '')

    if not code or not password:
        return {"status": "error", "message": "验证码和密码不能为空"}

    if len(password) < 6:
        return {"status": "error", "message": "密码长度至少6位"}

    if code not in user_db["chat_verification"]:
        return {"status": "error", "message": "验证码不存在"}

    verification = user_db["chat_verification"][code]

    # 过期则删除
    expire_time = datetime.datetime.fromisoformat(verification["expire_time"].replace('Z', '+00:00'))
    if datetime.datetime.now(datetime.timezone.utc) > expire_time:
        del user_db["chat_verification"][code]
        user_db.save()
        return {"status": "error", "message": "验证码已过期"}

    # 已使用但未绑定当前玩家，拒绝
    if verification.get("used") and (verification.get("player_id") is None):
        return {"status": "error", "message": "验证码已被使用"}

    if verification.get("player_id") is None:
        return {"status": "error", "message": "验证码尚未在游戏内验证"}

    player_id = verification["player_id"]

    # 保存用户密码
    user_db["chat_users"][player_id] = {
        "password": hash_password(password),
        "created_time": str(datetime.datetime.now(datetime.timezone.utc))
    }
    user_db.save()

    # 设置成功后删除验证码记录，避免复用
    try:
        del user_db["chat_verification"][code]
        user_db.save()
    except Exception:
        pass

    if server:
        server.logger.debug(f"聊天页用户 {player_id} 设置密码成功")

    result = {"status": "success", "message": "密码设置成功", "player_id": player_id}
    if server:
        try:
            uuid_val = await get_player_uuid(player_id, server)
            if uuid_val:
                result["uuid"] = uuid_val
        except Exception:
            pass
    return result


# ============================================================#
# 用户认证功能
async def chat_user_login(player_id: str, password: str, client_ip: str, server: PluginServerInterface) -> Dict[
    str, Any]:
    """
    聊天页用户登录

    Args:
        player_id: 玩家ID
        password: 密码
        client_ip: 客户端IP
        server: MCDR服务器接口

    Returns:
        Dict: 登录结果
    """
    # 防呆处理：自动去除可能存在的<>字符
    player_id = player_id.replace('<', '').replace('>', '')
    password = password.replace('<', '').replace('>', '')

    if not player_id or not password:
        return {"status": "error", "message": "玩家ID和密码不能为空"}

    # 检查用户是否存在
    if player_id not in user_db["chat_users"]:
        return {"status": "error", "message": "用户不存在"}

    # 验证密码
    if not verify_password(password, user_db["chat_users"][player_id]["password"]):
        return {"status": "error", "message": "密码错误"}

    # 登录IP限制：同一玩家最多允许两个不同IP同时在线
    # 清理过期会话并统计该玩家的有效IP集合
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    active_ips = set()
    sessions_to_delete = []
    for sid, sess in list(user_db["chat_sessions"].items()):
        try:
            expire_time = datetime.datetime.fromisoformat(sess["expire_time"].replace('Z', '+00:00'))
        except Exception:
            # 异常数据直接清理
            sessions_to_delete.append(sid)
            continue
        if now_utc > expire_time:
            sessions_to_delete.append(sid)
            continue
        if sess.get("player_id") == player_id:
            ip = sess.get("ip") or "unknown"
            active_ips.add(ip)

    # 执行清理
    for sid in sessions_to_delete:
        try:
            del user_db["chat_sessions"][sid]
        except KeyError:
            pass
    if sessions_to_delete:
        user_db.save()

    # 若已有两个不同IP且当前IP不在其中，拒绝登录
    if len(active_ips) >= 2 and client_ip not in active_ips:
        return {"status": "error", "message": "该账号登录IP已达上限，请先在其他设备退出或等待会话过期"}

    # 生成会话ID
    session_id = secrets.token_hex(16)

    # 设置会话过期时间
    server_config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
    expire_hours = server_config.get("chat_session_expire_hours", 24)
    expire_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=expire_hours)

    # 保存会话信息
    user_db["chat_sessions"][session_id] = {
        "player_id": player_id,
        "expire_time": str(expire_time),
        "ip": client_ip,
        "last_sent_ms": 0
    }
    user_db.save()

    if server:
        server.logger.debug(f"聊天页用户 {player_id} 登录成功")

    result = {
        "status": "success",
        "message": "登录成功",
        "session_id": session_id,
        "player_id": player_id
    }
    if server:
        try:
            uuid_val = await get_player_uuid(player_id, server)
            if uuid_val:
                result["uuid"] = uuid_val
        except Exception:
            pass
    return result


async def check_chat_session(session_id: str, server: PluginServerInterface = None) -> Dict[str, Any]:
    """
    检查聊天页会话状态

    Args:
        session_id: 会话ID
        server: MCDR服务器接口（用于获取玩家UUID）

    Returns:
        Dict: 会话状态
    """
    if not session_id:
        return {"status": "error", "message": "会话ID不能为空"}

    # 检查会话是否存在
    if session_id not in user_db["chat_sessions"]:
        return {"status": "error", "message": "会话不存在"}

    session = user_db["chat_sessions"][session_id]

    # 检查是否已过期
    expire_time = datetime.datetime.fromisoformat(session["expire_time"].replace('Z', '+00:00'))
    if datetime.datetime.now(datetime.timezone.utc) > expire_time:
        # 删除过期会话
        del user_db["chat_sessions"][session_id]
        user_db.save()
        return {"status": "error", "message": "会话已过期"}

    player_id = session["player_id"]
    result = {
        "status": "success",
        "valid": True,
        "player_id": player_id
    }
    if server:
        try:
            uuid_val = await get_player_uuid(player_id, server)
            if uuid_val:
                result["uuid"] = uuid_val
        except Exception:
            pass
    return result


def chat_user_logout(session_id: str) -> Dict[str, Any]:
    """
    聊天页用户退出登录

    Args:
        session_id: 会话ID

    Returns:
        Dict: 退出结果
    """
    if not session_id:
        return {"status": "error", "message": "会话ID不能为空"}

    # 删除会话
    if session_id in user_db["chat_sessions"]:
        del user_db["chat_sessions"][session_id]
        user_db.save()

    return {"status": "success", "message": "退出登录成功"}


# ============================================================#
# 消息处理功能
async def get_chat_messages_handler(limit: int = 50, offset: int = 0, after_id: Optional[int] = None,
                                    before_id: Optional[int] = None, server: PluginServerInterface = None) -> Dict[
    str, Any]:
    """
    获取聊天消息

    Args:
        limit: 消息数量限制
        offset: 偏移量
        after_id: 消息ID起点
        before_id: 获取ID小于此值的历史消息
        server: MCDR服务器接口

    Returns:
        Dict: 消息数据
    """
    # 导入聊天日志记录器
    chat_logger = ChatLogger()

    if after_id is not None:
        # 获取指定ID之后的新消息
        messages = chat_logger.get_new_messages(after_id)
    elif before_id is not None:
        # 获取指定ID之前的历史消息
        messages = chat_logger.get_messages(limit=limit, before_id=before_id)
    else:
        # 兼容旧版本，使用offset方式
        messages = chat_logger.get_messages(limit, offset)

    # 为消息补充UUID信息（优化版本 - 优先使用存储的UUID，减少网络查询）
    try:
        uuid_cache = {}
        need_uuid_players = set()

        # 首先检查哪些消息需要补充UUID
        for m in messages:
            pid = m.get('player_id')
            if pid and not m.get('is_plugin', False):  # 插件消息不需要UUID
                if m.get('uuid') is None:  # 只有没有UUID的消息才需要查询
                    need_uuid_players.add(pid)

        # 只对缺失UUID的玩家进行网络查询
        if need_uuid_players:
            for pid in need_uuid_players:
                uuid_val = await get_player_uuid(pid, server)
                uuid_cache[pid] = uuid_val

        # 为缺失UUID的消息设置UUID
        for m in messages:
            pid = m.get('player_id')
            if pid and m.get('uuid') is None and not m.get('is_plugin', False):
                if pid in uuid_cache:
                    m['uuid'] = uuid_cache[pid]

    except Exception:
        # 静默失败，不影响消息返回
        pass

    return {
        "status": "success",
        "messages": messages,
        "has_more": len(messages) == limit
    }


async def get_new_chat_messages_handler(after_id: int = 0, player_id_heartbeat: str = None,
                                        server: PluginServerInterface = None) -> Dict[str, Any]:
    """
    获取新消息（基于最后消息ID）

    Args:
        after_id: 消息ID起点
        player_id_heartbeat: 心跳玩家ID
        server: MCDR服务器接口

    Returns:
        Dict: 新消息数据
    """
    # 导入聊天日志记录器
    chat_logger = ChatLogger()

    messages = chat_logger.get_new_messages(after_id)

    # 为消息补充UUID信息（带超时处理）
    try:
        uuid_cache = {}
        # 为每个玩家并行获取UUID
        for m in messages:
            pid = m.get('player_id')
            if not pid: continue
            if pid in uuid_cache:
                uuid_val = uuid_cache[pid]
            else:
                uuid_val = await get_player_uuid(pid, server)
                uuid_cache[pid] = uuid_val
            m['uuid'] = uuid_val
    except Exception:
        pass

    # 记录Web在线心跳（+5秒）
    try:
        if isinstance(player_id_heartbeat, str) and player_id_heartbeat:
            WEB_ONLINE_PLAYERS[player_id_heartbeat] = int(time.time()) + 5
    except Exception:
        pass

    # 生成在线列表：游戏在线（通过 get_java_server_info），Web在线（通过心跳）
    online_web = set(pid for pid, until in WEB_ONLINE_PLAYERS.items() if until >= int(time.time()))
    online_game = set()

    # 获取服务器信息
    # Need to get port from config
    mc_port = get_server_port(server)

    # 快速RCON查询
    if server.is_rcon_running():
        now_sec = int(time.time())
        if RCON_ONLINE_CACHE["dirty"] or (now_sec - int(RCON_ONLINE_CACHE["ts"]) >= 300):
            try:
                # RCON query is still sync in MCDR, but we can run it in executor if needed
                feedback = server.rcon_query("list")
                names = set()
                if isinstance(feedback, str) and ":" in feedback:
                    names_part = feedback.split(":", 1)[1].strip()
                    if names_part:
                        for name in [n.strip() for n in names_part.split(",") if n.strip()]:
                            names.add(name)
                RCON_ONLINE_CACHE["names"] = names
                RCON_ONLINE_CACHE["ts"] = now_sec
                RCON_ONLINE_CACHE["dirty"] = False
            except Exception:
                pass
        online_game = set(RCON_ONLINE_CACHE["names"])

    # 快速获取假人列表
    online_bot = get_bot_list(server)

    return {
        "status": "success",
        "messages": messages,
        "last_message_id": chat_logger.get_last_message_id(),
        "online": {
            "web": list(online_web),
            "game": list(online_game),
            "bot": online_bot
        }
    }


def clear_chat_messages_handler(server: PluginServerInterface = None) -> Dict[str, Any]:
    """
    清空聊天消息

    Args:
        server: MCDR服务器接口

    Returns:
        Dict: 清空结果
    """
    # 导入聊天日志记录器
    chat_logger = ChatLogger()

    # 清空消息
    chat_logger.clear_messages()

    if server:
        status_msg = create_chat_logger_status_rtext('clear', True)
        server.logger.info(status_msg)

    return {"status": "success", "message": "聊天消息已清空"}


async def send_chat_message_handler(message: str, player_id: str, session_id: str,
                                    server: PluginServerInterface = None, is_admin: bool = False) -> Dict[str, Any]:
    """
    发送聊天消息到游戏

    Args:
        message: 消息内容
        player_id: 玩家ID
        session_id: 会话ID
        server: MCDR服务器接口
        is_admin: 是否为管理员（来自WebUI）

    Returns:
        Dict: 发送结果
    """
    if not message:
        return {"status": "error", "message": "消息内容不能为空"}

    if not player_id:
        return {"status": "error", "message": "玩家ID无效"}

    # 验证会话（管理员跳过）
    if not is_admin:
        if not session_id:
            return {"status": "error", "message": "会话ID无效"}

        if session_id not in user_db["chat_sessions"]:
            return {"status": "error", "message": "会话已过期，请重新登录"}

        session = user_db["chat_sessions"][session_id]
        if session["player_id"] != player_id:
            return {"status": "error", "message": "玩家ID与会话不匹配"}

        # 检查会话是否过期
        expire_time = datetime.datetime.fromisoformat(session["expire_time"].replace('Z', '+00:00'))
        if datetime.datetime.now(datetime.timezone.utc) > expire_time:
            del user_db["chat_sessions"][session_id]
            user_db.save()
            return {"status": "error", "message": "会话已过期，请重新登录"}

        # 发言速率限制：同一会话2秒/条
        try:
            now_ms = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
            last_ms = int(session.get("last_sent_ms") or 0)
            if now_ms - last_ms < 2000:
                return {"status": "error", "message": "发送过于频繁，请稍后再试"}
            # 通过频控，更新发送时间
            session["last_sent_ms"] = now_ms
            user_db.save()
        except Exception:
            # 出现异常不影响正常发送
            pass

    if not server:
        return {"status": "error", "message": "服务器接口不可用"}

    # 检查是否启用了聊天到游戏功能
    config = server.load_config_simple("config.json", DEFALUT_CONFIG, echo_in_console=False)
    if not config.get("public_chat_to_game_enabled", False):
        return {"status": "error", "message": "聊天到游戏功能未启用"}

    # 获取玩家UUID（如果可用）
    try:
        player_uuid = await get_player_uuid(player_id, server)
        # 如果仍然没有找到UUID，设置为"未知"
        if not player_uuid:
            player_uuid = "未知"
    except Exception as e:
        server.logger.debug(f"获取玩家UUID失败: {e}")
        player_uuid = "未知"

    # 构建用于广播的 RText 消息
    rtext_message = create_chat_message_rtext(player_id, message, player_uuid)

    # 首先分发WebUI聊天消息事件，供其他插件监听和处理
    try:
        from mcdreforged.api.all import LiteralEvent
        # 创建事件数据元组 - MCDR会将元组展开为多个参数
        event_data = (
            "webui",  # source
            player_id,  # player_id
            player_uuid,  # player_uuid
            message,  # message
            session_id,  # session_id
            int(datetime.datetime.now(datetime.timezone.utc).timestamp())  # timestamp (Unix时间戳)
        )
        # 分发事件
        server.dispatch_event(LiteralEvent("webui.chat_message_sent"), event_data)
    except Exception as e:
        server.logger.error(f"分发WebUI聊天消息事件失败: {e}")

    # 如果当前服务器内没有玩家在线，则仅记录，不下发到游戏
    try:
        # Need to get port from config
        from ..utils.mc_util import get_minecraft_path
        import javaproperties
        try:
            with open(get_minecraft_path(server, "working_directory") + "/server.properties", "r") as f:
                props = javaproperties.load(f)
                mc_port = int(props.get("server-port", 25565))
        except:
            mc_port = 25565
        info = await get_java_server_info(mc_port)
        player_count_raw = info.get("server_player_count")
        player_count = int(player_count_raw) if player_count_raw is not None and str(player_count_raw).isdigit() else 0
    except Exception:
        player_count = 0

    if player_count <= 0:
        # 仅记录到聊天日志
        try:
            chat_logger = ChatLogger()
            # 记录RText格式的消息，标记为WebUI消息
            chat_logger.add_message(player_id, message, rtext_data=rtext_message.to_json_object(), message_type=1,
                                    server=server)
        except Exception as e:
            server.logger.warning(f"记录聊天消息失败: {e}")
        return {
            "status": "success",
            "message": "已记录（当前无在线玩家）"
        }

    # 有玩家在线，使用广播发送消息
    server.broadcast(rtext_message)

    # 记录Web在线心跳（发送者计为在线5秒）
    try:
        WEB_ONLINE_PLAYERS[player_id] = int(time.time()) + 5
    except Exception:
        pass

    # 记录到聊天日志
    try:
        chat_logger = ChatLogger()
        # 记录RText格式的消息，标记为WebUI消息，这样前端显示时就能正确渲染
        chat_logger.add_message(player_id, message, rtext_data=rtext_message.to_json_object(), message_type=1,
                                server=server)
    except Exception as e:
        server.logger.warning(f"记录聊天消息失败: {e}")

    # 使用RText美化成功消息
    success_msg = create_chat_message_rtext(player_id, message, player_uuid)
    server.logger.debug(f"WebUI聊天消息: {success_msg}")

    return {
        "status": "success",
        "message": "消息发送成功"
    }


# ============================================================#
# 事件处理功能
def on_player_joined(_server, _player: str, _info=None):
    """处理玩家加入事件"""
    try:
        RCON_ONLINE_CACHE["dirty"] = True
    except Exception:
        pass


def on_player_left(_server, _player: str):
    """处理玩家离开事件"""
    try:
        RCON_ONLINE_CACHE["dirty"] = True
    except Exception:
        pass
