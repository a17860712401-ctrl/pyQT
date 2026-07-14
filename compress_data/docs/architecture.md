# 项目架构说明

## 总体结构

项目采用 UI、应用协调、文件处理、压缩、串口和持久化分离的结构。
所有界面控件只在 Qt 主线程访问。
光谱压缩和串口发送分别运行在独立后台线程中。
SQLite 操作每次使用独立短连接，避免跨线程共享连接。

```text
PyQt6 MainWindow
       │ Qt signals / commands
ApplicationController
       ├── ProcessingService thread
       │       ├── input/output folder polling
       │       ├── compression.py
       │       └── StateStore
       └── SerialWorker thread
               ├── pyserial port ownership
               ├── persistent send queue
               └── StateStore
```

## 模块职责

### `models.py`

该模块定义光谱点、压缩结果和串口配置数据类。
该模块不依赖 PyQt6、SQLite 或 pyserial。

### `compression.py`

该模块解析“波数，强度”数据并执行确定性点位筛选。
`parse_spectrum_lines()` 负责文本格式和无效行隔离。
`select_indexes()` 负责首尾、每 30 点和目标波数邻域的索引集合。
`encode_intensity()` 负责舍入、32 位无符号范围检查和最短整字节文本编码。
`compress_file()` 负责读取、压缩和原子输出。

压缩模块不导入 PyQt6。
这样可以在不启动窗口的情况下直接测试算法，并防止耗时处理进入 GUI 线程。

### `storage.py`

该模块使用 SQLite 保存输入序号、抽样决定、压缩结果和发送队列。
`input_files.sequence` 是持久自增序号。
`register_input()` 只在路径首次出现时分配序号，并由序号决定是否抽样。
`output_files.id` 定义发送顺序。
`next_pending_output()` 总是先查看最老的未完成记录，因此重试等待不会造成后续文件越队。

每个方法创建并显式关闭 SQLite 连接。
数据库启用 WAL、正常同步级别和 5 秒 busy timeout。
这种方式允许两个后台线程安全交错访问，同时避免 Windows 文件锁泄漏。

### `monitoring.py`

`scan_txt_files()` 负责跨平台目录枚举和稳定排序。
`FileStabilityTracker` 要求文件元数据连续多次不变。
`ProcessingService` 登记全部输入文件，只压缩选中的稳定文件。
服务也监控输出目录，以登记外部生成或重启后遗留的压缩文件。

每个文件在独立异常边界内处理。
坏文件会标记失败，但循环继续处理后续文件。
外层循环也有异常边界，并通过停止事件等待扫描间隔。

### `serial_comm.py`

`list_serial_ports()` 延迟导入 pyserial，因此缺少依赖时程序仍能显示 UI 和明确错误。
`load_hex_payload()` 验证每行 2、4、6 或 8 位十六进制并转换为原始字节。
固定 8 位的旧版压缩文件仍符合该规则。
`SerialWorker` 在线程内部创建、写入和关闭串口对象。
UI 和应用控制器不会直接访问 pyserial 对象。

发送器记录上一个文件的发送开始时间。
下一个文件只有在至少 1 秒后才允许开始。
写入异常会增加持久尝试次数并设置下一次尝试时间。
格式错误不会重试，而会隔离为失败记录，以免永久阻塞整个队列。

### `application.py`

`ApplicationController` 是 UI 与后台服务之间的边界。
该对象拥有任务和串口状态信号。
后台 Python 线程只调用控制器回调，回调再发射 Qt 信号。
Qt 会把连接到窗口的信号安全投递到 GUI 线程。

任务启动和停止使用可重入锁保护。
重复启动不会创建第二个处理线程。
重复停止不会抛出异常。
关闭流程先停止处理，再停止串口线程并等待退出。

### `ui/main_window.py`

该模块构建完整 PyQt6 主窗口。
窗口包含目录、串口、操作、状态和日志五个区域。
窗口只负责采集用户输入、调用控制器和呈现信号。
窗口不读取光谱文件、不操作 SQLite，也不调用串口写入。

### `config.py`

该模块使用 JSON 保存目录、串口参数、扫描间隔和窗口几何信息。
损坏文件或非法字段会单独回退到默认值。
写入使用临时文件和原子替换。

### `logging_setup.py`

该模块配置控制台日志和滚动文件日志。
文件日志容量有界，避免 7×24 小时运行持续占用磁盘。

## 数据流

1. 处理线程扫描输入目录，并按稳定顺序调用 `register_input()`。
2. SQLite 为新文件分配持久序号并决定是否抽样。
3. 选中的文件连续两次稳定后进入 `compress_file()`。
4. 压缩结果通过临时文件原子发布到输出目录。
5. 输出路径登记到 SQLite 持久发送队列。
6. 串口线程读取队首记录并调用 `load_hex_payload()`。
7. 原始字节完整写入后，记录标记为已发送。
8. 两个后台线程通过控制器信号更新 UI 日志和计数。

## 长时间运行措施

- GUI 主线程不执行轮询、文件解析或串口写入。
- 后台服务使用事件等待，不执行忙循环。
- SQLite 事务短小，并显式关闭每个连接。
- UI 日志最多保存 2000 个文本块。
- 文件日志滚动并限制备份数量。
- 串口重试使用有上限退避。
- 输出队列和文件发现状态持久化。
- 每个文件和每轮扫描均有异常边界。
- 关闭窗口时等待后台线程退出。

## 自定义接口

### 修改压缩选点

修改 `compression.py` 中的 `select_indexes()`。
调用者只依赖它返回有序且不重复的原始索引。
修改后应扩展 `tests/test_compression.py`。

### 修改强度编码

修改 `compression.py` 中的 `encode_intensity()`。
如果改变允许的输出行宽，必须同步修改 `serial_comm.py` 中的 `_HEX_LINE` 和测试。

### 修改设备通信协议

保持 `load_hex_payload()` 负责文件验证。
可以在 `SerialWorker.send_next_once()` 写入前添加帧头、长度、校验和或帧尾。
设备具备应答时，应在成功标记前解析应答，并为超时增加测试。

### 修改抽样规则

修改 `storage.py` 中 `register_input()` 的 selected 计算。
不要在扫描器中按当前目录长度计算，否则重启后序号会漂移。

### 修改 UI

窗口创建集中在 `MainWindow._build_ui()` 及其子方法。
后台服务只通过 `ApplicationController` 暴露，UI 不应直接导入压缩器或创建串口对象。

## 测试边界

`test_compression.py` 验证纯算法和文件输出。
`test_storage.py` 验证持久顺序、重启和队首重试。
`test_monitoring.py` 验证稳定性、抽样和异常隔离。
`test_serial_comm.py` 使用假串口验证字节、间隔和重试。
`test_application.py` 验证线程生命周期和 Qt 信号。
`test_ui.py` 在 offscreen 平台验证窗口和控件状态。
`test_startup.py` 验证日志和完整应用对象图。
