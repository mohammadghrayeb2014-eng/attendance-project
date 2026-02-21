from pathlib import Path
from PIL import Image
import pillow_heif

pillow_heif.register_heif_opener()

ROOTS = [
    Path(r"C:\Users\USER\Desktop\attendance_project\data\students"),
    Path(r"C:\Users\USER\Desktop\attendance_project\all students"),
]

def convert_root(root: Path):
    if not root.exists():
        print("Skip (not found):", root)
        return 0

    count = 0
    for heic in root.rglob("*.HEIC"):
        jpg = heic.with_suffix(".jpg")
        if jpg.exists():
            continue  # don't overwrite if already converted

        img = Image.open(heic)
        img.save(jpg, "JPEG", quality=95)
        print("Converted:", jpg)
        count += 1
    return count

total = 0
for r in ROOTS:
    total += convert_root(r)

print(f"\nDone. Converted {total} HEIC files to JPG.")
