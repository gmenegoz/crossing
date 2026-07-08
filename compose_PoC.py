import base64
import io
import random
from datetime import datetime
from pathlib import Path
from itertools import groupby

from PIL import Image

ASSETS_DIR = Path(__file__).parent / "assets"
OUTPUT_DIR = Path(__file__).parent / "output"

# Layers with _l/_r suffix are the left/right halves of the original PNG.
# The base name (without suffix) is the assets subfolder.
LAYER_ORDER = ["legback", "body", "legfront", "head", "tail", "wing"]
LAYER_POSITION = {
    "head":       (0, 0),
    "body":       (183, 51),
    "wing":       (345, 0),
    "legfront": (0, 181),
    "legfront_l": (0, 181),
    "legfront_r": (380, 181),
    "legback":  (0, 181),
    "legback_l":  (0, 181),
    "legback_r":  (380, 181),
    "tail":       (519, 0),
}

def pick_random_png(subfolder: str) -> Path:
    folder = ASSETS_DIR / subfolder
    pngs = sorted(folder.glob("*.png"))
    if not pngs:
        raise FileNotFoundError(f"No PNG files found in {folder}")
    return random.choice(pngs)


def load_piece(layer: str, path: Path) -> tuple[Image.Image, int, int]:
    """Load a PNG, apply split if needed, then autocrop to content bounding box."""
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

def img_to_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")

def add_part(img: Image.Image, layer: str, path: str, parts: list) -> list:
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    w, h = img.size
    b64 = img_to_b64(img)
    offset = (bbox[0], bbox[1]) if bbox else (0,0)
    x, y =  tuple(map(sum, zip(LAYER_POSITION[layer], offset)))
    parts.append({"layer": layer, "x": x, "y": y, "w": w, "h": h, "b64": b64})
    print(f"  {layer:14s} → {path.name}  ({w}×{h}) at ({x},{y})")
    return parts

def compose():
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Map subfolder -> chosen PNG path (so _l and _r share the same file)
    chosen: dict[str, Path] = {}
    for layer in LAYER_ORDER:
        subfolder = layer
        if subfolder not in chosen:
            chosen[subfolder] = pick_random_png(subfolder)

    parts = []
    for layer in LAYER_ORDER:
        subfolder = layer
        path = chosen[subfolder]
        img = load_piece(layer, path)
        if layer.startswith("leg"):
            legs = split_legs(img)
            if len(legs) == 1:
                parts = add_part(legs[0], layer, path, parts)
            else:
                parts = add_part(legs[0], layer+"_l", path, parts)
                parts = add_part(legs[1], layer+"_r", path, parts)
        else:
            parts = add_part(img, layer, path, parts)
        

    min_x = min(p["x"] for p in parts)
    min_y = min(p["y"] for p in parts)
    max_x = max(p["x"] + p["w"] for p in parts)
    max_y = max(p["y"] + p["h"] for p in parts)
    vw, vh = max_x - min_x, max_y - min_y

    images_xml = "\n".join(
        f'    <image x="{p["x"]+240}" y="{p["y"]+180}" width="{p["w"]}" height="{p["h"]}" '
        f'xlink:href="data:image/png;base64,{p["b64"]}" />'
        for p in parts
    )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="{min_x} {min_y} {vw} {vh}" '
        f'width="{vw}" height="{vh}">\n'
        f'  <g id="chimera" transform="scale(0.5)">\n'
        f"{images_xml}\n"
        f'  </g>\n'
        f"</svg>\n"
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"crossing_{timestamp}.svg"
    out_path.write_text(svg, encoding="utf-8")
    print(f"\nSaved → {out_path}")


if __name__ == "__main__":
    compose()
