"""A tiny in-process LRU cache for code -> target_url lookups.

Why this is safe here and would not be elsewhere: a Link's `target_url` is
immutable once created. There is no edit endpoint. So a cached value can never
go stale, and the usual objection to per-replica caching — that replicas
disagree — cannot occur. If we ever add link editing, this cache becomes a bug
and has to be replaced with a shared cache plus invalidation.

`hit_count` is deliberately *not* cached; that changes on every request and is
written straight through to the database.

The hit/miss counters exist to feed a Prometheus gauge in Stage 6, so the
dashboard has a real business metric on it rather than only RED metrics.
"""

import threading
from collections import OrderedDict


class LRUCache:
    def __init__(self, maxsize: int) -> None:
        self._maxsize = maxsize
        self._data: OrderedDict[str, str] = OrderedDict()
        # Uvicorn serves plain `def` handlers from a threadpool, so this cache
        # is touched from multiple threads concurrently. OrderedDict mutation
        # is not atomic across move_to_end + __setitem__, hence the lock.
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> str | None:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self.hits += 1
                return self._data[key]
            self.misses += 1
            return None

    def put(self, key: str, value: str) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            if len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = 0
            self.misses = 0

    @property
    def size(self) -> int:
        return len(self._data)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0
