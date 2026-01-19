from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
import time
from typing import Dict, Optional


class AutoTraderState(Enum):
    IDLE = auto()
    ENTRY_WAIT = auto()
    ENTRY_FILLED = auto()
    EXIT_WAIT = auto()
    FORCE_EXITING = auto()
    EXIT_FILLED = auto()
    ERROR = auto()


class OrderRole(Enum):
    ENTRY = auto()
    EXIT_PROFIT = auto()
    EXIT_LOSS = auto()
    EXIT_MARKET = auto()


class OrderStatus(Enum):
    NEW = auto()
    SENT = auto()
    PARTIAL = auto()
    FILLED = auto()
    CANCELED = auto()
    REJECTED = auto()
    ERROR = auto()


class BrokerInterface:
    def place_order(self, order: "Order") -> str:
        raise NotImplementedError

    def poll_order(self, order: "Order") -> OrderStatus:
        raise NotImplementedError

    def cancel_order(self, order: "Order") -> bool:
        raise NotImplementedError


@dataclass
class AutoTraderConfig:
    force_exit_poll_interval_sec: float = 3.0
    force_exit_max_duration_sec: float = 600.0
    force_exit_start_before_close_min: int = 30
    force_exit_deadline_before_close_min: int = 10


@dataclass
class Order:
    role: OrderRole
    order_type: str
    qty: float
    price: Optional[float] = None
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.NEW
    created_at: float = field(default_factory=time.time)

    def place(self, broker: BrokerInterface) -> None:
        self.order_id = broker.place_order(self)
        self.status = OrderStatus.SENT

    def poll_status(self, broker: BrokerInterface) -> OrderStatus:
        self.status = broker.poll_order(self)
        return self.status

    def cancel(self, broker: BrokerInterface) -> bool:
        success = broker.cancel_order(self)
        if success:
            self.status = OrderStatus.CANCELED
        return success


class DemoBroker(BrokerInterface):
    def __init__(self, fills_after_polls: int = 2) -> None:
        self.fills_after_polls = fills_after_polls
        self._poll_counts: Dict[str, int] = {}
        self._next_id = 1

    def place_order(self, order: Order) -> str:
        order_id = f"DEMO-{self._next_id}"
        self._next_id += 1
        self._poll_counts[order_id] = 0
        return order_id

    def poll_order(self, order: Order) -> OrderStatus:
        if order.order_id is None:
            return OrderStatus.ERROR
        self._poll_counts[order.order_id] += 1
        if self._poll_counts[order.order_id] > self.fills_after_polls:
            return OrderStatus.FILLED
        return OrderStatus.SENT

    def cancel_order(self, order: Order) -> bool:
        return True


class AutoTrader:
    def __init__(self, broker: BrokerInterface, config: Optional[AutoTraderConfig] = None) -> None:
        self.broker = broker
        self.config = config or AutoTraderConfig()
        self.state = AutoTraderState.IDLE
        self.orders: Dict[OrderRole, Order] = {}
        self.entry_order: Optional[Order] = None
        self.exit_profit_order: Optional[Order] = None
        self.exit_loss_order: Optional[Order] = None
        self._force_exit_started_at: Optional[float] = None
        self._last_force_exit_poll: Optional[float] = None

    def start_trade(self, entry_order: Order) -> None:
        if self.state != AutoTraderState.IDLE:
            self.state = AutoTraderState.ERROR
            return
        self.entry_order = entry_order
        self.orders[entry_order.role] = entry_order
        entry_order.place(self.broker)
        self.state = AutoTraderState.ENTRY_WAIT

    def on_order_event(self, order: Order, status: OrderStatus) -> None:
        if self.state == AutoTraderState.ERROR:
            return
        if order.role == OrderRole.ENTRY and status == OrderStatus.FILLED:
            self.state = AutoTraderState.ENTRY_FILLED
            self.create_exit_orders()
        elif order.role in (OrderRole.EXIT_PROFIT, OrderRole.EXIT_LOSS) and status == OrderStatus.FILLED:
            self.cancel_other_exit_orders(order)
            self.state = AutoTraderState.EXIT_FILLED
        elif order.role == OrderRole.EXIT_MARKET and status == OrderStatus.FILLED:
            self.state = AutoTraderState.EXIT_FILLED

    def create_exit_orders(self) -> None:
        if not self.entry_order:
            self.state = AutoTraderState.ERROR
            return
        self.exit_profit_order = Order(role=OrderRole.EXIT_PROFIT, order_type="LIMIT", qty=self.entry_order.qty)
        self.exit_loss_order = Order(role=OrderRole.EXIT_LOSS, order_type="STOP", qty=self.entry_order.qty)
        self.orders[self.exit_profit_order.role] = self.exit_profit_order
        self.orders[self.exit_loss_order.role] = self.exit_loss_order
        self.exit_profit_order.place(self.broker)
        self.exit_loss_order.place(self.broker)
        self.state = AutoTraderState.EXIT_WAIT

    def cancel_other_exit_orders(self, filled_order: Order) -> None:
        for role in (OrderRole.EXIT_PROFIT, OrderRole.EXIT_LOSS):
            order = self.orders.get(role)
            if order and order is not filled_order:
                order.cancel(self.broker)

    def force_exit_market(self) -> None:
        if self.state in (AutoTraderState.IDLE, AutoTraderState.ENTRY_WAIT):
            self.state = AutoTraderState.ERROR
            return
        if self.state in (AutoTraderState.EXIT_FILLED, AutoTraderState.ERROR):
            return
        exit_order = Order(role=OrderRole.EXIT_MARKET, order_type="MARKET", qty=self.entry_order.qty if self.entry_order else 0)
        self.orders[exit_order.role] = exit_order
        exit_order.place(self.broker)
        self.state = AutoTraderState.FORCE_EXITING
        now = time.monotonic()
        self._force_exit_started_at = now
        self._last_force_exit_poll = now

    def cancel_all_orders(self) -> None:
        for order in list(self.orders.values()):
            if order.status not in (OrderStatus.FILLED, OrderStatus.CANCELED):
                order.cancel(self.broker)

    def poll(self) -> None:
        if self.state in (AutoTraderState.ENTRY_WAIT, AutoTraderState.EXIT_WAIT, AutoTraderState.FORCE_EXITING):
            self._poll_active_orders()

    def _poll_active_orders(self) -> None:
        now = time.monotonic()
        if self.state == AutoTraderState.FORCE_EXITING:
            if self._force_exit_started_at and now - self._force_exit_started_at > self.config.force_exit_max_duration_sec:
                self.state = AutoTraderState.ERROR
                return
            if self._last_force_exit_poll and now - self._last_force_exit_poll < self.config.force_exit_poll_interval_sec:
                return
            self._last_force_exit_poll = now
        for order in list(self.orders.values()):
            if order.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.ERROR):
                continue
            status = order.poll_status(self.broker)
            if status == OrderStatus.PARTIAL and self.state == AutoTraderState.FORCE_EXITING:
                replacement = Order(role=OrderRole.EXIT_MARKET, order_type="MARKET", qty=order.qty)
                self.orders[replacement.role] = replacement
                replacement.place(self.broker)
            self.on_order_event(order, status)