"""Prepare video assets: trimmed logos, keyed BlueGecko logo, part photo, product screenshots.

Run: python -I scripts/prepare.py <images_dir> <release_notes_png_dir>
"""
import os
import shutil
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "assets")
DL = os.path.expanduser("~/Downloads")
REPO = os.path.dirname(os.path.dirname(ROOT))
IMG, RN = sys.argv[1], sys.argv[2]


def trim(rgba, pad=4):
    ys, xs = np.where(rgba[:, :, 3] > 8)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    return rgba[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]


def agent_logo(src, dst, tagline_box):
    im = cv2.imread(src, cv2.IMREAD_UNCHANGED)
    x0, y0 = tagline_box
    im[y0:, x0:, 3] = 0  # tagline sits bottom-right, mascot stays bottom-left
    cv2.imwrite(dst, trim(im))


def key_white(src, dst):
    im = cv2.imread(src).astype(np.float32)
    # distance from white -> alpha; logo has dark outlines so a soft key is clean
    d = 255 - im.min(axis=2)
    alpha = np.clip((d - 18) * 6, 0, 255)
    a = alpha[..., None] / 255.0
    # un-premultiply against white so edges don't keep a white halo
    rgb = np.where(a > 0.02, (im - 255 * (1 - a)) / np.maximum(a, 0.02), im)
    out = np.dstack([np.clip(rgb, 0, 255), alpha]).astype(np.uint8)
    cv2.imwrite(dst, trim(out))


os.makedirs(A, exist_ok=True)

agent_logo(f"{IMG}/8.png", f"{A}/falcon.png", (165, 316))
agent_logo(f"{IMG}/9.png", f"{A}/cheetah.png", (330, 478))
agent_logo(f"{IMG}/7.png", f"{A}/owl.png", (255, 318))
key_white(f"{DL}/WhatsApp Image 2025-05-05 at 20.23.56.jpeg", f"{A}/bluegecko.png")

shutil.copy(f"{IMG}/5.png", f"{A}/dama.png")
shutil.copy(f"{IMG}/4.png", f"{A}/qr.png")
shutil.copy(f"{DL}/nextgenlytics-navbar-logo (1).png", f"{A}/ngl-logo.png")
shutil.copy(os.path.join(REPO, "frontend/src/assets/parts/nvm-1040-hy/main.jpg"), f"{A}/tiltcyl.jpg")
for n, name in [("09", "shot-cheetah"), ("21", "shot-owl"), ("02", "shot-falcon")]:
    shutil.copy(f"{RN}/img{n}.png", f"{A}/{name}.png")

print("ok")
