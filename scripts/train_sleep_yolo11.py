from pathlib import Path
import argparse
import shutil

from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = PROJECT_ROOT / "sleep_yolo" / "data.yaml"
DEFAULT_OUTPUT_MODEL = PROJECT_ROOT / "models" / "sleep_yolo11.pt"


def parse_args():
    parser = argparse.ArgumentParser(description="Train the local YOLO11 sleep detector.")
    parser.add_argument("--data", default=str(DEFAULT_DATA))
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--imgsz", type=int, default=768)
    parser.add_argument("--batch", default="auto")
    parser.add_argument("--device", default=None)
    parser.add_argument("--project", default=str(PROJECT_ROOT / "runs" / "sleep_yolo"))
    parser.add_argument("--name", default="yolo11_sleep")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT_MODEL))
    return parser.parse_args()


def parse_batch(value):
    raw = str(value).strip().lower()

    if raw == "auto":
        return -1

    try:
        number = float(raw)
    except ValueError:
        raise SystemExit("--batch must be an integer, float, or auto")

    return int(number) if number.is_integer() else number


def main():
    args = parse_args()
    data_path = Path(args.data)

    if not data_path.exists():
        raise SystemExit(f"Dataset config not found: {data_path}")

    model = YOLO(args.model)
    train_args = {
        "data": str(data_path),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": parse_batch(args.batch),
        "project": args.project,
        "name": args.name,
        "exist_ok": True
    }

    if args.device:
        train_args["device"] = args.device

    results = model.train(**train_args)
    save_dir = Path(getattr(results, "save_dir", Path(args.project) / args.name))
    best_model = save_dir / "weights" / "best.pt"

    if not best_model.exists():
        raise SystemExit(f"Training finished but best.pt was not found at {best_model}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best_model, out_path)
    print(f"Saved trained sleep model: {out_path}")


if __name__ == "__main__":
    main()
