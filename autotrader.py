from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
import json
from pathlib import Path
import sqlite3
import time
from typing import Dict, Optional
from urllib import error as url_error
from urllib import request as url_request

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

class FrontOrderType(Enum):
    """kabuステーションAPIのFrontOrderTypeコード。"""

    MARKET = 10  # 成行
    MARKET_ON_OPEN = 11  # 寄成
    MARKET_ON_CLOSE = 12  # 引成
    MARKET_NO_EXECUTION = 13  # 不成
    IOC_MARKET = 14  # IOC成行
    LIMIT = 20  # 指値
    LIMIT_ON_OPEN = 21  # 寄指
    LIMIT_ON_CLOSE = 22  # 引指
    LIMIT_NO_EXECUTION = 23  # 不指
    IOC_LIMIT = 24  # IOC指値
    STOP = 30  # 逆指値
    STOP_MARKET = 31  # 逆指値(成行)
    STOP_LIMIT = 32  # 逆指値(指値)


class ReverseLimitUnderOver(Enum):
    """逆指値の判定方向。"""

    OVER = 1  # 指定価格以上で発動
    UNDER = 2  # 指定価格以下で発動


ORDER_TYPE_TO_FRONT_ORDER_TYPE: Dict[str, FrontOrderType] = {
    "MARKET": FrontOrderType.MARKET,
    "LIMIT": FrontOrderType.LIMIT,
    "STOP": FrontOrderType.STOP,
    "STOP_MARKET": FrontOrderType.STOP_MARKET,
    "STOP_LIMIT": FrontOrderType.STOP_LIMIT,
}


class BrokerInterface:
    """ブローカー（取引所APIなど）に依存する処理の抽象インターフェース。"""

    def place_order(self, order: "Order") -> str:
        """注文送信。注文IDを返す。"""
        raise NotImplementedError

    def poll_order(self, order: "Order") -> "OrderPollResult":
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
    market_close_hour: int = 15  # 大引け時刻(時)
    market_close_minute: int = 0  # 大引け時刻(分)
    force_exit_use_market_close: bool = True  # 閉場時刻で強制成行を動かすか
    reconcile_on_success: bool = True  # 約定成功時の再照合を実施するか


@dataclass(frozen=True)
class OrderPollResult:
    status: OrderStatus
    filled_qty: float = 0.0

@dataclass
class Order:
    """注文の内容を保持し、送信/状態確認/キャンセルを行う薄いラッパー。"""

    role: OrderRole
    order_type: str
    qty: float
    symbol: Optional[str] = None
    exchange: Optional[int] = None
    side: Optional[int] = None
    security_type: Optional[int] = None
    cash_margin: Optional[int] = None
    margin_trade_type: Optional[int] = None
    account_type: Optional[int] = None
    deliv_type: Optional[int] = None
    expire_day: Optional[int] = None
    front_order_type: Optional[int] = None
    symbol_code: Optional[str] = None
    time_in_force: Optional[str] = None
    price: Optional[float] = None
    close_position_id: Optional[str] = None
    stop_trigger_price: Optional[float] = None
    stop_after_hit_order_type: Optional[int] = None
    stop_after_hit_price: Optional[float] = None
    stop_under_over: Optional[int] = None
    order_id: Optional[str] = None
    status: OrderStatus = OrderStatus.NEW
    filled_qty: float = 0.0
    last_error: Optional[str] = None
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
        previous_filled_qty = self.filled_qty
        poll_result = broker.poll_order(self)
        self.status = poll_result.status
        if poll_result.filled_qty:
            self.filled_qty = poll_result.filled_qty
        if self.status == OrderStatus.FILLED and not self.filled_qty:
            self.filled_qty = self.qty
        if repository and (self.status != previous_status or self.filled_qty != previous_filled_qty):
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

    def poll_order(self, order: Order) -> OrderPollResult:
        """指定回数まではSENT、それ以降はFILLEDを返す。"""
        if order.order_id is None:
            return OrderPollResult(status=OrderStatus.ERROR)
        self._poll_counts[order.order_id] += 1
        if self._poll_counts[order.order_id] > self._required_polls(order):
            return OrderPollResult(status=OrderStatus.FILLED, filled_qty=order.qty)
        return OrderPollResult(status=OrderStatus.SENT)

    def cancel_order(self, order: Order) -> bool:
        """常にキャンセル成功を返す簡易実装。"""
        return True

@dataclass
class KabuStationConfig:
    base_url: str
    api_token: str
    trading_password: str
    timeout_sec: float = 10.0



class KabuStationBroker(BrokerInterface):
    """kabuステーションAPI用ブローカー実装。"""

    def __init__(
        self,
        base_url: str,
        api_password: str,
        trading_password: Optional[str] = None,
        api_token: Optional[str] = None,
        timeout_sec: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_password = api_password
        self.trading_password = trading_password
        self.api_token = api_token
        self.timeout_sec = timeout_sec

    def fetch_token(self) -> str:
        """APIトークンを取得して保持する。

        仕様:
        - POST /kabusapi/token
        - Header: Content-Type: application/json
        - Body: {"APIPassword": "<APIパスワード>"}
        """
        response = self._request_json(
            "POST",
            "/kabusapi/token",
            {"APIPassword": self.api_password},
            require_token=False,
        )
        token = response.get("Token") or response.get("token")
        if not token:
            raise RuntimeError("トークン取得レスポンスに Token が含まれていません。")
        self.api_token = token
        return token

    def request_json(
        self, method: str, path: str, payload: Optional[dict] = None
    ) -> dict:
        """APIリクエストを送り、トークン失効時は再取得して再試行する。"""
        if not self.api_token:
            self.fetch_token()
        try:
            return self._request_json(method, path, payload, require_token=True)
        except url_error.HTTPError as exc:
            if exc.code == 401:
                self.fetch_token()
                return self._request_json(method, path, payload, require_token=True)
            raise

    def place_order(self, order: "Order") -> str:
        payload = self._build_order_payload(order)
        response = self.request_json("POST", "/kabusapi/sendorder", payload)
        result = response.get("Result")
        if result is not None and int(result) != 0:
            message = response.get("Msg") or response.get("Message") or "注文送信に失敗しました。"
            raise RuntimeError(f"kabuステーションAPI注文エラー(Result={result}): {message}")
        order_id = response.get("OrderId") or response.get("orderId")
        if not order_id:
            raise RuntimeError("注文レスポンスに OrderId が含まれていません。")
        return str(order_id)

    def poll_order(self, order: "Order") -> OrderPollResult:
        if order.order_id is None:
            return OrderPollResult(status=OrderStatus.ERROR)
        response = self.request_json("GET", f"/kabusapi/orders?orderid={order.order_id}")
        result = response.get("Result") if isinstance(response, dict) else None
        if result is not None and int(result) != 0:
            message = response.get("Msg") or response.get("Message") or "注文照会に失敗しました。"
            order.last_error = f"kabuステーションAPI照会エラー(Result={result}): {message}"
            return OrderPollResult(status=OrderStatus.ERROR)
        order_payload = self._find_order_payload(order.order_id, response)
        status = self._map_order_status(order_payload)
        filled_qty = self._extract_filled_qty(order_payload)
        return OrderPollResult(status=status, filled_qty=filled_qty)
    
    def cancel_order(self, order: "Order") -> bool:
        if order.order_id is None:
            return False
        payload = {
            "OrderId": order.order_id,
            "Password": self._require_trading_password(),
        }
        response = self.request_json("PUT", "/kabusapi/cancelorder", payload)
        result = response.get("Result", 1)
        if int(result) != 0:
            message = response.get("Msg") or response.get("Message") or "注文キャンセルに失敗しました。"
            order.last_error = f"kabuステーションAPIキャンセルエラー(Result={result}): {message}"
            return False
        return True
    
    def _request_json(
        self,
        method: str,
        path: str,
        payload: Optional[dict],
        require_token: bool,
    ) -> dict:
        url = self._build_url(path)
        headers = {"Content-Type": "application/json"}
        if require_token and self.api_token:
            headers["X-API-KEY"] = self.api_token
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_obj = url_request.Request(url, data=data, headers=headers, method=method)
        try:
            with url_request.urlopen(request_obj, timeout=self.timeout_sec) as response:
                body = response.read().decode("utf-8")
        except url_error.HTTPError:
            raise
        except url_error.URLError as exc:
            raise RuntimeError("kabuステーションAPIへ接続できません。") from exc
        if not body:
            return {}
        return json.loads(body)

    def _build_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{path}"

    def _require_trading_password(self) -> str:
        if not self.trading_password:
            raise RuntimeError("取引パスワードが設定されていません。")
        return self.trading_password

    def _build_order_payload(self, order: Order) -> dict:
        password = self._require_trading_password()
        if order.front_order_type is None:
            mapped = ORDER_TYPE_TO_FRONT_ORDER_TYPE.get(order.order_type.upper())
            if mapped:
                order.front_order_type = mapped.value        
        required_fields = {
            "Symbol": (order.symbol, "銘柄コード(Symbol)"),
            "Exchange": (order.exchange, "市場コード(Exchange)"),
            "Side": (order.side, "売買区分(Side: 1=買い, 2=売り)"),
            "CashMargin": (order.cash_margin, "現物/信用区分(CashMargin: 1=現物, 2=信用)"),
            "Qty": (order.qty, "数量(Qty)"),
            "FrontOrderType": (order.front_order_type, "執行条件(FrontOrderType)"),
        }
        missing = [label for _, (value, label) in required_fields.items() if value is None]
        if order.cash_margin == 2 and order.margin_trade_type is None:
            missing.append("信用区分(MarginTradeType: 1=信用新規, 2=信用返済)")
        if missing:
            details = " / ".join(missing)
            raise RuntimeError(
                f"注文送信に必要な項目が不足しています: {details}。"
                "UI入力とAPI仕様(/kabusapi/sendorder)の対応を確認してください。"
            )
        payload: dict[str, object] = {
            "Password": password,
            "Symbol": order.symbol,
            "Exchange": order.exchange,
            "Side": order.side,
            "CashMargin": order.cash_margin,
            "Qty": order.qty,
            "FrontOrderType": order.front_order_type,
        }
        optional_fields = {
            "SecurityType": order.security_type,
            "MarginTradeType": order.margin_trade_type,
            "AccountType": order.account_type,
            "DelivType": order.deliv_type,
            "ExpireDay": order.expire_day,
            "Price": order.price,
            "TimeInForce": order.time_in_force,
        }
        for key, value in optional_fields.items():
            if value is not None:
                payload[key] = value
        if order.close_position_id:
            payload["ClosePositions"] = [{"HoldID": order.close_position_id, "Qty": order.qty}]
        if order.stop_trigger_price is not None:
            if order.stop_under_over is None or order.stop_after_hit_order_type is None:
                raise RuntimeError("逆指値条件に必要な項目が不足しています。")
            reverse_limit = {
                "TriggerPrice": order.stop_trigger_price,
                "UnderOver": order.stop_under_over,
                "AfterHitOrderType": order.stop_after_hit_order_type,
            }
            if order.stop_after_hit_price is not None:
                reverse_limit["AfterHitPrice"] = order.stop_after_hit_price
            payload["ReverseLimitOrder"] = reverse_limit                
        return payload

    @staticmethod
    def _find_order_payload(order_id: str, response: dict) -> dict:
        if not response:
            return {}
        if isinstance(response, list):
            for item in response:
                if str(item.get("OrderId")) == str(order_id):
                    return item
            return {}
        if isinstance(response, dict) and "Details" in response:
            for item in response.get("Details", []):
                if str(item.get("OrderId")) == str(order_id):
                    return item
        return response if isinstance(response, dict) else {}

    @staticmethod
    def _map_order_status(payload: dict) -> OrderStatus:
        state_value = payload.get("State") or payload.get("OrderState") or payload.get("Status")
        state_text = str(state_value or "").lower()
        if any(key in state_text for key in ("done", "filled", "約定", "complete")):
            return OrderStatus.FILLED
        if any(key in state_text for key in ("canceled", "cancel", "expired", "失効")):
            return OrderStatus.CANCELED
        if any(key in state_text for key in ("rejected", "reject", "却下")):
            return OrderStatus.REJECTED
        if any(key in state_text for key in ("partial", "一部")):
            return OrderStatus.PARTIAL
        if state_text.isdigit():
            state_code = int(state_text)
            status_map = {
                1: OrderStatus.SENT,
                2: OrderStatus.SENT,
                3: OrderStatus.PARTIAL,
                4: OrderStatus.FILLED,
                5: OrderStatus.CANCELED,
                6: OrderStatus.REJECTED,
                7: OrderStatus.CANCELED,
                8: OrderStatus.CANCELED,
            }
            mapped_status = status_map.get(state_code)
            if mapped_status:
                return mapped_status
        qty = payload.get("Qty") or payload.get("OrderQty")
        cum_qty = payload.get("CumQty") or payload.get("FilledQty") or payload.get("ExecuteQty")
        try:
            qty_value = float(qty) if qty is not None else None
            cum_value = float(cum_qty) if cum_qty is not None else None
        except (TypeError, ValueError):
            qty_value = None
            cum_value = None
        if qty_value and cum_value is not None:
            if cum_value >= qty_value:
                return OrderStatus.FILLED
            if 0 < cum_value < qty_value:
                return OrderStatus.PARTIAL
        if state_text:
            return OrderStatus.SENT
        return OrderStatus.ERROR

    @staticmethod
    def _extract_filled_qty(payload: dict) -> float:
        for key in ("CumQty", "FilledQty", "ExecuteQty", "Filled"):
            if key in payload and payload[key] is not None:
                try:
                    return float(payload[key])
                except (TypeError, ValueError):
                    continue
        return 0.0    
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
                    symbol TEXT,
                    exchange INTEGER,
                    side INTEGER,
                    security_type INTEGER,
                    cash_margin INTEGER,
                    margin_trade_type INTEGER,
                    account_type INTEGER,
                    deliv_type INTEGER,
                    expire_day INTEGER,
                    front_order_type INTEGER,
                    close_position_id TEXT,
                    price REAL,
                    stop_trigger_price REAL,
                    stop_after_hit_order_type INTEGER,
                    stop_after_hit_price REAL,
                    stop_under_over INTEGER,                    
                    filled_qty REAL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            self._ensure_columns(
                conn,
                {
                    "symbol": "TEXT",
                    "exchange": "INTEGER",
                    "side": "INTEGER",
                    "security_type": "INTEGER",
                    "cash_margin": "INTEGER",
                    "margin_trade_type": "INTEGER",
                    "account_type": "INTEGER",
                    "deliv_type": "INTEGER",
                    "expire_day": "INTEGER",
                    "close_position_id": "TEXT",
                    "front_order_type": "INTEGER",
                    "stop_trigger_price": "REAL",
                    "stop_after_hit_order_type": "INTEGER",
                    "stop_after_hit_price": "REAL",
                    "stop_under_over": "INTEGER",
                },
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_role ON orders(role)")
            self._ensure_column(conn, "orders", "symbol_code", "TEXT")
            self._ensure_column(conn, "orders", "time_in_force", "TEXT")
            self._ensure_column(conn, "orders", "filled_qty", "REAL")

    def _ensure_columns(self, conn: sqlite3.Connection, columns: Dict[str, str]) -> None:
        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(orders)")
        }
        for name, column_type in columns.items():
            if name not in existing_columns:
                conn.execute(f"ALTER TABLE orders ADD COLUMN {name} {column_type}")
    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table: str,
        name: str,
        column_type: str,
    ) -> None:
        existing_columns = {
            row[1] for row in conn.execute(f"PRAGMA table_info({table})")
        }
        if name not in existing_columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")


    def insert_order(self, order: "Order") -> None:
        if order.order_id is None:
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO orders (
                    order_id, role, order_type, qty, symbol, exchange, side, security_type,
                    cash_margin, margin_trade_type, account_type, deliv_type, expire_day,
                    front_order_type, symbol_code, time_in_force, close_position_id, price,
                    stop_trigger_price, stop_after_hit_order_type, stop_after_hit_price,
                    stop_under_over, filled_qty, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.order_id,
                    order.role.name,
                    order.order_type,
                    order.qty,
                    order.symbol,
                    order.exchange,
                    order.side,
                    order.security_type,
                    order.cash_margin,
                    order.margin_trade_type,
                    order.account_type,
                    order.deliv_type,
                    order.expire_day,
                    order.front_order_type,
                    order.symbol_code,
                    order.time_in_force,
                    order.close_position_id,
                    order.price,
                    order.stop_trigger_price,
                    order.stop_after_hit_order_type,
                    order.stop_after_hit_price,
                    order.stop_under_over,
                    order.filled_qty,
                    order.status.name,
                    order.created_at,
                ),
            )

    def update_status(self, order: "Order") -> None:
        if order.order_id is None:
            return
        with self._connect() as conn:
            conn.execute(
                "UPDATE orders SET status = ?, filled_qty = ? WHERE order_id = ?",
                (order.status.name, order.filled_qty, order.order_id),
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
        self._confirmed_order_ids: set[str] = set()

    def _enter_error_state(self) -> None:
        """エラー状態へ遷移し、未約定注文を可能な限り取り消す。"""
        self.state = AutoTraderState.ERROR
        self.cancel_all_orders()
        
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
        if entry_order.front_order_type is None:
            mapped = ORDER_TYPE_TO_FRONT_ORDER_TYPE.get(entry_order.order_type.upper())
            if mapped:
                entry_order.front_order_type = mapped.value
        self.entry_order = entry_order
        self.orders[entry_order.role] = entry_order
        entry_order.place(self.broker, repository=self.repository)
        self.state = AutoTraderState.ENTRY_WAIT

    def on_order_event(self, order: Order, status: OrderStatus) -> None:
        """注文ステータス変化に応じて状態遷移と後続処理を行う。"""
        if self.state == AutoTraderState.ERROR:
            return
        if status in (OrderStatus.REJECTED, OrderStatus.ERROR):
            self._enter_error_state()
            return
        # エントリーが約定したら利確/損切り注文を作る
        if order.role == OrderRole.ENTRY and status == OrderStatus.FILLED:
            self.state = AutoTraderState.ENTRY_FILLED
            self.create_exit_orders()
        # 利確 or 損切りのいずれかが約定したら他方をキャンセル
        elif order.role in (OrderRole.EXIT_PROFIT, OrderRole.EXIT_LOSS) and status == OrderStatus.FILLED:
            other_role = (
                OrderRole.EXIT_LOSS if order.role == OrderRole.EXIT_PROFIT else OrderRole.EXIT_PROFIT
            )
            other_order = self.orders.get(other_role)
            if other_order and other_order.status == OrderStatus.FILLED:
                self._enter_error_state()
                return
            
            self.cancel_other_exit_orders(order)
            if self.state != AutoTraderState.ERROR:
                self.state = AutoTraderState.EXIT_FILLED
        # 成行強制決済が約定したら終了
        elif order.role == OrderRole.EXIT_MARKET and status == OrderStatus.FILLED:
            self.state = AutoTraderState.EXIT_FILLED

    def _confirm_order_filled(self, order: Order) -> bool:
        if not self.config.reconcile_on_success:
            return True
        if order.order_id is None or order.order_id in self._confirmed_order_ids:
            return True
        confirmed_status = order.poll_status(self.broker, repository=self.repository)
        if confirmed_status == OrderStatus.FILLED:
            self._confirmed_order_ids.add(order.order_id)
            return True
        return False

    def create_exit_orders(self) -> None:
        """利確/損切り注文を作成して送信する。"""
        if not self.entry_order:
            self.state = AutoTraderState.ERROR
            return
        if self._profit_price is None or self._loss_price is None:
            # 利確/損切価格が未設定ならエラーにする
            self.state = AutoTraderState.ERROR
            return
        exit_side = self._resolve_exit_side()
        if exit_side is None and not isinstance(self.broker, DemoBroker):
            self.state = AutoTraderState.ERROR
            return
        base_kwargs = self._build_exit_order_base(exit_side)
        stop_under_over = self._resolve_stop_under_over()
        if stop_under_over is None and not isinstance(self.broker, DemoBroker):
            self.state = AutoTraderState.ERROR
            return        
        # エントリー数量に合わせて両建ての出口注文を作る
        self.exit_profit_order = Order(
            role=OrderRole.EXIT_PROFIT,
            order_type="LIMIT",
            qty=self.entry_order.qty,
            front_order_type=FrontOrderType.LIMIT.value,
            price=self._profit_price,
            **base_kwargs,
        )
        
        self.exit_loss_order = Order(
            role=OrderRole.EXIT_LOSS,
            order_type="STOP",
            qty=self.entry_order.qty,
            front_order_type=FrontOrderType.STOP.value,
            stop_trigger_price=self._loss_price,
            stop_under_over=stop_under_over,
            stop_after_hit_order_type=FrontOrderType.MARKET.value,
            **base_kwargs,
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
                success = order.cancel(self.broker, repository=self.repository)
                if not success:
                    self.force_exit_market()
                    if self.state != AutoTraderState.FORCE_EXITING:
                        self._enter_error_state()

    def force_exit_market(self) -> None:
        """強制決済（成行）を実行する。"""
        if self.state in (AutoTraderState.IDLE, AutoTraderState.ENTRY_WAIT):
            # まだポジションがない段階での強制決済はエラー扱い
            self.state = AutoTraderState.ERROR
            return
        if self.state in (AutoTraderState.EXIT_FILLED, AutoTraderState.ERROR):
            # すでに終わっているかエラーなら何もしない
            return
        exit_side = self._resolve_exit_side()
        if exit_side is None and not isinstance(self.broker, DemoBroker):
            self.state = AutoTraderState.ERROR
            return
        base_kwargs = self._build_exit_order_base(exit_side)
        exit_order = Order(
            role=OrderRole.EXIT_MARKET,
            order_type="MARKET",
            qty=self.entry_order.qty if self.entry_order else 0,
            close_position_id=self.entry_order.close_position_id if self.entry_order else None,
            front_order_type=FrontOrderType.MARKET.value,
            **base_kwargs,
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
        self._maybe_force_exit_by_market_close()
        if self.state in (AutoTraderState.ENTRY_WAIT, AutoTraderState.EXIT_WAIT, AutoTraderState.FORCE_EXITING):
            self._poll_active_orders()

    def _maybe_force_exit_by_market_close(self) -> None:
        if not self.config.force_exit_use_market_close:
            return
        if self.state in (AutoTraderState.EXIT_FILLED, AutoTraderState.ERROR):
            return
        now = datetime.now()
        close_time = now.replace(
            hour=self.config.market_close_hour,
            minute=self.config.market_close_minute,
            second=0,
            microsecond=0,
        )
        start_time = close_time - timedelta(minutes=self.config.force_exit_start_before_close_min)
        deadline_time = close_time - timedelta(minutes=self.config.force_exit_deadline_before_close_min)
        if now < start_time:
            return
        if self.state != AutoTraderState.FORCE_EXITING:
            if now <= deadline_time:
                self.force_exit_market()
            else:
                self._enter_error_state()

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
            if status in (OrderStatus.REJECTED, OrderStatus.ERROR):
                self._enter_error_state()
                return
            # 強制決済時に一部約定なら成行を出し直す
            if status == OrderStatus.PARTIAL:
                if self._handle_partial_fill(order):
                    continue
            # 状態変化に応じた処理へ
            self.on_order_event(order, status)

    def _handle_partial_fill(self, order: Order) -> bool:
        """部分約定時に残量分の注文を再送する。処理した場合はTrue。"""
        if order.filled_qty <= 0 or order.filled_qty >= order.qty:
            return False
        remaining_qty = order.qty - order.filled_qty
        if remaining_qty <= 0:
            return False
        if self.state == AutoTraderState.FORCE_EXITING:
            replacement = Order(
                role=OrderRole.EXIT_MARKET,
                order_type="MARKET",
                qty=remaining_qty,
                symbol=order.symbol,
                exchange=order.exchange,
                side=order.side,
                security_type=order.security_type,
                cash_margin=order.cash_margin,
                margin_trade_type=order.margin_trade_type,
                account_type=order.account_type,
                deliv_type=order.deliv_type,
                expire_day=order.expire_day,
                front_order_type=order.front_order_type,
                symbol_code=order.symbol_code,
                time_in_force=order.time_in_force,
                price=order.price,
                stop_trigger_price=order.stop_trigger_price,
                stop_after_hit_order_type=order.stop_after_hit_order_type,
                stop_after_hit_price=order.stop_after_hit_price,
                stop_under_over=order.stop_under_over,
            )
            self.orders[replacement.role] = replacement
            replacement.place(self.broker, repository=self.repository)
            return True
        if not order.cancel(self.broker, repository=self.repository):
            self._enter_error_state()
            return True
        replacement = Order(
            role=order.role,
            order_type=order.order_type,
            qty=remaining_qty,
            price=order.price,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            security_type=order.security_type,
            cash_margin=order.cash_margin,
            margin_trade_type=order.margin_trade_type,
            account_type=order.account_type,
            deliv_type=order.deliv_type,
            expire_day=order.expire_day,
            front_order_type=order.front_order_type,
            symbol_code=order.symbol_code,
            time_in_force=order.time_in_force,
            stop_trigger_price=order.stop_trigger_price,
            stop_after_hit_order_type=order.stop_after_hit_order_type,
            stop_after_hit_price=order.stop_after_hit_price,
            stop_under_over=order.stop_under_over,
        )
        self.orders[replacement.role] = replacement
        replacement.place(self.broker, repository=self.repository)
        return True
    def _resolve_exit_side(self) -> Optional[int]:
        if not self.entry_order:
            return None
        if self.entry_order.side is None:
            return None
        # TODO: kabuステーションAPIのSide仕様に合わせて明示的に変換する。
        if self.entry_order.side == 1:
            return 2
        if self.entry_order.side == 2:
            return 1
        return None
    def _resolve_stop_under_over(self) -> Optional[int]:
        if not self.entry_order:
            return None
        if self.entry_order.side == 1:
            return ReverseLimitUnderOver.UNDER.value
        if self.entry_order.side == 2:
            return ReverseLimitUnderOver.OVER.value
        return None

    def _build_exit_order_base(self, exit_side: Optional[int]) -> dict:
        if not self.entry_order:
            return {}
        return {
            "symbol": self.entry_order.symbol,
            "exchange": self.entry_order.exchange,
            "side": exit_side,
            "security_type": self.entry_order.security_type,
            "cash_margin": self.entry_order.cash_margin,
            "margin_trade_type": self.entry_order.margin_trade_type,
            "account_type": self.entry_order.account_type,
            "deliv_type": self.entry_order.deliv_type,
            "expire_day": self.entry_order.expire_day,
            "symbol_code": self.entry_order.symbol_code,
            "time_in_force": self.entry_order.time_in_force,
            "close_position_id": self.entry_order.close_position_id,
        }
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
