import io
from pathlib import Path
from typing import List, Tuple, Union
from PIL import Image
import numpy as np
from af_aidevs.schemas.vision import TilePinout

# Calibrated grid bounding box for 598x422 image
GRID_X0 = 142
GRID_Y0 = 90
TILE_W = 95
TILE_H = 95
DARK_THRESHOLD = 80.0  # Wire pixel intensity threshold in grayscale


def load_image(image_input: Union[Path, str, bytes, Image.Image]) -> Image.Image:
    """Loads an image into a PIL RGBA Image from Path, string, bytes, or PIL Image."""
    if isinstance(image_input, Image.Image):
        return image_input.convert("RGBA")
    if isinstance(image_input, bytes):
        return Image.open(io.BytesIO(image_input)).convert("RGBA")
    path = Path(image_input)
    if path.exists():
        return Image.open(path).convert("RGBA")
    raise FileNotFoundError(f"Image not found at {image_input}")


def crop_tiles(image_input: Union[Path, str, bytes, Image.Image]) -> List[List[Image.Image]]:
    """Slices a 3x3 puzzle board image into a matrix of 9 PIL tile images in memory."""
    img = load_image(image_input)
    w, h = img.size
    if (w, h) == (800, 450):
        gx0, gy0, tw, th = 238, 100, 95, 95
    else:
        gx0, gy0, tw, th = 142, 90, 95, 95

    tiles: List[List[Image.Image]] = []

    for r in range(3):
        row_tiles: List[Image.Image] = []
        for c in range(3):
            x = gx0 + c * tw
            y = gy0 + r * th
            tile_crop = img.crop((x, y, x + tw, y + th))
            row_tiles.append(tile_crop)
        tiles.append(row_tiles)

    return tiles


def extract_tile_pinout(tile: Image.Image) -> Tuple[TilePinout, float]:
    """
    Analyzes a single cropped tile using robust min-pixel edge sampling.
    Returns (TilePinout, confidence_score).
    """
    gray = tile.convert("L")
    arr = np.array(gray)

    # Sample central safe regions along each 95x95 edge (avoiding 0-5 and 90-95 boundary lines)
    top_min = float(arr[10:25, 40:55].min())
    bottom_min = float(arr[70:85, 40:55].min())
    left_min = float(arr[40:55, 10:25].min())
    right_min = float(arr[40:55, 70:85].min())

    top_pin = top_min < DARK_THRESHOLD
    bottom_pin = bottom_min < DARK_THRESHOLD
    left_pin = left_min < DARK_THRESHOLD
    right_pin = right_min < DARK_THRESHOLD

    # Compute contrast confidence
    margins = [abs(val - DARK_THRESHOLD) for val in [top_min, bottom_min, left_min, right_min]]
    confidence = float(min(1.0, 0.70 + (min(margins) / 100.0) * 0.30))

    pinout = TilePinout(top=top_pin, right=right_pin, bottom=bottom_pin, left=left_pin)
    return pinout, confidence


def extract_board_pinouts(image_input: Union[Path, str, bytes, Image.Image]) -> Tuple[List[List[TilePinout]], List[List[float]]]:
    """Extracts 4-way pinouts and confidence scores for all 9 tiles on the board in memory."""
    tiles = crop_tiles(image_input)
    board_pinouts: List[List[TilePinout]] = []
    board_confidence: List[List[float]] = []

    for row in tiles:
        row_pinouts: List[TilePinout] = []
        row_conf: List[float] = []
        for tile in row:
            pinout, conf = extract_tile_pinout(tile)
            row_pinouts.append(pinout)
            row_conf.append(conf)
        board_pinouts.append(row_pinouts)
        board_confidence.append(row_conf)

    return board_pinouts, board_confidence
