from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QLabel, QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from ui.pages.history_page import HistoryPage
from ui.pages.orders_page import OrdersPage
from ui.pages.settings_page import SettingsPage
from ui.widgets.sidebar import Sidebar
from ui.workers.demo_worker import DemoInputs, DemoWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AutoTrader Demo UI")
        self.setMinimumSize(1200, 720)
        self.worker: DemoWorker | None = None

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
        self.orders_page.start_requested.connect(self._start_demo)
        self.orders_page.stop_requested.connect(self._stop_demo)

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

    def _collect_inputs(self) -> DemoInputs:
        entry_order_type = (
            "MARKET" if self.orders_page.order_type_input.currentText() == "成行" else "LIMIT"
        )
        entry_price = (
            self.orders_page.entry_price_input.value() if entry_order_type == "LIMIT" else None
        )
        schedule_type = self.orders_page.schedule_type_input.currentText()
        scheduled_epoch = None
        if schedule_type == "予約":
            scheduled_epoch = self.orders_page.schedule_time_input.dateTime().toSecsSinceEpoch()
        return DemoInputs(
            symbol_code=self.orders_page.symbol_input.text().strip() or "N/A",
            entry_order_type=entry_order_type,
            entry_price=entry_price,
            profit_price=self.orders_page.profit_price_input.value(),
            loss_price=self.orders_page.loss_price_input.value(),
            schedule_type=schedule_type,
            scheduled_epoch=scheduled_epoch,
            side=self.orders_page.side_input.currentText(),
            poll_interval_sec=self.orders_page.poll_interval_input.value(),
            fills_after_polls=self.orders_page.fills_after_input.value(),
            force_exit_poll_interval_sec=self.settings_page.force_poll_interval_input.value(),
            force_exit_max_duration_sec=self.settings_page.force_max_duration_input.value(),
            force_exit_start_before_close_min=self.settings_page.force_start_before_input.value(),
            force_exit_deadline_before_close_min=self.settings_page.force_deadline_before_input.value(),
        )

    def _start_demo(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        inputs = self._collect_inputs()
        self.orders_page.log_output.clear()
        self.orders_page.final_state_label.setText("最終結果: -")

        self.worker = DemoWorker(inputs)
        self.worker.log_message.connect(self.orders_page.log_output.appendPlainText)
        self.worker.state_changed.connect(self.orders_page.state_label.setText)
        self.worker.finished_state.connect(self._on_demo_finished)
        self.worker.start()

        self.orders_page.start_button.setEnabled(False)
        self.orders_page.stop_button.setEnabled(True)

    def _stop_demo(self) -> None:
        if self.worker:
            self.worker.stop()
        self.orders_page.stop_button.setEnabled(False)

    def _on_demo_finished(self, state: str) -> None:
        self.orders_page.final_state_label.setText(f"最終結果: {state}")
        self.orders_page.start_button.setEnabled(True)
        self.orders_page.stop_button.setEnabled(False)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()