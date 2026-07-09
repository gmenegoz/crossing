import base64
import re
import io
from uuid import UUID, uuid4
from PIL import Image

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from fastapi.responses import Response as RawResponse

from app.composer import available_pngs, compose_svg, process_imported, random_pieces
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

# Match layer name as substring of filename stem, longest match first (legfront before front)
_LAYER_PATTERN = re.compile(
    r"(?i)(" + "|".join(sorted(LAYERS, key=len, reverse=True)) + r")"
)


def _infer_layer(filename: str) -> str | None:
    stem = filename.rsplit(".", 1)[0]
    m = _LAYER_PATTERN.search(stem)
    return m.group(1).lower() if m else None


def get_store(request: Request, response: Response) -> ChimeraStore:
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid4())
        response.set_cookie("session_id", session_id, max_age=600, samesite="lax", httponly=True)
    return registry.get_or_create(session_id)


def _to_list_item(c: Chimera) -> ChimeraListItem:
    return ChimeraListItem(id=c.id, number=c.number, name=c.name, svg=c.svg)

def _img_to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")

@router.get("/layers")
def get_layers(store: ChimeraStore = Depends(get_store)) -> dict[str, list[str]]:
    extra = store.imported_files()
    return {layer: available_pngs(layer, extra) for layer in LAYERS}


@router.post("/import-pieces")
async def import_pieces(
    files: list[UploadFile],
    store: ChimeraStore = Depends(get_store),
) -> dict[str, list[str]]:
    imported: dict[str, list[str]] = {layer: [] for layer in LAYERS}
    for upload in files:
        layer = _infer_layer(upload.filename or "")
        if layer is None:
            continue
        data = await upload.read()
        entries = process_imported(layer, upload.filename, data)
        store.add_imported(layer, upload.filename, entries)
        imported[layer].append(upload.filename)
    return {layer: fnames for layer, fnames in imported.items() if fnames}


@router.get("/imported-preview/{layer}/{filename}")
def imported_preview(layer: str, filename: str, store: ChimeraStore = Depends(get_store)) -> RawResponse:
    cache = store.imported_cache()
    key = f"{layer}/{filename}"
    entry = cache.get(key)
    if entry is None:
        raise HTTPException(status_code=404, detail="Not found")
    return RawResponse(content=base64.b64decode(_img_to_b64(entry)), media_type="image/png")


@router.get("/chimeras")
def list_chimeras(store: ChimeraStore = Depends(get_store)) -> list[ChimeraListItem]:
    return [_to_list_item(c) for c in store.all_ordered()]


@router.post("/chimeras/random")
def create_random(store: ChimeraStore = Depends(get_store)) -> Chimera:
    pieces = random_pieces(store.imported_files())
    number = store.next_number()
    chimera = Chimera(
        number=number,
        name=f"crossing{number}",
        pieces=pieces,
        svg=compose_svg(pieces, store.imported_cache()),
    )
    store.add(chimera)
    return chimera


@router.post("/chimeras/manual")
def create_manual(body: CreateManualRequest, store: ChimeraStore = Depends(get_store)) -> Chimera:
    number = store.next_number()
    chimera = Chimera(
        number=number,
        name=f"crossing{number}",
        pieces=body.pieces,
        svg=compose_svg(body.pieces, store.imported_cache()),
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
    updated = chimera.model_copy(update={
        "pieces": body.pieces,
        "svg": compose_svg(body.pieces, store.imported_cache()),
    })
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
