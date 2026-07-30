#!/usr/bin/env python3
"""Detect a white rectangle bordered by a black frame in a JPG, correct
perspective distortion, crop, resize to a fixed size and save as PNG."""

import sys
from pathlib import Path

import cv2
import numpy as np

TARGET_SIZE = {
    "head": (367, 483),
    "body": (438, 331),
    "tail": (240, 534),
    "legfront": (758, 357),
    "legback": (758, 357),
    "wing": (759, 534),
}
DEFAULT_TARGET = (367, 483)
ASPECT_TOLERANCE = 0.05


def target_size_for(filename: str) -> tuple[int, int]:
    stem = Path(filename).stem.lower()
    for key, size in TARGET_SIZE.items():
        if key in stem:
            return size
    return DEFAULT_TARGET


class FrameNotFoundError(Exception):
    pass


def order_corners(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).flatten()
    top_left = pts[np.argmin(s)]
    bottom_right = pts[np.argmax(s)]
    top_right = pts[np.argmin(diff)]
    bottom_left = pts[np.argmax(diff)]
    return np.array([top_left, top_right, bottom_right, bottom_left], dtype="float32")


RING_CONTRAST_RATIO = 0.6  # surrounding black frame must be this much darker than the rectangle


def is_framed_by_black_border(gray: np.ndarray, x: int, y: int, w: int, h: int) -> bool:
    """Check that a candidate white rectangle is fully enclosed by a darker
    border on all 4 sides (not touching the image edge, and not just
    adjacent to another bright region like a stray photo or lightbox)."""
    img_height, img_width = gray.shape
    pad = max(10, int(0.04 * max(w, h)))

    if x - pad < 0 or y - pad < 0 or x + w + pad > img_width or y + h + pad > img_height:
        return False

    inner_mean = gray[y : y + h, x : x + w].mean()
    top = gray[y - pad : y, x : x + w]
    bottom = gray[y + h : y + h + pad, x : x + w]
    left = gray[y : y + h, x - pad : x]
    right = gray[y : y + h, x + w : x + w + pad]

    return all(side.mean() < inner_mean * RING_CONTRAST_RATIO for side in (top, bottom, left, right))


def find_frame_corners(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise FrameNotFoundError("no contours found")

    image_area = gray.shape[0] * gray.shape[1]
    candidates = sorted(contours, key=cv2.contourArea, reverse=True)

    for contour in candidates[:15]:
        area = cv2.contourArea(contour)
        if area < image_area * 0.02 or area > image_area * 0.95:
            continue
        # Artwork/text inside the white rectangle can be dark enough to be
        # classified as background, carving notches into its contour; take
        # the convex hull so a busy interior doesn't break the quad fit.
        hull = cv2.convexHull(contour)
        perimeter = cv2.arcLength(hull, True)
        approx = cv2.approxPolyDP(hull, 0.02 * perimeter, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        x, y, w, h = cv2.boundingRect(approx)
        # The real scan target is a white rectangle fully enclosed by a black
        # frame; other bright regions in the shot (stray photos, lightboxes)
        # won't have a darker border on all 4 sides.
        if is_framed_by_black_border(gray, x, y, w, h):
            return order_corners(approx.reshape(4, 2).astype("float32"))

    raise FrameNotFoundError("no quadrilateral frame contour found")


def warp_to_rectangle(image: np.ndarray, corners: np.ndarray) -> np.ndarray:
    (top_left, top_right, bottom_right, bottom_left) = corners

    width_top = np.linalg.norm(top_right - top_left)
    width_bottom = np.linalg.norm(bottom_right - bottom_left)
    height_left = np.linalg.norm(bottom_left - top_left)
    height_right = np.linalg.norm(bottom_right - top_right)

    warped_width = int(round(max(width_top, width_bottom)))
    warped_height = int(round(max(height_left, height_right)))
    warped_width = max(warped_width, 1)
    warped_height = max(warped_height, 1)

    destination = np.array(
        [
            [0, 0],
            [warped_width - 1, 0],
            [warped_width - 1, warped_height - 1],
            [0, warped_height - 1],
        ],
        dtype="float32",
    )

    matrix = cv2.getPerspectiveTransform(corners, destination)
    return cv2.warpPerspective(image, matrix, (warped_width, warped_height))


def check_aspect_ratio(warped: np.ndarray, filename: str, target_size: tuple[int, int]) -> None:
    target_width, target_height = target_size
    target_ratio = target_width / target_height
    height, width = warped.shape[:2]
    ratio = width / height
    if abs(ratio - target_ratio) / target_ratio > ASPECT_TOLERANCE:
        print(
            f"[WARN] {filename}: detected aspect ratio {ratio:.3f} differs from "
            f"target {target_ratio:.3f} by more than {ASPECT_TOLERANCE:.0%}, "
            f"forcing resize anyway",
            file=sys.stderr,
        )


def correct_rotation(warped: np.ndarray, target_size: tuple[int, int]) -> np.ndarray:
    """Rotate 90° if the warped image's orientation doesn't match the target's."""
    target_width, target_height = target_size
    height, width = warped.shape[:2]
    is_portrait_target = target_height >= target_width
    is_portrait_image = height >= width
    if is_portrait_target != is_portrait_image:
        return cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
    return warped


def process_image(jpg_path: Path) -> Path:
    image = cv2.imread(str(jpg_path))
    if image is None:
        raise FrameNotFoundError(f"could not read image: {jpg_path}")

    target_size = target_size_for(jpg_path.name)

    corners = find_frame_corners(image)
    warped = warp_to_rectangle(image, corners)
    warped = correct_rotation(warped, target_size)
    check_aspect_ratio(warped, jpg_path.name, target_size)

    resized = cv2.resize(warped, target_size, interpolation=cv2.INTER_AREA)

    output_path = jpg_path.with_suffix(".png")
    cv2.imwrite(str(output_path), resized)
    return output_path


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path/to/image.jpg>", file=sys.stderr)
        return 2

    jpg_path = Path(sys.argv[1])
    target_width, target_height = target_size_for(jpg_path.name)
    try:
        output_path = process_image(jpg_path)
    except FrameNotFoundError as exc:
        print(f"[WARN] {jpg_path.name}: {exc}, skipping", file=sys.stderr)
        return 1

    print(f"[OK] {jpg_path.name} -> {output_path.name} ({target_width}x{target_height})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
