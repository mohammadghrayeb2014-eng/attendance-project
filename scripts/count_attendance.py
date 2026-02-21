from ultralytics import YOLO
import cv2
import pandas as pd
from pathlib import Path

VIDEO_PATH = "data/classroom_videos/crowd.mp4"  # change if .mov
OUT_CSV = Path("output/attendance/attendance_count.csv")
DEBUG_DIR = Path("output/debug_frames")
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# Speed control (process 1 frame per second)
SAMPLE_EVERY_SECONDS = 1.0
MAX_WIDTH = 960
CONF = 0.35  # detection confidence

model = YOLO("yolov8n.pt")  # detects "person"

def resize_keep_aspect(frame, max_width):
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame, 1.0
    scale = max_width / float(w)
    return cv2.resize(frame, (int(w * scale), int(h * scale))), scale

cap = cv2.VideoCapture(VIDEO_PATH)
if not cap.isOpened():
    raise SystemExit(f"Could not open video: {VIDEO_PATH}")

fps = cap.get(cv2.CAP_PROP_FPS)
frame_step = max(1, int(round(fps * SAMPLE_EVERY_SECONDS))) if fps else 30

rows = []
frame_idx = 0
saved = 0
max_people = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break

    if frame_idx % frame_step != 0:
        frame_idx += 1
        continue

    t = frame_idx / fps if fps else frame_idx * SAMPLE_EVERY_SECONDS
    frame_small, scale = resize_keep_aspect(frame, MAX_WIDTH)

    results = model(frame_small, conf=CONF, verbose=False)[0]

    people = 0
    for box in results.boxes:
        cls = int(box.cls[0])
        name = model.names.get(cls, str(cls))
        if name != "person":
            continue
        people += 1
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cv2.rectangle(frame_small, (x1, y1), (x2, y2), (0, 255, 0), 2)

    max_people = max(max_people, people)
    rows.append({"time_sec": round(t, 2), "people_count": people})

    # save some debug frames
    if saved < 30:
        cv2.putText(frame_small, f"people={people}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        cv2.imwrite(str(DEBUG_DIR / f"count_{frame_idx:06d}.jpg"), frame_small)
        saved += 1

    frame_idx += 1

cap.release()

df = pd.DataFrame(rows)
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT_CSV, index=False)

print("Saved:", OUT_CSV)
print("Max people seen:", max_people)
print("Average people:", round(df['people_count'].mean(), 2))
print("Debug frames:", DEBUG_DIR)
