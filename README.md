# 🐍 PyEnvKit — Python 环境全能管理工具箱

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows" />
  <img src="https://img.shields.io/badge/GUI-CustomTkinter-green" />
  <img src="https://img.shields.io/badge/License-MIT-yellow" />
</p>

<p align="center">
  <b>一站式 Python 环境管理 · 版本部署 · 包管理 · 虚拟环境 · 打包工具</b>
</p>

---

## ✨ 功能一览

### 📦 包管理 (Package)
- **探针式精准扫描** — 向目标 Python 解释器注入探针脚本，精确获取所有已安装库的名称、版本、磁盘占用和安装时间
- **实时搜索过滤** — 输入关键词即时筛选库列表
- **一键安装/卸载** — 图形化 pip 操作，终端输出实时显示
- **PyPI 在线查询** — 点击任意库即可查看作者、主页、简介等元信息
- **导出 requirements.txt** — 一键导出当前环境所有依赖，自动生成版本注释和 `pip install -r` 安装指引
- **多列排序** — 按库名、版本、大小、安装时间任意排序

### 🚀 环境部署 (Deploy)
- **自动扫描本机环境** — 通过 Windows 注册表 + `py -0p` 双通道检测所有已安装的 Python 版本
- **云端版本列表** — 实时从 Python 官方 FTP 获取所有可用版本
- **智能安装包探测** — 自动匹配正确的安装包文件名（兼容 amd64/win_amd64 等多种命名格式），避免 404 错误
- **一键静默安装/卸载** — 后台下载安装包，静默执行，零弹窗干扰
- **设为全局默认** — 修改用户 PATH 环境变量 + `PY_PYTHON` 配置，自动广播系统消息即时生效

### 🌐 全局虚拟环境 (Global Venv)
- **一键创建共享 Venv** — 选择基础解释器，一键创建可供 PyCharm / VSCode / 其他 IDE 共用的全局虚拟环境
- **路径一键复制** — 创建完成后直接复制虚拟环境 Python 路径，粘贴到 IDE 即可使用
- **默认存储位置** — 虚拟环境默认创建在 `%APPDATA%\GlobalPythonVenv`，整洁不污染用户目录

### 🔨 打包工具 (Packaging)
- **PyInstaller 图形化封装** — 告别命令行，可视化配置入口脚本、输出名称、图标、资源文件
- **多种打包模式** — 支持单文件 (.exe)、文件夹、或两种同时生成
- **实时日志 + 进度条** — 打包过程全程可视，中文输出不乱码
- **代码清洗** — 批量移除 Python 源码中的 `#` 注释和多余空行，生成 `_clean.py` 安全副本
- **环境隔离** — 自动净化 `TCL_LIBRARY` 等冲突变量，打包后的 EXE 也能稳定运行

---

## 📸 界面预览

> 💡 程序启动后自动扫描本机所有 Python 版本，无需手动配置即可开始使用。

| 包管理 | 环境部署 | 打包工具 |
|--------|----------|----------|
| 现代化卡片列表，支持搜索/排序/导出 | 云端版本 + 本机版本双栏对照 | PyInstaller 可视化配置 + 代码清洗 |

---

## 🔧 安装与运行

### 环境要求
- **操作系统**：Windows 10 / 11
- **Python**：3.8+
- **依赖库**：`customtkinter`（首次运行时会**自动安装**）

### 快速启动

```bash
# 克隆项目
git clone https://github.com/你的用户名/PyEnvKit.git
cd PyEnvKit

# 直接运行（缺失依赖会自动安装）
python Python版本管理.py
```

### 打包为 EXE（可选）

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name=PyEnvKit Python版本管理.py
```

> 🔒 部分功能（如修改 PATH 环境变量、安装/卸载 Python 版本）可能需要**以管理员身份运行**。

---

## 📁 项目结构

```
PyEnvKit/
├── Python版本管理.py      # 主程序（All-in-One 单文件）
├── PyLibManager.py         # 独立的轻量级包管理器（已集成至主程序）
├── PythonPackagingTool_v3.0.py  # 独立的打包工具（已集成至主程序）
└── README.md
```

---

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| GUI 框架 | [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — 现代化暗色主题 |
| 环境发现 | Windows 注册表 (`winreg`) + `py -0p` 双通道 |
| 包扫描 | 沙盒探针脚本 (`importlib.metadata`) |
| 在线数据 | Python 官方 FTP + PyPI JSON API |
| 安装/卸载 | 官方安装器静默模式 (`/quiet`) |
| 系统集成 | `ctypes` 广播 `WM_SETTINGCHANGE` 消息 |
| 打包 | PyInstaller 命令行封装 |
| 异步模型 | `threading` + `queue` + `self.after()` 线程安全 UI 更新 |

---

## 📝 更新日志

### v1.0 (2026-05-13)
- ✅ 自动扫描本机 Python 环境（注册表 + py 启动器）
- ✅ 在线获取可安装版本 & 一键静默部署/卸载
- ✅ 设置全局默认 Python 版本（修改 PATH + PY_PYTHON）
- ✅ 高级包管理（探针扫描、搜索、排序、PyPI 查询、导出 requirements.txt）
- ✅ 全局共享虚拟环境创建
- ✅ PyInstaller 打包工具 & 代码清洗
- ✅ 缺失依赖自动安装
- ✅ 打包为 EXE 后可正常运行

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。
