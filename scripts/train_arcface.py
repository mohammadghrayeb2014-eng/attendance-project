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
MAX_DETECT_WIDTH = int(os.getenv("TRAIN_MAX_DETECT_WIDTH", "1280"))
TRAIN_AUGMENT = os.getenv("TRAIN_AUGMENT", "1") != "0"
FACE_CROP_TARGET_SIZE = int(os.getenv("TRAIN_FACE_CROP_TARGET_SIZE", "224"))

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


def enhance_face_image(img):
    if img is None or img.size == 0:
        return None

    enhanced = img.copy()
    height, width = enhanced.shape[:2]
    largest_side = max(height, width)

    if FACE_CROP_TARGET_SIZE > 0 and largest_side < FACE_CROP_TARGET_SIZE:
        scale = FACE_CROP_TARGET_SIZE / largest_side
        enhanced = cv2.resize(
            enhanced,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_CUBIC
        )

    try:
        lab = cv2.cvtColor(enhanced, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_channel = clahe.apply(l_channel)
        enhanced = cv2.cvtColor(
            cv2.merge((l_channel, a_channel, b_channel)),
            cv2.COLOR_LAB2BGR
        )
    except Exception:
        pass

    blurred = cv2.GaussianBlur(enhanced, (0, 0), 1.0)
    return cv2.addWeighted(enhanced, 1.5, blurred, -0.5, 0)


def face_variants(aligned):
    variants = [("aligned", aligned)]

    if not TRAIN_AUGMENT:
        return variants

    enhanced = enhance_face_image(aligned)
    flipped = cv2.flip(aligned, 1)

    if enhanced is not None:
        variants.append(("enhanced", enhanced))

    variants.append(("flipped", flipped))

    enhanced_flipped = enhance_face_image(flipped)

    if enhanced_flipped is not None:
        variants.append(("enhanced_flipped", enhanced_flipped))

    return variants

def train():
    print(f"\nTraining ArcFace embeddings...")
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Students Dir: {STUDENTS_DIR}")
    
    if not YUNET_PATH.exists():
        print(f"ERROR: YuNet model not found at {YUNET_PATH}")
        return
        
    known_embeddings = []
    metadata = []
    
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
            
            detector = cv2.FaceDetectorYN.create(str(YUNET_PATH), "", (w, h), score_threshold=0.35)
            _, faces = detector.detect(img_small)
            
            if faces is not None and len(faces) > 0:
                face = sorted(faces, key=lambda item: item[-1], reverse=True)[0]
                face_orig = face.copy()
                face_orig[:14] = face[:14] / scale # Scale landmarks back
                
                aligned = align_face(img_bgr, face_orig)
                if aligned is not None:
                    for variant_name, variant_img in face_variants(aligned):
                        try:
                            res = DeepFace.represent(
                                img_path=variant_img,
                                model_name=MODEL_NAME,
                                detector_backend='skip',
                                enforce_detection=False,
                                align=False
                            )
                            if res and len(res) > 0:
                                student_ems.append({
                                    "embedding": res[0]["embedding"],
                                    "variant": variant_name
                                })
                        except Exception as e:
                            print(f"  DeepFace error ({variant_name}): {str(e)}")
                            continue
            else:
                # Log one failure for debugging
                pass
                        
        if student_ems:
            for idx, item in enumerate(student_ems, start=1):
                known_embeddings.append({
                    "name": name,
                    "embedding": item["embedding"],
                    "sample": idx,
                    "variant": item["variant"]
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
