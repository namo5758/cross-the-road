"""Thai-capable font discovery shared by game setup and rendering."""

import pygame

# Remember the chosen font path separately for regular and bold text to avoid repeated font searches.
# เก็บผลการค้นหาฟอนต์ไว้ใช้ซ้ำ แยกตัวปกติกับตัวหนา เพื่อลดการค้นหาซ้ำ
_THAI_FONT_CACHE = {}


def _renders_thai(font_path):
    """Check if the font contains actual distinct Thai glyphs."""
    try:
        test_font = pygame.font.Font(font_path, 20)
        # Render two different Thai letters and compare pixel bytes.
        # Identical output suggests the font drew the same missing-character placeholder for both.
        # ลองวาด ก กับ ข ถ้าภาพเหมือนกันอาจเป็นสัญลักษณ์แทนอักษรที่ฟอนต์ไม่รองรับ
        first_rendered_glyph = pygame.image.tobytes(test_font.render("ก", True, (255, 255, 255)), "RGBA")
        second_rendered_glyph = pygame.image.tobytes(test_font.render("ข", True, (255, 255, 255)), "RGBA")
        return first_rendered_glyph != second_rendered_glyph
    except Exception:
        return False


def _find_thai_font(bold):
    preferred_fonts = (
        "leelawadeeui", "leelawadee", "tahoma", "thonburi", "notosansthaiui",
        "notosansthai", "sarabun", "thsarabunnew", "garuda", "loma", "kinnari",
        "angsananew", "cordianew", "browallianew"
    )
    # Try preferred Thai fonts first, then add other installed fonts without repeating names.
    all_font_names = list(preferred_fonts) + [font_name for font_name in pygame.font.get_fonts() if font_name not in preferred_fonts]
    for font_name in all_font_names:
        font_path = pygame.font.match_font(font_name, bold=bold)
        if font_path and _renders_thai(font_path):
            return font_path
    return None


def load_font(size, bold=False):
    # Search once per style; if that style fails, try the opposite style before using the default font.
    if bold not in _THAI_FONT_CACHE:
        _THAI_FONT_CACHE[bold] = _find_thai_font(bold) or _find_thai_font(not bold)
    font_path = _THAI_FONT_CACHE[bold]
    return pygame.font.Font(font_path, size) if font_path else pygame.font.Font(None, size + 6)
