"""PyQt6 static-image workspace, separate from motor control."""

from __future__ import annotations

from pathlib import Path
import threading

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QImage, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
    QVBoxLayout, QWidget, QFrame, QSizePolicy, QDialog, QDialogButtonBox, QLineEdit,
)

from .vision import VisionParameters, VisionSession, export_paths, preview_png
from .camera import CameraFeed


class VisionWindow(QWidget):
    completed = pyqtSignal(object)
    exported = pyqtSignal(bool,str)

    def __init__(self, parent, stop):
        super().__init__(parent, Qt.WindowType.Window)
        self.owner = parent
        self.export_dialog = None
        self._export_busy = False
        self.camera = CameraFeed()
        self._camera_live = False
        self._camera_sequence = -1
        self._capture_process = False
        self.exported.connect(self._exported)
        self.setWindowTitle("F3P 图像处理 · 轮廓提取")
        self.resize(1280, 720)
        self.setMinimumSize(1050, 650)
        self.session = VisionSession(self.completed.emit)
        self.completed.connect(self._complete)
        self.pixmap = QPixmap()
        self._fit_cache = None
        self.setStyleSheet(parent.styleSheet() + """
            QPushButton { min-height: 28px; font-size: 14px; padding: 6px 10px; }
            QSpinBox, QDoubleSpinBox, QComboBox { font-size: 14px; min-width: 0;
                padding: 5px; background: #0b1424; border: 1px solid #365075; }
            QListWidget { background: #0b1424; border: 1px solid #263652; }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        header = QHBoxLayout()
        title = QLabel("图像处理 / 轮廓提取")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        self.exit_button = QPushButton("退出图像处理")
        self.exit_button.clicked.connect(self.close)
        header.addWidget(self.exit_button)
        button = QPushButton("■ 停止电机")
        button.clicked.connect(stop)
        button.setStyleSheet("background:#b52f3a;border-color:#ff6974;")
        header.addWidget(button)
        outer.addLayout(header)
        outer.addWidget(QLabel("图片 / 电脑摄像头 → 轮廓路径 · 像素坐标 · 空格键停止电机"))
        camera_row = QHBoxLayout()
        camera_row.addWidget(QLabel('电脑摄像头'))
        self.camera_index = QSpinBox(); self.camera_index.setRange(0, 9)
        camera_row.addWidget(self.camera_index)
        self.camera_open = QPushButton('打开摄像头'); self.camera_open.clicked.connect(self._open_camera)
        self.camera_close = QPushButton('关闭摄像头'); self.camera_close.clicked.connect(self._close_camera)
        self.camera_capture = QPushButton('拍照并提取轮廓'); self.camera_capture.clicked.connect(self._capture_camera)
        self.camera_resume = QPushButton('继续预览'); self.camera_resume.clicked.connect(self._resume_camera)
        for widget in (self.camera_open,self.camera_close,self.camera_capture,self.camera_resume):camera_row.addWidget(widget)
        camera_row.addStretch(); outer.addLayout(camera_row)
        columns = QHBoxLayout()
        outer.addLayout(columns, 1)

        left = QFrame()
        left.setObjectName("card")
        left.setFixedWidth(238)
        controls = QVBoxLayout(left)
        controls.addWidget(QLabel("01 / 图片与参数"))
        self.import_button = QPushButton("＋ 导入物品图片")
        self.import_button.clicked.connect(self._import)
        controls.addWidget(self.import_button)
        self.file_label = QLabel("尚未导入图片")
        self.file_label.setWordWrap(True)
        controls.addWidget(self.file_label)
        self.scope = QCheckBox("包含内部边界")
        controls.addWidget(self.scope)
        self.method = QComboBox()
        self.method.addItems(["自动阈值", "手动阈值"])
        controls.addWidget(QLabel("分割方法"))
        controls.addWidget(self.method)
        self.threshold = QSpinBox()
        self.threshold.setRange(0, 255)
        self.threshold.setValue(128)
        self.threshold.setEnabled(False)
        self.blur = QComboBox()
        self.blur.addItems(['0'] + [str(value) for value in range(1, 22, 2)])
        self.blur.setCurrentText('3')
        self.blur.setToolTip('0：不去噪；1～21：奇数高斯滤波窗口。')
        self.area = QSpinBox()
        self.area.setRange(1, 40000000)
        self.area.setValue(200)
        self.epsilon = QDoubleSpinBox()
        self.epsilon.setRange(0.5, 20)
        self.epsilon.setSingleStep(0.5)
        self.epsilon.setValue(2)
        for caption, widget in [("二值化阈值", self.threshold), ("去噪强度", self.blur),
                                ("最小面积 / 原图 px²", self.area), ("路径简化 / 原图 px", self.epsilon)]:
            controls.addWidget(QLabel(caption))
            controls.addWidget(widget)
        controls.addStretch()
        self.process_button = QPushButton("提取轮廓")
        self.process_button.clicked.connect(self._process)
        controls.addWidget(self.process_button)
        columns.addWidget(left)

        center = QFrame()
        center.setObjectName("card")
        preview = QVBoxLayout(center)
        self.view = QComboBox()
        self.view.addItems(["原图", "二值图", "轮廓", "叠加"])
        self.view.currentIndexChanged.connect(self._render)
        preview.addWidget(self.view)
        self.image = QLabel("导入一张背景简单的物品图片\n预览原图后点击“提取轮廓”")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(200, 200)
        self.image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.image.setStyleSheet("background:#0b1424;border-radius:8px;color:#91a4c4;")
        preview.addWidget(self.image, 1)
        self.dimensions = QLabel("坐标原点：图片左上角 · X 向右 · Y 向下")
        preview.addWidget(self.dimensions)
        columns.addWidget(center, 1)

        right = QFrame()
        right.setObjectName("card")
        right.setFixedWidth(238)
        results = QVBoxLayout(right)
        results.addWidget(QLabel("02 / 轮廓与路径"))
        self.stats = QLabel("尚无处理结果")
        self.stats.setWordWrap(True)
        results.addWidget(self.stats)
        self.paths = QListWidget()
        self.paths.itemChanged.connect(self._selection_changed)
        results.addWidget(self.paths, 1)
        results.addWidget(QLabel("03 / 保存结果"))
        self.svg = QPushButton("导出 SVG")
        self.json = QPushButton("导出路径 JSON")
        self.svg.clicked.connect(lambda: self._export("svg"))
        self.json.clicked.connect(lambda: self._export("json"))
        results.addWidget(self.svg)
        results.addWidget(self.json)
        note = QLabel("结果为像素路径。纸面标定、笔画排序和机器人执行将在后续接入。")
        note.setWordWrap(True)
        note.setObjectName("subtitle")
        results.addWidget(note)
        columns.addWidget(right)
        self.status = QLabel("就绪 · 支持 PNG / JPEG / BMP / WebP")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        self.method.currentIndexChanged.connect(self._changed)
        self.scope.toggled.connect(self._changed)
        self.threshold.valueChanged.connect(self._changed)
        self.blur.currentIndexChanged.connect(self._changed)
        self.area.valueChanged.connect(self._changed)
        self.epsilon.valueChanged.connect(self._changed)
        if not hasattr(parent,"_return_to_control"):
            QShortcut(QKeySequence("Space"), self, activated=stop)
        if not hasattr(parent,"_return_to_control"):
            QShortcut(QKeySequence("Esc"), self, activated=self.close)
        self._buttons()
        self.camera_timer = QTimer(self); self.camera_timer.setInterval(100)
        self.camera_timer.timeout.connect(self._poll_camera); self.camera_timer.start()

    def _open_camera(self):
        if self.session.busy:return
        if not self.camera.start(self.camera_index.value()):
            self.status.setText('摄像头正在关闭，请稍后再打开。');return
        self._camera_live=True; self._camera_sequence=-1
        self.status.setText('正在打开摄像头…'); self._buttons()

    def _close_camera(self):
        self.camera.stop(); self._camera_live=False
        self._render(); self.status.setText('摄像头已关闭。'); self._buttons()

    def _resume_camera(self):
        if self.camera.running and not self.session.busy:
            self._camera_live=True; self._camera_sequence=-1; self._buttons()

    def _poll_camera(self):
        if self.session.closed:return
        sequence, latest, message = self.camera.latest()
        if self._camera_live:
            self.status.setText(message)
            if latest is not None and sequence != self._camera_sequence:
                self._camera_sequence=sequence
                rgb=latest[1]; height,width=rgb.shape[:2]
                image=QImage(rgb.data,width,height,rgb.strides[0],QImage.Format.Format_RGB888).copy()
                self.pixmap=QPixmap.fromImage(image);self._preview_key=None;self._fit()
            if not self.camera.running and latest is None:self._camera_live=False
        self._buttons()

    def _capture_camera(self):
        _, latest, _ = self.camera.latest()
        if latest is None or self.session.busy:return
        self._camera_live=False; self._capture_process=True
        self.paths.clear();self.stats.setText('正在处理摄像头快照…')
        self.session.start(frame=latest[0].copy())
        self.status.setText('正在拍照…');self._buttons()

    def shutdown_camera(self):
        self.camera.stop(); self._camera_live=False; self.camera_timer.stop()

    def _buttons(self):
        busy = self.session.busy
        running=self.camera.running; latest=self.camera.latest()[1]
        self.camera_open.setEnabled(not running and not busy)
        self.camera_index.setEnabled(not running)
        self.camera_close.setEnabled(running)
        self.camera_capture.setEnabled(latest is not None and running and not busy)
        self.camera_resume.setEnabled(running and not self._camera_live and not busy)
        self.import_button.setEnabled(not busy and not self._camera_live)
        self.process_button.setEnabled(self.session.source is not None and not busy and not self._camera_live)
        available = self.session.result is not None and bool(self._selected()) and not busy and not self._export_busy and not self._camera_live
        self.svg.setEnabled(available)
        self.json.setEnabled(available)

    def _selected(self):
        return [self.paths.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.paths.count())
                if self.paths.item(i).checkState() == Qt.CheckState.Checked]

    def _changed(self, *_):
        self.threshold.setEnabled(self.method.currentIndex() == 1)
        self.session.invalidate()
        self.paths.clear()
        self.stats.setText("参数已修改 · 请重新提取")
        self.status.setText("处理结果已过期，导出已禁用。")
        self._render()
        self._buttons()

    def _import(self):
        filename, _ = QFileDialog.getOpenFileName(self, "导入物品图片", "",
                                                 "图片 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if filename:
            self.paths.clear()
            self.stats.setText("正在加载新图片…")
            self.session.start(filename=filename)
            self.status.setText("正在读取图片…")
            self._buttons()

    def _process(self):
        self.paths.clear()
        params = VisionParameters(self.scope.isChecked(), self.method.currentIndex() == 0,
                                  self.threshold.value(), int(self.blur.currentText()),
                                  self.area.value(), self.epsilon.value())
        self.session.start(parameters=params)
        self.status.setText("正在提取轮廓…")
        self._buttons()

    def _complete(self, completion):
        capture_process=self._capture_process
        self._capture_process=False
        outcome = self.session.accept(completion)
        if self.session.closed:
            return
        if outcome == "stale":
            self.status.setText("参数已变更，本次结果已丢弃；请重新提取。")
        elif outcome:
            self.status.setText(outcome)
        else:
            self._updating_preview = True
            source = self.session.source
            self.file_label.setText(Path(source["filename"]).name)
            self.dimensions.setText(f'{source["width"]} × {source["height"]} px · 原图像素坐标')
            if self.session.result is not None:
                self.paths.blockSignals(True)
                self.paths.clear()
                for path in self.session.result["paths"]:
                    kind = "内部" if path["parent_id"] else "外部"
                    item = QListWidgetItem(f'{path["id"]:02d} {kind}边界 · {len(path["points"])} 点')
                    item.setData(Qt.ItemDataRole.UserRole, path["id"])
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked)
                    self.paths.addItem(item)
                self.paths.blockSignals(False)
                self.view.setCurrentIndex(3)
                self.status.setText("提取完成，请确认轮廓再导出。" if self.paths.count()
                                    else "未找到符合条件的轮廓，请调整阈值或最小面积。")
            else:
                self.view.setCurrentIndex(0)
                self.stats.setText("图片已载入 · 等待提取")
                self.status.setText("图片已载入，可调整参数后提取。")
            self._updating_preview = False
            self.pixmap.loadFromData(completion[3], "PNG"); self._fit()
            self._preview_key = self._current_preview_key()
            self._selection_changed(render=False)
        self._buttons()
        if capture_process and outcome is None and completion[1]:self._process()

    def _current_preview_key(self):
        return (self.session.revision,self.view.currentIndex(),tuple(self._selected()))

    def _render(self, *_):
        if self._camera_live or self.session.source is None or getattr(self,'_updating_preview',False):
            return
        key=self._current_preview_key()
        if getattr(self,'_preview_key',None)==key:
            self._fit();return
        try:
            data = preview_png(self.session.source, self.session.result,
                               ["original", "binary", "contour", "overlay"][self.view.currentIndex()],
                               self._selected())
            self.pixmap.loadFromData(data, "PNG")
            self._preview_key=key
            self._fit()
        except Exception as exc:
            self.status.setText(str(exc))

    def _fit(self):
        if not self.pixmap.isNull():
            key=(self.pixmap.cacheKey(),self.image.width(),self.image.height())
            if self._fit_cache==key:return
            self._fit_cache=key
            self.image.setPixmap(self.pixmap.scaled(self.image.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "image"):
            self._fit()

    def _selection_changed(self, *_, render=True):
        if self.session.result is not None:
            selected = self._selected()
            count = sum(len(p["points"]) for p in self.session.result["paths"] if p["id"] in selected)
            self.stats.setText(f"选中 {len(selected)} 条轮廓 · {count} 个路径点")
            if render: self._render()
        self._buttons()

    def _export(self, format):
        if self.session.result is None or not self._selected() or self._export_busy:return
        self._export_format=format
        if self.export_dialog is None:
            self.export_dialog=QDialog(self);self.export_dialog.setWindowTitle('保存轮廓路径')
            self.export_dialog.setModal(True);self.export_dialog.resize(660,160)
            layout=QVBoxLayout(self.export_dialog);layout.addWidget(QLabel('保存路径（可以修改）'))
            self.export_entry=QLineEdit();layout.addWidget(self.export_entry)
            buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(self._save_export);buttons.rejected.connect(self.export_dialog.hide);layout.addWidget(buttons)
        from .recorder import default_directory
        self.export_entry.setText(str(default_directory()/('contours.'+format)))
        self.export_dialog.show();self.export_dialog.raise_()

    def _save_export(self):
        self.export_dialog.hide();filename=self.export_entry.text().strip();format=self._export_format
        if not filename:self.status.setText('保存路径不能为空');return
        if not filename.lower().endswith('.'+format):filename+='.'+format
        if Path(filename).exists() and QMessageBox.question(self,'覆盖文件','该文件已存在，是否覆盖？')!=QMessageBox.StandardButton.Yes:return
        result,selected=self.session.result,self._selected()
        if result is None or not selected:return
        self._export_busy=True;self._buttons();self.status.setText('正在保存轮廓…')
        def work():
            error=''
            try:
                Path(filename).parent.mkdir(parents=True,exist_ok=True)
                export_paths(result,selected,filename,format)
            except Exception as exc:error=str(exc)
            self.exported.emit(not error,error or filename)
        threading.Thread(target=work,daemon=True,name='f3p-path-export').start()

    def _exported(self, ok, message):
        self._export_busy=False
        if not self.session.closed:
            self.status.setText(('已保存：' if ok else '导出失败：')+message);self._buttons()

    def closeEvent(self, event):
        self._close_camera()
        if hasattr(self.owner,'_return_to_control'):self.owner._return_to_control()
        else:
            self.hide();self.owner.raise_();self.owner.activateWindow()
        event.ignore()
