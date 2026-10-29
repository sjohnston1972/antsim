"""
Ant Colony Simulation  -  Blind Foraging
=========================================
Ants find food ONLY by walking into it or following pheromone trails.

Architecture
- Grid-based pheromones (numpy) with decay + diffusion
- 3-sensor "antenna" steering (left / centre / right)
- Deposit reserve creates directional gradients automatically
- Two pheromone layers: FOOD trail (orange) and NEST trail (blue)

Controls
- Click in sim area : place food
- Drag brown circle : move nest
- SPACE : pause / resume
- R     : full reset
"""

import pygame
import sys
import math
import random

try:
    import numpy as np
except ImportError:
    print("Requires numpy  -  pip install numpy")
    sys.exit(1)

pygame.init()

# ============================================================================
# DISPLAY AND GRID
# ============================================================================
WIN_W, WIN_H = 1600, 900
SIM_W, SIM_H = 1200, 900
PANEL_X = SIM_W

CELL = 4                            # pixels per pheromone cell
GW   = SIM_W // CELL                # 300
GH   = SIM_H // CELL                # 225

MAX_PHER      = 255.0               # cap per cell
RESERVE_DECAY = 0.985               # deposit reserve fade per step

# ============================================================================
# COLOURS
# ============================================================================
WHITE    = (255, 255, 255)
BLACK    = (0, 0, 0)
CYAN     = (0, 255, 255)
YELLOW   = (255, 255, 0)
RED      = (220, 50, 40)
ORANGE   = (255, 170, 40)
L_GRAY   = (180, 180, 180)
D_GRAY   = (80, 80, 80)
PANEL_BG = (30, 30, 34)
NEST_C   = (100, 65, 30)
NEST_R   = (170, 120, 55)

# ============================================================================
# TUNABLE PARAMETERS  (all modified by sliders at runtime)
# ============================================================================
class Cfg:
    ant_count  = 80
    speed      = 2.0
    sens_dist  = 24.0        # how far ahead the 3 sensors sample
    sens_angle = 0.5         # L/R sensor spread in radians (~29 deg)
    turn       = 0.4         # max steer per frame when following trail
    wander     = 0.2         # random angular noise per frame
    decay      = 0.985       # pheromone multiplicative decay per frame
    diffuse_r  = 0.12        # fraction blended with 3x3 neighbours
    deposit    = 8.0         # pheromone deposited per step (scaled by reserve)
    food_sz    = 35          # radius of new food blobs
    nest_x     = 100.0
    nest_y     = float(SIM_H // 2)

cfg = Cfg()

# ============================================================================
# UI  -  SLIDER
# ============================================================================
class Slider:
    def __init__(self, x, y, w, lo, hi, val, label, is_float=False):
        self.rect = pygame.Rect(x, y, w, 8)
        self.lo, self.hi = lo, hi
        self.value = val
        self.label = label
        self.is_float = is_float
        self.dragging = False
        self._hr = 8
        r = (val - lo) / (hi - lo) if hi != lo else 0
        self.hx = x + int(r * w)

    def event(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN:
            mx, my = ev.pos
            if abs(mx - self.hx) < 14 and abs(my - self.rect.y) < 14:
                self.dragging = True
        elif ev.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
        elif ev.type == pygame.MOUSEMOTION and self.dragging:
            mx = max(self.rect.x, min(ev.pos[0], self.rect.right))
            self.hx = mx
            r = (mx - self.rect.x) / self.rect.w
            self.value = self.lo + r * (self.hi - self.lo)
            if not self.is_float:
                self.value = int(self.value)

    def draw(self, surf, font):
        surf.blit(font.render(self.label, True, WHITE),
                  (self.rect.x, self.rect.y - 18))
        v = f"{self.value:.3f}" if self.is_float else str(int(self.value))
        surf.blit(font.render(v, True, CYAN),
                  (self.rect.right + 8, self.rect.y - 4))
        pygame.draw.rect(surf, L_GRAY, self.rect)
        pygame.draw.circle(surf, YELLOW, (self.hx, self.rect.y + 4), self._hr)

# ============================================================================
# FOOD SOURCE
# ============================================================================
class Food:
    def __init__(self, cx, cy, sz, pieces=None):
        self.cx = float(cx)
        self.cy = float(cy)
        self.sz = sz
        self.pieces = pieces if pieces is not None else random.randint(80, 400)
        self.max_p = self.pieces
        # organic blob outline
        n = 28
        self.poly = []
        for i in range(n):
            a = (i / n) * math.tau
            r = sz * (0.75 + 0.25 * math.sin(i * 0.8) + random.uniform(-0.1, 0.1))
            self.poly.append((cx + math.cos(a) * r, cy + math.sin(a) * r))

    @property
    def depleted(self):
        return self.pieces <= 0

    def contains(self, x, y):
        return (x - self.cx) ** 2 + (y - self.cy) ** 2 < self.sz ** 2

    def take(self):
        if self.pieces > 0:
            self.pieces -= 1
            return self.pieces == 0
        return False

    def draw(self, surf, font):
        if self.depleted:
            return
        t = self.pieces / self.max_p
        g = int(220 * t + 35)
        pygame.draw.polygon(surf, (0, g, 0), self.poly)
        pygame.draw.polygon(surf, (0, max(0, g - 60), 0), self.poly, 2)
        txt = font.render(str(self.pieces), True, WHITE)
        surf.blit(txt, txt.get_rect(center=(int(self.cx), int(self.cy))))

# ============================================================================
# ANT  -  BLIND FORAGING WITH 3-SENSOR STEERING
# ============================================================================
class Ant:
    __slots__ = ('x', 'y', 'angle', 'has_food', 'reserve')

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.angle = random.uniform(0, math.tau)
        self.has_food = False
        self.reserve = 1.0       # deposit strength fades as ant walks

    # -- sensor read at angle offset from heading --
    def _sense(self, grid, offset):
        sx = self.x + math.cos(self.angle + offset) * cfg.sens_dist
        sy = self.y + math.sin(self.angle + offset) * cfg.sens_dist
        gx, gy = int(sx / CELL), int(sy / CELL)
        if 0 <= gx < GW and 0 <= gy < GH:
            return grid[gy, gx]
        return 0.0

    # -- turn toward strongest pheromone of the three sensors --
    def _steer(self, grid):
        L = self._sense(grid, -cfg.sens_angle)
        C = self._sense(grid,  0)
        R = self._sense(grid,  cfg.sens_angle)
        if C >= L and C >= R:
            return                                        # ahead is best
        if C < L and C < R:                               # both flanks better
            self.angle += cfg.turn * random.choice((-1, 1))
        elif L > R:
            self.angle -= cfg.turn
        else:
            self.angle += cfg.turn

    # -- deposit pheromone at current cell, consume reserve --
    def _lay(self, grid):
        gx, gy = int(self.x / CELL), int(self.y / CELL)
        if 0 <= gx < GW and 0 <= gy < GH:
            grid[gy, gx] = min(MAX_PHER,
                               grid[gy, gx] + cfg.deposit * self.reserve)
        self.reserve *= RESERVE_DECAY

    # -- main tick --
    def update(self, food_g, nest_g, foods):
        if self.has_food:
            # === RETURNING TO NEST ===
            self._steer(nest_g)          # follow nest-trail home
            self._lay(food_g)            # leave food-trail behind

            # gentle nest compass (path integration)
            to = math.atan2(cfg.nest_y - self.y, cfg.nest_x - self.x)
            d = to - self.angle
            while d >  math.pi: d -= math.tau
            while d < -math.pi: d += math.tau
            self.angle += d * 0.05

            # arrived at nest?
            dx, dy = self.x - cfg.nest_x, self.y - cfg.nest_y
            if dx * dx + dy * dy < 625:         # 25 px radius
                self.has_food = False
                self.reserve = 1.0               # fresh for nest-trail
                self.angle += math.pi + random.uniform(-0.4, 0.4)
                return 'delivered'
        else:
            # === SEARCHING FOR FOOD ===
            self._steer(food_g)          # follow food-trail outward
            self._lay(nest_g)            # leave nest-trail breadcrumbs

            # refresh reserve when passing through nest (beacon effect)
            dx, dy = self.x - cfg.nest_x, self.y - cfg.nest_y
            if dx * dx + dy * dy < 625:
                self.reserve = 1.0

            # physical contact with food  (the ONLY way to find food)
            for food in foods:
                if not food.depleted and food.contains(self.x, self.y):
                    was_last = food.take()
                    self.has_food = True
                    self.reserve = 1.0           # fresh for food-trail
                    self.angle += math.pi + random.uniform(-0.4, 0.4)
                    return 'depleted' if was_last else 'picked'

        # wander + move
        self.angle += random.uniform(-cfg.wander, cfg.wander)
        self.x += math.cos(self.angle) * cfg.speed
        self.y += math.sin(self.angle) * cfg.speed

        # bounce off walls
        if self.x < 2:
            self.x = 2;         self.angle = math.pi - self.angle
        elif self.x > SIM_W - 2:
            self.x = SIM_W - 2; self.angle = math.pi - self.angle
        if self.y < 2:
            self.y = 2;         self.angle = -self.angle
        elif self.y > SIM_H - 2:
            self.y = SIM_H - 2; self.angle = -self.angle
        return None

    def draw(self, surf):
        c = ORANGE if self.has_food else RED
        pygame.draw.circle(surf, c, (int(self.x), int(self.y)), 2)

# ============================================================================
# PHEROMONE GRID HELPERS
# ============================================================================
def diffuse(grid, rate):
    """Blend each cell with its 3x3 neighbourhood mean."""
    if rate <= 0:
        return
    pad  = np.pad(grid, 1, mode='edge')
    blur = (pad[:-2, :-2] + pad[:-2, 1:-1] + pad[:-2, 2:]  +
            pad[1:-1,:-2] + pad[1:-1, 1:-1] + pad[1:-1, 2:] +
            pad[2:,  :-2] + pad[2:,  1:-1]  + pad[2:,  2:]) / 9.0
    grid[:] = grid * (1.0 - rate) + blur * rate

# ============================================================================
# MAIN
# ============================================================================
def main():
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Ant Colony  -  Blind Foraging")
    clock  = pygame.time.Clock()
    font   = pygame.font.Font(None, 14)
    tfont  = pygame.font.Font(None, 18)
    ffont  = pygame.font.Font(None, 20)

    # -- pheromone grids --
    food_g = np.zeros((GH, GW), dtype=np.float64)
    nest_g = np.zeros((GH, GW), dtype=np.float64)

    # -- sliders --
    sls = []
    sx, sw, sp = PANEL_X + 15, 250, 36
    sy = 30
    def _sl(lo, hi, v, lbl, f=False):
        nonlocal sy
        sls.append(Slider(sx, sy, sw, lo, hi, v, lbl, f)); sy += sp

    _sl(10,  300,   cfg.ant_count,  "Ants")
    _sl(0.5, 5.0,   cfg.speed,     "Speed",        True)
    _sl(5,   50,    cfg.sens_dist,  "Sensor Dist",  True)
    _sl(0.1, 1.5,   cfg.sens_angle, "Sensor Angle", True)
    _sl(0.05,1.0,   cfg.turn,      "Turn Speed",   True)
    _sl(0.02,0.8,   cfg.wander,    "Wander",       True)
    _sl(0.95,0.999, cfg.decay,     "Ph. Decay",    True)
    _sl(0.0, 0.5,   cfg.diffuse_r, "Diffusion",    True)
    _sl(1,   30,    cfg.deposit,   "Deposit",      True)
    _sl(15,  60,    cfg.food_sz,   "Food Size")
    slider_bottom = sy

    # -- helpers --
    def mk_ants(n):
        return [Ant(cfg.nest_x + random.uniform(-25, 25),
                    cfg.nest_y + random.uniform(-25, 25)) for _ in range(n)]

    def mk_food(existing):
        for _ in range(200):
            fx = random.randint(120, SIM_W - 80)
            fy = random.randint(80, SIM_H - 80)
            if (fx - cfg.nest_x)**2 + (fy - cfg.nest_y)**2 < 200**2:
                continue
            if any((fx - f.cx)**2 + (fy - f.cy)**2 < 160**2
                   for f in existing if not f.depleted):
                continue
            return Food(fx, fy, cfg.food_sz)
        return Food(random.randint(250, SIM_W - 80),
                    random.randint(80, SIM_H - 80), cfg.food_sz)

    # -- initial entities --
    foods = []
    for _ in range(3):
        foods.append(mk_food(foods))
    ants = mk_ants(cfg.ant_count)

    total_collected = 0
    paused = False
    dragging_nest = False
    respawn = {}                     # Food obj -> frames remaining

    # ====================================================================
    # LOOP
    # ====================================================================
    running = True
    while running:
        # -- events --
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False

            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_SPACE:
                    paused = not paused
                elif ev.key == pygame.K_r:
                    food_g[:] = 0; nest_g[:] = 0
                    foods.clear(); respawn.clear()
                    for _ in range(3):
                        foods.append(mk_food(foods))
                    ants = mk_ants(cfg.ant_count)
                    total_collected = 0

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                mx, my = ev.pos
                if mx < SIM_W:
                    if (mx - cfg.nest_x)**2 + (my - cfg.nest_y)**2 < 900:
                        dragging_nest = True
                    else:
                        foods.append(Food(mx, my, cfg.food_sz))

            elif ev.type == pygame.MOUSEBUTTONUP:
                dragging_nest = False

            elif ev.type == pygame.MOUSEMOTION and dragging_nest:
                cfg.nest_x = max(30, min(SIM_W - 30, ev.pos[0]))
                cfg.nest_y = max(30, min(SIM_H - 30, ev.pos[1]))

            for s in sls:
                s.event(ev)

        # -- read sliders --
        cfg.ant_count  = int(sls[0].value)
        cfg.speed      = sls[1].value
        cfg.sens_dist  = sls[2].value
        cfg.sens_angle = sls[3].value
        cfg.turn       = sls[4].value
        cfg.wander     = sls[5].value
        cfg.decay      = sls[6].value
        cfg.diffuse_r  = sls[7].value
        cfg.deposit    = sls[8].value
        cfg.food_sz    = int(sls[9].value)

        # -- adjust ant population to match slider --
        while len(ants) < cfg.ant_count:
            ants.append(Ant(cfg.nest_x + random.uniform(-25, 25),
                            cfg.nest_y + random.uniform(-25, 25)))
        if len(ants) > cfg.ant_count:
            ants = ants[:cfg.ant_count]

        # -- simulate --
        if not paused:
            # decay and spread pheromones
            food_g *= cfg.decay
            nest_g *= cfg.decay
            diffuse(food_g, cfg.diffuse_r)
            diffuse(nest_g, cfg.diffuse_r)

            # update every ant
            for ant in ants:
                result = ant.update(food_g, nest_g, foods)
                if result == 'delivered':
                    total_collected += 1

            # start respawn timer for any newly-depleted food
            for f in foods:
                if f.depleted and f not in respawn:
                    respawn[f] = 900             # 15 sec at 60 fps

            # tick respawn timers
            done = []
            for f in list(respawn):
                respawn[f] -= 1
                if respawn[f] <= 0:
                    done.append(f)
            for f in done:
                del respawn[f]
                idx = foods.index(f)
                foods[idx] = mk_food(foods)

        # ================================================================
        # DRAW
        # ================================================================
        screen.fill(BLACK)

        # -- pheromone overlay (grid -> surface -> upscale) --
        rgb = np.zeros((GW, GH, 3), dtype=np.uint8)
        fv = np.clip(food_g.T * 2.5, 0, 255).astype(np.uint8)
        nv = np.clip(nest_g.T * 2.5, 0, 255).astype(np.uint8)
        rgb[:, :, 0] = fv                       # red   from food trail
        rgb[:, :, 1] = fv * 2 // 5              # green tint  -> orange
        rgb[:, :, 2] = nv                       # blue  from nest trail
        p_surf = pygame.surfarray.make_surface(rgb)
        screen.blit(pygame.transform.scale(p_surf, (SIM_W, SIM_H)), (0, 0))

        # -- food blobs --
        for f in foods:
            f.draw(screen, ffont)

        # -- nest --
        nx, ny = int(cfg.nest_x), int(cfg.nest_y)
        pygame.draw.circle(screen, NEST_C, (nx, ny), 22)
        pygame.draw.circle(screen, NEST_R, (nx, ny), 22, 2)
        nt = font.render("NEST", True, WHITE)
        screen.blit(nt, nt.get_rect(center=(nx, ny)))

        # -- ants --
        for a in ants:
            a.draw(screen)

        # ================================================================
        # PANEL
        # ================================================================
        pygame.draw.rect(screen, PANEL_BG, (PANEL_X, 0, WIN_W - PANEL_X, WIN_H))
        pygame.draw.line(screen, WHITE, (PANEL_X, 0), (PANEL_X, WIN_H), 2)

        screen.blit(tfont.render("CONTROLS", True, CYAN), (PANEL_X + 90, 8))
        for s in sls:
            s.draw(screen, font)

        # -- stats and legend --
        carrying = sum(1 for a in ants if a.has_food)
        active   = sum(1 for f in foods if not f.depleted)
        rsp      = len(respawn)
        sy_s     = slider_bottom + 15

        lines = [
            ("--- STATS ---",                             CYAN),
            (f"Ants: {len(ants)}  ({carrying} returning)",WHITE),
            (f"Food collected: {total_collected}",         WHITE),
            (f"Sources: {active} active  {rsp} respawning",WHITE),
            (f"FPS: {int(clock.get_fps())}",              WHITE),
            ("",                                          WHITE),
            ("--- TRAIL LEGEND ---",                      CYAN),
            ("Orange  =  food trail (toward food)",       ORANGE),
            ("Blue    =  nest trail (toward nest)",       (80, 120, 255)),
            ("",                                          WHITE),
            ("--- CONTROLS ---",                          CYAN),
            ("Click sim area : place food",               L_GRAY),
            ("Drag brown circle : move nest",             L_GRAY),
            ("SPACE : pause    R : reset",                L_GRAY),
        ]
        if paused:
            lines.insert(0, ("PAUSED", YELLOW))

        for i, (txt, col) in enumerate(lines):
            screen.blit(font.render(txt, True, col),
                        (PANEL_X + 20, sy_s + i * 18))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
