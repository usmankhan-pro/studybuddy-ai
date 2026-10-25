from pathlib import Path
from PIL import Image, ImageDraw

def create_studybuddy_icon(output_path: str = "app_icon.ico") -> None:
    canvas_size = 512
    img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.ellipse([100, 420, 412, 480], fill=(0, 0, 0, 50))
    draw.line([256, 120, 256, 45], fill=(74, 85, 104, 255), width=18)
    draw.ellipse([221, 20, 291, 90], fill=(56, 178, 172, 255))
    draw.rounded_rectangle([45, 195, 90, 325], radius=24, fill=(43, 108, 176, 255))
    draw.rounded_rectangle([422, 195, 467, 325], radius=24, fill=(43, 108, 176, 255))
    draw.rounded_rectangle([80, 105, 432, 415], radius=90, fill=(49, 130, 206, 255), outline=(44, 82, 130, 255), width=12)
    draw.rounded_rectangle([122, 150, 390, 360], radius=55, fill=(26, 32, 44, 255), outline=(45, 55, 72, 255), width=8)
    draw.ellipse([168, 205, 226, 270], fill=(79, 209, 197, 255))
    draw.ellipse([180, 215, 200, 235], fill=(255, 255, 255, 230))
    draw.ellipse([286, 205, 344, 270], fill=(79, 209, 197, 255))
    draw.ellipse([298, 215, 318, 235], fill=(255, 255, 255, 230))
    draw.arc([196, 260, 316, 330], start=20, end=160, fill=(79, 209, 197, 255), width=12)

    icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(output_path, format="ICO", sizes=icon_sizes)
    print(f"Icon generated: {Path(output_path).resolve()}")

if __name__ == "__main__":
    create_studybuddy_icon()
