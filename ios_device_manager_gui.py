import os
import sys
import json
import threading
import subprocess
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.installation_proxy import InstallationProxyService
    from pymobiledevice3.services.house_arrest import HouseArrestService
except ImportError:
    print("缺少依赖库，请在命令行运行: pip install pymobiledevice3")
    sys.exit(1)


# ---------------------------------------------------------------------------
# 跨平台辅助函数 (Windows / macOS / Linux)
# ---------------------------------------------------------------------------
APP_DIR_NAME = "iOSHouseArrestExplorer"
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".ios_housearrest_explorer.json")


def default_temp_dir():
    """默认的“双击预览”落地目录：系统临时目录下的独立子目录（跨平台）。

    旧版本硬编码为 Windows 的 D:\\temp，在 macOS/Linux（甚至没有 D 盘的
    Windows）上都会直接失败。这里改用系统临时目录，并允许用户自定义覆盖。
    """
    return os.path.join(tempfile.gettempdir(), APP_DIR_NAME)


def load_config():
    """读取用户配置（预览目录等）；缺失或损坏时返回空 dict。"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(cfg):
    """写回用户配置；失败返回 False（例如 home 目录不可写）。"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def open_with_default_app(path):
    """用系统默认程序打开文件（跨平台替代 os.startfile）。

    os.startfile 只在 Windows 存在，直接调用会在 macOS/Linux 抛
    AttributeError。这里按平台分派到对应的打开命令。
    """
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]  # 仅 Windows 可用
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=True)
    else:
        subprocess.run(["xdg-open", path], check=True)


class IOSDeviceManager:
    def __init__(self):
        self.lockdown = None
        self.udid = None

    def connect(self):
        try:
            self.lockdown = create_using_usbmux()
            self.udid = self.lockdown.udid
            return True, f"已连接: {self.lockdown.get_value(key='DeviceName')} (iOS {self.lockdown.get_value(key='ProductVersion')})"
        except Exception as e:
            return False, f"连接失败，请确认手机已解锁并信任电脑。错误: {e}"

    def get_file_sharing_apps(self):
        proxy = InstallationProxyService(self.lockdown)
        apps = proxy.get_apps()
        file_sharing_apps = {}
        for bundle_id, app_info in apps.items():
            if app_info.get('UIFileSharingEnabled', False):
                name = app_info.get('CFBundleDisplayName') or app_info.get('CFBundleName', 'Unknown')
                file_sharing_apps[bundle_id] = name
        return file_sharing_apps

    def get_house_arrest_afc(self, bundle_id):
        if not hasattr(HouseArrestService, 'send_command'):
            return None

        original_send_command = HouseArrestService.send_command

        def patched_send_command(self_instance, b_id, cmd="VendContainer"):
            return original_send_command(self_instance, b_id, "VendDocuments")

        HouseArrestService.send_command = patched_send_command
        try:
            afc = HouseArrestService(self.lockdown, bundle_id)
            return afc
        except Exception as e:
            print(f"HouseArrest Error: {e}")
            return None
        finally:
            HouseArrestService.send_command = original_send_command


class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("iOS 共享文件提取器 (HouseArrest)")
        self.root.geometry("1000x600")

        self.manager = IOSDeviceManager()
        self.current_afc = None
        self.apps_dict = {}  # "App Name (BundleID)" -> BundleID
        self.device_info = ""  # 已连接设备的描述，挂载完成后用于恢复状态栏

        # 双击预览的落地目录：可由用户自定义（目录或盘符），持久化到配置文件。
        self.config = load_config()
        self.temp_dir = self.config.get("temp_dir") or default_temp_dir()

        # AFC 底层是单条 socket，pull/listdir/stat 不可并发调用，否则会串包。
        # 所有后台线程访问 AFC 前都必须先拿到这把锁，串行化 socket 读写。
        self.afc_lock = threading.Lock()
        # 快速切换 App 时用于丢弃过期后台结果的令牌。
        self.select_token = 0
        self.export_running = False

        self.setup_ui()
        self.connect_device()

    # ------------------------------------------------------------------ UI
    def setup_ui(self):
        # 顶部菜单栏：设置预览/临时提取目录
        menubar = tk.Menu(self.root)
        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="预览提取目录…", command=self.configure_temp_dir)
        settings_menu.add_command(label="打开当前预览目录", command=self.open_temp_dir)
        menubar.add_cascade(label="设置", menu=settings_menu)
        self.root.config(menu=menubar)

        # 顶部工具栏
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)

        self.lbl_status = ttk.Label(top_frame, text="正在寻找设备...", foreground="blue")
        self.lbl_status.pack(side=tk.LEFT, padx=5)

        ttk.Label(top_frame, text="选择应用:").pack(side=tk.LEFT, padx=(20, 5))
        self.cb_apps = ttk.Combobox(top_frame, state="readonly", width=40)
        self.cb_apps.pack(side=tk.LEFT)
        self.cb_apps.bind("<<ComboboxSelected>>", self.on_app_selected)

        self.btn_refresh = ttk.Button(top_frame, text="刷新应用", command=self.load_apps, state=tk.DISABLED)
        self.btn_refresh.pack(side=tk.LEFT, padx=5)

        # 主内容区分割窗
        self.paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 左侧：文件树
        left_frame = ttk.LabelFrame(self.paned_window, text="设备文件浏览 (双击文件可临时查看)")
        self.paned_window.add(left_frame, weight=3)

        # 定义Treeview
        self.tree_fs = ttk.Treeview(left_frame, columns=("FullPath", "Size", "IsDir"), displaycolumns=("Size",))
        self.tree_fs.heading("#0", text="文件名", anchor=tk.W)
        self.tree_fs.heading("Size", text="大小", anchor=tk.W)
        self.tree_fs.column("#0", width=300)
        self.tree_fs.column("Size", width=80)

        scrollbar_fs = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.tree_fs.yview)
        self.tree_fs.configure(yscroll=scrollbar_fs.set)

        self.tree_fs.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_fs.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree_fs.bind("<<TreeviewOpen>>", self.on_tree_open)
        self.tree_fs.bind("<Double-1>", self.on_tree_double_click)

        # 中间：操作按钮
        mid_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(mid_frame, weight=0)

        self.btn_add = ttk.Button(mid_frame, text="加入导出任务 >>", command=self.add_to_tasks)
        self.btn_add.pack(pady=(100, 10))

        # 右侧：导出任务列表
        right_frame = ttk.LabelFrame(self.paned_window, text="待导出任务列表")
        self.paned_window.add(right_frame, weight=2)

        self.list_tasks = tk.Listbox(right_frame, selectmode=tk.EXTENDED)
        scrollbar_tasks = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.list_tasks.yview)
        self.list_tasks.configure(yscroll=scrollbar_tasks.set)

        self.list_tasks.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_tasks.pack(side=tk.RIGHT, fill=tk.Y)

        # 右侧底部按钮
        right_bottom_frame = ttk.Frame(right_frame)
        right_bottom_frame.pack(fill=tk.X, pady=5)

        self.btn_remove = ttk.Button(right_bottom_frame, text="移除选中", command=self.remove_task)
        self.btn_remove.pack(side=tk.LEFT, padx=5)

        self.btn_clear = ttk.Button(right_bottom_frame, text="清空列表", command=self.clear_tasks)
        self.btn_clear.pack(side=tk.LEFT, padx=5)

        self.btn_export = ttk.Button(right_bottom_frame, text="执行批量导出", command=self.batch_export)
        self.btn_export.pack(side=tk.RIGHT, padx=5)

        # 底部信息栏：显示当前预览提取目录，双击可打开
        bottom_bar = ttk.Frame(self.root, padding=(10, 2))
        bottom_bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(bottom_bar, text="预览目录:").pack(side=tk.LEFT)
        self.lbl_temp_dir = ttk.Label(bottom_bar, text=self.temp_dir, foreground="#555555", cursor="hand2")
        self.lbl_temp_dir.pack(side=tk.LEFT, padx=4)
        self.lbl_temp_dir.bind("<Double-1>", lambda e: self.configure_temp_dir())
        ttk.Button(bottom_bar, text="更改…", command=self.configure_temp_dir).pack(side=tk.RIGHT)

    # ------------------------------------------------- 预览/临时目录设置
    def get_temp_dir(self):
        """返回当前配置的预览提取目录；不可用时回退到系统默认临时目录。"""
        path = self.temp_dir or default_temp_dir()
        try:
            os.makedirs(path, exist_ok=True)
            return path
        except Exception:
            fallback = default_temp_dir()
            os.makedirs(fallback, exist_ok=True)
            return fallback

    def _apply_temp_dir(self, new_dir):
        """校验目录（可创建 + 可写），通过则保存并刷新界面。返回是否成功。"""
        new_dir = os.path.expanduser((new_dir or "").strip())
        if not new_dir:
            new_dir = default_temp_dir()
        new_dir = os.path.normpath(new_dir)
        # 实测可写：创建目录并写一个探针文件
        try:
            os.makedirs(new_dir, exist_ok=True)
            probe = os.path.join(new_dir, ".write_test")
            with open(probe, "w") as f:
                f.write("ok")
            os.remove(probe)
        except Exception as e:
            messagebox.showerror("目录不可用", f"无法写入该目录：\n{new_dir}\n\n{e}")
            return False

        self.temp_dir = new_dir
        self.config["temp_dir"] = new_dir
        if not save_config(self.config):
            messagebox.showwarning("提示", "目录已应用，但配置未能保存（下次启动会恢复默认）。")
        if hasattr(self, "lbl_temp_dir"):
            self.lbl_temp_dir.config(text=new_dir)
        return True

    def configure_temp_dir(self):
        """弹出对话框，允许输入路径/盘符，或浏览选择预览提取目录。"""
        dlg = tk.Toplevel(self.root)
        dlg.title("预览提取目录")
        dlg.geometry("560x180")
        dlg.transient(self.root)
        dlg.grab_set()

        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 560) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 180) // 2
        dlg.geometry(f"+{x}+{y}")

        ttk.Label(dlg, text="双击文件预览时，文件会被提取到此目录（可填目录或盘符，如 D:\\\\ 或 /Volumes/USB）：",
                  wraplength=520, justify=tk.LEFT).pack(anchor=tk.W, padx=15, pady=(15, 8))

        row = ttk.Frame(dlg)
        row.pack(fill=tk.X, padx=15)
        var = tk.StringVar(value=self.temp_dir)
        entry = ttk.Entry(row, textvariable=var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def browse():
            init = var.get() if os.path.isdir(var.get()) else os.path.expanduser("~")
            chosen = filedialog.askdirectory(title="选择预览提取目录", initialdir=init, parent=dlg)
            if chosen:
                var.set(chosen)

        ttk.Button(row, text="浏览…", command=browse).pack(side=tk.LEFT, padx=(6, 0))

        btns = ttk.Frame(dlg)
        btns.pack(fill=tk.X, padx=15, pady=15)

        def on_ok():
            if self._apply_temp_dir(var.get()):
                dlg.grab_release()
                dlg.destroy()

        ttk.Button(btns, text="恢复默认", command=lambda: var.set(default_temp_dir())).pack(side=tk.LEFT)
        ttk.Button(btns, text="取消", command=lambda: (dlg.grab_release(), dlg.destroy())).pack(side=tk.RIGHT)
        ttk.Button(btns, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=6)
        entry.focus_set()

    def open_temp_dir(self):
        """在文件管理器中打开当前预览提取目录。"""
        d = self.get_temp_dir()
        try:
            open_with_default_app(d)
        except Exception as e:
            messagebox.showerror("打开失败", f"无法打开目录 {d}:\n{e}")

    # ------------------------------------------------------- 设备连接 / App
    def connect_device(self):
        def worker():
            success, msg = self.manager.connect()
            self.root.after(0, self.on_connected, success, msg)
        threading.Thread(target=worker, daemon=True).start()

    def on_connected(self, success, msg):
        if success:
            self.device_info = msg
            self.lbl_status.config(text=msg, foreground="green")
            self.btn_refresh.config(state=tk.NORMAL)
            self.load_apps()
        else:
            self.lbl_status.config(text=msg, foreground="red")

    def load_apps(self):
        self.cb_apps.set("正在加载支持共享的 App...")
        self.cb_apps.config(state=tk.DISABLED)

        def worker():
            try:
                apps = self.manager.get_file_sharing_apps()
                self.root.after(0, self.on_apps_loaded, apps)
            except Exception as e:
                self.root.after(0, self.on_apps_load_failed, str(e))
        threading.Thread(target=worker, daemon=True).start()

    def on_apps_load_failed(self, err):
        self.cb_apps.config(state="readonly")
        self.cb_apps.set("加载 App 失败")
        self.lbl_status.config(text=f"加载 App 列表失败: {err}", foreground="red")

    def on_apps_loaded(self, apps):
        self.cb_apps.config(state="readonly")
        self.apps_dict.clear()

        display_list = []
        for bid, name in apps.items():
            display_name = f"{name} ({bid})"
            self.apps_dict[display_name] = bid
            display_list.append(display_name)

        self.cb_apps['values'] = display_list
        if display_list:
            self.cb_apps.set(display_list[0])
            self.on_app_selected(None)
        else:
            self.cb_apps.set("未找到支持文件共享的 App")

    # ----------------------------------------------- AFC 目录读取（加锁）
    @staticmethod
    def _join_remote(path, item):
        """拼接远程路径，避免出现 // 或 /./ 这类会触发 Error 10 的非法路径。"""
        if path == "" or path == ".":
            return item
        if path.endswith("/"):
            return f"{path}{item}"
        return f"{path}/{item}"

    def _fetch_dir_entries(self, afc, path):
        """列举远程目录并返回排序后的条目 —— 只做 I/O，不碰 Tk 控件。

        返回 [(name, full_path, is_dir, size), ...]，文件夹在前、文件在后。
        本方法在后台线程运行，内部对每次 AFC 调用加锁保护单 socket。
        """
        with self.afc_lock:
            items = afc.listdir(path)

        dirs, files = [], []
        for item in items:
            if item in ('.', '..'):
                continue
            full_path = self._join_remote(path, item)
            try:
                with self.afc_lock:
                    info = afc.stat(full_path)
                is_dir = info.get('st_ifmt') == 'S_IFDIR'
                size = info.get('st_size', 0)
            except Exception:
                is_dir, size = False, 0
            (dirs if is_dir else files).append((item, full_path, is_dir, size))

        return dirs + files

    def _build_children(self, parent_id, entries):
        """在主线程根据条目构建 Treeview 节点。"""
        for name, full_path, is_dir, size in entries:
            if is_dir:
                node = self.tree_fs.insert(parent_id, "end", text=f"📁 {name}", values=(full_path, "", "True"))
                self.tree_fs.insert(node, "end", text="dummy")  # 虚拟节点，便于展开
            else:
                self.tree_fs.insert(parent_id, "end", text=f"📄 {name}", values=(full_path, self.format_size(size), "False"))

    def format_size(self, size):
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size/1024:.1f} KB"
        else:
            return f"{size/(1024*1024):.2f} MB"

    # ------------------------------------------------- 选择 App / 挂载沙盒
    def on_app_selected(self, event):
        selection = self.cb_apps.get()
        if not selection or selection not in self.apps_dict:
            return

        bundle_id = self.apps_dict[selection]

        # 清空现有的树（主线程），并给出加载提示
        for item in self.tree_fs.get_children():
            self.tree_fs.delete(item)
        self.lbl_status.config(text="正在挂载应用沙盒...", foreground="blue")

        # 递增令牌：只有最后一次选择的结果才会被采用
        self.select_token += 1
        token = self.select_token

        def worker():
            try:
                afc = self.manager.get_house_arrest_afc(bundle_id)
                if not afc:
                    self.root.after(0, self._on_mount_failed, token,
                                    "无法挂载该 App 的沙盒（HouseArrest 失败）。")
                    return

                # 智能探测：不同 iOS 版本 / 应用对 AFC 根目录的定义有差异
                valid_root = "/"
                for test_path in ["/", "", ".", "/Documents"]:
                    try:
                        with self.afc_lock:
                            afc.listdir(test_path)
                        valid_root = test_path
                        break
                    except Exception:
                        continue

                entries = self._fetch_dir_entries(afc, valid_root)
                self.root.after(0, self._on_mount_ready, token, afc, valid_root, entries)
            except Exception as e:
                self.root.after(0, self._on_mount_failed, token, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _close_afc(self, afc):
        """在后台线程内持锁关闭 AFC，避免与其它线程的 socket 读写并发。"""
        if afc is None or not hasattr(afc, 'close'):
            return

        def _closer():
            with self.afc_lock:
                try:
                    afc.close()
                except Exception:
                    pass

        threading.Thread(target=_closer, daemon=True).start()

    def _on_mount_ready(self, token, afc, valid_root, entries):
        if token != self.select_token:
            # 用户已经切换到别的 App，丢弃这次过期结果并释放其 socket
            self._close_afc(afc)
            return

        # 切换成功，关闭上一个 App 的 AFC 连接，避免 socket 泄漏
        old = self.current_afc
        if old is not afc and not self.export_running:
            self._close_afc(old)
        self.current_afc = afc

        display_root = valid_root if valid_root else "/"
        root_node = self.tree_fs.insert("", "end", text=f"{display_root} (根目录)", values=(valid_root, "", "True"))
        self._build_children(root_node, entries)
        self.tree_fs.item(root_node, open=True)

        if self.device_info:
            self.lbl_status.config(text=self.device_info, foreground="green")

    def _on_mount_failed(self, token, err):
        if token != self.select_token:
            return
        self.lbl_status.config(text=f"挂载失败: {err}", foreground="red")
        messagebox.showerror("挂载失败", err)

    # -------------------------------------------------- 目录懒加载（后台）
    def on_tree_open(self, event):
        item_id = self.tree_fs.focus()
        values = self.tree_fs.item(item_id, "values")
        if not (values and values[2] == "True"):  # 只处理目录
            return

        children = self.tree_fs.get_children(item_id)
        if not (len(children) == 1 and self.tree_fs.item(children[0], "text") == "dummy"):
            return  # 已经加载过

        path = values[0]
        afc = self.current_afc
        if afc is None:
            return

        # 用占位提示替换 dummy，避免展开瞬间空白
        self.tree_fs.item(children[0], text="⏳ 正在加载...")

        def worker():
            try:
                entries = self._fetch_dir_entries(afc, path)
                self.root.after(0, self._on_children_loaded, item_id, afc, entries, None)
            except Exception as e:
                self.root.after(0, self._on_children_loaded, item_id, afc, None, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_children_loaded(self, item_id, afc, entries, err):
        # 若期间已切换 App，或节点已被销毁，则忽略
        if afc is not self.current_afc or not self.tree_fs.exists(item_id):
            return
        for child in self.tree_fs.get_children(item_id):
            self.tree_fs.delete(child)
        if err is not None:
            self.tree_fs.insert(item_id, "end", text=f"无法读取: {err}")
            return
        self._build_children(item_id, entries)

    # ---------------------------------------------------------- 文件下载
    def download_file_safely(self, afc, remote_path, local_path):
        """健壮的文件下载方法，支持大小文件；所有 AFC 读取均加锁。"""
        try:
            if hasattr(afc, 'pull'):
                with self.afc_lock:
                    afc.pull(remote_path, local_path)  # 流式拉取，避免大文件 OOM
                return True, ""
        except Exception:
            pass  # 回退到整读方案

        try:
            with self.afc_lock:
                data = afc.get_file_contents(remote_path)
            with open(local_path, "wb") as f:
                f.write(data)
            return True, ""
        except Exception as e:
            return False, str(e)

    def _safe_local_path(self, base_dir, remote_path):
        """把远程路径映射到 base_dir 下，保留目录层级并防止路径穿越。

        用 os.path.commonpath 做包含判断，能正确处理盘符根目录（如 D:\\）这类
        base_dir 本身已以分隔符结尾的情况——startswith 拼接会漏判。
        """
        safe_rel_path = remote_path.replace("\\", "/").lstrip("/")
        base_norm = os.path.normpath(base_dir)
        local_path = os.path.normpath(os.path.join(base_norm, safe_rel_path))
        try:
            if os.path.commonpath([base_norm, local_path]) == base_norm:
                return local_path
        except ValueError:
            pass  # 跨盘符 / 绝对相对混用等
        # 逃逸到 base_dir 之外则退化为只用文件名，仍落在 base_dir 内
        return os.path.join(base_norm, os.path.basename(safe_rel_path) or "file")

    def on_tree_double_click(self, event):
        item_id = self.tree_fs.focus()
        if not item_id:
            return

        values = self.tree_fs.item(item_id, "values")
        if not values or values[2] == "True":  # 忽略目录的双击
            return

        afc = self.current_afc
        if afc is None:
            return

        remote_path = values[0]

        # 保留远程目录结构，避免不同目录下的同名文件被相互覆盖
        local_path = self._safe_local_path(self.get_temp_dir(), remote_path)

        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
        except Exception as e:
            messagebox.showerror("错误", f"无法创建临时目录: {e}")
            return

        # 弹窗提示正在提取并锁定主界面 (Modal Dialog)
        tl = tk.Toplevel(self.root)
        tl.title("请稍候")
        tl.geometry("350x120")
        tl.transient(self.root)
        tl.grab_set()  # 锁定主窗口

        # 居中显示弹窗
        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 350) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 120) // 2
        tl.geometry(f"+{x}+{y}")

        ttk.Label(tl, text=f"正在提取文件...\n\n{os.path.basename(remote_path)}", justify=tk.CENTER).pack(expand=True)
        pb = ttk.Progressbar(tl, mode='indeterminate')
        pb.pack(fill=tk.X, padx=20, pady=10)
        pb.start()

        def worker():
            success, err = self.download_file_safely(afc, remote_path, local_path)
            self.root.after(0, on_finished, success, err)

        def on_finished(success, err):
            pb.stop()
            tl.grab_release()
            tl.destroy()
            if success:
                try:
                    open_with_default_app(local_path)
                except Exception as e:
                    messagebox.showerror("打开文件失败", f"文件已保存至 {local_path}，但无法自动打开: {e}")
            else:
                messagebox.showerror("提取失败", f"无法提取 {remote_path}:\n{err}")

        # 使用后台线程下载，保持进度条动画流畅
        threading.Thread(target=worker, daemon=True).start()

    # ---------------------------------------------------------- 任务列表
    def add_to_tasks(self):
        selected_items = self.tree_fs.selection()
        for item_id in selected_items:
            values = self.tree_fs.item(item_id, "values")
            if values:
                remote_path = values[0]
                is_dir = values[2] == "True"

                # 如果是文件夹，则把标识加进去
                task_str = f"[目录] {remote_path}" if is_dir else f"[文件] {remote_path}"

                # 查重
                existing = self.list_tasks.get(0, tk.END)
                if task_str not in existing:
                    self.list_tasks.insert(tk.END, task_str)

    def remove_task(self):
        selected_indices = self.list_tasks.curselection()
        for index in reversed(selected_indices):
            self.list_tasks.delete(index)

    def clear_tasks(self):
        self.list_tasks.delete(0, tk.END)

    # ---------------------------------------------------------- 批量导出
    def batch_export(self):
        tasks = self.list_tasks.get(0, tk.END)
        if not tasks:
            messagebox.showinfo("提示", "任务列表为空。")
            return

        afc = self.current_afc
        if afc is None:
            messagebox.showwarning("提示", "尚未选择 App 或沙盒未挂载。")
            return

        save_dir = filedialog.askdirectory(title="选择批量导出的保存文件夹")
        if not save_dir:
            return

        # 禁用按钮防止重复点击
        self.btn_export.config(state=tk.DISABLED)
        self.export_running = True

        # 创建批量导出的进度弹窗
        tl = tk.Toplevel(self.root)
        tl.title("批量导出中")
        tl.geometry("450x150")
        tl.transient(self.root)
        tl.grab_set()  # 锁定主窗口

        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 450) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 150) // 2
        tl.geometry(f"+{x}+{y}")

        lbl_progress = ttk.Label(tl, text="准备导出...", justify=tk.CENTER, wraplength=430)
        lbl_progress.pack(pady=20)

        pb = ttk.Progressbar(tl, mode='determinate', maximum=len(tasks))
        pb.pack(fill=tk.X, padx=20)

        def export_worker():
            total = len(tasks)
            success_count = 0

            for i, task_str in enumerate(tasks):
                # UI 更新回调：显示“正在处理第 i+1 个”
                def update_ui(idx, txt):
                    pb['value'] = idx
                    lbl_progress.config(text=f"正在导出 ({idx+1}/{total}):\n{txt}")
                    self.lbl_status.config(text=f"正在导出 ({idx+1}/{total})...")

                self.root.after(0, update_ui, i, task_str)

                is_dir = task_str.startswith("[目录]")
                remote_path = task_str.split(" ", 1)[1]

                if is_dir:
                    # afc.pull(src_dir, dst) 内部会自动在 dst 下再建一层 basename，
                    # 最终得到 save_dir/<目录名>/...。
                    # 旧代码把 save_dir/<目录名> 当作 dst 传入，导致被多套了一层
                    # （save_dir/名/名），这里修正为直接传 save_dir。
                    try:
                        if hasattr(afc, 'pull'):
                            with self.afc_lock:
                                afc.pull(remote_path, save_dir)  # → save_dir/<目录名>/...
                            success_count += 1
                        else:
                            print(f"当前版本不支持直接 pull 目录: {remote_path}")
                    except Exception as e:
                        print(f"导出目录失败 {remote_path}: {e}")
                else:
                    # 保留远程目录层级，避免不同目录下的同名文件相互覆盖
                    local_target = self._safe_local_path(save_dir, remote_path)
                    try:
                        os.makedirs(os.path.dirname(local_target), exist_ok=True)
                    except Exception as e:
                        print(f"创建目录失败 {local_target}: {e}")
                        continue
                    ok, _ = self.download_file_safely(afc, remote_path, local_target)
                    if ok:
                        success_count += 1

                # 处理完这一项，让进度条真正走到 i+1
                self.root.after(0, lambda v=i + 1: pb.configure(value=v))

            self.root.after(0, on_export_finished, success_count, total)

        def on_export_finished(success_count, total):
            self.export_running = False
            tl.grab_release()
            tl.destroy()
            self.btn_export.config(state=tk.NORMAL)
            self.lbl_status.config(text=f"批量导出完成！成功: {success_count}/{total}", foreground="green")
            messagebox.showinfo("完成", f"批量导出完成。\n共计 {total} 个任务，成功 {success_count} 个。")

        # 启动后台导出线程
        threading.Thread(target=export_worker, daemon=True).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = AppGUI(root)
    root.mainloop()
