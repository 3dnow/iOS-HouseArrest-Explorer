iOS HouseArrest Explorer 📱📂

English | 中文说明

<h2 id="english">English</h2>

A robust, GUI-based iOS file sharing extractor for **Windows, macOS, and Linux**. It allows you to browse, safely preview, and batch export iOS App sandbox (Documents) files via USB without jailbreak, utilizing Apple's native HouseArrest service.

✨ Features & Highlights

This is not just a simple wrapper. It handles many edge cases and protocol quirks that usually cause CLI tools to fail:

No Jailbreak Required: Communicates directly with iOS via USB (usbmuxd) to access apps with UIFileSharingEnabled.

Dynamic API Patching (Bypass VendContainer crash): Automatically monkey-patches underlying pymobiledevice3 APIs to force the VendDocuments command, ensuring perfect compatibility with App Store apps.

Smart AFC Root Probing (Fix Error 10): Automatically probes the correct AFC root path (/, "", ., /Documents) across different iOS versions to prevent the notorious Opcode: READ_DIR failed with status: 10 error.

Cross-Platform (Windows / macOS / Linux): Pure-Python + tkinter, no OS-specific code paths. Files open with the system default program (`start` / `open` / `xdg-open`) and are staged in the system temp directory automatically.

Safe Double-Click Preview: Double-click any file to instantly extract it and open it with the OS default program. It perfectly reconstructs the remote directory tree locally to prevent filename collisions. The extraction directory defaults to the system temp folder but is **fully configurable** — pick any folder or drive (e.g. `D:\` or `/Volumes/USB`) via **Settings → 预览提取目录…**; the choice is remembered across sessions (`~/.ios_housearrest_explorer.json`).

Robust Batch Export: Supports adding individual files or entire directories to a task queue. Uses stream-based .pull() for large files to prevent memory overflow crashes. Exported files keep their remote folder hierarchy, so same-named files from different directories never overwrite each other.

Fluid & Responsive UI: Built with tkinter. Every device / AFC I/O operation — mounting the sandbox, listing directories, previewing and exporting — runs on background threads, so the UI never freezes. A single lock serializes access to the AFC socket to keep the underlying connection safe.

🛠️ Prerequisites

Windows, macOS, or Linux

Python 3.9+ (with the standard-library `tkinter`; on some Linux distros install `python3-tk`)

usbmuxd running:
- **Windows**: install iTunes or the "Apple Devices" app (Microsoft Store) so the Apple Mobile Device / usbmuxd service is running.
- **macOS**: nothing to install — `usbmuxd` ships with the OS.
- **Linux**: install and start the `usbmuxd` package (e.g. `sudo apt install usbmuxd`).

An iOS device connected via USB, unlocked, and trusting the computer.

🚀 Installation & Usage

Clone the repository:

git clone https://github.com/3dnow/iOS-HouseArrest-Explorer.git
cd iOS-HouseArrest-Explorer


Install the pinned dependency:

pip install -r requirements.txt


> ⚠️ Note: this GUI targets the **synchronous** pymobiledevice3 API. Version 8.0.0+ migrated to an async API and is **not** supported (a plain `pip install pymobiledevice3` would break the app). `requirements.txt` therefore pins the last synchronous line (`pymobiledevice3>=7,<8`).

Run the application:

python ios_device_manager_gui.py


Usage:

Select an App from the top dropdown menu.

Browse the file tree on the left.

Double-click a file to preview it instantly.

Select files/folders, click "Add to Export Tasks >>".

Click "Execute Batch Export" to download everything to your PC.

<h2 id="中文说明">中文说明</h2>

一款强大的**跨平台（Windows / macOS / Linux）** iOS 共享文件提取器 (GUI版)。无需越狱，通过 USB 连接即可利用苹果原生的 HouseArrest 服务，轻松浏览、安全预览并批量导出 iOS App 的沙盒（Documents）文件。

✨ 核心特色与技术亮点

这不是一个简单的图形化套壳工具。它在底层处理了大量苹果通信协议的边缘情况和第三方库的痛点：

免越狱提取： 直接通过 USB (usbmuxd) 通信，读取所有开启了“文件共享” (UIFileSharingEnabled) 权限的 App 数据。

动态 API 劫持补丁 (解决 VendContainer 崩溃)： 针对 pymobiledevice3 库在挂载非越狱设备应用时报错的问题，在运行时动态劫持 (Monkey-Patch) 并强制发送 VendDocuments 指令，实现完美挂载。

智能 AFC 根目录探测 (修复 Error 10 Bug)： 不同的 iOS 版本对 AFC 协议根目录的解析存在差异。本工具采用智能探测池（依次尝试 /, "", ., /Documents），彻底消灭由于路径非法导致的 READ_DIR failed with status: 10 错误。

全平台支持 (Windows / macOS / Linux)： 纯 Python + tkinter，没有任何绑定某个系统的代码路径。落地临时文件使用系统临时目录，打开文件自动调用各系统的默认程序（`start` / `open` / `xdg-open`）。

安全的双击预览机制： 在左侧树形图中双击任意文件，工具会将其瞬间提取到本地并调用默认程序打开。核心细节： 提取时会在本地完美复刻手机端的目录层级结构，杜绝了同名文件互相覆盖的严重 Bug。**预览提取目录可自定义**：默认落在系统临时目录，也可通过菜单 **设置 → 预览提取目录…** 指定任意文件夹或盘符（如 `D:\` 或 `/Volumes/USB`），选择会持久化记住（保存在 `~/.ios_housearrest_explorer.json`）。

稳健的大文件批量导出： 支持将单文件或“整个文件夹”加入任务队列。优先采用底层的流式传输 (.pull()) 拉取大体积文件，彻底避免传统内存读取方式导致的 Python 内存溢出 (OOM) 崩溃。批量导出同样保留手机端目录层级，不同目录下的同名文件不会互相覆盖。

流畅的异步 UI： 原生 tkinter 打造，从挂载沙盒、列举目录到预览、导出，所有设备 / AFC 的 I/O 操作全部在后台独立线程运行，配合模态锁定遮罩 (Modal Dialog) 和实时进度条，告别界面假死。底层用一把锁串行化 AFC socket 访问，保证单条连接不被并发读写打乱。

🛠️ 环境准备

Windows / macOS / Linux 任意系统

Python 3.9+（需自带标准库 `tkinter`；部分 Linux 发行版需额外安装 `python3-tk`）

后台需运行 usbmuxd：
- **Windows**：安装 iTunes 或 Microsoft Store 的“Apple Devices (Apple 设备)”应用，以启动 Apple 移动设备 / usbmuxd 服务。
- **macOS**：无需安装，`usbmuxd` 系统自带。
- **Linux**：安装并启动 `usbmuxd`（如 `sudo apt install usbmuxd`）。

通过 USB 连接你的 iPhone/iPad，保持屏幕解锁，并在弹窗中选择“信任此电脑”。

🚀 安装与运行


安装依赖库（已锁定版本）：

pip install -r requirements.txt


> ⚠️ 注意：本 GUI 使用的是 pymobiledevice3 的**同步版 API**。8.0.0+ 已迁移为 async 异步 API，本项目**不支持**（直接 `pip install pymobiledevice3` 会装到新版导致工具失效）。因此 `requirements.txt` 锁定为最后一个同步版本线（`pymobiledevice3>=7,<8`）。

启动图形化程序：

python ios_device_manager_gui.py


操作指南：

在顶部下拉菜单选择你想查看的 App。

在左侧文件树中浏览文件。

双击任意文件即可调用 Windows 默认程序进行预览。

选中需要的文件或文件夹，点击 "加入导出任务 >>"。

在右侧确认任务列表后，点击 "执行批量导出" 选择本地保存路径即可。

📜 License

This project is licensed under the MIT License.
