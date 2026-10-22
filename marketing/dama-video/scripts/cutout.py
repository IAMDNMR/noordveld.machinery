"""Cut the NVM-1040-HY tilt cylinder out of its studio photo -> assets/tiltcyl-cut.png (for the dark opening)."""
import os

import cv2
import numpy as np

A = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
im = cv2.imread(os.path.join(A, "tiltcyl.jpg"))
h, w = im.shape[:2]
mask = np.zeros((h, w), np.uint8)
bg, fg = np.zeros((1, 65)), np.zeros((1, 65))
cv2.grabCut(im, mask, (int(w * 0.02), int(h * 0.2), int(w * 0.96), int(h * 0.6)), bg, fg, 6, cv2.GC_INIT_WITH_RECT)
m = np.where((mask == 1) | (mask == 3), 255, 0).astype(np.uint8)
m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
# drop the pale floor shadow under the part
hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
ys, xs = np.where(m > 0)
low = np.arange(h)[:, None] >= ys.min() + int((ys.max() - ys.min()) * 0.72)
m[(hsv[:, :, 2] > 150) & (hsv[:, :, 1] < 40) & low] = 0
n, lab, stats, _ = cv2.connectedComponentsWithStats(m)
m = np.where(lab == 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA]), 255, 0).astype(np.uint8)
m = cv2.GaussianBlur(cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)), (0, 0), 1.0)
ys, xs = np.where(m > 10)
out = np.dstack([im, m])[ys.min() - 4:ys.max() + 5, xs.min() - 4:xs.max() + 5]
cv2.imwrite(os.path.join(A, "tiltcyl-cut.png"), out)
print(out.shape)
