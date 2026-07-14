# 光谱压缩串口上位机

这是一个使用 Python 和 PyQt6 开发的光谱压缩串口上位机。
程序提供完整中文 UI，可自动抽样输入文件、压缩光谱强度并通过串口按队列发送。
程序支持 Windows 和 Linux，并针对长时间运行设计了后台线程、持久化状态、异常隔离和滚动日志。

## 功能

- 通过 UI 选择输入文件夹和输出文件夹。
- 自动记忆目录、串口参数和窗口大小。
- 配置串口、波特率、数据位、校验位和停止位。
- 在 UI 中打开或关闭串口，并启动或停止处理任务。
- 实时显示发现、压缩、待发送、发送成功和失败数量。
- 实时显示限长运行日志，并将完整日志写入滚动文件。
- 按首次发现顺序处理第 1、11、21 个文件。
- 等待文件连续两次扫描保持不变后再读取。
- 使用 SQLite 避免重启后重复计数、重复压缩或重复确认发送。
- 串口发送失败后保持队列顺序并自动退避重试。

## 环境要求

- Python 3.10 或更高版本。
- Windows 10/11 或主流桌面 Linux 发行版。
- VSCode 推荐安装 Python 扩展。

## 安装

进入 `compress_data` 目录后创建虚拟环境。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

运行只需要 `PyQt6` 和 `pyserial`。
`[dev]` 额外安装 pytest 和 PyInstaller，方便测试和打包。

## 运行

Windows 可以运行：

```powershell
.\scripts\run_windows.ps1
```

Linux 可以运行：

```bash
bash scripts/run_linux.sh
```

也可以在安装项目后直接运行：

```bash
python -m spectrum_compressor.main
```

## UI 操作

1. 在“数据文件夹”区域选择原始光谱输入目录和压缩输出目录。
2. 在“串口配置”区域刷新并选择串口。
3. 选择波特率、数据位、校验位和停止位。
4. 单击“打开串口”。
5. 单击“启动任务”。
6. 在运行状态和日志区域观察压缩及发送结果。
7. 结束时先停止任务，再关闭串口。

任务运行时目录控件会被锁定。
串口打开时串口参数控件会被锁定。
关闭窗口时程序会有序停止后台线程并保存配置。

## 输入数据格式

每条有效记录需要包含波数和强度两列。
程序接受英文逗号、中文逗号和空白字符分隔。
程序允许表头、空行和少量不能解析的行。

```text
波数,强度
200,123.4
230 125.5
260，126.6
```

如果文件没有任何有效数据，当前文件会标记为压缩失败。
该失败不会停止后续文件处理或串口线程。

## 文件抽样规则

程序按首次发现顺序为每个输入 txt 文件分配持久序号。
每组 10 个文件只处理第一个，因此处理序号为 1、11、21，依此类推。
未选中的文件仍会记录到 SQLite，确保程序重启后序号不漂移。

同一扫描周期出现多个文件时，程序优先按系统可用时间排序，再用文件名稳定排序。
Linux 文件系统可能没有真正的创建时间，此时使用修改时间排序。

## 压缩规则

目标波数为 200、800、1400、2000、2600、3200、3800 和 4400。
程序为每个范围内的目标波数寻找距离最近的数据点。
程序保留目标点及其前后各 10 个点。
其他区域按原始数据索引每 30 个点保留 1 个。
首点和尾点始终保留。
所有索引会合并去重，并保持原始文件顺序。

输出只包含强度值。
强度按 `ROUND_HALF_UP` 规则取整，即半数向远离零方向进位。
强度必须位于 32 位无符号整数范围 `0～4294967295`，负数会被拒绝。
每个结果写成最短整字节小写十六进制文本，不包含 `0x` 前缀。
每行长度只能为 2、4、6 或 8 位。

```text
强度 10  -> 0a
强度 255 -> ff
强度 256 -> 0100
强度 300 -> 012c
```

输出文件与输入文件同名。
程序先写临时文件，再原子替换目标文件，发送线程不会读到半成品。

## 串口发送规则

发送器逐行验证输出文件，每个非空行必须是 2、4、6 或 8 位十六进制字符。
发送器使用 `bytes.fromhex()` 将文本转换为原始字节。
例如 `012c` 会发送两个字节 `01 2C`。
程序不会发送字符 `0`、`1`、`2`、`c` 的 ASCII 字节。
旧版 8 位十六进制文件仍可正常发送。

程序不自动添加帧头、帧尾、长度字段或校验码。
如设备需要专用帧协议，请修改 `src/spectrum_compressor/serial_comm.py` 中的 `load_hex_payload()` 或发送前组帧逻辑。

相邻文件的发送开始时间至少间隔 1 秒。
写入异常采用 1、2、4、8、16、30 秒封顶退避。
失败文件保持在队首，重试等待期间不会越过它发送后续文件。
格式错误的压缩文件会标记为失败并隔离，避免永久阻塞队列。

设备没有回执协议时，程序只能把本地串口完整写入视为成功。
如果程序在设备已收到数据但 SQLite 尚未确认时突然断电，该文件重启后可能再次发送。

## 状态和配置位置

Windows 默认使用 `%APPDATA%\SpectrumCompressor`。
Linux 默认使用 `$XDG_CONFIG_HOME/SpectrumCompressor` 或 `~/.config/SpectrumCompressor`。

该目录包含：

- `config.json`，保存用户配置。
- `state.sqlite3`，保存输入序号和发送队列。
- `logs/application.log`，保存滚动日志。

日志单文件最大 5 MiB，并保留 5 个备份。
如需从零重新编号，必须先停止程序，再备份并删除 `state.sqlite3`。

## VSCode

用 VSCode 直接打开 `compress_data` 文件夹。
选择 `.venv` 中的 Python 解释器。
`.vscode/launch.json` 提供正常启动和无界面 UI 检查配置。
`.vscode/tasks.json` 提供虚拟环境、依赖安装和完整测试任务。

## 测试

项目测试使用标准库 unittest 编写，同时兼容 pytest 发现。

```powershell
$env:PYTHONPATH="src"
$env:QT_QPA_PLATFORM="offscreen"
python -m unittest discover -s tests -v
```

Linux：

```bash
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

也可以运行：

```bash
pytest -v
```

## 打包

Windows：

```powershell
.\scripts\build_windows.ps1
```

如果系统禁止执行 PowerShell 脚本，可以只对本次命令绕过策略：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\build_windows.ps1"
```

Linux：

```bash
bash scripts/build_linux.sh
```

生成结果位于 `dist/SpectrumCompressor`。
Windows 和 Linux 必须分别在目标操作系统上打包。
PyInstaller 不能在 Windows 上直接生成 Linux 可执行文件，反之亦然。

## 可修改点

- 修改目标波数、邻域半径或降采样步长：编辑 `compression.py` 中的 `ANCHOR_WAVENUMBERS`、`NEIGHBORHOOD_RADIUS` 和 `DOWNSAMPLE_STRIDE`。
- 修改强度范围、文本宽度或字节序：编辑 `compression.py` 中的 `encode_intensity()`，并同步修改 `serial_comm.py` 中的行格式校验。
- 修改文件抽样周期：编辑 `storage.py` 中 `register_input()` 的 `(sequence - 1) % 10 == 0`。
- 修改文件稳定次数：调整 `ProcessingService` 的 `stability_observations` 参数。
- 修改文件间隔和退避：编辑 `SerialWorker` 的 `minimum_file_interval` 和失败分支。
- 添加设备帧协议：编辑 `serial_comm.py` 中 `load_hex_payload()` 之后的发送组帧过程。
- 修改 UI 布局或样式：编辑 `ui/main_window.py`。
- 修改日志容量：编辑 `logging_setup.py` 中 `RotatingFileHandler` 参数。

详细模块边界见 [架构说明](docs/architecture.md)。

## 常见问题

### UI 无法启动并提示缺少 PyQt6

确认当前终端使用项目虚拟环境，并重新执行 `python -m pip install -e .`。

### 串口下拉框为空

确认已经安装 pyserial，并检查设备是否被系统识别。
Linux 用户还需要确认当前用户有串口权限，例如属于 `dialout` 组。
修改用户组后通常需要重新登录。

### 串口被占用

关闭其他串口调试软件和可能占用同一端口的程序。
Windows 可重新插拔设备并刷新串口列表。

### 新文件没有立即处理

程序需要连续两次扫描确认文件大小和修改时间不变。
默认扫描间隔为 1 秒，因此正常情况下会等待约 1 至 2 秒。
还要确认该文件序号是否为 1、11、21 等抽样序号。

### 输出文件没有发送

确认串口状态显示为已打开。
检查输出文件每个非空行是否为 2、4、6 或 8 位十六进制字符。
检查“待发送”和“发送文件错误”状态，并查看日志中的重试原因。

### 想重新处理同名输入文件

程序按规范化完整路径去重，同一路径不会自动重新编号。
如需重新开始，请停止程序，备份并删除用户配置目录中的 `state.sqlite3`。

### Linux 打包后无法打开串口

检查设备路径和用户权限。
通过终端启动程序可以看到系统权限错误，并可在日志文件中查看详细原因。
