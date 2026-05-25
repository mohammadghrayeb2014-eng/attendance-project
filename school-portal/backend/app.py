from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from types import SimpleNamespace
import base64
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
import urllib.parse
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
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(30 * 1024 * 1024)))
GCS_VIDEO_BUCKET = os.getenv("GCS_VIDEO_BUCKET", "").strip()
METADATA_HEADERS = {"Metadata-Flavor": "Google"}
ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "").strip()
ROBOFLOW_INFERENCE_URL = os.getenv(
    "ROBOFLOW_INFERENCE_URL",
    "https://serverless.roboflow.com/phone-detection-1gdp9/1"
).strip()
ROBOFLOW_ENDPOINT_MODE = os.getenv("ROBOFLOW_ENDPOINT_MODE", "").strip().lower()
ROBOFLOW_IMAGE_INPUT_NAME = os.getenv("ROBOFLOW_IMAGE_INPUT_NAME", "image").strip() or "image"
ROBOFLOW_WORKFLOW_PAYLOAD = os.getenv("ROBOFLOW_WORKFLOW_PAYLOAD", "workflow").strip().lower() or "workflow"
PHONE_DETECTION_MAX_FRAMES = int(os.getenv("PHONE_DETECTION_MAX_FRAMES", "40"))
PHONE_DETECTION_USE_TILES = os.getenv("PHONE_DETECTION_USE_TILES", "1") != "0"
PHONE_DETECTION_TILE_GRID = os.getenv("PHONE_DETECTION_TILE_GRID", "2x2").strip().lower()
PHONE_DETECTION_CONFIDENCE = float(os.getenv("PHONE_DETECTION_CONFIDENCE", "0.35"))
PHONE_DETECTION_CLASSES = {
    item.strip().lower()
    for item in os.getenv(
        "PHONE_DETECTION_CLASSES",
        "phone,cell phone,mobile phone,smartphone,using phone,cellphone"
    ).split(",")
    if item.strip()
}
PHONE_DETECTION_NEGATIVE_CLASSES = {
    item.strip().lower()
    for item in os.getenv(
        "PHONE_DETECTION_NEGATIVE_CLASSES",
        "no phone,no_phone,no-phone,not phone,without phone"
    ).split(",")
    if item.strip()
}

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


def roboflow_endpoint_mode():
    if ROBOFLOW_ENDPOINT_MODE in {"workflow", "model"}:
        return ROBOFLOW_ENDPOINT_MODE

    parsed = urllib.parse.urlparse(ROBOFLOW_INFERENCE_URL)

    if "/infer/workflows/" in parsed.path:
        return "workflow"

    return "model"


def roboflow_inference_url():
    if not ROBOFLOW_API_KEY:
        raise ValueError("ROBOFLOW_API_KEY is not configured.")

    if not ROBOFLOW_INFERENCE_URL:
        raise ValueError("ROBOFLOW_INFERENCE_URL is not configured.")

    parsed = urllib.parse.urlparse(ROBOFLOW_INFERENCE_URL)
    query = urllib.parse.parse_qs(parsed.query)

    if "api_key" not in query:
        query["api_key"] = [ROBOFLOW_API_KEY]

    if roboflow_endpoint_mode() == "model" and "confidence" not in query:
        query["confidence"] = [str(int(round(PHONE_DETECTION_CONFIDENCE * 100)))]

    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query, doseq=True)))


def find_detection_items(value):
    items = []

    if isinstance(value, dict):
        detection_keys = {
            "class", "class_name", "label", "name", "top", "predicted_class",
            "confidence", "score", "probability", "x", "y", "width", "height", "w", "h"
        }
        looks_like_probability_map = (
            value
            and not (set(value.keys()) & detection_keys)
            and any(isinstance(item, (int, float)) for item in value.values())
            and all(isinstance(item, (int, float, str)) for item in value.values())
        )

        if looks_like_probability_map:
            for label, confidence in value.items():
                try:
                    confidence = float(confidence)
                except Exception:
                    continue

                items.append({
                    "class": str(label),
                    "confidence": confidence,
                    "x": None,
                    "y": None,
                    "width": None,
                    "height": None
                })

        looks_like_nested_probability_map = (
            value
            and not (set(value.keys()) & detection_keys)
            and all(isinstance(item, dict) for item in value.values())
        )

        if looks_like_nested_probability_map:
            for label, prediction in value.items():
                confidence = prediction.get(
                    "confidence",
                    prediction.get("score", prediction.get("probability"))
                )

                if confidence is None:
                    continue

                try:
                    confidence = float(confidence)
                except Exception:
                    continue

                items.append({
                    "class": str(label),
                    "confidence": confidence,
                    "x": prediction.get("x"),
                    "y": prediction.get("y"),
                    "width": prediction.get("width", prediction.get("w")),
                    "height": prediction.get("height", prediction.get("h"))
                })

        label = (
            value.get("class")
            or value.get("class_name")
            or value.get("label")
            or value.get("name")
            or value.get("top")
            or value.get("predicted_class")
        )
        confidence = value.get("confidence", value.get("score", value.get("probability")))

        if confidence is None and isinstance(value.get("predictions"), dict) and label:
            confidence = value["predictions"].get(str(label))

        if isinstance(value.get("predictions"), dict):
            items.extend(find_detection_items(value["predictions"]))

        if confidence is None and isinstance(value.get("confidence"), str):
            confidence = value.get("confidence")

        if label is not None and confidence is not None:
            try:
                confidence = float(confidence)
            except Exception:
                confidence = 0.0

            items.append({
                "class": str(label),
                "confidence": confidence,
                "x": value.get("x"),
                "y": value.get("y"),
                "width": value.get("width", value.get("w")),
                "height": value.get("height", value.get("h"))
            })

        for child in value.values():
            items.extend(find_detection_items(child))

    elif isinstance(value, list):
        for child in value:
            items.extend(find_detection_items(child))

    return items


def roboflow_workflow_payloads(encoded):
    workflow_payload = {
        "api_key": ROBOFLOW_API_KEY,
        "inputs": {
            ROBOFLOW_IMAGE_INPUT_NAME: {
                "type": "base64",
                "value": encoded
            }
        }
    }

    if ROBOFLOW_WORKFLOW_PAYLOAD == "workflow":
        return [workflow_payload]

    if ROBOFLOW_WORKFLOW_PAYLOAD == "simple":
        return [{
            "api_key": ROBOFLOW_API_KEY,
            ROBOFLOW_IMAGE_INPUT_NAME: {
                "type": "base64",
                "value": encoded
            }
        }]

    if ROBOFLOW_WORKFLOW_PAYLOAD == "image":
        return [{
            "api_key": ROBOFLOW_API_KEY,
            ROBOFLOW_IMAGE_INPUT_NAME: encoded
        }]

    return [workflow_payload]


def roboflow_requests(encoded):
    if roboflow_endpoint_mode() == "model":
        return [{
            "data": encoded.encode("ascii"),
            "headers": {"Content-Type": "application/x-www-form-urlencoded"}
        }]

    return [
        {
            "data": json.dumps(payload).encode("utf-8"),
            "headers": {"Content-Type": "application/json"}
        }
        for payload in roboflow_workflow_payloads(encoded)
    ]


def safe_roboflow_error(text):
    clean = str(text or "")

    if ROBOFLOW_API_KEY:
        clean = clean.replace(ROBOFLOW_API_KEY, "<redacted>")

    clean = re.sub(r'("api_key"\s*:\s*")[^"]+', r'\1<redacted>', clean)
    clean = re.sub(r'("value"\s*:\s*")[^"]{80,}', r'\1<omitted>', clean)
    clean = re.sub(r'("image"\s*:\s*")[^"]{80,}', r'\1<omitted>', clean)

    return clean[:700]


def call_roboflow_phone_workflow(jpg_bytes):
    encoded = base64.b64encode(jpg_bytes).decode("ascii")
    last_error = None
    empty_response = None

    for request_payload in roboflow_requests(encoded):
        req = urllib.request.Request(
            roboflow_inference_url(),
            data=request_payload["data"],
            headers=request_payload["headers"],
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=45) as res:
                text = res.read().decode("utf-8", errors="replace")

            response = json.loads(text) if text else {}

            if find_detection_items(response):
                return response

            if empty_response is None:
                empty_response = response
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            last_error = f"Roboflow HTTP {e.code}: {safe_roboflow_error(body)}"
        except Exception as e:
            last_error = safe_roboflow_error(str(e))

        break

    if empty_response is not None:
        return empty_response

    raise RuntimeError(last_error or "Roboflow request failed.")


def is_phone_label(label):
    clean = str(label or "").strip().lower()

    if not clean:
        return False

    if clean in PHONE_DETECTION_NEGATIVE_CLASSES:
        return False

    if any(negative in clean for negative in PHONE_DETECTION_NEGATIVE_CLASSES):
        return False

    return clean in PHONE_DETECTION_CLASSES or any(item in clean for item in PHONE_DETECTION_CLASSES)


def phone_detections_from_response(response):
    detections = []

    for item in find_detection_items(response):
        label = item["class"].strip().lower()

        if not is_phone_label(label):
            continue

        if item["confidence"] < PHONE_DETECTION_CONFIDENCE:
            continue

        detections.append(item)

    detections.sort(key=lambda item: item["confidence"], reverse=True)
    return detections


def response_class_summary(response):
    summary = {}

    for item in find_detection_items(response):
        label = item["class"].strip().lower()

        if not label:
            continue

        current = summary.setdefault(label, {
            "count": 0,
            "best_confidence": 0.0
        })
        current["count"] += 1
        current["best_confidence"] = max(current["best_confidence"], item["confidence"])

    return [
        {
            "class": label,
            "count": values["count"],
            "best_confidence": round(values["best_confidence"], 4)
        }
        for label, values in sorted(
            summary.items(),
            key=lambda pair: pair[1]["best_confidence"],
            reverse=True
        )
    ]


def response_shape(value, depth=0):
    if depth > 2:
        return type(value).__name__

    if isinstance(value, dict):
        return {
            key: response_shape(child, depth + 1)
            for key, child in list(value.items())[:12]
        }

    if isinstance(value, list):
        return [response_shape(value[0], depth + 1)] if value else []

    return type(value).__name__


def normalize_detection_coordinates(detections, sample):
    normalized = []

    for detection in detections:
        item = dict(detection)
        x = item.get("x")
        y = item.get("y")

        try:
            if x is not None:
                x = float(x)

                if x <= 1:
                    x = x * sample["region_width"]

                item["x"] = sample["offset_x"] + x

            if y is not None:
                y = float(y)

                if y <= 1:
                    y = y * sample["region_height"]

                item["y"] = sample["offset_y"] + y
        except Exception:
            pass

        normalized.append(item)

    return normalized


def scrub_roboflow_debug(value, depth=0):
    if depth > 5:
        return type(value).__name__

    if isinstance(value, dict):
        scrubbed = {}

        for key, child in list(value.items())[:20]:
            key_text = str(key)

            if key_text.lower() in {"image", "output_image", "value", "base64"}:
                scrubbed[key_text] = "<omitted>"
                continue

            scrubbed[key_text] = scrub_roboflow_debug(child, depth + 1)

        return scrubbed

    if isinstance(value, list):
        return [scrub_roboflow_debug(item, depth + 1) for item in value[:3]]

    if isinstance(value, str):
        return value[:160]

    return value


def encode_frame_jpg(frame):
    import cv2

    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])

    return encoded.tobytes() if ok else None


def parse_tile_grid(raw):
    match = re.fullmatch(r"(\d+)x(\d+)", str(raw or "").strip().lower())

    if not match:
        return 2, 2

    cols = max(1, min(4, int(match.group(1))))
    rows = max(1, min(4, int(match.group(2))))
    return cols, rows


def frame_image_samples(frame):
    height, width = frame.shape[:2]
    full_jpg = encode_frame_jpg(frame)

    if full_jpg:
        yield {
            "region": "full",
            "frame_width": width,
            "frame_height": height,
            "offset_x": 0,
            "offset_y": 0,
            "region_width": width,
            "region_height": height,
            "jpg": full_jpg
        }

    if not PHONE_DETECTION_USE_TILES:
        return

    cols, rows = parse_tile_grid(PHONE_DETECTION_TILE_GRID)

    for row in range(rows):
        top = int(row * height / rows)
        bottom = int((row + 1) * height / rows)

        for col in range(cols):
            left = int(col * width / cols)
            right = int((col + 1) * width / cols)
            crop = frame[top:bottom, left:right]

            if crop.size == 0:
                continue

            jpg = encode_frame_jpg(crop)

            if jpg:
                yield {
                    "region": f"tile_{row + 1}_{col + 1}",
                    "frame_width": width,
                    "frame_height": height,
                    "offset_x": left,
                    "offset_y": top,
                    "region_width": right - left,
                    "region_height": bottom - top,
                    "jpg": jpg
                }


def sampled_video_frames(video_path, max_frames):
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

            for sample in frame_image_samples(frame):
                yield frame_number, sample
    finally:
        cap.release()


def run_phone_detection(video_path):
    frame_results = []
    phone_frames = 0
    total_phones = 0
    best_confidence = 0.0
    class_summary = {}
    response_shapes = []
    debug_samples = []

    frame_map = {}

    for frame_number, sample in sampled_video_frames(video_path, PHONE_DETECTION_MAX_FRAMES):
        response = call_roboflow_phone_workflow(sample["jpg"])
        detections = normalize_detection_coordinates(
            phone_detections_from_response(response),
            sample
        )

        if len(response_shapes) < 3:
            response_shapes.append(response_shape(response))

        if len(debug_samples) < 1:
            debug_samples.append(scrub_roboflow_debug(response))

        for item in response_class_summary(response):
            current = class_summary.setdefault(item["class"], {
                "count": 0,
                "best_confidence": 0.0
            })
            current["count"] += item["count"]
            current["best_confidence"] = max(current["best_confidence"], item["best_confidence"])

        if detections:
            total_phones += len(detections)
            best_confidence = max(best_confidence, detections[0]["confidence"])

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
        frame_item["detections"].sort(key=lambda item: item["confidence"], reverse=True)
        frame_item["detections"] = frame_item["detections"][:8]
        frame_item["phone_count"] = len(frame_item["detections"])

    frame_results = list(frame_map.values())
    phone_frames = sum(1 for item in frame_results if item["phone_count"] > 0)

    result = {
        "success": True,
        "phone_detected": phone_frames > 0,
        "frames_checked": len(frame_results),
        "phone_frames": phone_frames,
        "total_phones": total_phones,
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
        "response_shapes": response_shapes,
        "debug_samples": debug_samples,
        "frames": frame_results
    }

    PHONE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with (PHONE_OUTPUT_DIR / "phone_detection.json").open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return result


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

    if not object_name.startswith("attendance-uploads/"):
        return jsonify({"success": False, "error": "Invalid uploaded video object."}), 400

    try:
        filename = save_uploaded_video_from_gcs(object_name)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

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
        "results": attendance_csv_rows(),
        "stdout": result.stdout[-4000:]
    })


@app.post("/api/attendance/process-gcs-video-stream")
def process_gcs_attendance_video_stream():
    payload = request.get_json(force=True, silent=True) or {}
    object_name = payload.get("object_name") or ""
    expected_names = expected_names_from_payload(payload)

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
