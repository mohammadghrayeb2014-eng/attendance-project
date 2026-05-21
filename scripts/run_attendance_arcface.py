import cv2
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
import sys
import os

# Fix Windows console encoding
if sys.platform == 'win32':
    os.system('chcp 65001 > nul')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

# ===== PATHS =====
PROJECT_ROOT = Path(__file__).parent.parent
VIDEO_DIR = PROJECT_ROOT / "data/classroom_videos"
PKL_PATH = PROJECT_ROOT / "models/arcface_embeddings.pkl"
OUT_CSV = PROJECT_ROOT / "output/attendance/attendance.csv"
DEBUG_DIR = PROJECT_ROOT / "output/debug_frames"

# ===== DEEPFACE HOME =====
# Use local packaged deepface weights if available (avoids re-download on Cloud Run)
local_deepface = PROJECT_ROOT / "models/deepface"
user_deepface = Path.home() / ".deepface"

if local_deepface.exists():
    os.environ["DEEPFACE_HOME"] = str(local_deepface)
    print(f"Using local deepface weights: {local_deepface}")
elif user_deepface.exists():
    os.environ["DEEPFACE_HOME"] = str(user_deepface.parent)
    print(f"Using user deepface weights: {user_deepface}")
else:
    os.environ.setdefault("DEEPFACE_HOME", "/tmp")
    print("WARNING: No cached weights found, DeepFace will download them.")

from deepface import DeepFace

DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# ===== CONFIG =====
MODEL_NAME = "ArcFace"
DETECTOR_BACKEND = "retinaface"
THRESHOLD = 0.75  # Cosine distance threshold
PROCESS_EVERY_N_FRAMES = 3
MIN_HITS = 1

# ===== LOAD VIDEO =====
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}
VIDEO_CANDIDATES = sorted(
    p for p in VIDEO_DIR.iterdir()
    if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
)
if not VIDEO_CANDIDATES:
    print(f"No video found in {VIDEO_DIR}")
    sys.exit(1)

VIDEO_PATH = str(VIDEO_CANDIDATES[0])
print(f"Running ArcFace on: {VIDEO_PATH}")

# ===== LOAD EMBEDDINGS =====
if not PKL_PATH.exists():
    print("No embeddings file found. Run training first.")
    sys.exit(1)

with open(PKL_PATH, "rb") as f:
    known_data = pickle.load(f)

if not known_data:
    print("Embeddings file is empty. Run training first.")
    sys.exit(1)

print("Known students:", ", ".join(sorted({item["name"] for item in known_data})))


def cosine_distance(a, b):
    """Compute cosine distance between two embedding vectors."""
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 1.0
    return 1.0 - dot / norm


def find_matches(frame_face_embedding):
    best_name = "Unknown"
    min_dist = 1.0

    for item in known_data:
        dist = cosine_distance(frame_face_embedding, item["embedding"])
        if dist < min_dist:
            min_dist = dist
            best_name = item["name"]

    if min_dist > THRESHOLD:
        return "Unknown", min_dist
    return best_name, min_dist


def run():
    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        print(f"Could not open video: {VIDEO_PATH}")
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    hits = {item["name"]: 0 for item in known_data}
    confidences = {item["name"]: [] for item in known_data}

    frame_idx = 0
    saved = 0
    failures = 0
    first_error = None
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1
        if frame_idx % PROCESS_EVERY_N_FRAMES != 0:
            continue

        if frame_idx % 300 == 0:
            print(f"  Processing: {frame_idx}/{total_frames}")

        try:
            faces = DeepFace.represent(
                img_path=frame,
                model_name=MODEL_NAME,
                detector_backend=DETECTOR_BACKEND,
                enforce_detection=False,
                align=True
            )

            for f in faces:
                if f["face_confidence"] < 0.6:
                    continue

                name, dist = find_matches(f["embedding"])
                acc = max(0, 1 - dist)

                if name != "Unknown":
                    hits[name] += 1
                    confidences[name].append(dist)
                    color = (0, 255, 0)
                else:
                    color = (0, 0, 255)

                # Draw for debug
                x, y, w, h = (f["facial_area"]["x"], f["facial_area"]["y"],
                               f["facial_area"]["w"], f["facial_area"]["h"])
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                cv2.putText(frame, f"{name} ({acc:.2%})", (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            if saved < 20 and len(faces) > 0:
                cv2.imwrite(str(DEBUG_DIR / f"arcface_debug_{frame_idx}.jpg"), frame)
                saved += 1

        except Exception as e:
            failures += 1
            if first_error is None:
                first_error = repr(e)
            continue

    cap.release()

    if frame_idx == 0:
        print("Video opened, but no frames were readable.")
        sys.exit(1)

    if first_error:
        print(f"DeepFace warning: {failures} frame(s) failed. First error: {first_error}")

    # ===== Generate CSV =====
    rows = []
    for name in hits:
        is_present = hits[name] >= MIN_HITS
        avg_dist = np.mean(confidences[name]) if confidences[name] else 1.0

        rows.append({
            "date": run_date,
            "name": name,
            "present": "YES" if is_present else "NO",
            "hits": hits[name],
            "avg_confidence": f"{avg_dist:.4f}" if avg_dist < 1 else "N/A"
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nAttendance saved to {OUT_CSV}")
    print(f"Present: {sum(1 for r in rows if r['present'] == 'YES')}/{len(rows)}")


if __name__ == "__main__":
    run()

    # ===== UPDATE MASTER ATTENDANCE =====
    import subprocess
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts/update_master_attendance_fixed.py")],
        cwd=str(PROJECT_ROOT)
    )
    if result.returncode != 0:
        print(f"Warning: master attendance update failed with code {result.returncode}")
