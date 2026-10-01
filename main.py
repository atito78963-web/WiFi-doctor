# -*- coding: utf-8 -*-
"""
WiFi Doctor - Graphical User Interface (Tkinter / TTK)
Modern, responsive, Win11-styled GUI with deep scan, itemized selection,
live logging, verification, and full one-click rollback.
"""

import os
import sys
import threading
from typing import Dict, Any, List, Optional
import tkinter as tk
from tkinter import ttk, messagebox

from utils import Logger, BackupManager, is_admin, run_as_admin, LOG_FILE
from diagnostics import DiagnosticEngine
from fixer import FixerEngine

# Enforce UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


class WiFiDoctorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("WiFi Doctor")
        self.root.geometry("1000x720")
        self.root.minsize(900, 640)

        # Apply modern style
        self.style = ttk.Style()
        try:
            self.style.theme_use('clam')
        except Exception:
            pass

        self._configure_styles()

        self.diag_engine = DiagnosticEngine()
        self.fixer_engine = None
        self.scan_items = []
        self.item_check_vars = {}

        self._build_ui()

        # Register logger listener to write to UI
        Logger.register_listener(self._on_log_received)

        # Initial check
        self.root.after(300, self._initial_check)

    def _configure_styles(self):
        font_main = ('Microsoft YaHei UI', 9)
        font_bold = ('Microsoft YaHei UI', 9, 'bold')
        font_title = ('Microsoft YaHei UI', 13, 'bold')

        self.root.option_add("*Font", font_main)

        # Style colors
        bg_color = "#f4f6f9"
        self.root.configure(bg=bg_color)

        self.style.configure(".", background=bg_color, font=font_main)
        self.style.configure("TFrame", background=bg_color)
        self.style.configure("Card.TFrame", background="#ffffff", relief="solid", borderwidth=1)
        self.style.configure("TLabel", background=bg_color, foreground="#2d3748")
        self.style.configure("Card.TLabel", background="#ffffff", foreground="#2d3748")
        self.style.configure("Title.TLabel", font=font_title, foreground="#1a202c", background=bg_color)
        self.style.configure("Subtitle.TLabel", font=('Microsoft YaHei UI', 9), foreground="#718096", background=bg_color)

        # Buttons
        self.style.configure("Primary.TButton", font=font_bold, foreground="#ffffff", background="#2b6cb0", padding=6)
        self.style.map("Primary.TButton", background=[("active", "#2c5282")])

        self.style.configure("Success.TButton", font=font_bold, foreground="#ffffff", background="#2f855a", padding=6)
        self.style.map("Success.TButton", background=[("active", "#22543d")])

        self.style.configure("Danger.TButton", font=font_bold, foreground="#ffffff", background="#c53030", padding=6)
        self.style.map("Danger.TButton", background=[("active", "#9b2c2c")])

        self.style.configure("TButton", font=font_main, padding=5)

        # Treeview
        self.style.configure("Treeview", 
            background="#ffffff", 
            foreground="#2d3748", 
            fieldbackground="#ffffff", 
            rowheight=28,
            font=font_main
        )
        self.style.configure("Treeview.Heading", font=font_bold, foreground="#1a202c", background="#edf2f7")
        self.style.map("Treeview", background=[("selected", "#ebf8ff")], foreground=[("selected", "#2b6cb0")])

    def _build_ui(self):
        # 1. Top Header
        header_frame = ttk.Frame(self.root, padding="15 12 15 8")
        header_frame.pack(fill="x")

        title_box = ttk.Frame(header_frame)
        title_box.pack(side="left", fill="y")
        ttk.Label(title_box, text="WiFi Doctor", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="诊断热点断线原因，按需应用可回滚的修复", style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))

        # Admin Badge
        self.admin_badge_frame = ttk.Frame(header_frame)
        self.admin_badge_frame.pack(side="right", anchor="center")
        self.lbl_admin = tk.Label(self.admin_badge_frame, text="检测权限中...", font=('Microsoft YaHei UI', 9, 'bold'), padx=10, pady=4)
        self.lbl_admin.pack(side="right")

        # 2. Adapter Info Bar
        info_frame = ttk.Frame(self.root, padding="15 0 15 8")
        info_frame.pack(fill="x")
        self.card_info = ttk.Frame(info_frame, style="Card.TFrame", padding="10 8")
        self.card_info.pack(fill="x")

        self.lbl_adapter = ttk.Label(self.card_info, text="正在读取无线网卡与网络配置...", style="Card.TLabel")
        self.lbl_adapter.pack(side="left")

        # 3. Main PanedWindow (Split: Items List Top, Details & Log Bottom)
        main_paned = ttk.PanedWindow(self.root, orient="vertical")
        main_paned.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        # --- Top Section: Scan Items List ---
        top_pane = ttk.Frame(main_paned)
        main_paned.add(top_pane, weight=5)

        # Toolbar above tree
        toolbar = ttk.Frame(top_pane)
        toolbar.pack(fill="x", pady=(0, 6))

        self.btn_scan = ttk.Button(toolbar, text="🔍 开始深度扫描诊断", style="Primary.TButton", command=self.on_start_scan)
        self.btn_scan.pack(side="left", padx=(0, 8))

        self.btn_select_all = ttk.Button(toolbar, text="全选", command=self.select_all_items)
        self.btn_select_all.pack(side="left", padx=3)

        self.btn_select_none = ttk.Button(toolbar, text="取消全选", command=self.select_no_items)
        self.btn_select_none.pack(side="left", padx=3)

        self.btn_select_issues = ttk.Button(toolbar, text="仅选中隐患项", command=self.select_only_issues)
        self.btn_select_issues.pack(side="left", padx=3)

        # Right Action Buttons
        self.btn_rollback = ttk.Button(toolbar, text="↩️ 一键撤销所有修改 (恢复原状)", style="Danger.TButton", command=self.on_rollback_all)
        self.btn_rollback.pack(side="right", padx=(8, 0))

        self.btn_fix = ttk.Button(toolbar, text="⚡ 一键优化/修复选中项", style="Success.TButton", command=self.on_apply_fixes)
        self.btn_fix.pack(side="right", padx=4)

        # Treeview for diagnostic items
        tree_container = ttk.Frame(top_pane)
        tree_container.pack(fill="both", expand=True)

        columns = ("selected", "category", "title", "status", "action")
        self.tree = ttk.Treeview(tree_container, columns=columns, show="headings", selectmode="browse")
        
        self.tree.heading("selected", text="选择", anchor="center")
        self.tree.heading("category", text="分类", anchor="w")
        self.tree.heading("title", text="诊断检测项目", anchor="w")
        self.tree.heading("status", text="当前状态与检测结果", anchor="w")
        self.tree.heading("action", text="建议优化方案", anchor="w")

        self.tree.column("selected", width=55, minwidth=45, anchor="center")
        self.tree.column("category", width=110, minwidth=90, anchor="w")
        self.tree.column("title", width=260, minwidth=180, anchor="w")
        self.tree.column("status", width=260, minwidth=180, anchor="w")
        self.tree.column("action", width=250, minwidth=160, anchor="w")

        tree_scroll_y = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set)

        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll_y.pack(side="right", fill="y")

        self.tree.bind("<ButtonRelease-1>", self.on_tree_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # Progress bar
        self.progress_bar = ttk.Progressbar(top_pane, mode="indeterminate")

        # --- Bottom Section: Item Detail Box & Real-Time Log ---
        bottom_pane = ttk.Frame(main_paned)
        main_paned.add(bottom_pane, weight=4)

        # Notebook for Detail / Log
        self.notebook = ttk.Notebook(bottom_pane)
        self.notebook.pack(fill="both", expand=True)

        # Tab 1: Item Detail Explanation
        self.tab_detail = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.tab_detail, text="项目详情")

        self.txt_detail = tk.Text(self.tab_detail, wrap="word", bg="#ffffff", fg="#2d3748", relief="flat", padx=10, pady=10, font=('Microsoft YaHei UI', 9))
        self.txt_detail.pack(fill="both", expand=True)
        self.txt_detail.insert("1.0", "请在上方列表中点击任意项目，查看其为什么会导致【15分钟周期性断网】的底层机制、优化细节以及撤销原理。")
        self.txt_detail.config(state="disabled")

        # Tab 2: Live Log
        self.tab_log = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.tab_log, text="运行日志")

        log_container = ttk.Frame(self.tab_log)
        log_container.pack(fill="both", expand=True)

        self.txt_log = tk.Text(log_container, wrap="word", bg="#1a202c", fg="#e2e8f0", relief="flat", padx=8, pady=8, font=('Consolas', 9))
        log_scroll_y = ttk.Scrollbar(log_container, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=log_scroll_y.set)

        self.txt_log.pack(side="left", fill="both", expand=True)
        log_scroll_y.pack(side="right", fill="y")

        # Configure log text tags
        self.txt_log.tag_config("INFO", foreground="#63b3ed")
        self.txt_log.tag_config("SUCCESS", foreground="#68d391")
        self.txt_log.tag_config("WARN", foreground="#f6ad55")
        self.txt_log.tag_config("ERROR", foreground="#fc8181")

        # Bottom status bar
        status_bar = ttk.Frame(self.root, padding="15 4 15 8")
        status_bar.pack(fill="x")
        self.lbl_status = ttk.Label(status_bar, text="准备就绪。点击“开始扫描”检查当前 Wi-Fi 配置。")
        self.lbl_status.pack(side="left")

        btn_open_log = ttk.Button(status_bar, text="打开日志文件", command=self.open_log_file)
        btn_open_log.pack(side="right")

    def _initial_check(self):
        """Perform initial privileges check and adapter detection."""
        if is_admin():
            self.lbl_admin.config(text="✔ 管理员权限正常", bg="#c6f6d5", fg="#22543d")
        else:
            self.lbl_admin.config(text="⚠ 权限受限 [点击以管理员运行]", bg="#fed7d7", fg="#9b2c2c", cursor="hand2")
            self.lbl_admin.bind("<Button-1>", lambda e: self.elevate_admin())
            messagebox.showwarning("提示", "当前未以管理员权限运行！\n修改硬件节能及网络协议需要管理员权限，建议点击右上角以管理员身份重新运行。")

        # Find adapter in background
        threading.Thread(target=self._load_adapter_info, daemon=True).start()

    def elevate_admin(self):
        if run_as_admin():
            self.root.destroy()
        else:
            messagebox.showerror("错误", "无法调起系统 UAC 提权窗口，请右键以管理员身份运行本程序。")

    def _load_adapter_info(self):
        adapter = self.diag_engine.find_wifi_adapter()
        if adapter:
            self.fixer_engine = FixerEngine(adapter)
            text = f"🌐 当前无线网卡: [{adapter['name']}] {adapter['description']} | 驱动: {adapter['driver_version']} ({adapter['driver_date']}) | 状态: {adapter['status']}"
            status_text = "无线网卡已就绪。请点击左上方【🔍 开始深度扫描诊断】按钮开始排查。"
            self.root.after(0, lambda: self.lbl_adapter.config(text=text, foreground="#2d3748"))
            self.root.after(0, lambda: self.lbl_status.config(text=status_text))
            self.root.after(0, lambda: self.btn_scan.config(state="normal"))
            Logger.info(f"已就绪，识别到无线网卡: [{adapter['name']}] {adapter['description']}")
        else:
            text = "❌ 未检测到可用的 Wi-Fi 无线网卡，请确认笔记本无线硬件是否正常！"
            status_text = "未找到无线网卡。无法执行 Wi-Fi 诊断。"
            self.root.after(0, lambda: self.lbl_adapter.config(text=text, foreground="#e53e3e"))
            self.root.after(0, lambda: self.lbl_status.config(text=status_text))
            self.root.after(0, lambda: self.btn_scan.config(state="disabled"))
            self.root.after(0, lambda: self.btn_fix.config(state="disabled"))
            Logger.warn("未检测到可用的 Wi-Fi 无线网卡")

    def on_start_scan(self):
        """Trigger scan in background thread."""
        # Adapter discovery already runs during startup. Avoid repeating the
        # native scan on the Tk event thread, which makes the button feel stuck.
        if not self.diag_engine.wifi_adapter:
            messagebox.showwarning("提示", "未检测到可用的 Wi-Fi 无线网卡，无法进行无线网络诊断。")
            return

        self.btn_scan.config(state="disabled")
        self.progress_bar.pack(fill="x", pady=(4, 0))
        self.progress_bar.start(10)
        self.lbl_status.config(text="正在进行深度诊断扫描，请稍候...")

        threading.Thread(target=self._run_scan_thread, daemon=True).start()

    def _run_scan_thread(self):
        try:
            results = self.diag_engine.scan_all()
            self.root.after(0, lambda: self._on_scan_completed(results))
        except Exception as e:
            Logger.error(f"扫描发生未捕获异常: {e}")
            self.root.after(0, lambda: self._on_scan_error(str(e)))

    def _on_scan_error(self, err_msg: str):
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        self.btn_scan.config(state="normal")
        self.lbl_status.config(text=f"扫描失败: {err_msg}")
        messagebox.showerror("扫描失败", f"扫描过程中发生错误：\n{err_msg}")

    def _on_scan_completed(self, results):
        self.scan_items = results
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        self.btn_scan.config(state="normal")

        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.item_check_vars = {}
        issue_count = 0

        for it in results:
            item_id = it["id"]
            checked = it.get("selected", False)
            self.item_check_vars[item_id] = checked
            check_box = " [ √ ] " if checked else " [   ] "

            if it.get("can_fix", True) and it.get("has_issue", False):
                issue_count += 1
                status_disp = f"⚠️ {it['current_val']}"
            elif not it.get("can_fix", True):
                status_disp = f"ℹ️ {it['current_val']}"
            else:
                status_disp = f"✔ {it['current_val']}"

            # Insert into tree
            iid = self.tree.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    check_box,
                    it.get("category", "基础"),
                    it.get("title", ""),
                    status_disp,
                    it.get("fix_action", "")
                )
            )

        if issue_count > 0:
            status_msg = f"扫描完毕！共检测 {len(results)} 个核心项，发现 {issue_count} 项待优化点。已自动勾选，可点击【一键优化/修复选中项】。"
        else:
            status_msg = "扫描完毕！所有核心网络与电源配置均已处于最佳健康状态（0 待优化项）。"
        self.lbl_status.config(text=status_msg)
        Logger.info(status_msg)

        # Check if backup exists to update rollback button state
        backup = BackupManager.load_backup()
        num_backup = len(backup.get("items", {}))
        if num_backup > 0:
            self.btn_rollback.config(text=f"↩️ 一键撤销所有修改 ({num_backup}项可还原)")
        else:
            self.btn_rollback.config(text="↩️ 一键撤销所有修改 (暂无备份)")

    def on_tree_click(self, event):
        """Toggle checkbox when clicking on the first column."""
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        column = self.tree.identify_column(event.x)
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        # Check if clicked on first column (select checkbox)
        if column == "#1":
            cur = self.item_check_vars.get(item_id, False)
            # Find item
            item_obj = next((x for x in self.scan_items if x["id"] == item_id), None)
            if item_obj and not item_obj.get("can_fix", True):
                # Info-only item
                return
            new_val = not cur
            self.item_check_vars[item_id] = new_val
            check_box = " [ √ ] " if new_val else " [   ] "
            self.tree.set(item_id, "selected", check_box)

    def on_tree_select(self, event):
        """Show detailed explanation when row is selected."""
        selected = self.tree.selection()
        if not selected:
            return
        item_id = selected[0]
        item_obj = next((x for x in self.scan_items if x["id"] == item_id), None)
        if not item_obj:
            return

        self._show_item_detail(item_obj)

    def _show_item_detail(self, it: Dict[str, Any]):
        self.txt_detail.config(state="normal")
        self.txt_detail.delete("1.0", "end")

        title = it.get("title", "")
        cat = it.get("category", "")
        status = it.get("current_val", "")
        has_issue = it.get("has_issue", False)
        issue_desc = it.get("issue_desc", "")
        rec = it.get("recommendation", "")
        action = it.get("fix_action", "")
        can_fix = it.get("can_fix", True)

        detail_text = f"【项目名称】 {title} ({cat})\n"
        detail_text += f"【当前检测状态】 {status}\n"
        detail_text += f"【健康评估】 {'⚠️ 存在隐患（与 15 分钟热点断网高度相关）' if has_issue else '✔ 状态健康'}\n\n"
        detail_text += f"🔍【底层机制与断网诱因分析】\n{issue_desc}\n\n"
        detail_text += f"🛠️【建议优化方案】\n{rec}\n\n"
        can_rollback = it.get("can_rollback", True)
        if can_fix:
            detail_text += f"⚡【执行操作】 {action}\n"
            if can_rollback:
                detail_text += "↩️【可撤回保障】 执行前将自动在快照数据库中保存初始参数，若优化后无改善可随时点击【一键撤销】无损恢复！\n"
            else:
                detail_text += f"↩️【可撤回说明】 {it.get('rollback_note', '本项为即时维护动作，不写入持久配置，不可亦无需撤销。')}\n"
        else:
            detail_text += "ℹ️【说明】 本项为系统级审查与日志归因信息，仅作为诊断依据，无需单独修改。\n"

        self.txt_detail.insert("1.0", detail_text)
        self.txt_detail.config(state="disabled")

    def select_all_items(self):
        for it in self.scan_items:
            item_id = it["id"]
            if it.get("can_fix", True):
                self.item_check_vars[item_id] = True
                self.tree.set(item_id, "selected", " [ √ ] ")

    def select_no_items(self):
        for it in self.scan_items:
            item_id = it["id"]
            self.item_check_vars[item_id] = False
            self.tree.set(item_id, "selected", " [   ] ")

    def select_only_issues(self):
        for it in self.scan_items:
            item_id = it["id"]
            if it.get("can_fix", True) and it.get("has_issue", False):
                self.item_check_vars[item_id] = True
                self.tree.set(item_id, "selected", " [ √ ] ")
            else:
                self.item_check_vars[item_id] = False
                self.tree.set(item_id, "selected", " [   ] ")

    def on_apply_fixes(self):
        """Execute selected fixes."""
        if not is_admin():
            if not messagebox.askyesno("权限提示", "当前未以管理员权限运行，修改网络设置可能会失败。是否尝试提权运行？"):
                return
            self.elevate_admin()
            return

        to_fix = []
        for it in self.scan_items:
            if self.item_check_vars.get(it["id"], False) and it.get("can_fix", True):
                to_fix.append(it)

        if not to_fix:
            messagebox.showinfo("提示", "请先在上方列表中勾选需要优化/修复的项目。")
            return

        names = "\n".join([f"• {x['title']}" for x in to_fix])
        snapshot_count = sum(1 for item in to_fix if item.get("can_rollback", True))
        instant_count = len(to_fix) - snapshot_count
        if snapshot_count and instant_count:
            backup_note = (
                "可回滚项目会在修改前保存原始状态快照；\n"
                "网卡重启、缓存刷新等即时维护项目不会创建快照，也不进入撤销列表。"
            )
        elif snapshot_count:
            backup_note = "系统将在修改前为可回滚项目保存原始状态快照。"
        else:
            backup_note = "本次仅执行即时维护动作，不创建快照，也不进入撤销列表。"
        confirm = messagebox.askyesno(
            "确认执行优化",
            f"即将对以下 {len(to_fix)} 项进行优化修复：\n\n{names}\n\n"
            f"{backup_note}\n"
            "是否立即开始执行？"
        )
        if not confirm:
            return

        # Switch to log tab so user can watch in real time
        self.notebook.select(self.tab_log)
        self.btn_fix.config(state="disabled")
        self.btn_rollback.config(state="disabled")
        self.lbl_status.config(text=f"正在优化 {len(to_fix)} 个项目，请观察日志...")

        threading.Thread(target=self._run_fixes_thread, args=(to_fix,), daemon=True).start()

    def _run_fixes_thread(self, to_fix):
        try:
            if not self.fixer_engine:
                adapter = self.diag_engine.find_wifi_adapter()
                if not adapter:
                    raise RuntimeError("未检测到可用的 Wi-Fi 网卡，无法执行修复")
                self.fixer_engine = FixerEngine(adapter)

            res = self.fixer_engine.apply_fixes(to_fix)
            self.root.after(0, lambda: self._on_fixes_completed(res))
        except Exception as e:
            Logger.error(f"优化执行发生异常: {e}")
            self.root.after(0, lambda: self._on_fixes_error(str(e)))

    def _on_fixes_error(self, err_msg: str):
        self.btn_fix.config(state="normal")
        self.btn_rollback.config(state="normal")
        self.lbl_status.config(text=f"优化失败: {err_msg}")
        messagebox.showerror("优化异常", f"优化过程中发生错误：\n{err_msg}")

    def _on_fixes_completed(self, res):
        self.btn_fix.config(state="normal")
        self.btn_rollback.config(state="normal")

        instant_count = sum(1 for item in res.get("details", []) if not item.get("can_rollback", True))
        rollback_note = (
            f"\n\n其中 {instant_count} 项为即时维护动作，不进入撤销列表。"
            if instant_count else
            "\n\n成功修改仍可从“撤销修改”恢复。"
        )
        msg = f"优化完成\n成功：{res['success']} 项\n失败：{res['failed']} 项{rollback_note}"
        self.lbl_status.config(text=f"优化完毕: 成功 {res['success']} 项，失败 {res['failed']} 项。")
        messagebox.showinfo("优化结果", msg)

        # Re-run scan to reflect new values
        self.on_start_scan()

    def on_rollback_all(self):
        """Revert all changes using saved snapshot."""
        backup = BackupManager.load_backup()
        items = backup.get("items", {})
        if not items:
            messagebox.showinfo("提示", "当前没有检测到任何历史优化记录，无需撤销。")
            return

        names = "\n".join([f"• {v['title']} (将还原为: {v['original_val']})" for v in items.values()])
        confirm = messagebox.askyesno(
            "确认一键撤回所有修改",
            f"检测到历史修改快照包含以下 {len(items)} 项：\n\n{names}\n\n"
            "点击『是』将立即把以上所有设置 100% 还原为原始配置。\n"
            "确认立即撤销吗？"
        )
        if not confirm:
            return

        self.notebook.select(self.tab_log)
        self.btn_fix.config(state="disabled")
        self.btn_rollback.config(state="disabled")
        self.lbl_status.config(text="正在一键撤回所有修改，还原系统初始状态...")

        threading.Thread(target=self._run_rollback_thread, daemon=True).start()

    def _run_rollback_thread(self):
        try:
            res = FixerEngine.rollback_all()
            self.root.after(0, lambda: self._on_rollback_completed(res))
        except Exception as e:
            Logger.error(f"撤回还原发生异常: {e}")
            self.root.after(0, lambda: self._on_rollback_error(str(e)))

    def _on_rollback_error(self, err_msg: str):
        self.btn_fix.config(state="normal")
        self.btn_rollback.config(state="normal")
        self.lbl_status.config(text=f"撤销失败: {err_msg}")
        messagebox.showerror("撤销异常", f"撤回过程中发生错误：\n{err_msg}")

    def _on_rollback_completed(self, res):
        self.btn_fix.config(state="normal")
        self.btn_rollback.config(state="normal")

        msg = f"撤销还原操作执行完成！\n成功还原: {res['success']} 项\n失败: {res['failed']} 项\n\n系统配置已恢复至优化前的原始状态。"
        self.lbl_status.config(text=f"撤销完成：成功 {res['success']} 项，失败 {res['failed']} 项。")
        messagebox.showinfo("撤回完成", msg)

        # Re-scan to show original state
        self.on_start_scan()

    def _on_log_received(self, level, entry):
        """Append log line to UI text widget."""
        def append():
            self.txt_log.insert("end", entry + "\n", level)
            self.txt_log.see("end")
        self.root.after(0, append)

    def open_log_file(self):
        if os.path.exists(LOG_FILE):
            try:
                os.startfile(LOG_FILE)
            except Exception as e:
                messagebox.showerror("打开失败", f"无法打开日志文件: {e}")
        else:
            messagebox.showinfo("提示", "暂无日志文件。")


def main():
    root = tk.Tk()
    app = WiFiDoctorApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
