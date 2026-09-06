"""玩家在线统计（会话日志）单元测试。

覆盖：会话记录（join/leave）、在线曲线扫描线、每日聚合、排除无 IP 玩家/假人、
开环会话兜底、90 天裁剪、旧文件无 sessions 键的迁移兼容。
"""

from __future__ import annotations

import time

import pytest

import guguwebui.services.player_service as ps_mod


class _FakeLogger:
    def debug(self, *a):
        pass

    def error(self, *a):
        pass

    def warning(self, *a):
        pass


class _FakeServer:
    def __init__(self, online=()):
        self._online = list(online)
        self.logger = _FakeLogger()

    def get_player_list(self):
        return list(self._online)

    def is_rcon_running(self):
        return False

    def is_server_running(self):
        return True

    def get_player_ip(self, name):
        return None

    def get_player_info(self, name):
        return None


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(ps_mod, "PLAYER_STATS_PATH", tmp_path / "player_stats.json")
    srv = _FakeServer()
    return ps_mod.PlayerService(srv), srv


def _minute_aligned_hour_ago():
    return float(int(time.time() // 60) * 60 - 3600)


def test_session_recorded_on_join_and_left(service):
    svc, srv = service
    svc.on_player_joined(srv, "Steve")
    time.sleep(0.05)
    svc.on_player_left(srv, "Steve")

    stats = svc._load_stats()
    assert stats["players"]["Steve"]["total_playtime"] > 0.04
    assert len(stats["sessions"]) == 1
    s = stats["sessions"][0]
    assert s["p"] == "Steve"
    assert s["j"] is not None
    assert s["l"] is not None and s["l"] >= s["j"]


def test_rejoin_closes_stale_open_session(service):
    """事件丢失（丢下线事件）时，重复上线应关闭旧开环会话，避免重复计数。"""
    svc, srv = service
    svc.on_player_joined(srv, "Steve")
    # 玩家离开事件丢失，直接再次上线
    svc.on_player_joined(srv, "Steve")
    stats = svc._load_stats()
    sessions = stats["sessions"]
    assert len(sessions) == 2
    assert sessions[0]["l"] is not None  # 旧会话已被关闭
    assert sessions[1]["l"] is None  # 新会话开环


def test_online_curve_sweep_line():
    """扫描线：任意时刻并发数为精确值（非采样近似），峰值/峰值时刻正确。"""
    start = _minute_aligned_hour_ago()
    end = start + 3600
    sessions = [
        {"p": "D", "j": start - 100, "l": start + 100},  # 窗口开始前已在
        {"p": "A", "j": start, "l": start + 120},  # 窗口起点加入
        {"p": "B", "j": start + 60, "l": None},  # 在线至窗口结束
        {"p": "C", "j": start + 90, "l": start + 600},  # 中途加入
    ]
    points, peak, peak_ts = ps_mod.PlayerService._online_curve(sessions, start, end)
    assert points[0]["value"] == 2  # D + A
    assert points[1]["value"] == 3  # + B
    assert peak == 4  # D + A + B + C
    assert peak_ts == start + 90  # C 加入时刻
    assert points[-1]["value"] == 1  # 仅 B 在线至窗口结束


def test_online_curve_tail_point_covers_partial_minute():
    """最后一分钟内的活动不应在曲线上隐身：曲线末尾需有终点采样点。"""
    start = _minute_aligned_hour_ago()
    end = start + 3600
    # 会话全部发生在最后一个不足一分钟的窗口内（end-30 到 end）
    sessions = [
        {"p": "A", "j": end - 30, "l": None},
        {"p": "B", "j": end - 20, "l": None},
    ]
    points, peak, _ = ps_mod.PlayerService._online_curve(sessions, start, end)
    assert peak == 2
    # 分钟桶均为 0，但最后一个采样点应落在窗口终点且反映实时并发
    assert all(p["value"] == 0 for p in points[:-1])
    assert points[-1]["t"] == int(end)
    assert points[-1]["value"] == 2


def test_exclude_bots_filters_no_ip_sessions(service):
    svc, srv = service
    start = _minute_aligned_hour_ago()
    end = start + 3600
    sessions = [
        {"p": "Real1", "j": start, "l": None, "ip": "1.1.1.1"},
        {"p": "Real2", "j": start + 60, "l": None, "ip": "1.1.1.2"},
        {"p": "bot1", "j": start + 30, "l": None},  # 无 IP → 假人
    ]
    svc._save_stats({"players": {}, "sessions": sessions})

    hist_all = svc.get_stats_online_history("1h")
    hist_real = svc.get_stats_online_history("1h", exclude_bots=True)
    # 排除后曲线值整体低 1（bot 不在内）
    assert any(p["value"] >= 3 for p in hist_all["points"])
    assert all(p["value"] <= 2 for p in hist_real["points"])

    ov_all = svc.get_stats_overview("1h")
    ov_real = svc.get_stats_overview("1h", exclude_bots=True)
    assert ov_all["total_sessions"] == 3
    assert ov_real["total_sessions"] == 2
    assert ov_all["active_players"] == 3
    assert ov_real["active_players"] == 2


def test_daily_aggregation(service):
    svc, srv = service
    start = _minute_aligned_hour_ago()
    svc._save_stats(
        {
            "players": {},
            "sessions": [
                {"p": "A", "j": start, "l": start + 120},
                {"p": "B", "j": start + 60, "l": None},
                {"p": "A", "j": start + 300, "l": start + 600},
            ],
        }
    )
    daily = svc.get_stats_daily("1d")
    assert daily["points"], daily
    today = daily["points"][-1]
    assert today["players"] == 2  # A + B 唯一玩家
    assert today["sessions"] == 3
    assert today["playtime"] > 0
    # 今天的 playtime 应覆盖开环会话 B 的在线时长（含当前）
    assert today["playtime"] >= 120 + 540


def test_reconcile_closes_stale_open_sessions(service):
    svc, srv = service
    svc._save_stats(
        {
            "players": {},
            "sessions": [
                {"p": "Gone", "j": time.time() - 300, "l": None},  # 已不在线
                {"p": "Here", "j": time.time() - 60, "l": None},  # 仍在在线名单
            ],
        }
    )
    srv._online = ["Here"]
    ov = svc.get_stats_overview("1h")
    sessions = svc._load_stats()["sessions"]
    by_name = {s["p"]: s for s in sessions}
    assert by_name["Gone"]["l"] is not None  # 兜底关闭
    assert by_name["Here"]["l"] is None  # 保持开环
    assert ov["current_online"] == 1


def test_prune_expired_sessions(service):
    svc, srv = service
    old = time.time() - 100 * 86400  # 超过 90 天保留期
    svc._save_stats(
        {
            "players": {},
            "sessions": [
                {"p": "Old", "j": old, "l": old + 60},
                {"p": "New", "j": time.time() - 10, "l": None},
            ],
        }
    )
    sessions = svc._load_stats()["sessions"]
    assert all(s["p"] == "New" for s in sessions)


def test_legacy_file_without_sessions_key(service):
    svc, srv = service
    ps_mod.PLAYER_STATS_PATH.write_text(
        '{"players": {"X": {"total_playtime": 5}}}', encoding="utf-8"
    )
    svc.on_player_joined(srv, "X")
    stats = svc._load_stats()
    assert stats["players"]["X"]["total_playtime"] == 5  # 旧聚合保留
    assert len(stats["sessions"]) == 1  # 新会话日志正常记录


def test_stats_players_ranking(service):
    svc, srv = service
    start = _minute_aligned_hour_ago()
    svc._save_stats(
        {
            "players": {
                "Alice": {"total_playtime": 7200, "ips": ["1.1.1.1"]},
                "Bob": {"total_playtime": 3600, "ips": ["1.1.1.2"]},
                "bot1": {"total_playtime": 0},
            },
            "sessions": [
                {"p": "Alice", "j": start, "l": start + 600, "ip": "1.1.1.1"},
                {"p": "Bob", "j": start + 60, "l": start + 120, "ip": "1.1.1.2"},
                {"p": "bot1", "j": start + 30, "l": None},
            ],
        }
    )
    srv._online = ["Alice"]
    rows = svc.get_stats_players()
    assert rows["total"] == 3
    # 累计时长 = 聚合（含历史），Alice 7200 > Bob 3600
    assert rows["players"][0]["name"] == "Alice"
    assert rows["players"][0]["total_playtime"] == 7200
    assert rows["players"][0]["sessions"] == 1
    assert rows["players"][0]["avg_session"] == 600
    assert rows["players"][0]["online"] is True

    rows_real = svc.get_stats_players(exclude_bots=True)
    assert rows_real["total"] == 2
    assert all(r["name"] != "bot1" for r in rows_real["players"])