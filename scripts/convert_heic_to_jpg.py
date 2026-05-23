import argparse
from pathlib import Path

from PIL import Image, ImageOps
import pillow_heif


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = [
    PROJECT_ROOT / "data" / "students",
    PROJECT_ROOT / "all students",
]
HEIC_EXTENSIONS = {".heic", ".heif"}


def iter_heic_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in HEIC_EXTENSIONS:
            yield path


def converted_path(heic_path: Path) -> Path:
    return heic_path.with_suffix(".jpg")


def convert_file(heic_path: Path, overwrite: bool, dry_run: bool) -> str:
    jpg_path = converted_path(heic_path)

    if jpg_path.exists() and not overwrite:
        return f"skip existing: {jpg_path}"

    if dry_run:
        action = "overwrite" if jpg_path.exists() else "convert"
        return f"{action}: {heic_path} -> {jpg_path}"

    with Image.open(heic_path) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.save(jpg_path, "JPEG", quality=95, optimize=True)

    return f"converted: {heic_path} -> {jpg_path}"


def convert_root(root: Path, overwrite: bool, dry_run: bool) -> tuple[int, int]:
    if not root.exists():
        print(f"skip missing folder: {root}")
        return 0, 0

    found = 0
    converted = 0

    for heic_path in iter_heic_files(root):
        found += 1
        message = convert_file(heic_path, overwrite=overwrite, dry_run=dry_run)
        print(message)

        if message.startswith(("converted:", "convert:", "overwrite:")):
            converted += 1

    return found, converted


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert HEIC/HEIF student photos to JPG for AI training."
    )
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        help="Folders to scan. Defaults to data/students and all students.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite JPG files that already exist next to HEIC files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be converted without writing JPG files.",
    )
    return parser.parse_args()


def main():
    pillow_heif.register_heif_opener()
    args = parse_args()

    roots = args.roots or DEFAULT_ROOTS
    total_found = 0
    total_converted = 0

    for root in roots:
        root = root if root.is_absolute() else PROJECT_ROOT / root
        found, converted = convert_root(
            root,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
        total_found += found
        total_converted += converted

    action = "would convert" if args.dry_run else "converted"
    print(f"\nDone. Found {total_found} HEIC/HEIF files; {action} {total_converted}.")


if __name__ == "__main__":
    main()
