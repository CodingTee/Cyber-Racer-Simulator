# =============================================================================
# ai_evolution.py -- the NEAT training loop, rendered live.
#
# population.run() calls eval_genomes once per generation; eval_genomes
# simulates all 30 agents (plus an optional showcase replay of this
# session's champion) and draws every frame. There is NO generation cap:
# training runs until the user presses ESC and raises StopEvolution.
# =============================================================================
import os
import sys
import pygame
import neat

from settings import (
    screen, clock, FPS, SCREEN_WIDTH,
    COLOR_PANEL_BG, COLOR_BORDER, COLOR_TEXT,
    font_title, font_main, font_transition
)
from car import Car
from ui import NeuralNetVisualizer
from model_io import load_trained_model, save_trained_model


class StopEvolutionException(Exception):
    """Raised by the ESC handler to break out of population.run()."""
    pass


def run_mode_ai_evolution(track):
    """Train a NEAT population on `track` until the user presses ESC.

    Loads the archived champion so `all_time_best_fitness` starts from the
    saved score (a new checkpoint is only written when a generation beats
    it), then hands control to population.run().
    """
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
    config_file_path = os.path.join(base_dir, "config-feedforward.txt")
    try:
        neat_config = neat.Config(neat.DefaultGenome, neat.DefaultReproduction,
                                  neat.DefaultSpeciesSet, neat.DefaultStagnation,
                                  config_file_path)
    except Exception as e:
        print(f"Error loading NEAT config: {e}")
        return

    visualizer = NeuralNetVisualizer(neat_config)
    population = neat.Population(neat_config)
    current_gen = 0

    saved_net, saved_genome, _ = load_trained_model(track.model_filename)
    all_time_best_fitness = (
        float(saved_genome.fitness)
        if (saved_genome and hasattr(saved_genome, 'fitness') and saved_genome.fitness is not None)
        else 0.0
    )

    previous_generation_champion_id = None
    fast_forward = False

    # Session champion archive: the best genome produced *during this run*,
    # starting from 0 and independent of whatever score sits in the saved
    # .pkl. It only drives the showcase car below and is never injected back
    # into NEAT, so it cannot change evolution, speciation or the saved model.
    session_champion_genome = None
    session_champion_fitness = 0.0

    # Grid slot reserved for the showcase car. Index 15 is verified clear of
    # the walls on every track, both at the start line and at every sampled
    # curriculum spawn point (16+ collides on trioval, 26+ on ring).
    SHOWCASE_SPAWN_INDEX = 15

    def eval_genomes(genomes, config):
        """Simulate one generation: drive every agent, score it, render it.

        Called by NEAT once per generation. It owns the whole generation
        loop (including the "WRECKED" frame that shows the finished
        banner) and only returns when the generation is over.
        """
        nonlocal current_gen, all_time_best_fitness, previous_generation_champion_id, fast_forward
        nonlocal session_champion_genome, session_champion_fitness
        current_gen += 1
        nets, cars, ge = [], [], []

        # Curriculum spawning (spline circuit only): the rolling window shifts
        # every generation so the population discovers the full track in
        # pieces. The previous generation's champion and the first 8 cars
        # always start from the legitimate start line.
        curriculum_idx = None
        if track.id == "spline_gp" and current_gen > 2:
            curriculum_idx = (current_gen * 18) % len(track.circuit_path)

        for idx, (genome_id, genome) in enumerate(genomes):
            nets.append(neat.nn.FeedForwardNetwork.create(genome, config))
            is_last_champ = (current_gen > 1 and previous_generation_champion_id is not None and genome_id == previous_generation_champion_id)
            c = Car(sprite_type="black", spawn_index=idx, name=f"AI #{idx+1}", is_last_champion=is_last_champ)

            # Champions and the first 8 cars always start at the real line
            if is_last_champ or idx < 8 or curriculum_idx is None:
                c.reset(track, curriculum_idx=None)
            else:
                c.reset(track, curriculum_idx=curriculum_idx)

            cars.append(c)
            genome.fitness = 0.0
            ge.append(genome)

        # Showcase seat: once NEAT has dropped this session's champion out of
        # the gene pool, put a copy back on track so the best run stays
        # watchable. The copy gets a net and a car but NO entry in `ge`, so it
        # never touches fitness, speciation, stagnation or the saved model -
        # it is a pure spectator.
        # The original is identified by object identity: `elitism` passes the
        # exact same genome object down the generations, so `is` is exact.
        # (It leaves the pool either with its species on stagnation, or by
        # losing the top-2 tie-break, which favours the higher genome key.)
        showcase_idx = None
        showcase_fitness = 0.0
        if session_champion_genome is not None:
            champion_on_field = any(g is session_champion_genome for _, g in genomes)
            if not champion_on_field:
                showcase_idx = len(cars)
                nets.append(neat.nn.FeedForwardNetwork.create(session_champion_genome, config))
                showcase_car = Car(sprite_type="green", spawn_index=SHOWCASE_SPAWN_INDEX,
                                   name="CHAMPION REPLAY", is_last_champion=False)
                showcase_car.reset(track, curriculum_idx=curriculum_idx)
                cars.append(showcase_car)

        max_duration = track.max_gen_duration
        simulated_time = 0.0
        dt = 1.0 / FPS
        state = "EVOLVING"
        last_known_leader_idx = 0

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        raise StopEvolutionException()
                    if event.key == pygame.K_f:
                        fast_forward = not fast_forward

            sub_steps = 6 if fast_forward else 1

            for _ in range(sub_steps):
                if state == "EVOLVING":
                    simulated_time += dt
                    active_count = 0
                    for i, car in enumerate(cars):
                        if car.is_alive:
                            outputs = nets[i].activate(car.sensor_readings)
                            car.update(outputs[1] - outputs[0], track)
                            if car.is_alive:
                                active_count += 1
                        if i < len(ge):
                            ge[i].fitness = track.compute_fitness(car)
                        else:
                            showcase_fitness = track.compute_fitness(car)

                    if active_count == 0 or simulated_time >= max_duration:
                        state = "WRECKED"
                        break

            current_live_leader_idx = None
            max_live_fitness = -1.0
            for i, car in enumerate(cars):
                # The showcase car is skipped here on purpose: `display_leader_idx`
                # feeds the neural topology panel, which needs a real genome.
                if car.is_alive and i < len(ge):
                    fit = ge[i].fitness
                    if fit > max_live_fitness:
                        max_live_fitness = fit
                        current_live_leader_idx = i

            display_leader_idx = current_live_leader_idx if current_live_leader_idx is not None else last_known_leader_idx
            if current_live_leader_idx is not None:
                last_known_leader_idx = current_live_leader_idx

            if state == "WRECKED":
                gen_best_idx = max(range(len(ge)), key=lambda i: ge[i].fitness)
                gen_best_fitness = ge[gen_best_idx].fitness
                previous_generation_champion_id = genomes[gen_best_idx][0]

                if gen_best_fitness > all_time_best_fitness:
                    all_time_best_fitness = gen_best_fitness
                    ge[gen_best_idx].fitness = gen_best_fitness
                    save_trained_model(track.model_filename, ge[gen_best_idx], config)

                # Session-scoped record: starts at 0 every run, so it always
                # reflects this training session rather than the .pkl archive.
                if gen_best_fitness > session_champion_fitness:
                    session_champion_fitness = gen_best_fitness
                    session_champion_genome = ge[gen_best_idx]

            screen.blit(track.surface, (0, 0))

            for i, car in enumerate(cars):
                is_leader = (i == display_leader_idx and (car.is_alive or state == "WRECKED"))
                car.draw(screen, is_leader=is_leader, show_rays=(car.is_alive and is_leader))

            display_time_left = f"{max(0.0, max_duration - simulated_time):.1f}s"

            panel_x, panel_y, panel_w, panel_h = SCREEN_WIDTH - 380, 20, 360, 770
            pygame.draw.rect(screen, COLOR_PANEL_BG, (panel_x, panel_y, panel_w, panel_h), border_radius=8)
            pygame.draw.rect(screen, COLOR_BORDER, (panel_x, panel_y, panel_w, panel_h), width=2, border_radius=8)
            screen.blit(font_title.render("EVOLUTION TELEMETRY", True, (241, 196, 15)), (panel_x + 16, panel_y + 16))
            stats = [
                f"Track        : {track.name}",
                f"Generation   : {current_gen}",
                f"Active Agents: {active_count if state == 'EVOLVING' else 0} / {len(ge)}",
                f"Best Fitness : {all_time_best_fitness:.1f}",
                f"Time Left    : {display_time_left}",
                f"Sim Speed    : {'6.0X (TURBO)' if fast_forward else '1.0X'}",
                f"Status       : {state}",
                f"Showcase     : {'REPLAY ' + format(showcase_fitness, '.1f') if showcase_idx is not None else 'champion racing'}",
                "[F] Toggle Fast-Forward",
                "[ESC] Return to Menu"
            ]
            for i, text in enumerate(stats):
                screen.blit(font_main.render(text, True, COLOR_TEXT), (panel_x + 16, panel_y + 50 + i * 20))
            pygame.draw.line(screen, COLOR_BORDER, (panel_x + 15, panel_y + 245), (panel_x + panel_w - 15, panel_y + 245), 1)
            screen.blit(font_title.render("LEADER NEURAL TOPOLOGY", True, (52, 152, 219)), (panel_x + 16, panel_y + 255))
            if ge and display_leader_idx < len(ge):
                visualizer.render(ge[display_leader_idx], screen, panel_x + 10, panel_y + 290, panel_w - 20, 460)

            if state == "WRECKED":
                # Same anchor the "PRESS [SPACE]" prompt and the READY/GO countdown
                # use (see main.py). figure8 and trioval offset this away from the
                # geometric centre so overlays do not sit on top of the tarmac, so
                # falling back to track.center here would put the label somewhere
                # else than the prompt on those two tracks.
                overlay_anchor = getattr(track, "overlay_anchor", track.center)
                gen_surf = font_transition.render(f"GENERATION {current_gen} FINISHED", True, (241, 196, 15))
                screen.blit(gen_surf, gen_surf.get_rect(center=overlay_anchor))
                pygame.display.flip()
                if not fast_forward:
                    pygame.time.delay(350)
                break

            pygame.display.flip()
            clock.tick(FPS)

    try:
        population.run(eval_genomes, 10000)
    except StopEvolutionException:
        pass
    except neat.population.CompleteExtinctionException:
        # Fallback safety net: with reset_on_extinction=True in
        # config-feedforward.txt this should never trigger, but if the
        # config is ever reverted to False, fail gracefully instead of
        # dumping a raw traceback.
        print("[AI Evolution] All species went extinct after a stagnation streak.")
        print("[AI Evolution] Set reset_on_extinction=True in config-feedforward.txt to auto-recover.")
