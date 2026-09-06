from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QStyle, QSystemTrayIcon


def make_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#4f9cde"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(3, 3, 58, 58)
    font = QFont("Microsoft YaHei UI", 25)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("white"))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "鱼")
    painter.end()
    return QIcon(pixmap)


class TrayController:
    def __init__(self, app: QApplication, core, config, inbox, on_exit) -> None:
        self.app = app
        self.core = core
        self.config = config
        self.inbox = inbox
        self.on_exit = on_exit
        self.tray = QSystemTrayIcon(make_icon(), app)
        self.tray.setToolTip("大肥鱼 Codex 增强桌宠")
        self.menu = QMenu()

        self.show_action = self.menu.addAction("显示大肥鱼")
        self.show_action.triggered.connect(lambda: self._control("show"))
        self.hide_action = self.menu.addAction("隐藏大肥鱼")
        self.hide_action.triggered.connect(lambda: self._control("hide"))

        self.auto_action = self.menu.addAction("随 Codex 自动启动")
        self.auto_action.setCheckable(True)
        self.auto_action.setChecked(bool(config.get("auto_accompany")))
        self.auto_action.toggled.connect(self._set_auto)

        self.menu.addSeparator()
        self.status_action = self.menu.addAction("设置与状态")
        self.status_action.triggered.connect(self.show_status)
        self.menu.addSeparator()
        self.exit_action = self.menu.addAction("彻底退出")
        self.exit_action.triggered.connect(self.full_exit)

        self.menu.aboutToShow.connect(self.refresh)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activated)
        self.tray.show()

    def _control(self, action: str) -> None:
        self.core.handle_message({"kind": "control", "action": action})
        self.refresh()

    def _set_auto(self, checked: bool) -> None:
        self.core.handle_message({"kind": "control", "action": "set-auto-accompany", "enabled": checked})

    def refresh(self) -> None:
        self.auto_action.blockSignals(True)
        self.auto_action.setChecked(bool(self.config.get("auto_accompany")))
        self.auto_action.blockSignals(False)
        self.hide_action.setEnabled(self.core.pet.running and bool(self.config.get("visible")))
        self.show_action.setEnabled(not self.core.pet.running or not bool(self.config.get("visible")))
        self.tray.setToolTip("大肥鱼 Codex 增强桌宠\n" + self.core.status_text().splitlines()[0])

    def show_status(self) -> None:
        box = QMessageBox()
        box.setWindowTitle("大肥鱼 Codex 增强桌宠")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(self.core.status_text())
        box.setInformativeText(f"配置目录：{self.config.data_dir}")
        box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Open)
        if box.exec() == QMessageBox.StandardButton.Open:
            try:
                os.startfile(str(Path(self.config.data_dir)))  # type: ignore[attr-defined]
            except OSError:
                pass

    def full_exit(self) -> None:
        self.core.disable_until_manual_reopen()
        self.tray.hide()
        self.on_exit()

    def _activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.core.pet.running and self.config.get("visible"):
                self._control("hide")
            else:
                self._control("show")
