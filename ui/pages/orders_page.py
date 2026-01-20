from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.card import Card


class OrdersPage(QWidget):
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setSpacing(20)

        left_panel = QVBoxLayout()
        left_panel.setSpacing(18)

        self.input_card = Card("注文入力")
        left_panel.addWidget(self.input_card)
        self._build_inputs(self.input_card.body)

        self.controls_card = Card("操作")
        left_panel.addWidget(self.controls_card)
        self._build_controls(self.controls_card.body)
        left_panel.addStretch()

        right_panel = QVBoxLayout()
        right_panel.setSpacing(18)

        self.status_card = Card("状況")
        right_panel.addWidget(self.status_card)
        self._build_status(self.status_card.body)

        self.log_card = Card("ログ")
        right_panel.addWidget(self.log_card, 1)
        self._build_logs(self.log_card.body)

        layout.addLayout(left_panel, 3)
        layout.addLayout(right_panel, 2)

    def _build_inputs(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)

        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText("例: 7203")
        form.addRow("銘柄コード", self.symbol_input)

        self.side_input = QComboBox()
        self.side_input.addItems(["買入", "売入"])
        form.addRow("売買区分", self.side_input)

        self.order_type_input = QComboBox()
        self.order_type_input.addItems(["成行", "指値"])
        self.order_type_input.currentTextChanged.connect(self._toggle_entry_price)
        form.addRow("成行/価格指定", self.order_type_input)

        self.entry_price_input = QDoubleSpinBox()
        self.entry_price_input.setRange(1.0, 100000.0)
        self.entry_price_input.setDecimals(2)
        self.entry_price_input.setValue(100.0)
        form.addRow("エントリー価格", self.entry_price_input)

        self.profit_price_input = QDoubleSpinBox()
        self.profit_price_input.setRange(1.0, 100000.0)
        self.profit_price_input.setValue(105.0)
        self.profit_price_input.setDecimals(2)
        form.addRow("利確価格", self.profit_price_input)

        self.loss_price_input = QDoubleSpinBox()
        self.loss_price_input.setRange(1.0, 100000.0)
        self.loss_price_input.setValue(95.0)
        self.loss_price_input.setDecimals(2)
        form.addRow("損切価格", self.loss_price_input)

        self.schedule_type_input = QComboBox()
        self.schedule_type_input.addItems(["即時", "予約"])
        self.schedule_type_input.currentTextChanged.connect(self._toggle_schedule)
        form.addRow("予約/即時", self.schedule_type_input)

        self.schedule_time_input = QDateTimeEdit()
        self.schedule_time_input.setCalendarPopup(True)
        self.schedule_time_input.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.schedule_time_input.setDateTime(datetime.now())
        form.addRow("実行日時", self.schedule_time_input)

        layout.addLayout(form)
        self._toggle_entry_price(self.order_type_input.currentText())
        self._toggle_schedule(self.schedule_type_input.currentText())

        demo_controls = QGroupBox("デモ実行パラメータ")
        demo_layout = QFormLayout(demo_controls)
        demo_layout.setHorizontalSpacing(16)
        demo_layout.setVerticalSpacing(10)

        self.poll_interval_input = QDoubleSpinBox()
        self.poll_interval_input.setRange(0.1, 10.0)
        self.poll_interval_input.setSingleStep(0.1)
        self.poll_interval_input.setValue(0.5)
        demo_layout.addRow("ポーリング間隔(秒)", self.poll_interval_input)

        self.fills_after_input = QSpinBox()
        self.fills_after_input.setRange(1, 10)
        self.fills_after_input.setValue(2)
        demo_layout.addRow("約定までの回数", self.fills_after_input)

        layout.addWidget(demo_controls)

    def _build_controls(self, layout: QVBoxLayout) -> None:
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("デモ開始")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start_requested.emit)

        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_requested.emit)

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        layout.addLayout(button_layout)

    def _build_status(self, layout: QVBoxLayout) -> None:
        self.state_label = QLabel("IDLE")
        font = QFont()
        font.setPointSize(22)
        font.setBold(True)
        self.state_label.setFont(font)
        self.state_label.setObjectName("stateLabel")
        layout.addWidget(self.state_label)

        self.final_state_label = QLabel("最終結果: -")
        self.final_state_label.setObjectName("mutedLabel")
        layout.addWidget(self.final_state_label)

        self.log_hint = QLabel("ログを確認して進行状況を追跡できます")
        self.log_hint.setObjectName("mutedLabel")
        layout.addWidget(self.log_hint)

    def _build_logs(self, layout: QVBoxLayout) -> None:
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.log_output)

    def _toggle_entry_price(self, value: str) -> None:
        is_limit = value == "指値"
        self.entry_price_input.setVisible(is_limit)

    def _toggle_schedule(self, value: str) -> None:
        is_reserved = value == "予約"
        self.schedule_time_input.setVisible(is_reserved)