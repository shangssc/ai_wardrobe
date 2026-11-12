# -*- coding: utf-8 -*-
"""
数据库层：支持 SQLite（默认，零配置）和 MySQL（简历/上线用）。
切换方式：设置环境变量 MYSQL_HOST 即启用 MySQL，例如：
    set MYSQL_HOST=localhost
    set MYSQL_USER=root
    set MYSQL_PASSWORD=你的密码
    set MYSQL_DB=wardrobe
不设置任何变量 → 自动使用 SQLite 文件 wardrobe.db
"""
import os
import sqlite3

MYSQL_CONFIG = {
    "host": os.environ.get("MYSQL_HOST", ""),
    "port": int(os.environ.get("MYSQL_PORT", 3306)),
    "user": os.environ.get("MYSQL_USER", "root"),
    "password": os.environ.get("MYSQL_PASSWORD", ""),
    "database": os.environ.get("MYSQL_DB", "wardrobe"),
    "charset": "utf8mb4",
}

USE_MYSQL = bool(MYSQL_CONFIG["host"])

if USE_MYSQL:
    import pymysql


class DB:
    """统一接口：execute / query，两种数据库用法完全一致"""

    def __init__(self):
        if USE_MYSQL:
            self.conn = pymysql.connect(**MYSQL_CONFIG, autocommit=False,
                                        cursorclass=pymysql.cursors.DictCursor)
        else:
            self.conn = sqlite3.connect("wardrobe.db")
            self.conn.row_factory = sqlite3.Row

    # ---------- 写操作 ----------
    def execute(self, sql, params=()):
        if USE_MYSQL:
            # SQLite 的 ? 占位符 → MySQL 的 %s
            sql = sql.replace("?", "%s")
            with self.conn.cursor() as cur:
                cur.execute(sql, params)
            self.conn.commit()
        else:
            self.conn.execute(sql, params)
            self.conn.commit()

    def executemany(self, sql, seq):
        if USE_MYSQL:
            sql = sql.replace("?", "%s")
            with self.conn.cursor() as cur:
                cur.executemany(sql, seq)
            self.conn.commit()
        else:
            self.conn.executemany(sql, seq)
            self.conn.commit()

    # ---------- 读操作 ----------
    def query(self, sql, params=()):
        """返回字典列表"""
        if USE_MYSQL:
            sql = sql.replace("?", "%s")
            with self.conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        else:
            cur = self.conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def query_one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def close(self):
        self.conn.close()


# ================== 建表（两种库的 SQL 略有差异）=================

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    height REAL, weight REAL, shoulder REAL,
    bust REAL, waist REAL, hip REAL, sex TEXT
);
CREATE TABLE IF NOT EXISTS clothes(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    image TEXT NOT NULL,
    category TEXT, material TEXT, fit TEXT, color TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_clothes_user ON clothes(user_id);
"""

SCHEMA_MYSQL = [
    """CREATE TABLE IF NOT EXISTS users(
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(64) UNIQUE NOT NULL,
        password_hash CHAR(64) NOT NULL,
        height FLOAT, weight FLOAT, shoulder FLOAT,
        bust FLOAT, waist FLOAT, hip FLOAT, sex VARCHAR(4),
        INDEX idx_username (username)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS clothes(
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        image VARCHAR(255) NOT NULL,
        category VARCHAR(16), material VARCHAR(16), fit VARCHAR(16), color VARCHAR(8),
        created_at DATETIME,
        INDEX idx_clothes_user (user_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
]


def init_db():
    db = DB()
    try:
        if USE_MYSQL:
            for sql in SCHEMA_MYSQL:
                db.conn.cursor().execute(sql)
            db.conn.commit()
        else:
            db.conn.executescript(SCHEMA_SQLITE)
            db.conn.commit()
    finally:
        db.close()
