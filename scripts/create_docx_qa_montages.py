"""Create labeled 2x2 contact sheets for DOCX render QA."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pages", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    pages = sorted(args.pages.glob("page_*.png"))
    args.output.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default()
    for start in range(0, len(pages), 4):
        batch = pages[start : start + 4]
        opened = [Image.open(path).convert("RGB") for path in batch]
        width = max(image.width for image in opened)
        height = max(image.height for image in opened)
        label_height = 25
        sheet = Image.new("RGB", (width * 2, (height + label_height) * 2), "#d0d0d0")
        draw = ImageDraw.Draw(sheet)
        for index, (path, image) in enumerate(zip(batch, opened, strict=True)):
            x = (index % 2) * width
            y = (index // 2) * (height + label_height)
            sheet.paste(image, (x, y + label_height))
            draw.text((x + 6, y + 5), path.name, fill="black", font=font)
        end = start + len(batch)
        sheet.save(args.output / f"sheet_{start + 1:03d}_{end:03d}.png", optimize=True)


if __name__ == "__main__":
    main()
