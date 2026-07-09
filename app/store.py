from uuid import UUID
from PIL import Image
from app.models import LAYERS, Chimera


class ChimeraStore:
    def __init__(self) -> None:
        self._chimeras: dict[UUID, Chimera] = {}
        self._counter: int = 0
        self._imported: dict[str, dict] = {}              # "layer_variant/filename" -> {b64,w,h}
        self._imported_files: dict[str, list[str]] = {layer: [] for layer in LAYERS}

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

    def add_imported(self, layer: str, filename: str, entries: dict[str, Image.Image]) -> None:
        """Store processed cache entries for an imported piece and register its filename."""
        self._imported.update(entries)
        if filename not in self._imported_files[layer]:
            self._imported_files[layer].append(filename)

    def imported_files(self) -> dict[str, list[str]]:
        return {layer: list(files) for layer, files in self._imported_files.items()}

    def imported_cache(self) -> dict[str, dict]:
        return self._imported


class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, ChimeraStore] = {}

    def get_or_create(self, session_id: str) -> ChimeraStore:
        if session_id not in self._sessions:
            self._sessions[session_id] = ChimeraStore()
        return self._sessions[session_id]


registry = SessionRegistry()
