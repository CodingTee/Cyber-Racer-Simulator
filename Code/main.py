# =============================================================================
# main.py -- entry point, main menu and the three race modes.
#
# Every run_mode_* function is a self-contained loop: it builds its cars,
# runs the WAITING -> COUNTDOWN -> RACING -> Game Over state machine, draws
# the HUD and returns to the menu on ESC. All race sound cues go through
# update_race_audio, which each mode calls exactly once per frame.
# =============================================================================
import os
import sys
import time
import math
import pygame

from settings import (
    screen, clock, FPS, SCREEN_WIDTH, SCREEN_HEIGHT,
    COLOR_BG, COLOR_PANEL_BG, COLOR_BORDER, COLOR_TEXT,
    font_title, font_subtitle, font_main, font_transition
)
from tracks import get_all_tracks
from car import Car
from model_io import load_trained_model, save_trained_model
from ai_evolution import run_mode_ai_evolution
import audio
from ui import (
    Button, TrackCarousel, ModifierBoard, draw_hud_panel,
    draw_countdown_overlay, draw_confirm_reset_dialog
)

# id(car) -> was it alive last frame? Keyed by object so it self-heals on
# respawn (no per-mode bookkeeping to forget), and keyed here (not on the car)
# so AI Evolution, which drives thousands of deaths, is never touched.
_SFX_WAS_ALIVE = {}


# ---- Sound cues: one explosion the frame a car stops being alive ----
def play_crash_sfx(cars):
    """Play the explosion on the frame a car stops being alive."""
    for car in cars:
        if car is None:
            continue
        prev = _SFX_WAS_ALIVE.get(id(car), True)
        if prev and not car.is_alive:
            audio.play("crash")
        _SFX_WAS_ALIVE[id(car)] = car.is_alive


# last seen race state, so the starter fires exactly once on the frame the
# race begins -- i.e. AFTER the GO! voice has finished, not on top of it.
_SFX_LAST_STATE = None


def update_race_audio(state, winner_text=""):
    """Fire the starter on the green light, and the win sting on a finish.

    Called once per frame from each race mode. Both cues are one-shots, so
    this only acts on the state edge. `winner_text` is the HUD banner; only
    a real win ("WINS") earns the fanfare -- a crash-out ends on the
    explosion instead.
    """
    global _SFX_LAST_STATE
    if state == "RACING" and _SFX_LAST_STATE != "RACING":
        audio.ignite()
    if (state == "Game Over" and _SFX_LAST_STATE != "Game Over"
            and "WINS" in winner_text):
        audio.play("victory")
    _SFX_LAST_STATE = state

def reset_race_global(cars_list, track):
    """Send every car back to its start slot (respawn / restart)."""
    for car in cars_list:
        if car:
            car.reset(track)

def handle_standard_events(state, cars_list, track):
    """Shared key handling for the simpler modes; returns the next state.

    The returned float is the countdown timer to use (0.0 unless SPACE just
    started a countdown). ESC is handled by the caller, not here.
    """
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "MENU_EXIT", 0.0
            if state == "CONFIRM_RESET":
                if event.key == pygame.K_SPACE:
                    return "RACING", 0.0
                elif event.key == pygame.K_r:
                    reset_race_global(cars_list, track)
                    return "RESET", 0.0
            elif state == "RACING":
                if event.key == pygame.K_r:
                    return "CONFIRM_RESET", 0.0
            else:
                if event.key == pygame.K_r:
                    reset_race_global(cars_list, track)
                    return "RESET", 0.0
            
            if event.key == pygame.K_SPACE and state == "WAITING":
                return "COUNTDOWN", time.time()
            if event.key == pygame.K_SPACE and state == "Game Over":
                reset_race_global(cars_list, track)
                return "RESET", 0.0
                
    return state, 0.0

def get_display_time(state, race_start_time, final_race_time):
    """Elapsed time as a string; freezes at the final value once it is over."""
    if state == "Game Over":
        return f"{final_race_time:.1f}s"
    if race_start_time > 0:
        return f"{time.time() - race_start_time:.1f}s"
    return "0.0s"

def get_car_lap_count(car, track):
    """Accurately computes continuous lap progress for both polar and spline tracks."""
    if track.id == "ring_gp":
        return max(0.0, car.total_angle_traversed / (2 * math.pi))
    elif track.id == "figure8_gp":
        # Event-based laps: one gate-armed start-line pass == one full figure-8
        return track.get_lap_count(car)
    elif hasattr(track, 'circuit_path') and len(track.circuit_path) > 0:
        return max(0.0, car.checkpoints_passed / float(len(track.circuit_path)))
    elif hasattr(track, 'track_length') and track.track_length > 0:
        return max(0.0, car.total_distance / track.track_length)
    return max(0.0, car.total_distance / 2200.0)

# ------------------------------------------------------------------------------
# Mode 1 -- single player (Red) vs the trained NEAT champion (Yellow)
# ------------------------------------------------------------------------------
def run_mode_single_player(track):
    """Player vs AI: the AI is optional and driven by the saved genome."""
    trained_net, genome, config = load_trained_model(track.model_filename)
    p1 = Car(sprite_type="red", spawn_index=0, name="P1 (Red F1)")
    ai_car = Car(sprite_type="yellow", spawn_index=1, name="AI Opponent (Yellow)")
    
    # Modifier board placed above circuit title
    panel_x, panel_w = SCREEN_WIDTH - 380, 360
    modifier_board = ModifierBoard(panel_x + 10, 540, panel_w - 20, 136)

    reset_race_global([p1, ai_car], track)
    state = "WAITING"
    countdown_timer = race_start_time = final_race_time = 0.0
    go_played = False
    winner_text = ""

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            
            modifier_board.handle_event(event, state)

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    audio.stop_all()
                    return
                if state == "CONFIRM_RESET":
                    if event.key == pygame.K_SPACE:
                        state = "RACING"
                    elif event.key == pygame.K_r:
                        reset_race_global([p1, ai_car], track)
                        state = "WAITING"
                        countdown_timer = race_start_time = final_race_time = 0.0
                        winner_text = ""
                elif state == "RACING":
                    if event.key == pygame.K_r:
                        state = "CONFIRM_RESET"
                else:
                    if event.key == pygame.K_r:
                        reset_race_global([p1, ai_car], track)
                        state = "WAITING"
                        countdown_timer = race_start_time = final_race_time = 0.0
                        winner_text = ""
                
                if event.key == pygame.K_m:
                    audio.toggle()
                if event.key == pygame.K_SPACE and state == "WAITING":
                    state = "COUNTDOWN"
                    countdown_timer = time.time()
                    audio.play("ready")
                    go_played = False
                elif event.key == pygame.K_SPACE and state == "Game Over":
                    reset_race_global([p1, ai_car], track)
                    state = "WAITING"
                    countdown_timer = race_start_time = final_race_time = 0.0
                    winner_text = ""

# Re-read the board every frame so the HUD can never disagree with the sim,
# even though the board only accepts clicks between races.
        ai_active = modifier_board.is_ai_enabled()
        max_laps = modifier_board.get_max_laps()

        screen.blit(track.surface, (0, 0))
        p1.draw(screen, show_rays=False)
        if ai_active:
            ai_car.draw(screen, show_rays=False)

        # Simulation & Racing loop
        if state == "RACING":
            if race_start_time == 0.0:
                race_start_time = time.time()

            # Player inputs
            keys = pygame.key.get_pressed()
            steer_p1 = (1.0 if keys[pygame.K_RIGHT] or keys[pygame.K_d] else 0.0) - (1.0 if keys[pygame.K_LEFT] or keys[pygame.K_a] else 0.0)
            p1.update(steer_p1, track)

            # AI decision
            if ai_active and trained_net and ai_car.is_alive:
                outputs = trained_net.activate(ai_car.sensor_readings)
                ai_car.update(outputs[1] - outputs[0], track)

            # Lap counting calculations
            p1_laps_float = get_car_lap_count(p1, track)
            ai_laps_float = get_car_lap_count(ai_car, track)

            # Check win / game over condition
            if p1_laps_float >= max_laps:
                state = "Game Over"
                winner_text = "P1 (RED) WINS!"
                final_race_time = time.time() - race_start_time
            elif ai_active and ai_laps_float >= max_laps:
                state = "Game Over"
                winner_text = "AI (YELLOW) WINS!"
                final_race_time = time.time() - race_start_time
            elif not p1.is_alive and (not ai_active or not ai_car.is_alive):
                state = "Game Over"
                winner_text = "RACE TERMINATED (CRASH)"
                final_race_time = time.time() - race_start_time

            play_crash_sfx([p1, ai_car])

        # "GO!" fires halfway through the countdown (see draw_countdown_overlay)
        if state == "COUNTDOWN" and not go_played and time.time() - countdown_timer >= 0.5:
            audio.play("go")
            go_played = True

        overlay_anchor = getattr(track, 'overlay_anchor', track.center)
        if state in ["WAITING", "COUNTDOWN"]:
            state = draw_countdown_overlay(state, countdown_timer, overlay_anchor)
        elif state == "CONFIRM_RESET":
            draw_confirm_reset_dialog(overlay_anchor)
        update_race_audio(state, winner_text)


        # 1. Lap Counter formatting (accurate for all circuits, same logic as win check)
        # Pre-start (WAITING/COUNTDOWN) the HUD shows zeroes and does NOT call
        # the scoring code: figure-8's compute_fitness advances the checkpoint
        # tracker as a side effect, so calling it before the race would score
        # distance the car never drove.
        pre_race = state in ("WAITING", "COUNTDOWN")
        p1_laps_float = 0.0 if pre_race else get_car_lap_count(p1, track)
        ai_laps_float = 0.0 if pre_race else get_car_lap_count(ai_car, track)
        lap_target_str = modifier_board.lap_labels[modifier_board.selected_lap_idx]

        # 2. Fitness evaluation (same formula as training)
        p1_fitness = 0.0 if pre_race else track.compute_fitness(p1)
        ai_fitness = 0.0 if pre_race else track.compute_fitness(ai_car)

        hud_lines = [
            f"P1 (Red)   : {'ALIVE' if p1.is_alive else 'CRASHED'}",
            f"P1 Lap     : {p1_laps_float:.2f} / {lap_target_str}",
            f"P1 Fitness : {p1_fitness:.1f}", "",
            f"AI Bot     : {'ENABLED' if ai_active else 'DISABLED'}",
            f"AI Status  : {'ALIVE' if ai_car.is_alive else 'CRASHED'}" if ai_active else "AI Status  : OFF",
            f"AI Lap     : {ai_laps_float:.2f} / {lap_target_str}" if ai_active else "AI Lap     : --",
            f"AI Fitness : {ai_fitness:.1f}" if ai_active else "AI Fitness : --", "",
            f"Time Elapse: {get_display_time(state, race_start_time, final_race_time)}",
            f"Status     : {winner_text if state == 'Game Over' and winner_text else state}", "",
            "[SPACE] Start / Reset",
            "[R]     Restart Race",
            "[M]     Mute / Unmute",
            "[ESC]   Return to Menu"
        ]
        draw_hud_panel(f"SINGLE PLAYER ({track.name})", hud_lines)
        modifier_board.draw(screen, state)

        pygame.display.flip()
        clock.tick(FPS)

# ------------------------------------------------------------------------------
# Mode 2 -- two local players: P1 arrows (Red) vs P2 WASD (Yellow)
# ------------------------------------------------------------------------------
def run_mode_two_players(track):
    """Local PvP: no AI, same lap target, first to reach it wins."""
    p1 = Car(sprite_type="red", spawn_index=0, name="P1 (Red F1)")
    p2 = Car(sprite_type="yellow", spawn_index=1, name="P2 (Yellow F1)")
    
    # Modifier board for Multiplayer (without AI toggle, show_ai_toggle=False)
    panel_x, panel_w = SCREEN_WIDTH - 380, 360
    modifier_board = ModifierBoard(panel_x + 10, 580, panel_w - 20, show_ai_toggle=False)

    reset_race_global([p1, p2], track)
    state = "WAITING"
    countdown_timer = race_start_time = final_race_time = 0.0
    go_played = False
    winner_text = ""

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            modifier_board.handle_event(event, state)

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    audio.stop_all()
                    return
                if state == "CONFIRM_RESET":
                    if event.key == pygame.K_SPACE:
                        state = "RACING"
                    elif event.key == pygame.K_r:
                        reset_race_global([p1, p2], track)
                        state = "WAITING"
                        countdown_timer = race_start_time = final_race_time = 0.0
                        winner_text = ""
                elif state == "RACING":
                    if event.key == pygame.K_r:
                        state = "CONFIRM_RESET"
                else:
                    if event.key == pygame.K_r:
                        reset_race_global([p1, p2], track)
                        state = "WAITING"
                        countdown_timer = race_start_time = final_race_time = 0.0
                        winner_text = ""

                if event.key == pygame.K_m:
                    audio.toggle()
                if event.key == pygame.K_SPACE and state == "WAITING":
                    state = "COUNTDOWN"
                    countdown_timer = time.time()
                    audio.play("ready")
                    go_played = False
                elif event.key == pygame.K_SPACE and state == "Game Over":
                    reset_race_global([p1, p2], track)
                    state = "WAITING"
                    countdown_timer = race_start_time = final_race_time = 0.0
                    winner_text = ""

        max_laps = modifier_board.get_max_laps()

        screen.blit(track.surface, (0, 0))
        p1.draw(screen, show_rays=False)
        p2.draw(screen, show_rays=False)

        if state == "RACING":
            if race_start_time == 0.0:
                race_start_time = time.time()

            keys = pygame.key.get_pressed()
            # P1 Controls (Arrow Keys)
            steer_p1 = (1.0 if keys[pygame.K_RIGHT] else 0.0) - (1.0 if keys[pygame.K_LEFT] else 0.0)
            p1.update(steer_p1, track)

            # P2 Controls (WASD)
            steer_p2 = (1.0 if keys[pygame.K_d] else 0.0) - (1.0 if keys[pygame.K_a] else 0.0)
            p2.update(steer_p2, track)

            p1_laps_float = get_car_lap_count(p1, track)
            p2_laps_float = get_car_lap_count(p2, track)

            if p1_laps_float >= max_laps:
                state = "Game Over"
                winner_text = "P1 (RED) WINS!"
                final_race_time = time.time() - race_start_time
            elif p2_laps_float >= max_laps:
                state = "Game Over"
                winner_text = "P2 (YELLOW) WINS!"
                final_race_time = time.time() - race_start_time
            elif not p1.is_alive and not p2.is_alive:
                state = "Game Over"
                winner_text = "BOTH CARS CRASHED"
                final_race_time = time.time() - race_start_time

            play_crash_sfx([p1, p2])

        # "GO!" fires halfway through the countdown (see draw_countdown_overlay)
        if state == "COUNTDOWN" and not go_played and time.time() - countdown_timer >= 0.5:
            audio.play("go")
            go_played = True

        overlay_anchor = getattr(track, 'overlay_anchor', track.center)
        if state in ["WAITING", "COUNTDOWN"]:
            state = draw_countdown_overlay(state, countdown_timer, overlay_anchor)
        elif state == "CONFIRM_RESET":
            draw_confirm_reset_dialog(overlay_anchor)
        update_race_audio(state, winner_text)


        # Same pre-start gate as single player: no scoring calls before RACING.
        pre_race = state in ("WAITING", "COUNTDOWN")
        p1_laps_float = 0.0 if pre_race else get_car_lap_count(p1, track)
        p2_laps_float = 0.0 if pre_race else get_car_lap_count(p2, track)
        lap_target_str = modifier_board.lap_labels[modifier_board.selected_lap_idx]

        hud_lines = [
            f"P1 (Red/Arrows)  : {'ALIVE' if p1.is_alive else 'CRASHED'}",
            f"P1 Lap           : {p1_laps_float:.2f} / {lap_target_str}",
            f"P1 Fitness       : {0.0 if pre_race else track.compute_fitness(p1):.1f}", "",
            f"P2 (Yellow/WASD) : {'ALIVE' if p2.is_alive else 'CRASHED'}",
            f"P2 Lap           : {p2_laps_float:.2f} / {lap_target_str}",
            f"P2 Fitness       : {0.0 if pre_race else track.compute_fitness(p2):.1f}", "",
            f"Time Elapse      : {get_display_time(state, race_start_time, final_race_time)}",
            f"Status           : {winner_text if state == 'Game Over' and winner_text else state}", "",
            "[SPACE] Start / Reset",
            "[R]     Restart Race",
            "[M]     Mute / Unmute",
            "[ESC]   Return to Menu"
        ]
        draw_hud_panel(f"TWO PLAYERS ({track.name})", hud_lines)
        modifier_board.draw(screen, state)

        pygame.display.flip()
        clock.tick(FPS)

# ------------------------------------------------------------------------------
# Mode 3 -- training camp: solo practice with a LiDAR visibility toggle
# ------------------------------------------------------------------------------
def run_mode_training_camp(track):
    """Solo practice: no opponent, no lap target, ends on the first crash."""
    player = Car(sprite_type="red", spawn_index=0, name="Player (Red F1)")
    reset_race_global([player], track)
    state = "WAITING"
    countdown_timer = race_start_time = final_race_time = 0.0
    go_played = False
    show_support_lines = True

    # Reusable small panel for the LiDAR toggle
    panel_x, panel_w = SCREEN_WIDTH - 380, 360
    toggle_box_rect = pygame.Rect(panel_x + 10, 580, panel_w - 20, 48)
    switch_anim = 1.0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    audio.stop_all()
                    return
                if event.key == pygame.K_t:
                    show_support_lines = not show_support_lines
                if state == "CONFIRM_RESET":
                    if event.key == pygame.K_SPACE:
                        state = "RACING"
                    elif event.key == pygame.K_r:
                        reset_race_global([player], track)
                        state = "WAITING"
                        countdown_timer = race_start_time = final_race_time = 0.0
                elif state == "RACING":
                    if event.key == pygame.K_r:
                        state = "CONFIRM_RESET"
                else:
                    if event.key == pygame.K_r:
                        reset_race_global([player], track)
                        state = "WAITING"
                        countdown_timer = race_start_time = final_race_time = 0.0

                if event.key == pygame.K_m:
                    audio.toggle()
                if event.key == pygame.K_SPACE and state == "WAITING":
                    state = "COUNTDOWN"
                    countdown_timer = time.time()
                    audio.play("ready")
                    go_played = False
                elif event.key == pygame.K_SPACE and state == "Game Over":
                    reset_race_global([player], track)
                    state = "WAITING"
                    countdown_timer = race_start_time = final_race_time = 0.0

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if toggle_box_rect.collidepoint(event.pos):
                    show_support_lines = not show_support_lines

        screen.blit(track.surface, (0, 0))
        player.draw(screen, show_rays=show_support_lines)

        if state == "RACING":
            if race_start_time == 0.0:
                race_start_time = time.time()
            keys = pygame.key.get_pressed()
            steer = (1.0 if keys[pygame.K_RIGHT] or keys[pygame.K_d] else 0.0) - (1.0 if keys[pygame.K_LEFT] or keys[pygame.K_a] else 0.0)
            player.update(steer, track)
            play_crash_sfx([player])
            if not player.is_alive:
                state = "Game Over"
                final_race_time = time.time() - race_start_time

        # "GO!" fires halfway through the countdown (see draw_countdown_overlay)
        if state == "COUNTDOWN" and not go_played and time.time() - countdown_timer >= 0.5:
            audio.play("go")
            go_played = True

        overlay_anchor = getattr(track, 'overlay_anchor', track.center)
        if state in ["WAITING", "COUNTDOWN"]:
            state = draw_countdown_overlay(state, countdown_timer, overlay_anchor)
        elif state == "CONFIRM_RESET":
            draw_confirm_reset_dialog(overlay_anchor)
        update_race_audio(state)


        # Same pre-start gate as single player: no scoring calls before RACING.
        pre_race = state in ("WAITING", "COUNTDOWN")
        player_laps = 0.0 if pre_race else get_car_lap_count(player, track)
        player_fitness = 0.0 if pre_race else track.compute_fitness(player)

        draw_hud_panel(f"TRAINING CAMP ({track.name})", [
            f"Car State  : {'DRIVING' if player.is_alive else 'CRASHED'}",
            f"Lap Count  : {player_laps:.2f} Laps",
            f"Fitness    : {player_fitness:.1f}", "",
            f"LiDAR Lines: {'ENABLED' if show_support_lines else 'DISABLED'}",
            f"Time Elapse: {get_display_time(state, race_start_time, final_race_time)}",
            f"Status     : {state}", "",
            "[SPACE] Start / Reset (Game Over)",
            "[R]     Respawn Line",
            "[M]     Mute / Unmute",
            "[T]     Toggle Support Lines",
            "[ESC]   Return to Menu"
        ])

        # --- Render Clean Toggle Panel with Vertical Accent Strip ---
        target_anim = 1.0 if show_support_lines else 0.0
        switch_anim += (target_anim - switch_anim) * 0.35

        # 1. Base Box
        pygame.draw.rect(screen, (22, 26, 35), toggle_box_rect, border_radius=8)
        pygame.draw.rect(screen, (45, 52, 65), toggle_box_rect, width=1, border_radius=8)

        # 2. Left Vertical Accent Strip (Dynamic Green / Muted)
        strip_color = (46, 204, 113) if show_support_lines else (70, 80, 95)
        strip_rect = pygame.Rect(toggle_box_rect.x, toggle_box_rect.y + 6, 4, toggle_box_rect.height - 12)
        pygame.draw.rect(screen, strip_color, strip_rect, border_top_left_radius=2, border_bottom_left_radius=2)

        # 3. Text Label
        lbl_surf = font_subtitle.render("LIDAR SENSORS [T]", True, (150, 165, 185))
        screen.blit(lbl_surf, (toggle_box_rect.x + 18, toggle_box_rect.y + 16))

        # 4. Pill Switch
        sw_w, sw_h = 38, 18
        sw_x = toggle_box_rect.x + lbl_surf.get_width() + 38
        sw_y = toggle_box_rect.y + 15
        sw_rect = pygame.Rect(sw_x, sw_y, sw_w, sw_h)

        r_col = int(40 + (46 - 40) * switch_anim)
        g_col = int(48 + (204 - 48) * switch_anim)
        b_col = int(62 + (113 - 62) * switch_anim)
        pygame.draw.rect(screen, (r_col, g_col, b_col), sw_rect, border_radius=sw_h // 2)
        pygame.draw.rect(screen, (65, 78, 95), sw_rect, width=1, border_radius=sw_h // 2)

        # 5. Sliding Knob
        knob_r = 6
        k_min = sw_x + knob_r + 3
        k_max = sw_x + sw_w - knob_r - 3
        k_cur = k_min + (k_max - k_min) * switch_anim
        knob_center = (int(k_cur), sw_y + sw_h // 2)
        pygame.draw.circle(screen, (15, 20, 25), (knob_center[0] + 1, knob_center[1] + 1), knob_r)
        pygame.draw.circle(screen, (245, 248, 250), knob_center, knob_r)

        # 6. Status Text
        stat_txt = "ON" if show_support_lines else "OFF"
        stat_col = (46, 204, 113) if show_support_lines else (140, 150, 165)
        stat_surf = font_main.render(stat_txt, True, stat_col)
        screen.blit(stat_surf, (sw_x + sw_w + 8, toggle_box_rect.y + 16))

        pygame.display.flip()
        clock.tick(FPS)

# ------------------------------------------------------------------------------
# Main menu -- circuit carousel on the left, mode buttons on the right
# ------------------------------------------------------------------------------
def main_menu():
    """Track picker + mode picker; launches a run_mode_* loop on selection."""
    available_tracks = get_all_tracks()
    
    panel_w = 480
    panel_gap = 60
    total_w = panel_w * 2 + panel_gap
    start_x = (SCREEN_WIDTH - total_w) // 2
    right_x = start_x + panel_w + panel_gap
    
    track_carousel = TrackCarousel(start_x, 195, panel_w, 465, available_tracks)
    
    mode_buttons = [
        Button((right_x, 195, panel_w, 75), "1. SINGLE PLAYER (VS AI)", "Player (Red F1) vs NEAT Champion (Yellow F1)", accent_color=(46, 204, 113)),
        Button((right_x, 292, panel_w, 75), "2. TWO PLAYERS (LOCAL PVP)", "P1 (Red F1) vs P2 (Yellow F1) on 1 keyboard", accent_color=(52, 152, 219)),
        Button((right_x, 390, panel_w, 75), "3. TRAINING CAMP (PRACTICE)", "Solo test drive with Red F1 and LiDAR rays", accent_color=(241, 196, 15)),
        Button((right_x, 487, panel_w, 75), "4. AI EVOLUTION METHOD (TRAIN)", "Dynamic Leader (Yellow) vs Last Champ (Red)", accent_color=(155, 89, 182)),
        Button((right_x, 585, panel_w, 75), "5. EXIT GAME", "Quit simulation engine", accent_color=(231, 76, 60))
    ]
    
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
                
            track_carousel.handle_event(event)
                    
            for i, btn in enumerate(mode_buttons):
                if btn.handle_event(event):
                    cur_track = available_tracks[track_carousel.selected_index]
                    if i == 0: run_mode_single_player(cur_track)
                    elif i == 1: run_mode_two_players(cur_track)
                    elif i == 2: run_mode_training_camp(cur_track)
                    elif i == 3: run_mode_ai_evolution(cur_track)
                    elif i == 4:
                        pygame.quit()
                        sys.exit()
                        
# Backdrop: a faint 40 px grid so the panels read as floating above it.
        screen.fill(COLOR_BG)
        for gx in range(0, SCREEN_WIDTH, 40):
            pygame.draw.line(screen, (16, 21, 30), (gx, 0), (gx, SCREEN_HEIGHT), 1)
        for gy in range(0, SCREEN_HEIGHT, 40):
            pygame.draw.line(screen, (16, 21, 30), (0, gy), (SCREEN_WIDTH, gy), 1)
        
        title_surf = font_title.render("Cyber Racer Simulator", True, (0, 210, 255))
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH // 2, 60))
        screen.blit(title_surf, title_rect)
        
        subtitle_surf = font_subtitle.render("Portfolio Architecture: Multi-Track NEAT Neural Evolution Engine", True, (130, 142, 160))
        subtitle_rect = subtitle_surf.get_rect(center=(SCREEN_WIDTH // 2, 95))
        screen.blit(subtitle_surf, subtitle_rect)
        
        screen.blit(font_title.render("SELECT CIRCUIT", True, (46, 204, 113)), (start_x, 155))
        screen.blit(font_title.render("SELECT GAME MODE", True, (241, 196, 15)), (right_x, 155))
        
        track_carousel.draw(screen)
        for btn in mode_buttons:
            btn.draw(screen)
            
        footer_surf = font_subtitle.render("Cyber Racer Simulator by Tee Yi Xuan", True, (90, 102, 120))
        footer_rect = footer_surf.get_rect(center=(SCREEN_WIDTH // 2, 755))
        screen.blit(footer_surf, footer_rect)
        
        pygame.display.flip()
        clock.tick(FPS)

if __name__ == "__main__":
    audio.init()
    main_menu()