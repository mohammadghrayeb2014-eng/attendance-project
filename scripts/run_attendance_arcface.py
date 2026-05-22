import cv2
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
import sys
import os

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

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
YUNET_PATH = PROJECT_ROOT / "models/face_yunet.onnx"
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
THRESHOLD = float(os.getenv("AI_MATCH_THRESHOLD", "0.55"))
PROCESS_EVERY_N_FRAMES = int(os.getenv("AI_PROCESS_EVERY_N_FRAMES", "6"))
MIN_HITS = int(os.getenv("AI_MIN_HITS", "5"))
MAX_FRAME_WIDTH = int(os.getenv("AI_MAX_FRAME_WIDTH", "960"))
MIN_FACE_SCORE = float(os.getenv("AI_MIN_FACE_SCORE", "0.45"))
MAX_FRAMES = int(os.getenv("AI_MAX_FRAMES", "900"))
MAX_FACES_PER_FRAME = int(os.getenv("AI_MAX_FACES_PER_FRAME", "12"))
EXPECTED_NAMES_RAW = os.getenv("AI_EXPECTED_NAMES", "")

CANONICAL = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)

print(
    "AI config:",
    f"model={MODEL_NAME}",
    "detector=yunet",
    f"threshold={THRESHOLD}",
    f"every_n_frames={PROCESS_EVERY_N_FRAMES}",
    f"min_hits={MIN_HITS}",
    f"max_frame_width={MAX_FRAME_WIDTH}",
    f"min_face_score={MIN_FACE_SCORE}",
    f"max_frames={MAX_FRAMES or 'unlimited'}",
    f"max_faces_per_frame={MAX_FACES_PER_FRAME or 'unlimited'}"
)

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

if not YUNET_PATH.exists():
    print(f"YuNet face detector is missing: {YUNET_PATH}")
    sys.exit(1)

with open(PKL_PATH, "rb") as f:
    known_data = pickle.load(f)

if not known_data:
    print("Embeddings file is empty. Run training first.")
    sys.exit(1)


def normalize_name(name):
    return str(name or "").strip().lower()


known_name_by_normalized = {
    normalize_name(item["name"]): item["name"]
    for item in known_data
    if item.get("name")
}
expected_names = {
    known_name_by_normalized[name]
    for name in (normalize_name(part) for part in EXPECTED_NAMES_RAW.split(","))
    if name in known_name_by_normalized
}
match_data = [
    item for item in known_data
    if not expected_names or item["name"] in expected_names
]

print("Known students:", ", ".join(sorted({item["name"] for item in known_data})))

if expected_names:
    print("Limiting AI matching to seated students:", ", ".join(sorted(expected_names)))


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

    for item in match_data:
        dist = cosine_distance(frame_face_embedding, item["embedding"])
        if dist < min_dist:
            min_dist = dist
            best_name = item["name"]

    if min_dist > THRESHOLD:
        return "Unknown", min_dist
    return best_name, min_dist


def align_face(img, face):
    pts = face[4:14].reshape(5, 2).astype(np.float32)
    matrix, _ = cv2.estimateAffinePartial2D(pts, CANONICAL, method=cv2.LMEDS)

    if matrix is None:
        return None

    return cv2.warpAffine(
        img,
        matrix,
        (112, 112),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT
    )


face_detector = cv2.FaceDetectorYN.create(
    str(YUNET_PATH),
    "",
    (320, 320),
    score_threshold=MIN_FACE_SCORE
)


def detect_faces(frame):
    height, width = frame.shape[:2]
    face_detector.setInputSize((width, height))
    _, faces = face_detector.detect(frame)

    if faces is None:
        return []

    if MAX_FACES_PER_FRAME > 0 and len(faces) > MAX_FACES_PER_FRAME:
        faces = sorted(faces, key=lambda face: face[-1], reverse=True)
        faces = faces[:MAX_FACES_PER_FRAME]

    return faces


def run():
    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        print(f"Could not open video: {VIDEO_PATH}")
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    hits = {item["name"]: 0 for item in match_data}
    confidences = {item["name"]: [] for item in match_data}

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

        if MAX_FRAMES > 0 and frame_idx > MAX_FRAMES:
            break

        if frame_idx % PROCESS_EVERY_N_FRAMES != 0:
            continue

        if MAX_FRAME_WIDTH > 0 and frame.shape[1] > MAX_FRAME_WIDTH:
            scale = MAX_FRAME_WIDTH / frame.shape[1]
            frame = cv2.resize(
                frame,
                (MAX_FRAME_WIDTH, int(frame.shape[0] * scale)),
                interpolation=cv2.INTER_AREA
            )

        if frame_idx % 300 == 0:
            print(f"  Processing: {frame_idx}/{total_frames}")

        try:
            faces = detect_faces(frame)
            frame_detections = []

            for face in faces:
                aligned = align_face(frame, face)

                if aligned is None:
                    continue

                represented = DeepFace.represent(
                    img_path=aligned,
                    model_name=MODEL_NAME,
                    detector_backend="skip",
                    enforce_detection=False,
                    align=False
                )

                if not represented:
                    continue

                name, dist = find_matches(represented[0]["embedding"])
                acc = max(0, 1 - dist)
                frame_detections.append({
                    "name": name,
                    "dist": dist,
                    "acc": acc,
                    "face": face
                })

            frame_best = {}

            for item in frame_detections:
                name = item["name"]

                if name == "Unknown":
                    continue

                if name not in frame_best or item["dist"] < frame_best[name]["dist"]:
                    frame_best[name] = item

            for name, item in frame_best.items():
                hits[name] += 1
                confidences[name].append(item["dist"])

            for item in frame_detections:
                name = item["name"]
                face = item["face"]
                counted = name in frame_best and frame_best[name] is item
                color = (0, 255, 0) if counted else (0, 0, 255)

                # Draw for debug. A hit is counted once per student per frame.
                x, y, w, h = map(int, face[:4])
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                cv2.putText(frame, f"{name} ({item['acc']:.2%})", (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            if saved < 20 and len(faces) > 0:
                cv2.imwrite(str(DEBUG_DIR / f"arcface_debug_{frame_idx}.jpg"), frame)
                saved += 1

            if expected_names and all(hits.get(name, 0) >= MIN_HITS for name in expected_names):
                print(f"Early stop: matched all {len(expected_names)} seated student(s).")
                break

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
