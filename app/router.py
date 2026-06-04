from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.composer import available_pngs, compose_svg, random_pieces
from app.models import (
    LAYERS,
    Chimera,
    ChimeraListItem,
    CreateManualRequest,
    RenameRequest,
    UpdatePiecesRequest,
)
from app.store import ChimeraStore, registry

router = APIRouter()

# TODO Update cookie at every action


def get_store(request: Request, response: Response) -> ChimeraStore:
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid4())
        response.set_cookie("session_id", session_id, max_age=60, samesite="lax", httponly=True)
    return registry.get_or_create(session_id)


def _to_list_item(c: Chimera) -> ChimeraListItem:
    return ChimeraListItem(id=c.id, number=c.number, name=c.name, svg=c.svg)


@router.get("/layers")
def get_layers() -> dict[str, list[str]]:
    return {layer: available_pngs(layer) for layer in LAYERS}


@router.get("/chimeras")
def list_chimeras(store: ChimeraStore = Depends(get_store)) -> list[ChimeraListItem]:
    return [_to_list_item(c) for c in store.all_ordered()]


@router.post("/chimeras/random")
def create_random(store: ChimeraStore = Depends(get_store)) -> Chimera:
    pieces = random_pieces()
    number = store.next_number()
    chimera = Chimera(
        number=number,
        name=f"crossing{number}",
        pieces=pieces,
        svg=compose_svg(pieces),
    )
    store.add(chimera)
    return chimera

# TODO Almost a duplicate of the previous one
@router.post("/chimeras/manual")
def create_manual(body: CreateManualRequest, store: ChimeraStore = Depends(get_store)) -> Chimera:
    number = store.next_number()
    chimera = Chimera(
        number=number,
        name=f"crossing{number}",
        pieces=body.pieces,
        svg=compose_svg(body.pieces),
    )
    store.add(chimera)
    return chimera


@router.get("/chimeras/{id}")
def get_chimera(id: UUID, store: ChimeraStore = Depends(get_store)) -> Chimera:
    chimera = store.get(id)
    if chimera is None:
        raise HTTPException(status_code=404, detail="Not found")
    return chimera


@router.patch("/chimeras/{id}/pieces")
def update_pieces(id: UUID, body: UpdatePiecesRequest, store: ChimeraStore = Depends(get_store)) -> Chimera:
    chimera = store.get(id)
    if chimera is None:
        raise HTTPException(status_code=404, detail="Not found")
    updated = chimera.model_copy(update={"pieces": body.pieces, "svg": compose_svg(body.pieces)})
    store.update(updated)
    return updated


@router.patch("/chimeras/{id}/name")
def rename(id: UUID, body: RenameRequest, store: ChimeraStore = Depends(get_store)) -> Chimera:
    chimera = store.get(id)
    if chimera is None:
        raise HTTPException(status_code=404, detail="Not found")
    updated = chimera.model_copy(update={"name": body.name})
    store.update(updated)
    return updated


@router.delete("/chimeras/{id}")
def delete_chimera(id: UUID, store: ChimeraStore = Depends(get_store)) -> dict:
    if not store.delete(id):
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}
