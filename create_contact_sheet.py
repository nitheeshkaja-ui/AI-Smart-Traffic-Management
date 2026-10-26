import cv2
import os
import glob
import math
import numpy as np

folder = os.path.expandvars(
    r"%USERPROFILE%\Downloads\Intersection_Preview\Validation Data Sample\Run_1290"
)

videos = sorted(glob.glob(os.path.join(folder, "VisualCamera*.mp4")))

tiles = []

for video in videos:
    cap = cv2.VideoCapture(video)

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total // 2))
    success, frame = cap.read()
    cap.release()

    if not success:
        print("Could not read:", os.path.basename(video))
        continue

    frame = cv2.resize(frame, (480, 270))
    label = os.path.basename(video)

    cv2.rectangle(frame, (0, 0), (480, 35), (0, 0, 0), -1)
    cv2.putText(frame, label, (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

    tiles.append(frame)

    print(f"{label}: {width}x{height}, {fps:.1f} FPS, {total/fps:.1f} seconds")

if not tiles:
    raise SystemExit("No readable camera videos found.")

columns = 2
rows = math.ceil(len(tiles) / columns)

sheet = np.zeros((rows * 270, columns * 480, 3), dtype=np.uint8)

for i, tile in enumerate(tiles):
    y = (i // columns) * 270
    x = (i % columns) * 480
    sheet[y:y+270, x:x+480] = tile

output = os.path.expandvars(r"%USERPROFILE%\Downloads\camera_contact_sheet.jpg")
cv2.imwrite(output, sheet)

print("\nContact sheet saved:", output)
