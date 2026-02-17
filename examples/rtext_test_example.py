#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RText功能测试示例

这个示例展示了如何使用WebUI的RText功能发送富文本消息
现在使用统一的 send_message_to_webui 函数，通过 is_rtext=True 参数发送RText消息
"""

from mcdreforged.api.command import Literal, QuotableText
from mcdreforged.api.rtext import RAction, RColor, RStyle, RText, RTextList
from mcdreforged.api.types import PluginServerInterface

def on_load(server: PluginServerInterface, old):
    """插件加载时注册命令"""
    
    def show_help(source):
        """显示帮助信息"""
        help_msg = RTextList(
            RText("=== RText测试插件 ===", color=RColor.gold, bold=True),
            RText("\n可用命令:", color=RColor.yellow),
            RText("\n!!rtext test", color=RColor.green),
            RText(" - 发送各种RText测试消息", color=RColor.white),
            RText("\n!!rtext color <消息>", color=RColor.green),
            RText(" - 发送彩色消息", color=RColor.white),
            RText("\n!!rtext click <命令>", color=RColor.green),
            RText(" - 发送可点击消息", color=RColor.white),
            RText("\n!!rtext hover <消息>", color=RColor.green),
            RText(" - 发送悬停消息", color=RColor.white),
            RText("\n!!rtext mcdr", color=RColor.green),
            RText(" - 发送MCDR RText对象消息", color=RColor.white)
        )
        source.reply(help_msg)
    
    def test_command(source, ctx):
        """测试命令"""
        test_rtext_messages(source, ctx)
    
    def color_command(source, ctx):
        """彩色消息命令"""
        test_colored_message(source, ctx)
    
    def click_command(source, ctx):
        """点击消息命令"""
        test_clickable_message(source, ctx)
    
    def hover_command(source, ctx):
        """悬停消息命令"""
        test_hover_message(source, ctx)
    
    def mcdr_command(source, ctx):
        """MCDR RText消息命令"""
        test_mcdr_rtext_message(source, ctx)
    
    # 注册命令
    server.register_command(
        Literal('!!rtext').runs(show_help)
        .then(Literal('test').runs(test_command))
        .then(Literal('color').then(QuotableText('message').runs(color_command)))
        .then(Literal('click').then(QuotableText('command').runs(click_command)))
        .then(Literal('hover').then(QuotableText('message').runs(hover_command)))
        .then(Literal('mcdr').runs(mcdr_command))
    )

def test_rtext_messages(src, ctx):
    """测试各种RText消息"""
    server = src.get_server()
    
    # 获取WebUI插件实例
    webui_plugin = server.get_plugin_instance("guguwebui")
    if not webui_plugin or not hasattr(webui_plugin, 'send_message_to_webui'):
        src.reply(RText("WebUI插件未找到或版本过低，无法使用RText功能", color=RColor.red))
        return
    
    # 测试1：简单的彩色消息
    rtext1 = {
        "text": "这是",
        "color": "red",
        "bold": True,
        "extra": [
            {"text": "一条", "color": "blue"},
            {"text": "彩色", "color": "green", "italic": True},
            {"text": "消息", "color": "gold", "underlined": True}
        ]
    }
    
    webui_plugin.send_message_to_webui(
        server_interface=server,
        source="RTextTest",
        message=rtext1,
        message_type="info",
        is_rtext=True
    )
    
    # 测试2：带点击事件的消息
    rtext2 = {
        "text": "点击我执行命令",
        "color": "yellow",
        "bold": True,
        "underlined": True,
        "clickEvent": {
            "action": "suggest_command",
            "value": "/say Hello from RText!"
        },
        "hoverEvent": {
            "action": "show_text",
            "value": "点击执行 /say Hello from RText!"
        }
    }
    
    webui_plugin.send_message_to_webui(
        server_interface=server,
        source="RTextTest",
        message=rtext2,
        message_type="success",
        is_rtext=True
    )
    
    # 测试3：复合消息
    rtext3 = [
        {"text": "欢迎", "color": "green", "bold": True},
        {"text": "使用", "color": "blue"},
        {"text": "RText", "color": "gold", "italic": True, "underlined": True},
        {"text": "功能！", "color": "red"}
    ]
    
    webui_plugin.send_message_to_webui(
        server_interface=server,
        source="RTextTest",
        message=rtext3,
        message_type="info",
        is_rtext=True
    )
    
    # 测试4：发送普通消息到WebUI（会自动转换为RText格式）
    webui_plugin.send_message_to_webui(
        server_interface=server,
        source="RTextTest",
        message="这是一条普通消息，会被转换为RText格式",
        message_type="info"
    )
    
    src.reply(RText("已发送4条RText测试消息到WebUI", color=RColor.green))

def test_colored_message(src, ctx):
    """测试彩色消息"""
    server = src.get_server()
    message = ctx['message']
    
    webui_plugin = server.get_plugin_instance("guguwebui")
    if not webui_plugin or not hasattr(webui_plugin, 'send_message_to_webui'):
        src.reply(RText("WebUI插件未找到", color=RColor.red))
        return
    
    rtext = {
        "text": message,
        "color": "aqua",
        "bold": True
    }
    
    webui_plugin.send_message_to_webui(
        server_interface=server,
        source="RTextTest",
        message=rtext,
        message_type="info",
        is_rtext=True
    )
    
    src.reply(RText(f"已发送彩色消息: {message}", color=RColor.green))

def test_clickable_message(src, ctx):
    """测试可点击消息"""
    server = src.get_server()
    command = ctx['command']
    
    webui_plugin = server.get_plugin_instance("guguwebui")
    if not webui_plugin or not hasattr(webui_plugin, 'send_message_to_webui'):
        src.reply(RText("WebUI插件未找到", color=RColor.red))
        return
    
    rtext = {
        "text": f"点击执行: {command}",
        "color": "yellow",
        "underlined": True,
        "clickEvent": {
            "action": "run_command",
            "value": command
        },
        "hoverEvent": {
            "action": "show_text",
            "value": f"点击执行命令: {command}"
        }
    }
    
    webui_plugin.send_message_to_webui(
        server_interface=server,
        source="RTextTest",
        message=rtext,
        message_type="warning",
        is_rtext=True
    )
    
    src.reply(RText(f"已发送可点击消息，命令: {command}", color=RColor.green))

def test_hover_message(src, ctx):
    """测试悬停消息"""
    server = src.get_server()
    message = ctx['message']
    
    webui_plugin = server.get_plugin_instance("guguwebui")
    if not webui_plugin or not hasattr(webui_plugin, 'send_message_to_webui'):
        src.reply(RText("WebUI插件未找到", color=RColor.red))
        return
    
    rtext = {
        "text": "悬停查看详细信息",
        "color": "light_purple",
        "italic": True,
        "hoverEvent": {
            "action": "show_text",
            "value": message
        }
    }
    
    webui_plugin.send_message_to_webui(
        server_interface=server,
        source="RTextTest",
        message=rtext,
        message_type="info",
        is_rtext=True
    )
    
    src.reply(RText(f"已发送悬停消息，内容: {message}", color=RColor.green))

def test_mcdr_rtext_message(src, ctx):
    """测试MCDR RText对象消息"""
    server = src.get_server()
    
    webui_plugin = server.get_plugin_instance("guguwebui")
    if not webui_plugin or not hasattr(webui_plugin, 'send_message_to_webui'):
        src.reply(RText("WebUI插件未找到", color=RColor.red))
        return
    
    # 测试1：简单的MCDR RText对象
    mcdr_rtext1 = RTextList(
        RText("这是", color=RColor.red, styles=RStyle.bold),
        RText("一条", color=RColor.blue),
        RText("MCDR", color=RColor.green, styles=RStyle.italic),
        RText("RText", color=RColor.gold, styles=RStyle.underlined),
        RText("消息", color=RColor.aqua)
    )
    
    webui_plugin.send_message_to_webui(
        server_interface=server,
        source="RTextTest",
        message=mcdr_rtext1,
        message_type="info",
        is_rtext=True
    )
    
    # 测试2：带点击事件的MCDR RText对象
    mcdr_rtext2 = RText("点击我执行命令", color=RColor.yellow, styles=[RStyle.bold, RStyle.underlined])
    mcdr_rtext2.c(RAction.suggest_command, "/say Hello from MCDR RText!")
    mcdr_rtext2.h("点击执行 /say Hello from MCDR RText!")
    
    webui_plugin.send_message_to_webui(
        server_interface=server,
        source="RTextTest",
        message=mcdr_rtext2,
        message_type="success",
        is_rtext=True
    )
    
    # 测试3：复杂的MCDR RText对象
    mcdr_rtext3 = RTextList(
        RText("欢迎", color=RColor.green, styles=RStyle.bold),
        RText("使用", color=RColor.blue),
        RText("MCDR", color=RColor.gold, styles=[RStyle.italic, RStyle.underlined]),
        RText("RText", color=RColor.red, styles=[RStyle.bold, RStyle.italic]),
        RText("功能！", color=RColor.light_purple)
    )
    
    webui_plugin.send_message_to_webui(
        server_interface=server,
        source="RTextTest",
        message=mcdr_rtext3,
        message_type="info",
        is_rtext=True
    )
    
    # 测试4：带多种事件的MCDR RText对象
    mcdr_rtext4 = RText("多功能按钮", color=RColor.aqua, styles=[RStyle.bold, RStyle.underlined])
    mcdr_rtext4.c(RAction.run_command, "/say 这是通过MCDR RText发送的消息！")
    mcdr_rtext4.h("点击执行命令，悬停查看提示")
    
    webui_plugin.send_message_to_webui(
        server_interface=server,
        source="RTextTest",
        message=mcdr_rtext4,
        message_type="warning",
        is_rtext=True
    )
    
    src.reply(RText("已发送4条MCDR RText测试消息到WebUI", color=RColor.green))

# 使用说明
"""
使用方法：
!!rtext test          - 发送各种RText测试消息（JSON格式）
!!rtext color <消息>   - 发送彩色消息（JSON格式）
!!rtext click <命令>   - 发送可点击消息（JSON格式）
!!rtext hover <消息>   - 发送悬停消息（JSON格式）
!!rtext mcdr          - 发送MCDR RText对象消息

示例：
!!rtext color 这是一条彩色消息
!!rtext click /say Hello World
!!rtext hover 这是悬停时显示的内容
!!rtext mcdr

注意：
- 现在使用 send_message_to_webui 函数发送RText消息
- 通过 is_rtext=True 参数指定消息为RText格式
- 消息会同步到游戏中（如果有玩家在线）
- JSON格式和MCDR RText对象格式都支持
"""