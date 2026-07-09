import base64
import io
import random
from pathlib import Path
from itertools import groupby

from PIL import Image

from app.models import LAYERS, Pieces

ASSETS_DIR = Path(__file__).parent.parent / "assets"

LAYER_ORDER = ["legback", "body", "legfront", "head", "tail", "wing"]
LAYER_POSITION = {
    "head":         (0, 0),
    "body":         (183, 51),
    "wing":         (345, 0),
    "legfront":     (0, 181),
    "legfront_l":   (0, 181),
    "legfront_r":   (380, 181),
    "legback":      (0, 181),
    "legback_l":    (0, 181),
    "legback_r":    (380, 181),
    "tail":         (519, 0),
}

LAYER_PROBABILITY = {
    "head": 1,
    "body": 1,
    "wing": 0.15,
    "tail": 0.8,
    "legback": 0.95,
    "legfront": 0.95
}


# Global cache for built-in assets: "layer_variant/filename" -> {b64, w, h}
_cache: dict[str, dict] = {}

def load_piece( path: Path) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    return img

def split_legs(img: Image.Image) -> Image.Image:
    w, h = img.size
    xProjection = img.getchannel('A').getprojection()[0]
    grouped = [(k, len(list(g))) for k, g in groupby(xProjection)]
    print(grouped)
    if len(grouped) == 3:
        legs = [img] 
    else:
        if grouped[0][0] == 0:
            split_x = grouped[0][1]+grouped[1][1] + 1
        else:
            split_x = grouped[0][1]+ 1
        print (split_x)
        leftLeg = img.crop((0, 0, split_x, h))
        if grouped[-1][0] == 0:
            split_x = grouped[-1][1]+grouped[-2][1] + 1
        else:
            split_x = grouped[-1][1]+ 1
        print (split_x)
        rightLeg = img.crop((w - split_x, 0, w, h))
        legs = [leftLeg, rightLeg]
        
    return legs



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
            img = load_piece(png)
            _cache[f"{layer}/{png.name}"] = img


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
    entries[f"{layer}/{filename}"] = img
    return entries


def random_pieces(extra_files: dict[str, list[str]] | None = None) -> Pieces:
    parts = {}
    for layer in LAYER_ORDER:
        threshold = LAYER_PROBABILITY[layer]
        if layer == "legfront":
            if "legback" in parts.keys():
                threshold = 1.0
            else:
                continue
        if random.random() >= threshold:
            continue
        parts[layer] = random.choice(available_pngs(layer, extra_files))
        
    return Pieces(**parts)


def add_part(img: Image.Image, layer: str, path: str, parts: list) -> list:
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    w, h = img.size
    b64 = _img_to_b64(img)
    offset = (bbox[0], bbox[1]) if bbox else (0,0)
    x, y =  tuple(map(sum, zip(LAYER_POSITION[layer], offset)))
    parts.append({"layer": layer, "x": x, "y": y, "w": w, "h": h, "b64": b64})
    print(f"  {layer:14s} → {path}  ({w}×{h}) at ({x},{y})")
    return parts

def compose_svg(pieces: Pieces, extra_cache: dict[str, dict] | None = None) -> str:
    parts = []
    print(pieces)
    for layer in LAYER_ORDER:
        subfolder = layer
        filename = getattr(pieces, subfolder)
        if(filename):
            key = f"{layer}/{filename}"
            entry = (extra_cache or {}).get(key) or _cache[key]
            if layer.startswith("leg"):
                legs = split_legs(entry)
                if len(legs) == 1:
                    parts = add_part(legs[0], layer, key, parts)
                else:
                    parts = add_part(legs[0], layer+"_l", key, parts)
                    parts = add_part(legs[1], layer+"_r", key, parts)
            else:
                parts = add_part(entry, layer, key, parts)

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
