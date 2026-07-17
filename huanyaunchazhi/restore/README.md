# 光谱还原软件

这是一个仅用于 Windows 的 Python 和 PyQt6 光谱还原工具。
软件使用用户选择的 TXT 文件第一列作为完整横坐标，并还原 `compress_data` 生成的单列压缩强度。

## 数据规则

横坐标模板可以包含一列或多列数据。
软件只读取每个非空行的第一列，后续列全部忽略。
模板不允许表头、非数值、无穷值或重复横坐标。
横坐标必须严格递增或严格递减，不能任意乱序。

压缩文件的每个非空行必须是 2、4、6 或 8 位十六进制整数。
软件先把十六进制文本转换为十进制强度。
例如，`0a` 转换为 `10`，`ff` 转换为 `255`，`012c` 转换为 `300`。
还原文件不会输出十六进制强度。

## 还原方式

软件按照 `compress_data` 的规则重新计算真实点索引。
普通区域每隔 35 点保留一个点，首尾点始终保留。
软件还保留 981、1386、2911、2578、2593 和 4134 附近左右各 9 点。
压缩强度数量与计算索引数量不一致时，软件拒绝该文件。

三个或更多真实点使用 PCHIP 保形插值。
两个真实点自动使用线性插值。
PCHIP 失败时也自动退化为线性插值。
程序禁止范围外推，并在插值后强制恢复全部真实点。

输出文件名为 `<原文件名>_restored.txt`。
输出第一列保留模板横坐标原文，第二列为十进制强度。
插值强度最多保留 4 位小数，并去除末尾零。

## 安装

需要 Windows 10 或 Windows 11，以及 Python 3.10 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 启动

```powershell
.\scripts\run_windows.ps1
```

也可以直接运行：

```powershell
python run_app.py
```

## 使用

先选择包含完整横坐标的模板 TXT 文件。
再选择一个或多个压缩 TXT 文件。
程序默认在第一个压缩文件所在目录下创建 `Restored`，也可以手动选择其他目录。
单击“开始还原”后，进度条和处理日志会显示每个文件的结果。
单个文件失败不会中断其他文件。

## 测试

```powershell
$env:PYTHONPATH="src"
$env:QT_QPA_PLATFORM="offscreen"
python -m unittest discover -s tests -v
```

## 打包

先安装开发依赖：

```powershell
python -m pip install -e ".[dev]"
```

再执行：

```powershell
.\scripts\build_windows.ps1
```

生成的可执行文件位于 `dist\SpectrumRestore.exe`。

详细原理和异常说明见 [使用与算法说明](docs/使用与算法说明.md)。
