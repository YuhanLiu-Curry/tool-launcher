# Tool Launcher — Windows 系统托盘工具箱

基于 Tkinter 的 Windows 系统托盘应用，统一管理多个本地工具和服务：一键启动 / 停止、状态实时显示、开机自启。

## 解决什么问题

日常要用的本地 Web 工具（书签管理器、爬虫服务等）每个都要手动开命令行启动，操作繁琐还容易忘。Tool Launcher 提供统一入口：托盘常驻、一键启动、自动打开浏览器。

## 功能特性

- 系统托盘常驻，右键菜单快速操作
- 一键启动 / 停止各工具服务，托盘状态实时显示（启动中 / 运行中 / 已停止）
- 服务就绪后自动打开浏览器访问
- 支持 Windows 开机自启（`install-startup.ps1`）

## 快速开始

环境要求：Windows 10+，Python 3.8+（Tkinter 为标准库，无需额外安装依赖）

```bash
python run.py
```

或直接双击 `start.bat` 启动、`stop.bat` 停止。

## 添加自己的工具

编辑 `tools.json`，为每个工具添加一条配置（名称、描述、启动命令、访问 URL），保存即生效，无需改代码。

## 设计决策

- **Tkinter 而非 Electron**：Python 标准库零额外依赖，包体小
- **Windows 原生 API 实现托盘图标**：减少第三方库的维护风险
- **JSON 配置而非数据库**：新增工具只需加一条配置，修改即生效

## 与其他工具配合

与 [bookmark-manager](https://github.com/YuhanLiu-Curry/bookmark-manager) 配合使用：Tool Launcher 一键启动书签管理器并自动打开浏览器，构成完整的本地工具工作流。
