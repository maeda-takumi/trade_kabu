from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
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

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        scroll_contents = QWidget()
        left_panel = QVBoxLayout(scroll_contents)
        left_panel.setSpacing(18)

        self.input_cards_container = QGridLayout()
        self.input_cards_container.setHorizontalSpacing(18)
        self.input_cards_container.setVerticalSpacing(18)
        self.order_inputs: list[dict[str, QWidget]] = []
        self.input_card_columns = 2
        self.input_card_width = 360

        self.order_count_card = Card("注文数")
        left_panel.addWidget(self.order_count_card)
        self._build_order_count(self.order_count_card.body)

        self.controls_card = Card("操作")
        left_panel.addWidget(self.controls_card)
        self._build_controls(self.controls_card.body)
        left_panel.addLayout(self.input_cards_container)
        left_panel.addStretch()

        scroll_area.setWidget(scroll_contents)

        layout.addWidget(scroll_area)
        right_panel = QVBoxLayout()
        right_panel.setSpacing(18)

        self.status_card = Card("状態")
        right_panel.addWidget(self.status_card)
        self._build_status(self.status_card.body)

        self.log_card = Card("ログ")
        right_panel.addWidget(self.log_card)
        self._build_log(self.log_card.body)

        right_panel.addStretch()
        layout.addLayout(right_panel, 1)

    def _build_order_count(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)

        self.order_count_input = QSpinBox()
        self.order_count_input.setRange(1, 5)
        self.order_count_input.setValue(1)
        self.order_count_input.valueChanged.connect(self._update_order_cards)
        form.addRow("注文数", self.order_count_input)

        layout.addLayout(form)
        self._update_order_cards(self.order_count_input.value())

    def _build_inputs(self, layout: QVBoxLayout) -> dict[str, QWidget]:
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)

        symbol_input = QLineEdit()
        symbol_input.setPlaceholderText("例: 7203")
        form.addRow("銘柄コード", symbol_input)

        side_input = QComboBox()
        side_input.addItems(["買入", "売入"])
        form.addRow("売買区分", side_input)

        order_type_input = QComboBox()
        order_type_input.addItems(["成行", "指値"])
        form.addRow("成行/価格指定", order_type_input)

        entry_price_input = QDoubleSpinBox()
        entry_price_input.setRange(1.0, 100000.0)
        entry_price_input.setDecimals(2)
        entry_price_input.setValue(100.0)
        form.addRow("エントリー価格", entry_price_input)

        profit_price_input = QDoubleSpinBox()
        profit_price_input.setRange(1.0, 100000.0)
        profit_price_input.setValue(105.0)
        profit_price_input.setDecimals(2)
        form.addRow("利確価格", profit_price_input)

        loss_price_input = QDoubleSpinBox()
        loss_price_input.setRange(1.0, 100000.0)
        loss_price_input.setValue(95.0)
        loss_price_input.setDecimals(2)
        form.addRow("損切価格", loss_price_input)

        schedule_type_input = QComboBox()
        schedule_type_input.addItems(["即時", "予約"])
        form.addRow("予約/即時", schedule_type_input)

        schedule_time_input = QDateTimeEdit()
        schedule_time_input.setCalendarPopup(True)
        schedule_time_input.setDisplayFormat("yyyy-MM-dd HH:mm")
        schedule_time_input.setDateTime(datetime.now())
        form.addRow("実行日時", schedule_time_input)

        layout.addLayout(form)

        order_type_input.currentTextChanged.connect(
            lambda value, target=entry_price_input: self._toggle_entry_price(target, value)
        )
        schedule_type_input.currentTextChanged.connect(
            lambda value, target=schedule_time_input: self._toggle_schedule(target, value)
        )
        self._toggle_entry_price(entry_price_input, order_type_input.currentText())
        self._toggle_schedule(schedule_time_input, schedule_type_input.currentText())

        demo_controls = QGroupBox("デモ実行パラメータ")
        demo_layout = QFormLayout(demo_controls)
        demo_layout.setHorizontalSpacing(16)
        demo_layout.setVerticalSpacing(10)

        poll_interval_input = QDoubleSpinBox()
        poll_interval_input.setRange(0.1, 10.0)
        poll_interval_input.setSingleStep(0.1)
        poll_interval_input.setValue(0.5)
        demo_layout.addRow("ポーリング間隔(秒)", poll_interval_input)

        fills_after_input = QSpinBox()
        fills_after_input.setRange(1, 10)
        fills_after_input.setValue(2)
        demo_layout.addRow("約定までの回数", fills_after_input)

        layout.addWidget(demo_controls)
        return {
            "symbol_input": symbol_input,
            "side_input": side_input,
            "order_type_input": order_type_input,
            "entry_price_input": entry_price_input,
            "profit_price_input": profit_price_input,
            "loss_price_input": loss_price_input,
            "schedule_type_input": schedule_type_input,
            "schedule_time_input": schedule_time_input,
            "poll_interval_input": poll_interval_input,
            "fills_after_input": fills_after_input,
        }

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
        self.state_label = QLabel("現在状態: -")
        self.state_label.setObjectName("stateLabel")
        self.final_state_label = QLabel("最終結果: -")
        self.final_state_label.setObjectName("mutedLabel")
        layout.addWidget(self.state_label)
        layout.addWidget(self.final_state_label)

    def _build_log(self, layout: QVBoxLayout) -> None:
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(320)
        layout.addWidget(self.log_output)
    
    def _toggle_entry_price(self, entry_price_input: QDoubleSpinBox, value: str) -> None:
        is_limit = value == "指値"
        entry_price_input.setVisible(is_limit)

    def _toggle_schedule(self, schedule_time_input: QDateTimeEdit, value: str) -> None:
        is_reserved = value == "予約"
        schedule_time_input.setVisible(is_reserved)

    def _update_order_cards(self, count: int) -> None:
        self._clear_layout(self.input_cards_container)
        self.order_inputs.clear()
        for index in range(count):
            title = "注文入力" if index == 0 else f"注文入力 {index + 1}"
            card = Card(title)
            card.setFixedWidth(self.input_card_width)
            row = index // self.input_card_columns
            col = index % self.input_card_columns
            self.input_cards_container.addWidget(card, row, col)
            inputs = self._build_inputs(card.body)
            self.order_inputs.append(inputs)

            if index == 0:
                self.symbol_input = inputs["symbol_input"]
                self.side_input = inputs["side_input"]
                self.order_type_input = inputs["order_type_input"]
                self.entry_price_input = inputs["entry_price_input"]
                self.profit_price_input = inputs["profit_price_input"]
                self.loss_price_input = inputs["loss_price_input"]
                self.schedule_type_input = inputs["schedule_type_input"]
                self.schedule_time_input = inputs["schedule_time_input"]
                self.poll_interval_input = inputs["poll_interval_input"]
                self.fills_after_input = inputs["fills_after_input"]
        self.input_cards_container.setColumnStretch(self.input_card_columns, 1)
        self.input_cards_container.setRowStretch(
            (count - 1) // self.input_card_columns + 1, 1
        )

    @staticmethod
    def _clear_layout(layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.setParent(None)
            elif child_layout is not None:
                OrdersPage._clear_layout(child_layout)
