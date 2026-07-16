from pathlib import Path
from PIL import Image

BASE = Path(r"D:/PROGRAMA/OFICINA DE PESCA/OFICINA_PESCA_ORIGINAL/android_apk/app/src/main/res")
ICO = Path(r"D:/PROGRAMA/OFICINA DE PESCA/OFICINA_PESCA_ORIGINAL/icone_oficina.ico")
STATIC_DIR = Path(r"D:/PROGRAMA/OFICINA DE PESCA/OFICINA_PESCA_ORIGINAL/static")

img = Image.open(ICO)
best = None
frames = getattr(img, "n_frames", 1)
for frame in range(frames):
    try:
        img.seek(frame)
        current = img.convert("RGBA")
        if best is None or current.size[0] * current.size[1] > best.size[0] * best.size[1]:
            best = current.copy()
    except EOFError:
        break

if best is None:
    best = img.convert("RGBA")

sizes = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}

for folder, size in sizes.items():
    out = BASE / folder / "ic_launcher.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    best.resize((size, size), Image.LANCZOS).save(out, format="PNG")
    print(f"updated {out}")

logo_path = STATIC_DIR / "logo.png"
logo_path.parent.mkdir(parents=True, exist_ok=True)
best.resize((256, 256), Image.LANCZOS).save(logo_path, format="PNG")
print(f"updated {logo_path}")

favicon_path = STATIC_DIR / "favicon.ico"
favicon_path.write_bytes(ICO.read_bytes())
print(f"updated {favicon_path}")
