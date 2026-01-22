from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
import sqlite3
import time
from typing import Dict, Optional


class AutoTraderState(Enum):
    """状態機械の現在地を表すステータス。"""

    IDLE = auto()  # まだ注文を出していない待機状態
    ENTRY_WAIT = auto()  # 新規（エントリー）注文の約定待ち
    ENTRY_FILLED = auto()  # 新規注文が約定した直後
    EXIT_WAIT = auto()  # 利確/損切りの出口注文の約定待ち
    FORCE_EXITING = auto()  # 強制成行決済中
    EXIT_FILLED = auto()  # 決済完了
    ERROR = auto()  # 想定外の状態に入ったことを示す


class OrderRole(Enum):
    """注文の役割（どのフェーズの注文か）を表す分類。"""

    ENTRY = auto()  # 新規エントリー注文
    EXIT_PROFIT = auto()  # 利確注文
    EXIT_LOSS = auto()  # 損切り注文
    EXIT_MARKET = auto()  # 強制決済の成行注文


class OrderStatus(Enum):
    """ブローカーから返ってくる注文状態の簡易モデル。"""

    NEW = auto()  # まだブローカーに送っていない
    SENT = auto()  # 送信済み
    PARTIAL = auto()  # 一部約定
    FILLED = auto()  # 全部約定
    CANCELED = auto()  # キャンセル済み
    REJECTED = auto()  # 拒否
    ERROR = auto()  # エラー


class BrokerInterface:
    """ブローカー（取引所APIなど）に依存する処理の抽象インターフェース。"""

    def place_order(self, order: "Order") -> str:
        """注文送信。注文IDを返す。"""
        raise NotImplementedError

    def poll_order(self, order: "Order") -> OrderStatus:
        """注文状態のポーリング。"""
        raise NotImplementedError

    def cancel_order(self, order: "Order") -> bool:
        """注文キャンセル。成功/失敗を返す。"""
        raise NotImplementedError


@dataclass
class AutoTraderConfig:
    """強制決済などのタイムアウト系パラメータをまとめた設定。"""

    force_exit_poll_interval_sec: float = 3.0  # 強制決済中のポーリング間隔
    force_exit_max_duration_sec: float = 600.0  # 強制決済が失敗扱いになるまでの最大時間
    force_exit_start_before_close_min: int = 30  # 大引け前に強制決済を開始する目安
    force_exit_deadline_before_close_min: int = 10  # 大引け前の強制決済デッドライン


@dataclass
class Order:
    """注文の内容を保持し、送信/状態確認/キャンセルを行う薄いラッパー。"""

    role: OrderRole
    order_type: str
    qty: float
    price: Optional[float] = None
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.NEW
    created_at: float = field(default_factory=time.time)

    def place(self, broker: BrokerInterface, repository: Optional["OrderRepository"] = None) -> None:
        """ブローカーに注文を送信し、注文IDを保存する。"""
        self.order_id = broker.place_order(self)
        self.status = OrderStatus.SENT
        if repository:
            repository.insert_order(self)

    def poll_status(self, broker: BrokerInterface, repository: Optional["OrderRepository"] = None) -> OrderStatus:
        """ブローカーから最新状態を取得して保持する。"""
        previous_status = self.status
        self.status = broker.poll_order(self)
        if repository and self.status != previous_status:
            repository.update_status(self)
        return self.status

    def cancel(self, broker: BrokerInterface, repository: Optional["OrderRepository"] = None) -> bool:
        """ブローカーにキャンセルを依頼し、成功なら状態を更新する。"""
        success = broker.cancel_order(self)
        if success:
            self.status = OrderStatus.CANCELED
            if repository:
                repository.update_status(self)
        return success


class DemoBroker(BrokerInterface):
    """デモ用の簡易ブローカー実装。指定回数のポーリング後に約定させる。"""

    def __init__(self, fills_after_polls: int = 2) -> None:
        self.fills_after_polls = fills_after_polls
        self._poll_counts: Dict[str, int] = {}
        self._next_id = 1

    def _required_polls(self, order: Order) -> int:
        if order.role == OrderRole.EXIT_PROFIT:
            return self.fills_after_polls + 1
        return self.fills_after_polls
    
    def place_order(self, order: Order) -> str:
        """注文IDを発行し、ポーリング回数を初期化する。"""
        order_id = f"DEMO-{self._next_id}"
        self._next_id += 1
        self._poll_counts[order_id] = 0
        return order_id

    def poll_order(self, order: Order) -> OrderStatus:
        """指定回数まではSENT、それ以降はFILLEDを返す。"""
        if order.order_id is None:
            return OrderStatus.ERROR
        self._poll_counts[order.order_id] += 1
        if self._poll_counts[order.order_id] > self._required_polls(order):
            return OrderStatus.FILLED
        return OrderStatus.SENT

    def cancel_order(self, order: Order) -> bool:
        """常にキャンセル成功を返す簡易実装。"""
        return True

class OrderRepository:
    """注文情報をSQLiteに保存するリポジトリ。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT UNIQUE,
                    role TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    qty REAL NOT NULL,
                    price REAL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_role ON orders(role)")

    def insert_order(self, order: "Order") -> None:
        if order.order_id is None:
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO orders (
                    order_id, role, order_type, qty, price, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.order_id,
                    order.role.name,
                    order.order_type,
                    order.qty,
                    order.price,
                    order.status.name,
                    order.created_at,
                ),
            )

    def update_status(self, order: "Order") -> None:
        if order.order_id is None:
            return
        with self._connect() as conn:
            conn.execute(
                "UPDATE orders SET status = ? WHERE order_id = ?",
                (order.status.name, order.order_id),
            )


class AutoTrader:
    """エントリーから決済までを管理する状態機械。"""

    def __init__(
        self,
        broker: BrokerInterface,
        config: Optional[AutoTraderConfig] = None,
        repository: Optional[OrderRepository] = None,
    ) -> None:
        self.broker = broker
        self.config = config or AutoTraderConfig()
        default_db_path = Path(__file__).with_name("trade.db")
        self.repository = repository or OrderRepository(default_db_path)        
        self.state = AutoTraderState.IDLE
        # 役割別の注文をまとめて管理する辞書（同じ役割の注文は最新が入る）
        self.orders: Dict[OrderRole, Order] = {}
        self.entry_order: Optional[Order] = None
        self.exit_profit_order: Optional[Order] = None
        self.exit_loss_order: Optional[Order] = None
        self._profit_price: Optional[float] = None
        self._loss_price: Optional[float] = None
        self._force_exit_started_at: Optional[float] = None
        self._last_force_exit_poll: Optional[float] = None

    @staticmethod
    def calculate_qty(capital: float, entry_price: float) -> int:
        """軍資金とエントリー価格から注文数量を算出する（端数切り捨て）。"""
        if entry_price <= 0:
            return 0
        return int(capital // entry_price)

    def start_trade(self, entry_order: Order, profit_price: float, loss_price: float) -> None:
        """取引を開始する。IDLEでない場合はERRORに遷移する。"""
        if self.state != AutoTraderState.IDLE:
            self.state = AutoTraderState.ERROR
            return
        self._profit_price = profit_price
        self._loss_price = loss_price        
        self._profit_price = profit_price
        self._loss_price = loss_price
        # 新規エントリー注文を送信
        self.entry_order = entry_order
        self.orders[entry_order.role] = entry_order
        entry_order.place(self.broker, repository=self.repository)
        self.state = AutoTraderState.ENTRY_WAIT

    def on_order_event(self, order: Order, status: OrderStatus) -> None:
        """注文ステータス変化に応じて状態遷移と後続処理を行う。"""
        if self.state == AutoTraderState.ERROR:
            return
        # エントリーが約定したら利確/損切り注文を作る
        if order.role == OrderRole.ENTRY and status == OrderStatus.FILLED:
            self.state = AutoTraderState.ENTRY_FILLED
            self.create_exit_orders()
        # 利確 or 損切りのいずれかが約定したら他方をキャンセル
        elif order.role in (OrderRole.EXIT_PROFIT, OrderRole.EXIT_LOSS) and status == OrderStatus.FILLED:
            self.cancel_other_exit_orders(order)
            self.state = AutoTraderState.EXIT_FILLED
        # 成行強制決済が約定したら終了
        elif order.role == OrderRole.EXIT_MARKET and status == OrderStatus.FILLED:
            self.state = AutoTraderState.EXIT_FILLED

    def create_exit_orders(self) -> None:
        """利確/損切り注文を作成して送信する。"""
        if not self.entry_order:
            self.state = AutoTraderState.ERROR
            return
        if self._profit_price is None or self._loss_price is None:
            # 利確/損切価格が未設定ならエラーにする
            self.state = AutoTraderState.ERROR
            return
        # エントリー数量に合わせて両建ての出口注文を作る
        self.exit_profit_order = Order(
            role=OrderRole.EXIT_PROFIT,
            order_type="LIMIT",
            qty=self.entry_order.qty,
            price=self._profit_price,
        )
        
        self.exit_loss_order = Order(
            role=OrderRole.EXIT_LOSS,
            order_type="STOP",
            qty=self.entry_order.qty,
            price=self._loss_price,
        )
        print(
            "[demo] create exit orders: "
            f"profit={self.exit_profit_order.order_type} price={self.exit_profit_order.price} qty={self.exit_profit_order.qty}, "
            f"loss={self.exit_loss_order.order_type} price={self.exit_loss_order.price} qty={self.exit_loss_order.qty}"
        )        
        self.orders[self.exit_profit_order.role] = self.exit_profit_order
        self.orders[self.exit_loss_order.role] = self.exit_loss_order

        # OCOがない前提のため、損切→利確の順に送信する
        self.exit_loss_order.place(self.broker, repository=self.repository)
        self.exit_profit_order.place(self.broker, repository=self.repository)
        self.state = AutoTraderState.EXIT_WAIT

    def cancel_other_exit_orders(self, filled_order: Order) -> None:
        """片方が約定したらもう片方をキャンセルする。"""
        for role in (OrderRole.EXIT_PROFIT, OrderRole.EXIT_LOSS):
            order = self.orders.get(role)
            if order and order is not filled_order:
                order.cancel(self.broker, repository=self.repository)

    def force_exit_market(self) -> None:
        """強制決済（成行）を実行する。"""
        if self.state in (AutoTraderState.IDLE, AutoTraderState.ENTRY_WAIT):
            # まだポジションがない段階での強制決済はエラー扱い
            self.state = AutoTraderState.ERROR
            return
        if self.state in (AutoTraderState.EXIT_FILLED, AutoTraderState.ERROR):
            # すでに終わっているかエラーなら何もしない
            return
        exit_order = Order(
            role=OrderRole.EXIT_MARKET,
            order_type="MARKET",
            qty=self.entry_order.qty if self.entry_order else 0,
        )
        self.orders[exit_order.role] = exit_order
        exit_order.place(self.broker, repository=self.repository)
        self.state = AutoTraderState.FORCE_EXITING
        # 強制決済用のタイムスタンプを記録
        now = time.monotonic()
        self._force_exit_started_at = now
        self._last_force_exit_poll = now

    def cancel_all_orders(self) -> None:
        """未約定の注文をすべてキャンセルする。"""
        for order in list(self.orders.values()):
            if order.status not in (OrderStatus.FILLED, OrderStatus.CANCELED):
                order.cancel(self.broker, repository=self.repository)

    def poll(self) -> None:
        """状態に応じて注文のポーリング処理を実行する。"""
        if self.state in (AutoTraderState.ENTRY_WAIT, AutoTraderState.EXIT_WAIT, AutoTraderState.FORCE_EXITING):
            self._poll_active_orders()

    def _poll_active_orders(self) -> None:
        """アクティブな注文をポーリングし、状態遷移を処理する。"""
        now = time.monotonic()
        if self.state == AutoTraderState.FORCE_EXITING:
            # 強制決済が長引きすぎたらエラーにする
            if self._force_exit_started_at and now - self._force_exit_started_at > self.config.force_exit_max_duration_sec:
                self.state = AutoTraderState.ERROR
                return
            # 強制決済中は一定間隔でのみポーリング
            if self._last_force_exit_poll and now - self._last_force_exit_poll < self.config.force_exit_poll_interval_sec:
                return
            self._last_force_exit_poll = now
        for order in list(self.orders.values()):
            # すでに確定した注文はスキップ
            if order.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.ERROR):
                continue
            status = order.poll_status(self.broker, repository=self.repository)
            # 強制決済時に一部約定なら成行を出し直す
            if status == OrderStatus.PARTIAL and self.state == AutoTraderState.FORCE_EXITING:
                replacement = Order(role=OrderRole.EXIT_MARKET, order_type="MARKET", qty=order.qty)
                self.orders[replacement.role] = replacement
                replacement.place(self.broker, repository=self.repository)
            # 状態変化に応じた処理へ
            self.on_order_event(order, status)


def run_demo(
    poll_interval_sec: float = 0.5,
    fills_after_polls: int = 2,
    profit_price: float = 105.0,
    loss_price: float = 95.0,
) -> AutoTraderState:
    broker = DemoBroker(fills_after_polls=fills_after_polls)
    trader = AutoTrader(broker)
    entry_order = Order(role=OrderRole.ENTRY, order_type="MARKET", qty=1)
    print(f"[demo] state={trader.state.name} -> start_trade")
    trader.start_trade(entry_order, profit_price=profit_price, loss_price=loss_price)
    last_state = trader.state
    print(f"[demo] state={last_state.name}")
    while trader.state not in (AutoTraderState.EXIT_FILLED, AutoTraderState.ERROR):
        trader.poll()
        if trader.state != last_state:
            print(f"[demo] state={last_state.name} -> {trader.state.name}")
            last_state = trader.state
        time.sleep(poll_interval_sec)
    print(f"[demo] completed with state={trader.state.name}")
    return trader.state


if __name__ == "__main__":
    run_demo()
