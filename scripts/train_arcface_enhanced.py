import cv2
import pickle
import numpy as np
from deepface import DeepFace
from pathlib import Path
import json

# Enhanced training with better alignment and quality control
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent
STUDENTS_DIR = PROJECT_ROOT / "data" / "students"
MODEL_DIR = PROJECT_ROOT / "models"
MODEL_DIR.mkdir(exist_ok=True)
PKL_PATH = MODEL_DIR / "arcface_embeddings.pkl"
LABELS_PATH = MODEL_DIR / "labels.json"

# CONFIG for high-quality embeddings
MODEL_NAME = "ArcFace"
DETECTOR_BACKEND = "retinaface"  # Use RetinaFace for better detection quality
MIN_IMAGES_PER_STUDENT = 5
QUALITY_THRESHOLD = 0.90  # Minimum face confidence

print(f"\n{'='*70}")
print(f"  Enhanced ArcFace Training - High Quality Embeddings")
print(f"{'='*70}")
print(f"Detector: {DETECTOR_BACKEND}")
print(f"Model: {MODEL_NAME}")
print(f"Quality threshold: {QUALITY_THRESHOLD}")
print(f"{'='*70}\n")

known_embeddings = []
student_dirs = sorted([d for d in STUDENTS_DIR.iterdir() if d.is_dir()])

for student_dir in student_dirs:
    name = student_dir.name
    images = list(student_dir.glob("*.jpg")) + list(student_dir.glob("*.png")) + list(student_dir.glob("*.jpeg"))
    
    print(f"Processing {name} ({len(images)} images)...")
    
    student_ems = []
    quality_scores = []
    
    for img_path in images:
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            continue
        
        try:
            # Use RetinaFace for better detection
            result = DeepFace.represent(
                img_path=img_bgr,
                model_name=MODEL_NAME,
                detector_backend=DETECTOR_BACKEND,
                enforce_detection=True,  # Ensure face is detected
                align=True
            )
            
            if result and len(result) > 0:
                face_data = result[0]
                confidence = face_data.get("face_confidence", 0)
                
                # Only accept high-quality detections
                if confidence >= QUALITY_THRESHOLD:
                    student_ems.append(face_data["embedding"])
                    quality_scores.append(confidence)
                    
        except Exception as e:
            continue
    
    if len(student_ems) >= MIN_IMAGES_PER_STUDENT:
        # Use median embedding for robustness
        avg_em = np.median(student_ems, axis=0)
        avg_quality = np.mean(quality_scores)
        
        known_embeddings.append({
            "name": name,
            "embedding": avg_em,
            "num_samples": len(student_ems),
            "avg_quality": avg_quality
        })
        print(f"  [OK] Generated {len(student_ems)} embeddings (avg quality: {avg_quality:.2f})")
    else:
        print(f"  [SKIP] Only {len(student_ems)} good quality images (need {MIN_IMAGES_PER_STUDENT})")

if known_embeddings:
    with open(PKL_PATH, "wb") as f:
        pickle.dump(known_embeddings, f)
    print(f"\n[SUCCESS] Saved {len(known_embeddings)} student embeddings to {PKL_PATH}")
    
    # Save metadata
    metadata = {
        "model": MODEL_NAME,
        "detector": DETECTOR_BACKEND,
        "students": [{"name": e["name"], "samples": e["num_samples"], "quality": e["avg_quality"]} 
                     for e in known_embeddings]
    }
    with open(LABELS_PATH, "w") as f:
        json.dump(metadata, f, indent=2)
else:
    print("\n[ERROR] No embeddings generated")
