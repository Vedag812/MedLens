"""
MedLens Image Preprocessing Module
Enhances low-quality medicine images for better OCR accuracy.
Multiple preprocessing strategies are tried and the best result is kept.
"""

import cv2
import numpy as np


def preprocess_for_ocr(img_array: np.ndarray) -> list[np.ndarray]:
    """
    Takes a raw image (numpy array, BGR or RGB) and returns multiple
    preprocessed versions optimized for OCR on medicine strips/bottles.
    
    Returns a list of processed images. The OCR engine should try
    each one and pick the result with the most text detected.
    """
    # Make sure we're working with BGR (OpenCV default)
    if len(img_array.shape) == 2:
        gray = img_array
        color = cv2.cvtColor(img_array, cv2.COLOR_GRAY2BGR)
    else:
        color = img_array.copy()
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

    results = []

    # Strategy 1: Enhanced original (good for decent quality photos)
    enhanced = _enhance_basic(color)
    results.append(enhanced)

    # Strategy 2: Aggressive contrast + denoise (for blurry/dark photos)
    high_contrast = _enhance_aggressive(gray)
    results.append(cv2.cvtColor(high_contrast, cv2.COLOR_GRAY2RGB))

    # Strategy 3: Adaptive threshold (for very low contrast text)
    adaptive = _adaptive_threshold(gray)
    results.append(cv2.cvtColor(adaptive, cv2.COLOR_GRAY2RGB))

    # Strategy 4: Sharpened + CLAHE (for out-of-focus photos)
    sharpened = _sharpen_and_clahe(gray)
    results.append(cv2.cvtColor(sharpened, cv2.COLOR_GRAY2RGB))

    return results


def _enhance_basic(color_img: np.ndarray) -> np.ndarray:
    """Basic enhancement: resize, slight denoise, slight sharpen."""
    img = color_img.copy()

    # Resize if too small (OCR works better on larger images)
    h, w = img.shape[:2]
    if max(h, w) < 800:
        scale = 800 / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # Resize if too large (saves processing time)
    if max(h, w) > 2000:
        scale = 2000 / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    # Light denoise
    img = cv2.fastNlMeansDenoisingColored(img, None, 6, 6, 7, 21)

    # Slight sharpen
    kernel = np.array([
        [0, -0.5, 0],
        [-0.5, 3, -0.5],
        [0, -0.5, 0]
    ])
    img = cv2.filter2D(img, -1, kernel)

    return img


def _enhance_aggressive(gray_img: np.ndarray) -> np.ndarray:
    """Aggressive enhancement for blurry or dark images."""
    img = gray_img.copy()

    # Resize up if small
    h, w = img.shape[:2]
    if max(h, w) < 800:
        scale = 800 / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # Heavy denoise
    img = cv2.fastNlMeansDenoising(img, None, 12, 7, 21)

    # CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    img = clahe.apply(img)

    # Strong unsharp mask
    blurred = cv2.GaussianBlur(img, (0, 0), 3)
    img = cv2.addWeighted(img, 2.0, blurred, -1.0, 0)

    # Otsu binarization
    _, img = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return img


def _adaptive_threshold(gray_img: np.ndarray) -> np.ndarray:
    """Adaptive thresholding for tricky lighting conditions."""
    img = gray_img.copy()

    # Resize up if small
    h, w = img.shape[:2]
    if max(h, w) < 800:
        scale = 800 / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # Denoise first
    img = cv2.fastNlMeansDenoising(img, None, 8, 7, 21)

    # Bilateral filter (preserves edges while smoothing)
    img = cv2.bilateralFilter(img, 9, 75, 75)

    # Adaptive threshold
    img = cv2.adaptiveThreshold(
        img, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=15,
        C=8
    )

    # Clean up noise with morphological operations
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    img = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)

    return img


def _sharpen_and_clahe(gray_img: np.ndarray) -> np.ndarray:
    """Sharpening + CLAHE for out-of-focus or motion-blurred photos."""
    img = gray_img.copy()

    # Resize up if small
    h, w = img.shape[:2]
    if max(h, w) < 800:
        scale = 800 / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    img = clahe.apply(img)

    # Unsharp mask (stronger version)
    blurred = cv2.GaussianBlur(img, (0, 0), 2)
    img = cv2.addWeighted(img, 1.8, blurred, -0.8, 0)

    # Denoise after sharpening to remove artifacts
    img = cv2.fastNlMeansDenoising(img, None, 6, 7, 21)

    return img


def auto_rotate(img_array: np.ndarray) -> np.ndarray:
    """
    Try to detect and correct image rotation.
    Useful when users take photos at an angle.
    """
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY) if len(img_array.shape) == 3 else img_array.copy()

    # Edge detection
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)

    # Hough line detection
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=100, maxLineGap=10)

    if lines is None or len(lines) == 0:
        return img_array

    # Calculate median angle of detected lines
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        # Only consider near-horizontal lines (likely text lines)
        if abs(angle) < 30:
            angles.append(angle)

    if not angles:
        return img_array

    median_angle = np.median(angles)

    # Only rotate if the skew is noticeable but not too extreme
    if abs(median_angle) < 0.5 or abs(median_angle) > 15:
        return img_array

    # Rotate the image
    h, w = img_array.shape[:2]
    center = (w // 2, h // 2)
    rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    rotated = cv2.warpAffine(img_array, rotation_matrix, (w, h),
                              flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)

    return rotated
