from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import time
from typing import Optional

from PySide6.QtCore import QThread, Signal

from autotrader import (
    AutoTrader,
    AutoTraderConfig,
    AutoTraderState,
    DemoBroker,
    Order,
    OrderRole,
)


@dataclass
class DemoInputs:
    symbol_code: str
    entry_order_type: str
    entry_price: Optional[float]
    profit_price: float
    loss_price: float
    schedule_type: str
    scheduled_epoch: Optional[float]
    side: str
    poll_interval_sec: float
    fills_after_polls: int
    force_exit_poll_interval_sec: float
    force_exit_max_duration_sec: float
    force_exit_start_before_close_min: int
    force_exit_deadline_before_close_min: int


class DemoWorker(QThread):
    log_message = Signal(str)
    state_changed = Signal(str)
    exit_status_changed = Signal(str, str)
    finished_state = Signal(str)

    def __init__(self, inputs: DemoInputs, parent: Optional[object] = None) -> None:
        super().__init__(parent=parent)
        self.inputs = inputs
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def _wait_until_scheduled(self) -> bool:
        if not self.inputs.scheduled_epoch:
            return True
        while True:
            if self._stop_requested:
                self.log_message.emit("[demo] stop requested before scheduled start")
                return False
            now = time.time()
            if now >= self.inputs.scheduled_epoch:
                return True
            time.sleep(0.5)

    def run(self) -> None:
        config = AutoTraderConfig(
            force_exit_poll_interval_sec=self.inputs.force_exit_poll_interval_sec,
            force_exit_max_duration_sec=self.inputs.force_exit_max_duration_sec,
            force_exit_start_before_close_min=self.inputs.force_exit_start_before_close_min,
            force_exit_deadline_before_close_min=self.inputs.force_exit_deadline_before_close_min,
        )
        broker = DemoBroker(fills_after_polls=self.inputs.fills_after_polls)
        trader = AutoTrader(broker, config=config)
        entry_price = (
            self.inputs.entry_price if self.inputs.entry_order_type == "LIMIT" else None
        )        
        entry_price = (
            self.inputs.entry_price if self.inputs.entry_order_type == "LIMIT" else None
        )
        entry_order = Order(
            role=OrderRole.ENTRY,
            order_type=self.inputs.entry_order_type,
            qty=1,
            price=entry_price,
        )

        self.log_message.emit(
            "[demo] setup: "
            f"symbol={self.inputs.symbol_code}, side={self.inputs.side}, "
            f"order_type={self.inputs.entry_order_type}, entry_price={self.inputs.entry_price}, "
            f"profit={self.inputs.profit_price}, loss={self.inputs.loss_price}"
        )

        if self.inputs.schedule_type == "予約" and self.inputs.scheduled_epoch:
            scheduled_at = datetime.fromtimestamp(self.inputs.scheduled_epoch)
            self.log_message.emit(
                f"[demo] scheduled start at {scheduled_at:%Y-%m-%d %H:%M}"
            )
            if not self._wait_until_scheduled():
                self.finished_state.emit("CANCELED")
                return
        else:
            self.log_message.emit("[demo] start immediately")

        self.log_message.emit(f"[demo] state={trader.state.name} -> start_trade")
        trader.start_trade(
            entry_order,
            profit_price=self.inputs.profit_price,
            loss_price=self.inputs.loss_price,
        )
        last_state = trader.state
        self.state_changed.emit(trader.state.name)
        self.log_message.emit(f"[demo] state={trader.state.name}")
        self._emit_exit_statuses(trader, None)

        stopping = False
        last_exit_statuses: Optional[tuple[str, str]] = None
        while trader.state not in (AutoTraderState.EXIT_FILLED, AutoTraderState.ERROR):
            if self._stop_requested:
                self.log_message.emit("[demo] stop requested by user")
                if trader.state in (AutoTraderState.IDLE, AutoTraderState.ENTRY_WAIT):
                    trader.cancel_all_orders()
                    self.state_changed.emit(trader.state.name)
                    self.finished_state.emit("CANCELED")
                    return
                if not stopping:
                    trader.force_exit_market()
                    stopping = True
                    if trader.state != last_state:
                        self.log_message.emit(
                            f"[demo] state={last_state.name} -> {trader.state.name}"
                        )
                        last_state = trader.state
                        self.state_changed.emit(trader.state.name)
            trader.poll()
            if trader.state != last_state:
                self.log_message.emit(
                    f"[demo] state={last_state.name} -> {trader.state.name}"
                )
                last_state = trader.state
                self.state_changed.emit(trader.state.name)
            current_exit_statuses = self._emit_exit_statuses(trader, last_exit_statuses)
            if current_exit_statuses is not None:
                last_exit_statuses = current_exit_statuses
            time.sleep(self.inputs.poll_interval_sec)

        self.log_message.emit(f"[demo] completed with state={trader.state.name}")
        self.state_changed.emit(trader.state.name)
        self._emit_exit_statuses(trader, last_exit_statuses)
        self.finished_state.emit(trader.state.name)

    def _emit_exit_statuses(
        self, trader: AutoTrader, previous: Optional[tuple[str, str]]
    ) -> Optional[tuple[str, str]]:
        profit_status = (
            trader.exit_profit_order.status.name
            if trader.exit_profit_order
            else "NOT_SENT"
        )
        loss_status = (
            trader.exit_loss_order.status.name if trader.exit_loss_order else "NOT_SENT"
        )
        current = (profit_status, loss_status)
        if current != previous:
            self.exit_status_changed.emit(*current)
        return current