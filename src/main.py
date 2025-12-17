import os
import re
import sys
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

# PyQt5 imports
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLineEdit, QTreeWidget, QTreeWidgetItem, QLabel, 
    QFileDialog, QTextEdit, QProgressBar, QMessageBox, QSplitter,
    QCheckBox, QHeaderView, QMenu, QFrame, QAbstractItemView
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QIcon

import os
import sys
import time
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem, QProgressBar,
    QTextEdit, QFileDialog, QMessageBox, QCheckBox, QSplitter,
    QAbstractItemView, QMenu
)

# ===========================
# 获取程序所在目录（支持 EXE）
# ===========================
def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()
QUICKBMS_PATH = os.path.join(BASE_DIR, "quickbms.exe")
SCRIPT_PATH = os.path.join(BASE_DIR, "Script.bms")
FSB_EXTRACTOR_PATH = os.path.join(BASE_DIR, "fsb_aud_extr.exe")


# ===========================
# 后台任务线程（与 v9 完全相同，仅微调日志前缀）
# ===========================
class Worker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    done_signal = pyqtSignal(str)

    def __init__(self, bank_file, source_dir, target_dir, do_unpack):
        super().__init__()
        self.bank_file = bank_file
        self.source_dir = Path(source_dir)
        self.target_dir = Path(target_dir)
        self.do_unpack = do_unpack

    def _log(self, msg: str):
        self.log_signal.emit(msg)

    def _run_with_log(self, cmd, cwd=None, prefix="[log]"):
        cmd_str = '" "'.join(cmd)
        self._log(f"{prefix} 执行命令: {cmd_str}")
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        for line in process.stdout:
            line = line.rstrip()
            if line:
                self._log(f"{prefix} {line}")
        process.wait()
        return process.returncode

    def find_audio_roots(self, root_dir):
        audio_dirs = []
        for root, dirs, files in os.walk(root_dir):
            for f in files:
                if f.lower().endswith(".wav"):
                    audio_dirs.append(root)
                    break
        return audio_dirs

    @staticmethod
    def get_core_filename(file_name):
        stem = Path(file_name).stem.lower()
        match = re.match(r'^([a-z]{2,3}_)(.*)$', stem)
        return match.group(2) if match else stem

    def run(self):
        bank_name = Path(self.bank_file).stem

        with tempfile.TemporaryDirectory(prefix="WT_AudioTool_") as temp_root:
            try:
                self.progress_signal.emit(0)
                bank_output_dir = Path(temp_root) / bank_name
                bank_output_dir.mkdir(parents=True, exist_ok=True)

                if self.do_unpack:
                    self._unpack_banks_and_fsb(bank_output_dir)

                audio_roots = self.find_audio_roots(bank_output_dir)
                if not audio_roots:
                    self._log(f"[{bank_name}] [错误] 未找到任何 wav 文件")
                    self.done_signal.emit(self.bank_file)
                    return

                self._log(f"[{bank_name}] [信息] 找到 {len(audio_roots)} 个音频目录")
                self._copy_audio_by_structure(audio_roots, bank_output_dir)

                self.progress_signal.emit(100)
            except Exception as e:
                self._log(f"[{bank_name}] [错误] {e}")
            finally:
                self.done_signal.emit(self.bank_file)

    def _unpack_banks_and_fsb(self, out_dir: Path):
        missing = []
        for tool, path in [("quickbms.exe", QUICKBMS_PATH), ("Script.bms", SCRIPT_PATH), ("fsb_aud_extr.exe", FSB_EXTRACTOR_PATH)]:
            if not os.path.exists(path):
                missing.append(tool)
        if missing:
            self._log(f"[错误] 缺少工具: {', '.join(missing)}")
            return

        self._log(">>> 开始解包 BANK 文件")
        ret = self._run_with_log([QUICKBMS_PATH, SCRIPT_PATH, self.bank_file, str(out_dir)], prefix="[quickbms]")
        if ret != 0:
            self._log(f"[错误] QuickBMS 返回码: {ret}")

        fsb_files = list(out_dir.glob("*.fsb"))
        total = len(fsb_files) or 1
        for i, fsb_path in enumerate(fsb_files):
            fsb_out = out_dir / f"fsb_{fsb_path.stem}"
            fsb_out.mkdir(exist_ok=True)
            self._log(f">>> 解包 FSB: {fsb_path.name}")
            ret = self._run_with_log([FSB_EXTRACTOR_PATH, str(fsb_path)], cwd=str(fsb_out), prefix="[fsb]")
            if ret != 0:
                self._log(f"[错误] fsb_aud_extr 返回码: {ret}")
            self.progress_signal.emit(int((i + 1) / total * 40))

        if not fsb_files:
            self._log("[提示] 未发现 .fsb 文件")

    def _copy_audio_by_structure(self, audio_roots, temp_root):
        self._log("[信息] 正在构建参考结构文件名映射...")
        ref_map = {}
        for ref_path in self.source_dir.rglob("*.*"):
            if ref_path.is_file():
                core = self.get_core_filename(ref_path.name)
                rel_dir = ref_path.parent.relative_to(self.source_dir)
                ref_map.setdefault(core, []).append(rel_dir)

        self._log(f"[信息] 参考结构中共有 {len(ref_map)} 个唯一核心文件名")

        audio_files = []
        for root in audio_roots:
            audio_files.extend(Path(root).rglob("*.wav"))

        total_audio = len(audio_files)
        self._log(f"[信息] 共发现 {total_audio} 个 WAV 文件")

        for idx, audio_path in enumerate(audio_files, 1):
            file_name = audio_path.name
            core = self.get_core_filename(file_name)

            matches = ref_map.get(core, [])
            if not matches:
                self._log(f"[缺失匹配] 未找到: {file_name} (核心: {core})")
            else:
                for rel_dir in matches:
                    dest_dir = self.target_dir / rel_dir
                    dest_path = dest_dir / file_name
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(audio_path, dest_path)
                    self._log(f"[复制] {file_name} → {rel_dir / file_name}")

            progress = 40 + int(idx / total_audio * 60)
            self.progress_signal.emit(min(progress, 99))


# ===========================
# GUI 主窗口 - v9.1（GUI 大幅优化）
# ===========================
class WTTool(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("War Thunder Audio Tool")
        self.resize(1100, 800)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowMaximizeButtonHint)
        
        # 设置窗口图标
        base_dir = get_base_dir()
        # 当程序被打包后，需要从可执行文件所在目录向上找到项目根目录
        # 可执行文件位于 dist/WarThunderAudioTool.exe
        # 项目根目录是 dist/../.. = 项目根目录
        if getattr(sys, "frozen", False):
            # 打包后的情况：dist/WarThunderAudioTool.exe
            project_root = os.path.dirname(os.path.dirname(base_dir))  # 向上两级到项目根目录
        else:
            # 未打包的情况：src/main.py
            project_root = os.path.dirname(base_dir)  # 向上一级到项目根目录
        icon_path = os.path.join(project_root, "ui", "favicon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            print(f"警告：未找到图标文件 {icon_path}")

        self.current_file_index = 0
        self.total_files = 0
        self.workers = []

        self.init_ui()
        self._check_tool_existence()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # === 1. 第一行：游戏目录 + 扫描 + 搜索 ===
        top_layout = QHBoxLayout()

        # 游戏目录
        top_layout.addWidget(QLabel("游戏目录："))
        self.game_dir = QLineEdit()
        self.game_dir.setMinimumWidth(320)
        #self.game_dir.setFixedHeight(30)  # 与表格行高度一致
        top_layout.addWidget(self.game_dir)
        btn_game_dir = QPushButton("选择")
        btn_game_dir.setFixedHeight(30)
        btn_game_dir.setToolTip("选择War Thunder游戏安装目录")
        btn_game_dir.clicked.connect(self.choose_game_dir)
        top_layout.addWidget(btn_game_dir)

        # 扫描按钮
        self.btn_scan = QPushButton("扫描游戏目录")
        #self.btn_scan.setFixedHeight(30)
        self.btn_scan.setMinimumWidth(140)
        self.btn_scan.setToolTip("扫描游戏目录中的.assets.bank文件")
        # 初始禁用扫描按钮
        self.btn_scan.setEnabled(False)
        top_layout.addWidget(self.btn_scan)

        # 搜索
        top_layout.addWidget(QLabel("搜索："))
        self.search_input = QLineEdit()
        self.search_input.setMinimumWidth(300)
        #self.search_input.setFixedHeight(30)  # 与表格行高度一致
        self.search_input.setPlaceholderText("输入关键词搜索银行文件...")
        self.search_input.returnPressed.connect(self.search_assets)
        top_layout.addWidget(self.search_input)
        btn_search = QPushButton("搜索")
        btn_search.setFixedHeight(30)
        btn_search.setToolTip("根据关键词筛选显示的文件")
        btn_search.clicked.connect(self.search_assets)
        top_layout.addWidget(btn_search)

        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        # === 2. 第二行：参考结构目录 ===
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("参考结构目录："))
        self.source_dir = QLineEdit()
        self.source_dir.setMinimumWidth(400)
        #self.source_dir.setFixedHeight(30)  # 与表格行高度一致
        self.source_dir.setPlaceholderText("选择包含参考结构的目录...")
        source_layout.addWidget(self.source_dir)
        btn_source_dir = QPushButton("选择")
        #btn_source_dir.setFixedHeight(30)
        btn_source_dir.setToolTip("选择包含音频文件参考结构的目录")
        btn_source_dir.clicked.connect(self.choose_source_dir)
        source_layout.addWidget(btn_source_dir)
        source_layout.addStretch()
        main_layout.addLayout(source_layout)

        # === 3. 文件列表提示 ===
        tip_label = QLabel("找到的 .assets.bank 文件（双击""输出目录""或""参考结构目录""列设置路径）：")
        tip_label.setStyleSheet("font-weight: bold; color: #333; margin-bottom: 5px;")
        main_layout.addWidget(tip_label)

        # === 4. Splitter：文件列表 + 日志 ===
        splitter = QSplitter(Qt.Vertical)

        # 文件列表
        tree_container = QWidget()
        tree_vlayout = QVBoxLayout(tree_container)
        tree_vlayout.setContentsMargins(0, 0, 0, 0)
        # 在 init_ui() 中，创建 self.bank_tree 后替换原有设置
        self.bank_tree = QTreeWidget()
        self.bank_tree.setHeaderLabels(["选择", "Bank文件", "输出目录", "参考结构目录"])
        # 禁止直接编辑，只能通过双击触发对话框设置
        self.bank_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # 设置只能选择整行
        self.bank_tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        # 禁用展开/折叠功能（如果不需要）
        self.bank_tree.setItemsExpandable(False)

        header = self.bank_tree.header()

        # 鼠标左键调整列宽（Interactive 模式）
        header.setSectionResizeMode(0, QHeaderView.Fixed)            # 选择列固定宽度
        header.setSectionResizeMode(1, QHeaderView.Interactive)     # Bank文件列可手动拖拽
        header.setSectionResizeMode(2, QHeaderView.Interactive)     # 输出目录可手动拖拽
        header.setSectionResizeMode(3, QHeaderView.Interactive)     # 参考结构目录可手动拖拽

        # 设置足够初始宽度 + 最小宽度，防止任何截断
        header.setMinimumSectionSize(80)  # 最小80px，文字永不截断
        self.bank_tree.setColumnWidth(0, 40)  # 选择列设置为40px
        self.bank_tree.setColumnWidth(1, 200)  # Bank文件列初始200px
        self.bank_tree.setColumnWidth(2, 200)  # 输出目录初始200px
        self.bank_tree.setColumnWidth(3, 200)  # 参考结构目录初始200px

        self.bank_tree.setSortingEnabled(True)
        self.bank_tree.setAlternatingRowColors(True)  # 交替行颜色，更易读

        # 设置行高，与编辑框大小一致
        self.bank_tree.setIndentation(20)
        self.bank_tree.setStyleSheet("""
            QTreeWidget::item {
                height: 30px;  /* 与编辑框高度一致 */
            }
        """)

        # 设置表头对齐方式
        header.setDefaultAlignment(Qt.AlignLeft)

        # 移除局部样式，避免与整体样式冲突
        tree_vlayout.addWidget(self.bank_tree)

        # 日志
        log_container = QWidget()
        log_container.setStyleSheet("background-color: white; border-radius: 8px; padding: 5px;")
        log_vlayout = QVBoxLayout(log_container)
        log_vlayout.setContentsMargins(0, 0, 0, 0)
        log_vlayout.addWidget(QLabel("日志："))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 12))
        # 确保日志区域保持黑底白字
        self.log.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #dcdcdc;
                border: 1px solid #444;
                border-radius: 6px;
                font-family: Consolas, monospace;
                font-size: 12px;
            }
        """)
        log_vlayout.addWidget(self.log)

        splitter.addWidget(tree_container)
        splitter.addWidget(log_container)
        splitter.setSizes([450, 350])
        main_layout.addWidget(splitter, stretch=1)

        # === 5. 底部一行：全选按钮 + 解包复选框 + 开始执行 ===
        bottom_layout = QHBoxLayout()

        # 左侧：全选可见 + 取消全选
        left_group = QHBoxLayout()
        left_group.setSpacing(8)
        self.select_all_button = QPushButton("全选")
        self.select_all_button.setFixedHeight(36)
        self.select_all_button.setMinimumWidth(100)
        self.select_all_button.setToolTip("选择所有当前可见的文件")
        self.deselect_all_button = QPushButton("取消全选")
        self.deselect_all_button.setFixedHeight(36)
        self.deselect_all_button.setMinimumWidth(100)
        self.deselect_all_button.setToolTip("取消选择所有当前可见的文件")
        self.select_all_button.clicked.connect(self.select_all)
        self.deselect_all_button.clicked.connect(self.deselect_all)
        left_group.addWidget(self.select_all_button)
        left_group.addWidget(self.deselect_all_button)
        bottom_layout.addLayout(left_group)

        bottom_layout.addStretch()  # 中间拉伸

        # 右侧：解包复选框 + 开始执行按钮
        right_group = QHBoxLayout()
        right_group.setSpacing(15)
        self.chk_unpack = QCheckBox("执行 BANK + FSB 解包步骤（防呆设计）")
        self.chk_unpack.setChecked(False)
        self.chk_unpack.setToolTip("勾选此项将先解包BANK文件和FSB文件，再进行音频文件复制")
        right_group.addWidget(self.chk_unpack)

        self.btn_run = QPushButton("开始执行")
        self.btn_run.setFixedHeight(36)
        self.btn_run.setMinimumWidth(160)
        self.btn_run.setEnabled(False)
        self.btn_run.setToolTip("开始处理选中的文件")
        # 让“开始执行”按钮背景为浅蓝（符合原始设计）
        self.btn_run.setStyleSheet("""
            QPushButton {
                background-color: #a0c4ff;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #106ebe; }            QPushButton:pressed { background-color: #005a9e; }
            QPushButton:pressed { background-color: #6058ff; }
            QPushButton:disabled {
                background-color: #c8dcff;
                color: #aaa;
            }
        """)
        right_group.addWidget(self.btn_run)

        bottom_layout.addLayout(right_group)
        main_layout.addLayout(bottom_layout)

        # === 6. 进度条 ===
        self.progress = QProgressBar()
        self.progress.setFixedHeight(28)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        # 优化进度条样式
        self.progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 8px;
                text-align: center;
                background-color: #e0e0e0;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 6px;
            }
        """)
        main_layout.addWidget(self.progress)

        # === 整体样式（Windows 11 风格）===
        self.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
                font-family: "Segoe UI", sans-serif;
            }
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #106ebe; }
            QPushButton:pressed { background-color: #005a9e; }
            QPushButton:disabled { background-color: #a0c4ff; color: #ccc; }
            QMenu {
                background-color: white;
                color: black;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                background-color: transparent;
                color: black;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QMenu::item:hover {
                background-color: #0078d4;
                color: white;
            }
            QMenu::item:selected {
                background-color: #0078d4;
                color: white;
            }
            QMenu::item:pressed {
                background-color: #005a9e;
                color: white;
            }
            QLineEdit {
                border: 2px solid #e0e0e0;
                border-radius: 6px;
                padding: 8px;
                background: white;
                font-size: 13px;
            }
            QLineEdit:focus { border-color: #0078d4; }
            QTreeWidget {
                background-color: white;
                border: 2px solid #e0e0e0;
                border-radius: 6px;
                alternate-background-color: #f8f9fa;
                font-size: 13px;
            }
            QTreeWidget::header {
                background-color: #f0f0f0;
                border: none;
                font-weight: bold;
                font-size: 12px; /* 适当减小字体大小确保标题完整显示 */
                padding: 6px 0;
                min-height: 35px; /* 增加表头高度 */
            }
            QTreeWidget::header::section {
                background-color: #f0f0f0;
                border: none;
                padding: 12px 10px; /* 增加左右内边距 */
                border-right: 1px solid #d0d0d0;
                text-align: left;
                min-width: 100px; /* 增加最小宽度 */
                spacing: 10px; /* 增加列间距 */
            }
            QTreeWidget::header::section:last {
                border-right: none;
            }
            QTreeWidget::item {
                padding: 4px;
                border: none;
            }
            QTreeWidget::item:hover {
                background-color: #e0e9f5;
            }
            QTreeWidget::item:selected {
                background-color: #d0e3ff;
                color: #000;
            }
            /* 滚动条样式 */
            QScrollBar:vertical {
                background-color: #f5f5f5;
                width: 12px;
                border-radius: 6px;
                margin: 2px 0;
            }
            QScrollBar::handle:vertical {
                background-color: #c1c1c1;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a8a8a8;
            }
            QScrollBar::handle:vertical:pressed {
                background-color: #888888;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
                height: 0;
            }
            QScrollBar:horizontal {
                background-color: #f5f5f5;
                height: 12px;
                border-radius: 6px;
                margin: 0 2px;
            }
            QScrollBar::handle:horizontal {
                background-color: #c1c1c1;
                border-radius: 6px;
                min-width: 20px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #a8a8a8;
            }
            QScrollBar::handle:horizontal:pressed {
                background-color: #888888;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                border: none;
                background: none;
                width: 0;
            }
            QLabel { 
                font-weight: bold; 
                color: #333;
                font-size: 14px;
            }
            QCheckBox { 
                font-weight: normal; 
                color: #333;
                font-size: 13px;
            }
        """)

        # 信号连接
        self.game_dir.textChanged.connect(self.normalize_path)
        self.game_dir.textChanged.connect(self.check_scan_button)
        self.source_dir.textChanged.connect(self.check_scan_button)
        self.btn_scan.clicked.connect(self.scan_game_dir)
        self.btn_run.clicked.connect(self.run_all)
        self.bank_tree.itemChanged.connect(self.on_item_changed)
        self.bank_tree.itemDoubleClicked.connect(self.edit_output_dir)
        self.bank_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.bank_tree.customContextMenuRequested.connect(self.show_context_menu)

    # === 其余方法与 v9 完全相同（仅复制关键部分）===
    def on_item_changed(self, item, column):
        if column == 0:
            self.check_run_button()

    def check_scan_button(self):
        self.btn_scan.setEnabled(bool(self.game_dir.text().strip()))

    def check_run_button(self):
        """检查开始执行按钮是否可用：必须有选中文件且防呆设计勾选"""
        has_checked = any(self.bank_tree.topLevelItem(i).checkState(0) == Qt.Checked
                          for i in range(self.bank_tree.topLevelItemCount()))
        # 按钮可用条件：有选中文件 且 防呆设计勾选
        self.btn_run.setEnabled(has_checked and self.chk_unpack.isChecked())

    def log_print(self, text: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{timestamp}] {text}")
        self.log.ensureCursorVisible()
    
    def normalize_path(self):
        """归一化路径格式，确保显示为Windows格式"""
        current_text = self.game_dir.text()
        # 暂时断开信号连接，避免无限循环
        self.game_dir.textChanged.disconnect(self.normalize_path)
        
        try:
            # 转换为Path对象自动处理分隔符
            if current_text.strip():
                normalized_path = str(Path(current_text))
                self.game_dir.setText(normalized_path)
        finally:
            # 重新连接信号
            self.game_dir.textChanged.connect(self.normalize_path)

    def choose_game_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择游戏目录")
        if path:
            self.game_dir.setText(path)

    def choose_source_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择参考结构目录")
        if path:
            self.source_dir.setText(path)

    def edit_output_dir(self, item, column):
        if column == 2:
            dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录", item.text(2))
            if dir_path:
                item.setText(2, dir_path)
        elif column == 3:
            default = item.text(3) or self.source_dir.text().strip()
            dir_path = QFileDialog.getExistingDirectory(self, "选择参考结构目录", default)
            if dir_path:
                item.setText(3, dir_path)

    def scan_game_dir(self):
        game_dir = Path(self.game_dir.text().strip())
        if not game_dir.is_dir():
            QMessageBox.warning(self, "错误", "请正确选择游戏目录")
            return

        sound_dir = game_dir / "sound"
        if not sound_dir.is_dir():
            QMessageBox.warning(self, "错误", "未找到 sound 文件夹")
            return

        self.bank_tree.clear()
        self.log.clear()
        self.log_print(f"[信息] 扫描目录: {sound_dir}")

        bank_files = list(sound_dir.rglob("*.assets.bank"))
        self.log_print(f"[信息] 找到 {len(bank_files)} 个 .assets.bank 文件")

        global_source = self.source_dir.text().strip()
        for bank_file in bank_files:
            item = QTreeWidgetItem(self.bank_tree)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            item.setCheckState(0, Qt.Unchecked)
            item.setText(1, str(bank_file))
            item.setText(2, "")
            item.setText(3, global_source)

    def get_checked_items(self):
        return [self.bank_tree.topLevelItem(i) for i in range(self.bank_tree.topLevelItemCount())
                if self.bank_tree.topLevelItem(i).checkState(0) == Qt.Checked]

    def search_assets(self):
        keyword = self.search_input.text().strip().lower()
        count = 0
        for i in range(self.bank_tree.topLevelItemCount()):
            item = self.bank_tree.topLevelItem(i)
            visible = not keyword or keyword in item.text(1).lower()
            item.setHidden(not visible)
            if visible:
                count += 1
        self.log_print(f"[信息] 搜索完成，显示 {count} 个文件")

    def select_all(self):
        count = 0
        for i in range(self.bank_tree.topLevelItemCount()):
            item = self.bank_tree.topLevelItem(i)
            if not item.isHidden():
                item.setCheckState(0, Qt.Checked)
                count += 1
        self.log_print(f"[信息] 已全选 {count} 个可见文件")
        self.check_run_button()

    def deselect_all(self):
        count = 0
        for i in range(self.bank_tree.topLevelItemCount()):
            item = self.bank_tree.topLevelItem(i)
            if not item.isHidden():
                item.setCheckState(0, Qt.Unchecked)
                count += 1
        self.log_print(f"[信息] 已取消全选 {count} 个可见文件")
        self.check_run_button()

    def _check_tool_existence(self):
        tools = ["quickbms.exe", "Script.bms", "fsb_aud_extr.exe", "fmodex.dll", "fmodL.dll", "fmod_extr.exe"]
        missing = [t for t in tools if not os.path.exists(os.path.join(BASE_DIR, t))]
        if missing:
            self.log_print(f"[警告] 缺少工具: {', '.join(missing)}")
        else:
            self.log_print("[信息] 所有工具就绪")

    def run_all(self):
        global_source = self.source_dir.text().strip()
        tasks = []
        for item in self.get_checked_items():
            bank_file = item.text(1)
            output_dir = item.text(2).strip()
            if not output_dir:
                QMessageBox.warning(self, "错误", f"{Path(bank_file).name} 未设置输出目录")
                return
            ref_dir = item.text(3).strip() or global_source
            if not ref_dir:
                QMessageBox.warning(self, "错误", f"{Path(bank_file).name} 未设置参考结构目录")
                return
            tasks.append((bank_file, ref_dir, output_dir))

        if not tasks:
            QMessageBox.warning(self, "错误", "请至少选择一个文件")
            return

        for w in [self.btn_run, self.btn_scan, self.select_all_button, self.deselect_all_button]:
            w.setEnabled(False)

        self.progress.setValue(0)
        self.current_file_index = 0
        self.total_files = len(tasks)
        self.workers = []

        self.log_print(f"[信息] 开始处理 {self.total_files} 个文件")

        for bank_file, source_dir, target_dir in tasks:
            basename = Path(bank_file).stem
            self.log_print(f"\n[信息] ====== 开始处理: {basename} ======")

            worker = Worker(bank_file, source_dir, target_dir, self.chk_unpack.isChecked())
            worker.log_signal.connect(lambda msg, b=basename: self.log_print(f"[{b}] {msg}"))
            worker.progress_signal.connect(self.update_progress)
            worker.done_signal.connect(self.on_file_done)
            self.workers.append(worker)

        if self.workers:
            self.workers[0].start()

    def update_progress(self, value):
        if self.total_files == 0:
            self.progress.setValue(0)
            return
        overall = (self.current_file_index * 100 + value) // self.total_files
        self.progress.setValue(min(overall, 100))

    def on_file_done(self, file_path):
        basename = Path(file_path).stem
        self.log_print(f"[信息] ====== {basename} 处理完成 ======")
        self.current_file_index += 1
        if self.current_file_index < len(self.workers):
            self.workers[self.current_file_index].start()
        else:
            self.on_all_done()

    def on_all_done(self):
        self.progress.setValue(100)
        for w in [self.btn_run, self.btn_scan, self.select_all_button, self.deselect_all_button]:
            w.setEnabled(True)
        self.log_print("\n[完成] 全部处理完毕！")

    def show_context_menu(self, position):
        item = self.bank_tree.itemAt(position)
        if not item:
            return
        menu = QMenu(self)
        menu.addAction("设置输出目录", lambda: self.edit_output_dir(item, 2))
        menu.addAction("设置参考结构目录", lambda: self.edit_output_dir(item, 3))
        menu.addSeparator()  # 添加分隔线
        menu.addAction("清除设置", lambda: self.clear_settings(item))
        menu.exec_(self.bank_tree.viewport().mapToGlobal(position))
    
    def clear_settings(self, item):
        """清除输出目录和参考结构目录的路径"""
        item.setText(2, "")  # 清除输出目录（第2列）
        item.setText(3, "")  # 清除参考结构目录（第3列）


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WTTool()
    window.show()
    sys.exit(app.exec_())