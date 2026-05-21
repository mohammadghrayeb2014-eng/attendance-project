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

os.environ.setdefault("DEEPFACE_HOME", str(Path("/tmp/deepface")))

from deepface import DeepFace

# ===== PATHS =====
PROJECT_ROOT = Path(__file__).parent.parent
VIDEO_DIR = PROJECT_ROOT / "data/classroom_videos"
PKL_PATH = PROJECT_ROOT / "models/arcface_embeddings.pkl"
OUT_CSV = PROJECT_ROOT / "output/attendance/attendance.csv"
DEBUG_DIR = PROJECT_ROOT / "output/debug_frames"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# ===== CONFIG =====
MODEL_NAME = "ArcFace"
DETECTOR_BACKEND = "retinaface" # More accurate for 4K video
THRESHOLD = 0.75 # Cosine distance threshold (lenient for better coverage)
PROCESS_EVERY_N_FRAMES = 3 # Reverted for accuracy
MIN_HITS = 1 # Reverted to 1 hit for verification
# TARGET_WIDTH = 1280 # Disabled resizing for debugging
# TARGET_HEIGHT = 720

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

def find_matches(frame_face_embedding):
    best_name = "Unknown"
    min_dist = 1.0
    
    for item in known_data:
        # Cosine distance
        dist = DeepFace.verification.dst_utils.findCosineDistance(frame_face_embedding, item["embedding"])
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

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
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
        if not ret: break
        
        frame_idx += 1
        if frame_idx % PROCESS_EVERY_N_FRAMES != 0: continue
        
        # Resize frame for speed (Disabled for debugging)
        # frame = cv2.resize(frame, (TARGET_WIDTH, TARGET_HEIGHT))
        
        if frame_idx % 100 == 0:
            print(f"  Processing: {frame_idx}/{total_frames}")

        try:
            # Detect and represent faces in frame
            faces = DeepFace.represent(
                img_path=frame, 
                model_name=MODEL_NAME, 
                detector_backend=DETECTOR_BACKEND,
                enforce_detection=False,
                align=True
            )
            
            for f in faces:
                if f["face_confidence"] < 0.6: continue
                
                name, dist = find_matches(f["embedding"])
                
                # Convert distance to accuracy (1 - dist)
                acc = max(0, 1 - dist)
                
                if name != "Unknown":
                    hits[name] += 1
                    confidences[name].append(dist)
                    color = (0, 255, 0)
                else:
                    color = (0, 0, 255)
                
                # Draw for debug
                x, y, w, h = f["facial_area"]["x"], f["facial_area"]["y"], f["facial_area"]["w"], f["facial_area"]["h"]
                cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
                cv2.putText(frame, f"{name} ({acc:.2%})", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

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
    
    # Generate CSV
    rows = []
    for name in hits:
        is_present = hits[name] >= MIN_HITS
        avg_dist = np.mean(confidences[name]) if confidences[name] else 80 # default high dist
        
        rows.append({
            "date": run_date,
            "name": name,
            "present": "YES" if is_present else "NO",
            "hits": hits[name],
            "avg_confidence": f"{avg_dist:.1f}" if avg_dist < 1 else "N/A"
        })
    
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nAttendance saved to {OUT_CSV}")

if __name__ == "__main__":
    run()
    
    # ===== UPDATE MASTER ATTENDANCE =====
    import subprocess
    import sys
    subprocess.run([sys.executable, "scripts/update_master_attendance_fixed.py"])
