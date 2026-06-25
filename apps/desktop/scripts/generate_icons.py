from pathlib import Path

from PIL import Image
from reportlab.graphics import renderPM
from svglib.svglib import svg2rlg


def main() -> int:
    desktop_root = Path(__file__).resolve().parent.parent
    svg_path = desktop_root / "src-tauri" / "app-icon.svg"
    icons_dir = desktop_root / "src-tauri" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    drawing = svg2rlg(str(svg_path))
    if drawing is None:
        raise RuntimeError(f"Could not parse {svg_path}")

    png_1024 = icons_dir / "icon.png"
    renderPM.drawToFile(drawing, str(png_1024), fmt="PNG", dpi=96)

    source = Image.open(png_1024).convert("RGBA")
    if source.width != 1024 or source.height != 1024:
        source = source.resize((1024, 1024), Image.Resampling.LANCZOS)
        source.save(png_1024)

    sizes = [16, 32, 48, 64, 128, 256]
    images = [source.resize((size, size), Image.Resampling.LANCZOS) for size in sizes]

    ico_path = icons_dir / "icon.ico"
    images[0].save(
        ico_path,
        format="ICO",
        sizes=[(img.width, img.height) for img in images],
        append_images=images[1:],
    )

    for size in [32, 128, 256, 512]:
        resized = source.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(icons_dir / f"icon{size}.png", format="PNG")

    print(f"Icons generated in {icons_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
