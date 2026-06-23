import aiosqlite
from datetime import datetime

DB_PATH = "kleinanzeigen.db"


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS searches (
                    id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    category TEXT DEFAULT 'all',
                    max_pages INTEGER DEFAULT 3,
                    created_at TEXT NOT NULL,
                    count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending'
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_id TEXT NOT NULL,
                    title TEXT,
                    price_text TEXT,
                    price_value REAL,
                    description TEXT,
                    location TEXT,
                    date_posted TEXT,
                    url TEXT,
                    km INTEGER,
                    year INTEGER,
                    fuel TEXT,
                    gearbox TEXT,
                    power_hp INTEGER,
                    condition TEXT,
                    color TEXT,
                    doors INTEGER,
                    seats INTEGER,
                    prev_owners INTEGER,
                    hu_until TEXT,
                    body_type TEXT,
                    features TEXT,
                    scraped_at TEXT,
                    FOREIGN KEY (search_id) REFERENCES searches(id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS arbitrage_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ran_at TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    domain TEXT,
                    product_query TEXT,
                    market_json TEXT,
                    deals_json TEXT,
                    products_json TEXT,
                    raw_text TEXT,
                    pipeline_run_id TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    created_at TEXT,
                    last_seen_at TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS watch_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    query TEXT NOT NULL,
                    current_query TEXT DEFAULT '',
                    category TEXT DEFAULT 'all',
                    plz TEXT DEFAULT '',
                    radius INTEGER DEFAULT 0,
                    price_min INTEGER DEFAULT 0,
                    price_max INTEGER DEFAULT 0,
                    year_from INTEGER DEFAULT 0,
                    year_to INTEGER DEFAULT 0,
                    km_max INTEGER DEFAULT 0,
                    ps_min INTEGER DEFAULT 0,
                    max_pages INTEGER DEFAULT 3,
                    interval_minutes INTEGER DEFAULT 20,
                    exclude TEXT DEFAULT '',
                    custom_prompt TEXT DEFAULT '',
                    active INTEGER DEFAULT 1,
                    notes TEXT DEFAULT '',
                    created_at TEXT,
                    last_run_at TEXT,
                    next_run_at TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS watch_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    search_id TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    status TEXT DEFAULT 'running',
                    query_used TEXT,
                    raw_count INTEGER DEFAULT 0,
                    new_count INTEGER DEFAULT 0,
                    reviewed_count INTEGER DEFAULT 0,
                    deal_count INTEGER DEFAULT 0,
                    market_json TEXT,
                    deals_json TEXT,
                    log TEXT,
                    error TEXT,
                    FOREIGN KEY (product_id) REFERENCES watch_products(id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS watch_seen (
                    product_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT,
                    price REAL,
                    first_seen_at TEXT,
                    verdict TEXT,
                    score INTEGER,
                    reason TEXT,
                    PRIMARY KEY (product_id, url)
                )
            """)
            # Migrate older DBs: add missing columns if not present.
            for col, typ in [
                ("gearbox", "TEXT"), ("power_hp", "INTEGER"),
                ("condition", "TEXT"), ("color", "TEXT"),
                ("doors", "INTEGER"), ("seats", "INTEGER"),
                ("prev_owners", "INTEGER"), ("hu_until", "TEXT"),
                ("body_type", "TEXT"), ("features", "TEXT"),
            ]:
                try:
                    await db.execute(f"ALTER TABLE listings ADD COLUMN {col} {typ}")
                except Exception:
                    pass  # column already exists
            # Multi-user migration: scope searches/products/runs to a user.
            for table in ("searches", "watch_products", "arbitrage_runs"):
                try:
                    await db.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER")
                except Exception:
                    pass  # column already exists
            # Multi-query migration: agent-maintained synonym search terms.
            try:
                await db.execute("ALTER TABLE watch_products ADD COLUMN query_aliases TEXT DEFAULT ''")
            except Exception:
                pass
            # Max listing age filter (default 60 days).
            try:
                await db.execute("ALTER TABLE watch_products ADD COLUMN max_age_days INTEGER DEFAULT 60")
            except Exception:
                pass
            await db.commit()

    async def save_search(self, search_id: str, query: str, category: str, max_pages: int,
                          user_id: int = None):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO searches (id, query, category, max_pages, created_at, status, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (search_id, query, category, max_pages, datetime.now().isoformat(), "running", user_id)
            )
            await db.commit()

    async def save_listings(self, search_id: str, listings: list):
        async with aiosqlite.connect(self.path) as db:
            for l in listings:
                await db.execute("""
                    INSERT INTO listings
                    (search_id, title, price_text, price_value, description, location, date_posted, url,
                     km, year, fuel, gearbox, power_hp, condition, color, doors, seats, prev_owners,
                     hu_until, body_type, features, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?,  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    search_id,
                    l.get("title", ""),
                    l.get("price_text", ""),
                    l.get("price_value"),
                    l.get("description", ""),
                    l.get("location", ""),
                    l.get("date_posted", ""),
                    l.get("url", ""),
                    l.get("km"),
                    l.get("year"),
                    l.get("fuel"),
                    l.get("gearbox"),
                    l.get("power_hp"),
                    l.get("condition"),
                    l.get("color"),
                    l.get("doors"),
                    l.get("seats"),
                    l.get("prev_owners"),
                    l.get("hu_until"),
                    l.get("body_type"),
                    l.get("features"),
                    l.get("scraped_at", ""),
                ))
            await db.execute(
                "UPDATE searches SET count = ?, status = ? WHERE id = ?",
                (len(listings), "done", search_id)
            )
            await db.commit()

    async def set_search_error(self, search_id: str, error: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE searches SET status = ? WHERE id = ?",
                (f"error:{error[:200]}", search_id)
            )
            await db.commit()

    async def get_listings(self, search_id: str) -> list:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM listings WHERE search_id = ? ORDER BY price_value ASC NULLS LAST",
                (search_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_searches(self, user_id: int = None) -> list:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            if user_id is None:
                cursor = await db.execute("SELECT * FROM searches ORDER BY created_at DESC")
            else:
                cursor = await db.execute(
                    "SELECT * FROM searches WHERE user_id = ? ORDER BY created_at DESC",
                    (user_id,),
                )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def delete_search(self, search_id: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM listings WHERE search_id = ?", (search_id,))
            await db.execute("DELETE FROM searches WHERE id = ?", (search_id,))
            await db.commit()

    async def save_arbitrage_run(
        self,
        ran_at: str,
        stage: str,
        domain: str = None,
        product_query: str = None,
        market_json: str = None,
        deals_json: str = None,
        products_json: str = None,
        raw_text: str = None,
        pipeline_run_id: str = None,
    ):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO arbitrage_runs
                (ran_at, stage, domain, product_query, market_json, deals_json,
                 products_json, raw_text, pipeline_run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ran_at, stage, domain, product_query, market_json, deals_json,
                 products_json, raw_text, pipeline_run_id),
            )
            await db.commit()

    async def get_arbitrage_runs(self, limit: int = 200) -> list:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM arbitrage_runs ORDER BY ran_at DESC LIMIT ?",
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_arbitrage_run(self, run_id: int) -> dict:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM arbitrage_runs WHERE id = ?",
                (run_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def delete_arbitrage_run(self, run_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM arbitrage_runs WHERE id = ?", (run_id,))
            await db.commit()

    # ── Settings ────────────────────────────────────────────────────────────

    async def get_setting(self, key: str) -> str:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else ""

    async def set_setting(self, key: str, value: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            await db.commit()

    # ── Watch products ──────────────────────────────────────────────────────

    WATCH_FIELDS = [
        "name", "query", "current_query", "category", "plz", "radius",
        "price_min", "price_max", "year_from", "year_to", "km_max", "ps_min",
        "max_pages", "interval_minutes", "exclude", "custom_prompt", "active",
        "max_age_days",
    ]

    async def create_watch_product(self, data: dict, user_id: int = None) -> int:
        now = datetime.now().isoformat()
        cols = self.WATCH_FIELDS + ["user_id", "created_at", "next_run_at"]
        vals = [data.get(f) for f in self.WATCH_FIELDS] + [user_id, now, now]
        placeholders = ", ".join("?" * len(cols))
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                f"INSERT INTO watch_products ({', '.join(cols)}) VALUES ({placeholders})",
                vals,
            )
            await db.commit()
            return cur.lastrowid

    async def update_watch_product(self, product_id: int, data: dict):
        sets, vals = [], []
        allowed = set(self.WATCH_FIELDS + ["notes", "query_aliases", "last_run_at", "next_run_at"])
        for k, v in data.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                vals.append(v)
        if not sets:
            return
        vals.append(product_id)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(f"UPDATE watch_products SET {', '.join(sets)} WHERE id = ?", vals)
            await db.commit()

    async def get_watch_products(self, user_id: int = None) -> list:
        """user_id=None returns ALL products (scheduler); else only that user's."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            if user_id is None:
                cur = await db.execute("SELECT * FROM watch_products ORDER BY created_at DESC")
            else:
                cur = await db.execute(
                    "SELECT * FROM watch_products WHERE user_id = ? ORDER BY created_at DESC",
                    (user_id,),
                )
            return [dict(r) for r in await cur.fetchall()]

    async def get_watch_product(self, product_id: int) -> dict:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM watch_products WHERE id = ?", (product_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def delete_watch_product(self, product_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM watch_runs WHERE product_id = ?", (product_id,))
            await db.execute("DELETE FROM watch_seen WHERE product_id = ?", (product_id,))
            await db.execute("DELETE FROM watch_products WHERE id = ?", (product_id,))
            await db.commit()

    # ── Watch runs ──────────────────────────────────────────────────────────

    async def create_watch_run(self, product_id: int, query_used: str, search_id: str = None) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT INTO watch_runs (product_id, search_id, started_at, status, query_used) "
                "VALUES (?, ?, ?, 'running', ?)",
                (product_id, search_id, datetime.now().isoformat(), query_used),
            )
            await db.commit()
            return cur.lastrowid

    async def update_watch_run(self, run_id: int, data: dict):
        allowed = {"search_id", "finished_at", "status", "raw_count", "new_count",
                   "reviewed_count", "deal_count", "market_json", "deals_json", "log", "error"}
        sets, vals = [], []
        for k, v in data.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                vals.append(v)
        if not sets:
            return
        vals.append(run_id)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(f"UPDATE watch_runs SET {', '.join(sets)} WHERE id = ?", vals)
            await db.commit()

    async def get_watch_runs(self, product_id: int, limit: int = 50) -> list:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM watch_runs WHERE product_id = ? ORDER BY started_at DESC LIMIT ?",
                (product_id, limit),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def get_watch_run(self, run_id: int) -> dict:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM watch_runs WHERE id = ?", (run_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    # ── Watch seen (dedup across rounds) ────────────────────────────────────

    async def get_seen_urls(self, product_id: int) -> set:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT url FROM watch_seen WHERE product_id = ?", (product_id,)
            ) as cur:
                return {r[0] for r in await cur.fetchall()}

    async def upsert_seen(self, product_id: int, entries: list[dict]):
        """entries: [{url, title, price, verdict, score, reason}]"""
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.path) as db:
            for e in entries:
                await db.execute(
                    """INSERT INTO watch_seen (product_id, url, title, price, first_seen_at, verdict, score, reason)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(product_id, url) DO UPDATE SET
                         verdict = excluded.verdict, score = excluded.score, reason = excluded.reason""",
                    (product_id, e.get("url", ""), e.get("title", ""), e.get("price"),
                     now, e.get("verdict", ""), e.get("score"), e.get("reason", "")),
                )
            await db.commit()

    async def get_top_seen(self, product_id: int, limit: int = 30) -> list:
        """Best listings ever found for this product (verdict top_deal/ok, score desc)."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM watch_seen WHERE product_id = ? AND verdict IN ('top_deal', 'ok') "
                "ORDER BY score DESC, first_seen_at DESC LIMIT ?",
                (product_id, limit),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    # ── Users ───────────────────────────────────────────────────────────────

    async def login_user(self, name: str) -> dict:
        """Create-or-get a user by name (case-insensitive). The FIRST user ever
        created claims all legacy rows that predate multi-user mode."""
        name = name.strip()
        now = datetime.now().isoformat()
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE name = ? COLLATE NOCASE", (name,)
            ) as cur:
                row = await cur.fetchone()
            if row:
                await db.execute("UPDATE users SET last_seen_at = ? WHERE id = ?", (now, row["id"]))
                await db.commit()
                return dict(row)

            async with db.execute("SELECT COUNT(*) FROM users") as cur:
                is_first = (await cur.fetchone())[0] == 0
            cur = await db.execute(
                "INSERT INTO users (name, created_at, last_seen_at) VALUES (?, ?, ?)",
                (name, now, now),
            )
            uid = cur.lastrowid
            if is_first:
                for table in ("searches", "watch_products", "arbitrage_runs"):
                    await db.execute(f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL", (uid,))
            await db.commit()
            return {"id": uid, "name": name, "created_at": now, "last_seen_at": now}

    async def get_users(self) -> list:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT id, name FROM users ORDER BY last_seen_at DESC") as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def count_watch_products(self, user_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM watch_products WHERE user_id = ?", (user_id,)
            ) as cur:
                return (await cur.fetchone())[0]

    # ── Retention / pruning ─────────────────────────────────────────────────

    async def prune_user_searches(self, user_id: int, keep: int = 50):
        """Delete a user's oldest manual searches beyond `keep`. Searches that
        belong to a watch run are governed by prune_watch_runs instead."""
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """SELECT id FROM searches
                   WHERE user_id = ?
                     AND id NOT IN (SELECT search_id FROM watch_runs WHERE search_id IS NOT NULL)
                   ORDER BY created_at DESC LIMIT -1 OFFSET ?""",
                (user_id, keep),
            ) as cur:
                old_ids = [r[0] for r in await cur.fetchall()]
            for sid in old_ids:
                await db.execute("DELETE FROM listings WHERE search_id = ?", (sid,))
                await db.execute("DELETE FROM searches WHERE id = ?", (sid,))
            await db.commit()
            return len(old_ids)

    async def prune_watch_runs(self, product_id: int, keep: int = 50):
        """Keep the newest `keep` runs per product; delete older runs together
        with their raw search + listings."""
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT id, search_id FROM watch_runs WHERE product_id = ? "
                "ORDER BY started_at DESC LIMIT -1 OFFSET ?",
                (product_id, keep),
            ) as cur:
                old = await cur.fetchall()
            for run_id, sid in old:
                if sid:
                    await db.execute("DELETE FROM listings WHERE search_id = ?", (sid,))
                    await db.execute("DELETE FROM searches WHERE id = ?", (sid,))
                await db.execute("DELETE FROM watch_runs WHERE id = ?", (run_id,))
            await db.commit()
            return len(old)

    async def prune_seen(self, product_id: int, keep: int = 2000):
        """Cap the dedup memory per product — old listings are offline anyway."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """DELETE FROM watch_seen WHERE product_id = ? AND url NOT IN (
                       SELECT url FROM watch_seen WHERE product_id = ?
                       ORDER BY first_seen_at DESC LIMIT ?)""",
                (product_id, product_id, keep),
            )
            await db.commit()
