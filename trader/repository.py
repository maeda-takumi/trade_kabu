from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Dict

from .models import Order


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
                    close_position_order INTEGER,
                    close_positions TEXT,
                    price REAL,
                    fund_type TEXT,
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
                    "close_position_order": "INTEGER",
                    "front_order_type": "INTEGER",
                    "stop_trigger_price": "REAL",
                    "stop_after_hit_order_type": "INTEGER",
                    "stop_after_hit_price": "REAL",
                    "stop_under_over": "INTEGER",
                    "fund_type": "TEXT",
                },
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_role ON orders(role)")
            self._ensure_column(conn, "orders", "symbol_code", "TEXT")
            self._ensure_column(conn, "orders", "time_in_force", "TEXT")
            self._ensure_column(conn, "orders", "filled_qty", "REAL")

    def _ensure_columns(self, conn: sqlite3.Connection, columns: Dict[str, str]) -> None:
        existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(orders)")}
        for name, column_type in columns.items():
            if name not in existing_columns:
                conn.execute(f"ALTER TABLE orders ADD COLUMN {name} {column_type}")

    def _ensure_column(self, conn: sqlite3.Connection, table: str, name: str, column_type: str) -> None:
        existing_columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if name not in existing_columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")

    def insert_order(self, order: Order) -> None:
        if order.order_id is None:
            return
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO orders (
                        order_id, role, order_type, qty, symbol, exchange, side, security_type,
                        cash_margin, margin_trade_type, account_type, deliv_type, expire_day,
                        front_order_type, symbol_code, time_in_force, close_position_id, close_position_order, price,
                        fund_type,
                        stop_trigger_price, stop_after_hit_order_type, stop_after_hit_price,
                        stop_under_over, close_positions, filled_qty, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        order.close_position_order,
                        order.price,
                        order.fund_type,
                        order.stop_trigger_price,
                        order.stop_after_hit_order_type,
                        order.stop_after_hit_price,
                        order.stop_under_over,
                        json.dumps(order.close_positions) if order.close_positions else None,
                        order.filled_qty,
                        order.status.name,
                        order.created_at,
                    ),
                )
            except sqlite3.OperationalError as exc:
                if "close_positions" not in str(exc):
                    raise
                self._ensure_column(conn, "orders", "close_positions", "TEXT")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO orders (
                        order_id, role, order_type, qty, symbol, exchange, side, security_type,
                        cash_margin, margin_trade_type, account_type, deliv_type, expire_day,
                        front_order_type, symbol_code, time_in_force, close_position_id, close_position_order, price,
                        fund_type,
                        stop_trigger_price, stop_after_hit_order_type, stop_after_hit_price,
                        stop_under_over, close_positions, filled_qty, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        order.close_position_order,
                        order.price,
                        order.fund_type,
                        order.stop_trigger_price,
                        order.stop_after_hit_order_type,
                        order.stop_after_hit_price,
                        order.stop_under_over,
                        json.dumps(order.close_positions) if order.close_positions else None,
                        order.filled_qty,
                        order.status.name,
                        order.created_at,
                    ),
                )

    def update_status(self, order: Order) -> None:
        if order.order_id is None:
            return
        with self._connect() as conn:
            conn.execute(
                "UPDATE orders SET status = ?, filled_qty = ? WHERE order_id = ?",
                (order.status.name, order.filled_qty, order.order_id),
            )


__all__ = ["OrderRepository"]