iOS HouseArrest Explorer 📱📂

English | 中文说明

<h2 id="english">English</h2>

A robust, GUI-based iOS file sharing extractor for Windows. It allows you to browse, safely preview, and batch export iOS App sandbox (Documents) files via USB without jailbreak, utilizing Apple's native HouseArrest service.

✨ Features & Highlights

This is not just a simple wrapper. It handles many edge cases and protocol quirks that usually cause CLI tools to fail:

No Jailbreak Required: Communicates directly with iOS via USB (usbmuxd) to access apps with UIFileSharingEnabled.

Dynamic API Patching (Bypass VendContainer crash): Automatically monkey-patches underlying pymobiledevice3 APIs to force the VendDocuments command, ensuring perfect compatibility with App Store apps.

Smart AFC Root Probing (Fix Error 10): Automatically probes the correct AFC root path (/, "", ., /Documents) across different iOS versions to prevent the notorious Opcode: READ_DIR failed with status: 10 error.

Safe Double-Click Preview: Double-click any file to instantly extract it to %TEMP% and open it with Windows' default program. It perfectly reconstructs the remote directory tree locally to prevent filename collisions.

Robust Batch Export: Supports adding individual files or entire directories to a task queue. Uses stream-based .pull() for large files to prevent memory overflow crashes.

Fluid & Responsive UI: Built with tkinter. Features multi-threading, modal dialogs, and real-time progress bars to ensure the UI never freezes during heavy I/O operations.

🛠️ Prerequisites

Windows OS

Python 3.8+

Apple Mobile Device Support: Ensure iTunes or the "Apple Devices" app (from Microsoft Store) is installed so the Windows usbmuxd service is running.

An iOS device connected via USB, unlocked, and trusting the computer.

🚀 Installation & Usage

Clone the repository:

git clone [https://github.com/yourusername/iOS-HouseArrest-Explorer.git](https://github.com/yourusername/iOS-HouseArrest-Explorer.git)
cd iOS-HouseArrest-Explorer


Install the required dependency:

pip install pymobiledevice3


Run the application:

python ios_device_manager_gui.py


Usage:

Select an App from the top dropdown menu.

Browse the file tree on the left.

Double-click a file to preview it instantly.

Select files/folders, click "Add to Export Tasks >>".

Click "Execute Batch Export" to download everything to your PC.

<h2 id="中文说明">中文说明</h2>

一款强大的 Windows 端 iOS 共享文件提取器 (GUI版)。无需越狱，通过 USB 连接即可利用苹果原生的 HouseArrest 服务，轻松浏览、安全预览并批量导出 iOS App 的沙盒（Documents）文件。

✨ 核心特色与技术亮点

这不是一个简单的图形化套壳工具。它在底层处理了大量苹果通信协议的边缘情况和第三方库的痛点：

免越狱提取： 直接通过 USB (usbmuxd) 通信，读取所有开启了“文件共享” (UIFileSharingEnabled) 权限的 App 数据。

动态 API 劫持补丁 (解决 VendContainer 崩溃)： 针对 pymobiledevice3 库在挂载非越狱设备应用时报错的问题，在运行时动态劫持 (Monkey-Patch) 并强制发送 VendDocuments 指令，实现完美挂载。

智能 AFC 根目录探测 (修复 Error 10 Bug)： 不同的 iOS 版本对 AFC 协议根目录的解析存在差异。本工具采用智能探测池（依次尝试 /, "", ., /Documents），彻底消灭由于路径非法导致的 READ_DIR failed with status: 10 错误。

安全的双击预览机制： 在左侧树形图中双击任意文件，工具会将其瞬间提取到 Windows 的 %TEMP% 目录并调用默认程序打开。核心细节： 提取时会在本地完美复刻手机端的目录层级结构，杜绝了同名文件互相覆盖的严重 Bug。

稳健的大文件批量导出： 支持将单文件或“整个文件夹”加入任务队列。优先采用底层的流式传输 (.pull()) 拉取大体积文件，彻底避免传统内存读取方式导致的 Python 内存溢出 (OOM) 崩溃。

流畅的异步 UI： 原生 tkinter 打造，所有耗时 I/O 操作均在后台独立线程运行，配合模态锁定遮罩 (Modal Dialog) 和实时进度条，告别界面假死。

🛠️ 环境准备

Windows 操作系统

Python 3.8+

Apple 驱动支持：请确保电脑已安装 iTunes 或 Microsoft Store 中的“Apple Devices (Apple 设备)”应用，以保证后台存在 usbmuxd 守护进程。

通过 USB 连接你的 iPhone/iPad，保持屏幕解锁，并在弹窗中选择“信任此电脑”。

🚀 安装与运行


安装核心依赖库：

pip install pymobiledevice3


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
