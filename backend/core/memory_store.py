class MemoryStore:
    def __init__(self):
        # In a real environment, this might use Redis or a cache layer syncing with Supabase
        self._store = {}

    def get_session_state(self, session_id: str) -> dict:
        return self._store.get(session_id, {})

    def save_session_state(self, session_id: str, state: dict):
        self._store[session_id] = state

    async def log_episodic_memory(
        self, session_id: str, state: dict, action: str, outcome: dict, reward: float
    ):
        """Asynchronously flush to the 'episodic_memory' table within Supabase"""
        pass


memory_store = MemoryStore()
