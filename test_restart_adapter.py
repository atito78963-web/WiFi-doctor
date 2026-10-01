# -*- coding: utf-8 -*-
"""Command-flow tests for the optional Wi-Fi interface restart action."""

from unittest.mock import patch

from fixer import FixerEngine


def _item(name="Wi-Fi"):
    return {
        "id": "restart_wifi_adapter",
        "title": "Wi-Fi 网卡状态重启",
        "raw_val": {"adapter_name": name},
    }


def test_restart_success_without_touching_real_network():
    calls = []

    def fake_run_native(executable, args, timeout=15):
        calls.append((executable, args))
        if args[:3] == ["interface", "set", "interface"]:
            return 0, "", ""
        return 0, "Admin State    State          Type             Interface Name\nEnabled        Disconnected   Dedicated        Wi-Fi", ""

    with patch("fixer.run_native", side_effect=fake_run_native), patch("fixer.time.sleep"):
        ok, detail = FixerEngine({"name": "Wi-Fi"})._fix_restart_wifi_adapter(_item())

    assert ok, detail
    assert "已重新启用" in detail
    assert calls[0] == ("netsh", ["interface", "set", "interface", "name=Wi-Fi", "admin=disabled"])
    assert calls[1] == ("netsh", ["interface", "set", "interface", "name=Wi-Fi", "admin=enabled"])
    assert calls[2][1] == ["interface", "show", "interface"]


def test_restart_stops_when_disable_fails():
    with patch("fixer.run_native", return_value=(1, "", "拒绝访问")) as run_native:
        ok, detail = FixerEngine({"name": "Wi-Fi"})._fix_restart_wifi_adapter(_item())

    assert not ok
    assert "禁用" in detail
    run_native.assert_called_once()


if __name__ == "__main__":
    test_restart_success_without_touching_real_network()
    test_restart_stops_when_disable_fails()
    print("Restart adapter mock tests passed!")
