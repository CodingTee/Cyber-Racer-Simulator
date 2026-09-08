# =============================================================================
# settings.py -- process-wide configuration and shared pygame resources.
#
# Every module imports this, so anything created here is a singleton: the
# 1440x810 window, the colour palette, the monospace fonts and the four
# pre-scaled car sprites. Importing the module also boots pygame itself, so
# it has to be imported before any other project module.
# =============================================================================
import os
import ctypes
import sys
import pygame

# ---- Absolute path to the folder holding this file ----
# Bundled assets are resolved against the module directory rather than the
# shell's working directory, so `python Code/main.py` run from the repository
# root finds the same sprites as `python main.py` run from inside Code/.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- Display and simulation timing ----
SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 810
FPS = 60

# ---- Car geometry and LiDAR ----
CAR_WIDTH = 24
CAR_HEIGHT = 50
MAX_RAY_LENGTH = 300.0  # Increased range for early corner detection

# Colors
COLOR_BG = (20, 22, 28)
COLOR_GRASS = (46, 117, 59)
COLOR_GRASS_DARK = (38, 98, 49)
COLOR_GRAVEL = (214, 185, 127)
COLOR_ASPHALT = (65, 72, 85)
COLOR_ASPHALT_LINE = (110, 120, 138)
COLOR_KERB_RED = (220, 53, 69)
COLOR_KERB_WHITE = (245, 245, 245)
COLOR_TEXT = (236, 240, 241)
COLOR_TEXT_MUTED = (140, 150, 165)
COLOR_PANEL_BG = (30, 34, 44)
COLOR_BORDER = (60, 68, 85)
COLOR_WRECK = (100, 100, 100)

# ---- Car liveries, HUD accents and LiDAR ray colours ----
COLOR_CAR_RED = (220, 53, 69)
COLOR_CAR_BLACK = (55, 62, 70)
COLOR_CAR_YELLOW = (241, 196, 15)
COLOR_CAR_GREEN = (80, 200, 120)
COLOR_GOLD_AURA = (241, 196, 15)
COLOR_RAY_SAFE = (46, 204, 113)
COLOR_RAY_ALERT = (231, 76, 60)

# ==============================================================================
# Pygame & Windows IME Hard Disable
# ==============================================================================
os.environ["SDL_IME_SHOW_UI"] = "0"
os.environ["SDL_IME_INTERNAL_EDITING"] = "0"

pygame.init()
pygame.font.init()
pygame.key.stop_text_input()

# SCALED keeps the 1440x810 design resolution on any monitor size; the game
# never has to know the real window dimensions.
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN | pygame.SCALED)
pygame.display.set_caption("Cyber Racer Simulator")
clock = pygame.time.Clock()

def disable_windows_ime():
    """Disables Windows IME composition to prevent input delays and candidate window popups."""
    if sys.platform.startswith("win"):
        try:
            hwnd = pygame.display.get_wm_info().get("window")
            if not hwnd:
                hwnd = ctypes.windll.user32.GetActiveWindow()
            if hwnd:
                imm32 = ctypes.windll.imm32
                imm32.ImmAssociateContext(hwnd, None)
                imm32.ImmDisableIME(0)
                KLF_ACTIVATE = 1
                ctypes.windll.user32.LoadKeyboardLayoutW("00000409", KLF_ACTIVATE)
        except Exception:
            pass

disable_windows_ime()

# ---- Fonts: Consolas everywhere so the HUD columns line up ----
font_btn = pygame.font.SysFont("Consolas", 18, bold=True)
font_main = pygame.font.SysFont("Consolas", 14, bold=True)
font_title = pygame.font.SysFont("Consolas", 24, bold=True)
font_subtitle = pygame.font.SysFont("Consolas", 13)
font_countdown = pygame.font.SysFont("Consolas", 64, bold=True)
font_prompt = pygame.font.SysFont("Consolas", 22, bold=True)
font_transition = pygame.font.SysFont("Consolas", 28, bold=True)

def load_car_sprite(primary_name, fallback_color):
    """Searches root, Pictures, and pictures folders for sprite assets.

    The working directory is searched first and BASE_DIR second, so launching
    from any directory still finds the bundled sprites.
    """
    search_dirs = ["", "Pictures", "pictures",
                   BASE_DIR, os.path.join(BASE_DIR, "Pictures")]
    extensions = ["", ".png", ".jpg", ".jpeg"]
    name_variants = [primary_name, primary_name.replace(" ", "_")]

    candidates = []
    for d in search_dirs:
        for name in name_variants:
            for ext in extensions:
                path = os.path.join(d, f"{name}{ext}") if d else f"{name}{ext}"
                candidates.append(path)

    found_path = next((c for c in candidates if os.path.exists(c)), None)
    if found_path:
        raw_img = pygame.image.load(found_path).convert_alpha()
        if raw_img.get_at((0, 0))[:3] == (0, 0, 0):
            raw_img.set_colorkey((0, 0, 0))
        crop_box = raw_img.get_bounding_rect()
        cropped = raw_img.subsurface(crop_box).copy() if (crop_box.width > 0 and crop_box.height > 0) else raw_img
        return pygame.transform.smoothscale(cropped, (CAR_WIDTH, CAR_HEIGHT))
    
    surf = pygame.Surface((CAR_WIDTH, CAR_HEIGHT), pygame.SRCALPHA)
    pygame.draw.rect(surf, fallback_color, (0, 0, CAR_WIDTH, CAR_HEIGHT), border_radius=4)
    pygame.draw.rect(surf, (255, 255, 255), (3, 5, CAR_WIDTH - 6, 8), border_radius=2)
    return surf

# Build the four liveries once at import time; every Car instance shares them.
SPRITE_RED_F1 = load_car_sprite("Red F1 2D", COLOR_CAR_RED)
SPRITE_BLACK_F1 = load_car_sprite("Black F1 2D", COLOR_CAR_BLACK)
SPRITE_YELLOW_F1 = load_car_sprite("Yellow F1 2D", COLOR_CAR_YELLOW)
SPRITE_GREEN_F1 = load_car_sprite("Light Green F1 2D", COLOR_CAR_GREEN)
