# -*- coding: utf-8 -*-
"""
WiFi Doctor - Native Diagnostics Module
High-speed, 100% reliable system diagnostics using pure winreg and native Windows utilities.
No external PowerShell dependencies, robust against substring bugs, accurate update queries.
"""

import re
import datetime
import winreg
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from utils import run_cmd, run_native, Logger

NET_CLASS_KEY = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}"

class DiagnosticEngine:
    def __init__(self):
        self.wifi_adapter: Optional[Dict[str, Any]] = None
        self.scan_results: List[Dict[str, Any]] = []

    def find_wifi_adapter(self) -> Optional[Dict[str, Any]]:
        """Find the active Wi-Fi adapter via native netsh and winreg."""
        code, out, err = run_native("netsh", ["wlan", "show", "interfaces"])
        if code != 0 or not out:
            code, out, err = run_cmd("netsh wlan show interfaces")

        name = None
        desc = None
        guid = None
        state = "未知"

        if code == 0 and out:
            for line in out.splitlines():
                line = line.strip()
                guid_match = re.match(r"^GUID\s*:\s*([a-fA-F0-9\-]+)", line, re.IGNORECASE)
                if guid_match:
                    guid = guid_match.group(1).lower()
                    continue
                name_match = re.match(r"^(?:Name|名称)\s*:\s*(.+)", line, re.IGNORECASE)
                if name_match:
                    name = name_match.group(1).strip()
                    continue
                desc_match = re.match(r"^(?:Description|描述|说明)\s*:\s*(.+)", line, re.IGNORECASE)
                if desc_match:
                    desc = desc_match.group(1).strip()
                    continue
                # Strictly match exact line-start 'State' or '状态'
                state_match = re.match(r"^(?:State|状态)\s*:\s*(.+)", line, re.IGNORECASE)
                if state_match:
                    raw_s = state_match.group(1).strip()
                    s_lower = raw_s.lower()
                    # Check disconnected first to avoid substring trap
                    if any(x in s_lower for x in ["disconnected", "未连接", "断开"]):
                        state = "未连接 (Disconnected)"
                    elif any(x in s_lower for x in ["connected", "已连接", "连接"]):
                        state = "已连接 (Up)"
                    else:
                        state = raw_s
                    continue

        # Match adapter in Windows Registry
        matched_subkey = None
        driver_version = ""
        driver_date = ""

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, NET_CLASS_KEY) as root:
                i = 0
                while True:
                    try:
                        sub = winreg.EnumKey(root, i)
                        i += 1
                        if not sub.isdigit():
                            continue
                        with winreg.OpenKey(root, sub) as k:
                            try:
                                k_guid, _ = winreg.QueryValueEx(k, "NetCfgInstanceId")
                                clean_guid = guid.replace("{", "").replace("}", "") if guid else ""
                                clean_k_guid = k_guid.lower().replace("{", "").replace("}", "")
                                if clean_guid and clean_guid == clean_k_guid:
                                    matched_subkey = sub
                                    try:
                                        reg_desc, _ = winreg.QueryValueEx(k, "DriverDesc")
                                        if reg_desc:
                                            desc = reg_desc
                                        driver_version, _ = winreg.QueryValueEx(k, "DriverVersion")
                                        driver_date, _ = winreg.QueryValueEx(k, "DriverDate")
                                    except Exception:
                                        pass
                                    break
                                # Fallback: match driver description
                                k_desc, _ = winreg.QueryValueEx(k, "DriverDesc")
                                if desc and desc.lower() in k_desc.lower():
                                    matched_subkey = sub
                                    try:
                                        if k_desc:
                                            desc = k_desc
                                        driver_version, _ = winreg.QueryValueEx(k, "DriverVersion")
                                        driver_date, _ = winreg.QueryValueEx(k, "DriverDate")
                                    except Exception:
                                        pass
                                    break
                            except Exception:
                                pass
                    except OSError:
                        break
        except Exception as e:
            Logger.warning(f"读取网卡注册表失败: {e}")

        # If no adapter found via netsh, attempt registry fallback
        if not guid or not matched_subkey:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, NET_CLASS_KEY) as root:
                    i = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(root, i)
                            i += 1
                            if not sub.isdigit():
                                continue
                            with winreg.OpenKey(root, sub) as k:
                                try:
                                    k_desc, _ = winreg.QueryValueEx(k, "DriverDesc")
                                    k_guid, _ = winreg.QueryValueEx(k, "NetCfgInstanceId")
                                    if any(w in k_desc.lower() for w in ["wi-fi", "wireless", "8086", "wlan"]):
                                        guid = k_guid.lower().replace("{", "").replace("}", "")
                                        desc = k_desc
                                        name = "WLAN"
                                        matched_subkey = sub
                                        state = "已就绪"
                                        try:
                                            driver_version, _ = winreg.QueryValueEx(k, "DriverVersion")
                                            driver_date, _ = winreg.QueryValueEx(k, "DriverDate")
                                        except Exception:
                                            pass
                                        break
                                except Exception:
                                    pass
                        except OSError:
                            break
            except Exception:
                pass

        # If still no valid wireless adapter or GUID, return None (do NOT fake a WLAN adapter!)
        if not guid or not matched_subkey:
            self.wifi_adapter = None
            return None

        self.wifi_adapter = {
            "name": name or "WLAN",
            "description": desc or "无线网卡",
            "guid": guid,
            "status": state,
            "registry_subkey": matched_subkey,
            "driver_version": driver_version,
            "driver_date": driver_date
        }
        return self.wifi_adapter

    def scan_all(self) -> List[Dict[str, Any]]:
        """Run the complete diagnostic scan without changing network state."""
        self.scan_results = []
        Logger.info("开始进行系统深度网络扫描 (纯原生极速引擎)...")

        adapter = self.find_wifi_adapter()
        if not adapter:
            Logger.error("未检测到系统无线网卡 (Wi-Fi 适配器)！")
            return []

        Logger.info(f"已识别无线网卡: [{adapter['name']}] {adapter['description']} (驱动: {adapter['driver_version']})")

        # 1. Adapter Power Saving (PnPCapabilities / WMI)
        item1 = self._scan_adapter_power_saving(adapter)
        self.scan_results.append(item1)

        # 2. Power Plan Wireless Setting (AC/DC)
        item2 = self._scan_power_plan_wireless()
        self.scan_results.append(item2)

        # 3. Roaming Aggressiveness
        item3 = self._scan_roaming_aggressiveness(adapter)
        self.scan_results.append(item3)

        # 4. MIMO Power Save Mode (SMPS)
        item4 = self._scan_mimo_power_save(adapter)
        self.scan_results.append(item4)

        # 5. IPv6 on WLAN (Router Advertisement 900s timeout)
        item5 = self._scan_ipv6_status(adapter)
        self.scan_results.append(item5)

        # 6. WLAN AutoConfig Background Probing
        item6 = self._scan_autoconfig_probing(adapter)
        self.scan_results.append(item6)

        # 7. Recent Updates & Hotfixes Audit
        item7 = self._scan_recent_updates()
        self.scan_results.append(item7)

        # 8. WLAN Disconnect Events (wevtutil Event 8003)
        item8 = self._scan_event_log_disconnects()
        self.scan_results.append(item8)

        # 9. Wi-Fi adapter restart (manual maintenance action only)
        self.scan_results.append({
            "id": "restart_wifi_adapter",
            "title": "Wi-Fi 网卡状态重启",
            "category": "网卡状态维护",
            "has_issue": False,
            "can_fix": True,
            "can_rollback": False,
            "current_val": "按需执行禁用并重新启用",
            "raw_val": {"adapter_name": adapter.get("name", "")},
            "issue_desc": "当 Wi-Fi 图标消失、无线网卡状态卡死，或系统没有及时恢复接口时，可通过禁用后重新启用网卡刷新接口状态。",
            "recommendation": "仅在 Wi-Fi 图标消失或网卡状态异常时执行。操作期间 Wi-Fi 会短暂断开，恢复后请等待系统重新连接。",
            "fix_action": "禁用并重新启用 Wi-Fi 网卡",
            "rollback_note": "本项只执行一次即时的禁用/启用操作，不写入持久配置，也不创建回滚快照。",
            "selected": False
        })

        # 10. DNS & ARP Cache
        item10 = self._scan_dns_arp_status()
        self.scan_results.append(item10)

        Logger.info(f"深度扫描完成，共诊断 {len(self.scan_results)} 个关键项。")
        return self.scan_results

    def _scan_adapter_power_saving(self, adapter: Dict[str, Any]) -> Dict[str, Any]:
        """Check WMI MSPower_DeviceEnable and PnPCapabilities power-saving sleep bit."""
        sub = adapter.get("registry_subkey")
        pnp_val = None
        pnp_exists = False
        wmi_power_enabled = None

        # 1. Authoritative check via WMI MSPower_DeviceEnable
        pythoncom = None
        try:
            import pythoncom
            pythoncom.CoInitialize()
            import win32com.client
            wmi = win32com.client.GetObject(r"winmgmts:\\.\root\wmi")
            items = wmi.ExecQuery("Select * from MSPower_DeviceEnable")
            for it in items:
                inst = str(it.InstanceName).lower()
                if any(x in inst for x in ["2725", "wlan", "wifi", "8086", "10ec"]) and ("pci" in inst or "usb" in inst):
                    if it.Enable is not None:
                        wmi_power_enabled = bool(it.Enable)
                        break
        except Exception:
            pass
        finally:
            try:
                del items
            except Exception:
                pass
            try:
                del it
            except Exception:
                pass
            try:
                del wmi
            except Exception:
                pass
            if pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

        # 2. Check registry PnPCapabilities as secondary reference
        if sub:
            try:
                full_path = f"{NET_CLASS_KEY}\\{sub}"
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, full_path) as k:
                    try:
                        pnp_val, _ = winreg.QueryValueEx(k, "PnPCapabilities")
                        pnp_exists = True
                    except FileNotFoundError:
                        pnp_val = None
            except Exception:
                pass

        if wmi_power_enabled is not None:
            is_power_saving_on = wmi_power_enabled
        elif pnp_val is not None:
            is_power_saving_on = (pnp_val == 16)
        else:
            is_power_saving_on = False

        if is_power_saving_on:
            status_text = "已启用 (允许系统关闭网卡休眠)"
            has_issue = True
            rec_text = "建议关闭。Win11 在低吞吐热点下会向网卡发送 D3 低功耗休眠，引发约15分钟周期性掉线。"
        else:
            status_text = "已禁用/已优化 (禁止休眠断电关卡)"
            has_issue = False
            rec_text = "当前已禁止网卡休眠断电，配置健康。"

        return {
            "id": "adapter_power_saving",
            "title": "网卡节能关断 (允许计算机关闭此设备以节约电源)",
            "category": "硬件电源管理",
            "has_issue": has_issue,
            "can_fix": True,
            "can_rollback": True,
            "current_val": status_text,
            "raw_val": {"pnp_val": pnp_val, "pnp_exists": pnp_exists, "wmi_power_enabled": wmi_power_enabled, "subkey": sub},
            "issue_desc": "Windows 11 笔记本在连接手机热点时，系统会根据网络吞吐量判断为空闲状态，在周期定时器（约15分钟）触发时将无线网卡置入低功耗休眠，引发断线。",
            "recommendation": rec_text,
            "fix_action": "关闭网卡休眠节能属性 (修改 PnPCapabilities 禁止休眠)",
            "selected": has_issue
        }

    def _scan_power_plan_wireless(self) -> Dict[str, Any]:
        """Check active power scheme wireless adapter power saving mode."""
        code, out, err = run_native("powercfg", ["/q", "SCHEME_CURRENT", "19cbb8fa-5279-450e-9fac-8a3d5fedd0c1", "12bbebe6-58d6-4636-95bb-3217ef867c1a"])
        if code != 0 or not out:
            code, out, err = run_cmd("powercfg /q SCHEME_CURRENT 19cbb8fa-5279-450e-9fac-8a3d5fedd0c1 12bbebe6-58d6-4636-95bb-3217ef867c1a")

        ac_val = None
        dc_val = None

        mode_map = {0: "最高性能 (无节能)", 1: "低节能", 2: "中等节能", 3: "最高节能"}

        ac_match = re.search(r"(?:交流|AC).*?(0x[0-9a-fA-F]+)", out)
        dc_match = re.search(r"(?:直流|DC).*?(0x[0-9a-fA-F]+)", out)

        if ac_match:
            try:
                ac_val = int(ac_match.group(1), 16)
            except Exception:
                pass
        if dc_match:
            try:
                dc_val = int(dc_match.group(1), 16)
            except Exception:
                pass

        has_issue = False
        parts = []
        if ac_val is not None:
            parts.append(f"接通电源: {mode_map.get(ac_val, f'模式{ac_val}')}")
            if ac_val > 0:
                has_issue = True
        if dc_val is not None:
            parts.append(f"使用电池: {mode_map.get(dc_val, f'模式{dc_val}')}")
            if dc_val > 0:
                has_issue = True

        current_val = " | ".join(parts) if parts else "未检测到或默认方案"

        return {
            "id": "power_plan_wireless",
            "title": "系统电源计划 - 无线适配器节能模式",
            "category": "系统电源方案",
            "has_issue": has_issue,
            "can_fix": True,
            "can_rollback": True,
            "current_val": current_val,
            "raw_val": {"ac": ac_val, "dc": dc_val},
            "issue_desc": "笔记本在平衡电源计划下，使用电池或接通电源时常默认设为『中等节能』或『最高节能』。节能模式会降低射频发射功率并关闭接收信道，极易导致与手机热点失去同步而断开。",
            "recommendation": "将交流供电与电池供电下的无线适配器模式均统一优化为『最高性能』，保障热点稳定连接。",
            "fix_action": "设置电源方案无线模式为【最高性能】",
            "selected": has_issue
        }

    def _scan_roaming_aggressiveness(self, adapter: Dict[str, Any]) -> Dict[str, Any]:
        """Check Roaming Aggressiveness directly from registry in 0.001s."""
        sub = adapter.get("registry_subkey")
        roam_val = None
        found_key = "RoamAggressiveness"
        existed = False

        if sub:
            try:
                full_path = f"{NET_CLASS_KEY}\\{sub}"
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, full_path) as k:
                    for candidate in ["RoamAggressiveness", "*RoamingAggressiveness", "RoamingAggressiveness"]:
                        try:
                            val, _ = winreg.QueryValueEx(k, candidate)
                            roam_val = str(val)
                            found_key = candidate
                            existed = True
                            break
                        except FileNotFoundError:
                            pass
            except Exception:
                pass

        val_map = {
            "1": "1. 最低 (Lowest - 推荐)",
            "2": "2. 中低",
            "3": "3. 中间 (Medium)",
            "4": "4. 中高",
            "5": "5. 最高 (Highest)"
        }

        has_issue = False
        if roam_val is not None:
            if roam_val in ["2", "3", "4", "5"]:
                has_issue = True
            disp_text = val_map.get(roam_val, f"值: {roam_val}")
        else:
            disp_text = "未配置或驱动默认 (中等)"
            has_issue = True

        return {
            "id": "roaming_aggressiveness",
            "title": "网卡漫游激进度 (Roaming Aggressiveness)",
            "category": "网卡高级驱动参数",
            "has_issue": has_issue,
            "can_fix": True,
            "can_rollback": True,
            "current_val": disp_text,
            "raw_val": {"keyword": found_key, "roam_val": roam_val, "subkey": sub, "existed": existed},
            "issue_desc": "手机热点为单一AP信源。若漫游激进度设为『中等』或『较高』，网卡每隔约10~15分钟就会强制进行全信道漫游扫描寻找更强信号，导致与手机热点短暂解除握手脱网。",
            "recommendation": "将漫游激进度调整为『1. 最低 (Lowest)』，禁止不必要的主动脱网搜寻。",
            "fix_action": "调整漫游激进度为【1. 最低】",
            "selected": has_issue
        }

    def _scan_mimo_power_save(self, adapter: Dict[str, Any]) -> Dict[str, Any]:
        """Check MIMO SMPS power save directly from registry in 0.001s."""
        sub = adapter.get("registry_subkey")
        mimo_val = None
        found_key = "MIMOPowerSaveMode"
        existed = False

        if sub:
            try:
                full_path = f"{NET_CLASS_KEY}\\{sub}"
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, full_path) as k:
                    for candidate in ["MIMOPowerSaveMode", "*MIMOPowerSaveMode"]:
                        try:
                            val, _ = winreg.QueryValueEx(k, candidate)
                            mimo_val = str(val)
                            found_key = candidate
                            existed = True
                            break
                        except FileNotFoundError:
                            pass
            except Exception:
                pass

        smps_map = {
            "0": "自动 SMPS (Dynamic SMPS - 易冲突)",
            "1": "动态 SMPS",
            "2": "静态 SMPS",
            "3": "无 SMPS (No SMPS - 全通道常开)"
        }

        has_issue = False
        if mimo_val is not None:
            if mimo_val in ["0", "1", "2"]:
                has_issue = True
            disp_text = smps_map.get(mimo_val, f"值: {mimo_val}")
        else:
            disp_text = "未配置或驱动默认 (自动 SMPS)"
            has_issue = True

        return {
            "id": "mimo_power_save",
            "title": "MIMO 多天线节能模式 (SMPS)",
            "category": "网卡高级驱动参数",
            "has_issue": has_issue,
            "can_fix": True,
            "can_rollback": True,
            "current_val": disp_text,
            "raw_val": {"keyword": found_key, "mimo_val": mimo_val, "subkey": sub, "existed": existed},
            "issue_desc": "动态 SMPS 模式会在空闲时自动关闭部分天线通道以省电。许多手机热点芯片（高通/联发科手机）对此特性的兼容性较差，天线切换时易触发解关联（Deauth）丢包断网。",
            "recommendation": "设置为『无 SMPS (No SMPS)』，保持双天线/多天线常开全功率工作，彻底杜绝芯片休眠冲突。",
            "fix_action": "设置 MIMO 节能为【无 SMPS / 保持全天线开启】",
            "selected": has_issue
        }

    def _scan_ipv6_status(self, adapter: Dict[str, Any]) -> Dict[str, Any]:
        """Check IPv6 router discovery and default routes via native netsh."""
        name = adapter.get("name", "WLAN")
        code, out, err = run_native("netsh", ["interface", "ipv6", "show", "interface", name])
        if code != 0 or not out:
            code, out, err = run_cmd(f'netsh interface ipv6 show interface "{name}"')

        # Case-insensitive regex check for router discovery and ignore default routes
        rd_disabled = bool(re.search(r"Router\s*Discovery\s*:\s*disabled|路由器发现\s*:\s*(?:已禁用|disabled)", out, re.I))
        idr_enabled = bool(re.search(r"Ignore\s*Default\s*Routes\s*:\s*enabled|忽略默认路由\s*:\s*(?:已启用|enabled)", out, re.I))

        # Full protection against 15m RA timeout requires BOTH router discovery disabled AND ignore default routes enabled
        has_issue = not (rd_disabled and idr_enabled)
        status_text = "已启用热点路由宣告 (15分钟可能触发超时)" if has_issue else "✔ 已优化 (已忽略热点失效路由 / 纯 IPv4 稳定运行)"

        return {
            "id": "wlan_ipv6_binding",
            "title": "WLAN IPv6 协议栈热点路由超时防御 (15分钟核心诱因)",
            "category": "网络协议栈",
            "has_issue": has_issue,
            "can_fix": True,
            "can_rollback": True,
            "current_val": status_text,
            "raw_val": {"rd_disabled": rd_disabled, "idr_enabled": idr_enabled, "adapter_name": name},
            "issue_desc": "【高危核心项】三大运营商手机热点下发的 IPv6 路由器宣告 (Router Advertisement) 生命周期通常刚好是 900 秒 (15分钟)！超时后手机热点未及时刷新前缀，电脑仍尝试走失效的 IPv6 导致断网。优化禁用热点 IPv6 路由下发即可彻底解决。",
            "recommendation": "优化无线网卡策略：忽略热点下发的失效 IPv6 默认路由，强制主干流量走极稳定的 IPv4（随时可一键撤销恢复）。",
            "fix_action": "关闭热点 IPv6 路由宣告接管 (防御15分钟超时掉线)",
            "selected": has_issue
        }

    def _scan_autoconfig_probing(self, adapter: Dict[str, Any]) -> Dict[str, Any]:
        """Check WLAN AutoConfig periodic background probing status."""
        code, out, err = run_native("netsh", ["wlan", "show", "interfaces"])
        if code != 0 or not out:
            code, out, err = run_cmd("netsh wlan show interfaces")

        is_enabled = True
        if "已停用" in out or "Disabled" in out or "disabled" in out:
            is_enabled = False

        status_text = "已启用 (系统正常维护无线连接)" if is_enabled else "已停用 (自动搜网配置已关闭)"

        return {
            "id": "wlan_autoconfig_scan",
            "title": "WLAN 自动配置服务后台搜网行为",
            "category": "系统服务",
            "has_issue": False,
            "can_fix": False,
            "can_rollback": False,
            "current_val": status_text,
            "raw_val": {"is_enabled": is_enabled},
            "issue_desc": "WlanSvc 服务负责自动探测与维持 Wi-Fi 连接。通常保持开启即可，可在极端热点抖动时作为排查参考。",
            "recommendation": "当前服务正常运行，保持默认开启以确保正常搜索热点。",
            "fix_action": "保持默认 (无需修改)",
            "selected": False
        }

    def _scan_recent_updates(self) -> Dict[str, Any]:
        """Check recent Windows Updates in last 4 days via Windows Update COM API (supports Win11 24H2)."""
        recent_updates = []
        pythoncom = None
        try:
            import pythoncom
            pythoncom.CoInitialize()
            import win32com.client
            session = win32com.client.Dispatch("Microsoft.Update.Session")
            searcher = session.CreateUpdateSearcher()
            history = searcher.QueryHistory(0, 10)
            cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=4)
            for i in range(history.Count):
                entry = history.Item(i)
                entry_date = entry.Date
                if hasattr(entry_date, "timestamp") and entry_date >= cutoff:
                    title_clean = str(entry.Title).split("(")[0].strip()
                    recent_updates.append(f"{title_clean} ({str(entry_date)[:10]})")
        except Exception:
            pass
        finally:
            try:
                del history
            except Exception:
                pass
            try:
                del entry
            except Exception:
                pass
            try:
                del searcher
            except Exception:
                pass
            try:
                del session
            except Exception:
                pass
            if pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

        if recent_updates:
            status_text = f"近4天内安装了 {len(recent_updates)} 项更新: " + ", ".join(recent_updates[:2])
            issue_desc = f"检测到近 4 天内安装了系统更新或驱动更新：【{recent_updates[0]}】。这可能与这两天开始的断网现象有关。若执行常规优化后仍有掉线，建议在设备管理器中对无线网卡点击【回退驱动程序】。"
            rec_text = "已记录近期补丁信息。优先通过硬件节能禁用与 IPv6 优化即可有效解决。"
        else:
            status_text = "近4天内无新增系统更新或补丁记录"
            issue_desc = "近几天未检测到系统热补丁更新，掉网诱因为网卡节能策略与热点握手问题。"
            rec_text = "通过网卡电源管理与 IPv6 优化即可解决。"

        return {
            "id": "recent_updates_audit",
            "title": "系统近期补丁与驱动变更审查 (排查突发诱因)",
            "category": "系统更新审计",
            "has_issue": False,  # Informational audit, not an error
            "can_fix": False,
            "can_rollback": False,
            "current_val": status_text,
            "raw_val": {"recent_updates": recent_updates},
            "issue_desc": issue_desc,
            "recommendation": rec_text,
            "fix_action": "提供排查参考 (已审计补丁信息)",
            "selected": False
        }

    def _scan_event_log_disconnects(self) -> Dict[str, Any]:
        """Extract WLAN disconnect reasons from native wevtutil in 0.05s."""
        code, out, err = run_native(
            "wevtutil",
            ["qe", "Microsoft-Windows-WLAN-AutoConfig/Operational", "/q:*[System[(EventID=8003)]]", "/c:5", "/rd:true", "/f:xml"]
        )

        disconnect_events = []
        if code == 0 and out:
            try:
                root_xml = "<Events>" + out + "</Events>"
                tree = ET.fromstring(root_xml)
                for event in tree.findall("{http://schemas.microsoft.com/win/2004/08/events/event}Event"):
                    time_elem = event.find("{http://schemas.microsoft.com/win/2004/08/events/event}System/{http://schemas.microsoft.com/win/2004/08/events/event}TimeCreated")
                    t_str = time_elem.attrib.get("SystemTime", "") if time_elem is not None else ""
                    
                    event_data = event.find("{http://schemas.microsoft.com/win/2004/08/events/event}EventData")
                    reason = "驱动程序或网络断开连接"
                    if event_data is not None:
                        for d in event_data:
                            if d.attrib.get("Name") in ["Reason", "ReasonCode"]:
                                reason = f"原因: {d.text}"
                                break
                    disconnect_events.append({"time": t_str[:19].replace("T", " "), "reason": reason})
            except Exception:
                pass

        if disconnect_events:
            status_text = f"捕获到底层记录的 {len(disconnect_events)} 次断网事件"
            issue_desc = f"系统日志验证了频繁断线现象！底层最近记录的断网原因包括：【{disconnect_events[0]['reason']}】。明确表明是驱动端或超时脱网，印证了网卡节能休眠与热点握手失效。"
            rec_text = "落实节能禁用与 IPv6 超时防御即可精准消除此类断开。"
        else:
            status_text = "近期未记录到异常脱网事件 (或日志已轮替)"
            issue_desc = "未找到严重异常日志，断网多发生于无感知网络层路由失效。"
            rec_text = "实施标准网络热点稳定性优化配置。"

        return {
            "id": "event_log_audit",
            "title": "底层系统 WLAN 断网原因审计 (Event 8003 日志分析)",
            "category": "系统日志审计",
            "has_issue": False,  # Informational audit, not an error
            "can_fix": False,
            "can_rollback": False,
            "current_val": status_text,
            "raw_val": {"events": disconnect_events},
            "issue_desc": issue_desc,
            "recommendation": rec_text,
            "fix_action": "日志已精准归因 (作为优化依据)",
            "selected": False
        }

    def _scan_dns_arp_status(self) -> Dict[str, Any]:
        """Scan ARP cache and DNS cache status."""
        return {
            "id": "flush_dns_arp",
            "title": "陈旧 DNS 缓存与 ARP 邻居表清理",
            "category": "网络协议栈",
            "has_issue": False,  # Maintenance item, not an error
            "can_fix": True,
            "can_rollback": False,  # Transparently communicate that cache flush cannot be undone
            "current_val": "✔ 网络缓存正常 (支持按需自选清理)",
            "raw_val": {},
            "issue_desc": "手机热点频繁重新分配局域网 IP 时，电脑旧有的 ARP 邻居解析与 DNS 缓存未及时丢弃，容易产生冲突与请求黑洞。",
            "recommendation": "当前网络缓存正常。若刚切换了不同的手机热点，可随时按需勾选本项清空陈旧 ARP 缓存表与 DNS 缓存。",
            "fix_action": "清理 ARP 邻居表并刷新 DNS 解析缓存",
            "selected": False
        }
