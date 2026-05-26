from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from types import SimpleNamespace
import os
import csv
import json
import pickle
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.request
import bcrypt
import secrets
import string
import firebase_admin
from firebase_admin import firestore
from google.cloud import storage
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent
ROOT = FRONTEND_DIR.parent

load_dotenv(BASE_DIR / ".env")
load_dotenv()

OUTPUT_ATT = ROOT / "output" / "attendance"
ATT_CSV = OUTPUT_ATT / "attendance.csv"
MASTER_CSV = OUTPUT_ATT / "master_attendance.csv"
VIDEO_UPLOAD_DIR = ROOT / "data" / "classroom_videos"
PHONE_VIDEO_UPLOAD_DIR = ROOT / "data" / "phone_detection_videos"
PHONE_OUTPUT_DIR = ROOT / "output" / "phone_detection"
SLEEP_VIDEO_UPLOAD_DIR = ROOT / "data" / "sleep_detection_videos"
SLEEP_OUTPUT_DIR = ROOT / "output" / "sleep_detection"
TEACHER_PRESENCE_VIDEO_UPLOAD_DIR = ROOT / "data" / "teacher_presence_videos"
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(30 * 1024 * 1024)))
GCS_VIDEO_BUCKET = os.getenv("GCS_VIDEO_BUCKET", "").strip()
METADATA_HEADERS = {"Metadata-Flavor": "Google"}
PHONE_DETECTION_MODEL = os.getenv("PHONE_DETECTION_MODEL", "").strip()
PHONE_DETECTION_FALLBACK_MODEL = os.getenv("PHONE_DETECTION_FALLBACK_MODEL", "models/yolo11s.pt").strip()
PHONE_DETECTION_DEVICE = os.getenv("PHONE_DETECTION_DEVICE", "").strip()
PHONE_DETECTION_MAX_FRAMES = int(os.getenv("PHONE_DETECTION_MAX_FRAMES", "60"))
PHONE_DETECTION_USE_TILES = os.getenv("PHONE_DETECTION_USE_TILES", "1") != "0"
PHONE_DETECTION_TILE_GRID = os.getenv("PHONE_DETECTION_TILE_GRID", "3x3").strip().lower()
PHONE_DETECTION_CONFIDENCE = float(os.getenv("PHONE_DETECTION_CONFIDENCE", "0.10"))
PHONE_DETECTION_FALLBACK_CONFIDENCE = float(os.getenv("PHONE_DETECTION_FALLBACK_CONFIDENCE", "0.35"))
PHONE_DETECTION_STRONG_CONFIDENCE = float(os.getenv("PHONE_DETECTION_STRONG_CONFIDENCE", "0.75"))
PHONE_DETECTION_MIN_SUPPORT_FRAMES = int(os.getenv("PHONE_DETECTION_MIN_SUPPORT_FRAMES", "2"))
PHONE_DETECTION_FALLBACK_USE_TILES = os.getenv("PHONE_DETECTION_FALLBACK_USE_TILES", "0") == "1"
PHONE_DETECTION_SEAT_ROWS = int(os.getenv("PHONE_DETECTION_SEAT_ROWS", "4"))
PHONE_DETECTION_SEAT_COLS = int(os.getenv("PHONE_DETECTION_SEAT_COLS", "6"))
PHONE_DETECTION_IMGSZ = int(os.getenv("PHONE_DETECTION_IMGSZ", "768"))
PHONE_DETECTION_CLASSES = {
    item.strip().lower()
    for item in os.getenv(
        "PHONE_DETECTION_CLASSES",
        "phone,cell phone,mobile phone,smartphone,using phone,cellphone"
    ).split(",")
    if item.strip()
}
PHONE_YOLO_MODELS = {}
SLEEP_DETECTION_MODEL = os.getenv("SLEEP_DETECTION_MODEL", "models/sleep_yolo11.pt").strip()
SLEEP_DETECTION_DEVICE = os.getenv("SLEEP_DETECTION_DEVICE", PHONE_DETECTION_DEVICE).strip()
SLEEP_DETECTION_MAX_FRAMES = int(os.getenv("SLEEP_DETECTION_MAX_FRAMES", "20"))
SLEEP_DETECTION_USE_TILES = os.getenv("SLEEP_DETECTION_USE_TILES", "0") != "0"
SLEEP_DETECTION_TILE_GRID = os.getenv("SLEEP_DETECTION_TILE_GRID", "3x3").strip().lower()
SLEEP_DETECTION_CONFIDENCE = float(os.getenv("SLEEP_DETECTION_CONFIDENCE", "0.35"))
SLEEP_DETECTION_STRONG_CONFIDENCE = float(os.getenv("SLEEP_DETECTION_STRONG_CONFIDENCE", "0.90"))
SLEEP_DETECTION_MIN_SUPPORT_FRAMES = int(os.getenv("SLEEP_DETECTION_MIN_SUPPORT_FRAMES", "5"))
SLEEP_DETECTION_SEAT_ROWS = int(os.getenv("SLEEP_DETECTION_SEAT_ROWS", str(PHONE_DETECTION_SEAT_ROWS)))
SLEEP_DETECTION_SEAT_COLS = int(os.getenv("SLEEP_DETECTION_SEAT_COLS", str(PHONE_DETECTION_SEAT_COLS)))
SLEEP_DETECTION_IMGSZ = int(os.getenv("SLEEP_DETECTION_IMGSZ", "768"))
SLEEP_DETECTION_CLASSES = {
    item.strip().lower()
    for item in os.getenv(
        "SLEEP_DETECTION_CLASSES",
        "sleep,sleeping,sleeper,asleep,nap,napping,head down,heads down,lying down,laying down,prone,supine,to-left,to-right,to left,to right"
    ).split(",")
    if item.strip()
}
SLEEP_YOLO_MODELS = {}
TEACHER_PRESENCE_MODEL = os.getenv("TEACHER_PRESENCE_MODEL", "models/yolo11s.pt").strip()
TEACHER_PRESENCE_DEVICE = os.getenv("TEACHER_PRESENCE_DEVICE", PHONE_DETECTION_DEVICE).strip()
TEACHER_PRESENCE_MAX_FRAMES = int(os.getenv("TEACHER_PRESENCE_MAX_FRAMES", "20"))
TEACHER_PRESENCE_CONFIDENCE = float(os.getenv("TEACHER_PRESENCE_CONFIDENCE", "0.35"))
TEACHER_PRESENCE_MIN_FRAMES = int(os.getenv("TEACHER_PRESENCE_MIN_FRAMES", "3"))
TEACHER_PRESENCE_STRONG_CONFIDENCE = float(os.getenv("TEACHER_PRESENCE_STRONG_CONFIDENCE", "0.85"))
TEACHER_PRESENCE_IMGSZ = int(os.getenv("TEACHER_PRESENCE_IMGSZ", "768"))
TEACHER_PRESENCE_BOARD_ZONE = os.getenv("TEACHER_PRESENCE_BOARD_ZONE", "0.05,0.00,0.95,0.70").strip()
TEACHER_PRESENCE_MIN_PERSON_HEIGHT = float(os.getenv("TEACHER_PRESENCE_MIN_PERSON_HEIGHT", "0.18"))
TEACHER_PRESENCE_MIN_ASPECT = float(os.getenv("TEACHER_PRESENCE_MIN_ASPECT", "1.05"))
TEACHER_YOLO_MODELS = {}

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Firestore default credentials: works in Cloud Shell and Cloud Run
if not firebase_admin._apps:
    firebase_admin.initialize_app()

db = firestore.client()
storage_client = storage.Client()
AI_PROCESS_LOCK = threading.Lock()
print("[OK] Connected to Firestore")


def normalize_username(username):
    return (username or "").strip().lower()


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password, password_hash):
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_password(length=10):
    alphabet = string.ascii_letters + string.digits + "!$@#"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def next_id(collection_name):
    docs = (
        db.collection(collection_name)
        .order_by("id", direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream()
    )

    for doc in docs:
        data = doc.to_dict()
        return int(data.get("id", 0)) + 1

    return 1


def get_first(collection, field, value):
    docs = db.collection(collection).where(field, "==", value).limit(1).stream()
    for doc in docs:
        return doc, doc.to_dict()
    return None, None


def docs_to_list(collection):
    return [doc.to_dict() for doc in db.collection(collection).stream()]


def distance_to_match_percent(distance):
    try:
        distance = float(distance)
    except Exception:
        return None

    if distance >= 1:
        return None

    # ArcFace returns cosine distance: lower is better. This is a direct
    # match score from that distance, not a probability of attendance.
    return round(max(0.0, min(100.0, (1.0 - distance) * 100)), 1)


def normalized_gcs_bucket_name():
    bucket = GCS_VIDEO_BUCKET.strip().strip("\"'")

    if bucket.startswith("gs://"):
        bucket = bucket[5:]

    if bucket.startswith("https://storage.googleapis.com/"):
        bucket = bucket.removeprefix("https://storage.googleapis.com/")

    bucket = bucket.replace("\\", "/").split("/", 1)[0].strip().strip("\"'")

    if not bucket:
        return ""

    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]", bucket):
        raise ValueError(
            "GCS_VIDEO_BUCKET must be only the bucket name, like "
            "attendance-project-uploads. Remove quotes, spaces, gs://, and paths."
        )

    return bucket


def attendance_csv_rows():
    if not ATT_CSV.exists():
        return []

    with ATT_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    results = []

    for row in rows:
        present = str(row.get("present") or "").strip().upper()
        raw_confidence = row.get("avg_confidence") or row.get("confidence") or ""

        accuracy = distance_to_match_percent(raw_confidence)

        item = {
            "date": row.get("date"),
            "name": row.get("name"),
            "username": normalize_username(row.get("name")),
            "present": present,
            "status": "Present" if present == "YES" else "Absent",
            "hits": row.get("hits"),
            "avg_confidence": raw_confidence,
            "match_distance": raw_confidence
        }

        if accuracy is not None:
            item["accuracy"] = accuracy

        results.append(item)

    return results


def clear_uploaded_videos():
    VIDEO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for path in VIDEO_UPLOAD_DIR.iterdir():
        if path.is_file() and path.suffix.lower() in ALLOWED_VIDEO_EXTENSIONS:
            path.unlink()


def clear_phone_detection_videos():
    PHONE_VIDEO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for path in PHONE_VIDEO_UPLOAD_DIR.iterdir():
        if path.is_file() and path.suffix.lower() in ALLOWED_VIDEO_EXTENSIONS:
            path.unlink()


def clear_sleep_detection_videos():
    SLEEP_VIDEO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for path in SLEEP_VIDEO_UPLOAD_DIR.iterdir():
        if path.is_file() and path.suffix.lower() in ALLOWED_VIDEO_EXTENSIONS:
            path.unlink()


def clear_teacher_presence_videos():
    TEACHER_PRESENCE_VIDEO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for path in TEACHER_PRESENCE_VIDEO_UPLOAD_DIR.iterdir():
        if path.is_file() and path.suffix.lower() in ALLOWED_VIDEO_EXTENSIONS:
            path.unlink()


def ai_subprocess_env(extra_env=None):
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("CUDA_VISIBLE_DEVICES", "-1")
    env.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

    for key, value in (extra_env or {}).items():
        env[key] = value

    return env


def ai_timeout_seconds():
    return int(os.getenv("AI_ATTENDANCE_TIMEOUT", "840"))


def ai_runner_time_budget_seconds():
    configured = os.getenv("AI_RUNNER_TIME_BUDGET_SECONDS")

    if configured:
        return int(configured)

    return max(60, ai_timeout_seconds() - 180)


def run_ai_attendance(expected_names=None):
    script_path = ROOT / "scripts" / "run_attendance_arcface.py"

    if not script_path.exists():
        return None, ("AI runner script is missing", 500)

    try:
        extra_env = {
            "AI_RUNNER_TIME_BUDGET_SECONDS": str(ai_runner_time_budget_seconds())
        }

        if expected_names:
            extra_env["AI_EXPECTED_NAMES"] = ",".join(expected_names)

        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=ai_timeout_seconds(),
            env=ai_subprocess_env(extra_env)
        )
    except subprocess.TimeoutExpired:
        return None, ("AI processing timed out before the video finished. Use a shorter video or increase Cloud Run timeout.", 504)

    if result.returncode != 0:
        app.logger.error(
            "AI attendance failed with code %s\nSTDOUT:\n%s\nSTDERR:\n%s",
            result.returncode,
            result.stdout[-4000:],
            result.stderr[-4000:]
        )
        return result, ("AI processing failed", 500)

    return result, None


def ai_failure_details(result):
    if not result:
        return "The AI runner stopped before returning output."

    if result.returncode < 0:
        return (
            f"The AI runner was killed by the platform with signal {-result.returncode}. "
            "This usually means Cloud Run ran out of memory, CPU time, or request timeout. "
            "Use a shorter video, increase Cloud Run memory/timeout, or raise AI_PROCESS_EVERY_N_FRAMES."
        )

    stderr = (result.stderr or "").strip()
    stdout = (result.stdout or "").strip()
    noisy_patterns = (
        "cuda",
        "cudnn",
        "cublas",
        "cufft",
        "tensorrt",
        "cpu_feature_guard",
        "tensorflow/core/platform",
        "stream_executor",
        "this tensorflow binary is optimized"
    )

    lines = []

    for line in (stdout + "\n" + stderr).splitlines():
        clean = line.strip()

        if not clean:
            continue

        lower = clean.lower()

        if any(pattern in lower for pattern in noisy_patterns):
            continue

        lines.append(clean)

    detail = "\n".join(lines[-20:]) or stdout or stderr

    if not detail:
        detail = f"The AI runner exited with code {result.returncode} but did not print an error."

    return detail[-1200:]


def is_phone_label(label):
    clean = str(label or "").strip().lower()

    if not clean:
        return False

    return clean in PHONE_DETECTION_CLASSES or any(item in clean for item in PHONE_DETECTION_CLASSES)


def is_sleep_label(label):
    clean = str(label or "").strip().lower()

    if not clean:
        return False

    return clean in SLEEP_DETECTION_CLASSES or any(item in clean for item in SLEEP_DETECTION_CLASSES)


def resolve_yolo_model_path(value, fallback="yolo11n.pt"):
    configured = Path(value)

    if configured.is_absolute():
        return str(configured) if configured.exists() else fallback

    if "/" in value or "\\" in value:
        configured = ROOT / configured
        return str(configured) if configured.exists() else fallback

    return value


def active_phone_detection_models():
    custom_model = ROOT / "models" / "phone_yolo11.pt"
    fallback_model = ROOT / "models" / "yolo11s.pt"
    candidates = []

    if PHONE_DETECTION_MODEL:
        candidates.append({
            "role": "custom",
            "path": resolve_yolo_model_path(PHONE_DETECTION_MODEL)
        })
    elif custom_model.exists():
        candidates.append({
            "role": "custom",
            "path": str(custom_model)
        })

    if PHONE_DETECTION_FALLBACK_MODEL:
        candidates.append({
            "role": "fallback",
            "path": resolve_yolo_model_path(PHONE_DETECTION_FALLBACK_MODEL)
        })
    elif fallback_model.exists():
        candidates.append({
            "role": "fallback",
            "path": str(fallback_model)
        })

    if not candidates:
        candidates.append({
            "role": "fallback",
            "path": "yolo11n.pt"
        })

    deduped = []
    seen = set()

    for candidate in candidates:
        key = candidate["path"]

        if key in seen:
            continue

        seen.add(key)
        deduped.append(candidate)

    return deduped


def active_sleep_detection_models():
    custom_model = ROOT / "models" / "sleep_yolo11.pt"
    candidates = []

    if SLEEP_DETECTION_MODEL:
        model_path = resolve_yolo_model_path(SLEEP_DETECTION_MODEL, "")

        if model_path:
            candidates.append({
                "role": "sleep",
                "path": model_path
            })
    elif custom_model.exists():
        candidates.append({
            "role": "sleep",
            "path": str(custom_model)
        })

    deduped = []
    seen = set()

    for candidate in candidates:
        key = candidate["path"]

        if key in seen:
            continue

        seen.add(key)
        deduped.append(candidate)

    return deduped


def phone_detection_model(model_path):
    if model_path in PHONE_YOLO_MODELS:
        return PHONE_YOLO_MODELS[model_path]

    try:
        from ultralytics import YOLO
    except ImportError as e:
        raise RuntimeError(
            "Local phone detector is not installed. Run `pip install -r requirements.txt` "
            "so the ultralytics YOLO package is available."
        ) from e

    PHONE_YOLO_MODELS[model_path] = YOLO(model_path)
    return PHONE_YOLO_MODELS[model_path]


def sleep_detection_model(model_path):
    if model_path in SLEEP_YOLO_MODELS:
        return SLEEP_YOLO_MODELS[model_path]

    try:
        from ultralytics import YOLO
    except ImportError as e:
        raise RuntimeError(
            "Local sleep detector is not installed. Run `pip install -r requirements.txt` "
            "so the ultralytics YOLO package is available."
        ) from e

    SLEEP_YOLO_MODELS[model_path] = YOLO(model_path)
    return SLEEP_YOLO_MODELS[model_path]


def teacher_presence_model(model_path):
    if model_path in TEACHER_YOLO_MODELS:
        return TEACHER_YOLO_MODELS[model_path]

    try:
        from ultralytics import YOLO
    except ImportError as e:
        raise RuntimeError(
            "Local teacher presence detector is not installed. Run `pip install -r requirements.txt` "
            "so the ultralytics YOLO package is available."
        ) from e

    TEACHER_YOLO_MODELS[model_path] = YOLO(model_path)
    return TEACHER_YOLO_MODELS[model_path]


def yolo_detection_kwargs(confidence, imgsz=PHONE_DETECTION_IMGSZ, device=PHONE_DETECTION_DEVICE):
    kwargs = {
        "conf": confidence,
        "imgsz": imgsz,
        "verbose": False
    }

    if device:
        kwargs["device"] = device

    return kwargs


def update_class_summary(summary, label, confidence):
    current = summary.setdefault(label, {
        "count": 0,
        "best_confidence": 0.0
    })
    current["count"] += 1
    current["best_confidence"] = max(current["best_confidence"], confidence)


def detect_phone_sample(sample, model_candidate, class_summary, errors):
    model_path = model_candidate["path"]
    model_role = model_candidate["role"]

    if model_role == "fallback" and sample["region"] != "full" and not PHONE_DETECTION_FALLBACK_USE_TILES:
        return []

    try:
        model = phone_detection_model(model_path)
    except Exception as e:
        errors.append(f"{model_role} model could not load: {e}")
        return []

    try:
        confidence = (
            PHONE_DETECTION_FALLBACK_CONFIDENCE
            if model_role == "fallback"
            else PHONE_DETECTION_CONFIDENCE
        )
        result = model(sample["frame"], **yolo_detection_kwargs(confidence))[0]
    except Exception as e:
        errors.append(f"{model_role} model inference failed: {e}")
        return []

    names = getattr(model, "names", {}) or getattr(result, "names", {}) or {}
    detections = []

    boxes = getattr(result, "boxes", None)

    if boxes is None:
        return detections

    for box in boxes:
        cls = int(box.cls[0])
        label = str(names.get(cls, cls)).strip().lower()
        confidence = float(box.conf[0])

        if not is_phone_label(label):
            continue

        update_class_summary(class_summary, label, confidence)

        x1, y1, x2, y2 = [float(value) for value in box.xyxy[0]]
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)

        detections.append({
            "class": label,
            "confidence": confidence,
            "x": sample["offset_x"] + x1 + (width / 2),
            "y": sample["offset_y"] + y1 + (height / 2),
            "width": width,
            "height": height,
            "region": sample["region"],
            "model": model_role
        })

    detections.sort(key=lambda item: item["confidence"], reverse=True)
    return detections


def stable_phone_detections(frame_results):
    all_detections = []

    for frame_item in frame_results:
        for detection in frame_item["detections"]:
            item = dict(detection)
            item["_frame"] = frame_item["frame"]
            item["_nx"] = detection_center_ratio(item.get("x"), frame_item["frame_width"])
            item["_ny"] = detection_center_ratio(item.get("y"), frame_item["frame_height"])

            if item["_nx"] is None or item["_ny"] is None:
                continue

            all_detections.append(item)

    keep = set()

    for index, detection in enumerate(all_detections):
        support_frames = {
            other["_frame"]
            for other in all_detections
            if abs(other["_nx"] - detection["_nx"]) <= 0.10
            and abs(other["_ny"] - detection["_ny"]) <= 0.10
        }

        if (
            detection["confidence"] >= PHONE_DETECTION_STRONG_CONFIDENCE
            or len(support_frames) >= PHONE_DETECTION_MIN_SUPPORT_FRAMES
        ):
            keep.add(index)

    kept_by_frame = {}

    for index in keep:
        detection = {
            key: value
            for key, value in all_detections[index].items()
            if not key.startswith("_")
        }
        kept_by_frame.setdefault(all_detections[index]["_frame"], []).append(detection)

    for frame_item in frame_results:
        frame_item["raw_phone_count"] = len(frame_item["detections"])
        frame_item["detections"] = dedupe_detections(kept_by_frame.get(frame_item["frame"], []))
        frame_item["detections"] = frame_item["detections"][:8]
        frame_item["phone_count"] = len(frame_item["detections"])

    return frame_results


def detection_center_ratio(value, size):
    try:
        value = float(value)
        size = float(size)
    except Exception:
        return None

    if size <= 0:
        return None

    return max(0.0, min(1.0, value / size))


def seat_label_for_detection(detection, frame_item):
    center_x = detection_center_ratio(detection.get("x"), frame_item.get("frame_width"))
    center_y = detection_center_ratio(detection.get("y"), frame_item.get("frame_height"))

    if center_x is None or center_y is None:
        return None

    rows = max(1, PHONE_DETECTION_SEAT_ROWS)
    cols = max(1, PHONE_DETECTION_SEAT_COLS)
    row = max(0, min(rows - 1, int(center_y * rows)))
    col = max(0, min(cols - 1, int(center_x * cols)))

    return f"{chr(65 + row)}{col + 1}"


def phone_seat_summary(frame_results):
    seats = {}

    for frame_item in frame_results:
        for detection in frame_item["detections"]:
            label = seat_label_for_detection(detection, frame_item)

            if not label:
                continue

            item = seats.setdefault(label, {
                "seat": label,
                "frames": set(),
                "count": 0,
                "best_confidence": 0.0
            })
            item["frames"].add(frame_item["frame"])
            item["count"] += 1
            item["best_confidence"] = max(item["best_confidence"], detection["confidence"])

    stable = []

    for item in seats.values():
        frame_count = len(item["frames"])

        if frame_count < PHONE_DETECTION_MIN_SUPPORT_FRAMES and item["best_confidence"] < PHONE_DETECTION_STRONG_CONFIDENCE:
            continue

        stable.append({
            "seat": item["seat"],
            "frames": frame_count,
            "count": item["count"],
            "best_confidence": round(item["best_confidence"], 4)
        })

    stable.sort(key=lambda item: (item["frames"], item["best_confidence"], item["count"]), reverse=True)
    return stable[:1]


def detection_iou(a, b):
    ax1 = float(a["x"]) - (float(a.get("width") or 0) / 2)
    ay1 = float(a["y"]) - (float(a.get("height") or 0) / 2)
    ax2 = float(a["x"]) + (float(a.get("width") or 0) / 2)
    ay2 = float(a["y"]) + (float(a.get("height") or 0) / 2)
    bx1 = float(b["x"]) - (float(b.get("width") or 0) / 2)
    by1 = float(b["y"]) - (float(b.get("height") or 0) / 2)
    bx2 = float(b["x"]) + (float(b.get("width") or 0) / 2)
    by2 = float(b["y"]) + (float(b.get("height") or 0) / 2)

    overlap_x1 = max(ax1, bx1)
    overlap_y1 = max(ay1, by1)
    overlap_x2 = min(ax2, bx2)
    overlap_y2 = min(ay2, by2)
    overlap = max(0.0, overlap_x2 - overlap_x1) * max(0.0, overlap_y2 - overlap_y1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - overlap

    return overlap / union if union > 0 else 0.0


def dedupe_detections(detections, iou_threshold=0.45):
    kept = []

    for detection in sorted(detections, key=lambda item: item["confidence"], reverse=True):
        if any(detection_iou(detection, existing) >= iou_threshold for existing in kept):
            continue

        kept.append(detection)

    return kept


def parse_tile_grid(raw):
    match = re.fullmatch(r"(\d+)x(\d+)", str(raw or "").strip().lower())

    if not match:
        return 2, 2

    cols = max(1, min(4, int(match.group(1))))
    rows = max(1, min(4, int(match.group(2))))
    return cols, rows


def frame_image_samples(frame, use_tiles=PHONE_DETECTION_USE_TILES, tile_grid=PHONE_DETECTION_TILE_GRID):
    height, width = frame.shape[:2]
    yield {
        "region": "full",
        "frame_width": width,
        "frame_height": height,
        "offset_x": 0,
        "offset_y": 0,
        "region_width": width,
        "region_height": height,
        "frame": frame
    }

    if not use_tiles:
        return

    cols, rows = parse_tile_grid(tile_grid)

    for row in range(rows):
        top = int(row * height / rows)
        bottom = int((row + 1) * height / rows)

        for col in range(cols):
            left = int(col * width / cols)
            right = int((col + 1) * width / cols)
            crop = frame[top:bottom, left:right]

            if crop.size == 0:
                continue

            yield {
                "region": f"tile_{row + 1}_{col + 1}",
                "frame_width": width,
                "frame_height": height,
                "offset_x": left,
                "offset_y": top,
                "region_width": right - left,
                "region_height": bottom - top,
                "frame": crop
            }


def sampled_video_frames(video_path, max_frames, use_tiles=PHONE_DETECTION_USE_TILES, tile_grid=PHONE_DETECTION_TILE_GRID):
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        raise ValueError("Could not open uploaded video.")

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_count = max(1, min(max_frames, total_frames or max_frames))

        if total_frames > 0:
            frame_numbers = sorted(set(np.linspace(1, total_frames, sample_count, dtype=int).tolist()))
        else:
            frame_numbers = list(range(1, sample_count + 1))

        for frame_number in frame_numbers:
            if total_frames > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_number - 1))

            ok, frame = cap.read()

            if not ok:
                continue

            for sample in frame_image_samples(frame, use_tiles, tile_grid):
                yield frame_number, sample
    finally:
        cap.release()


def run_phone_detection(video_path):
    frame_results = []
    phone_frames = 0
    total_phones = 0
    best_confidence = 0.0
    class_summary = {}
    detection_errors = []
    model_candidates = active_phone_detection_models()

    frame_map = {}

    for frame_number, sample in sampled_video_frames(video_path, PHONE_DETECTION_MAX_FRAMES):
        detections = []

        for model_candidate in model_candidates:
            detections.extend(
                detect_phone_sample(
                    sample,
                    model_candidate,
                    class_summary,
                    detection_errors
                )
            )

        frame_item = frame_map.setdefault(frame_number, {
            "frame": frame_number,
            "frame_width": sample["frame_width"],
            "frame_height": sample["frame_height"],
            "phone_count": 0,
            "regions_checked": [],
            "detections": []
        })
        frame_item["regions_checked"].append(sample["region"])
        frame_item["detections"].extend(detections)
        frame_item["detections"] = dedupe_detections(frame_item["detections"])
        frame_item["detections"] = frame_item["detections"][:8]
        frame_item["phone_count"] = len(frame_item["detections"])

    frame_results = stable_phone_detections(list(frame_map.values()))
    phone_frames = sum(1 for item in frame_results if item["phone_count"] > 0)
    total_phones = sum(item["phone_count"] for item in frame_results)
    raw_total_phones = sum(item.get("raw_phone_count", item["phone_count"]) for item in frame_results)
    seat_summary = phone_seat_summary(frame_results)
    best_confidence = max(
        (
            detection["confidence"]
            for item in frame_results
            for detection in item["detections"]
        ),
        default=0.0
    )

    result = {
        "success": True,
        "detector": "local_yolo_ensemble",
        "model": model_candidates[0]["path"] if model_candidates else "",
        "models": model_candidates,
        "warnings": sorted(set(detection_errors))[:6],
        "phone_detected": phone_frames > 0,
        "frames_checked": len(frame_results),
        "phone_frames": phone_frames,
        "total_phones": total_phones,
        "raw_total_phones": raw_total_phones,
        "phone_seats": seat_summary,
        "best_confidence": round(best_confidence, 4),
        "tiles_enabled": PHONE_DETECTION_USE_TILES,
        "tile_grid": PHONE_DETECTION_TILE_GRID if PHONE_DETECTION_USE_TILES else "off",
        "classes_seen": [
            {
                "class": label,
                "count": values["count"],
                "best_confidence": round(values["best_confidence"], 4)
            }
            for label, values in sorted(
                class_summary.items(),
                key=lambda pair: pair[1]["best_confidence"],
                reverse=True
            )
        ][:12],
        "frames": frame_results
    }

    PHONE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with (PHONE_OUTPUT_DIR / "phone_detection.json").open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return result


def detect_sleep_sample(sample, model_candidate, class_summary, errors):
    model_path = model_candidate["path"]
    model_role = model_candidate["role"]

    try:
        model = sleep_detection_model(model_path)
    except Exception as e:
        errors.append(f"{model_role} model could not load: {e}")
        return []

    try:
        result = model(
            sample["frame"],
            **yolo_detection_kwargs(
                SLEEP_DETECTION_CONFIDENCE,
                SLEEP_DETECTION_IMGSZ,
                SLEEP_DETECTION_DEVICE
            )
        )[0]
    except Exception as e:
        errors.append(f"{model_role} model inference failed: {e}")
        return []

    names = getattr(model, "names", {}) or getattr(result, "names", {}) or {}
    detections = []
    boxes = getattr(result, "boxes", None)

    if boxes is None:
        return detections

    for box in boxes:
        cls = int(box.cls[0])
        label = str(names.get(cls, cls)).strip().lower()
        confidence = float(box.conf[0])

        if not is_sleep_label(label):
            continue

        update_class_summary(class_summary, label, confidence)

        x1, y1, x2, y2 = [float(value) for value in box.xyxy[0]]
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)

        detections.append({
            "class": label,
            "confidence": confidence,
            "x": sample["offset_x"] + x1 + (width / 2),
            "y": sample["offset_y"] + y1 + (height / 2),
            "width": width,
            "height": height,
            "region": sample["region"],
            "model": model_role
        })

    detections.sort(key=lambda item: item["confidence"], reverse=True)
    return detections


def stable_sleep_detections(frame_results):
    all_detections = []

    for frame_item in frame_results:
        for detection in frame_item["detections"]:
            item = dict(detection)
            item["_frame"] = frame_item["frame"]
            item["_nx"] = detection_center_ratio(item.get("x"), frame_item["frame_width"])
            item["_ny"] = detection_center_ratio(item.get("y"), frame_item["frame_height"])

            if item["_nx"] is None or item["_ny"] is None:
                continue

            all_detections.append(item)

    keep = set()

    for index, detection in enumerate(all_detections):
        support_frames = {
            other["_frame"]
            for other in all_detections
            if abs(other["_nx"] - detection["_nx"]) <= 0.12
            and abs(other["_ny"] - detection["_ny"]) <= 0.12
        }

        if (
            detection["confidence"] >= SLEEP_DETECTION_STRONG_CONFIDENCE
            or len(support_frames) >= SLEEP_DETECTION_MIN_SUPPORT_FRAMES
        ):
            keep.add(index)

    kept_by_frame = {}

    for index in keep:
        detection = {
            key: value
            for key, value in all_detections[index].items()
            if not key.startswith("_")
        }
        kept_by_frame.setdefault(all_detections[index]["_frame"], []).append(detection)

    for frame_item in frame_results:
        frame_item["raw_sleep_count"] = len(frame_item["detections"])
        frame_item["detections"] = dedupe_detections(kept_by_frame.get(frame_item["frame"], []))
        frame_item["detections"] = frame_item["detections"][:12]
        frame_item["sleep_count"] = len(frame_item["detections"])

    return frame_results


def sleep_seat_label_for_detection(detection, frame_item):
    center_x = detection_center_ratio(detection.get("x"), frame_item.get("frame_width"))
    center_y = detection_center_ratio(detection.get("y"), frame_item.get("frame_height"))

    if center_x is None or center_y is None:
        return None

    rows = max(1, SLEEP_DETECTION_SEAT_ROWS)
    cols = max(1, SLEEP_DETECTION_SEAT_COLS)
    row = max(0, min(rows - 1, int(center_y * rows)))
    col = max(0, min(cols - 1, int(center_x * cols)))

    return f"{chr(65 + row)}{col + 1}"


def sleep_seat_summary(frame_results):
    seats = {}

    for frame_item in frame_results:
        for detection in frame_item["detections"]:
            label = sleep_seat_label_for_detection(detection, frame_item)

            if not label:
                continue

            item = seats.setdefault(label, {
                "seat": label,
                "frames": set(),
                "count": 0,
                "best_confidence": 0.0
            })
            item["frames"].add(frame_item["frame"])
            item["count"] += 1
            item["best_confidence"] = max(item["best_confidence"], detection["confidence"])

    stable = []

    for item in seats.values():
        frame_count = len(item["frames"])

        if frame_count < SLEEP_DETECTION_MIN_SUPPORT_FRAMES and item["best_confidence"] < SLEEP_DETECTION_STRONG_CONFIDENCE:
            continue

        stable.append({
            "seat": item["seat"],
            "frames": frame_count,
            "count": item["count"],
            "best_confidence": round(item["best_confidence"], 4)
        })

    stable.sort(key=lambda item: (item["frames"], item["best_confidence"], item["count"]), reverse=True)
    return stable[:8]


def run_sleep_detection(video_path):
    class_summary = {}
    detection_errors = []
    model_candidates = active_sleep_detection_models()

    if not model_candidates:
        raise RuntimeError("Sleep detection model is not ready. Train models/sleep_yolo11.pt first.")

    frame_map = {}

    for frame_number, sample in sampled_video_frames(
        video_path,
        SLEEP_DETECTION_MAX_FRAMES,
        SLEEP_DETECTION_USE_TILES,
        SLEEP_DETECTION_TILE_GRID
    ):
        detections = []

        for model_candidate in model_candidates:
            detections.extend(
                detect_sleep_sample(
                    sample,
                    model_candidate,
                    class_summary,
                    detection_errors
                )
            )

        frame_item = frame_map.setdefault(frame_number, {
            "frame": frame_number,
            "frame_width": sample["frame_width"],
            "frame_height": sample["frame_height"],
            "sleep_count": 0,
            "regions_checked": [],
            "detections": []
        })
        frame_item["regions_checked"].append(sample["region"])
        frame_item["detections"].extend(detections)
        frame_item["detections"] = dedupe_detections(frame_item["detections"])
        frame_item["detections"] = frame_item["detections"][:12]
        frame_item["sleep_count"] = len(frame_item["detections"])

    frame_results = stable_sleep_detections(list(frame_map.values()))
    sleep_frames = sum(1 for item in frame_results if item["sleep_count"] > 0)
    total_sleepers = sum(item["sleep_count"] for item in frame_results)
    raw_total_sleepers = sum(item.get("raw_sleep_count", item["sleep_count"]) for item in frame_results)
    seat_summary = sleep_seat_summary(frame_results)
    best_confidence = max(
        (
            detection["confidence"]
            for item in frame_results
            for detection in item["detections"]
        ),
        default=0.0
    )
    sleep_detected = (
        sleep_frames >= SLEEP_DETECTION_MIN_SUPPORT_FRAMES
        or best_confidence >= SLEEP_DETECTION_STRONG_CONFIDENCE
    )

    result = {
        "success": True,
        "detector": "local_yolo_sleep",
        "model": model_candidates[0]["path"] if model_candidates else "",
        "models": model_candidates,
        "warnings": sorted(set(detection_errors))[:6],
        "sleep_detected": sleep_detected,
        "frames_checked": len(frame_results),
        "sleep_frames": sleep_frames,
        "total_sleepers": total_sleepers,
        "raw_total_sleepers": raw_total_sleepers,
        "sleep_seats": seat_summary,
        "best_confidence": round(best_confidence, 4),
        "tiles_enabled": SLEEP_DETECTION_USE_TILES,
        "tile_grid": SLEEP_DETECTION_TILE_GRID if SLEEP_DETECTION_USE_TILES else "off",
        "classes_seen": [
            {
                "class": label,
                "count": values["count"],
                "best_confidence": round(values["best_confidence"], 4)
            }
            for label, values in sorted(
                class_summary.items(),
                key=lambda pair: pair[1]["best_confidence"],
                reverse=True
            )
        ][:12],
        "frames": frame_results
    }

    SLEEP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with (SLEEP_OUTPUT_DIR / "sleep_detection.json").open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return result


def parse_teacher_board_zone(raw):
    default = (0.05, 0.0, 0.95, 0.70)

    try:
        values = [float(item.strip()) for item in str(raw or "").split(",")]
    except Exception:
        return default

    if len(values) != 4:
        return default

    x1, y1, x2, y2 = [max(0.0, min(1.0, value)) for value in values]

    if x2 <= x1 or y2 <= y1:
        return default

    return x1, y1, x2, y2


def normalized_box_overlap_with_zone(box, zone):
    x1, y1, x2, y2 = box
    zx1, zy1, zx2, zy2 = zone
    overlap_x1 = max(x1, zx1)
    overlap_y1 = max(y1, zy1)
    overlap_x2 = min(x2, zx2)
    overlap_y2 = min(y2, zy2)
    overlap = max(0.0, overlap_x2 - overlap_x1) * max(0.0, overlap_y2 - overlap_y1)
    box_area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return overlap / box_area if box_area > 0 else 0.0


def detect_teacher_presence_sample(sample, model_path, board_zone, errors):
    try:
        model = teacher_presence_model(model_path)
    except Exception as e:
        errors.append(f"teacher model could not load: {e}")
        return [], 0

    try:
        result = model(
            sample["frame"],
            **yolo_detection_kwargs(
                TEACHER_PRESENCE_CONFIDENCE,
                TEACHER_PRESENCE_IMGSZ,
                TEACHER_PRESENCE_DEVICE
            )
        )[0]
    except Exception as e:
        errors.append(f"teacher model inference failed: {e}")
        return [], 0

    names = getattr(model, "names", {}) or getattr(result, "names", {}) or {}
    boxes = getattr(result, "boxes", None)

    if boxes is None:
        return [], 0

    frame_width = max(1, int(sample["frame_width"]))
    frame_height = max(1, int(sample["frame_height"]))
    detections = []
    raw_people = 0

    for box in boxes:
        cls = int(box.cls[0])
        label = str(names.get(cls, cls)).strip().lower()

        if label != "person":
            continue

        raw_people += 1
        confidence = float(box.conf[0])
        x1, y1, x2, y2 = [float(value) for value in box.xyxy[0]]
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        norm_box = (
            max(0.0, min(1.0, x1 / frame_width)),
            max(0.0, min(1.0, y1 / frame_height)),
            max(0.0, min(1.0, x2 / frame_width)),
            max(0.0, min(1.0, y2 / frame_height))
        )
        center_x = (norm_box[0] + norm_box[2]) / 2
        center_y = (norm_box[1] + norm_box[3]) / 2
        zone_overlap = normalized_box_overlap_with_zone(norm_box, board_zone)
        height_ratio = height / frame_height
        aspect_ratio = height / max(1.0, width)
        center_in_zone = (
            board_zone[0] <= center_x <= board_zone[2]
            and board_zone[1] <= center_y <= board_zone[3]
        )

        if not center_in_zone and zone_overlap < 0.35:
            continue

        if height_ratio < TEACHER_PRESENCE_MIN_PERSON_HEIGHT:
            continue

        if aspect_ratio < TEACHER_PRESENCE_MIN_ASPECT:
            continue

        detections.append({
            "class": label,
            "confidence": confidence,
            "x": x1 + (width / 2),
            "y": y1 + (height / 2),
            "width": width,
            "height": height,
            "height_ratio": round(height_ratio, 4),
            "aspect_ratio": round(aspect_ratio, 4),
            "zone_overlap": round(zone_overlap, 4)
        })

    detections.sort(key=lambda item: (item["confidence"], item["height_ratio"]), reverse=True)
    return detections[:3], raw_people


def run_teacher_presence_detection(video_path):
    model_path = resolve_yolo_model_path(TEACHER_PRESENCE_MODEL, "yolo11s.pt")
    board_zone = parse_teacher_board_zone(TEACHER_PRESENCE_BOARD_ZONE)
    frame_results = []
    errors = []

    for frame_number, sample in sampled_video_frames(
        video_path,
        TEACHER_PRESENCE_MAX_FRAMES,
        False,
        "off"
    ):
        detections, raw_people = detect_teacher_presence_sample(
            sample,
            model_path,
            board_zone,
            errors
        )
        frame_results.append({
            "frame": frame_number,
            "frame_width": sample["frame_width"],
            "frame_height": sample["frame_height"],
            "raw_person_count": raw_people,
            "teacher_count": len(detections),
            "detections": detections[:1]
        })

    teacher_frames = sum(1 for item in frame_results if item["teacher_count"] > 0)
    raw_person_total = sum(item["raw_person_count"] for item in frame_results)
    best_confidence = max(
        (
            detection["confidence"]
            for item in frame_results
            for detection in item["detections"]
        ),
        default=0.0
    )
    teacher_present = (
        teacher_frames >= TEACHER_PRESENCE_MIN_FRAMES
        or best_confidence >= TEACHER_PRESENCE_STRONG_CONFIDENCE
    )

    return {
        "success": True,
        "detector": "teacher_board_person_yolo",
        "model": model_path,
        "warnings": sorted(set(errors))[:6],
        "teacher_present": teacher_present,
        "status": "Present" if teacher_present else "Absent",
        "reason": "person_near_board" if teacher_present else "no_teacher_near_board",
        "frames_checked": len(frame_results),
        "teacher_frames": teacher_frames,
        "raw_person_total": raw_person_total,
        "best_confidence": round(best_confidence, 4),
        "board_zone": [round(value, 4) for value in board_zone],
        "frames": frame_results[:20]
    }


def int_or_none(value):
    try:
        return int(value)
    except Exception:
        return None


def teacher_presence_metadata(source):
    teacher_username = normalize_username(source.get("teacher_username"))
    class_id = int_or_none(source.get("class_id"))
    subject_id = int_or_none(source.get("subject_id"))
    class_name = str(source.get("class_name") or "").strip()
    subject_name = str(source.get("subject_name") or "").strip()

    if class_id and not class_name:
        _, class_doc = get_first("classes", "id", class_id)
        class_name = (class_doc or {}).get("name", "")

    if subject_id and not subject_name:
        _, subject_doc = get_first("subjects", "id", subject_id)
        subject_name = (subject_doc or {}).get("name", "")

    if not teacher_username or not class_id:
        return None

    return {
        "teacher_username": teacher_username,
        "class_id": class_id,
        "subject_id": subject_id,
        "class_name": class_name or f"Class {class_id}",
        "subject_name": subject_name or ""
    }


def save_teacher_presence_record(metadata, result, filename):
    if not metadata:
        return None

    now = datetime.now()
    record = {
        "id": next_id("teacher_attendance"),
        "teacher_username": metadata["teacher_username"],
        "class_id": metadata["class_id"],
        "subject_id": metadata.get("subject_id"),
        "class_name": metadata.get("class_name", ""),
        "subject_name": metadata.get("subject_name", ""),
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "status": result["status"],
        "teacher_present": bool(result["teacher_present"]),
        "reason": result["reason"],
        "filename": filename,
        "frames_checked": result["frames_checked"],
        "teacher_frames": result["teacher_frames"],
        "best_confidence": result["best_confidence"]
    }

    db.collection("teacher_attendance").add(record)
    return record


def analyze_and_save_teacher_presence(video_path, filename, metadata):
    if not metadata:
        return None

    result = run_teacher_presence_detection(video_path)
    record = save_teacher_presence_record(metadata, result, filename)
    return {
        **result,
        "record": record
    }


def save_uploaded_video_from_gcs(object_name):
    bucket_name = normalized_gcs_bucket_name()

    if not bucket_name:
        raise RuntimeError("GCS_VIDEO_BUCKET is not configured.")

    clear_uploaded_videos()

    if ATT_CSV.exists():
        ATT_CSV.unlink()

    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    filename = secure_filename(Path(object_name).name)
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise ValueError("Unsupported video type. Upload mp4, mov, avi, or mkv.")

    VIDEO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    video_path = VIDEO_UPLOAD_DIR / filename
    blob.download_to_filename(video_path)
    return filename


def metadata_value(path):
    url = f"http://metadata.google.internal/computeMetadata/v1/{path}"
    req = urllib.request.Request(url, headers=METADATA_HEADERS)

    with urllib.request.urlopen(req, timeout=10) as res:
        return res.read().decode("utf-8")


def cloud_run_signing_identity():
    service_account_email = metadata_value("instance/service-accounts/default/email")
    token_json = metadata_value("instance/service-accounts/default/token")
    access_token = json.loads(token_json)["access_token"]
    return service_account_email, access_token


def signed_url_error_details(error):
    details = str(error)

    if "signBlob" in details or "iam.serviceAccounts" in details:
        return (
            f"{details} Grant the Cloud Run service account "
            "roles/iam.serviceAccountTokenCreator so it can sign upload URLs."
        )

    if "storage.objects" in details or "does not have storage" in details:
        return (
            f"{details} Grant the Cloud Run service account Storage Object Admin "
            "or Storage Object Creator on the upload bucket."
        )

    return details


def expected_names_from_payload(payload):
    names = payload.get("expected_names") or []

    if not isinstance(names, list):
        return []

    clean_names = []

    for name in names:
        clean = str(name or "").strip()

        if clean:
            clean_names.append(clean[:120])

    return clean_names[:80]


def ndjson_event(**payload):
    return json.dumps(payload, ensure_ascii=False) + "\n"


def ensure_admin():
    _, admin = get_first("users", "username", "admin")

    if not admin:
        db.collection("users").add({
            "id": 1,
            "username": "admin",
            "role": "admin",
            "name": "Administrator",
            "password_hash": hash_password("admin123")
        })
        print("[INIT] Created default admin: admin / admin123")


try:
    ensure_admin()
except Exception:
    app.logger.exception("Could not verify default admin during startup")


@app.errorhandler(RequestEntityTooLarge)
def uploaded_file_too_large(error):
    max_mb = round(MAX_UPLOAD_BYTES / 1024 / 1024)
    return jsonify({
        "success": False,
        "error": f"Video is too large. Please upload a video smaller than {max_mb} MB."
    }), 413


@app.errorhandler(Exception)
def json_error(error):
    if isinstance(error, HTTPException):
        return jsonify({
            "success": False,
            "error": error.description,
            "status": error.code
        }), error.code

    app.logger.exception("Unhandled server error")
    return jsonify({
        "success": False,
        "error": "Internal server error",
        "details": str(error)
    }), 500


@app.get("/")
def index():
    return send_from_directory(str(FRONTEND_DIR), "login.html")


@app.get("/login")
def login_page():
    return send_from_directory(str(FRONTEND_DIR), "login.html")


@app.get("/admin")
def admin_page():
    return send_from_directory(str(FRONTEND_DIR), "admin.html")


@app.get("/teacher")
def teacher_page():
    return send_from_directory(str(FRONTEND_DIR), "teacher.html")


@app.get("/student")
def student_page():
    return send_from_directory(str(FRONTEND_DIR), "student.html")


@app.get("/class")
def class_page():
    return send_from_directory(str(FRONTEND_DIR), "class.html")


@app.get("/session")
def session_page():
    return send_from_directory(str(FRONTEND_DIR), "class.html")


@app.route("/<path:filename>")
def serve_static_files(filename):
    return send_from_directory(str(FRONTEND_DIR), filename)


@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "storage": "firestore"
    })


@app.get("/api/ai/status")
def ai_status():
    model_path = ROOT / "models" / "arcface_embeddings.pkl"
    runner_path = ROOT / "scripts" / "run_attendance_arcface.py"

    status = {
        "ok": model_path.exists() and runner_path.exists(),
        "model": str(model_path.relative_to(ROOT)),
        "model_exists": model_path.exists(),
        "runner_exists": runner_path.exists(),
        "known_students": []
    }

    if model_path.exists():
        try:
            with model_path.open("rb") as f:
                known_data = pickle.load(f)
            status["known_students"] = sorted({
                str(item.get("name", "")).strip()
                for item in known_data
                if item.get("name")
            })
            status["embedding_count"] = len(known_data)
        except Exception as e:
            status["ok"] = False
            status["error"] = str(e)

    return jsonify(status), 200 if status["ok"] else 500


@app.post("/api/login")
def api_login():
    payload = request.get_json(force=True, silent=True) or {}

    username = normalize_username(payload.get("username"))
    password = payload.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    _, user = get_first("users", "username", username)

    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    password_hash = user.get("password_hash") or ""

    if not password_hash:
        return jsonify({"error": "Account has no password configured"}), 403

    if not check_password(password, password_hash):
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({
        "id": user.get("id"),
        "username": user.get("username"),
        "role": user.get("role"),
        "name": user.get("name", user.get("username"))
    })


@app.get("/api/users")
def get_users():
    users = docs_to_list("users")
    for u in users:
        u.pop("password_hash", None)
    return jsonify(users)


@app.get("/api/teachers")
def get_teachers():
    teachers = []
    docs = db.collection("users").where("role", "==", "teacher").stream()

    for doc in docs:
        data = doc.to_dict()
        data.pop("password_hash", None)
        teachers.append(data)

    return jsonify(teachers)


@app.get("/api/students")
def get_students():
    students = []
    docs = db.collection("users").where("role", "==", "student").stream()

    for doc in docs:
        data = doc.to_dict()
        data.pop("password_hash", None)
        students.append(data)

    return jsonify(students)


def create_user(role):
    payload = request.get_json(force=True, silent=True) or {}

    username = normalize_username(payload.get("username"))
    name = (payload.get("name") or "").strip() or username

    if not username:
        return jsonify({"error": "Username is required"}), 400

    _, existing = get_first("users", "username", username)

    if existing:
        return jsonify({"error": "Username already exists"}), 400

    plain_password = generate_password()

    user = {
        "id": next_id("users"),
        "username": username,
        "role": role,
        "name": name,
        "password_hash": hash_password(plain_password)
    }

    db.collection("users").add(user)

    return jsonify({
        "id": user["id"],
        "username": username,
        "role": role,
        "name": name,
        "password": plain_password
    }), 201


@app.post("/api/admin/create_teacher")
def admin_create_teacher():
    return create_user("teacher")


@app.post("/api/admin/create_student")
def admin_create_student():
    return create_user("student")


@app.post("/api/admin/create_admin")
def admin_create_admin():
    return create_user("admin")


@app.get("/api/classes")
def get_classes():
    return jsonify(docs_to_list("classes"))


@app.post("/api/classes")
def add_class():
    payload = request.get_json(force=True, silent=True) or {}

    name = (payload.get("name") or "").strip()

    try:
        rows = int(payload.get("rows") or 4)
        cols = int(payload.get("cols") or 6)
    except Exception:
        return jsonify({"error": "Rows and columns must be numbers"}), 400

    if not name:
        return jsonify({"error": "Class name required"}), 400

    if rows <= 0 or cols <= 0:
        return jsonify({"error": "Rows and columns must be positive"}), 400

    new_class = {
        "id": next_id("classes"),
        "name": name,
        "rows": rows,
        "cols": cols,
        "seating": {}
    }

    db.collection("classes").add(new_class)
    return jsonify(new_class), 201


@app.post("/api/classes/seat")
def update_seat():
    payload = request.get_json(force=True, silent=True) or {}

    try:
        class_id = int(payload.get("class_id") or 0)
        row = int(payload.get("row") or 0)
        col = int(payload.get("col") or 0)
    except Exception:
        return jsonify({"error": "Invalid class/seat values"}), 400

    name = (payload.get("name") or "").strip()
    username = normalize_username(payload.get("username"))
    key = f"{row}_{col}"

    class_ref = None
    class_data = None

    docs = db.collection("classes").where("id", "==", class_id).limit(1).stream()

    for doc in docs:
        class_ref = doc.reference
        class_data = doc.to_dict()
        break

    if not class_ref:
        return jsonify({"error": "Class not found"}), 404

    seating = class_data.get("seating", {})

    if name:
        seating[key] = {
            "name": name,
            "username": username or normalize_username(name)
        }
    else:
        seating.pop(key, None)

    class_ref.update({"seating": seating})

    return jsonify({
        "success": True,
        "class_id": class_id,
        "seat": key,
        "name": name,
        "username": username
    })


@app.get("/api/subjects")
def get_subjects():
    return jsonify(docs_to_list("subjects"))


@app.post("/api/subjects")
def add_subject():
    payload = request.get_json(force=True, silent=True) or {}

    name = (payload.get("name") or "").strip()

    if not name:
        return jsonify({"error": "Subject name required"}), 400

    subject = {
        "id": next_id("subjects"),
        "name": name
    }

    db.collection("subjects").add(subject)
    return jsonify(subject), 201


@app.get("/api/assignments")
def get_assignments():
    return jsonify(docs_to_list("assignments"))


@app.post("/api/assignments")
def add_assignment():
    payload = request.get_json(force=True, silent=True) or {}

    teacher_username = normalize_username(payload.get("teacher_username"))

    try:
        class_id = int(payload.get("class_id") or 0)
        subject_id = int(payload.get("subject_id") or 0)
    except Exception:
        return jsonify({"error": "Invalid class or subject"}), 400

    if not teacher_username or not class_id or not subject_id:
        return jsonify({"error": "Teacher, class, and subject are required"}), 400

    docs = (
        db.collection("users")
        .where("username", "==", teacher_username)
        .where("role", "==", "teacher")
        .limit(1)
        .stream()
    )

    teacher = None
    for doc in docs:
        teacher = doc.to_dict()
        break

    if not teacher:
        return jsonify({"error": "Teacher not found"}), 404

    _, class_doc = get_first("classes", "id", class_id)
    if not class_doc:
        return jsonify({"error": "Class not found"}), 404

    _, subject_doc = get_first("subjects", "id", subject_id)
    if not subject_doc:
        return jsonify({"error": "Subject not found"}), 404

    docs = (
        db.collection("assignments")
        .where("teacher_username", "==", teacher_username)
        .where("class_id", "==", class_id)
        .where("subject_id", "==", subject_id)
        .limit(1)
        .stream()
    )

    for doc in docs:
        return jsonify({"error": "Assignment already exists"}), 400

    assignment = {
        "id": next_id("assignments"),
        "teacher_username": teacher_username,
        "class_id": class_id,
        "subject_id": subject_id
    }

    db.collection("assignments").add(assignment)
    return jsonify(assignment), 201


@app.get("/api/exams")
def get_exams():
    query = db.collection("exams")

    if request.args.get("teacher_username"):
        query = query.where("teacher_username", "==", normalize_username(request.args.get("teacher_username")))

    if request.args.get("class_id"):
        query = query.where("class_id", "==", int(request.args.get("class_id")))

    if request.args.get("subject_id"):
        query = query.where("subject_id", "==", int(request.args.get("subject_id")))

    return jsonify([doc.to_dict() for doc in query.stream()])


@app.post("/api/exams")
def create_exam():
    payload = request.get_json(force=True, silent=True) or {}

    teacher_username = normalize_username(payload.get("teacher_username"))

    try:
        class_id = int(payload.get("class_id") or 0)
        subject_id = int(payload.get("subject_id") or 0)
    except Exception:
        return jsonify({"error": "Invalid class or subject"}), 400

    title = (payload.get("title") or "").strip()
    kind = (payload.get("kind") or "exam").strip()
    date = (payload.get("date") or "").strip()

    if not teacher_username or not title or not date:
        return jsonify({"error": "teacher_username, title, and date are required"}), 400

    exam = {
        "id": next_id("exams"),
        "teacher_username": teacher_username,
        "class_id": class_id,
        "subject_id": subject_id,
        "title": title,
        "kind": kind,
        "date": date
    }

    db.collection("exams").add(exam)
    return jsonify(exam), 201


@app.get("/api/homework")
def get_homework():
    query = db.collection("homework")

    if request.args.get("teacher_username"):
        query = query.where("teacher_username", "==", normalize_username(request.args.get("teacher_username")))

    if request.args.get("class_id"):
        query = query.where("class_id", "==", int(request.args.get("class_id")))

    if request.args.get("subject_id"):
        query = query.where("subject_id", "==", int(request.args.get("subject_id")))

    return jsonify([doc.to_dict() for doc in query.stream()])


@app.post("/api/homework")
def create_homework():
    payload = request.get_json(force=True, silent=True) or {}

    teacher_username = normalize_username(payload.get("teacher_username"))

    try:
        class_id = int(payload.get("class_id") or 0)
        subject_id = int(payload.get("subject_id") or 0)
    except Exception:
        return jsonify({"error": "Invalid class or subject"}), 400

    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()
    due_date = (payload.get("due_date") or "").strip()

    if not teacher_username or not title or not due_date:
        return jsonify({"error": "teacher_username, title, and due_date are required"}), 400

    hw = {
        "id": next_id("homework"),
        "teacher_username": teacher_username,
        "class_id": class_id,
        "subject_id": subject_id,
        "title": title,
        "description": description,
        "due_date": due_date
    }

    db.collection("homework").add(hw)
    return jsonify(hw), 201


@app.get("/api/grades")
def get_grades():
    query = db.collection("grades")

    if request.args.get("item_id"):
        query = query.where("item_id", "==", str(request.args.get("item_id")))

    if request.args.get("item_type"):
        query = query.where("item_type", "==", request.args.get("item_type"))

    if request.args.get("class_id"):
        query = query.where("class_id", "==", int(request.args.get("class_id")))

    return jsonify([doc.to_dict() for doc in query.stream()])


@app.post("/api/grades")
def save_grades():
    payload = request.get_json(force=True, silent=True) or {}

    item_id = payload.get("item_id")
    item_type = payload.get("item_type")
    class_id = payload.get("class_id")
    grades_data = payload.get("grades", [])

    if item_id is None or not item_type:
        return jsonify({"error": "item_id and item_type are required"}), 400

    try:
        class_id = int(class_id)
    except Exception:
        return jsonify({"error": "class_id is required"}), 400

    item_id = str(item_id)

    old_docs = (
        db.collection("grades")
        .where("item_id", "==", item_id)
        .where("item_type", "==", item_type)
        .where("class_id", "==", class_id)
        .stream()
    )

    for doc in old_docs:
        doc.reference.delete()

    saved = 0

    for entry in grades_data:
        student_name = (entry.get("student_name") or "").strip()
        score = entry.get("score")
        comment = entry.get("comment") or ""

        if student_name and score != "":
            db.collection("grades").add({
                "item_id": item_id,
                "item_type": item_type,
                "class_id": class_id,
                "student_name": student_name,
                "score": str(score),
                "comment": comment
            })
            saved += 1

    return jsonify({"success": True, "saved": saved})


@app.get("/api/attendance/records")
def get_attendance_records():
    return jsonify(docs_to_list("attendance"))


@app.get("/api/attendance/history")
def get_attendance_history():
    return jsonify(docs_to_list("attendance"))


@app.get("/api/teacher-attendance/records")
def get_teacher_attendance_records():
    return jsonify(docs_to_list("teacher_attendance"))


@app.post("/api/teacher-attendance/upload")
def upload_teacher_presence_video():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No video file uploaded"}), 400

    metadata = teacher_presence_metadata(request.form)

    if not metadata:
        return jsonify({
            "success": False,
            "error": "Teacher and class are required for teacher presence."
        }), 400

    uploaded = request.files["file"]

    if not uploaded or not uploaded.filename:
        return jsonify({"success": False, "error": "No video file selected"}), 400

    filename = secure_filename(uploaded.filename)
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_VIDEO_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": "Unsupported video type. Upload mp4, mov, avi, or mkv."
        }), 400

    clear_teacher_presence_videos()
    video_path = TEACHER_PRESENCE_VIDEO_UPLOAD_DIR / filename
    uploaded.save(video_path)

    try:
        teacher_presence = analyze_and_save_teacher_presence(video_path, filename, metadata)
    except ValueError as e:
        return jsonify({
            "success": False,
            "filename": filename,
            "error": str(e)
        }), 400
    except Exception as e:
        app.logger.exception("Teacher presence detection failed")
        return jsonify({
            "success": False,
            "filename": filename,
            "error": "Teacher presence detection failed.",
            "details": str(e)
        }), 500

    return jsonify({
        "success": True,
        "filename": filename,
        "teacher_presence": teacher_presence
    })


@app.post("/api/attendance/save")
def save_attendance():
    payload = request.get_json(force=True, silent=True) or {}

    try:
        class_id = int(payload.get("class_id") or 0)
        subject_id = int(payload.get("subject_id") or 0)
    except Exception:
        return jsonify({"error": "Invalid class_id or subject_id"}), 400

    teacher_username = normalize_username(payload.get("teacher_username"))
    date = (payload.get("date") or "").strip()
    records = payload.get("records", [])

    if not class_id or not subject_id or not teacher_username or not date:
        return jsonify({"error": "Missing required attendance fields"}), 400

    if not isinstance(records, list) or not records:
        return jsonify({"error": "Attendance records are required"}), 400

    record = {
        "id": next_id("attendance"),
        "class_id": class_id,
        "subject_id": subject_id,
        "teacher_username": teacher_username,
        "date": date,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "records": records
    }

    db.collection("attendance").add(record)
    return jsonify({"success": True, "id": record["id"]}), 201


@app.get("/api/attendance/latest-ai-result")
def latest_ai_result():
    rows = attendance_csv_rows()

    if rows:
        return jsonify(rows)

    return jsonify({"error": "No processed AI attendance result. Upload a video first."}), 404


@app.post("/api/attendance/upload")
def upload_attendance_video():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No video file uploaded"}), 400

    uploaded = request.files["file"]

    if not uploaded or not uploaded.filename:
        return jsonify({"success": False, "error": "No video file selected"}), 400

    filename = secure_filename(uploaded.filename)
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_VIDEO_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": "Unsupported video type. Upload mp4, mov, avi, or mkv."
        }), 400

    clear_uploaded_videos()

    if ATT_CSV.exists():
        ATT_CSV.unlink()

    video_path = VIDEO_UPLOAD_DIR / filename
    uploaded.save(video_path)
    teacher_presence = None
    teacher_metadata = teacher_presence_metadata(request.form)

    try:
        teacher_presence = analyze_and_save_teacher_presence(video_path, filename, teacher_metadata)
    except Exception as e:
        app.logger.exception("Teacher presence detection failed")
        teacher_presence = {
            "success": False,
            "error": "Teacher presence detection failed.",
            "details": str(e)
        }

    result, error = run_ai_attendance()

    if error:
        message, status = error
        return jsonify({
            "success": False,
            "filename": filename,
            "error": message,
            "details": ai_failure_details(result),
            "stdout": result.stdout[-4000:] if result else "",
            "stderr": result.stderr[-4000:] if result else ""
        }), status

    return jsonify({
        "success": True,
        "filename": filename,
        "teacher_presence": teacher_presence,
        "results": attendance_csv_rows(),
        "stdout": result.stdout[-4000:]
    })


@app.post("/api/phone-detection/upload")
def upload_phone_detection_video():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No video file uploaded"}), 400

    uploaded = request.files["file"]

    if not uploaded or not uploaded.filename:
        return jsonify({"success": False, "error": "No video file selected"}), 400

    filename = secure_filename(uploaded.filename)
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_VIDEO_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": "Unsupported video type. Upload mp4, mov, avi, or mkv."
        }), 400

    clear_phone_detection_videos()
    video_path = PHONE_VIDEO_UPLOAD_DIR / filename
    uploaded.save(video_path)

    try:
        result = run_phone_detection(video_path)
    except ValueError as e:
        return jsonify({
            "success": False,
            "filename": filename,
            "error": str(e)
        }), 400
    except Exception as e:
        app.logger.exception("Phone detection failed")
        return jsonify({
            "success": False,
            "filename": filename,
            "error": "Phone detection failed.",
            "details": str(e)
        }), 500

    return jsonify({
        **result,
        "filename": filename
    })


@app.post("/api/sleep-detection/upload")
def upload_sleep_detection_video():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No video file uploaded"}), 400

    uploaded = request.files["file"]

    if not uploaded or not uploaded.filename:
        return jsonify({"success": False, "error": "No video file selected"}), 400

    filename = secure_filename(uploaded.filename)
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_VIDEO_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": "Unsupported video type. Upload mp4, mov, avi, or mkv."
        }), 400

    clear_sleep_detection_videos()
    video_path = SLEEP_VIDEO_UPLOAD_DIR / filename
    uploaded.save(video_path)

    try:
        result = run_sleep_detection(video_path)
    except ValueError as e:
        return jsonify({
            "success": False,
            "filename": filename,
            "error": str(e)
        }), 400
    except Exception as e:
        app.logger.exception("Sleep detection failed")
        return jsonify({
            "success": False,
            "filename": filename,
            "error": "Sleep detection failed.",
            "details": str(e)
        }), 500

    return jsonify({
        **result,
        "filename": filename
    })


@app.post("/api/attendance/gcs-upload-url")
def create_gcs_upload_url():
    try:
        bucket_name = normalized_gcs_bucket_name()
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    if not bucket_name:
        return jsonify({
            "success": False,
            "error": "GCS_VIDEO_BUCKET is not configured for large video uploads."
        }), 500

    payload = request.get_json(force=True, silent=True) or {}
    filename = secure_filename(payload.get("filename") or "")
    content_type = payload.get("content_type") or "application/octet-stream"
    suffix = Path(filename).suffix.lower()

    if not filename or suffix not in ALLOWED_VIDEO_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": "Unsupported video type. Upload mp4, mov, avi, or mkv."
        }), 400

    object_name = f"attendance-uploads/{uuid4().hex}_{filename}"

    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        service_account_email, access_token = cloud_run_signing_identity()
        upload_url = blob.generate_signed_url(
            version="v4",
            expiration=900,
            method="PUT",
            content_type=content_type,
            service_account_email=service_account_email,
            access_token=access_token
        )
    except Exception as e:
        app.logger.exception("Could not create GCS signed upload URL")
        return jsonify({
            "success": False,
            "error": "Could not create signed upload URL.",
            "details": signed_url_error_details(e)
        }), 500

    return jsonify({
        "success": True,
        "upload_url": upload_url,
        "object_name": object_name
    })


@app.post("/api/attendance/process-gcs-video")
def process_gcs_attendance_video():
    payload = request.get_json(force=True, silent=True) or {}
    object_name = payload.get("object_name") or ""
    expected_names = expected_names_from_payload(payload)
    teacher_metadata = teacher_presence_metadata(payload)

    if not object_name.startswith("attendance-uploads/"):
        return jsonify({"success": False, "error": "Invalid uploaded video object."}), 400

    try:
        filename = save_uploaded_video_from_gcs(object_name)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    video_path = VIDEO_UPLOAD_DIR / filename
    teacher_presence = None

    try:
        teacher_presence = analyze_and_save_teacher_presence(video_path, filename, teacher_metadata)
    except Exception as e:
        app.logger.exception("Teacher presence detection failed")
        teacher_presence = {
            "success": False,
            "error": "Teacher presence detection failed.",
            "details": str(e)
        }

    result, error = run_ai_attendance(expected_names)

    if error:
        message, status = error
        return jsonify({
            "success": False,
            "filename": filename,
            "error": message,
            "details": ai_failure_details(result),
            "stdout": result.stdout[-4000:] if result else "",
            "stderr": result.stderr[-4000:] if result else ""
        }), status

    return jsonify({
        "success": True,
        "filename": filename,
        "teacher_presence": teacher_presence,
        "results": attendance_csv_rows(),
        "stdout": result.stdout[-4000:]
    })


@app.post("/api/attendance/process-gcs-video-stream")
def process_gcs_attendance_video_stream():
    payload = request.get_json(force=True, silent=True) or {}
    object_name = payload.get("object_name") or ""
    expected_names = expected_names_from_payload(payload)
    teacher_metadata = teacher_presence_metadata(payload)

    if not object_name.startswith("attendance-uploads/"):
        return jsonify({"success": False, "error": "Invalid uploaded video object."}), 400

    @stream_with_context
    def generate():
        acquired = AI_PROCESS_LOCK.acquire(blocking=False)

        if not acquired:
            yield ndjson_event(
                type="error",
                success=False,
                error="Another AI video is already processing. Please wait for it to finish."
            )
            return

        try:
            yield ndjson_event(type="status", message="Downloading uploaded video...")

            try:
                filename = save_uploaded_video_from_gcs(object_name)
            except Exception as e:
                app.logger.exception("Could not download uploaded GCS video")
                yield ndjson_event(type="error", success=False, error=str(e))
                return

            teacher_presence = None
            video_path = VIDEO_UPLOAD_DIR / filename

            try:
                yield ndjson_event(type="status", message="Checking teacher near the board...")
                teacher_presence = analyze_and_save_teacher_presence(
                    video_path,
                    filename,
                    teacher_metadata
                )
            except Exception as e:
                app.logger.exception("Teacher presence detection failed")
                teacher_presence = {
                    "success": False,
                    "error": "Teacher presence detection failed.",
                    "details": str(e)
                }

            script_path = ROOT / "scripts" / "run_attendance_arcface.py"

            if not script_path.exists():
                yield ndjson_event(type="error", success=False, error="AI runner script is missing")
                return

            yield ndjson_event(type="status", message="Starting AI video processing...")

            timeout_seconds = ai_timeout_seconds()
            extra_env = {
                "AI_RUNNER_TIME_BUDGET_SECONDS": str(ai_runner_time_budget_seconds())
            }

            if expected_names:
                extra_env["AI_EXPECTED_NAMES"] = ",".join(expected_names)

            try:
                process = subprocess.Popen(
                    [sys.executable, str(script_path)],
                    cwd=str(ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=ai_subprocess_env(extra_env)
                )
            except Exception as e:
                app.logger.exception("Could not start AI attendance subprocess")
                yield ndjson_event(type="error", success=False, error=f"Could not start AI processing. {e}")
                return

            output_queue = queue.Queue()
            output_lines = []

            def read_output():
                try:
                    for line in process.stdout:
                        output_queue.put(line)
                finally:
                    output_queue.put(None)

            threading.Thread(target=read_output, daemon=True).start()

            started_at = time.monotonic()
            last_status_at = 0
            reader_done = False
            noisy_patterns = (
                "cuda",
                "cudnn",
                "cublas",
                "cufft",
                "tensorrt",
                "cpu_feature_guard",
                "tensorflow/core/platform",
                "stream_executor"
            )

            while True:
                elapsed = int(time.monotonic() - started_at)

                if elapsed > timeout_seconds:
                    process.kill()
                    process.wait(timeout=5)
                    yield ndjson_event(
                        type="error",
                        success=False,
                        error="AI processing timed out before the video finished. Use a shorter video or increase Cloud Run timeout."
                    )
                    return

                if process.poll() is not None and reader_done and output_queue.empty():
                    break

                try:
                    item = output_queue.get(timeout=2)
                except queue.Empty:
                    if time.monotonic() - last_status_at >= 10:
                        yield ndjson_event(
                            type="status",
                            message=f"Processing video... {elapsed}s",
                            elapsed=elapsed
                        )
                        last_status_at = time.monotonic()
                    continue

                if item is None:
                    reader_done = True
                    continue

                clean = item.strip()

                if not clean:
                    continue

                output_lines.append(clean)
                output_lines = output_lines[-200:]

                lower = clean.lower()

                if any(pattern in lower for pattern in noisy_patterns):
                    continue

                if time.monotonic() - last_status_at >= 2:
                    yield ndjson_event(
                        type="status",
                        message=clean[:240],
                        elapsed=elapsed
                    )
                    last_status_at = time.monotonic()

            stdout = "\n".join(output_lines)

            if process.returncode != 0:
                result = SimpleNamespace(returncode=process.returncode, stdout=stdout, stderr="")
                app.logger.error(
                    "AI attendance failed with code %s\nOUTPUT:\n%s",
                    process.returncode,
                    stdout[-4000:]
                )
                yield ndjson_event(
                    type="error",
                    success=False,
                    filename=filename,
                    error="AI processing failed",
                    details=ai_failure_details(result),
                    stdout=stdout[-4000:],
                    stderr=""
                )
                return

            yield ndjson_event(
                type="complete",
                success=True,
                filename=filename,
                teacher_presence=teacher_presence,
                results=attendance_csv_rows(),
                stdout=stdout[-4000:]
            )
        except Exception as e:
            app.logger.exception("Streaming AI processing failed")
            yield ndjson_event(
                type="error",
                success=False,
                error="AI processing failed.",
                details=str(e)
            )
        finally:
            AI_PROCESS_LOCK.release()

    return Response(
        generate(),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/reports/attendance")
def attendance_report():
    query = db.collection("attendance")

    if request.args.get("class_id"):
        query = query.where("class_id", "==", int(request.args.get("class_id")))

    sessions = [doc.to_dict() for doc in query.stream()]
    stats = {}

    for session in sessions:
        for record in session.get("records", []):
            name = record.get("name")
            status = record.get("status")

            if not name:
                continue

            if name not in stats:
                stats[name] = {"present": 0, "absent": 0, "total": 0}

            stats[name]["total"] += 1

            if status == "Present":
                stats[name]["present"] += 1
            else:
                stats[name]["absent"] += 1

    result = []

    for name, data in stats.items():
        pct = (data["present"] / data["total"] * 100) if data["total"] else 0

        result.append({
            "name": name,
            "present": data["present"],
            "absent": data["absent"],
            "total": data["total"],
            "percentage": round(pct, 1)
        })

    return jsonify(result)


@app.get("/api/reports/performance")
def performance_report():
    query = db.collection("grades")

    if request.args.get("class_id"):
        query = query.where("class_id", "==", int(request.args.get("class_id")))

    grades = [doc.to_dict() for doc in query.stream()]
    stats = {}

    for grade in grades:
        name = grade.get("student_name")
        score = grade.get("score")

        if not name:
            continue

        try:
            score = float(score)
        except Exception:
            continue

        if name not in stats:
            stats[name] = []

        stats[name].append(score)

    return jsonify([
        {
            "name": name,
            "average": round(sum(scores) / len(scores), 1),
            "count": len(scores)
        }
        for name, scores in stats.items()
    ])


@app.get("/api/analytics/attendance_trend")
def attendance_trend():
    sessions = docs_to_list("attendance")
    daily = {}

    for session in sessions:
        date = str(session.get("date") or "").split(" ")[0]
        if not date:
            continue

        if date not in daily:
            daily[date] = {"total": 0, "present": 0}

        for record in session.get("records", []):
            daily[date]["total"] += 1
            if record.get("status") == "Present":
                daily[date]["present"] += 1

    result = []

    for date in sorted(daily.keys()):
        total = daily[date]["total"]
        present = daily[date]["present"]

        result.append({
            "date": date,
            "percentage": round((present / total * 100) if total else 0, 1)
        })

    return jsonify(result)


@app.get("/api/analytics/grade_distribution")
def grade_distribution():
    grades = docs_to_list("grades")

    brackets = {
        "A (90-100)": 0,
        "B (80-89)": 0,
        "C (70-79)": 0,
        "D (60-69)": 0,
        "F (<60)": 0
    }

    for grade in grades:
        try:
            score = float(grade.get("score", 0))
        except Exception:
            continue

        if score >= 90:
            brackets["A (90-100)"] += 1
        elif score >= 80:
            brackets["B (80-89)"] += 1
        elif score >= 70:
            brackets["C (70-79)"] += 1
        elif score >= 60:
            brackets["D (60-69)"] += 1
        else:
            brackets["F (<60)"] += 1

    return jsonify([
        {"label": label, "count": count}
        for label, count in brackets.items()
    ])


@app.get("/api/attendance")
def attendance_csv():
    if not ATT_CSV.exists():
        return jsonify({"ok": False, "error": "attendance.csv not found"}), 404

    return send_from_directory(OUTPUT_ATT, "attendance.csv", as_attachment=False)


@app.get("/api/master")
def master_csv():
    if not MASTER_CSV.exists():
        return jsonify({"ok": False, "error": "master_attendance.csv not found"}), 404

    return send_from_directory(OUTPUT_ATT, "master_attendance.csv", as_attachment=False)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
