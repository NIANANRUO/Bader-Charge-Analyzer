# Bader 电荷分析 GUI 工具

这是一个用于处理 VASP Bader 电荷分析结果的 Python 图形界面工具。项目提供工作区管理、Bader 计算结果解析、电荷统计、二维图表和三维结构可视化等功能。

## 功能概览

- 管理多个 Bader 分析工作区
- 导入和解析 `ACF.dat`、`CONTCAR`、`POTCAR` 等文件
- 计算原子电荷转移和元素统计信息
- 生成箱线图等统计图表
- 使用 PyVista 显示三维结构和电荷颜色映射

## 环境要求

- Python 3.10 或更高版本
- Bader 命令行程序
- Windows、Linux 或 macOS 桌面环境

## 安装依赖

建议先创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

安装 Python 依赖：

```powershell
pip install -r requirements.txt
```

## Bader 程序配置

本仓库不包含第三方 `bader` 或 `bader.exe` 可执行文件。请自行获取对应平台的 Bader 程序，并使用下面任一方式配置：

1. 将 `bader` 或 `bader.exe` 放到项目根目录。
2. 将 Bader 程序所在目录加入系统 `PATH`。

程序运行 Bader 时会优先检查指定路径，也会检查系统 `PATH`。

## 运行程序

```powershell
python main.py
```

## 运行测试

```powershell
pytest
```

## 项目结构

```text
.
├── assets/          # 静态资源
├── core/            # 文件解析、计算、Bader 调用和工作区管理
├── gui/             # PySide6 图形界面
├── rendering/       # 三维结构渲染和颜色映射
├── tests/           # 自动化测试
├── main.py          # 程序入口
├── requirements.txt # Python 依赖
├── 图标.png         # 当前应用窗口图标
└── pytest.ini       # pytest 配置
```

## GitHub 上传说明

仓库已配置 `.gitignore`，默认不会上传以下本地内容：

- `workspaces/` 中的计算工作区和原始 VASP 数据
- `bader`、`bader.exe` 等第三方可执行文件
- `__pycache__/`、`.pytest_cache/` 等缓存
- `.vscode/`、`.workbuddy/` 等本地配置

如果需要分享示例数据，建议新建体积较小、可公开的 `examples/` 目录，并确认其中不包含敏感或版权受限文件。
