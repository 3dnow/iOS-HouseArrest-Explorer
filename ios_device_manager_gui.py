import os
import sys
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.installation_proxy import InstallationProxyService
    from pymobiledevice3.services.house_arrest import HouseArrestService
except ImportError:
    print("缺少依赖库，请在命令行运行: pip install pymobiledevice3")
    sys.exit(1)

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
        
        self.setup_ui()
        self.connect_device()

    def setup_ui(self):
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

    def connect_device(self):
        def worker():
            success, msg = self.manager.connect()
            self.root.after(0, self.on_connected, success, msg)
        threading.Thread(target=worker, daemon=True).start()

    def on_connected(self, success, msg):
        if success:
            self.lbl_status.config(text=msg, foreground="green")
            self.btn_refresh.config(state=tk.NORMAL)
            self.load_apps()
        else:
            self.lbl_status.config(text=msg, foreground="red")

    def load_apps(self):
        self.cb_apps.set("正在加载支持共享的 App...")
        self.cb_apps.config(state=tk.DISABLED)
        
        def worker():
            apps = self.manager.get_file_sharing_apps()
            self.root.after(0, self.on_apps_loaded, apps)
        threading.Thread(target=worker, daemon=True).start()

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

    def on_app_selected(self, event):
        selection = self.cb_apps.get()
        if not selection or selection not in self.apps_dict: return
        
        bundle_id = self.apps_dict[selection]
        self.current_afc = self.manager.get_house_arrest_afc(bundle_id)
        
        # 清空现有的树
        for item in self.tree_fs.get_children():
            self.tree_fs.delete(item)
            
        if self.current_afc:
            # 智能探测：不同的 iOS 版本和应用对 AFC 根目录的定义有差异
            valid_root = "/"
            for test_path in ["/", "", ".", "/Documents"]:
                try:
                    self.current_afc.listdir(test_path)
                    valid_root = test_path
                    break
                except Exception:
                    continue
                    
            display_root = valid_root if valid_root else "/"
            
            # 插入根节点并尝试展开
            root_node = self.tree_fs.insert("", "end", text=f"{display_root} (根目录)", values=(valid_root, "", "True"))
            self.populate_node(root_node, valid_root)
            self.tree_fs.item(root_node, open=True)

    def format_size(self, size):
        if size < 1024: return f"{size} B"
        elif size < 1024 * 1024: return f"{size/1024:.1f} KB"
        else: return f"{size/(1024*1024):.2f} MB"

    def populate_node(self, parent_id, path):
        """懒加载子目录内容"""
        # 删除 dummy 节点
        for child in self.tree_fs.get_children(parent_id):
            self.tree_fs.delete(child)
            
        try:
            items = self.current_afc.listdir(path)
        except Exception as e:
            self.tree_fs.insert(parent_id, "end", text=f"无法读取: {e}")
            return
            
        # 排序：文件夹在前，文件在后
        dirs, files = [], []
        for item in items:
            if item in ['.', '..']: continue
            
            # 兼容路径拼接，防止出现 // 或 /./ 这种引发 Error 10 的非法路径
            if path == "" or path == ".":
                full_path = item
            elif path.endswith("/"):
                full_path = f"{path}{item}"
            else:
                full_path = f"{path}/{item}"
                
            try:
                info = self.current_afc.stat(full_path)
                is_dir = info.get('st_ifmt') == 'S_IFDIR'
                size = info.get('st_size', 0)
            except:
                is_dir = False
                size = 0
                
            if is_dir:
                dirs.append((item, full_path, size))
            else:
                files.append((item, full_path, size))
                
        for item, full_path, size in dirs:
            node = self.tree_fs.insert(parent_id, "end", text=f"📁 {item}", values=(full_path, "", "True"))
            self.tree_fs.insert(node, "end", text="dummy") # 插入虚拟节点以便可以展开
            
        for item, full_path, size in files:
            self.tree_fs.insert(parent_id, "end", text=f"📄 {item}", values=(full_path, self.format_size(size), "False"))

    def on_tree_open(self, event):
        item_id = self.tree_fs.focus()
        values = self.tree_fs.item(item_id, "values")
        if values and values[2] == "True": # 是目录
            children = self.tree_fs.get_children(item_id)
            if len(children) == 1 and self.tree_fs.item(children[0], "text") == "dummy":
                path = values[0]
                self.populate_node(item_id, path)

    def download_file_safely(self, remote_path, local_path):
        """健壮的文件下载方法，支持大小文件"""
        try:
            if hasattr(self.current_afc, 'pull'):
                self.current_afc.pull(remote_path, local_path)
                return True, ""
        except Exception:
            pass # fallback
            
        try:
            data = self.current_afc.get_file_contents(remote_path)
            with open(local_path, "wb") as f:
                f.write(data)
            return True, ""
        except Exception as e:
            return False, str(e)

    def on_tree_double_click(self, event):
        item_id = self.tree_fs.focus()
        if not item_id: return
        
        values = self.tree_fs.item(item_id, "values")
        if not values or values[2] == "True": return # 忽略目录的双击
        
        remote_path = values[0]
        
        # 修复Bug：保持远程目录结构，避免不同目录下的同名文件被相互覆盖
        safe_rel_path = remote_path.replace("\\", "/").lstrip("/")
        temp_dir = r"D:\temp"
        local_path = os.path.join(temp_dir, os.path.normpath(safe_rel_path))
        
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
        tl.grab_set() # 锁定主窗口
        
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
            success, err = self.download_file_safely(remote_path, local_path)
            self.root.after(0, on_finished, success, err)
            
        def on_finished(success, err):
            tl.grab_release()
            tl.destroy()
            if success:
                try:
                    os.startfile(local_path)
                except Exception as e:
                    messagebox.showerror("打开文件失败", f"文件已保存至 {local_path}，但无法自动打开: {e}")
            else:
                messagebox.showerror("提取失败", f"无法提取 {remote_path}:\n{err}")

        # 使用后台线程下载，保持进度条动画流畅
        threading.Thread(target=worker, daemon=True).start()

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

    def batch_export(self):
        tasks = self.list_tasks.get(0, tk.END)
        if not tasks:
            messagebox.showinfo("提示", "任务列表为空。")
            return
            
        save_dir = filedialog.askdirectory(title="选择批量导出的保存文件夹")
        if not save_dir: return
        
        # 禁用按钮防止重复点击
        self.btn_export.config(state=tk.DISABLED)
        
        # 创建批量导出的进度弹窗
        tl = tk.Toplevel(self.root)
        tl.title("批量导出中")
        tl.geometry("450x150")
        tl.transient(self.root)
        tl.grab_set() # 锁定主窗口
        
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
                # UI 更新回调
                def update_ui(idx, txt):
                    pb['value'] = idx
                    lbl_progress.config(text=f"正在导出 ({idx+1}/{total}):\n{txt}")
                    self.lbl_status.config(text=f"正在导出 ({idx+1}/{total})...")
                    
                self.root.after(0, update_ui, i, task_str)
                
                is_dir = task_str.startswith("[目录]")
                remote_path = task_str.split(" ", 1)[1]
                
                if is_dir:
                    local_target = os.path.join(save_dir, os.path.basename(remote_path.rstrip('/')))
                    try:
                        if hasattr(self.current_afc, 'pull'):
                            self.current_afc.pull(remote_path, local_target)
                            success_count += 1
                        else:
                            print(f"当前版本不支持直接 pull 目录: {remote_path}")
                    except Exception as e:
                        print(f"导出目录失败 {remote_path}: {e}")
                else:
                    local_target = os.path.join(save_dir, os.path.basename(remote_path))
                    ok, _ = self.download_file_safely(remote_path, local_target)
                    if ok: success_count += 1
            
            self.root.after(0, on_export_finished, success_count, total)
            
        def on_export_finished(success_count, total):
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