"""Sunset grade for The Sheryl photos (b-events.amsterdam/en/ruimtes/the-sheryl/).

Run: python -I scripts/grade_sheryl.py <folder with the downloaded photos>
"""
import os
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1]
OUT = os.path.join(ROOT, "assets")

SHOTS = {
    "sheryl-drone.jpg": "zaal-huren-B-Amsterdam-event-ruimte-The-Sheryl-3.png",
    "sheryl-lounge.jpg": "zaal-huren-B-Amsterdam-event-ruimte-The-Sheryl-4-scaled.jpg",
}


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def sunset(path, horizon):
    im = cv2.imread(path).astype(np.float32) / 255.0  # BGR
    h, w = im.shape[:2]
    b, g, r = im[..., 0], im[..., 1], im[..., 2]
    lum = 0.11 * b + 0.59 * g + 0.30 * r
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None]

    # sky = bright, blue-ish pixels above the horizon
    sky = smooth(0.0, 0.08, b - r) * smooth(0.38, 0.6, lum) * smooth(horizon + 0.04, horizon - 0.06, y)
    sky = cv2.GaussianBlur(sky.astype(np.float32), (0, 0), 6)

    # sunset gradient (RGB): dusky violet -> coral -> gold at the horizon
    stops = [(0.0, (0.36, 0.30, 0.55)), (0.45, (0.94, 0.52, 0.42)), (0.8, (1.0, 0.70, 0.40)), (1.0, (1.0, 0.82, 0.52))]
    k = np.clip(y / horizon, 0, 1)[..., 0]
    grad = np.zeros((h, 3), np.float32)
    for (a, ca), (bb, cb) in zip(stops, stops[1:]):
        m = (k >= a) & (k <= bb)
        tt = ((k[m] - a) / (bb - a))[:, None]
        grad[m] = np.array(ca) * (1 - tt) + np.array(cb) * tt
    grad = grad[:, ::-1][:, None, :]  # RGB -> BGR, broadcast across width
    detail = 0.8 + 0.4 * (lum - cv2.GaussianBlur(lum, (0, 0), 25))[..., None] * 4 + 0.15
    skyimg = np.clip(grad * detail, 0, 1)
    im = im * (1 - sky[..., None]) + skyimg * sky[..., None]

    # golden-hour grade: warm highlights, cool-ish shadows, slightly darker
    lum = (0.11 * im[..., 0] + 0.59 * im[..., 1] + 0.30 * im[..., 2])[..., None]
    warm = np.array([0.70, 0.90, 1.18], np.float32)
    cool = np.array([1.06, 0.98, 0.92], np.float32)
    im = im * (warm * lum + cool * (1 - lum))
    im = np.clip(im, 0, 1) ** 1.12

    # low sun glow near the horizon, right side
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx - w * 0.78) / w) ** 2 + ((yy - h * horizon) / h) ** 2 * 2.5)
    glow = np.clip(1 - d / 0.5, 0, 1) ** 2.2
    im = im + glow[..., None] * np.array([0.05, 0.22, 0.42], np.float32)
    v = np.clip(1 - (((xx - w / 2) / w) ** 2 + ((yy - h / 2) / h) ** 2) * 0.9, 0.55, 1)
    im = np.clip(im * v[..., None], 0, 1)
    return (im * 255).astype(np.uint8)


HORIZON = {"sheryl-drone.jpg": 0.52, "sheryl-lounge.jpg": 0.50}

for out, src in SHOTS.items():
    cv2.imwrite(os.path.join(OUT, out), sunset(os.path.join(SRC, src), HORIZON[out]), [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(out)
