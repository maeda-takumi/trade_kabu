from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFrame,
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
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


from ui.widgets.card import Card


STATUS_LABELS = {
    "READY": "準備中",
    "IDLE": "待機中",
    "ENTRY_WAIT": "エントリー待ち",
    "ENTRY_FILLED": "エントリー約定",
    "EXIT_WAIT": "決済待ち",
    "FORCE_EXITING": "成行決済中",
    "EXIT_FILLED": "決済完了",
    "CANCELED": "キャンセル",
    "ERROR": "エラー",
}

STATUS_VARIANTS = {
    "READY": "neutral",
    "IDLE": "neutral",
    "ENTRY_WAIT": "info",
    "ENTRY_FILLED": "info",
    "EXIT_WAIT": "info",
    "FORCE_EXITING": "warning",
    "EXIT_FILLED": "success",
    "CANCELED": "neutral",
    "ERROR": "danger",
}

ORDER_STATUS_LABELS = {
    "NOT_SENT": "未送信",
    "NEW": "新規",
    "SENT": "送信済",
    "PARTIAL": "一部約定",
    "FILLED": "約定済",
    "CANCELED": "キャンセル",
    "REJECTED": "拒否",
    "ERROR": "エラー",
}

ORDER_STATUS_VARIANTS = {
    "NOT_SENT": "neutral",
    "NEW": "neutral",
    "SENT": "info",
    "PARTIAL": "warning",
    "FILLED": "success",
    "CANCELED": "neutral",
    "REJECTED": "danger",
    "ERROR": "danger",
}


class StatusRowWidget(QFrame):
    def __init__(
        self,
        index: str,
        symbol: str,
        side: str,
        order_type: str,
        schedule: str,
        state_label: str,
        state_variant: str,
        final_label: str,
        final_variant: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("statusItem")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        title = QLabel(f"注文{index} · {symbol}")
        title.setObjectName("statusTitle")
        header_row.addWidget(title)
        header_row.addStretch()
        self.state_badge = self._make_badge(state_label, state_variant)
        header_row.addWidget(self.state_badge)
        layout.addLayout(header_row)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)
        chips_row.addWidget(self._make_chip(side))
        chips_row.addWidget(self._make_chip(order_type))
        chips_row.addWidget(self._make_chip(schedule))
        chips_row.addStretch()
        layout.addLayout(chips_row)

        detail_row = QHBoxLayout()
        detail_row.setSpacing(12)
        profit_label = QLabel("利確注文")
        profit_label.setObjectName("statusMeta")
        detail_row.addWidget(profit_label)
        self.profit_badge = self._make_badge("-", "neutral")
        detail_row.addWidget(self.profit_badge)
        detail_row.addStretch()
        loss_label = QLabel("損切注文")
        loss_label.setObjectName("statusMeta")
        detail_row.addWidget(loss_label)
        self.loss_badge = self._make_badge("-", "neutral")
        detail_row.addWidget(self.loss_badge)
        layout.addLayout(detail_row)

        footer_row = QHBoxLayout()
        footer_row.setSpacing(8)
        footer_label = QLabel("最終結果")
        footer_label.setObjectName("statusMeta")
        footer_row.addWidget(footer_label)
        self.final_badge = self._make_badge(final_label, final_variant)
        footer_row.addWidget(self.final_badge)
        footer_row.addStretch()
        layout.addLayout(footer_row)

    def _make_chip(self, text: str) -> QLabel:
        chip = QLabel(text or "-")
        chip.setObjectName("statusChip")
        return chip

    def _make_badge(self, text: str, variant: str) -> QLabel:
        badge = QLabel(text or "-")
        badge.setObjectName("statusBadge")
        badge.setProperty("variant", variant)
        badge.style().unpolish(badge)
        badge.style().polish(badge)
        return badge

    def update_state(self, label: str, variant: str) -> None:
        self.state_badge.setText(label)
        self.state_badge.setProperty("variant", variant)
        self.state_badge.style().unpolish(self.state_badge)
        self.state_badge.style().polish(self.state_badge)

    def update_final(self, label: str, variant: str) -> None:
        self.final_badge.setText(label)
        self.final_badge.setProperty("variant", variant)
        self.final_badge.style().unpolish(self.final_badge)
        self.final_badge.style().polish(self.final_badge)

    def update_exit_status(
        self, profit_label: str, profit_variant: str, loss_label: str, loss_variant: str
    ) -> None:
        self.profit_badge.setText(profit_label)
        self.profit_badge.setProperty("variant", profit_variant)
        self.profit_badge.style().unpolish(self.profit_badge)
        self.profit_badge.style().polish(self.profit_badge)

        self.loss_badge.setText(loss_label)
        self.loss_badge.setProperty("variant", loss_variant)
        self.loss_badge.style().unpolish(self.loss_badge)
        self.loss_badge.style().polish(self.loss_badge)

class OrdersPage(QWidget):
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setSpacing(20)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_contents = QWidget()
        left_panel = QVBoxLayout(scroll_contents)
        left_panel.setSpacing(18)

        self.input_cards_container = QGridLayout()
        self.input_cards_container.setHorizontalSpacing(18)
        self.input_cards_container.setVerticalSpacing(18)
        self.order_inputs: list[dict[str, QWidget]] = []
        self.input_card_columns = 2

        self.order_count_card = Card("注文数")
        left_panel.addWidget(self.order_count_card)
        self._build_order_count(self.order_count_card.body)

        self.controls_card = Card("操作")
        left_panel.addWidget(self.controls_card)
        self._build_controls(self.controls_card.body)
        left_panel.addLayout(self.input_cards_container)
        left_panel.addStretch()

        scroll_area.setWidget(scroll_contents)

        layout.addWidget(scroll_area, 3)
        right_panel_container = QWidget()
        right_panel_container.setMinimumWidth(360)
        right_panel_container.setMaximumWidth(520)
        right_panel_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        right_panel = QVBoxLayout(right_panel_container)
        right_panel.setSpacing(18)

        self.status_card = Card("状態")
        right_panel.addWidget(self.status_card)
        self._build_status(self.status_card.body)

        right_panel.addStretch()
        layout.addWidget(right_panel_container, 1)

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

        exchange_input = QSpinBox()
        exchange_input.setRange(1, 99)
        exchange_input.setValue(1)
        form.addRow("市場コード", exchange_input)

        qty_input = QSpinBox()
        qty_input.setRange(1, 100000)
        qty_input.setValue(100)
        form.addRow("数量", qty_input)

        side_input = QComboBox()
        side_input.addItem("買入", 1)
        side_input.addItem("売入", 2)
        form.addRow("売買区分", side_input)

        cash_margin_input = QComboBox()
        cash_margin_input.addItem("現物", 1)
        cash_margin_input.addItem("信用", 2)
        form.addRow("現物/信用区分", cash_margin_input)

        margin_trade_type_input = QComboBox()
        margin_trade_type_input.addItem("信用新規", 1)
        margin_trade_type_input.addItem("信用返済", 2)
        form.addRow("信用新規/返済", margin_trade_type_input)
        # TODO: kabuステーションAPI仕様で信用区分が不要な場合は削除する。

        security_type_input = QSpinBox()
        security_type_input.setRange(0, 99)
        security_type_input.setValue(0)
        form.addRow("商品区分コード(SecurityType)", security_type_input)

        account_type_input = QSpinBox()
        account_type_input.setRange(0, 99)
        account_type_input.setValue(0)
        form.addRow("口座種別(AccountType)", account_type_input)

        deliv_type_input = QSpinBox()
        deliv_type_input.setRange(0, 99)
        deliv_type_input.setValue(0)
        form.addRow("受渡区分(DelivType)", deliv_type_input)

        expire_day_input = QSpinBox()
        expire_day_input.setRange(0, 99999999)
        expire_day_input.setValue(0)
        form.addRow("有効期限(ExpireDay)", expire_day_input)

        advanced_toggle = QCheckBox("詳細設定を表示")
        form.addRow("", advanced_toggle)

        advanced_group = QGroupBox("詳細設定")
        advanced_group.setVisible(False)
        advanced_layout = QFormLayout(advanced_group)
        advanced_layout.setHorizontalSpacing(16)
        advanced_layout.setVerticalSpacing(10)

        close_positions_input = QPlainTextEdit()
        close_positions_input.setPlaceholderText("例: HoldID,数量\n123456,100")
        close_positions_input.setMaximumHeight(72)
        advanced_layout.addRow("信用返済(ClosePositions)", close_positions_input)
        
        time_in_force_input = QLineEdit()
        time_in_force_input.setPlaceholderText("例: DAY / IOC")
        form.addRow("執行条件(TimeInForce)", time_in_force_input)

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
        layout.addWidget(advanced_group)

        order_type_input.currentTextChanged.connect(
            lambda value, target=entry_price_input: self._toggle_entry_price(target, value)
        )
        cash_margin_input.currentIndexChanged.connect(
            lambda _, target=margin_trade_type_input, source=cash_margin_input, group=advanced_group, toggle=advanced_toggle: (
                self._toggle_margin_trade_type(target, source),
                self._toggle_advanced_settings(group, toggle, source, target),
            )
        )
        margin_trade_type_input.currentIndexChanged.connect(
            lambda _, target=advanced_group, toggle=advanced_toggle, cash=cash_margin_input, margin=margin_trade_type_input: (
                self._toggle_advanced_settings(target, toggle, cash, margin)
            )
        )
        advanced_toggle.stateChanged.connect(
            lambda _, target=advanced_group, toggle=advanced_toggle, cash=cash_margin_input, margin=margin_trade_type_input: (
                self._toggle_advanced_settings(target, toggle, cash, margin)
            )
        )
        schedule_type_input.currentTextChanged.connect(
            lambda value, target=schedule_time_input: self._toggle_schedule(target, value)
        )
        self._toggle_entry_price(entry_price_input, order_type_input.currentText())
        self._toggle_margin_trade_type(margin_trade_type_input, cash_margin_input)
        self._toggle_advanced_settings(
            advanced_group, advanced_toggle, cash_margin_input, margin_trade_type_input
        )
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
            "exchange_input": exchange_input,
            "qty_input": qty_input,
            "side_input": side_input,
            "cash_margin_input": cash_margin_input,
            "margin_trade_type_input": margin_trade_type_input,
            "security_type_input": security_type_input,
            "account_type_input": account_type_input,
            "deliv_type_input": deliv_type_input,
            "expire_day_input": expire_day_input,
            "close_positions_input": close_positions_input,
            "advanced_toggle": advanced_toggle,
            "advanced_group": advanced_group,
            "time_in_force_input": time_in_force_input,
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
        self.mode_input = QComboBox()
        self.mode_input.addItems(["デモ", "実運用"])
        button_layout.addWidget(self.mode_input)
        self.start_button = QPushButton("開始")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start_requested.emit)

        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_requested.emit)

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        layout.addLayout(button_layout)

    def _build_status(self, layout: QVBoxLayout) -> None:
        self.status_list = QListWidget()
        self.status_list.setObjectName("statusList")
        self.status_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.status_list.setSpacing(12)
        layout.addWidget(self.status_list)
        self.status_rows: list[StatusRowWidget] = []
        self.status_items: list[QListWidgetItem] = []

    def reset_status_rows(self, rows: list[dict[str, str]]) -> None:
        self.status_list.clear()
        self.status_rows.clear()
        self.status_items.clear()
        for data in rows:
            state_label, state_variant = self._localize_state("READY")
            final_label, final_variant = self._localize_state("-")
            profit_label, profit_variant = self._localize_order_status("NOT_SENT")
            loss_label, loss_variant = self._localize_order_status("NOT_SENT")

            widget = StatusRowWidget(
                index=data.get("index", "-"),
                symbol=data.get("symbol", "-"),
                side=data.get("side", "-"),
                order_type=data.get("order_type", "-"),
                schedule=data.get("schedule", "-"),
                state_label=state_label,
                state_variant=state_variant,
                final_label=final_label,
                final_variant=final_variant,
            )
            widget.update_exit_status(
                profit_label, profit_variant, loss_label, loss_variant
            )
            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint())
            self.status_list.addItem(item)
            self.status_list.setItemWidget(item, widget)
            self.status_rows.append(widget)
            self.status_items.append(item)

    def update_status_row(self, row_index: int, state: str) -> None:
        if row_index < 0 or row_index >= len(self.status_rows):
            return
        label, variant = self._localize_state(state)
        self.status_rows[row_index].update_state(label, variant)
        self._refresh_status_item(row_index)

    def update_exit_rows(self, row_index: int, profit_status: str, loss_status: str) -> None:
        if row_index < 0 or row_index >= len(self.status_rows):
            return
        profit_label, profit_variant = self._localize_order_status(profit_status)
        loss_label, loss_variant = self._localize_order_status(loss_status)
        self.status_rows[row_index].update_exit_status(
            profit_label, profit_variant, loss_label, loss_variant
        )
        self._refresh_status_item(row_index)

    def update_final_row(self, row_index: int, state: str) -> None:
        if row_index < 0 or row_index >= len(self.status_rows):
            return
        label, variant = self._localize_state(state)
        self.status_rows[row_index].update_final(label, variant)
        self._refresh_status_item(row_index)

    def _toggle_entry_price(self, entry_price_input: QDoubleSpinBox, value: str) -> None:
        is_limit = value == "指値"
        entry_price_input.setVisible(is_limit)

    def _toggle_schedule(self, schedule_time_input: QDateTimeEdit, value: str) -> None:
        is_reserved = value == "予約"
        schedule_time_input.setVisible(is_reserved)

    def _toggle_margin_trade_type(
        self, margin_trade_type_input: QComboBox, cash_margin_input: QComboBox
    ) -> None:
        is_margin = cash_margin_input.currentData() == 2
        margin_trade_type_input.setVisible(is_margin)

    def _toggle_advanced_settings(
        self,
        advanced_group: QGroupBox,
        advanced_toggle: QCheckBox,
        cash_margin_input: QComboBox,
        margin_trade_type_input: QComboBox,
    ) -> None:
        is_margin = cash_margin_input.currentData() == 2
        is_repay = margin_trade_type_input.currentData() == 2
        advanced_group.setVisible(advanced_toggle.isChecked() and is_margin and is_repay)
        
    def _localize_state(self, state: str) -> tuple[str, str]:
        key = state.upper() if state else "-"
        label = STATUS_LABELS.get(key, state if state else "-")
        variant = STATUS_VARIANTS.get(key, "neutral")
        return label, variant
    
    def _localize_order_status(self, status: str) -> tuple[str, str]:
        key = status.upper() if status else "NOT_SENT"
        label = ORDER_STATUS_LABELS.get(key, status if status else "-")
        variant = ORDER_STATUS_VARIANTS.get(key, "neutral")
        return label, variant

    def _refresh_status_item(self, row_index: int) -> None:
        if row_index < 0 or row_index >= len(self.status_items):
            return
        item = self.status_items[row_index]
        widget = self.status_rows[row_index]
        item.setSizeHint(widget.sizeHint())

    def _update_order_cards(self, count: int) -> None:
        self._clear_layout(self.input_cards_container)
        self.order_inputs.clear()
        for index in range(count):
            title = "注文入力" if index == 0 else f"注文入力 {index + 1}"
            card = Card(title)
            row = index // self.input_card_columns
            col = index % self.input_card_columns
            self.input_cards_container.addWidget(card, row, col)
            inputs = self._build_inputs(card.body)
            self.order_inputs.append(inputs)

            if index == 0:
                self.symbol_input = inputs["symbol_input"]
                self.exchange_input = inputs["exchange_input"]
                self.qty_input = inputs["qty_input"]
                self.side_input = inputs["side_input"]
                self.cash_margin_input = inputs["cash_margin_input"]
                self.margin_trade_type_input = inputs["margin_trade_type_input"]
                self.security_type_input = inputs["security_type_input"]
                self.account_type_input = inputs["account_type_input"]
                self.deliv_type_input = inputs["deliv_type_input"]
                self.expire_day_input = inputs["expire_day_input"]
                self.time_in_force_input = inputs["time_in_force_input"]               
                self.order_type_input = inputs["order_type_input"]
                self.entry_price_input = inputs["entry_price_input"]
                self.profit_price_input = inputs["profit_price_input"]
                self.loss_price_input = inputs["loss_price_input"]
                self.schedule_type_input = inputs["schedule_type_input"]
                self.schedule_time_input = inputs["schedule_time_input"]
                self.poll_interval_input = inputs["poll_interval_input"]
                self.fills_after_input = inputs["fills_after_input"]
        for col in range(self.input_card_columns):
            self.input_cards_container.setColumnStretch(col, 1)
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
