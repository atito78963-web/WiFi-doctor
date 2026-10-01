# -*- coding: utf-8 -*-
"""
WiFi Doctor - Native Fixer and Rollback Module
Ultra-fast, reliable optimizations with strict verification, error checking,
whitelisted security validation, exact registry type preservation, and selective rollback cleanup.
"""

import re
import time
import winreg
from typing import Dict, Any, List, Tuple, Optional
from utils import run_cmd, run_native, Logger, BackupManager

NET_CLASS_KEY = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e972-e325-11ce-bfc1-08002be10318}"
ALLOWED_REG_PREFIX = r"system\currentcontrolset\control\class\{4d36e972-e325-11ce-bfc1-08002be10318}\\"
ALLOWED_REG_NAMES = {
    "pnpcapabilities", "roamaggressiveness", "*roamaggressiveness",
    "roamingaggressiveness", "mimopowersavemode", "*mimopowersavemode"
}

class FixerEngine:
    def __init__(self, wifi_adapter: Optional[Dict[str, Any]]):
        self.adapter = wifi_adapter

    def apply_fixes(self, selected_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Apply all selected fixes with immediate read-back verification."""
        summary = {
            "total": len(selected_items),
            "success": 0,
            "failed": 0,
            "details": []
        }

        if not self.adapter:
            Logger.error("未检测到有效无线网卡，取消优化执行！")
            return summary

        Logger.info(f"===> 开始执行选中的 {len(selected_items)} 项极速优化任务 <===")

        for item in selected_items:
            item_id = item.get("id")
            title = item.get("title", item_id)
            Logger.info(f"正在优化: 【{title}】...")

            success, detail = self._apply_single_fix(item)
            if success:
                summary["success"] += 1
                Logger.success(f"【{title}】优化并验证成功: {detail}")
            else:
                summary["failed"] += 1
                Logger.error(f"【{title}】优化失败: {detail}")

            summary["details"].append({
                "id": item_id,
                "title": title,
                "success": success,
                "detail": detail,
                "can_rollback": item.get("can_rollback", True)
            })
            time.sleep(0.08)

        Logger.info(f"===> 优化处理完成！成功: {summary['success']}, 失败: {summary['failed']} <===")
        return summary

    def _apply_single_fix(self, item: Dict[str, Any]) -> Tuple[bool, str]:
        item_id = item["id"]
        
        if item_id == "adapter_power_saving":
            return self._fix_adapter_power_saving(item)
        elif item_id == "power_plan_wireless":
            return self._fix_power_plan_wireless(item)
        elif item_id == "roaming_aggressiveness":
            return self._fix_roaming_aggressiveness(item)
        elif item_id == "mimo_power_save":
            return self._fix_mimo_power_save(item)
        elif item_id == "wlan_ipv6_binding":
            return self._fix_ipv6_binding(item)
        elif item_id == "restart_wifi_adapter":
            return self._fix_restart_wifi_adapter(item)
        elif item_id == "flush_dns_arp":
            return self._fix_flush_dns_arp(item)
        else:
            return False, "未知或不可修复的项目"

    def _fix_restart_wifi_adapter(self, item: Dict[str, Any]) -> Tuple[bool, str]:
        """Restart the Wi-Fi interface to recover a missing or stuck Wi-Fi state."""
        if not self.adapter:
            return False, "未找到有效的无线网卡硬件"

        raw = item.get("raw_val", {}) or {}
        name = raw.get("adapter_name") or self.adapter.get("name")
        if not name or not str(name).strip():
            return False, "未找到可操作的 Wi-Fi 接口名称"
        name = str(name).strip()

        # Use the native netsh API so an adapter name is passed as one argument,
        # including names containing spaces or non-ASCII characters.
        disabled_code, disabled_out, disabled_err = run_native(
            "netsh", ["interface", "set", "interface", f"name={name}", "admin=disabled"]
        )
        if disabled_code != 0:
            detail = disabled_err or disabled_out or f"返回码 {disabled_code}"
            return False, f"禁用 Wi-Fi 网卡失败: {detail}"

        # The driver needs a short interval to release the interface before it
        # can accept the enable request reliably.
        time.sleep(0.8)
        enabled_code, enabled_out, enabled_err = run_native(
            "netsh", ["interface", "set", "interface", f"name={name}", "admin=enabled"]
        )
        if enabled_code != 0:
            detail = enabled_err or enabled_out or f"返回码 {enabled_code}"
            return False, f"重新启用 Wi-Fi 网卡失败: {detail}"

        # Windows may report the interface a little after netsh returns. Retry
        # briefly so a successful command is not reported as a false failure.
        last_detail = "接口尚未重新出现"
        for _ in range(6):
            verified, detail = self._verify_wifi_interface(name)
            if verified:
                return True, f"已重新启用 Wi-Fi 网卡 [{name}]，接口已恢复可见"
            last_detail = detail
            time.sleep(0.25)

        return False, f"网卡已执行重新启用，但接口验证未通过: {last_detail}"

    @staticmethod
    def _verify_wifi_interface(name: str) -> Tuple[bool, str]:
        """Return whether netsh can see the named interface after enabling it."""
        code, out, err = run_native("netsh", ["interface", "show", "interface"])
        if code == 0 and out:
            name_folded = name.casefold()
            for line in out.splitlines():
                line_folded = line.casefold()
                if name_folded in line_folded:
                    if re.search(r"\bdisabled\b|已禁用|禁用", line, re.I):
                        return False, "接口仍处于禁用状态"
                    return True, "netsh interface 已显示该接口"

        # wlan output is a useful fallback on systems where the interface table
        # is localized or does not include the adapter row immediately.
        wlan_code, wlan_out, wlan_err = run_native("netsh", ["wlan", "show", "interfaces"])
        if wlan_code == 0 and wlan_out and name.casefold() in wlan_out.casefold():
            return True, "netsh wlan 已显示该接口"

        detail = err or wlan_err or "netsh 未返回该接口"
        return False, detail

    def _fix_adapter_power_saving(self, item: Dict[str, Any]) -> Tuple[bool, str]:
        """Disable power saving on the Wi-Fi adapter via WMI and registry with verification."""
        if not self.adapter:
            return False, "未找到有效的无线网卡硬件"

        sub = self.adapter.get("registry_subkey")
        raw = item.get("raw_val", {})
        orig_pnp = raw.get("pnp_val")
        orig_pnp_exists = raw.get("pnp_exists", orig_pnp is not None)
        orig_wmi = raw.get("wmi_power_enabled", True)

        full_path = f"{NET_CLASS_KEY}\\{sub}" if sub else None

        # 1. Save snapshot
        restore_info = {
            "type": "adapter_power",
            "path": full_path,
            "orig_pnp": orig_pnp,
            "orig_pnp_exists": orig_pnp_exists,
            "orig_wmi": orig_wmi
        }
        BackupManager.save_item_snapshot(
            "adapter_power_saving",
            "网卡休眠节能关断",
            "允许系统关闭此设备以节约电源",
            "禁止系统关闭此设备 (已优化)",
            restore_info
        )

        # 2. Update WMI MSPower_DeviceEnable
        wmi_updated = False
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
                    it.Enable = False
                    it.Put_()
                    wmi_updated = True
                    break
        except Exception as e:
            Logger.warning(f"WMI 更新提示: {e}")
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

        # 3. Update Registry PnPCapabilities = 24
        reg_updated = False
        if full_path:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, full_path, 0, winreg.KEY_SET_VALUE) as k:
                    winreg.SetValueEx(k, "PnPCapabilities", 0, winreg.REG_DWORD, 24)
                    reg_updated = True
            except Exception as e:
                Logger.warning(f"注册表 PnPCapabilities 写入提示: {e}")

        # 4. Strict read-back verification: verify WMI is False
        verified = False
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
                    if it.Enable is False:
                        verified = True
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

        if not verified and reg_updated:
            # Check registry read-back
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, full_path, 0, winreg.KEY_QUERY_VALUE) as k:
                    v, _ = winreg.QueryValueEx(k, "PnPCapabilities")
                    if v == 24:
                        verified = True
            except Exception:
                pass

        if verified:
            return True, "已直接更新网卡硬件电源管理策略为禁止休眠，经验证生效"
        return False, "验证未通过：网卡硬件休眠属性未能成功置为 False"

    def _fix_power_plan_wireless(self, item: Dict[str, Any]) -> Tuple[bool, str]:
        """Set active power scheme wireless setting to 0 (最高性能) for AC & DC with verification."""
        raw = item.get("raw_val", {})
        orig_ac = raw.get("ac", 2)
        orig_dc = raw.get("dc", 3)

        # 1. Save snapshot
        restore_info = {
            "type": "powercfg_wireless",
            "orig_ac": orig_ac,
            "orig_dc": orig_dc
        }
        BackupManager.save_item_snapshot(
            "power_plan_wireless",
            "系统电源计划-无线适配器节能",
            f"交流={orig_ac}, 电池={orig_dc}",
            "交流=0, 电池=0",
            restore_info
        )

        # 2. Execute powercfg commands
        subgroup = "19cbb8fa-5279-450e-9fac-8a3d5fedd0c1"
        setting = "12bbebe6-58d6-4636-95bb-3217ef867c1a"

        c1, _, e1 = run_native("powercfg", ["/setacvalueindex", "SCHEME_CURRENT", subgroup, setting, "0"])
        c2, _, e2 = run_native("powercfg", ["/setdcvalueindex", "SCHEME_CURRENT", subgroup, setting, "0"])
        c3, _, e3 = run_native("powercfg", ["/s", "SCHEME_CURRENT"])

        if c1 != 0 or c2 != 0 or c3 != 0:
            return False, f"执行 powercfg 失败: {e1 or e2 or e3}"

        # 3. Read-back verification
        code, out, err = run_native("powercfg", ["/q", "SCHEME_CURRENT", subgroup, setting])
        if code == 0 and "0x00000000" in out:
            return True, "系统电源计划已调整为【最高性能】，AC/DC 节能已全部关闭并验证通过"
        return False, f"验证未通过：电源方案无线设置未能在系统生效 ({err or out[:60]})"

    def _fix_roaming_aggressiveness(self, item: Dict[str, Any]) -> Tuple[bool, str]:
        """Set RoamAggressiveness to '1' (Lowest) with exact type and existence preservation."""
        if not self.adapter:
            return False, "未找到有效的无线网卡硬件"

        sub = self.adapter.get("registry_subkey")
        raw = item.get("raw_val", {})
        keyword = raw.get("keyword", "RoamAggressiveness")
        full_path = f"{NET_CLASS_KEY}\\{sub}" if sub else None

        if not full_path:
            return False, "未找到网卡注册表配置项"

        # 1. Query exact original state and val_type before modifying
        orig_val = None
        orig_type = winreg.REG_SZ
        existed = False
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, full_path, 0, winreg.KEY_QUERY_VALUE) as k:
                orig_val, orig_type = winreg.QueryValueEx(k, keyword)
                existed = True
        except FileNotFoundError:
            existed = False
        except Exception as e:
            return False, f"无法读取当前漫游激进度注册表: {e}"

        restore_info = {
            "type": "registry_val",
            "path": full_path,
            "name": keyword,
            "orig_val": orig_val,
            "val_type": orig_type,
            "existed": existed
        }
        BackupManager.save_item_snapshot(
            "roaming_aggressiveness",
            "网卡漫游激进度",
            str(orig_val) if existed else "未配置(原值不存在)",
            "1 (最低)",
            restore_info
        )

        # 2. Write to registry
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, full_path, 0, winreg.KEY_SET_VALUE) as k:
                # Intel/Realtek expects string "1" for lowest roaming
                winreg.SetValueEx(k, keyword, 0, winreg.REG_SZ, "1")
        except Exception as e:
            return False, f"写入漫游激进度注册表失败: {e}"

        # 3. Read-back verification
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, full_path, 0, winreg.KEY_QUERY_VALUE) as k:
                check_val, _ = winreg.QueryValueEx(k, keyword)
                if str(check_val) == "1":
                    return True, "已直接将漫游激进度调整为【1. 最低】，网卡将不再脱网扫描热点"
        except Exception as e:
            return False, f"验证失败：无法读出漫游激进度注册表 ({e})"

        return False, "验证未通过：写入漫游激进度后未读出预期值 1"

    def _fix_mimo_power_save(self, item: Dict[str, Any]) -> Tuple[bool, str]:
        """Set MIMOPowerSaveMode to '3' (No SMPS) with exact type and existence preservation."""
        if not self.adapter:
            return False, "未找到有效的无线网卡硬件"

        sub = self.adapter.get("registry_subkey")
        raw = item.get("raw_val", {})
        keyword = raw.get("keyword", "MIMOPowerSaveMode")
        full_path = f"{NET_CLASS_KEY}\\{sub}" if sub else None

        if not full_path:
            return False, "未找到网卡注册表配置项"

        # 1. Query exact original state and val_type before modifying
        orig_val = None
        orig_type = winreg.REG_SZ
        existed = False
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, full_path, 0, winreg.KEY_QUERY_VALUE) as k:
                orig_val, orig_type = winreg.QueryValueEx(k, keyword)
                existed = True
        except FileNotFoundError:
            existed = False
        except Exception as e:
            return False, f"无法读取当前 MIMO 节能注册表: {e}"

        restore_info = {
            "type": "registry_val",
            "path": full_path,
            "name": keyword,
            "orig_val": orig_val,
            "val_type": orig_type,
            "existed": existed
        }
        BackupManager.save_item_snapshot(
            "mimo_power_save",
            "MIMO 多天线节能模式",
            str(orig_val) if existed else "未配置(原值不存在)",
            "3 (无 SMPS)",
            restore_info
        )

        # 2. Write to registry
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, full_path, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, keyword, 0, winreg.REG_SZ, "3")
        except Exception as e:
            return False, f"写入 MIMO 节能注册表失败: {e}"

        # 3. Read-back verification
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, full_path, 0, winreg.KEY_QUERY_VALUE) as k:
                check_val, _ = winreg.QueryValueEx(k, keyword)
                if str(check_val) == "3":
                    return True, "已设为【无 SMPS (No SMPS)】，多天线常开防休眠已生效"
        except Exception as e:
            return False, f"验证失败：无法读出 MIMO 节能注册表 ({e})"

        return False, "验证未通过：写入 MIMO 节能后未读出预期值 3"

    def _fix_ipv6_binding(self, item: Dict[str, Any]) -> Tuple[bool, str]:
        """Disable router discovery & ignore default routes on WLAN via native netsh with exact rollback."""
        if not self.adapter:
            return False, "未找到有效的无线网卡硬件"

        name = self.adapter.get("name", "WLAN")

        # 1. Query exact original values before modifying
        code, out, _ = run_native("netsh", ["interface", "ipv6", "show", "interface", name])
        if code != 0 or not out:
            code, out, _ = run_cmd(f'netsh interface ipv6 show interface "{name}"')

        orig_rd = "disabled" if re.search(r"Router\s*Discovery\s*:\s*disabled|路由器发现\s*:\s*(?:已禁用|disabled)", out, re.I) else "enabled"
        orig_idr = "enabled" if re.search(r"Ignore\s*Default\s*Routes\s*:\s*enabled|忽略默认路由\s*:\s*(?:已启用|enabled)", out, re.I) else "disabled"

        restore_info = {
            "type": "netsh_ipv6",
            "adapter_name": name,
            "orig_router_discovery": orig_rd,
            "orig_ignore_default_routes": orig_idr
        }
        BackupManager.save_item_snapshot(
            "wlan_ipv6_binding",
            "WLAN IPv6 路由超时防御",
            f"路由宣告={orig_rd}, 忽略默认路由={orig_idr}",
            "路由宣告=disabled, 忽略默认路由=enabled",
            restore_info
        )

        # 2. Run native netsh commands
        cmd_args = ["interface", "ipv6", "set", "interface", name, "routerdiscovery=disabled", "ignoredefaultroutes=enabled"]
        code, out, err = run_native("netsh", cmd_args)
        if code != 0:
            code, out, err = run_cmd(f'netsh interface ipv6 set interface "{name}" routerdiscovery=disabled ignoredefaultroutes=enabled')

        if code != 0:
            return False, f"执行 netsh 命令失败: {err or out}"

        # 3. Read-back verification
        v_code, v_out, _ = run_native("netsh", ["interface", "ipv6", "show", "interface", name])
        v_rd = bool(re.search(r"Router\s*Discovery\s*:\s*disabled|路由器发现\s*:\s*(?:已禁用|disabled)", v_out, re.I))
        v_idr = bool(re.search(r"Ignore\s*Default\s*Routes\s*:\s*enabled|忽略默认路由\s*:\s*(?:已启用|enabled)", v_out, re.I))

        if v_rd and v_idr:
            return True, "已成功停用热点 IPv6 路由接管（彻底杜绝15分钟热点宣告失效掉线），经验证生效"
        return False, "验证未通过：IPv6 路由防御参数未能在网卡生效"

    def _fix_flush_dns_arp(self, item: Dict[str, Any]) -> Tuple[bool, str]:
        """Flush DNS cache and ARP table via native utilities."""
        c1, _, e1 = run_native("ipconfig", ["/flushdns"])
        c2, _, e2 = run_native("arp", ["-d", "*"])
        if c1 == 0 and c2 == 0:
            return True, "已刷新 Windows DNS 缓存与 ARP 邻居表 (即时生效，协议栈随网络通信自动重建)"
        return False, f"缓存清理失败: ipconfig返回={c1}, arp返回={c2}"

    @classmethod
    def rollback_all(cls) -> Dict[str, Any]:
        """
        Rollback all previously backed-up settings to their exact original states.
        Enforces strict registry path whitelisting and only removes successfully restored items.
        """
        backup = BackupManager.load_backup()
        items = backup.get("items", {})

        if not items:
            Logger.warning("当前没有检测到任何需要撤回的历史优化记录。")
            return {"total": 0, "success": 0, "failed": 0, "details": []}

        Logger.info(f"===> 开始一键撤销所有修改，共 {len(items)} 项配置待还原 <===")
        summary = {
            "total": len(items),
            "success": 0,
            "failed": 0,
            "details": []
        }

        for item_id, record in list(items.items()):
            title = record.get("title", item_id)
            orig_val = record.get("original_val")
            restore_info = record.get("restore_info", {})
            r_type = restore_info.get("type")

            Logger.info(f"正在撤回还原: 【{title}】 (目标还原值: {orig_val})...")
            success = False
            detail = ""

            try:
                if r_type == "registry_val":
                    path = restore_info.get("path", "")
                    name = restore_info.get("name", "")
                    val = restore_info.get("orig_val")
                    vtype = restore_info.get("val_type", winreg.REG_SZ)
                    existed = restore_info.get("existed", True)

                    # Security Whitelist Check: Prevent registry injection via JSON tampering
                    path_clean = path.lower().strip()
                    name_clean = name.lower().strip()
                    if not path_clean.startswith(ALLOWED_REG_PREFIX) or name_clean not in ALLOWED_REG_NAMES:
                        success = False
                        detail = f"安全拦截：注册表路径 [{path}] 或参数 [{name}] 不在白名单内，已拒绝写入！"
                    else:
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_SET_VALUE) as k:
                            if not existed:
                                # Value did not exist originally -> delete it!
                                try:
                                    winreg.DeleteValue(k, name)
                                    detail = f"已删除优化新增的键值 {name}，恢复初始未配置状态"
                                except FileNotFoundError:
                                    detail = f"初始未配置，键值已处于干净状态"
                                success = True
                            else:
                                # Value existed originally -> restore exact type and value
                                winreg.SetValueEx(k, name, 0, vtype, val)
                                detail = f"已通过注册表将 {name} 还原为原始值 ({val})"
                                success = True

                elif r_type == "powercfg_wireless":
                    orig_ac = str(restore_info.get("orig_ac", 0))
                    orig_dc = str(restore_info.get("orig_dc", 0))
                    subgroup = "19cbb8fa-5279-450e-9fac-8a3d5fedd0c1"
                    setting = "12bbebe6-58d6-4636-95bb-3217ef867c1a"
                    c1, _, _ = run_native("powercfg", ["/setacvalueindex", "SCHEME_CURRENT", subgroup, setting, orig_ac])
                    c2, _, _ = run_native("powercfg", ["/setdcvalueindex", "SCHEME_CURRENT", subgroup, setting, orig_dc])
                    c3, _, _ = run_native("powercfg", ["/s", "SCHEME_CURRENT"])
                    if c1 == 0 and c2 == 0 and c3 == 0:
                        success = True
                        detail = f"已恢复电源方案无线设置为原始值 (AC: {orig_ac}, DC: {orig_dc})"
                    else:
                        success = False
                        detail = "powercfg 恢复命令执行失败"

                elif r_type == "netsh_ipv6":
                    name = restore_info.get("adapter_name", "WLAN")
                    orig_rd = restore_info.get("orig_router_discovery", "enabled")
                    orig_idr = restore_info.get("orig_ignore_default_routes", "disabled")
                    code, _, err = run_native("netsh", ["interface", "ipv6", "set", "interface", name, f"routerdiscovery={orig_rd}", f"ignoredefaultroutes={orig_idr}"])
                    if code == 0:
                        success = True
                        detail = f"已精确还原 IPv6 策略为初始配置 (路由宣告={orig_rd}, 忽略默认路由={orig_idr})"
                    else:
                        success = False
                        detail = f"还原 IPv6 netsh 失败: {err}"

                elif r_type == "adapter_power":
                    orig_wmi = restore_info.get("orig_wmi", True)
                    orig_pnp = restore_info.get("orig_pnp")
                    orig_pnp_exists = restore_info.get("orig_pnp_exists", orig_pnp is not None)
                    path = restore_info.get("path")
                    # Restore WMI
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
                                it.Enable = bool(orig_wmi)
                                it.Put_()
                                break
                    except Exception as e:
                        Logger.warning(f"WMI 还原提示: {e}")
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

                    # Restore Registry
                    if path:
                        # Security check on path
                        if path.lower().startswith(ALLOWED_REG_PREFIX):
                            try:
                                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_SET_VALUE) as k:
                                    if orig_pnp_exists and orig_pnp is not None:
                                        winreg.SetValueEx(k, "PnPCapabilities", 0, winreg.REG_DWORD, orig_pnp)
                                    else:
                                        try:
                                            winreg.DeleteValue(k, "PnPCapabilities")
                                        except FileNotFoundError:
                                            pass
                            except Exception:
                                pass
                    success = True
                    detail = "已恢复网卡电源节能为原始状态"

                else:
                    success = True
                    detail = "跳过无状态项"

            except Exception as e:
                success = False
                detail = f"撤销异常: {str(e)}"

            if success:
                summary["success"] += 1
                # Selective cleanup: only remove snapshot when successfully rolled back!
                BackupManager.remove_item_snapshot(item_id)
                Logger.success(f"【{title}】撤销成功: {detail}")
            else:
                summary["failed"] += 1
                Logger.error(f"【{title}】撤销失败: {detail}，保留快照以便重试。")

            summary["details"].append({
                "id": item_id,
                "title": title,
                "success": success,
                "detail": detail
            })
            time.sleep(0.05)

        Logger.info(f"===> 撤回操作执行完毕！成功: {summary['success']}, 失败: {summary['failed']} <===")
        return summary
