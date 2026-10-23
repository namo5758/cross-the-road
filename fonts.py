"""Thai-capable font discovery shared by game setup and rendering."""

import pygame

_THAI_FONT = {}


def _renders_thai(path):
    """True if the font really has Thai glyphs (missing glyphs all render as the same box)."""
    try:
        f = pygame.font.Font(path, 20)
        a = pygame.image.tobytes(f.render("ก", True, (255, 255, 255)), "RGBA")
        b = pygame.image.tobytes(f.render("ข", True, (255, 255, 255)), "RGBA")
        return a != b
    except Exception:
        return False


def _find_thai_font(bold):
    preferred = ("leelawadeeui", "leelawadee", "tahoma", "thonburi", "notosansthaiui",
                 "notosansthai", "sarabun", "thsarabunnew", "garuda", "loma", "kinnari",
                 "angsananew", "cordianew", "browallianew")
    names = list(preferred) + [n for n in pygame.font.get_fonts() if n not in preferred]
    for name in names:
        path = pygame.font.match_font(name, bold=bold)
        if path and _renders_thai(path):
            return path
    return None


def load_font(size, bold=False):
    if bold not in _THAI_FONT:
        _THAI_FONT[bold] = _find_thai_font(bold) or _find_thai_font(not bold)
    path = _THAI_FONT[bold]
    return pygame.font.Font(path, size) if path else pygame.font.Font(None, size + 6)



