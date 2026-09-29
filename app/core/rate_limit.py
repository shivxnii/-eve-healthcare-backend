import re
import time
from collections import defaultdict, deque
from threading import Lock


def parse_limit(value: str) -> tuple[int, int]:
    match = re.match(r"^(\d+)\s*/\s*(second|minute|hour)$", value.strip().lower())
    if not match:
        return 100, 60
    count = int(match.group(1))
    seconds = {"second": 1, "minute": 60, "hour": 3600}[match.group(2)]
    return count, seconds


class RateLimiter:
    def __init__(self, rule: str):
        self.limit, self.window = parse_limit(rule)
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = Lock()

    def allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True
