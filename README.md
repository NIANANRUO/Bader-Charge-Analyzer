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
- Bader 命令行程序，可选
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

如果已经有 `ACF.dat`，程序可以直接导入并解析，不需要再调用 Bader 生成结果。

## 运行程序

```powershell
python main.py
```

## 运行测试

```powershell
pytest
```

## 构建 Windows 安装包

项目使用与 DBand Studio 相同的发布链路：先用 PyInstaller 生成目录版程序，再用 Inno Setup 封装安装器。

准备条件：

- 安装 Inno Setup 6，并确保 `ISCC.exe` 可用。
- 使用包含完整依赖的 Python 环境，例如：

```powershell
c:\Users\21483\.conda\envs\lis_sac_ml\python.exe
```

- 可选：准备 Windows 版 `bader.exe`。

源码仓库不上传 `bader` 或 `bader.exe`。如果安装包不包含 Windows 可执行的 `bader.exe`，用户仍可导入已有 `ACF.dat`、`CONTCAR`、`POTCAR` 等文件进行解析、统计和可视化；只是不能在缺少 `ACF.dat` 时由程序自动调用 Bader 生成结果。

构建不内置 Bader 的安装包：

```powershell
.\installer\build_windows.ps1
```

构建并内置 Windows 版 Bader：

```powershell
.\installer\build_windows.ps1 -BaderExe C:\path\to\bader.exe
```

如果 Inno Setup 没有加入 `PATH`，可以显式指定：

```powershell
.\installer\build_windows.ps1 `
  -ISCCPath "C:\Users\21483\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
```

构建产物：

```text
dist/BaderChargeAnalyzer/BaderChargeAnalyzer.exe
dist/BaderChargeAnalyzer_Setup_v0.1.2.exe
```

安装器支持用户自定义安装位置。安装包不会包含本机已经加载的 `workspaces/`、分组配置、测试缓存或开发目录。安装后的用户工作区会写入用户本地数据目录，不会写入程序安装目录。

## 项目结构

```text
.
├── assets/          # 静态资源
├── core/            # 文件解析、计算、Bader 调用和工作区管理
├── gui/             # PySide6 图形界面
├── installer/       # PyInstaller 和 Inno Setup 打包配置
├── rendering/       # 三维结构渲染和颜色映射
├── tests/           # 自动化测试
├── main.py          # 程序入口
├── requirements.txt # Python 依赖
├── 图标.png         # 当前应用窗口图标
└── pytest.ini       # pytest 配置
```
导入文件说明：
导入Bader计算之后得到的CONTCAR、POTCAR以及ACF.dat文件进行计算解析。
