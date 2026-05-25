from pathlib import Path
import argparse
import hashlib
import random
import re
import shutil
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "datasets" / "sleep" / "source.zip"
DEFAULT_OUTPUT = PROJECT_ROOT / "sleep_yolo"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
DEFAULT_TERMS = "sleep,sleeping,sleeper,asleep,nap,napping,head down,heads down,lying down,laying down"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract a single-class YOLO sleep dataset from a YOLO-format source dataset."
    )
    parser.add_argument("--source", default=str(DEFAULT_SOURCE),
                        help="YOLO dataset zip or extracted folder.")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT),
                        help="Output YOLO dataset folder.")
    parser.add_argument("--terms", default=DEFAULT_TERMS,
                        help="Comma-separated class-name terms that should map to sleep.")
    parser.add_argument("--max-negatives", type=int, default=800,
                        help="Copy up to this many non-sleep images as negative examples.")
    parser.add_argument("--max-positives", type=int, default=0,
                        help="Copy up to this many positive images. 0 means all positives.")
    parser.add_argument("--val-split", type=float, default=0.2,
                        help="Validation split to create if the source has no validation positives.")
    parser.add_argument("--clean", action="store_true",
                        help="Remove the output dataset before writing.")
    parser.add_argument("--seed", type=int, default=11)
    return parser.parse_args()


def load_yaml(text):
    try:
        import yaml
    except ImportError as e:
        raise SystemExit("PyYAML is required. It is installed with ultralytics; run `pip install -r requirements.txt`.") from e

    return yaml.safe_load(text) or {}


def normalize_name(name):
    return str(name).replace("\\", "/")


def parse_names(data):
    raw_names = data.get("names") or {}

    if isinstance(raw_names, list):
        return {index: str(name) for index, name in enumerate(raw_names)}

    if isinstance(raw_names, dict):
        names = {}

        for key, value in raw_names.items():
            try:
                names[int(key)] = str(value)
            except (TypeError, ValueError):
                continue

        return names

    return {}


def class_ids_for_terms(names, terms):
    wanted = set()
    terms = [term.strip().lower() for term in terms.split(",") if term.strip()]

    for class_id, name in names.items():
        clean = re.sub(r"[_-]+", " ", str(name).strip().lower())

        if any(term in clean for term in terms):
            wanted.add(class_id)

    return wanted


def split_from_name(name):
    parts = normalize_name(name).lower().split("/")

    if "train" in parts:
        return "train"

    if "val" in parts or "valid" in parts or "validation" in parts or "test" in parts:
        return "val"

    return ""


def filter_label_text(text, wanted_ids):
    kept = []

    for line in text.splitlines():
        parts = line.strip().split()

        if len(parts) < 5:
            continue

        try:
            class_id = int(float(parts[0]))
        except ValueError:
            continue

        if class_id not in wanted_ids:
            continue

        kept.append("0 " + " ".join(parts[1:]))

    return kept


def safe_stem(name):
    raw = Path(normalize_name(name)).stem
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._-") or "image"
    digest = hashlib.sha1(normalize_name(name).encode("utf-8")).hexdigest()[:10]
    return f"{clean}_{digest}"


def prepare_output(root, clean=False):
    root = Path(root)

    if clean and root.exists():
        resolved = root.resolve()

        if PROJECT_ROOT.resolve() not in resolved.parents and resolved != PROJECT_ROOT.resolve():
            raise SystemExit(f"Refusing to clean outside the project: {resolved}")

        shutil.rmtree(root)

    paths = {
        "train_images": root / "images" / "train",
        "val_images": root / "images" / "val",
        "train_labels": root / "labels" / "train",
        "val_labels": root / "labels" / "val",
    }

    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)

    return paths


def write_dataset_yaml(root):
    dataset_root = Path(root).resolve()
    (dataset_root / "data.yaml").write_text(
        f"path: {dataset_root.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        "  0: sleep\n",
        encoding="utf-8"
    )


def locate_image(name, image_names):
    normalized = normalize_name(name)

    if "/labels/" not in normalized:
        return ""

    base = normalized.replace("/labels/", "/images/", 1)
    base_no_ext = str(Path(base).with_suffix("")).replace("\\", "/")

    for extension in IMAGE_EXTENSIONS:
        candidate = base_no_ext + extension

        if candidate in image_names:
            return candidate

    lower_images = {item.lower(): item for item in image_names}

    for extension in IMAGE_EXTENSIONS:
        candidate = (base_no_ext + extension).lower()

        if candidate in lower_images:
            return lower_images[candidate]

    return ""


def records_from_zip(path, wanted_ids, rng, max_negatives):
    positives = []
    negatives = []

    with zipfile.ZipFile(path) as archive:
        names = [normalize_name(item) for item in archive.namelist()]
        name_set = set(names)
        label_names = [
            item for item in names
            if item.lower().endswith(".txt") and "/labels/" in item.lower()
        ]

        for label_name in label_names:
            try:
                text = archive.read(label_name).decode("utf-8", errors="ignore")
            except KeyError:
                continue

            image_name = locate_image(label_name, name_set)

            if not image_name:
                continue

            kept = filter_label_text(text, wanted_ids)
            split = split_from_name(label_name)
            record = {
                "split": split,
                "label_name": label_name,
                "image_name": image_name,
                "labels": kept
            }

            if kept:
                positives.append(record)
            elif max_negatives > 0:
                negatives.append(record)

        rng.shuffle(negatives)

    return positives, negatives[:max_negatives]


def records_from_folder(path, wanted_ids, rng, max_negatives):
    root = Path(path)
    positives = []
    negatives = []
    image_paths = {
        item.relative_to(root).as_posix()
        for item in root.rglob("*")
        if item.suffix.lower() in IMAGE_EXTENSIONS
    }

    for label_path in root.rglob("*.txt"):
        relative_label = label_path.relative_to(root).as_posix()

        if "/labels/" not in relative_label.lower():
            continue

        image_name = locate_image(relative_label, image_paths)

        if not image_name:
            continue

        text = label_path.read_text(encoding="utf-8", errors="ignore")
        kept = filter_label_text(text, wanted_ids)
        record = {
            "split": split_from_name(relative_label),
            "label_path": label_path,
            "image_path": root / image_name,
            "labels": kept
        }

        if kept:
            positives.append(record)
        elif max_negatives > 0:
            negatives.append(record)

    rng.shuffle(negatives)
    return positives, negatives[:max_negatives]


def source_names_from_zip(path):
    with zipfile.ZipFile(path) as archive:
        yaml_names = [
            name for name in archive.namelist()
            if Path(normalize_name(name)).name.lower() in {"data.yaml", "dataset.yaml"}
        ]

        if not yaml_names:
            raise SystemExit("Could not find data.yaml inside the YOLO archive.")

        data = load_yaml(archive.read(yaml_names[0]).decode("utf-8", errors="ignore"))
        return parse_names(data)


def source_names_from_folder(path):
    root = Path(path)
    yaml_paths = [
        item for item in root.rglob("*.yaml")
        if item.name.lower() in {"data.yaml", "dataset.yaml"}
    ]

    if not yaml_paths:
        raise SystemExit("Could not find data.yaml in the YOLO folder.")

    data = load_yaml(yaml_paths[0].read_text(encoding="utf-8", errors="ignore"))
    return parse_names(data)


def assign_validation(records, rng, val_split):
    if any(record["split"] == "val" for record in records if record["labels"]):
        for record in records:
            if not record["split"]:
                record["split"] = "train"

        return

    positives = [record for record in records if record["labels"]]
    rng.shuffle(positives)
    val_count = max(1, int(len(positives) * max(0.0, min(0.9, val_split)))) if len(positives) > 1 else 0
    val_ids = {id(record) for record in positives[:val_count]}

    for record in records:
        if id(record) in val_ids:
            record["split"] = "val"
        elif record["split"] not in {"train", "val"}:
            record["split"] = "train"


def copy_zip_records(source, records, paths):
    copied = 0

    with zipfile.ZipFile(source) as archive:
        for record in records:
            split = "val" if record["split"] == "val" else "train"
            image_name = record["image_name"]
            extension = Path(image_name).suffix.lower() or ".jpg"
            stem = safe_stem(image_name)
            image_out = paths[f"{split}_images"] / f"{stem}{extension}"
            label_out = paths[f"{split}_labels"] / f"{stem}.txt"

            image_out.write_bytes(archive.read(image_name))
            label_out.write_text("\n".join(record["labels"]) + ("\n" if record["labels"] else ""), encoding="utf-8")
            copied += 1

    return copied


def copy_folder_records(records, paths):
    copied = 0

    for record in records:
        split = "val" if record["split"] == "val" else "train"
        image_path = record["image_path"]
        extension = image_path.suffix.lower() or ".jpg"
        stem = safe_stem(str(image_path))
        image_out = paths[f"{split}_images"] / f"{stem}{extension}"
        label_out = paths[f"{split}_labels"] / f"{stem}.txt"

        shutil.copy2(image_path, image_out)
        label_out.write_text("\n".join(record["labels"]) + ("\n" if record["labels"] else ""), encoding="utf-8")
        copied += 1

    return copied


def main():
    args = parse_args()
    rng = random.Random(args.seed)
    source = Path(args.source)

    if not source.exists():
        raise SystemExit(f"Source dataset not found: {source}")

    names = source_names_from_zip(source) if source.suffix.lower() == ".zip" else source_names_from_folder(source)
    wanted_ids = class_ids_for_terms(names, args.terms)

    if not wanted_ids:
        available = ", ".join(f"{key}:{value}" for key, value in sorted(names.items()))
        raise SystemExit(f"No sleep class matched --terms. Available classes: {available}")

    if source.suffix.lower() == ".zip":
        positives, negatives = records_from_zip(source, wanted_ids, rng, args.max_negatives)
    else:
        positives, negatives = records_from_folder(source, wanted_ids, rng, args.max_negatives)

    if args.max_positives > 0:
        rng.shuffle(positives)
        positives = positives[:args.max_positives]

    if not positives:
        matched = ", ".join(names[class_id] for class_id in sorted(wanted_ids))
        raise SystemExit(f"Matched classes ({matched}) but found no positive sleep labels.")

    records = positives + negatives
    assign_validation(records, rng, args.val_split)
    paths = prepare_output(args.out, args.clean)
    write_dataset_yaml(args.out)

    copied = (
        copy_zip_records(source, records, paths)
        if source.suffix.lower() == ".zip"
        else copy_folder_records(records, paths)
    )
    train_count = sum(1 for item in records if item["split"] != "val")
    val_count = sum(1 for item in records if item["split"] == "val")
    matched = ", ".join(names[class_id] for class_id in sorted(wanted_ids))

    print(f"Matched sleep classes: {matched}")
    print(f"Positive images: {len(positives)}")
    print(f"Negative images: {len(negatives)}")
    print(f"Copied images: {copied}")
    print(f"Train/val: {train_count}/{val_count}")
    print(f"Dataset: {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()
