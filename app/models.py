from uuid import UUID, uuid4
from pydantic import BaseModel, Field

LAYERS = ["head", "body", "tail", "legfront", "legback", "wing"]


class Pieces(BaseModel):
    head: str
    body: str
    tail: str
    legfront: str
    legback: str
    wing: str


class Chimera(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    number: int
    name: str
    pieces: Pieces
    svg: str


class ChimeraListItem(BaseModel):
    id: UUID
    number: int
    name: str
    svg: str


class CreateManualRequest(BaseModel):
    pieces: Pieces


class UpdatePiecesRequest(BaseModel):
    pieces: Pieces


class RenameRequest(BaseModel):
    name: str
