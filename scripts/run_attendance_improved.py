import sys
import os

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    os.system('chcp 65001 > nul')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

import cv2
import numpy as np
import pandas as pd
import json
from pathlib import Path
from datetime import datetime

# ===== AUTO-DETECT VIDEO =====
VIDEO_DIR = Path("data/classroom_videos")
VIDEO_CANDIDATES = []
for ext in ("*.mp4", "*.mov", "*.avi", "*.mkv", "*.MP4", "*.MOV", "*.AVI"):
    VIDEO_CANDIDATES += sorted(VIDEO_DIR.glob(ext))

if not VIDEO_CANDIDATES:
    raise SystemExit(f"❌ No video found in: {VIDEO_DIR.resolve()}")

VIDEO_PATH = str(VIDEO_CANDIDATES[0])
print(f"🎥 Using video: {VIDEO_PATH}")

# ===== FILES =====
MODEL_ONNX = "models/face_yunet.onnx"
LBPH_MODEL = "models/lbph_model.yml"
LABELS_PATH = "models/labels.json"

OUT_CSV = Path("output/attendance/attendance.csv")
DEBUG_DIR = Path("output/debug_frames")
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# ===== OPTIMIZED SETTINGS =====
PROCESS_EVERY_N_FRAMES = 3  # Process more frames for better accuracy
MAX_WIDTH = 1920
MIN_FACE_SIZE = 40  # Lowered to catch smaller faces

# IMPORTANT: Tune this threshold based on your results
# Lower = stricter (65-75 for high security)
# Medium = balanced (75-90 for normal use) ✓ RECOMMENDED
# Higher = looser (90-110 for low quality videos)
LBPH_THRESHOLD = 80

# Attendance confidence
MIN_HITS_TO_BE_PRESENT = 3  # Need 3+ recognitions to mark present

# ===== LOAD MODEL =====
with open(LABELS_PATH, "r", encoding="utf-8") as f:
    id_to_name = {int(k): v for k, v in json.load(f).items()}

recognizer = cv2.face.LBPHFaceRecognizer_create()
recognizer.read(LBPH_MODEL)

if not Path(MODEL_ONNX).exists():
    raise SystemExit(f"❌ Missing YuNet model: {MODEL_ONNX}")

detector = cv2.FaceDetectorYN.create(
    MODEL_ONNX, "", (320, 320),
    score_threshold=0.6,
    nms_threshold=0.3,
    top_k=5000
)

# ===== CANONICAL LANDMARKS =====
CANONICAL = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)

def resize_keep_aspect(frame, max_width):
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame, 1.0
    s = max_width / float(w)
    return cv2.resize(frame, (int(w * s), int(h * s))), s

def align_face(bgr, face):
    """Align face using landmarks for better recognition"""
    pts = face[4:14].reshape(5, 2).astype(np.float32)
    M, _ = cv2.estimateAffinePartial2D(pts, CANONICAL, method=cv2.LMEDS)
    if M is None:
        return None
    aligned = cv2.warpAffine(
        bgr, M, (112, 112),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT
    )
    return aligned

def preprocess_face(face_bgr):
    """Advanced preprocessing matching training"""
    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (200, 200))
    
    # CLAHE for better contrast
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    # Bilateral filter
    gray = cv2.bilateralFilter(gray, 5, 50, 50)
    
    return gray

# ===== PROCESS VIDEO =====
cap = cv2.VideoCapture(VIDEO_PATH)
if not cap.isOpened():
    raise SystemExit(f"❌ Could not open video: {VIDEO_PATH}")

fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

print(f"📊 Video info: {total_frames} frames @ {fps:.1f} fps")
print(f"⚙️  Settings: threshold={LBPH_THRESHOLD}, min_hits={MIN_HITS_TO_BE_PRESENT}")
print(f"🔄 Processing every {PROCESS_EVERY_N_FRAMES} frames...\n")

hits = {name: 0 for name in id_to_name.values()}
unknown_hits = 0
confidence_scores = {name: [] for name in id_to_name.values()}

frame_idx = 0
saved = 0
run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    frame_idx += 1
    
    if frame_idx % PROCESS_EVERY_N_FRAMES != 0:
        continue

    if frame_idx % 100 == 0:
        print(f"  Processing frame {frame_idx}/{total_frames}...")

    t = frame_idx / fps
    frame_small, _ = resize_keep_aspect(frame, MAX_WIDTH)

    h, w = frame_small.shape[:2]
    detector.setInputSize((w, h))
    _, faces = detector.detect(frame_small)

    if faces is None or len(faces) == 0:
        continue

    for f in faces:
        x, y, fw, fh = f[:4].astype(int)

        if fw < MIN_FACE_SIZE or fh < MIN_FACE_SIZE:
            continue

        # Align and preprocess face
        face_aligned = align_face(frame_small, f)
        if face_aligned is None:
            continue
        
        face_processed = preprocess_face(face_aligned)

        # Predict
        label_id, dist = recognizer.predict(face_processed)

        # Check against threshold
        if dist > LBPH_THRESHOLD:
            unknown_hits += 1
            color = (0, 0, 255)
            text = f"Unknown ({dist:.0f})"
        else:
            name = id_to_name.get(label_id, "Unknown")
            if name == "Unknown":
                unknown_hits += 1
                color = (0, 0, 255)
                text = f"Unknown ({dist:.0f})"
            else:
                hits[name] += 1
                confidence_scores[name].append(dist)
                color = (0, 255, 0)
                text = f"{name} ({dist:.0f})"

        # Draw on frame
        cv2.rectangle(frame_small, (x, y), (x + fw, y + fh), color, 2)
        cv2.putText(frame_small, text, (x, max(0, y - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    # Save debug frames
    if saved < 50:
        cv2.putText(frame_small, f"t={t:.1f}s | thr={LBPH_THRESHOLD}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.imwrite(str(DEBUG_DIR / f"frame_{frame_idx:06d}.jpg"), frame_small)
        saved += 1

cap.release()

# ===== GENERATE ATTENDANCE =====
rows = []
for name, count in hits.items():
    is_present = count >= MIN_HITS_TO_BE_PRESENT
    avg_confidence = np.mean(confidence_scores[name]) if confidence_scores[name] else 0
    
    rows.append({
        "date": run_date,
        "name": name,
        "present": "YES" if is_present else "NO",
        "hits": count,
        "avg_confidence": f"{avg_confidence:.1f}" if avg_confidence > 0 else "N/A"
    })

df = pd.DataFrame(rows).sort_values(["present", "hits"], ascending=[False, False])
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT_CSV, index=False)

# ===== PRINT RESULTS =====
print(f"\n✅ Attendance saved: {OUT_CSV}")
print(f"🖼️  Debug frames: {DEBUG_DIR}")
print(f"❓ Unknown faces detected: {unknown_hits}")
print(f"\n📋 ATTENDANCE SUMMARY:")
print("=" * 60)

for _, row in df.iterrows():
    status = "✓ PRESENT" if row['present'] == "YES" else "✗ ABSENT"
    print(f"{status:12} | {row['name']:15} | Hits: {row['hits']:3} | Conf: {row['avg_confidence']}")

print("=" * 60)

# ===== UPDATE MASTER ATTENDANCE (FIXED) =====
import subprocess
import sys
subprocess.run([sys.executable, "scripts/update_master_attendance_fixed.py"])
