import cv2
import pickle
import numpy as np
from deepface import DeepFace
from pathlib import Path
import json
import os

# ===== PATHS =====
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent
STUDENTS_DIR = PROJECT_ROOT / "data" / "students"
MODEL_DIR = PROJECT_ROOT / "models"
MODEL_DIR.mkdir(exist_ok=True)
PKL_PATH = MODEL_DIR / "arcface_embeddings.pkl"
LABELS_PATH = MODEL_DIR / "labels.json"
YUNET_PATH = MODEL_DIR / "face_yunet.onnx"

# ===== CONFIG =====
MODEL_NAME = "ArcFace"
MAX_DETECT_WIDTH = 1024 

# Alignment Matrix
CANONICAL = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)

def align_face(img, face):
    pts = face[4:14].reshape(5, 2).astype(np.float32)
    M, _ = cv2.estimateAffinePartial2D(pts, CANONICAL, method=cv2.LMEDS)
    if M is None: return None
    aligned = cv2.warpAffine(img, M, (112, 112), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return aligned

def train():
    print(f"\nTraining ArcFace embeddings...")
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Students Dir: {STUDENTS_DIR}")
    
    if not YUNET_PATH.exists():
        print(f"ERROR: YuNet model not found at {YUNET_PATH}")
        return
        
    known_embeddings = []
    metadata = []
    
    # We'll use a single detector instance for the entire training if possible
    # but detection size must match image size. 
    
    student_dirs = sorted([d for d in STUDENTS_DIR.iterdir() if d.is_dir()])
    
    for student_dir in student_dirs:
        name = student_dir.name
        images = list(student_dir.glob("*.jpg")) + list(student_dir.glob("*.png")) + list(student_dir.glob("*.jpeg"))
        
        print(f"Evaluating {name} ({len(images)} images)...")
        
        student_ems = []
        for img_path in images:
            img_bgr = cv2.imread(str(img_path))
            if img_bgr is None:
                print(f"  Failed to read: {img_path}")
                continue
            
            orig_h, orig_w = img_bgr.shape[:2]
            scale = MAX_DETECT_WIDTH / float(orig_w) if orig_w > MAX_DETECT_WIDTH else 1.0
            
            img_small = cv2.resize(img_bgr, (0,0), fx=scale, fy=scale)
            h, w = img_small.shape[:2]
            
            detector = cv2.FaceDetectorYN.create(str(YUNET_PATH), "", (w, h), score_threshold=0.5)
            _, faces = detector.detect(img_small)
            
            if faces is not None and len(faces) > 0:
                face = faces[0]
                face_orig = face.copy()
                face_orig[:14] = face[:14] / scale # Scale landmarks back
                
                aligned = align_face(img_bgr, face_orig)
                if aligned is not None:
                    try:
                        res = DeepFace.represent(
                            img_path=aligned,
                            model_name=MODEL_NAME,
                            detector_backend='skip',
                            enforce_detection=False,
                            align=False
                        )
                        if res and len(res) > 0:
                            student_ems.append(res[0]["embedding"])
                    except Exception as e:
                        print(f"  DeepFace error: {str(e)}")
                        continue
            else:
                # Log one failure for debugging
                pass
                        
        if student_ems:
            for idx, embedding in enumerate(student_ems, start=1):
                known_embeddings.append({
                    "name": name,
                    "embedding": embedding,
                    "sample": idx
                })

            metadata.append({
                "name": name,
                "samples": len(student_ems)
            })
            print(f"  SUCCESS: Generated {len(student_ems)} embeddings")
        else:
            print(f"  FAILED: No faces detected for {name}")

    if known_embeddings:
        with open(PKL_PATH, "wb") as f:
            pickle.dump(known_embeddings, f)
        print(f"\nDATABASE SAVED: {PKL_PATH}")

        with open(LABELS_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "model": MODEL_NAME,
                "detector": "yunet",
                "students": metadata,
                "total_embeddings": len(known_embeddings)
            }, f, indent=2)
    else:
        print("\nTRAINING FAILED: Zero embeddings generated.")

if __name__ == "__main__":
    train()
