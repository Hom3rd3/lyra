from collections import deque


def target_allowed(actor_id, owner_id, actor_rank, target_id, target_rank,
                   bot_id, bot_rank):
    return (target_id not in (actor_id, owner_id, bot_id)
            and bot_rank > target_rank
            and (actor_id == owner_id or actor_rank > target_rank))


class SpamDetector:
    def __init__(self, limit=6, window=8):
        self.limit, self.window = limit, window
        self.messages = {}

    def hit(self, key, now):
        # Bound memory even when many different members send messages.
        if len(self.messages) > 10000:
            self.messages = {k: q for k, q in self.messages.items()
                             if q and now - q[-1] < self.window}
        queue = self.messages.setdefault(key, deque(maxlen=self.limit))
        while queue and now - queue[0] >= self.window:
            queue.popleft()
        queue.append(now)
        if len(queue) >= self.limit:
            queue.clear()
            return True
        return False
