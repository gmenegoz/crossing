import base64
import io
import random
from pathlib import Path

from PIL import Image

from app.models import LAYERS, Pieces

ASSETS_DIR = Path(__file__).parent.parent / "assets"

LAYER_ORDER = ["legback_l", "legback_r", "body", "legfront_l", "legfront_r", "head", "tail", "wing"]
LAYER_POSITION = {
    "head":       (0, 0),
    "body":       (183, 51),
    "wing":       (345, 0),
    "legfront_l": (0, 181),
    "legfront_r": (380, 181),
    "legback_l":  (0, 181),
    "legback_r":  (380, 181),
    "tail":       (519, 0),
}
OPTIONAL_LAYERS = ["tail", "wing", "legfront", "legback"]

# Global cache for built-in assets: "layer_variant/filename" -> {b64, w, h}
_cache: dict[str, dict] = {}


def _split_legs(layer: str, img: Image.Image) -> Image.Image:
    """Apply left/right split (for leg layers) and autocrop to content bounding box."""
    w, h = img.size
    if layer.endswith("_l"):
        img = img.crop((0, 0, w // 2, h))
    elif layer.endswith("_r"):
        img = img.crop((w // 2, 0, w, h))
    return img

def _get_offset(img: Image.Image) -> (int, int):
    bbox = img.getbbox()
    return (bbox[0], bbox[1]) if bbox else (0,0)
 
def _process_piece(layer: str, img: Image.Image) -> Image.Image:
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    return img


def _img_to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _build_cache() -> None:
    for layer in LAYERS:
        folder = ASSETS_DIR / layer
        for png in folder.glob("*.png"):
            img = Image.open(png).convert("RGBA")
            if layer in ("legfront", "legback"):
                for variant in ("_l", "_r"):
                    splitted = _split_legs(layer + variant, img.copy())
                    offset = _get_offset(splitted)
                    px,py = tuple(map(sum, zip(LAYER_POSITION[layer+variant], offset))) 
                    processed = _process_piece(layer + variant, splitted)
                    pw, ph = processed.size
                    _cache[f"{layer}{variant}/{png.name}"] = {"b64": _img_to_b64(processed), "w": pw, "h": ph, "x": px, "y": py}
            else:
                offset = _get_offset(img) 
                processed = _process_piece(layer, img)
                pw, ph = processed.size
                px,py = tuple(map(sum, zip(LAYER_POSITION[layer], offset)))
                _cache[f"{layer}/{png.name}"] = {"b64": _img_to_b64(processed), "w": pw, "h": ph, "x": px, "y": py}
            


_build_cache()




def available_pngs(layer: str, extra_files: dict[str, list[str]] | None = None) -> list[str]:
    builtin = sorted(p.name for p in (ASSETS_DIR / layer).glob("*.png"))
    if extra_files and extra_files.get(layer):
        return builtin + extra_files[layer]
    return builtin


def process_imported(layer: str, filename: str, data: bytes) -> dict[str, dict]:
    """Process an uploaded PNG for the given layer. Returns cache entries to store."""
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    entries: dict[str, dict] = {}
    if layer in ("legfront", "legback"):
        for variant in ("_l", "_r"):
            splitted = _split_legs(layer + variant, img.copy())
            offset = _get_offset(splitted)
            processed = _process_piece(layer + variant, splitted)
            px,py = tuple(map(sum, zip(LAYER_POSITION[layer+variant], offset))) 
            pw, ph = processed.size
            entries[f"{layer}{variant}/{filename}"] = {"b64": _img_to_b64(processed), "w": pw, "h": ph, "x": px, "y": py}
    else:
        offset = _get_offset(img)
        processed = _process_piece(layer, img)
        pw, ph = processed.size
        px,py = tuple(map(sum, zip(LAYER_POSITION[layer], offset)))
        entries[f"{layer}/{filename}"] = {"b64": _img_to_b64(processed), "w": pw, "h": ph, "x": px, "y": py}
    return entries


def random_pieces(extra_files: dict[str, list[str]] | None = None) -> Pieces:
    return Pieces(**{layer: random.choice(available_pngs(layer, extra_files)) for layer in LAYERS})


def compose_svg(pieces: Pieces, extra_cache: dict[str, dict] | None = None) -> str:
    parts = []
    for layer in LAYER_ORDER:
        subfolder = layer[:-2] if layer.endswith(("_l", "_r")) else layer
        filename = getattr(pieces, subfolder)
        key = f"{layer}/{filename}"
        entry = (extra_cache or {}).get(key) or _cache[key]
        parts.append({"x": entry["x"], "y": entry["y"], "w": entry["w"], "h": entry["h"], "b64": entry["b64"]})

    min_x = min(p["x"] for p in parts)
    min_y = min(p["y"] for p in parts)
    max_x = max(p["x"] + p["w"] for p in parts)
    max_y = max(p["y"] + p["h"] for p in parts)
    vw, vh = max_x - min_x, max_y - min_y

# TODO add id to each part
    images_xml = "\n".join(
        f'    <image x="{p["x"] + 120}" y="{p["y"] + 90}" width="{p["w"]}" height="{p["h"]}" '
        f'xlink:href="data:image/png;base64,{p["b64"]}" />'
        for p in parts
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="{min_x} {min_y} {vw} {vh}" '
        f'width="{vw}" height="{vh}">\n'
        f'  <g id="chimera" transform="scale(0.7)">\n'
        f"{images_xml}\n"
        f'  </g>\n'
        f"</svg>\n"
    )
