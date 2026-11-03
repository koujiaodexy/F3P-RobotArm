"""One pending display snapshot; transport events never pass through this mailbox."""
import threading

class SnapshotMailbox:
    def __init__(self):
        self._lock = threading.Lock()
        self._latest = None
        self.closed = False

    def put(self, snapshot):
        with self._lock:
            if not self.closed: self._latest = snapshot

    def take(self):
        with self._lock:
            latest, self._latest = self._latest, None
            return latest

    def close(self):
        with self._lock:
            self.closed = True
            self._latest = None
