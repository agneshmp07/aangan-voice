"""Storage: SQLite locally and in tests; Postgres (Supabase) when DATABASE_URL is set,
which is required on Vercel because its disk does not persist.

SQLite notes: One short-lived connection per operation; WAL so the cron, the tools and
the dashboard don't block each other. Atomic UPDATE ... WHERE claimed_by IS NULL gives
"first tap wins" without any locking in Python."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .settings import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    id TEXT PRIMARY KEY, phone TEXT, started_at TEXT, ended_at TEXT, duration_s REAL,
    ended_reason TEXT, language TEXT, transcript TEXT, summary TEXT, recording_url TEXT,
    cost_inr REAL, cost_source TEXT, missed INTEGER DEFAULT 0, synthetic INTEGER DEFAULT 0,
    raw TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT, call_id TEXT UNIQUE, phone TEXT,
    facts TEXT DEFAULT '{}', asked TEXT DEFAULT '{}', outcome TEXT, say_key TEXT,
    reasons TEXT DEFAULT '[]', notes TEXT DEFAULT '[]', unresolved TEXT DEFAULT '[]',
    priority INTEGER DEFAULT 0, asked_price INTEGER DEFAULT 0, verified_client INTEGER,
    booking_id INTEGER, handoff_sent_at TEXT, handoff_channel TEXT, handoff_kind TEXT,
    claimed_by TEXT, claimed_at TEXT, claim_alerted_at TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS leads_phone ON leads(phone);
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER, slot_start TEXT, slot_end TEXT,
    calendar_event_id TEXT, status TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS callbacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT, call_id TEXT, reason TEXT,
    priority INTEGER DEFAULT 0, due_at TEXT, status TEXT DEFAULT 'pending',
    note TEXT, created_at TEXT, dispatched_at TEXT
);
CREATE INDEX IF NOT EXISTS callbacks_phone ON callbacks(phone, status);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT, recipient TEXT, subject TEXT,
    body TEXT, ref TEXT, status TEXT, error TEXT, external_id TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, type TEXT, call_id TEXT,
    tool TEXT, latency_ms REAL, ok INTEGER, data TEXT
);
CREATE TABLE IF NOT EXISTS rule_overrides (
    key TEXT PRIMARY KEY, value TEXT, updated_at TEXT, updated_by TEXT
);
CREATE TABLE IF NOT EXISTS sheet_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER UNIQUE, row TEXT, updated_at TEXT
);
"""


def _path() -> str:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    return settings.db_path


def safe_database_url(url: str) -> str:
    """Percent-encode the password so '@', '#', '/', ':' in it can't break the URL.
    Splits at the LAST '@' before the host, so it works on raw and already-encoded URLs."""
    from urllib.parse import quote, unquote
    scheme, sep, rest = url.partition("://")
    if not sep or "@" not in rest:
        return url
    creds, _, host = rest.rpartition("@")
    user, colon, pwd = creds.partition(":")
    return f"{scheme}://{user}{colon}{quote(unquote(pwd), safe='')}@{host}" if colon else url


def redact(text: str) -> str:
    """Never let a password reach a log line or /health."""
    url = settings.database_url or ""
    _, _, rest = url.partition("://")
    creds = rest.rpartition("@")[0]
    pwd = creds.partition(":")[2]
    for secret in {pwd, __import__("urllib.parse").parse.unquote(pwd)} - {""}:
        text = text.replace(secret, "***")
    return text


def is_postgres() -> bool:
    return (settings.database_url or "").startswith(("postgres://", "postgresql://"))


class _Result:
    """Same surface for both drivers: rowcount, lastrowid, fetchone(), fetchall()."""
    def __init__(self, rows=None, rowcount=-1, lastrowid=None):
        self._rows, self.rowcount, self.lastrowid = rows or [], rowcount, lastrowid

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _SQLite:
    def __init__(self):
        self.c = sqlite3.connect(_path(), timeout=2.0, isolation_level=None)
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA journal_mode=WAL")
        self.c.execute("PRAGMA busy_timeout=2000")

    def execute(self, sql, args=()):
        cur = self.c.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()] if cur.description else []
        return _Result(rows, cur.rowcount, cur.lastrowid)

    def script(self, sql):
        self.c.executescript(sql)

    def close(self):
        self.c.close()


_pg_local = threading.local()
_pg_generation = 0


def reset_connections():
    """Make every thread reconnect on its next query (tests reset the schema between cases)."""
    global _pg_generation
    _pg_generation += 1


class _Postgres:
    """Supabase/Postgres. One connection per thread, reused across requests on a warm
    serverless instance (a fresh TLS connect per query would blow the latency budget).
    Use Supabase's *pooler* URL (port 6543); prepared statements are off for it."""
    def __init__(self):
        import psycopg
        from psycopg.rows import dict_row
        c = getattr(_pg_local, "conn", None)
        stale = (getattr(_pg_local, "url", None) != settings.database_url or getattr(_pg_local, "gen", None) != _pg_generation)
        if c is not None and stale:
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
            c = None
        if c is None or c.closed:
            c = psycopg.connect(safe_database_url(settings.database_url), autocommit=True, row_factory=dict_row,
                                prepare_threshold=None, connect_timeout=5)
            _pg_local.conn, _pg_local.url, _pg_local.gen = c, settings.database_url, _pg_generation
        self.c = c

    @staticmethod
    def _sql(sql: str) -> str:
        return sql.replace("%", "%%").replace("?", "%s")

    def execute(self, sql, args=()):
        try:
            cur = self.c.execute(self._sql(sql), list(args))
        except Exception:
            # Broken connection (idle timeout on the pooler): drop it so the next call reconnects.
            if self.c.closed or self.c.broken:
                _pg_local.conn = None
            raise
        rows = cur.fetchall() if cur.description else []
        last = rows[0].get("id") if rows and sql.lstrip().upper().startswith("INSERT") else None
        return _Result([dict(r) for r in rows], cur.rowcount, last)

    def script(self, sql):
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
        for stmt in (x.strip() for x in sql.split(";")):
            if stmt:
                self.c.execute(stmt)

    def close(self):
        pass  # kept open for reuse


@contextmanager
def conn():
    c = _Postgres() if is_postgres() else _SQLite()
    try:
        yield c
    finally:
        c.close()


# Columns added after the first deploy. migrate() adds whichever are missing, on SQLite or Postgres,
# so an existing Supabase database upgrades itself on the next cold start.
ADDED_COLUMNS = {
    "leads": [("stage", "TEXT"), ("stage_at", "TEXT"), ("stage_by", "TEXT"), ("claimed_by_tg", "TEXT"),
              ("self_booked", "INTEGER DEFAULT 0")],
    "calls": [("purged", "INTEGER DEFAULT 0")],
}


def _columns(c, table: str) -> set[str]:
    if is_postgres():
        rows = c.execute("SELECT column_name AS name FROM information_schema.columns WHERE table_name=?", (table,)).fetchall()
    else:
        rows = c.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"] for r in rows}


def migrate(c):
    for table, cols in ADDED_COLUMNS.items():
        have = _columns(c, table)
        for name, typ in cols:
            if name not in have:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")


def init():
    with conn() as c:
        c.script(SCHEMA)
        migrate(c)


def row(sql, *args) -> dict | None:
    with conn() as c:
        return c.execute(sql, args).fetchone()


def rows(sql, *args) -> list[dict]:
    with conn() as c:
        return c.execute(sql, args).fetchall()


def execute(sql, *args) -> _Result:
    with conn() as c:
        return c.execute(sql, args)


NO_ID_TABLES = {"rule_overrides"}  # keyed by `key`, no serial id


def insert(table: str, data: dict) -> int:
    cols = ",".join(data)
    q = ",".join("?" for _ in data)
    sql = f"INSERT INTO {table} ({cols}) VALUES ({q})"
    if is_postgres() and "id" not in data and table not in NO_ID_TABLES:
        sql += " RETURNING id"
    with conn() as c:
        return c.execute(sql, list(data.values())).lastrowid


def update(table: str, id_, data: dict, id_col="id"):
    sets = ",".join(f"{k}=?" for k in data)
    with conn() as c:
        c.execute(f"UPDATE {table} SET {sets} WHERE {id_col}=?", [*data.values(), id_])


def j(v) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def unj(v, default=None):
    if v in (None, ""):
        return default
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default
