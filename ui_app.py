from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QLabel, QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from ui.pages.history_page import HistoryPage
from ui.pages.orders_page import OrdersPage
from ui.pages.settings_page import SettingsPage
from ui.widgets.sidebar import Sidebar
from ui.workers.demo_worker import TradeInputs, DemoWorker
from ui.workers.live_worker import LiveWorker

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AutoTrader Demo UI")
        self.setMinimumSize(1900, 950)
        self.workers: list[DemoWorker] = []

        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QHBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar)

        content_wrapper = QWidget()
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(32, 28, 32, 28)
        content_layout.setSpacing(20)

        header = QLabel("AutoTrader Console")
        header.setObjectName("headerTitle")
        content_layout.addWidget(header)

        self.stack = QStackedWidget()
        self.settings_page = SettingsPage()
        self.orders_page = OrdersPage()
        self.history_page = HistoryPage()

        self.stack.addWidget(self.settings_page)
        self.stack.addWidget(self.orders_page)
        self.stack.addWidget(self.history_page)
        content_layout.addWidget(self.stack, 1)

        self.sidebar.list_widget.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.orders_page.start_requested.connect(self._start_trade)
        self.orders_page.stop_requested.connect(self._stop_trade)


        main_layout.addWidget(content_wrapper, 1)
        self._apply_style()
        self.sidebar.list_widget.setCurrentRow(1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background-color: #F5F7FA;
                color: #0F172A;
                font-size: 14px;
            }
            QWidget#sidebar {
                background-color: #0F172A;
            }
            QLabel#sidebarBrand {
                color: #FFFFFF;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#sidebarMeta {
                color: #94A3B8;
                font-size: 12px;
            }
            QListWidget#sidebarList {
                background: transparent;
                border: none;
                color: #E2E8F0;
            }
            QListWidget#sidebarList::item {
                padding: 10px 12px;
                border-radius: 10px;
            }
            QListWidget#sidebarList::item:selected {
                background: #2563EB;
                color: #FFFFFF;
            }
            QLabel#headerTitle {
                font-size: 26px;
                font-weight: 700;
                color: #0F172A;
            }
            QFrame#card {
                background-color: #FFFFFF;
                border-radius: 18px;
            }
            QListWidget#statusList {
                background: transparent;
                border: none;
            }
            QFrame#statusItem {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 16px;
            }
            QLabel#statusTitle {
                font-size: 15px;
                font-weight: 600;
                color: #0F172A;
            }
            QLabel#statusMeta {
                color: #64748B;
                font-size: 12px;
            }
            QLabel#statusChip {
                background: #E2E8F0;
                color: #334155;
                border-radius: 10px;
                padding: 2px 8px;
                font-size: 12px;
            }
            QLabel#statusBadge {
                background: #DBEAFE;
                color: #1D4ED8;
                border-radius: 10px;
                padding: 2px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#statusBadge[variant="info"] {
                background: #DBEAFE;
                color: #1D4ED8;
            }
            QLabel#statusBadge[variant="success"] {
                background: #DCFCE7;
                color: #166534;
            }
            QLabel#statusBadge[variant="danger"] {
                background: #FEE2E2;
                color: #991B1B;
            }
            QLabel#statusBadge[variant="warning"] {
                background: #FEF3C7;
                color: #92400E;
            }
            QLabel#statusBadge[variant="neutral"] {
                background: #E2E8F0;
                color: #334155;
            }
            QListWidget#statusList {
                background: transparent;
                border: none;
            }
            QFrame#statusItem {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 16px;
            }
            QLabel#statusTitle {
                font-size: 15px;
                font-weight: 600;
                color: #0F172A;
            }
            QLabel#statusMeta {
                color: #64748B;
                font-size: 12px;
            }
            QLabel#statusChip {
                background: #E2E8F0;
                color: #334155;
                border-radius: 10px;
                padding: 2px 8px;
                font-size: 12px;
            }
            QLabel#statusBadge {
                background: #DBEAFE;
                color: #1D4ED8;
                border-radius: 10px;
                padding: 2px 10px;
                font-size: 12px;
                font-weight: 600;
            }
            QLabel#statusBadge[variant="success"] {
                background: #DCFCE7;
                color: #166534;
            }
            QLabel#statusBadge[variant="danger"] {
                background: #FEE2E2;
                color: #991B1B;
            }
            QLabel#statusBadge[variant="warning"] {
                background: #FEF3C7;
                color: #92400E;
            }
            QLabel#statusBadge[variant="neutral"] {
                background: #E2E8F0;
                color: #334155;
            }
            QLabel#cardTitle {
                font-size: 16px;
                font-weight: 600;
                color: #1F2937;
            }
            QLabel#mutedLabel {
                color: #6B7280;
            }
            QLabel#stateLabel {
                color: #2563EB;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QComboBox, QDateTimeEdit {
                background: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 10px;
                padding: 6px 10px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QPushButton {
                border: none;
                border-radius: 12px;
                padding: 10px 18px;
                background: #E5E7EB;
            }
            QPushButton#primaryButton {
                background: #2563EB;
                color: #FFFFFF;
            }
            QPushButton:disabled {
                background: #D1D5DB;
                color: #9CA3AF;
            }
            QGroupBox {
                border: 1px solid #E5E7EB;
                border-radius: 12px;
                padding: 8px;
                font-weight: 600;
                background: #F9FAFB;
            }
            """
        )

    def _collect_inputs(self) -> list[TradeInputs]:
        inputs: list[TradeInputs] = []
        for input_set in self.orders_page.order_inputs:
            security_type = input_set["security_type_input"].value() or None
            account_type = input_set["account_type_input"].value() or None
            deliv_type = input_set["deliv_type_input"].value() or None
            expire_day = input_set["expire_day_input"].value() or None
            time_in_force = input_set["time_in_force_input"].text().strip() or None
            entry_order_type = (
                "MARKET" if input_set["order_type_input"].currentText() == "成行" else "LIMIT"
            )
            entry_price = (
                input_set["entry_price_input"].value() if entry_order_type == "LIMIT" else None
            )
            schedule_type = input_set["schedule_type_input"].currentText()
            scheduled_epoch = None
            if schedule_type == "予約":
                scheduled_epoch = input_set["schedule_time_input"].dateTime().toSecsSinceEpoch()
            side_label = input_set["side_input"].currentText()
            side_code = input_set["side_input"].currentData()
            cash_margin = input_set["cash_margin_input"].currentData()
            margin_trade_type = (
                input_set["margin_trade_type_input"].currentData()
                if cash_margin == 2
                else None
            )                
            inputs.append(
                TradeInputs(
                    symbol_code=input_set["symbol_input"].text().strip() or "N/A",
                    exchange=input_set["exchange_input"].value(),
                    qty=input_set["qty_input"].value(),
                    entry_order_type=entry_order_type,
                    entry_price=entry_price,
                    profit_price=input_set["profit_price_input"].value(),
                    loss_price=input_set["loss_price_input"].value(),
                    schedule_type=schedule_type,
                    scheduled_epoch=scheduled_epoch,
                    side_label=side_label,
                    side_code=side_code,
                    cash_margin=cash_margin,
                    margin_trade_type=margin_trade_type,
                    security_type=security_type,
                    account_type=account_type,
                    deliv_type=deliv_type,
                    expire_day=expire_day,
                    time_in_force=time_in_force,
                    poll_interval_sec=input_set["poll_interval_input"].value(),
                    fills_after_polls=input_set["fills_after_input"].value(),
                    force_exit_poll_interval_sec=self.settings_page.force_poll_interval_input.value(),
                    force_exit_max_duration_sec=self.settings_page.force_max_duration_input.value(),
                    force_exit_start_before_close_min=self.settings_page.force_start_before_input.value(),
                    force_exit_deadline_before_close_min=self.settings_page.force_deadline_before_input.value(),
                    force_exit_use_market_close=self.settings_page.force_exit_use_close_input.isChecked(),
                    market_close_hour=self.settings_page.market_close_hour_input.value(),
                    market_close_minute=self.settings_page.market_close_minute_input.value(),
                    base_url=self.settings_page.base_url_input.text().strip(),
                    api_password=self.settings_page.api_password_input.text().strip(),
                    trading_password=self.settings_page.trading_password_input.text().strip(),
                    api_token=self.settings_page.api_token_input.text().strip() or None,
                )
            )
        return inputs

    def _start_trade(self) -> None:
        if any(worker.isRunning() for worker in self.workers):
            return
        inputs_list = self._collect_inputs()
        self.workers.clear()
        mode = self.orders_page.mode_input.currentText()
        is_live = mode == "実運用"
        rows = []
        for index, inputs in enumerate(inputs_list, start=1):
            rows.append(
                {
                    "index": str(index),
                    "symbol": inputs.symbol_code,
                    "side": inputs.side_label,
                    "order_type": "成行" if inputs.entry_order_type == "MARKET" else "指値",
                    "schedule": inputs.schedule_type,
                }
            )
        self.orders_page.reset_status_rows(rows)

        for index, inputs in enumerate(inputs_list):
            worker = LiveWorker(inputs) if is_live else DemoWorker(inputs)
            worker.state_changed.connect(
                lambda state, row=index: self.orders_page.update_status_row(row, state)
            )
            worker.finished_state.connect(
                lambda state, row=index: self._on_demo_finished(row, state)
            )
            worker.exit_status_changed.connect(
                lambda profit, loss, row=index: self.orders_page.update_exit_rows(
                    row, profit, loss
                )
            )
            worker.log_message.connect(self.history_page.append_log)
            worker.start()
            self.workers.append(worker)

        self.orders_page.start_button.setEnabled(False)
        self.orders_page.stop_button.setEnabled(True)

    def _stop_trade(self) -> None:
        for worker in self.workers:
            worker.stop()
        self.orders_page.stop_button.setEnabled(False)

    def _on_demo_finished(self, row: int, state: str) -> None:
        self.orders_page.update_final_row(row, state)
        if all(not worker.isRunning() for worker in self.workers):
            self.orders_page.start_button.setEnabled(True)
            self.orders_page.stop_button.setEnabled(False)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()