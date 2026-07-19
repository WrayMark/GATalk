from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from PySide6.QtGui import QImage

from scenelens.analysis.models import UInt8Image


def numpy_to_qimage(
    rgb: UInt8Image,
    alpha: NDArray[np.uint8] | None = None,
) -> QImage:
    rgb_contiguous = np.ascontiguousarray(rgb)
    height, width = rgb_contiguous.shape[:2]

    if alpha is None:
        image = QImage(
            rgb_contiguous.data,
            width,
            height,
            rgb_contiguous.strides[0],
            QImage.Format.Format_RGB888,
        )
        return image.copy()

    alpha_contiguous = np.ascontiguousarray(alpha)
    if alpha_contiguous.shape != (height, width):
        raise ValueError("alpha shape must match rgb dimensions")
    rgba = np.dstack((rgb_contiguous, alpha_contiguous))
    rgba = np.ascontiguousarray(rgba)
    image = QImage(
        rgba.data,
        width,
        height,
        rgba.strides[0],
        QImage.Format.Format_RGBA8888,
    )
    return image.copy()

