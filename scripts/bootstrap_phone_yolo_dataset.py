from pathlib import Path
import argparse
import random

import cv2
import numpy as np
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIDEO_DIR = PROJECT_ROOT / "data" / "classroom_videos"
DEFAULT_DATASET_DIR = PROJECT_ROOT / "phone_yolo"
PHONE_LABELS = {"phone", "cell phone", "mobile phone", "smartphone", "cellphone"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a YOLO11 phone dataset from local photos or videos."
    )
    parser.add_argument("--source", action="append", default=[],
                        help="Image/video file or folder. Can be passed more than once.")
    parser.add_argument("--exclude", action="append", default=[],
                        help="Skip files whose path contains this text. Can be passed more than once.")
    parser.add_argument("--out", default=str(DEFAULT_DATASET_DIR),
                        help="Output dataset folder.")
    parser.add_argument("--model", default="yolo11n.pt",
                        help="YOLO11 model used to create first-pass labels.")
    parser.add_argument("--conf", type=float, default=0.20,
                        help="Confidence threshold for auto-labeling phones.")
    parser.add_argument("--frames-per-video", type=int, default=80,
                        help="Maximum frames to sample from each video.")
    parser.add_argument("--val-split", type=float, default=0.20,
                        help="Validation split from 0.0 to 0.9.")
    parser.add_argument("--include-negatives", action="store_true",
                        help="Also keep frames/images where YOLO11 found no phone.")
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


def dataset_paths(root):
    root = Path(root)
    paths = {
        "train_images": root / "images" / "train",
        "val_images": root / "images" / "val",
        "train_labels": root / "labels" / "train",
        "val_labels": root / "labels" / "val",
    }

    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)

    return paths


def iter_sources(raw_sources, excludes):
    sources = [Path(item) for item in raw_sources] or [DEFAULT_VIDEO_DIR]
    excludes = [item.lower() for item in excludes if item]

    for source in sources:
        source = source if source.is_absolute() else PROJECT_ROOT / source

        if any(item in str(source).lower() for item in excludes):
            continue

        if source.is_file() and source.suffix.lower() in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
            yield source
            continue

        if not source.is_dir():
            continue

        for path in source.rglob("*"):
            if (
                path.suffix.lower() in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
                and not any(item in str(path).lower() for item in excludes)
            ):
                yield path


def yolo_boxes(model, frame, conf):
    result = model(frame, conf=conf, verbose=False)[0]
    names = getattr(model, "names", {}) or getattr(result, "names", {}) or {}
    boxes = getattr(result, "boxes", None)

    if boxes is None:
        return []

    height, width = frame.shape[:2]
    labels = []

    for box in boxes:
        cls = int(box.cls[0])
        label = str(names.get(cls, cls)).strip().lower()

        if label not in PHONE_LABELS:
            continue

        x1, y1, x2, y2 = [float(value) for value in box.xyxy[0]]
        center_x = ((x1 + x2) / 2) / width
        center_y = ((y1 + y2) / 2) / height
        box_w = max(0.0, x2 - x1) / width
        box_h = max(0.0, y2 - y1) / height
        labels.append(f"0 {center_x:.6f} {center_y:.6f} {box_w:.6f} {box_h:.6f}")

    return labels


def sample_video_frames(path, max_frames):
    cap = cv2.VideoCapture(str(path))

    if not cap.isOpened():
        print(f"Skipping unreadable video: {path}")
        return

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        count = max(1, min(max_frames, total_frames or max_frames))
        frame_numbers = np.linspace(0, max(0, total_frames - 1), count, dtype=int) if total_frames else range(count)

        for frame_number in sorted(set(int(item) for item in frame_numbers)):
            if total_frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

            ok, frame = cap.read()

            if ok:
                yield frame_number, frame
    finally:
        cap.release()


def save_item(paths, split, stem, frame, labels):
    image_path = paths[f"{split}_images"] / f"{stem}.jpg"
    label_path = paths[f"{split}_labels"] / f"{stem}.txt"
    cv2.imwrite(str(image_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    label_path.write_text("\n".join(labels) + ("\n" if labels else ""), encoding="utf-8")


def write_dataset_yaml(root):
    dataset_root = Path(root).resolve()
    data_yaml = dataset_root / "data.yaml"
    data_yaml.write_text(
        f"path: {dataset_root.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        "  0: phone\n",
        encoding="utf-8"
    )


def main():
    args = parse_args()
    random.seed(args.seed)
    paths = dataset_paths(args.out)
    write_dataset_yaml(args.out)
    model = YOLO(args.model)
    sources = list(iter_sources(args.source, args.exclude))

    if not sources:
        raise SystemExit("No images or videos found for dataset bootstrapping.")

    saved = 0
    positives = 0

    for source_index, source in enumerate(sources):
        is_video = source.suffix.lower() in VIDEO_EXTENSIONS
        frames = (
            sample_video_frames(source, args.frames_per_video)
            if is_video
            else [(0, cv2.imread(str(source)))]
        )

        for frame_index, frame in frames:
            if frame is None:
                continue

            labels = yolo_boxes(model, frame, args.conf)

            if not labels and not args.include_negatives:
                continue

            split = "val" if random.random() < min(0.9, max(0.0, args.val_split)) else "train"
            stem = f"{source.stem}_{source_index:03d}_{int(frame_index):06d}"
            save_item(paths, split, stem, frame, labels)
            saved += 1
            positives += 1 if labels else 0

    print(f"Saved images: {saved}")
    print(f"Images with phone labels: {positives}")
    print(f"Dataset: {Path(args.out).resolve()}")

    if positives == 0:
        raise SystemExit(
            "No phones were auto-labeled. Add labeled phone photos manually or lower --conf."
        )


if __name__ == "__main__":
    main()
