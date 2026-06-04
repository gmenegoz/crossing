import base64
import random
import struct
from pathlib import Path

from app.models import LAYERS, Pieces

ASSETS_DIR = Path(__file__).parent.parent / "assets"

LAYER_ORDER = ["legback", "body", "wing", "legfront", "head", "tail"]
LAYER_POSITION = {
    "head": (-70, 20),
    "body": (110, 131),
    "wing": (300, 0),
    "legfront": (-110, 220),
    "legback": (-110, 220),
    "tail": (460, 70),
}

# Cache: "layer/filename" -> {b64, w, h}
_cache: dict[str, dict] = {}


def _build_cache() -> None:
    for layer in LAYERS:
        folder = ASSETS_DIR / layer
        for png in folder.glob("*.png"):
            key = f"{layer}/{png.name}"
            data = png.read_bytes()
            w = struct.unpack(">I", data[16:20])[0]
            h = struct.unpack(">I", data[20:24])[0]
            b64 = base64.b64encode(data).decode("ascii")
            _cache[key] = {"b64": b64, "w": w, "h": h}


_build_cache()


def available_pngs(layer: str) -> list[str]:
    return sorted(p.name for p in (ASSETS_DIR / layer).glob("*.png"))


def random_pieces() -> Pieces:
    return Pieces(**{layer: random.choice(available_pngs(layer)) for layer in LAYERS})


def compose_svg(pieces: Pieces) -> str:
    parts = []
    for layer in LAYER_ORDER:
        filename = getattr(pieces, layer)
        key = f"{layer}/{filename}"
        entry = _cache[key]
        x, y = LAYER_POSITION[layer]
        parts.append({"x": x, "y": y, "w": entry["w"], "h": entry["h"], "b64": entry["b64"]})

    min_x = min(p["x"] for p in parts)
    min_y = min(p["y"] for p in parts)
    max_x = max(p["x"] + p["w"] for p in parts)
    max_y = max(p["y"] + p["h"] for p in parts)
    vw, vh = max_x - min_x, max_y - min_y

    images_xml = "\n".join(
        f'  <image x="{p["x"]}" y="{p["y"]}" width="{p["w"]}" height="{p["h"]}" '
        f'xlink:href="data:image/png;base64,{p["b64"]}" />'
        for p in parts
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="{min_x} {min_y} {vw} {vh}" '
        f'width="{vw}" height="{vh}">\n'
        f"{images_xml}\n"
        f"</svg>\n"
    )
