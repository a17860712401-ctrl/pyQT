from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..models import FileFailure, RestoreResult
from ..parsing import SpectrumFormatError, parse_template
from .worker import RestoreWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.template_path: Path | None = None
        self.compressed_paths: tuple[Path, ...] = ()
        self.output_directory: Path | None = None
        self._thread: QThread | None = None
        self._worker: RestoreWorker | None = None

        self.setWindowTitle("光谱还原")
        self.resize(860, 680)
        self.setMinimumSize(720, 560)
        self._build_ui()
        self._apply_style()
        self._update_ready_state()

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        title = QLabel("光谱还原")
        title.setObjectName("titleLabel")
        subtitle = QLabel("使用完整横坐标模板，将压缩十六进制强度还原为十进制光谱")
        subtitle.setObjectName("subtitleLabel")
        root.addWidget(title)
        root.addWidget(subtitle)

        template_group = QGroupBox("1. 选择横坐标模板")
        template_layout = QHBoxLayout(template_group)
        self.template_path_edit = QLineEdit()
        self.template_path_edit.setReadOnly(True)
        self.template_path_edit.setPlaceholderText("请选择包含完整横坐标第一列的 TXT 文件")
        self.template_button = QPushButton("选择模板…")
        self.template_button.clicked.connect(self.choose_template)
        template_layout.addWidget(self.template_path_edit, 1)
        template_layout.addWidget(self.template_button)
        root.addWidget(template_group)

        files_group = QGroupBox("2. 选择压缩文件")
        files_layout = QVBoxLayout(files_group)
        file_buttons = QHBoxLayout()
        self.compressed_button = QPushButton("添加压缩文件…")
        self.compressed_button.clicked.connect(self.choose_compressed_files)
        self.clear_button = QPushButton("清空列表")
        self.clear_button.clicked.connect(self.clear_compressed_files)
        file_buttons.addWidget(self.compressed_button)
        file_buttons.addWidget(self.clear_button)
        file_buttons.addStretch(1)
        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(120)
        files_layout.addLayout(file_buttons)
        files_layout.addWidget(self.file_list)
        root.addWidget(files_group, 1)

        output_group = QGroupBox("3. 选择输出目录")
        output_layout = QHBoxLayout(output_group)
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setReadOnly(True)
        self.output_path_edit.setPlaceholderText("默认在压缩文件目录下创建 Restored")
        self.output_button = QPushButton("选择目录…")
        self.output_button.clicked.connect(self.choose_output_directory)
        output_layout.addWidget(self.output_path_edit, 1)
        output_layout.addWidget(self.output_button)
        root.addWidget(output_group)

        action_layout = QGridLayout()
        self.restore_button = QPushButton("开始还原")
        self.restore_button.setObjectName("primaryButton")
        self.restore_button.clicked.connect(self.start_restore)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.summary_label = QLabel("等待选择文件")
        action_layout.addWidget(self.restore_button, 0, 0, 2, 1)
        action_layout.addWidget(self.progress_bar, 0, 1)
        action_layout.addWidget(self.summary_label, 1, 1)
        action_layout.setColumnStretch(1, 1)
        root.addLayout(action_layout)

        log_group = QGroupBox("处理日志")
        log_layout = QVBoxLayout(log_group)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(500)
        log_layout.addWidget(self.log_edit)
        root.addWidget(log_group, 1)
        self.setCentralWidget(central)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #f4f7fb; }
            QLabel#titleLabel { color: #17324d; font-size: 26px; font-weight: 700; }
            QLabel#subtitleLabel { color: #5f7185; font-size: 13px; margin-bottom: 4px; }
            QGroupBox {
                background: white; border: 1px solid #d9e2ec; border-radius: 8px;
                margin-top: 10px; padding-top: 10px; font-weight: 600; color: #243b53;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
            QLineEdit, QListWidget, QPlainTextEdit {
                border: 1px solid #bcccdc; border-radius: 5px; padding: 6px;
                background: #fbfdff; color: #102a43;
            }
            QPushButton {
                border: 1px solid #9fb3c8; border-radius: 5px; padding: 7px 14px;
                background: #ffffff; color: #243b53;
            }
            QPushButton:hover { background: #edf4fa; }
            QPushButton:disabled { color: #9aa5b1; background: #e9eef3; }
            QPushButton#primaryButton {
                background: #1769aa; color: white; border: none; font-weight: 700;
                min-width: 110px; min-height: 38px;
            }
            QPushButton#primaryButton:hover { background: #12578e; }
            QProgressBar { border: 1px solid #bcccdc; border-radius: 5px; text-align: center; }
            QProgressBar::chunk { background: #2f80b9; border-radius: 4px; }
            """
        )

    def set_template_path(self, path: Path | str) -> None:
        self.template_path = Path(path)
        self.template_path_edit.setText(str(self.template_path))
        self._update_ready_state()

    def set_compressed_paths(self, paths: tuple[Path | str, ...] | list[Path | str]) -> None:
        unique: list[Path] = []
        seen: set[Path] = set()
        for path in paths:
            candidate = Path(path)
            if candidate not in seen:
                seen.add(candidate)
                unique.append(candidate)
        self.compressed_paths = tuple(unique)
        self.file_list.clear()
        self.file_list.addItems(str(path) for path in self.compressed_paths)
        if self.compressed_paths and self.output_directory is None:
            self.set_output_directory(self.compressed_paths[0].parent / "Restored")
        self._update_ready_state()

    def set_output_directory(self, path: Path | str) -> None:
        self.output_directory = Path(path)
        self.output_path_edit.setText(str(self.output_directory))
        self._update_ready_state()

    def clear_compressed_files(self) -> None:
        self.compressed_paths = ()
        self.file_list.clear()
        self._update_ready_state()

    def choose_template(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "选择横坐标模板", "", "TXT 文件 (*.txt)")
        if selected:
            self.set_template_path(selected)

    def choose_compressed_files(self) -> None:
        selected, _ = QFileDialog.getOpenFileNames(self, "选择压缩文件", "", "TXT 文件 (*.txt)")
        if selected:
            self.set_compressed_paths(tuple(Path(path) for path in selected))

    def choose_output_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择还原文件输出目录")
        if selected:
            self.set_output_directory(selected)

    def _is_ready(self) -> bool:
        return bool(self.template_path and self.compressed_paths and self.output_directory)

    def _update_ready_state(self) -> None:
        running = self._thread is not None and self._thread.isRunning()
        self.restore_button.setEnabled(self._is_ready() and not running)
        self.clear_button.setEnabled(bool(self.compressed_paths) and not running)

    def set_running(self, running: bool) -> None:
        for control in (
            self.template_button,
            self.compressed_button,
            self.output_button,
            self.clear_button,
        ):
            control.setEnabled(not running)
        self.restore_button.setEnabled(self._is_ready() and not running)

    def start_restore(self) -> None:
        if not self._is_ready():
            QMessageBox.warning(self, "输入不完整", "请先选择模板、压缩文件和输出目录。")
            return
        assert self.template_path is not None
        assert self.output_directory is not None
        try:
            parse_template(self.template_path)
        except SpectrumFormatError as error:
            QMessageBox.critical(self, "模板错误", str(error))
            return

        self.progress_bar.setValue(0)
        self.summary_label.setText(f"准备处理 {len(self.compressed_paths)} 个文件")
        self.log_edit.appendPlainText("开始还原…")
        self.set_running(True)

        thread = QThread(self)
        worker = RestoreWorker(
            self.template_path,
            self.compressed_paths,
            self.output_directory,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.file_succeeded.connect(self._on_file_succeeded)
        worker.file_failed.connect(self._on_file_failed)
        worker.finished.connect(self._on_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._release_thread)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_progress(self, current: int, total: int, name: str) -> None:
        self.progress_bar.setValue(round(current * 100 / total) if total else 0)
        self.summary_label.setText(f"正在处理 {current}/{total}：{name}")

    def _on_file_succeeded(self, result: RestoreResult) -> None:
        self.log_edit.appendPlainText(
            f"成功：{result.source_path.name} → {result.output_path.name}（{result.method}）"
        )
        for warning in result.warnings:
            self.log_edit.appendPlainText(f"警告：{warning}")

    def _on_file_failed(self, failure: FileFailure) -> None:
        self.log_edit.appendPlainText(f"失败：{failure.source_path.name}：{failure.message}")

    def _on_finished(self, successes: int, failures: int) -> None:
        self.progress_bar.setValue(100)
        self.summary_label.setText(f"处理完成：成功 {successes} 个，失败 {failures} 个")
        self.log_edit.appendPlainText(f"处理完成：成功 {successes} 个，失败 {failures} 个。")
        self.set_running(False)

    def _release_thread(self) -> None:
        self._thread = None
        self._worker = None
        self._update_ready_state()
