import base64
import random
import struct
from datetime import datetime
from pathlib import Path

ASSETS_DIR = Path(__file__).parent / "assets"
OUTPUT_DIR = Path(__file__).parent / "output"

LAYER_ORDER = ["legback", "body", "wing", "legfront", "head", "tail"]
LAYER_POSITION = {"head": (-70,0), "body": (110,131), "wing": (300,0), "legfront": (-110,220), "legback": (-110,220), "tail": (460,0)}


def png_dimensions(data: bytes) -> tuple[int, int]:
    # PNG: 8-byte signature, then IHDR chunk (4 len + 4 type + 4 width + 4 height)
    w = struct.unpack(">I", data[16:20])[0]
    h = struct.unpack(">I", data[20:24])[0]
    return w, h


def pick_random_png(subfolder: str) -> Path:
    folder = ASSETS_DIR / subfolder
    pngs = sorted(folder.glob("*.png"))
    if not pngs:
        raise FileNotFoundError(f"No PNG files found in {folder}")
    return random.choice(pngs)


def compose():
    OUTPUT_DIR.mkdir(exist_ok=True)

    parts = []
    for layer in LAYER_ORDER:
        path = pick_random_png(layer)
        data = path.read_bytes()
        w, h = png_dimensions(data)
        x, y = LAYER_POSITION[layer]
        b64 = base64.b64encode(data).decode("ascii")
        parts.append({"layer": layer, "path": path, "x": x, "y": y, "w": w, "h": h, "b64": b64})
        print(f"  {layer:10s} → {path.name}  ({w}×{h}) at ({x},{y})")

    min_x = min(p["x"] for p in parts)
    min_y = min(p["y"] for p in parts)
    max_x = max(p["x"] + p["w"] for p in parts)
    max_y = max(p["y"] + p["h"] for p in parts)

    images_xml = "\n".join(
        f'  <image x="{p["x"]}" y="{p["y"]}" width="{p["w"]}" height="{p["h"]}" '
        f'xlink:href="data:image/png;base64,{p["b64"]}" />'
        for p in parts
    )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="{min_x} {min_y} {max_x - min_x} {max_y - min_y}" '
        f'width="{max_x - min_x}" height="{max_y - min_y}">\n'
        f"{images_xml}\n"
        f"</svg>\n"
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"crossing_{timestamp}.svg"
    out_path.write_text(svg, encoding="utf-8")
    print(f"\nSaved → {out_path}")


if __name__ == "__main__":
    compose()
