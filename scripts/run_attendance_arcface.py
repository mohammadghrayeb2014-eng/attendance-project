import cv2
import pickle
import numpy as np
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
import sys
import os
import time

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
DEBUG_CSV = PROJECT_ROOT / "output/attendance/match_debug.csv"
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
THRESHOLD = float(os.getenv("AI_MATCH_THRESHOLD", "0.45"))
PARTIAL_FACE_THRESHOLD = float(os.getenv("AI_PARTIAL_FACE_THRESHOLD", "0.45"))
MIN_MATCH_MARGIN = float(os.getenv("AI_MIN_MATCH_MARGIN", "0.001"))
MATCH_TOP_K = int(os.getenv("AI_MATCH_TOP_K", "3"))
PROCESS_EVERY_N_FRAMES = int(os.getenv("AI_PROCESS_EVERY_N_FRAMES", "6"))
MIN_HITS = int(os.getenv("AI_MIN_HITS", "2"))
MAX_FRAME_WIDTH = int(os.getenv("AI_MAX_FRAME_WIDTH", "1280"))
MIN_FACE_SCORE = float(os.getenv("AI_MIN_FACE_SCORE", "0.25"))
MAX_FRAMES = int(os.getenv("AI_MAX_FRAMES", "0"))
MAX_PROCESSED_FRAMES = int(os.getenv("AI_MAX_PROCESSED_FRAMES", "140"))
MAX_FACES_PER_FRAME = int(os.getenv("AI_MAX_FACES_PER_FRAME", "12"))
DETECT_UPSCALE = float(os.getenv("AI_DETECT_UPSCALE", "1.40"))
FACE_NMS_IOU = float(os.getenv("AI_FACE_NMS_IOU", "0.35"))
MIN_FACE_WIDTH_RATIO = float(os.getenv("AI_MIN_FACE_WIDTH_RATIO", "0.010"))
MIN_FACE_HEIGHT_RATIO = float(os.getenv("AI_MIN_FACE_HEIGHT_RATIO", "0.015"))
MAX_FACE_WIDTH_RATIO = float(os.getenv("AI_MAX_FACE_WIDTH_RATIO", "0.28"))
MAX_FACE_HEIGHT_RATIO = float(os.getenv("AI_MAX_FACE_HEIGHT_RATIO", "0.28"))
FACE_CROP_PADDING = float(os.getenv("AI_FACE_CROP_PADDING", "0.45"))
FACE_CROP_TARGET_SIZE = int(os.getenv("AI_FACE_CROP_TARGET_SIZE", "224"))
RUNNER_TIME_BUDGET_SECONDS = int(os.getenv("AI_RUNNER_TIME_BUDGET_SECONDS", "600"))
IGNORE_REGIONS_RAW = os.getenv("AI_IGNORE_REGIONS", "")
EXPECTED_NAMES_RAW = os.getenv("AI_EXPECTED_NAMES", "")
ALLOW_PARTIAL_MATCHES = os.getenv("AI_ALLOW_PARTIAL_MATCHES", "0") == "1"
SEAT_VERIFY_ENABLED = os.getenv("AI_SEAT_VERIFY", "1") != "0"
SEAT_VERIFY_MIN_HITS = int(os.getenv("AI_SEAT_VERIFY_MIN_HITS", "2"))
SEAT_VERIFY_CANDIDATE_MAX_DISTANCE = float(os.getenv("AI_SEAT_VERIFY_CANDIDATE_MAX_DISTANCE", "0.62"))
SEAT_MAP_RAW = os.getenv("AI_SEAT_MAP", "")

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
    f"partial_threshold={PARTIAL_FACE_THRESHOLD}",
    f"min_match_margin={MIN_MATCH_MARGIN}",
    f"match_top_k={MATCH_TOP_K}",
    f"every_n_frames={PROCESS_EVERY_N_FRAMES}",
    f"min_hits={MIN_HITS}",
    f"max_frame_width={MAX_FRAME_WIDTH}",
    f"min_face_score={MIN_FACE_SCORE}",
    f"max_frames={MAX_FRAMES or 'unlimited'}",
    f"max_processed_frames={MAX_PROCESSED_FRAMES or 'unlimited'}",
    f"max_faces_per_frame={MAX_FACES_PER_FRAME or 'unlimited'}",
    f"detect_upscale={DETECT_UPSCALE}",
    f"face_nms_iou={FACE_NMS_IOU}",
    f"min_face_ratio={MIN_FACE_WIDTH_RATIO}x{MIN_FACE_HEIGHT_RATIO}",
    f"max_face_ratio={MAX_FACE_WIDTH_RATIO}x{MAX_FACE_HEIGHT_RATIO}",
    f"face_crop_padding={FACE_CROP_PADDING}",
    f"face_crop_target_size={FACE_CROP_TARGET_SIZE}",
    f"time_budget={RUNNER_TIME_BUDGET_SECONDS or 'unlimited'}",
    f"allow_partial_matches={ALLOW_PARTIAL_MATCHES}",
    f"seat_verify={SEAT_VERIFY_ENABLED}",
    f"seat_verify_min_hits={SEAT_VERIFY_MIN_HITS}",
    f"ignore_regions={IGNORE_REGIONS_RAW or 'none'}"
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


def parse_seat_map(raw):
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except Exception as e:
        print(f"Seat verification disabled: could not parse seat map ({e})")
        return None

    try:
        rows = int(data.get("rows") or 0)
        cols = int(data.get("cols") or 0)
    except Exception:
        return None

    if rows <= 0 or cols <= 0:
        return None

    seats = []

    for item in data.get("seats") or []:
        if not isinstance(item, dict):
            continue

        try:
            row = int(item.get("row"))
            col = int(item.get("col"))
        except Exception:
            continue

        if row < 0 or col < 0 or row >= rows or col >= cols:
            continue

        name = str(item.get("name") or item.get("student_name") or "").strip()
        username = str(item.get("username") or item.get("student_username") or "").strip()

        if not name and not username:
            continue

        seats.append({
            "row": row,
            "col": col,
            "seat": str(item.get("seat") or f"{chr(65 + row)}{col + 1}"),
            "name": name,
            "username": username
        })

    if not seats:
        return None

    return {
        "rows": rows,
        "cols": cols,
        "seats": seats
    }


def parse_ignore_regions(raw):
    regions = []

    for chunk in str(raw or "").split(";"):
        parts = [part.strip() for part in chunk.split(",")]

        if len(parts) != 4:
            continue

        try:
            left, top, right, bottom = [float(part) for part in parts]
        except ValueError:
            continue

        left = max(0.0, min(1.0, left))
        top = max(0.0, min(1.0, top))
        right = max(0.0, min(1.0, right))
        bottom = max(0.0, min(1.0, bottom))

        if right > left and bottom > top:
            regions.append((left, top, right, bottom))

    return regions


IGNORE_REGIONS = parse_ignore_regions(IGNORE_REGIONS_RAW)
SEAT_MAP = parse_seat_map(SEAT_MAP_RAW)


known_name_by_normalized = {
    normalize_name(item["name"]): item["name"]
    for item in known_data
    if item.get("name")
}
seat_by_label = {}
seat_label_by_name = {}

if SEAT_MAP:
    for item in SEAT_MAP["seats"]:
        known_name = None

        for value in (item.get("name"), item.get("username")):
            normalized = normalize_name(value)

            if normalized in known_name_by_normalized:
                known_name = known_name_by_normalized[normalized]
                break

        if not known_name:
            continue

        label = item["seat"]
        seat_by_label[label] = known_name
        seat_label_by_name[known_name] = label

expected_names = {
    known_name_by_normalized[name]
    for name in (normalize_name(part) for part in EXPECTED_NAMES_RAW.split(","))
    if name in known_name_by_normalized
}

if not expected_names and SEAT_MAP:
    expected_names = set(seat_by_label.values())

match_data = [
    item for item in known_data
    if not expected_names or item["name"] in expected_names
]
match_groups = {}

for item in match_data:
    match_groups.setdefault(item["name"], []).append(item)

print("Known students:", ", ".join(sorted({item["name"] for item in known_data})))

if expected_names:
    print("Limiting AI matching to seated students:", ", ".join(sorted(expected_names)))

if IGNORE_REGIONS:
    print("Ignoring camera regions:", IGNORE_REGIONS)

if SEAT_MAP and seat_by_label:
    print(f"Seat verification enabled for {len(seat_by_label)} assigned seat(s).")


def cosine_distance(a, b):
    """Compute cosine distance between two embedding vectors."""
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 1.0
    return 1.0 - dot / norm


def nearest_match(frame_face_embedding):
    scores = []

    for name, items in match_groups.items():
        distances = sorted(
            cosine_distance(frame_face_embedding, item["embedding"])
            for item in items
        )

        if not distances:
            continue

        top_k = distances[:max(1, min(MATCH_TOP_K, len(distances)))]
        scores.append((float(np.mean(top_k)), name))

    if not scores:
        return {
            "name": "Unknown",
            "dist": 1.0,
            "second_dist": 1.0,
            "margin": 0.0
        }

    scores.sort()
    best_dist, best_name = scores[0]
    second_dist = scores[1][0] if len(scores) > 1 else 1.0

    return {
        "name": best_name,
        "dist": best_dist,
        "second_dist": second_dist,
        "margin": second_dist - best_dist
    }


def find_matches(frame_face_embedding, threshold=THRESHOLD):
    match = nearest_match(frame_face_embedding)

    if match["dist"] > threshold or match["margin"] < MIN_MATCH_MARGIN:
        return "Unknown", match["dist"]

    return match["name"], match["dist"]


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


def crop_face(img, face):
    height, width = img.shape[:2]
    x, y, w, h = face[:4]
    pad_x = int(w * FACE_CROP_PADDING)
    pad_y = int(h * FACE_CROP_PADDING)
    left = max(0, int(x) - pad_x)
    top = max(0, int(y) - pad_y)
    right = min(width, int(x + w) + pad_x)
    bottom = min(height, int(y + h) + pad_y)

    if right <= left or bottom <= top:
        return None

    crop = img[top:bottom, left:right]

    if crop.size == 0:
        return None

    return crop


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


def represent_image(img):
    represented = DeepFace.represent(
        img_path=img,
        model_name=MODEL_NAME,
        detector_backend="skip",
        enforce_detection=False,
        align=False
    )

    if not represented:
        return None

    return represented[0]["embedding"]


def match_face(frame, face):
    variants = []
    aligned = align_face(frame, face)

    if aligned is not None:
        variants.append(("aligned", aligned, THRESHOLD))

        enhanced_aligned = enhance_face_image(aligned)
        if enhanced_aligned is not None:
            variants.append(("aligned_enhanced", enhanced_aligned, THRESHOLD))

    padded_crop = crop_face(frame, face)

    if ALLOW_PARTIAL_MATCHES and padded_crop is not None:
        variants.append(("partial", padded_crop, PARTIAL_FACE_THRESHOLD))

        enhanced_crop = enhance_face_image(padded_crop)
        if enhanced_crop is not None:
            variants.append(("partial_enhanced", enhanced_crop, PARTIAL_FACE_THRESHOLD))

    best = {
        "name": "Unknown",
        "dist": 1.0,
        "variant": "none",
        "accepted": False,
        "margin": 0.0,
        "candidate_name": "Unknown",
        "candidate_dist": 1.0
    }

    for variant_name, img, threshold in variants:
        embedding = represent_image(img)

        if embedding is None:
            continue

        nearest = nearest_match(embedding)
        name = nearest["name"]
        dist = nearest["dist"]
        accepted = dist <= threshold and nearest["margin"] >= MIN_MATCH_MARGIN

        if (accepted and not best["accepted"]) or (accepted == best["accepted"] and dist < best["dist"]):
            best = {
                "name": name,
                "dist": dist,
                "variant": variant_name,
                "accepted": accepted,
                "margin": nearest["margin"],
                "candidate_name": name,
                "candidate_dist": dist
            }

    if not best["accepted"]:
        best["candidate_name"] = best["name"]
        best["candidate_dist"] = best["dist"]
        best["name"] = "Unknown"

    return best


face_detector = cv2.FaceDetectorYN.create(
    str(YUNET_PATH),
    "",
    (320, 320),
    score_threshold=MIN_FACE_SCORE
)


def detect_faces_at_scale(frame, scale):
    height, width = frame.shape[:2]

    if scale and scale > 1:
        detect_frame = cv2.resize(
            frame,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_CUBIC
        )
    else:
        scale = 1.0
        detect_frame = frame

    detect_height, detect_width = detect_frame.shape[:2]
    face_detector.setInputSize((detect_width, detect_height))
    _, faces = face_detector.detect(detect_frame)

    if faces is None:
        return []

    faces = [face.copy() for face in faces]

    if scale != 1.0:
        for face in faces:
            face[:14] = face[:14] / scale

    return faces


def face_iou(a, b):
    ax, ay, aw, ah = a[:4]
    bx, by, bw, bh = b[:4]
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)

    if right <= left or bottom <= top:
        return 0.0

    intersection = (right - left) * (bottom - top)
    union = (aw * ah) + (bw * bh) - intersection

    return float(intersection / union) if union else 0.0


def merge_duplicate_faces(faces):
    if not faces:
        return []

    kept = []

    for face in sorted(faces, key=lambda item: item[-1], reverse=True):
        if all(face_iou(face, existing) < FACE_NMS_IOU for existing in kept):
            kept.append(face)

    return kept


def detect_faces(frame):
    height, width = frame.shape[:2]
    faces = detect_faces_at_scale(frame, 1.0)

    if DETECT_UPSCALE and DETECT_UPSCALE > 1:
        faces.extend(detect_faces_at_scale(frame, DETECT_UPSCALE))

    faces = merge_duplicate_faces(faces)

    filtered_faces = []

    for face in faces:
        x, y, w, h = face[:4]
        cx = (x + w / 2) / width
        cy = (y + h / 2) / height

        if MIN_FACE_WIDTH_RATIO > 0 and (w / width) < MIN_FACE_WIDTH_RATIO:
            continue

        if MIN_FACE_HEIGHT_RATIO > 0 and (h / height) < MIN_FACE_HEIGHT_RATIO:
            continue

        if MAX_FACE_WIDTH_RATIO > 0 and (w / width) > MAX_FACE_WIDTH_RATIO:
            continue

        if MAX_FACE_HEIGHT_RATIO > 0 and (h / height) > MAX_FACE_HEIGHT_RATIO:
            continue

        if any(left <= cx <= right and top <= cy <= bottom for left, top, right, bottom in IGNORE_REGIONS):
            continue

        filtered_faces.append(face)

    faces = filtered_faces

    if MAX_FACES_PER_FRAME > 0 and len(faces) > MAX_FACES_PER_FRAME:
        faces = sorted(faces, key=lambda face: face[-1], reverse=True)
        faces = faces[:MAX_FACES_PER_FRAME]

    return faces


def seat_label_for_face(face, frame_shape):
    if not SEAT_MAP:
        return None

    height, width = frame_shape[:2]
    x, y, w, h = face[:4]
    cx = max(0.0, min(0.9999, (x + w / 2) / max(1, width)))
    cy = max(0.0, min(0.9999, (y + h / 2) / max(1, height)))
    row = int(cy * SEAT_MAP["rows"])
    col = int(cx * SEAT_MAP["cols"])
    return f"{chr(65 + row)}{col + 1}"


def sampled_frame_numbers(total_frames):
    if total_frames <= 0:
        return []

    last_frame = min(total_frames, MAX_FRAMES) if MAX_FRAMES > 0 else total_frames

    if last_frame <= 0:
        return []

    if MAX_PROCESSED_FRAMES > 0:
        sample_count = min(MAX_PROCESSED_FRAMES, last_frame)
        return sorted(set(np.linspace(1, last_frame, sample_count, dtype=int).tolist()))

    step = max(1, PROCESS_EVERY_N_FRAMES)
    return list(range(1, last_frame + 1, step))


def run():
    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        print(f"Could not open video: {VIDEO_PATH}")
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_numbers = sampled_frame_numbers(total_frames)

    hits = {item["name"]: 0 for item in match_data}
    seat_hits = {item["name"]: 0 for item in match_data}
    seat_raw_hits = {item["name"]: 0 for item in match_data}
    confidences = {item["name"]: [] for item in match_data}
    candidate_stats = {
        item["name"]: {
            "candidate_frames": 0,
            "best_distance": 1.0,
            "best_margin": 0.0,
            "best_variant": "none"
        }
        for item in match_data
    }

    frame_idx = 0
    processed_frames = 0
    saved = 0
    failures = 0
    first_error = None
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    started_at = time.monotonic()
    stopped_for_budget = False

    print(f"Sampling {len(frame_numbers) or 'streamed'} frame(s) from {total_frames or 'unknown'} total frames")

    while True:
        if RUNNER_TIME_BUDGET_SECONDS > 0 and time.monotonic() - started_at >= RUNNER_TIME_BUDGET_SECONDS:
            stopped_for_budget = True
            print(
                f"Stopping early after {RUNNER_TIME_BUDGET_SECONDS}s time budget. "
                "Writing best attendance result collected so far."
            )
            break

        if frame_numbers:
            if processed_frames >= len(frame_numbers):
                break

            frame_idx = frame_numbers[processed_frames]
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_idx - 1))
            ret, frame = cap.read()
        else:
            ret, frame = cap.read()
            if ret:
                frame_idx += 1

                if MAX_FRAMES > 0 and frame_idx > MAX_FRAMES:
                    break

                if frame_idx % PROCESS_EVERY_N_FRAMES != 0:
                    continue

                if MAX_PROCESSED_FRAMES > 0 and processed_frames >= MAX_PROCESSED_FRAMES:
                    break

        if not ret:
            if frame_numbers:
                processed_frames += 1
                continue
            break

        processed_frames += 1

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
                match = match_face(frame, face)
                name = match["name"]
                dist = match["dist"]
                acc = max(0, 1 - dist)
                frame_detections.append({
                    "name": name,
                    "dist": dist,
                    "acc": acc,
                    "face": face,
                    "variant": match["variant"],
                    "candidate_name": match["candidate_name"],
                    "candidate_dist": match["candidate_dist"],
                    "margin": match["margin"]
                })

                candidate_name = match["candidate_name"]
                if candidate_name in candidate_stats:
                    stats = candidate_stats[candidate_name]
                    stats["candidate_frames"] += 1

                    if match["candidate_dist"] < stats["best_distance"]:
                        stats["best_distance"] = match["candidate_dist"]
                        stats["best_margin"] = match["margin"]
                        stats["best_variant"] = match["variant"]

            if SEAT_VERIFY_ENABLED and SEAT_MAP and seat_by_label:
                frame_seat_hits = set()
                frame_seat_raw_hits = set()

                for item in frame_detections:
                    seat_label = seat_label_for_face(item["face"], frame.shape)
                    assigned_name = seat_by_label.get(seat_label)

                    if not assigned_name or assigned_name not in seat_hits:
                        continue

                    frame_seat_raw_hits.add(assigned_name)

                    matched_name = item["name"]
                    candidate_name = item["candidate_name"]
                    candidate_dist = item["candidate_dist"]

                    if (
                        matched_name == assigned_name
                        or matched_name == "Unknown"
                        or (
                            candidate_name == assigned_name
                            and candidate_dist <= SEAT_VERIFY_CANDIDATE_MAX_DISTANCE
                        )
                    ):
                        frame_seat_hits.add(assigned_name)

                for name in frame_seat_hits:
                    seat_hits[name] += 1

                for name in frame_seat_raw_hits:
                    seat_raw_hits[name] += 1

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
                cv2.putText(frame, f"{name} {item['variant']} ({item['acc']:.2%})", (x, y - 10),
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

    if processed_frames == 0:
        print("Video opened, but no frames were readable.")
        sys.exit(1)

    if first_error:
        print(f"DeepFace warning: {failures} frame(s) failed. First error: {first_error}")

    if stopped_for_budget:
        print(f"Processed {processed_frames}/{len(frame_numbers) or '?'} sampled frame(s) before time budget.")

    # ===== Generate CSV =====
    rows = []
    for name in hits:
        face_present = hits[name] >= MIN_HITS
        seat_present = (
            SEAT_VERIFY_ENABLED
            and not face_present
            and seat_hits.get(name, 0) >= SEAT_VERIFY_MIN_HITS
        )
        is_present = face_present or seat_present
        avg_dist = np.mean(confidences[name]) if confidences[name] else 1.0

        rows.append({
            "date": run_date,
            "name": name,
            "present": "YES" if is_present else "NO",
            "hits": hits[name],
            "seat_hits": seat_hits.get(name, 0),
            "seat_raw_hits": seat_raw_hits.get(name, 0),
            "seat_label": seat_label_by_name.get(name, ""),
            "verification": "face" if face_present else "seat" if seat_present else "absent",
            "avg_confidence": f"{avg_dist:.4f}" if avg_dist < 1 else "N/A"
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)

    debug_rows = []
    for name, stats in candidate_stats.items():
        debug_rows.append({
            "name": name,
            "hits": hits[name],
            "seat_hits": seat_hits.get(name, 0),
            "seat_raw_hits": seat_raw_hits.get(name, 0),
            "seat_label": seat_label_by_name.get(name, ""),
            "candidate_frames": stats["candidate_frames"],
            "best_distance": f"{stats['best_distance']:.4f}" if stats["best_distance"] < 1 else "N/A",
            "best_margin": f"{stats['best_margin']:.4f}",
            "best_variant": stats["best_variant"]
        })

    pd.DataFrame(debug_rows).to_csv(DEBUG_CSV, index=False)
    print(f"\nAttendance saved to {OUT_CSV}")
    print(f"Match debug saved to {DEBUG_CSV}")
    print(f"Present: {sum(1 for r in rows if r['present'] == 'YES')}/{len(rows)}")
    print(f"Seat verified: {sum(1 for r in rows if r.get('verification') == 'seat')}/{len(rows)}")


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
