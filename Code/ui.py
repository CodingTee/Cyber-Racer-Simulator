# =============================================================================
# ui.py -- every reusable on-screen widget and overlay.
#
# Presentation only, with one exception: ModifierBoard owns the two race
# settings (lap target, AI on/off) and is locked while a race is live.
# =============================================================================
import re
import time
import pygame
import math

from settings import (
    screen, SCREEN_WIDTH, SCREEN_HEIGHT,
    COLOR_BG, COLOR_PANEL_BG, COLOR_BORDER, COLOR_TEXT,
    font_title, font_subtitle, font_main, font_transition
)


class Button:
    """Modern Cyberpunk Menu Action Button with glowing accents and icon badges."""
    def __init__(self, rect_tuple, text, subtext="", tag="MODE", accent_color=(52, 152, 219)):
        """`accent_color` drives the stripe, the border glow and the arrow."""
        self.rect = pygame.Rect(rect_tuple)
        self.text = text
        self.subtext = subtext
        self.tag = tag
        self.accent_color = accent_color
        self.is_hovered = False
        self.hover_progress = 0.0

    def handle_event(self, event):
        """Track hover; return True when the button is left-clicked."""
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return True
        return False

    def draw(self, surface):
        """Draw the button, easing colour and border towards the hover look."""
        # Smooth hover animation
        target_prog = 1.0 if self.is_hovered else 0.0
        self.hover_progress += (target_prog - self.hover_progress) * 0.25

        # Background fill
        base_bg = (24, 30, 42)
        hover_bg = (32, 44, 62)
        r = int(base_bg[0] + (hover_bg[0] - base_bg[0]) * self.hover_progress)
        g = int(base_bg[1] + (hover_bg[1] - base_bg[1]) * self.hover_progress)
        b = int(base_bg[2] + (hover_bg[2] - base_bg[2]) * self.hover_progress)

        pygame.draw.rect(surface, (r, g, b), self.rect, border_radius=10)

        # Border glow
        border_color = (
            int(COLOR_BORDER[0] + (self.accent_color[0] - COLOR_BORDER[0]) * self.hover_progress),
            int(COLOR_BORDER[1] + (self.accent_color[1] - COLOR_BORDER[1]) * self.hover_progress),
            int(COLOR_BORDER[2] + (self.accent_color[2] - COLOR_BORDER[2]) * self.hover_progress)
        )
        pygame.draw.rect(surface, border_color, self.rect, width=2 if self.is_hovered else 1, border_radius=10)

        # Left Accent Stripe
        stripe_rect = pygame.Rect(self.rect.x, self.rect.y + 6, 4, self.rect.height - 12)
        pygame.draw.rect(surface, self.accent_color, stripe_rect, border_radius=2)

        # Mode Text
        text_color = (255, 255, 255) if self.is_hovered else (230, 235, 245)
        text_surf = font_main.render(self.text, True, text_color)
        surface.blit(text_surf, (self.rect.x + 22, self.rect.y + 16))

        # Description Text
        if self.subtext:
            sub_surf = font_subtitle.render(self.subtext, True, (135, 148, 165))
            surface.blit(sub_surf, (self.rect.x + 22, self.rect.y + 44))

        # Right Action Indicator Arrow (>)
        arrow_color = self.accent_color if self.is_hovered else (70, 85, 105)
        arrow_surf = font_main.render(">", True, arrow_color)
        surface.blit(arrow_surf, (self.rect.right - 28, self.rect.centery - arrow_surf.get_height() // 2))

class ModifierBoard:
    """The race settings the player can change between races.

    Owns the lap target (1 / 3 / 5 / unlimited) and, in single player,
    whether the trained AI opponent runs at all. Both are ignored once a
    race is live, which is why every handler checks the state first.
    """
    def __init__(self, x, y, width, height=136, show_ai_toggle=True):
        """Lay out the board; `show_ai_toggle=False` gives the shorter PvP panel."""
        self.rect = pygame.Rect(x, y, width, height if show_ai_toggle else 76)
        self.show_ai_toggle = show_ai_toggle
        self.lap_options = [1, 3, 5, "INF"]
        self.lap_labels = ["1 LAP", "3 LAPS", "5 LAPS", "UNLIMITED"]
        self.selected_lap_idx = 0

        self.ai_enabled = True
        self.switch_anim = 1.0

    def get_max_laps(self):
        """Selected lap target as a number; the "INF" option is infinity."""
        val = self.lap_options[self.selected_lap_idx]
        return float('inf') if val == "INF" else val

    def is_ai_enabled(self):
        """Whether the trained opponent is switched on (single player only)."""
        return self.ai_enabled

    def handle_event(self, event, race_state):
        """Handle clicks; does nothing at all while a race is running."""
        if race_state not in ["WAITING", "Game Over"]:
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if not self.rect.collidepoint(mx, my):
                return

            # 1. Lap Selection Row
            lap_y = self.rect.y + 34
            btn_w = (self.rect.width - 30) // 4
            for i in range(4):
                bx = self.rect.x + 12 + i * (btn_w + 2)
                if pygame.Rect(bx, lap_y, btn_w, 28).collidepoint(mx, my):
                    self.selected_lap_idx = i
                    return

            # 2. Toggle Switch Row (Only if AI toggle is enabled)
            if self.show_ai_toggle:
                row_y = self.rect.y + 74
                toggle_row_rect = pygame.Rect(self.rect.x + 12, row_y, self.rect.width - 24, 38)
                if toggle_row_rect.collidepoint(mx, my):
                    self.ai_enabled = not self.ai_enabled
                    return

    def draw(self, surface, race_state):
        """Draw the lap-target row, the AI toggle, and the lock hint."""
        # Panel Background
        pygame.draw.rect(surface, (22, 26, 35), self.rect, border_radius=8)
        pygame.draw.rect(surface, (45, 52, 65), self.rect, width=1, border_radius=8)

        # --- Section 1: Race Length / Laps ---
        title_surf = font_subtitle.render("RACE LENGTH / LAPS", True, (150, 165, 185))
        surface.blit(title_surf, (self.rect.x + 12, self.rect.y + 12))

        lap_y = self.rect.y + 32
        btn_w = (self.rect.width - 30) // 4
        for i, lbl in enumerate(["1L", "3L", "5L", "INF"]):
            bx = self.rect.x + 12 + i * (btn_w + 2)
            btn_rect = pygame.Rect(bx, lap_y, btn_w, 26)
            is_active = (i == self.selected_lap_idx)

            bg_col = (46, 204, 113) if is_active else (30, 36, 48)
            txt_col = (15, 20, 25) if is_active else (170, 180, 195)

            pygame.draw.rect(surface, bg_col, btn_rect, border_radius=4)
            if not is_active:
                pygame.draw.rect(surface, (55, 65, 80), btn_rect, width=1, border_radius=4)

            txt = font_main.render(lbl, True, txt_col)
            surface.blit(txt, txt.get_rect(center=btn_rect.center))

        # --- Section 2: AI Toggle Switch (Single Player only) ---
        if self.show_ai_toggle:
            target_anim = 1.0 if self.ai_enabled else 0.0
            self.switch_anim += (target_anim - self.switch_anim) * 0.35

            row_y = self.rect.y + 74
            start_x = self.rect.x + 12

            # Label
            lbl_surf = font_subtitle.render("TRAINED AI OPPONENT", True, (150, 165, 185))
            surface.blit(lbl_surf, (start_x, row_y + 8))

            # Pill Switch
            sw_w, sw_h = 38, 18
            sw_x = start_x + lbl_surf.get_width() + 20
            sw_y = row_y + 7
            sw_rect = pygame.Rect(sw_x, sw_y, sw_w, sw_h)

            r_col = int(40 + (46 - 40) * self.switch_anim)
            g_col = int(48 + (204 - 48) * self.switch_anim)
            b_col = int(62 + (113 - 62) * self.switch_anim)
            track_col = (r_col, g_col, b_col)

            pygame.draw.rect(surface, track_col, sw_rect, border_radius=sw_h // 2)
            pygame.draw.rect(surface, (65, 78, 95), sw_rect, width=1, border_radius=sw_h // 2)

            # Knob
            knob_radius = 6
            knob_min_x = sw_x + knob_radius + 3
            knob_max_x = sw_x + sw_w - knob_radius - 3
            knob_cur_x = knob_min_x + (knob_max_x - knob_min_x) * self.switch_anim
            knob_center = (int(knob_cur_x), sw_y + sw_h // 2)

            pygame.draw.circle(surface, (15, 20, 25), (knob_center[0] + 1, knob_center[1] + 1), knob_radius)
            pygame.draw.circle(surface, (245, 248, 250), knob_center, knob_radius)

            # Status text
            status_txt = "ON" if self.ai_enabled else "OFF"
            status_col = (46, 204, 113) if self.ai_enabled else (140, 150, 165)
            stat_surf = font_main.render(status_txt, True, status_col)
            surface.blit(stat_surf, (sw_x + sw_w + 8, row_y + 8))

            if race_state not in ["WAITING", "Game Over"]:
                lock_hint = font_subtitle.render("Modifiers locked in-race", True, (110, 120, 135))
                surface.blit(lock_hint, (start_x, self.rect.y + 115))

class TrackCarousel:
    """Refined, scrollable card carousel for selecting circuits."""
    def __init__(self, x, y, width, height, tracks):
        """Build the card strip: geometry, nav arrows, thumbnail cache."""
        self.rect = pygame.Rect(x, y, width, height)
        self.tracks = tracks
        self.selected_index = 0
        self.scroll_offset = 0.0
        self.target_offset = 0.0
        self.card_width = 340
        self.card_height = 430
        self.card_spacing = 25
        
        # Dedicated title font for carousel cards (cleaner & moderately scaled)
        self.card_title_font = pygame.font.SysFont("Consolas", 20, bold=True)
        
        # Navigation buttons placed at bottom corners
        btn_w, btn_h = 44, 38
        self.btn_left = pygame.Rect(x + 16, y + height - btn_h - 14, btn_w, btn_h)
        self.btn_right = pygame.Rect(x + width - btn_w - 16, y + height - btn_h - 14, btn_w, btn_h)

        self.is_dragging = False
        self.drag_start_x = 0
        self.drag_start_offset = 0
        self._preview_cache = {}

    def _get_cropped_preview(self, track, target_size):
        """Downscale a circuit into a card thumbnail (cached per track).

        The right-hand HUD strip is cut off first so the thumbnail shows
        the circuit and not the telemetry panel.
        """
        if track.id in self._preview_cache:
            return self._preview_cache[track.id]

        if hasattr(track, 'surface') and track.surface:
            surf_w = track.surface.get_width()
            surf_h = track.surface.get_height()
            
            hud_cutoff = max(600, surf_w - 380)
            crop_rect = pygame.Rect(0, 0, min(surf_w, hud_cutoff), surf_h)
            cropped_subsurface = track.surface.subsurface(crop_rect)

            scaled = pygame.transform.smoothscale(cropped_subsurface, target_size)
            self._preview_cache[track.id] = scaled
            return scaled
        return None

    def handle_event(self, event):
        """Arrows, mouse wheel and drag; True when the event was consumed."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if self.btn_left.collidepoint(event.pos):
                    self.set_index(self.selected_index - 1)
                    return True
                elif self.btn_right.collidepoint(event.pos):
                    self.set_index(self.selected_index + 1)
                    return True
                
                if self.rect.collidepoint(event.pos):
                    self.is_dragging = True
                    self.drag_start_x = event.pos[0]
                    self.drag_start_offset = self.scroll_offset

            elif event.button == 4:  # Wheel left
                self.set_index(self.selected_index - 1)
                return True
            elif event.button == 5:  # Wheel right
                self.set_index(self.selected_index + 1)
                return True

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and self.is_dragging:
                self.is_dragging = False
                total_card_w = self.card_width + self.card_spacing
                nearest_idx = round(-self.scroll_offset / total_card_w)
                self.set_index(nearest_idx)
                return True

        elif event.type == pygame.MOUSEMOTION:
            if self.is_dragging:
                dx = event.pos[0] - self.drag_start_x
                self.scroll_offset = self.drag_start_offset + dx

        return False

    def set_index(self, index):
        """Clamp to a valid track index and retarget the scroll offset."""
        self.selected_index = max(0, min(len(self.tracks) - 1, index))
        total_card_w = self.card_width + self.card_spacing
        self.target_offset = -self.selected_index * total_card_w

    def update(self):
        """Ease the scroll offset towards the selected card (no drag)."""
        if not self.is_dragging:
            self.scroll_offset += (self.target_offset - self.scroll_offset) * 0.22

    def draw(self, surface):
        """Draw the clipped card strip, the nav arrows and the page dots."""
        self.update()
        
        # Outer container card
        pygame.draw.rect(surface, (18, 23, 33), self.rect, border_radius=14)
        pygame.draw.rect(surface, COLOR_BORDER, self.rect, width=1, border_radius=14)

        clip_rect = surface.get_clip()
        surface.set_clip(self.rect.inflate(-6, -6))

        center_x = self.rect.x + self.rect.width // 2
        center_y = self.rect.y + self.rect.height // 2 - 24
        total_card_w = self.card_width + self.card_spacing

        for i, track in enumerate(self.tracks):
            card_center_x = center_x + self.scroll_offset + i * total_card_w
            card_rect = pygame.Rect(
                card_center_x - self.card_width // 2,
                center_y - self.card_height // 2,
                self.card_width,
                self.card_height
            )

            if card_rect.right < self.rect.left or card_rect.left > self.rect.right:
                continue

            is_selected = (i == self.selected_index)
            
            # Card styling
            bg_color = (26, 34, 48) if is_selected else (19, 25, 36)
            border_color = (46, 204, 113) if is_selected else (45, 55, 75)
            border_width = 2 if is_selected else 1

            pygame.draw.rect(surface, bg_color, card_rect, border_radius=12)
            pygame.draw.rect(surface, border_color, card_rect, width=border_width, border_radius=12)

            # Map Thumbnail Frame
            preview_rect = pygame.Rect(card_rect.x + 14, card_rect.y + 14, self.card_width - 28, 215)
            pygame.draw.rect(surface, (11, 15, 22), preview_rect, border_radius=8)
            pygame.draw.rect(surface, (38, 48, 65), preview_rect, width=1, border_radius=8)

            cropped_map = self._get_cropped_preview(track, (preview_rect.width - 6, preview_rect.height - 6))
            if cropped_map:
                surface.blit(cropped_map, (preview_rect.x + 3, preview_rect.y + 3))

            # Circuit Name (Moderately scaled down & Middle Aligned)
            clean_name = re.sub(r"^\s*\d+[\.\-\:]\s*", "", track.name)
            name_surf = self.card_title_font.render(clean_name, True, (255, 255, 255) if is_selected else (205, 215, 230))
            name_rect = name_surf.get_rect(center=(card_rect.centerx, card_rect.y + 248))
            surface.blit(name_surf, name_rect)

            # Description (Middle Aligned & Wrapped)
            desc_color = (46, 204, 113) if is_selected else (135, 148, 165)
            self._draw_multiline_text(
                surface, track.description,
                center_x=card_rect.centerx,
                start_y=card_rect.y + 274,
                max_width=self.card_width - 36,
                font=font_subtitle, color=desc_color, line_spacing=18
            )

            # Active Map Pill Button
            badge_rect = pygame.Rect(card_rect.centerx - 65, card_rect.bottom - 42, 130, 28)
            if is_selected:
                pygame.draw.rect(surface, (46, 204, 113), badge_rect, border_radius=6)
                badge_text = font_main.render("ACTIVE MAP", True, (10, 30, 20))
            else:
                pygame.draw.rect(surface, (28, 36, 48), badge_rect, border_radius=6)
                badge_text = font_main.render("SELECT", True, (110, 122, 138))
            surface.blit(badge_text, badge_text.get_rect(center=badge_rect.center))

        surface.set_clip(clip_rect)

        # Carousel Arrows
        self._draw_nav_btn(surface, self.btn_left, "<", self.selected_index > 0)
        self._draw_nav_btn(surface, self.btn_right, ">", self.selected_index < len(self.tracks) - 1)

        # Pagination Dots
        dot_spacing = 16
        total_dots_w = (len(self.tracks) - 1) * dot_spacing
        dots_start_x = self.rect.centerx - total_dots_w // 2
        dots_y = self.rect.bottom - 24

        for idx in range(len(self.tracks)):
            color = (46, 204, 113) if idx == self.selected_index else (55, 68, 88)
            radius = 5 if idx == self.selected_index else 3
            pygame.draw.circle(surface, color, (dots_start_x + idx * dot_spacing, dots_y), radius)

    def _draw_multiline_text(self, surface, text, center_x, start_y, max_width, font, color, line_spacing):
        """Greedy word wrap, centred, hard-capped at three lines."""
        words = text.split(' ')
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            if font.size(test_line)[0] <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))

        for i, line in enumerate(lines[:3]):
            line_surf = font.render(line, True, color)
            line_rect = line_surf.get_rect(center=(center_x, start_y + i * line_spacing))
            surface.blit(line_surf, line_rect)

    def _draw_nav_btn(self, surface, rect, text, enabled):
        """One carousel arrow; greyed out when it cannot move any further."""
        mouse_pos = pygame.mouse.get_pos()
        is_hover = rect.collidepoint(mouse_pos) and enabled

        bg = (38, 50, 70) if is_hover else ((30, 40, 56) if enabled else (20, 26, 36))
        border = (52, 152, 219) if enabled else (40, 48, 60)
        text_color = (255, 255, 255) if enabled else (70, 80, 95)
        
        pygame.draw.rect(surface, bg, rect, border_radius=6)
        pygame.draw.rect(surface, border, rect, width=1, border_radius=6)
        txt_surf = font_main.render(text, True, text_color)
        surface.blit(txt_surf, txt_surf.get_rect(center=rect.center))


def draw_hud_panel(title, lines):
    """Draws full-height right-hand telemetry HUD panel with centered header and bottom circuit badge."""
    margin = 20
    panel_w = 360
    panel_x = SCREEN_WIDTH - panel_w - margin
    panel_y = margin
    panel_h = SCREEN_HEIGHT - 2 * margin

    pygame.draw.rect(screen, COLOR_PANEL_BG, (panel_x, panel_y, panel_w, panel_h), border_radius=10)
    pygame.draw.rect(screen, COLOR_BORDER, (panel_x, panel_y, panel_w, panel_h), width=1, border_radius=10)

    circuit_name = ""
    mode_name = title
    match = re.search(r"\((.*?)\)", title)
    if match:
        circuit_name = match.group(1)
        circuit_name = re.sub(r"^\s*\d+[\.\-\:]\s*", "", circuit_name)
        mode_name = re.sub(r"\s*\(.*?\)", "", title).strip()

    title_surf = font_title.render(mode_name, True, (46, 204, 113))
    title_rect = title_surf.get_rect(center=(panel_x + panel_w // 2, panel_y + 25))
    screen.blit(title_surf, title_rect)

    pygame.draw.line(screen, COLOR_BORDER, (panel_x + 16, panel_y + 46), (panel_x + panel_w - 16, panel_y + 46), 1)

    curr_y = panel_y + 60
    for line in lines:
        if line == "":
            curr_y += 10
            continue
            
        if line.startswith("["):
            color = (52, 152, 219)
        else:
            color = COLOR_TEXT

        line_surf = font_main.render(line, True, color)
        screen.blit(line_surf, (panel_x + 16, curr_y))
        curr_y += 24

    if circuit_name:
        badge_y = panel_y + panel_h - 60
        pygame.draw.line(screen, COLOR_BORDER, (panel_x + 16, badge_y - 12), (panel_x + panel_w - 16, badge_y - 12), 1)

        track_lbl = font_subtitle.render("CURRENT CIRCUIT", True, (135, 148, 165))
        track_lbl_rect = track_lbl.get_rect(center=(panel_x + panel_w // 2, badge_y + 2))
        screen.blit(track_lbl, track_lbl_rect)

        track_name_surf = font_title.render(circuit_name, True, (241, 196, 15))
        track_name_rect = track_name_surf.get_rect(center=(panel_x + panel_w // 2, badge_y + 26))
        screen.blit(track_name_surf, track_name_rect)


def draw_countdown_overlay(state, timer, center):
    """Draws balanced medium-large prompt and oversized 'READY'/'GO!' countdown."""
    if state == "WAITING":
        msg = "PRESS [SPACE] TO START RACE"
        prompt_font = pygame.font.SysFont("Consolas", 20, bold=True)
        surf = prompt_font.render(msg, True, (241, 196, 15))
        
        pad_x, pad_y = 20, 10
        badge_rect = pygame.Rect(
            center[0] - surf.get_width() // 2 - pad_x,
            center[1] - surf.get_height() // 2 - pad_y,
            surf.get_width() + pad_x * 2,
            surf.get_height() + pad_y * 2
        )
        
        pygame.draw.rect(screen, (12, 16, 24), badge_rect, border_radius=8)
        pygame.draw.rect(screen, (52, 73, 94), badge_rect, width=2, border_radius=8)
        screen.blit(surf, surf.get_rect(center=badge_rect.center))
        return state

    if state == "COUNTDOWN":
        elapsed = time.time() - timer
        countdown_font = pygame.font.SysFont("Arial", 76, bold=True)
        
        if elapsed < 0.5:
            text = "READY"
            color = (241, 196, 15)
        elif elapsed < 1.0:
            text = "GO!"
            color = (46, 204, 113)
        else:
            return "RACING"

        surf = countdown_font.render(text, True, color)
        rect = surf.get_rect(center=center)
        screen.blit(surf, rect)
        return state

    return state


def draw_confirm_reset_dialog(center):
    """Centred modal: [R] restart the race, [SPACE] resume it."""
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    screen.blit(overlay, (0, 0))

    box_w, box_h = 440, 140
    box_rect = pygame.Rect(center[0] - box_w // 2, center[1] - box_h // 2, box_w, box_h)
    pygame.draw.rect(screen, COLOR_PANEL_BG, box_rect, border_radius=10)
    pygame.draw.rect(screen, (231, 76, 60), box_rect, width=2, border_radius=10)

    title_surf = font_title.render("RESTART RACE?", True, (231, 76, 60))
    sub1_surf = font_main.render("[R] Confirm Restart", True, COLOR_TEXT)
    sub2_surf = font_main.render("[SPACE] Resume Race", True, (46, 204, 113))

    screen.blit(title_surf, title_surf.get_rect(center=(center[0], center[1] - 30)))
    screen.blit(sub1_surf, sub1_surf.get_rect(center=(center[0], center[1] + 10)))
    screen.blit(sub2_surf, sub2_surf.get_rect(center=(center[0], center[1] + 35)))


class NeuralNetVisualizer:
    """Cyberpunk / Sci-fi styled Neural Network Visualizer."""
    def __init__(self, neat_config):
        """Cache the node labels and the two small badge fonts."""
        self.neat_config = neat_config
        self.input_labels = ["-90°", "-60°", "-30°", " 0° ", "+30°", "+60°", "+90°"]
        self.output_labels = ["Steer L", "Steer R"]
        self.tag_font = pygame.font.SysFont("Consolas", 12, bold=True)
        self.mini_font = pygame.font.SysFont("Consolas", 10, bold=True)

    def render(self, genome, surface, x, y, width, height):
        """Draw the leader's genome: inputs | hidden | outputs, weights as edges.

        Green edges are positive weights, red negative, and the line
        thickness scales with weight magnitude -- the picture of what the
        network has learned so far.
        """
        pygame.draw.rect(surface, (15, 19, 27), (x, y, width, height), border_radius=8)
        pygame.draw.rect(surface, (35, 45, 60), (x, y, width, height), width=1, border_radius=8)

        pygame.draw.line(surface, (24, 30, 42), (x + 75, y + 10), (x + 75, y + height - 10), 1)
        pygame.draw.line(surface, (24, 30, 42), (x + width // 2, y + 10), (x + width // 2, y + height - 10), 1)
        pygame.draw.line(surface, (24, 30, 42), (x + width - 75, y + 10), (x + width - 75, y + height - 10), 1)

        num_inputs = self.neat_config.genome_config.num_inputs
        num_outputs = self.neat_config.genome_config.num_outputs

        input_keys = [-i - 1 for i in range(num_inputs)]
        output_keys = [i for i in range(num_outputs)]

        positions = {}
        for i, k in enumerate(input_keys):
            nx = x + 75
            ny = y + int((i + 1) * (height / (num_inputs + 1)))
            positions[k] = (nx, ny)

        for i, k in enumerate(output_keys):
            nx = x + width - 75
            ny = y + int((i + 1) * (height / (num_outputs + 1)))
            positions[k] = (nx, ny)

        hidden_nodes = [k for k in genome.nodes.keys() if k not in output_keys]
        for i, k in enumerate(hidden_nodes):
            nx = x + width // 2
            ny = y + int((i + 1) * (height / (len(hidden_nodes) + 1)))
            positions[k] = (nx, ny)

        for cg in genome.connections.values():
            if not cg.enabled:
                continue
            in_node, out_node = cg.key
            if in_node in positions and out_node in positions:
                p1 = positions[in_node]
                p2 = positions[out_node]
                weight_color = (46, 204, 113) if cg.weight > 0 else (231, 76, 60)
                thickness = max(1, min(4, int(abs(cg.weight * 1.5))))
                pygame.draw.line(surface, weight_color, p1, p2, thickness)

        for k, (nx, ny) in positions.items():
            if k in input_keys:
                idx = -k - 1
                lbl_text = self.input_labels[idx] if idx < len(self.input_labels) else f"In{idx+1}"
                
                badge_w, badge_h = 44, 20
                badge_rect = pygame.Rect(nx - badge_w - 12, ny - badge_h // 2, badge_w, badge_h)
                pygame.draw.rect(surface, (20, 32, 48), badge_rect, border_radius=4)
                pygame.draw.rect(surface, (41, 128, 185), badge_rect, width=1, border_radius=4)
                
                txt_surf = self.tag_font.render(lbl_text, True, (0, 210, 255))
                surface.blit(txt_surf, txt_surf.get_rect(center=badge_rect.center))
                
                self._draw_glowing_node(surface, nx, ny, (0, 180, 255), (0, 230, 255))

            elif k in output_keys:
                lbl_text = self.output_labels[k] if k < len(self.output_labels) else f"Out{k+1}"
                
                badge_w, badge_h = 58, 20
                badge_rect = pygame.Rect(nx + 12, ny - badge_h // 2, badge_w, badge_h)
                pygame.draw.rect(surface, (38, 30, 15), badge_rect, border_radius=4)
                pygame.draw.rect(surface, (241, 196, 15), badge_rect, width=1, border_radius=4)
                
                txt_surf = self.tag_font.render(lbl_text, True, (243, 156, 18))
                surface.blit(txt_surf, txt_surf.get_rect(center=badge_rect.center))
                
                self._draw_glowing_node(surface, nx, ny, (241, 196, 15), (255, 230, 100))

            else:
                h_idx = hidden_nodes.index(k) + 1
                h_badge = pygame.Rect(nx - 11, ny - 18, 22, 12)
                pygame.draw.rect(surface, (30, 20, 42), h_badge, border_radius=3)
                pygame.draw.rect(surface, (155, 89, 182), h_badge, width=1, border_radius=3)
                h_txt = self.mini_font.render(f"H{h_idx}", True, (210, 150, 240))
                surface.blit(h_txt, h_txt.get_rect(center=h_badge.center))

                self._draw_glowing_node(surface, nx, ny, (155, 89, 182), (210, 150, 240))

    def _draw_glowing_node(self, surface, nx, ny, base_color, core_color):
        """Three concentric circles: dark halo, body, hot core."""
        halo_color = (base_color[0] // 3, base_color[1] // 3, base_color[2] // 3)
        pygame.draw.circle(surface, halo_color, (nx, ny), 11)
        pygame.draw.circle(surface, base_color, (nx, ny), 7)
        pygame.draw.circle(surface, core_color, (nx, ny), 3)


