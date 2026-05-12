import sys
import os
import subprocess
import shutil

# 自动安装缺失依赖
def _ensure_deps():
    required = {'customtkinter': 'customtkinter'}
    for mod, pkg in required.items():
        try:
            __import__(mod)
        except ImportError:
            print(f"[自动安装] 正在安装缺失依赖: {pkg} ...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg])

_ensure_deps()

import customtkinter as ctk
import tkinter as tk
import threading
import tkinter.messagebox as messagebox
import winreg
import urllib.request
import re
import tempfile
import ctypes
import json
import queue
import tokenize
import io
from concurrent.futures import ThreadPoolExecutor

IS_FROZEN = getattr(sys, 'frozen', False)
# Windows 控制台默认编码 (GBK/CP936)，用于解码本地程序输出
SYS_ENCODING = 'gbk' if os.name == 'nt' else 'utf-8'

def _version_key(v):
    """将版本号字符串解析为可排序的元组，安全处理如 3.14.0b2 等非纯数字版本号"""
    parts = re.split(r'[^0-9]+', v)
    return tuple(int(p) for p in parts if p)

PROBE_SCRIPT = """
import importlib.metadata
import os
import datetime
import json

def get_size_and_date(dist):
    try:
        files = dist.files
        if not files:
            return "N/A", "N/A", 0
        
        base_path = None
        p = dist.locate_file(files[0])
        if os.path.exists(p):
            base_path = os.path.dirname(str(p))
            
        if not base_path or not os.path.exists(base_path):
            return "未知", "未知", 0
            
        total_size = 0
        latest_time = 0
        
        for dirpath, _, filenames in os.walk(base_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    stat = os.stat(fp)
                    total_size += stat.st_size
                    if stat.st_mtime > latest_time:
                        latest_time = stat.st_mtime
                except: pass
                
        size_str = f"{total_size / (1024*1024):.2f} MB"
        if latest_time > 0:
            date_str = datetime.datetime.fromtimestamp(latest_time).strftime('%Y-%m-%d %H:%M')
        else:
            date_str = "未知"
        return size_str, date_str, total_size
    except:
        return "错误", "错误", 0

data = []
try:
    dists = list(importlib.metadata.distributions())
    for dist in dists:
        name = dist.metadata['Name']
        version = dist.version
        size, date, raw_size = get_size_and_date(dist)
        data.append({
            "name": name,
            "version": version,
            "size": size,
            "date": date,
            "raw_size": raw_size
        })
except Exception as e:
    data = [{"error": str(e)}]

print(json.dumps(data))
"""

# 设置极简科技风主题
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class PythonEnvManager(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Python Environment & Package Manager")
        self.geometry("1200x800")
        
        # 核心数据结构
        self.python_paths = []
        self.installed_versions = {}
        self.current_python = None
        self.installed_packages = []
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # 打包工具相关
        self.resource_files = []
        self.clean_files = []
        self.log_queue = queue.Queue()
        self.clean_log_queue = queue.Queue()
        self.base_path = sys._MEIPASS if IS_FROZEN else os.path.dirname(os.path.abspath(__file__))

        self.setup_ui()
        self.auto_scan_environments()
        self.fetch_online_versions_async()
        self._poll_log_queues()

    def setup_ui(self):
        # 左侧面板：Python 版本管理（固定宽度）
        self.sidebar = ctk.CTkFrame(self, width=260, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        
        self.logo_label = ctk.CTkLabel(self.sidebar, text="Env Manager", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.pack(padx=20, pady=(20, 10))

        self.path_entry = ctk.CTkEntry(self.sidebar, placeholder_text="输入 python.exe 绝对路径")
        self.path_entry.pack(padx=15, pady=10, fill="x")

        self.add_btn = ctk.CTkButton(self.sidebar, text="添加解释器", command=self.add_python_path)
        self.add_btn.pack(padx=15, pady=5, fill="x")

        self.scan_btn = ctk.CTkButton(self.sidebar, text="自动扫描本机环境", command=self.auto_scan_environments, fg_color="#2b7b50", hover_color="#1d5c39")
        self.scan_btn.pack(padx=15, pady=5, fill="x")

        self.env_listbox = ctk.CTkOptionMenu(self.sidebar, values=["请先添加解释器"], command=self.select_env, dynamic_resizing=False, width=230)
        self.env_listbox.pack(padx=15, pady=20)

        # 右侧面板：使用 Tabview
        self.main_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="transparent")
        self.main_frame.pack(side="right", fill="both", expand=True, padx=20, pady=20)

        self.tabview = ctk.CTkTabview(self.main_frame)
        self.tabview.pack(fill="both", expand=True)
        
        self.tab_pkg = self.tabview.add("包管理(Package)")
        self.tab_install = self.tabview.add("环境部署(Deploy)")
        self.tab_venv = self.tabview.add("全局虚拟环境(Global Venv)")
        self.tab_pack = self.tabview.add("打包工具(Packaging)")

        self.setup_pkg_tab()
        self.setup_install_tab()
        self.setup_venv_tab()
        self.setup_pack_tab()

    # ==========================
    # Tab 1: 高级包管理 (现代版 UI)
    # ==========================
    def setup_pkg_tab(self):
        self.selected_pkg_name = None
        self.selected_row_frame = None
        self.sort_col = "name"
        self.sort_reverse = False
        
        # 顶部操作区
        self.action_frame = ctk.CTkFrame(self.tab_pkg, fg_color="transparent")
        self.action_frame.pack(padx=10, pady=10, fill="x")

        # 搜索
        ctk.CTkLabel(self.action_frame, text="搜索库:").pack(side="left", padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self.filter_packages)
        self.search_entry = ctk.CTkEntry(self.action_frame, textvariable=self.search_var, width=120)
        self.search_entry.pack(side="left", padx=5)

        ctk.CTkLabel(self.action_frame, text=" | ").pack(side="left", padx=5)

        # 安装
        self.pkg_entry = ctk.CTkEntry(self.action_frame, placeholder_text="包名 (如 numpy)", width=150)
        self.pkg_entry.pack(side="left", padx=5)
        self.install_btn = ctk.CTkButton(self.action_frame, text="安装", width=60, command=self.install_package)
        self.install_btn.pack(side="left", padx=5)
        
        # 卸载
        self.uninstall_btn = ctk.CTkButton(self.action_frame, text="卸载选中", width=80, fg_color="#8B0000", hover_color="#5c0000", command=self.uninstall_package)
        self.uninstall_btn.pack(side="left", padx=5)

        # 刷新
        self.refresh_btn = ctk.CTkButton(self.action_frame, text="刷新列表", width=80, command=self.refresh_packages)
        self.refresh_btn.pack(side="right", padx=5)

        # 导出
        self.export_btn = ctk.CTkButton(self.action_frame, text="导出 requirements", width=130, fg_color="#2b7b50", hover_color="#1d5c39", command=self.export_requirements)
        self.export_btn.pack(side="right", padx=5)

        # 主体列表区域
        list_container = ctk.CTkFrame(self.tab_pkg)
        list_container.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 表头
        header_frame = ctk.CTkFrame(list_container, fg_color="#1f538d", height=40, corner_radius=5)
        header_frame.pack(fill="x", padx=5, pady=(5, 0))
        header_frame.pack_propagate(False)
        
        header_frame.columnconfigure(0, weight=3)
        header_frame.columnconfigure(1, weight=2)
        header_frame.columnconfigure(2, weight=2)
        header_frame.columnconfigure(3, weight=3)
        
        btn_name = ctk.CTkButton(header_frame, text="📦 库名", fg_color="transparent", font=ctk.CTkFont(size=14, weight="bold"), command=lambda: self.sort_packages("name"))
        btn_name.grid(row=0, column=0, sticky="w", padx=20, pady=5)
        btn_version = ctk.CTkButton(header_frame, text="🏷️ 版本", fg_color="transparent", font=ctk.CTkFont(size=14, weight="bold"), command=lambda: self.sort_packages("version"))
        btn_version.grid(row=0, column=1, sticky="w", padx=10, pady=5)
        btn_size = ctk.CTkButton(header_frame, text="💾 预估大小", fg_color="transparent", font=ctk.CTkFont(size=14, weight="bold"), command=lambda: self.sort_packages("raw_size"))
        btn_size.grid(row=0, column=2, sticky="w", padx=10, pady=5)
        btn_date = ctk.CTkButton(header_frame, text="🕒 安装时间", fg_color="transparent", font=ctk.CTkFont(size=14, weight="bold"), command=lambda: self.sort_packages("date"))
        btn_date.grid(row=0, column=3, sticky="w", padx=10, pady=5)

        # 数据列表容器
        self.pkg_scroll = ctk.CTkScrollableFrame(list_container, fg_color="transparent")
        self.pkg_scroll.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        # 底部详情区域
        detail_frame = ctk.CTkFrame(self.tab_pkg, fg_color="#1a1a1a", corner_radius=5, height=120)
        detail_frame.pack(fill="x", padx=10, pady=10)
        detail_frame.pack_propagate(False)

        ctk.CTkLabel(detail_frame, text="终端输出与 PyPI 简介:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        self.detail_text = ctk.CTkTextbox(detail_frame, fg_color="transparent")
        self.detail_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.detail_text.configure(state=tk.DISABLED)

    def refresh_packages(self):
        if not self.current_python or self.current_python == "请先添加解释器": return
        self.selected_pkg_name = None
        self.selected_row_frame = None
        for widget in self.pkg_scroll.winfo_children():
            widget.destroy()
        self.set_detail_text(f"正在扫描环境: {self.current_python} ...\n如果库很多，可能需要几秒钟。")
        threading.Thread(target=self._scan_thread, args=(self.current_python,), daemon=True).start()

    def _scan_thread(self, py_path):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run([py_path, "-c", PROBE_SCRIPT], capture_output=True, text=True, encoding='utf-8', errors='ignore', startupinfo=startupinfo)
            if result.returncode != 0: raise Exception(result.stderr)
            raw_json = result.stdout.strip()
            if not raw_json: raise Exception("未返回数据")
            data = json.loads(raw_json)
            if data and "error" in data[0]: raise Exception(f"探针错误: {data[0]['error']}")
            
            self.installed_packages = data
            self.after(0, self._render_packages)
            self.after(0, lambda: self.set_detail_text(f"就绪。共找到 {len(data)} 个库。"))
        except Exception as e:
            self.after(0, lambda: self.set_detail_text(f"扫描失败: {str(e)}"))

    def filter_packages(self, *args):
        self._render_packages()

    def sort_packages(self, col):
        if self.sort_col == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_col = col
            self.sort_reverse = False
        self._render_packages()

    def _render_packages(self):
        for widget in self.pkg_scroll.winfo_children():
            widget.destroy()
            
        self.selected_row_frame = None
        
        query = self.search_var.get().lower()
        filtered = [p for p in self.installed_packages if query in p['name'].lower()]
        
        # 排序
        try:
            filtered.sort(key=lambda x: x[self.sort_col], reverse=self.sort_reverse)
        except:
            pass
            
        for i, pkg in enumerate(filtered):
            bg_color = "#2b2b2b" if i % 2 == 0 else "#222222"
            is_selected = (self.selected_pkg_name == pkg['name'])
            current_bg = "#1f538d" if is_selected else bg_color
            
            row = ctk.CTkFrame(self.pkg_scroll, fg_color=current_bg, corner_radius=5)
            row.pack(fill="x", pady=2, padx=2)
            
            if is_selected:
                self.selected_row_frame = row
            row._orig_bg = bg_color
            
            lbl_name = ctk.CTkLabel(row, text=pkg['name'], font=ctk.CTkFont(size=14, weight="bold"), anchor="w", width=200)
            lbl_name.pack(side="left", padx=(20, 10), pady=8)
            
            lbl_version = ctk.CTkLabel(row, text=pkg['version'], font=ctk.CTkFont(size=13), anchor="w", width=100)
            lbl_version.pack(side="left", padx=10, pady=8)
            
            lbl_size = ctk.CTkLabel(row, text=pkg['size'], font=ctk.CTkFont(size=13), text_color="#a0a0a0", anchor="w", width=100)
            lbl_size.pack(side="left", padx=10, pady=8)
            
            lbl_date = ctk.CTkLabel(row, text=pkg['date'], font=ctk.CTkFont(size=13), text_color="#a0a0a0", anchor="w", width=140)
            lbl_date.pack(side="left", padx=10, pady=8)
            
            def on_click(e, name=pkg['name'], r=row):
                if self.selected_row_frame:
                    try: self.selected_row_frame.configure(fg_color=self.selected_row_frame._orig_bg)
                    except: pass
                self.selected_row_frame = r
                self.selected_pkg_name = name
                r.configure(fg_color="#1f538d")
                self.set_detail_text(f"正在从 PyPI 获取 {name} 的详细信息...")
                self.executor.submit(self._fetch_pypi, name)
                
            def on_enter(e, r=row):
                if r != self.selected_row_frame:
                    r.configure(fg_color="#3a3a3a")
            def on_leave(e, r=row):
                if r != self.selected_row_frame:
                    r.configure(fg_color=r._orig_bg)
                    
            for w in (row, lbl_name, lbl_version, lbl_size, lbl_date):
                w.bind("<Button-1>", on_click)
                w.bind("<Enter>", lambda e, r=row: on_enter(e, r))
                w.bind("<Leave>", lambda e, r=row: on_leave(e, r))

    def _fetch_pypi(self, name):
        text = "获取失败或此包非标准 PyPI 包。"
        try:
            url = f"https://pypi.org/pypi/{name}/json"
            with urllib.request.urlopen(url, timeout=3) as res:
                if res.status == 200:
                    info = json.loads(res.read().decode())['info']
                    text = f"名称: {info.get('name')}\n作者: {info.get('author')}\n主页: {info.get('home_page')}\n简介: {info.get('summary')}"
        except: pass
        self.after(0, lambda: self.set_detail_text(text))

    def set_detail_text(self, text):
        self.detail_text.configure(state=tk.NORMAL)
        self.detail_text.delete(1.0, tk.END)
        self.detail_text.insert(tk.END, text)
        self.detail_text.configure(state=tk.DISABLED)

    def install_package(self):
        pkg = self.pkg_entry.get().strip()
        if not self.current_python or not pkg: return
        self._run_pip(["install", pkg], f"安装 {pkg}")

    def uninstall_package(self):
        if not self.selected_pkg_name: return
        pkg = self.selected_pkg_name
        if messagebox.askyesno("确认", f"确定要卸载 {pkg} 吗？"):
            self._run_pip(["uninstall", "-y", pkg], f"卸载 {pkg}")

    def _run_pip(self, args, op_name):
        self.install_btn.configure(state="disabled")
        self.uninstall_btn.configure(state="disabled")
        self.set_detail_text(f"正在执行: {op_name} ...")
        def task():
            try:
                cmd = [self.current_python, "-m", "pip"] + args
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', startupinfo=startupinfo)
                out, err = process.communicate()
                is_ok = process.returncode == 0
                msg = f"{op_name} {'成功' if is_ok else '失败'}\n\n[终端输出]:\n{out}\n{err}"
                self.after(0, lambda: self.set_detail_text(msg))
                if is_ok: self.after(0, self.refresh_packages)
            except Exception as e:
                self.after(0, lambda: self.set_detail_text(f"执行错误: {str(e)}"))
            finally:
                self.after(0, lambda: self.install_btn.configure(state="normal"))
                self.after(0, lambda: self.uninstall_btn.configure(state="normal"))
        threading.Thread(target=task, daemon=True).start()

    def export_requirements(self):
        if not self.current_python or not self.installed_packages:
            messagebox.showinfo("提示", "请先选择环境并加载包列表")
            return
        from tkinter import filedialog
        save_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt")],
            initialfile="requirements.txt"
        )
        if not save_path: return
        # 获取当前 Python 版本号
        py_version = "unknown"
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            r = subprocess.run([self.current_python, '--version'], capture_output=True, text=True, startupinfo=startupinfo)
            out = r.stdout.strip() or r.stderr.strip()
            if out.startswith("Python "): py_version = out.split(" ")[1]
        except: pass
        lines = [
            f"# Python {py_version} — requirements.txt",
            f"# 生成自: {self.current_python}",
            f"# 一键安装: pip install -r requirements.txt",
            ""
        ]
        for pkg in sorted(self.installed_packages, key=lambda x: x['name'].lower()):
            lines.append(f"{pkg['name']}=={pkg['version']}")
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        messagebox.showinfo("成功", f"已导出 {len(self.installed_packages)} 个包到:\n{save_path}")
        self.set_detail_text(f"已导出 requirements.txt → {save_path}")

    # ==========================
    # Tab 2: 环境部署 (在线安装/卸载/默认配置)
    # ==========================
    def setup_install_tab(self):
        self.deploy_split_frame = ctk.CTkFrame(self.tab_install, fg_color="transparent")
        self.deploy_split_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 左侧：可安装版本
        self.online_frame = ctk.CTkFrame(self.deploy_split_frame)
        self.online_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ctk.CTkLabel(self.online_frame, text="云端可安装版本", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.online_scroll = ctk.CTkScrollableFrame(self.online_frame)
        self.online_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        self.online_loading_label = ctk.CTkLabel(self.online_scroll, text="正在获取列表...")
        self.online_loading_label.pack(pady=20)

        # 右侧：已安装版本
        self.installed_frame = ctk.CTkFrame(self.deploy_split_frame)
        self.installed_frame.pack(side="right", fill="both", expand=True, padx=(10, 0))
        ctk.CTkLabel(self.installed_frame, text="本机已安装版本", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.installed_scroll = ctk.CTkScrollableFrame(self.installed_frame)
        self.installed_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        self.installed_loading_label = ctk.CTkLabel(self.installed_scroll, text="等待扫描...")
        self.installed_loading_label.pack(pady=20)

        # 安装选项区
        opt_frame = ctk.CTkFrame(self.tab_install, fg_color="#2b2b2b", corner_radius=5)
        opt_frame.pack(fill="x", padx=10, pady=(5, 0))
        ctk.CTkLabel(opt_frame, text="安装选项:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10, pady=8)
        self.install_all_users = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(opt_frame, text="为所有用户安装 (需要管理员权限)", variable=self.install_all_users).pack(side="left", padx=10, pady=8)
        self.install_silent = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(opt_frame, text="静默安装 (无界面)", variable=self.install_silent).pack(side="left", padx=10, pady=8)

        self.install_console = ctk.CTkTextbox(self.tab_install, height=120)
        self.install_console.pack(padx=10, pady=(0, 10), fill="x")

    def fetch_online_versions_async(self):
        def fetch_task():
            url = "https://www.python.org/ftp/python/"
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                response = urllib.request.urlopen(req, timeout=10)
                html = response.read().decode('utf-8')
                versions = set(re.findall(r'<a href="(\d+\.\d+\.\d+)/">', html))
                valid_versions = sorted(
                    [v for v in versions if _version_key(v) >= (3, 6, 0)],
                    key=_version_key, reverse=True
                )
                self.after(0, self._update_online_versions_ui, valid_versions)
            except Exception as e:
                self.after(0, lambda: ctk.CTkLabel(self.online_scroll, text=f"获取失败: {str(e)}").pack(pady=20))
        threading.Thread(target=fetch_task, daemon=True).start()

    def _update_online_versions_ui(self, valid_versions):
        for widget in self.online_scroll.winfo_children(): widget.destroy()
        for v in valid_versions:
            frame = ctk.CTkFrame(self.online_scroll, fg_color="#2b2b2b", corner_radius=5)
            frame.pack(fill="x", padx=5, pady=5)
            ctk.CTkLabel(frame, text=f"Python {v}", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10, pady=5)
            btn = ctk.CTkButton(frame, text="下载并安装", width=80, fg_color="#1f538d", hover_color="#14375e", command=lambda ver=v: self.deploy_version(ver))
            btn.pack(side="right", padx=10, pady=5)

    def _find_installer_url(self, version):
        """探测FTP目录，找到实际可用的安装包文件名"""
        base_url = f"https://www.python.org/ftp/python/{version}/"
        try:
            req = urllib.request.Request(base_url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=10)
            html = resp.read().decode('utf-8')
            # 优先顺序: amd64.exe > .exe > -webinstall
            candidates = [
                f"python-{version}-amd64.exe",
                f"python-{version}.exe",
                f"python-{version}-win_amd64.exe",
            ]
            for name in candidates:
                if name in html:
                    return base_url + name, name
            # 回退: 用正则找任意 .exe (排除 webinstall)
            exes = re.findall(r'href="(python-[^"]+\.exe)"', html)
            exes = [e for e in exes if 'webinstall' not in e.lower()]
            if exes:
                return base_url + exes[0], exes[0]
        except:
            pass
        return None, None

    def deploy_version(self, version):
        def install_task():
            installer_path = None
            try:
                self.install_console.insert("end", f"> 正在查找 Python {version} 安装包...\n")
                self.install_console.see("end")
                installer_url, filename = self._find_installer_url(version)
                if not installer_url:
                    self.install_console.insert("end", f"[错误] 未找到 Python {version} 的 Windows 安装包。\n该版本可能不提供 Windows 安装程序，请尝试其他版本。\n")
                    self.install_console.see("end")
                    return
                installer_path = os.path.join(tempfile.gettempdir(), filename)
                self.install_console.insert("end", f"> 开始下载 {filename} ...\n")
                self.install_console.see("end")
                urllib.request.urlretrieve(installer_url, installer_path)
                self.install_console.insert("end", f"> 下载完成，开始安装...\n")
                self.install_console.see("end")
                
                all_users = self.install_all_users.get()
                silent = self.install_silent.get()
                
                cmd = [installer_path]
                if silent:
                    cmd.append("/quiet")
                else:
                    cmd.append("/passive")  # 显示进度界面但无需用户操作
                
                cmd.append(f"InstallAllUsers={'1' if all_users else '0'}")
                cmd.append("PrependPath=0")
                cmd.append("Include_test=0")
                
                mode_desc = ("全局" if all_users else "当前用户") + " | " + ("静默" if silent else "可视")
                self.install_console.insert("end", f"> 安装模式: {mode_desc}\n")
                self.install_console.see("end")
                
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding=SYS_ENCODING, errors='replace', startupinfo=startupinfo)
                process.wait()
                self.install_console.insert("end", f"--- 安装完成 ---\n")
                self.install_console.see("end")
                self.auto_scan_environments()
            except Exception as e:
                self.install_console.insert("end", f"[安装错误] {str(e)}\n")
            finally:
                if installer_path and os.path.exists(installer_path):
                    try: os.remove(installer_path)
                    except: pass
        threading.Thread(target=install_task, daemon=True).start()

    def update_installed_versions_ui(self):
        for widget in self.installed_scroll.winfo_children(): widget.destroy()
        if not self.installed_versions:
            ctk.CTkLabel(self.installed_scroll, text="未检测到已安装版本").pack(pady=20)
            return
        sorted_versions = sorted(self.installed_versions.keys(), key=_version_key, reverse=True)
        for v in sorted_versions:
            frame = ctk.CTkFrame(self.installed_scroll, fg_color="#2b2b2b", corner_radius=5)
            frame.pack(fill="x", padx=5, pady=5)
            ctk.CTkLabel(frame, text=f"Python {v}", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10, pady=5)
            btn_uninstall = ctk.CTkButton(frame, text="卸载", width=60, fg_color="#8B0000", hover_color="#5c0000", command=lambda ver=v: self.remove_version(ver))
            btn_uninstall.pack(side="right", padx=(5, 10), pady=5)
            btn_default = ctk.CTkButton(frame, text="设为默认", width=80, fg_color="#2b7b50", hover_color="#1d5c39", command=lambda ver=v: self.set_global_default_version(ver))
            btn_default.pack(side="right", padx=5, pady=5)

    def remove_version(self, version):
        if not messagebox.askyesno("确认卸载", f"确定要卸载 Python {version} 吗？"): return
        def uninstall_task():
            installer_path = None
            try:
                self.install_console.insert("end", f"> 正在查找 Python {version} 安装包...\n")
                self.install_console.see("end")
                installer_url, filename = self._find_installer_url(version)
                if not installer_url:
                    self.install_console.insert("end", f"[错误] 未找到 Python {version} 的安装包，无法执行卸载。\n")
                    self.install_console.see("end")
                    return
                installer_path = os.path.join(tempfile.gettempdir(), filename)
                self.install_console.insert("end", f"> 下载 {filename} 用于卸载...\n")
                self.install_console.see("end")
                urllib.request.urlretrieve(installer_url, installer_path)
                self.install_console.insert("end", f"> 开始静默卸载...\n")
                self.install_console.see("end")
                cmd = [installer_path, "/uninstall", "/quiet"]
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding=SYS_ENCODING, errors='replace', startupinfo=startupinfo)
                process.wait()
                self.install_console.insert("end", f"--- 卸载完成 ---\n")
                self.install_console.see("end")
                self.after(0, self._reset_and_scan)
            except Exception as e:
                self.install_console.insert("end", f"[卸载错误] {str(e)}\n")
            finally:
                if installer_path and os.path.exists(installer_path):
                    try: os.remove(installer_path)
                    except: pass
        threading.Thread(target=uninstall_task, daemon=True).start()

    def set_global_default_version(self, version):
        path = self.installed_versions.get(version)
        if not path: return
        if not messagebox.askyesno("确认", f"确定要将 Python {version} 设置为全局默认环境吗？\n(这将会修改系统环境变量 PATH)"): return
        python_dir = os.path.dirname(path)
        scripts_dir = os.path.join(python_dir, "Scripts")
        def set_default_task():
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Environment', 0, winreg.KEY_ALL_ACCESS)
                try: current_path, _ = winreg.QueryValueEx(key, 'Path')
                except FileNotFoundError: current_path = ""
                path_list = [p for p in current_path.split(';') if p]
                path_list = [p for p in path_list if p.lower() != python_dir.lower() and p.lower() != scripts_dir.lower()]
                path_list.insert(0, scripts_dir)
                path_list.insert(0, python_dir)
                winreg.SetValueEx(key, 'Path', 0, winreg.REG_EXPAND_SZ, ';'.join(path_list))
                winreg.SetValueEx(key, 'PY_PYTHON', 0, winreg.REG_SZ, version)
                winreg.CloseKey(key)
                
                HWND_BROADCAST = 0xFFFF
                WM_SETTINGCHANGE = 0x001A
                SMTO_ABORTIFHUNG = 0x0002
                result = ctypes.c_long()
                ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, 'Environment', SMTO_ABORTIFHUNG, 5000, ctypes.byref(result))
                self.after(0, lambda: messagebox.showinfo("成功", f"已成功将 Python {version} 设置为全局默认！\n(新的终端窗口或IDE重启后即可生效)"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("错误", f"设置失败: {str(e)}\n请尝试以管理员身份运行本程序。"))
        threading.Thread(target=set_default_task, daemon=True).start()

    # ==========================
    # Tab 3: 虚拟环境
    # ==========================
    def setup_venv_tab(self):
        title = ctk.CTkLabel(self.tab_venv, text="全局共用虚拟环境配置", font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(pady=(20, 10))
        desc = ctk.CTkLabel(self.tab_venv, text="为您所有的 IDE (如 PyCharm, VSCode) 提供一个统一的、包含常用库的虚拟环境。\n避免每个项目重复下载相同的包，节省空间。", text_color="gray")
        desc.pack(pady=(0, 20))

        form_frame = ctk.CTkFrame(self.tab_venv, fg_color="transparent")
        form_frame.pack(fill="x", padx=40)
        ctk.CTkLabel(form_frame, text="基础解释器:").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        self.venv_base_menu = ctk.CTkOptionMenu(form_frame, values=["请先添加解释器"], width=400)
        self.venv_base_menu.grid(row=0, column=1, padx=10, pady=10, sticky="w")

        ctk.CTkLabel(form_frame, text="虚拟环境存放路径:").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        default_venv_path = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), "GlobalPythonVenv")
        self.venv_path_entry = ctk.CTkEntry(form_frame, width=400)
        self.venv_path_entry.insert(0, default_venv_path)
        self.venv_path_entry.grid(row=1, column=1, padx=10, pady=10, sticky="w")

        self.create_venv_btn = ctk.CTkButton(form_frame, text="一键创建 / 重置虚拟环境", command=self.create_global_venv, fg_color="#1f538d", hover_color="#14375e")
        self.create_venv_btn.grid(row=2, column=1, padx=10, pady=20, sticky="w")

        res_frame = ctk.CTkFrame(self.tab_venv, fg_color="transparent")
        res_frame.pack(fill="x", padx=40, pady=10)
        ctk.CTkLabel(res_frame, text="虚拟环境 Python 路径 (供 IDE 使用):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10)
        path_copy_frame = ctk.CTkFrame(res_frame, fg_color="transparent")
        path_copy_frame.pack(fill="x", padx=10, pady=5)
        self.venv_result_entry = ctk.CTkEntry(path_copy_frame, width=450, state="readonly")
        self.venv_result_entry.pack(side="left", padx=(0, 10))
        self.copy_btn = ctk.CTkButton(path_copy_frame, text="复制路径", width=100, command=self.copy_venv_path)
        self.copy_btn.pack(side="left")

        self.venv_console = ctk.CTkTextbox(self.tab_venv, height=120)
        self.venv_console.pack(padx=50, pady=20, fill="both", expand=True)

    def copy_venv_path(self):
        path = self.venv_result_entry.get()
        if path:
            self.clipboard_clear()
            self.clipboard_append(path)
            messagebox.showinfo("成功", "路径已复制到剪贴板！\n请在 PyCharm 或 VSCode 中将此路径设置为 Python Interpreter。")

    def create_global_venv(self):
        base_python = self.venv_base_menu.get()
        target_dir = self.venv_path_entry.get().strip()
        if not base_python or base_python == "请先添加解释器": return
        if not target_dir: return

        def venv_task():
            self.create_venv_btn.configure(state="disabled")
            self.venv_console.insert("end", f"> 开始在 {target_dir} 创建虚拟环境...\n")
            self.venv_console.see("end")
            cmd = [base_python, "-m", "venv", target_dir]
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', startupinfo=startupinfo)
                for line in process.stdout: self.venv_console.insert("end", line)
                for line in process.stderr: self.venv_console.insert("end", line)
                process.wait()
                if process.returncode == 0:
                    self.venv_console.insert("end", f"--- 虚拟环境创建成功！---\n")
                    venv_py_path = os.path.join(target_dir, "Scripts", "python.exe")
                    self.venv_result_entry.configure(state="normal")
                    self.venv_result_entry.delete(0, 'end')
                    self.venv_result_entry.insert(0, venv_py_path)
                    self.venv_result_entry.configure(state="readonly")
                else:
                    self.venv_console.insert("end", f"--- 虚拟环境创建失败 (退出码 {process.returncode}) ---\n")
            except Exception as e:
                self.venv_console.insert("end", f"[错误] {str(e)}\n")
            finally:
                self.create_venv_btn.configure(state="normal")
                self.venv_console.see("end")
        threading.Thread(target=venv_task, daemon=True).start()

    # ==========================
    # 核心路径与环境扫描逻辑
    # ==========================
    def add_python_path(self):
        path = self.path_entry.get().strip()
        if not path or not os.path.exists(path) or not path.lower().endswith("python.exe"):
            messagebox.showerror("错误", "请输入有效的 python.exe 绝对路径")
            return
        self._add_path_to_list(path)
        self.path_entry.delete(0, 'end')
        self._extract_and_record_version(path)
        self.update_installed_versions_ui()

    def _add_path_to_list(self, path):
        if path not in self.python_paths:
            self.python_paths.append(path)
            self.env_listbox.configure(values=self.python_paths)
            self.venv_base_menu.configure(values=self.python_paths)
            if self.current_python is None or self.current_python not in self.python_paths:
                self.env_listbox.set(path)
                self.venv_base_menu.set(path)
                self.select_env(path)

    def select_env(self, selected_path):
        if selected_path == "请先添加解释器" or not selected_path: return
        self.current_python = selected_path
        self.refresh_packages()

    def _extract_and_record_version(self, path):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run([path, '--version'], capture_output=True, text=True, encoding='utf-8', errors='replace', startupinfo=startupinfo)
            out = result.stdout.strip() or result.stderr.strip()
            if out.startswith("Python "):
                version = out.split(" ")[1]
                self.installed_versions[version] = path
        except: pass

    def auto_scan_environments(self):
        def scan_task():
            paths = set()
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    key = winreg.OpenKey(hive, r'Software\Python\PythonCore')
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        version = winreg.EnumKey(key, i)
                        try:
                            path_key = winreg.OpenKey(key, version + r'\InstallPath')
                            path = winreg.QueryValue(path_key, None)
                            if path:
                                exe_path = os.path.join(path, 'python.exe')
                                if os.path.exists(exe_path): paths.add(exe_path)
                        except: pass
                except: pass
            
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                result = subprocess.run(['py', '-0p'], capture_output=True, text=True, encoding=SYS_ENCODING, errors='replace', startupinfo=startupinfo)
                for line in result.stdout.split('\n'):
                    parts = line.strip().split()
                    if len(parts) >= 2 and parts[-1].lower().endswith('python.exe') and os.path.exists(parts[-1]):
                        paths.add(parts[-1])
            except: pass

            for p in paths: self._extract_and_record_version(p)
            self.after(0, self._update_paths_ui, list(paths))
        threading.Thread(target=scan_task, daemon=True).start()

    def _update_paths_ui(self, paths):
        for p in paths:
            if p not in self.python_paths:
                self.python_paths.append(p)
        if self.python_paths:
            self.env_listbox.configure(values=self.python_paths)
            self.venv_base_menu.configure(values=self.python_paths)
            if not self.current_python or self.current_python == "请先添加解释器":
                self.env_listbox.set(self.python_paths[0])
                self.venv_base_menu.set(self.python_paths[0])
                self.select_env(self.python_paths[0])
            else:
                self.env_listbox.set(self.current_python)
        self.update_installed_versions_ui()

    def _reset_and_scan(self):
        self.python_paths.clear()
        self.installed_versions.clear()
        self.current_python = None
        self.env_listbox.configure(values=["请先添加解释器"])
        self.env_listbox.set("请先添加解释器")
        self.venv_base_menu.configure(values=["请先添加解释器"])
        self.venv_base_menu.set("请先添加解释器")
        
        self.selected_pkg_name = None
        self.selected_row_frame = None
        for widget in self.pkg_scroll.winfo_children(): widget.destroy()
        
        self.detail_text.configure(state=tk.NORMAL)
        self.detail_text.delete(1.0, tk.END)
        self.detail_text.configure(state=tk.DISABLED)
        self.update_installed_versions_ui()
        self.auto_scan_environments()

    # ==========================
    # Tab 4: 打包工具 (PyInstaller + 代码清洗)
    # ==========================
    def setup_pack_tab(self):
        self.pack_main_script = tk.StringVar()
        self.pack_output_name = tk.StringVar()
        self.pack_icon_path = tk.StringVar()
        self.pack_mode = tk.StringVar(value="single_dir")
        self.pack_console = tk.BooleanVar(value=False)
        self.pack_upx = tk.BooleanVar(value=False)

        # 内部分栅 Tabview
        self.pack_tabview = ctk.CTkTabview(self.tab_pack, height=30)
        self.pack_tabview.pack(fill="both", expand=True, padx=5, pady=5)
        self.pack_config_tab = self.pack_tabview.add("⚙️ 打包配置")
        self.pack_log_tab = self.pack_tabview.add("📝 执行日志")
        self.pack_clean_tab = self.pack_tabview.add("🧹 代码清洗")

        self._init_pack_config_tab()
        self._init_pack_log_tab()
        self._init_pack_clean_tab()

    def _init_pack_config_tab(self):
        tab = self.pack_config_tab
        # 入口脚本
        row1 = ctk.CTkFrame(tab, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(row1, text="入口脚本(.py):").pack(side="left", padx=5)
        ctk.CTkEntry(row1, textvariable=self.pack_main_script, width=350).pack(side="left", padx=5, fill="x", expand=True)
        ctk.CTkButton(row1, text="浏览...", width=60, command=self._select_main_script).pack(side="left", padx=5)

        # 输出名称
        row2 = ctk.CTkFrame(tab, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(row2, text="生成文件名:").pack(side="left", padx=5)
        ctk.CTkEntry(row2, textvariable=self.pack_output_name, width=200).pack(side="left", padx=5)

        # 图标
        row3 = ctk.CTkFrame(tab, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(row3, text="自定义图标(.ico):").pack(side="left", padx=5)
        ctk.CTkEntry(row3, textvariable=self.pack_icon_path, width=300).pack(side="left", padx=5, fill="x", expand=True)
        ctk.CTkButton(row3, text="浏览...", width=60, command=self._select_icon).pack(side="left", padx=5)

        # 打包参数
        opt_frame = ctk.CTkFrame(tab, fg_color="#2b2b2b", corner_radius=5)
        opt_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(opt_frame, text="打包模式:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
        mode_row = ctk.CTkFrame(opt_frame, fg_color="transparent")
        mode_row.pack(fill="x", padx=10, pady=5)
        ctk.CTkRadioButton(mode_row, text="单文件 (.exe)", variable=self.pack_mode, value="single_file").pack(side="left", padx=10)
        ctk.CTkRadioButton(mode_row, text="文件夹 (推荐)", variable=self.pack_mode, value="single_dir").pack(side="left", padx=10)
        ctk.CTkRadioButton(mode_row, text="两种都生成", variable=self.pack_mode, value="both").pack(side="left", padx=10)

        chk_row = ctk.CTkFrame(opt_frame, fg_color="transparent")
        chk_row.pack(fill="x", padx=10, pady=(5, 10))
        ctk.CTkCheckBox(chk_row, text="显示控制台窗口 (Debug)", variable=self.pack_console).pack(side="left", padx=10)
        ctk.CTkCheckBox(chk_row, text="UPX压缩", variable=self.pack_upx).pack(side="left", padx=10)

        # 资源文件列表
        res_frame = ctk.CTkFrame(tab, fg_color="#2b2b2b", corner_radius=5)
        res_frame.pack(fill="both", expand=True, padx=10, pady=5)
        ctk.CTkLabel(res_frame, text="资源文件 (图片/DLL/配置):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        self.res_scroll = ctk.CTkScrollableFrame(res_frame, fg_color="transparent", height=80)
        self.res_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        res_btn_row = ctk.CTkFrame(res_frame, fg_color="transparent")
        res_btn_row.pack(fill="x", padx=5, pady=5)
        ctk.CTkButton(res_btn_row, text="+ 添加文件", width=80, command=self._add_res_file).pack(side="left", padx=5)
        ctk.CTkButton(res_btn_row, text="+ 添加文件夹", width=80, command=self._add_res_folder).pack(side="left", padx=5)
        ctk.CTkButton(res_btn_row, text="清空", width=60, fg_color="#8B0000", hover_color="#5c0000", command=self._clear_res).pack(side="left", padx=5)

        # 底部按钮
        bot = ctk.CTkFrame(tab, fg_color="transparent")
        bot.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(bot, text="🧹 清理临时文件", width=120, command=self._clean_temp).pack(side="left", padx=5)
        ctk.CTkButton(bot, text="🚀 开始打包", width=120, fg_color="#2b7b50", hover_color="#1d5c39", command=self._start_pack).pack(side="right", padx=5)

    def _init_pack_log_tab(self):
        self.pack_log_text = ctk.CTkTextbox(self.pack_log_tab, fg_color="#1a1a1a")
        self.pack_log_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.pack_progress = ctk.CTkProgressBar(self.pack_log_tab)
        self.pack_progress.pack(fill="x", padx=10, pady=5)
        self.pack_progress.set(0)

    def _init_pack_clean_tab(self):
        tab = self.pack_clean_tab
        ctk.CTkLabel(tab, text="ℹ️ 安全清洗：生成 '_clean.py' 新文件，仅删除 '#' 注释和多余空行。", text_color="gray").pack(anchor="w", padx=10, pady=5)

        split = ctk.CTkFrame(tab, fg_color="transparent")
        split.pack(fill="both", expand=True, padx=5, pady=5)

        left = ctk.CTkFrame(split)
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))
        ctk.CTkLabel(left, text="待处理文件列表", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.clean_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.clean_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        clean_btn_row = ctk.CTkFrame(left, fg_color="transparent")
        clean_btn_row.pack(fill="x", padx=5, pady=5)
        ctk.CTkButton(clean_btn_row, text="+ 添加文件", width=80, command=self._add_clean_file).pack(side="left", padx=5)
        ctk.CTkButton(clean_btn_row, text="清空", width=60, fg_color="#8B0000", hover_color="#5c0000", command=self._clear_clean_list).pack(side="left", padx=5)

        right = ctk.CTkFrame(split)
        right.pack(side="right", fill="both", expand=True, padx=(5, 0))
        ctk.CTkLabel(right, text="处理日志", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.clean_log_text = ctk.CTkTextbox(right, fg_color="#1a1a1a")
        self.clean_log_text.pack(fill="both", expand=True, padx=5, pady=5)

        self.clean_option_empty = tk.BooleanVar(value=True)
        bot = ctk.CTkFrame(tab, fg_color="transparent")
        bot.pack(fill="x", padx=10, pady=5)
        ctk.CTkCheckBox(bot, text="删除多余空行", variable=self.clean_option_empty).pack(side="left", padx=10)
        ctk.CTkButton(bot, text="🚀 开始清洗", width=120, fg_color="#2b7b50", hover_color="#1d5c39", command=self._start_clean).pack(side="right", padx=10)

    # --- 打包工具功能函数 ---
    def _select_main_script(self):
        from tkinter import filedialog
        p = filedialog.askopenfilename(filetypes=[("Python", "*.py")])
        if p:
            self.pack_main_script.set(p)
            if not self.pack_output_name.get():
                self.pack_output_name.set(os.path.splitext(os.path.basename(p))[0])

    def _select_icon(self):
        from tkinter import filedialog
        p = filedialog.askopenfilename(filetypes=[("Icon", "*.ico")])
        if p: self.pack_icon_path.set(p)

    def _add_res_file(self):
        from tkinter import filedialog
        fs = filedialog.askopenfilenames()
        for f in fs:
            if f not in self.resource_files:
                self.resource_files.append(f)
                ctk.CTkLabel(self.res_scroll, text=f, anchor="w").pack(fill="x", padx=5)

    def _add_res_folder(self):
        from tkinter import filedialog
        d = filedialog.askdirectory()
        if d and d not in self.resource_files:
            self.resource_files.append(d)
            ctk.CTkLabel(self.res_scroll, text=d, anchor="w").pack(fill="x", padx=5)

    def _clear_res(self):
        self.resource_files.clear()
        for w in self.res_scroll.winfo_children(): w.destroy()

    def _clean_temp(self, silent=False):
        script = self.pack_main_script.get()
        if not script: return
        d = os.path.dirname(script)
        for x in ['build', 'dist', '__pycache__']:
            p = os.path.join(d, x)
            if os.path.exists(p): shutil.rmtree(p, ignore_errors=True)
        name = self.pack_output_name.get()
        if name:
            spec = os.path.join(d, name + ".spec")
            if os.path.exists(spec):
                try: os.remove(spec)
                except: pass
        if not silent:
            messagebox.showinfo("完成", "临时文件已清理")

    def _start_pack(self):
        if not self.pack_main_script.get():
            return messagebox.showerror("错误", "未选择入口脚本")
        # 检查 PyInstaller
        py = self.current_python or sys.executable
        self.pack_tabview.set("📝 执行日志")
        self.pack_log_text.delete(1.0, tk.END)
        self.pack_progress.set(0)
        threading.Thread(target=self._pack_thread, args=(py,), daemon=True).start()

    def _pack_thread(self, interpreter):
        self._clean_temp(silent=True)
        script = self.pack_main_script.get()
        name = self.pack_output_name.get() or os.path.splitext(os.path.basename(script))[0]
        script_dir = os.path.dirname(os.path.abspath(script))

        mode = self.pack_mode.get()
        modes = []
        if mode == 'single_file': modes = ['--onefile']
        elif mode == 'single_dir': modes = ['--onedir']
        elif mode == 'both': modes = ['--onedir', '--onefile']

        for idx, current_mode in enumerate(modes):
            self.log_queue.put(f"\n>>> 正在启动第 {idx+1}/{len(modes)} 步: {current_mode} ...\n")
            cmd = [
                interpreter, "-m", "PyInstaller", script,
                "--noconfirm", "--clean", f"--name={name}",
                f"--distpath={os.path.join(script_dir, 'dist')}",
                f"--workpath={os.path.join(script_dir, 'build')}",
                f"--specpath={script_dir}", current_mode,
            ]
            if not self.pack_console.get(): cmd.append("--noconsole")
            if not self.pack_upx.get(): cmd.append("--noupx")
            icon = self.pack_icon_path.get()
            if icon and os.path.exists(icon): cmd.append(f"--icon={icon}")
            sep = ";" if os.name == 'nt' else ":"
            for r in self.resource_files:
                if os.path.exists(r):
                    dest = "." if os.path.isfile(r) else os.path.basename(r)
                    cmd.append(f"--add-data={r}{sep}{dest}")

            if not self._run_pack_cmd(cmd):
                self.log_queue.put("\n❌ 失败终止。\n")
                return

        self.after(0, lambda: self.pack_progress.set(1.0))
        dist_path = os.path.join(script_dir, 'dist')
        self.log_queue.put(f"\n✅ 任务完成！输出目录: {dist_path}\n")
        self.after(0, lambda: messagebox.showinfo("成功", f"打包完成！\n路径: {dist_path}"))
        try: os.startfile(dist_path)
        except: pass

    def _run_pack_cmd(self, cmd):
        try:
            clean_env = os.environ.copy()
            for key in ['TCL_LIBRARY', 'TK_LIBRARY', '_MEIPASS2']:
                clean_env.pop(key, None)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self.log_queue.put(f"Cmd: {' '.join(cmd)}\n")
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding=SYS_ENCODING, errors='replace', startupinfo=startupinfo, env=clean_env)
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None: break
                if line: self.log_queue.put(line)
            return process.poll() == 0
        except Exception as e:
            self.log_queue.put(f"Error: {e}\n")
            return False

    # --- 代码清洗 ---
    def _add_clean_file(self):
        from tkinter import filedialog
        fs = filedialog.askopenfilenames(filetypes=[("Python", "*.py")])
        for f in fs:
            if f not in self.clean_files:
                self.clean_files.append(f)
                ctk.CTkLabel(self.clean_scroll, text=os.path.basename(f), anchor="w").pack(fill="x", padx=5, pady=2)

    def _clear_clean_list(self):
        self.clean_files.clear()
        for w in self.clean_scroll.winfo_children(): w.destroy()

    def _start_clean(self):
        if not self.clean_files:
            return messagebox.showinfo("提示", "请先添加文件")
        self.clean_log_text.delete(1.0, tk.END)
        threading.Thread(target=self._clean_thread, daemon=True).start()

    def _clean_thread(self):
        total = len(self.clean_files)
        success = 0
        self.clean_log_queue.put(f"开始批量处理 {total} 个文件...\n")
        for idx, fpath in enumerate(self.clean_files):
            try:
                self.clean_log_queue.put(f"[{idx+1}/{total}] {os.path.basename(fpath)} ... ")
                new_path = self._clean_single_file(fpath)
                if new_path:
                    self.clean_log_queue.put("✅ 成功\n")
                    success += 1
            except Exception as e:
                self.clean_log_queue.put(f"❌ 失败: {str(e)}\n")
        self.clean_log_queue.put(f"\n完成！成功 {success}/{total}。\n")
        self.after(0, lambda: messagebox.showinfo("完成", "批量清洗完成！"))

    def _clean_single_file(self, source_path):
        base, ext = os.path.splitext(source_path)
        new_path = f"{base}_clean{ext}"
        with open(source_path, 'rb') as f:
            tokens = list(tokenize.tokenize(f.readline))
            src_encoding = 'utf-8'
            if tokens and tokens[0].type == tokenize.ENCODING:
                src_encoding = tokens[0].string
        out_tokens = [t for t in tokens if t.type != tokenize.COMMENT]
        cleaned_bytes = tokenize.untokenize(out_tokens)
        cleaned_code = cleaned_bytes.decode(src_encoding)
        if self.clean_option_empty.get():
            lines = cleaned_code.splitlines()
            final_lines, blank_count = [], 0
            for line in lines:
                if not line.strip():
                    blank_count += 1
                    if blank_count > 1: continue
                else:
                    blank_count = 0
                final_lines.append(line)
            cleaned_code = "\n".join(final_lines)
        with open(new_path, 'w', encoding=src_encoding) as f:
            f.write(cleaned_code)
        return new_path

    # --- 日志队列轮询 ---
    def _poll_log_queues(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.pack_log_text.insert(tk.END, msg)
                self.pack_log_text.see(tk.END)
        except queue.Empty: pass
        try:
            while True:
                msg = self.clean_log_queue.get_nowait()
                self.clean_log_text.insert(tk.END, msg)
                self.clean_log_text.see(tk.END)
        except queue.Empty: pass
        self.after(100, self._poll_log_queues)

if __name__ == "__main__":
    app = PythonEnvManager()
    app.mainloop()
