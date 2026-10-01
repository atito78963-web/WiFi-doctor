# WiFi Doctor

WiFi Doctor 是一个面向 Windows 11 的 Wi-Fi 热点断线诊断与修复工具，重点处理手机热点周期性断线、电源管理、无线网卡高级参数和 IPv6 路由策略等问题。

## 功能

- 检查无线网卡电源管理、电源计划、漫游激进度和 MIMO 节能。
- 检查 WLAN IPv6 路由发现、WLAN 自动配置服务、近期系统更新和断线事件。
- Wi-Fi 图标消失或网卡状态卡死时，可按需禁用并重新启用 Wi-Fi 接口。
- 修复前保存快照，支持按项目选择和一键回滚。
- 所有命令检查返回值，并在修改后读取系统状态验证结果。
- 使用 Tkinter 构建，无需目标电脑安装 Python。

网卡重启项使用 Windows 自带的 `netsh` 临时切换接口状态，执行期间 Wi-Fi 会短暂断开；它不会修改驱动文件，也不创建持久回滚快照。

## 使用已发布程序

从 GitHub Releases 下载 `WiFiDoctor.exe`，右键以管理员身份运行。程序会请求 UAC 权限，因为部分检查和修复需要访问系统注册表、电源计划和网络配置。

程序只修改用户明确选择的项目。修改前会保存快照，快照存放在 `%ProgramData%\\WiFiDoctor`。

## 从源码构建

```powershell
py -m pip install -r requirements.txt
py build_exe.py
```

生成文件位于 `dist/WiFiDoctor.exe`。

## 注意事项

不同无线网卡驱动公开的注册表参数可能不同。工具只会修改识别到的参数，无法保证适用于所有硬件组合。IPv6 策略修改可能影响依赖 IPv6 的网络，必要时可使用“撤销修改”恢复。

## 许可证

本项目使用 MIT License，详见 [LICENSE](LICENSE)。
