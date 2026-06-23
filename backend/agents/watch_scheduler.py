"""
Background scheduler for watch agents.

A single asyncio task wakes every TICK_SECONDS, finds active products whose
next_run_at is due, and runs their rounds strictly sequentially (one playwright
scrape at a time keeps memory + Kleinanzeigen rate pressure sane).

next_run_at is bumped to now + interval BEFORE the round starts so a slow round
never causes double-scheduling. Manual "run now" just sets next_run_at = now.
"""
import asyncio
import logging
from datetime import datetime, timedelta

from agents.watcher import run_watch_round
from database import Database

logger = logging.getLogger(__name__)

TICK_SECONDS = 15


class WatchScheduler:
    def __init__(self, db: Database):
        self.db = db
        self.running_ids: set[int] = set()   # products currently in a round
        self._task: asyncio.Task | None = None
        self._round_lock = asyncio.Lock()    # one round at a time

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            logger.info("watch scheduler started")

    def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()

    async def trigger_now(self, product_id: int):
        """Schedule an immediate round (picked up within one tick)."""
        await self.db.update_watch_product(product_id, {
            "next_run_at": datetime.now().isoformat(),
        })

    async def _loop(self):
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("watch scheduler tick failed")
            await asyncio.sleep(TICK_SECONDS)

    async def _tick(self):
        now = datetime.now()
        products = await self.db.get_watch_products()
        for p in products:
            if not p.get("active"):
                continue
            pid = p["id"]
            if pid in self.running_ids:
                continue
            nra = p.get("next_run_at")
            try:
                due = nra is None or datetime.fromisoformat(nra) <= now
            except (TypeError, ValueError):
                due = True
            if not due:
                continue

            interval = max(5, int(p.get("interval_minutes") or 20))
            await self.db.update_watch_product(pid, {
                "next_run_at": (now + timedelta(minutes=interval)).isoformat(),
            })
            self.running_ids.add(pid)
            try:
                async with self._round_lock:
                    await run_watch_round(pid, self.db)
            finally:
                self.running_ids.discard(pid)
