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
import json
import numpy as np
from pathlib import Path

# ===== PATHS =====
STUDENTS_DIR = Path("data/students")
MODEL_DIR = Path("models")
MODEL_DIR.mkdir(exist_ok=True)

LBPH_PATH = MODEL_DIR / "lbph_model.yml"
LABELS_PATH = MODEL_DIR / "labels.json"
DEBUG_DIR = Path("output/debug_train")
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# ===== YUNET FACE DETECTOR (BETTER THAN HAAR) =====
MODEL_ONNX = "models/face_yunet.onnx"
if not Path(MODEL_ONNX).exists():
    print("⚠️  YuNet model not found, falling back to Haar Cascade")
    USE_YUNET = False
    CASCADE = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
else:
    USE_YUNET = True
    detector = cv2.FaceDetectorYN.create(
        MODEL_ONNX, "", (320, 320),
        score_threshold=0.7,
        nms_threshold=0.3,
        top_k=5000
    )

# ===== CANONICAL LANDMARKS FOR ALIGNMENT =====
CANONICAL = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)

def align_face_yunet(bgr, face):
    """Align face using YuNet landmarks"""
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
    """Advanced preprocessing for better recognition"""
    # Convert to grayscale
    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    
    # Resize to standard size
    gray = cv2.resize(gray, (200, 200))
    
    # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    # Bilateral filter to reduce noise while preserving edges
    gray = cv2.bilateralFilter(gray, 5, 50, 50)
    
    return gray

def load_images(folder):
    return list(folder.glob("*.jpg")) + list(folder.glob("*.png")) + \
           list(folder.glob("*.jpeg")) + list(folder.glob("*.JPG")) + \
           list(folder.glob("*.PNG")) + list(folder.glob("*.JPEG"))

# ===== DATA =====
faces = []
labels = []
label_map = {}
current_id = 0

print("\n🚀 Training Advanced LBPH Model...\n")
print(f"Using detector: {'YuNet (Advanced)' if USE_YUNET else 'Haar Cascade (Basic)'}\n")

for student_dir in sorted(STUDENTS_DIR.iterdir()):
    if not student_dir.is_dir():
        continue

    name = student_dir.name
    images = load_images(student_dir)

    used, skipped = 0, 0
    label_map[current_id] = name

    for img_path in images:
        img = cv2.imread(str(img_path))
        if img is None:
            skipped += 1
            continue

        h, w = img.shape[:2]
        
        if USE_YUNET:
            # Use YuNet detector
            detector.setInputSize((w, h))
            _, faces_detected = detector.detect(img)
            
            if faces_detected is None or len(faces_detected) != 1:
                skipped += 1
                cv2.imwrite(
                    str(DEBUG_DIR / f"{name}_{img_path.stem}_skip.jpg"),
                    img
                )
                continue
            
            # Align face using landmarks
            face_aligned = align_face_yunet(img, faces_detected[0])
            if face_aligned is None:
                skipped += 1
                continue
            
            face_processed = preprocess_face(face_aligned)
        else:
            # Use Haar Cascade
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces_rects = CASCADE.detectMultiScale(
                gray, 
                scaleFactor=1.1, 
                minNeighbors=5, 
                minSize=(30, 30)
            )

            if len(faces_rects) != 1:
                skipped += 1
                cv2.imwrite(
                    str(DEBUG_DIR / f"{name}_{img_path.stem}_skip.jpg"),
                    img
                )
                continue

            x, y, w, h = faces_rects[0]
            face_crop = img[y:y+h, x:x+w]
            face_processed = preprocess_face(face_crop)

        faces.append(face_processed)
        labels.append(current_id)
        used += 1

    print(f"✓ {name}: used {used}, skipped {skipped}")
    current_id += 1

if len(faces) < 5:
    raise SystemExit("\n❌ Not enough face samples. Need at least 5 faces total.")

# ===== TRAIN WITH OPTIMIZED PARAMETERS =====
print(f"\n📊 Training on {len(faces)} face samples from {len(label_map)} students...")

recognizer = cv2.face.LBPHFaceRecognizer_create(
    radius=1,           # Keep at 1 (default)
    neighbors=8,        # Keep at 8 (default) - 16 causes MASSIVE histograms!
    grid_x=8,          # Standard grid
    grid_y=8           # Standard grid
)

recognizer.train(faces, np.array(labels))
recognizer.write(str(LBPH_PATH))

with open(LABELS_PATH, "w", encoding="utf-8") as f:
    json.dump(label_map, f, indent=2, ensure_ascii=False)

print("\n✅ Training Complete!")
print(f"📁 Saved:")
print(f"   - {LBPH_PATH}")
print(f"   - {LABELS_PATH}")
print(f"👥 Students: {len(label_map)}")
print(f"🖼️  Total faces: {len(faces)}")
print(f"📈 Average samples per student: {len(faces)/len(label_map):.1f}")
print(f"\n💡 Tip: For best accuracy, use at least 15-20 photos per student!")
