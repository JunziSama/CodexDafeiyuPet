
# -*- coding: utf-8 -*-
"""EAC 原生聊天气泡复刻（用于 dsh-pet-indesktop）。

视觉规格直接复用 dsh-dafeiyu/runtime/helper.py 中的气泡卡片：
- 大圆角 30px；
- 双层错位阴影；
- 1px 半透明浅灰描边；
- 主标题 11px DemiBold #25282D；
- 副标题 9px #747981；
- 右侧状态圆点 46px 直径，按状态着色。
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QFrame

_MAC = sys.platform == "darwin"

_CARD_X = 14
_CARD_Y = 7
_CARD_HEIGHT = 84
_CARD_RADIUS = 30
_CARD_WINDOW_WIDTH = 448
_CARD_WINDOW_HEIGHT = 98

_STATUS_COLORS = {
    "SUCCESS": (QColor("#D9F7E4"), QColor("#12B85A")),
    "ERROR": (QColor("#FDE3E3"), QColor("#E5484D")),
    "WAITING": (QColor("#FFF0CE"), QColor("#D88A00")),
    "THINKING": (QColor("#E2ECFF"), QColor("#4C78E8")),
    "WORKING": (QColor("#DDEBFF"), QColor("#3478F6")),
    "DISCONNECTED": (QColor("#ECEEF1"), QColor("#7B818A")),
}
_STATUS_DEFAULT = (QColor("#ECEEF1"), QColor("#747A84"))


class PetSpeechBubble(QFrame):
    dismissed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pet-speech-bubble-eac")
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        if _MAC:
            flags |= Qt.WindowType.WindowDoesNotAcceptFocus
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        if _MAC:
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)

        self.title = ""
        self.detail = ""
        self.state = "IDLE"
        self._anchor_rect = QRect()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._dismiss)
        self.setFixedSize(_CARD_WINDOW_WIDTH, _CARD_WINDOW_HEIGHT)

    # ---------------------------------------------------------- text input
    def show_text(
        self,
        text: str,
        anchor_rect: QRect,
        duration_ms: int = 3200,
        state: str = "IDLE",
    ) -> None:
        text = str(text).strip()
        if not text:
            return
        lines = text.splitlines()
        self.title = lines[0].strip()
        self.detail = " ".join(line.strip() for line in lines[1:] if line.strip())
        if not self.detail:
            self.detail = "Codex · 等待下一次任务"
        self.state = str(state or "IDLE").upper()

        # Match EAC native card width: at least 448px, wider when text needs it.
        title_font = QFont("Microsoft YaHei UI", 11)
        title_font.setWeight(QFont.Weight.DemiBold)
        detail_font = QFont("Microsoft YaHei UI", 9)
        needed = max(
            QFontMetrics(title_font).horizontalAdvance(self.title),
            QFontMetrics(detail_font).horizontalAdvance(self.detail),
        )
        width = max(_CARD_WINDOW_WIDTH, int(needed) + 130)
        self.setFixedSize(width, _CARD_WINDOW_HEIGHT)

        self._anchor_rect = anchor_rect
        self._place(anchor_rect)
        self.show()
        if not _MAC:
            self.raise_()
        self._hide_timer.start(max(500, int(duration_ms)))

    def _dismiss(self) -> None:
        """Hide the active bubble and report the exact timer boundary."""
        was_visible = self.isVisible()
        self.hide()
        if was_visible:
            self.dismissed.emit()

    def reposition(self, anchor_rect: QRect) -> None:
        if self.isVisible():
            self._place(anchor_rect)

    # ------------------------------------------------------------ painting
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        card_width = w - 28
        card_height = _CARD_HEIGHT

        # Reuse the EAC native card geometry exactly.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(17, 24, 39, 13))
        painter.drawRoundedRect(
            _CARD_X + 1, _CARD_Y + 13, card_width - 2, card_height,
            _CARD_RADIUS, _CARD_RADIUS,
        )
        painter.setBrush(QColor(17, 24, 39, 18))
        painter.drawRoundedRect(
            _CARD_X, _CARD_Y + 7, card_width, card_height,
            _CARD_RADIUS, _CARD_RADIUS,
        )
        painter.setPen(QPen(QColor(218, 221, 226, 205), 1))
        painter.setBrush(QColor(252, 252, 253, 248))
        painter.drawRoundedRect(
            _CARD_X, _CARD_Y, card_width, card_height,
            _CARD_RADIUS, _CARD_RADIUS,
        )

        icon_center_x = _CARD_X + card_width - 39
        icon_center_y = _CARD_Y + card_height // 2
        self._draw_status_icon(painter, icon_center_x, icon_center_y)

        text_x = _CARD_X + 24
        text_width = card_width - 102
        title_font = QFont("Microsoft YaHei UI", 11)
        title_font.setWeight(QFont.Weight.DemiBold)
        detail_font = QFont("Microsoft YaHei UI", 9)

        painter.setFont(title_font)
        painter.setPen(QColor("#25282D"))
        title_text = QFontMetrics(title_font).elidedText(
            self.title, Qt.TextElideMode.ElideRight, text_width,
        )
        painter.drawText(
            text_x, _CARD_Y + 15, text_width, 27,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title_text,
        )

        painter.setFont(detail_font)
        painter.setPen(QColor("#747981"))
        detail_text = QFontMetrics(detail_font).elidedText(
            self.detail, Qt.TextElideMode.ElideRight, text_width,
        )
        painter.drawText(
            text_x, _CARD_Y + 43, text_width, 24,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            detail_text,
        )
        painter.end()

    def _draw_status_icon(self, painter: QPainter, center_x: int, center_y: int) -> None:
        background, foreground = _STATUS_COLORS.get(self.state, _STATUS_DEFAULT)
        radius = 23
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)
        pen = QPen(foreground, 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        state = self.state
        if state == "SUCCESS":
            painter.drawLine(center_x - 10, center_y, center_x - 3, center_y + 8)
            painter.drawLine(center_x - 3, center_y + 8, center_x + 12, center_y - 10)
        elif state == "ERROR":
            painter.drawLine(center_x - 8, center_y - 8, center_x + 8, center_y + 8)
            painter.drawLine(center_x + 8, center_y - 8, center_x - 8, center_y + 8)
        elif state == "WAITING":
            painter.drawLine(center_x, center_y - 10, center_x, center_y + 3)
            painter.setBrush(foreground)
            painter.drawEllipse(center_x - 2, center_y + 9, 4, 4)
        elif state in {"THINKING", "WORKING"}:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(foreground)
            for offset in (-9, 0, 9):
                painter.drawEllipse(center_x + offset - 3, center_y - 3, 6, 6)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(foreground)
            painter.drawEllipse(center_x - 5, center_y - 5, 10, 10)

    # ----------------------------------------------------------- placement
    def _place(self, anchor_rect: QRect) -> None:
        if QGuiApplication.primaryScreen() is None:
            return
        avail = QGuiApplication.primaryScreen().availableGeometry()
        gap = 10
        size = self.size()
        centered_x = anchor_rect.left() + (anchor_rect.width() - size.width()) // 2
        candidates = [
            QPoint(centered_x, anchor_rect.top() - size.height() - gap),
            QPoint(anchor_rect.right() + gap, anchor_rect.top() - size.height()),
            QPoint(anchor_rect.left() - size.width() - gap, anchor_rect.top() - size.height()),
            QPoint(centered_x, anchor_rect.bottom() + gap),
        ]
        chosen = candidates[-1]
        for point in candidates:
            if avail.contains(QRect(point, size)):
                chosen = point
                break
        x = min(max(chosen.x(), avail.left()), avail.right() - size.width() + 1)
        y = min(max(chosen.y(), avail.top()), avail.bottom() - size.height() + 1)
        self.move(x, y)
