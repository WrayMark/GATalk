from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray

from scenelens.analysis.models import UInt8Image


def normalized_rect_to_pixels(
    rect: tuple[float, float, float, float],
    image_shape: tuple[int, ...],
) -> tuple[int, int, int, int]:
    height, width = int(image_shape[0]), int(image_shape[1])
    x, y, region_width, region_height = rect
    left = max(0, min(width - 1, int(round(x * width))))
    top = max(0, min(height - 1, int(round(y * height))))
    right = max(left + 1, min(width, int(round((x + region_width) * width))))
    bottom = max(top + 1, min(height, int(round((y + region_height) * height))))
    return left, top, right - left, bottom - top


def visible_asset_mask(
    rgb: UInt8Image,
    rect: tuple[float, float, float, float],
    *,
    iterations: int = 4,
) -> tuple[NDArray[np.uint8], str]:
    """Refine a visible-evidence rectangle; never infer occluded pixels."""

    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError("rgb must be an HxWx3 uint8 image")
    left, top, width, height = normalized_rect_to_pixels(rect, rgb.shape)
    mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
    if width < 6 or height < 6:
        mask[top : top + height, left : left + width] = 255
        return mask, "rectangle_proxy_v1"
    grabcut_mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
    bg_model = np.zeros((1, 65), np.float64)
    fg_model = np.zeros((1, 65), np.float64)
    inset = (
        min(left + 1, rgb.shape[1] - 1),
        min(top + 1, rgb.shape[0] - 1),
        max(1, width - 2),
        max(1, height - 2),
    )
    try:
        cv2.grabCut(
            np.ascontiguousarray(rgb),
            grabcut_mask,
            inset,
            bg_model,
            fg_model,
            max(1, int(iterations)),
            cv2.GC_INIT_WITH_RECT,
        )
        foreground = (grabcut_mask == cv2.GC_FGD) | (
            grabcut_mask == cv2.GC_PR_FGD
        )
        foreground[:top, :] = False
        foreground[top + height :, :] = False
        foreground[:, :left] = False
        foreground[:, left + width :] = False
        if int(foreground.sum()) < max(8, width * height // 100):
            raise ValueError("foreground too small")
        mask[foreground] = 255
        return mask, "grabcut_visible_v1"
    except (cv2.error, ValueError):
        mask[top : top + height, left : left + width] = 255
        return mask, "rectangle_proxy_v1"


def apply_transparent_mask(
    rgb: UInt8Image,
    mask: NDArray[np.uint8],
) -> NDArray[np.uint8]:
    if mask.shape != rgb.shape[:2]:
        raise ValueError("mask size must match image size")
    return np.dstack((rgb, mask)).astype(np.uint8, copy=False)

