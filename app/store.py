from uuid import UUID

from app.models import Chimera


class ChimeraStore:
    def __init__(self) -> None:
        self._chimeras: dict[UUID, Chimera] = {}
        self._counter: int = 0

    def next_number(self) -> int:
        self._counter += 1
        return self._counter

    def add(self, chimera: Chimera) -> None:
        self._chimeras[chimera.id] = chimera

    def get(self, id: UUID) -> Chimera | None:
        return self._chimeras.get(id)

    def all_ordered(self) -> list[Chimera]:
        return sorted(self._chimeras.values(), key=lambda c: c.number)

    def delete(self, id: UUID) -> bool:
        return self._chimeras.pop(id, None) is not None

    def update(self, chimera: Chimera) -> None:
        self._chimeras[chimera.id] = chimera


class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, ChimeraStore] = {}

    def get_or_create(self, session_id: str) -> ChimeraStore:
        if session_id not in self._sessions:
            self._sessions[session_id] = ChimeraStore()
        return self._sessions[session_id]


registry = SessionRegistry()
