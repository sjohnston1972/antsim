import pygame
import random
import math
import sys

# Initialize Pygame
pygame.init()

# ============================================================================
# WINDOW AND UI CONFIGURATION
# ============================================================================
WINDOW_WIDTH = 1600
WINDOW_HEIGHT = 900
SIMULATION_WIDTH = 1200
SIMULATION_HEIGHT = 900
PANEL_WIDTH = WINDOW_WIDTH - SIMULATION_WIDTH
PANEL_X = SIMULATION_WIDTH

PHERO_SCALE = 3        # Pheromone glow layer is rendered at 1/3 resolution then smoothed up
GRID_CELL = 60         # Spatial hash cell size (matches ant sensing radius)
SENSE_RADIUS = 60
MAX_PHEROMONES = 4000
NEST_RADIUS = 22       # Ants inside this radius drop off food

# Palette
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
SOIL = (22, 18, 15)
FOOD_TRAIL = (255, 140, 30)    # 'to_food' pheromone glow (amber)
NEST_TRAIL = (30, 130, 190)    # 'to_nest' pheromone glow (teal)
ANT_SEARCH = (200, 95, 65)
ANT_CARRY = (245, 210, 150)
CRUMB = (150, 225, 80)
FOOD_COLORS = [(110, 195, 65), (140, 215, 75), (90, 170, 55), (175, 220, 90), (125, 200, 95)]
SPIDER_BODY = (38, 30, 44)
SPIDER_EYE = (255, 60, 50)
PANEL_BG = (17, 16, 20)
CARD_BG = (27, 26, 32)
TEXT = (228, 224, 216)
TEXT_DIM = (128, 124, 118)
ACCENT = (255, 165, 55)
ACCENT_COOL = (95, 185, 225)
TRACK = (50, 48, 56)
DANGER = (235, 75, 70)

def load_font(size, bold=False):
    return pygame.font.SysFont("segoeui,helveticaneue,arial", size, bold=bold)

def scale_color(color, k):
    return tuple(max(0, min(255, int(c * k))) for c in color)

def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

# ============================================================================
# SIMULATION PARAMETERS
# ============================================================================
class SimParams:
    def __init__(self):
        # Ant parameters
        self.ant_count = 40
        self.ant_speed = 1.5
        self.ant_max_age = 6000
        self.ant_reproduction_food = 3
        self.ant_reproduction_cooldown = 600

        # Food blob size
        self.food_blob_size = 40

        # Predator parameters
        self.predator_count = 0
        self.predator_speed = 1.0
        self.predator_hunt_range = 100

        # Pheromone parameters
        self.pheromone_decay = 0.992
        self.pheromone_strength = 100
        self.pheromone_reinforce_amount = 15

        # ACO parameters
        self.alpha = 1.0  # Pheromone importance (higher = follow pheromones more)
        self.beta = 2.0   # Distance importance (higher = prefer closer pheromones)
        self.elite_percentage = 0.3  # Top 30% of ants are "elite"

        # Exploration parameters
        self.exploration_rate = 0.15  # Chance to ignore trails and explore (15%)
        self.trail_spread = 30  # Pixels of randomness when following trails

        # Nest location
        self.nest_x = 120
        self.nest_y = 120

params = SimParams()

# ============================================================================
# GRAPHICS HELPERS
# ============================================================================
def make_glow(radius, color, intensity=1.0):
    """Radial glow on a black surface, meant to be blitted with BLEND_ADD"""
    surf = pygame.Surface((radius * 2, radius * 2))
    for r in range(radius, 0, -1):
        k = (1 - r / radius) ** 2 * intensity
        pygame.draw.circle(surf, scale_color(color, k), (radius, radius), r)
    return surf

def make_background():
    """Mottled soil with pebbles and a vignette, rendered once"""
    w, h = SIMULATION_WIDTH, SIMULATION_HEIGHT
    rng = random.Random(7)

    # Low-res noise smoothed up gives soft mottling
    noise = pygame.Surface((w // 12, h // 12))
    for x in range(noise.get_width()):
        for y in range(noise.get_height()):
            noise.set_at((x, y), scale_color(SOIL, rng.uniform(0.75, 1.35)))
    surf = pygame.transform.smoothscale(noise, (w, h))

    # Pebbles and grit
    for _ in range(1400):
        x, y = rng.randint(0, w), rng.randint(0, h)
        r = rng.choice((1, 1, 1, 2, 2, 3))
        shade = scale_color(SOIL, rng.uniform(1.4, 2.6))
        if r > 1:
            pygame.draw.circle(surf, scale_color(SOIL, 0.6), (x + 1, y + 1), r)
        pygame.draw.circle(surf, shade, (x, y), r)
    for _ in range(40):
        x, y = rng.randint(0, w), rng.randint(0, h)
        rw, rh = rng.randint(5, 11), rng.randint(4, 8)
        pygame.draw.ellipse(surf, scale_color(SOIL, 0.55), (x + 2, y + 2, rw, rh))
        pygame.draw.ellipse(surf, scale_color(SOIL, rng.uniform(1.8, 2.5)), (x, y, rw, rh))
        pygame.draw.ellipse(surf, scale_color(SOIL, 3.2), (x + 2, y + 1, rw // 3, rh // 3))

    # Vignette
    vig = pygame.Surface((w // 8, h // 8))
    cx, cy = vig.get_width() / 2, vig.get_height() / 2
    for x in range(vig.get_width()):
        for y in range(vig.get_height()):
            d = math.hypot((x - cx) / cx, (y - cy) / cy) / math.sqrt(2)
            v = int(255 * (1 - 0.65 * d ** 1.8))
            vig.set_at((x, y), (v, v, v))
    surf.blit(pygame.transform.smoothscale(vig, (w, h)), (0, 0), special_flags=pygame.BLEND_MULT)
    return surf

def make_nest_surface():
    """Dirt mound with an entrance hole"""
    R = 38
    surf = pygame.Surface((R * 2 + 4, R * 2 + 4), pygame.SRCALPHA)
    c = R + 2
    rng = random.Random(3)
    for r in range(R, 0, -1):
        t = r / R
        if t > 0.42:
            col = lerp_color((112, 84, 58), (52, 39, 28), (t - 0.42) / 0.58)
        else:
            col = lerp_color((20, 14, 10), (112, 84, 58), (t / 0.42) ** 3)
        pygame.draw.circle(surf, col, (c, c), r)
    for _ in range(90):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(R * 0.45, R * 0.95)
        pygame.draw.circle(surf, (135, 104, 74, 200), (c + math.cos(a) * d, c + math.sin(a) * d), 1)
    pygame.draw.ellipse(surf, (8, 5, 4), (c - 8, c - 6, 16, 12))
    return surf

# ============================================================================
# UI SLIDER CLASS
# ============================================================================
class Slider:
    def __init__(self, x, y, width, min_val, max_val, initial_val, label, decimals=0):
        self.x = x
        self.y = y
        self.rect = pygame.Rect(x, y + 22, width, 4)
        self.min_val = min_val
        self.max_val = max_val
        self.value = initial_val
        self.label = label
        self.decimals = decimals
        self.dragging = False

    def _set_from_x(self, mouse_x):
        ratio = max(0.0, min(1.0, (mouse_x - self.rect.x) / self.rect.width))
        self.value = self.min_val + ratio * (self.max_val - self.min_val)
        if self.decimals == 0:
            self.value = int(round(self.value))

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.inflate(16, 18).collidepoint(event.pos):
                self.dragging = True
                self._set_from_x(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._set_from_x(event.pos[0])

    def draw(self, screen, font):
        screen.blit(font.render(self.label, True, TEXT_DIM), (self.x, self.y))
        value_text = f"{self.value:.{self.decimals}f}"
        value_surface = font.render(value_text, True, ACCENT if self.dragging else TEXT)
        screen.blit(value_surface, (self.rect.right - value_surface.get_width(), self.y))

        ratio = (self.value - self.min_val) / (self.max_val - self.min_val)
        handle_x = self.rect.x + ratio * self.rect.width
        pygame.draw.rect(screen, TRACK, self.rect, border_radius=2)
        pygame.draw.rect(screen, ACCENT, (self.rect.x, self.rect.y, handle_x - self.rect.x, 4), border_radius=2)
        pygame.draw.circle(screen, ACCENT, (handle_x, self.rect.centery), 8 if self.dragging else 7)
        pygame.draw.circle(screen, WHITE, (handle_x, self.rect.centery), 4)

# ============================================================================
# PHEROMONE CLASS
# ============================================================================
class Pheromone:
    def __init__(self, x, y, strength, pheromone_type='to_nest'):
        self.x = x
        self.y = y
        self.strength = strength
        self.type = pheromone_type
        self.max_strength = strength

        # Saturation tracking - penalize overcrowded trails
        self.recent_uses = 0  # How many ants used this recently
        self.saturation_decay = 0.9  # How fast saturation recovers

    def update(self):
        self.strength *= params.pheromone_decay
        # Saturation recovers over time
        self.recent_uses *= self.saturation_decay
        return self.strength > 5

    def reinforce(self, amount):
        self.strength = min(self.max_strength * 2, self.strength + amount)
        # Track usage for saturation
        self.recent_uses += 1

    def get_effective_strength(self):
        """Get strength adjusted for saturation - crowded trails are less attractive"""
        saturation_penalty = 1.0 / (1.0 + self.recent_uses * 0.3)
        return self.strength * saturation_penalty

class PheromoneField:
    """All pheromones, bucketed in a spatial hash so ants only scan nearby cells"""
    def __init__(self):
        self.items = []
        self.cells = {}

    def __len__(self):
        return len(self.items)

    def add(self, pheromone):
        self.items.append(pheromone)
        key = (int(pheromone.x) // GRID_CELL, int(pheromone.y) // GRID_CELL)
        self.cells.setdefault(key, []).append(pheromone)

    def update(self):
        alive = [p for p in self.items if p.update()]
        if len(alive) > MAX_PHEROMONES:
            alive.sort(key=lambda p: p.strength, reverse=True)
            alive = alive[:int(MAX_PHEROMONES * 0.85)]
        self.items = []
        self.cells = {}
        for p in alive:
            self.add(p)

    def near(self, x, y):
        cx, cy = int(x) // GRID_CELL, int(y) // GRID_CELL
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                cell = self.cells.get((gx, gy))
                if cell:
                    yield from cell

    def deposit(self, x, y, strength, pheromone_type, reinforce_amount=None):
        """Strengthen an existing pheromone of the same type close by, or lay a new one"""
        for p in self.near(x, y):
            if p.type == pheromone_type and (p.x - x) ** 2 + (p.y - y) ** 2 < 36:
                p.reinforce(reinforce_amount if reinforce_amount is not None else strength * 0.5)
                return
        self.add(Pheromone(x, y, strength, pheromone_type))

    def draw(self, screen, layer):
        """Additive glow: each pheromone lights one low-res pixel, then the layer is smoothed up"""
        layer.fill(BLACK)
        ref = params.pheromone_strength * 1.5
        for p in self.items:
            k = min(1.0, p.strength / ref) * 0.95
            color = FOOD_TRAIL if p.type == 'to_food' else NEST_TRAIL
            if p.type == 'to_nest':
                k *= 0.75
            layer.fill(scale_color(color, k), (int(p.x) // PHERO_SCALE, int(p.y) // PHERO_SCALE, 1, 1),
                       special_flags=pygame.BLEND_ADD)
        glow = pygame.transform.smoothscale(layer, (SIMULATION_WIDTH, SIMULATION_HEIGHT))
        screen.blit(glow, (0, 0), special_flags=pygame.BLEND_ADD)

# ============================================================================
# ANT CLASS - PROBABILISTIC TRAIL FOLLOWING
# ============================================================================
class Ant:
    def __init__(self, x, y, age=0):
        self.x = x
        self.y = y
        self.angle = random.uniform(0, 2 * math.pi)
        self.has_food = False
        self.age = age
        self.food_collected = 0
        self.reproduction_timer = 0
        self.gait = random.uniform(0, 2 * math.pi)

        # Performance tracking for elite ant system
        self.trip_times = []  # List of time taken for each successful food trip
        self.current_trip_start = 0  # Frame when current trip started
        self.total_distance_traveled = 0  # Total distance moved
        self.last_x = x
        self.last_y = y

    def senses(self, dx, dy, dist):
        """True if a point is inside the ant's forward sensing cone (+/-60 deg)"""
        if dist < 3:
            return False
        return dx * math.cos(self.angle) + dy * math.sin(self.angle) > 0.5 * dist

    def pick_weighted(self, candidates):
        """Roulette-wheel selection over (pheromone, score) pairs"""
        total_score = sum(score for _, score in candidates)
        rand_value = random.uniform(0, total_score)
        cumulative = 0
        for pheromone, score in candidates:
            cumulative += score
            if rand_value <= cumulative:
                return pheromone
        return candidates[-1][0]

    def turn_towards(self, target_angle, rate, jitter):
        angle_diff = (target_angle - self.angle + math.pi) % (2 * math.pi) - math.pi
        self.angle += angle_diff * rate + random.uniform(-jitter, jitter)

    def update(self, elite_ants, food_blobs, field, nest_x, nest_y, frame_count):
        self.age += 1
        if self.reproduction_timer > 0:
            self.reproduction_timer -= 1

        if self.age > params.ant_max_age:
            return False

        result = None

        if self.has_food:
            # RETURN TO NEST
            dx_nest = nest_x - self.x
            dy_nest = nest_y - self.y
            dist_to_nest_sq = dx_nest**2 + dy_nest**2

            if dist_to_nest_sq < NEST_RADIUS ** 2:
                self.has_food = False
                self.food_collected += 1

                # Track trip performance for elite ant system
                trip_time = frame_count - self.current_trip_start
                self.trip_times.append(trip_time)
                if len(self.trip_times) > 10:
                    self.trip_times.pop(0)

                self.angle += math.pi + random.uniform(-0.5, 0.5)
                return 'food_delivered'

            # PROBABILISTIC selection among nest-trail pheromones that lead closer to the nest
            candidates = []
            for pheromone in field.near(self.x, self.y):
                if pheromone.type != 'to_nest':
                    continue
                dx = pheromone.x - self.x
                dy = pheromone.y - self.y
                dist_sq = dx*dx + dy*dy
                if dist_sq < SENSE_RADIUS ** 2:
                    if (nest_x - pheromone.x)**2 + (nest_y - pheromone.y)**2 < dist_to_nest_sq:
                        dist = math.sqrt(dist_sq)
                        score = (pheromone.get_effective_strength() ** params.alpha) * ((1.0 / (1 + dist)) ** params.beta)
                        if score > 0:
                            candidates.append((pheromone, score))

            if candidates and random.random() > params.exploration_rate:
                target = self.pick_weighted(candidates)
                noise = random.uniform(-1, 1) * (params.trail_spread / 100)
                target_angle = math.atan2(target.y - self.y, target.x - self.x) + noise
            else:
                target_angle = math.atan2(dy_nest, dx_nest)

            self.turn_towards(target_angle, 0.2, 0.1)

            # Only successful foragers lay the food trail; elite ants lay it thicker
            if random.random() < 0.5:
                field.deposit(self.x, self.y, params.pheromone_strength, 'to_food',
                              self.get_reinforce_amount(elite_ants))

        else:
            # SEARCHING FOR FOOD - BLIND FORAGING
            # Ants cannot sense food directly; they find it only by
            # physically walking into it or following pheromone trails.

            # Drop breadcrumb pheromones while searching
            if random.random() < 0.2:
                field.deposit(self.x, self.y, params.pheromone_strength * 0.5, 'to_nest',
                              params.pheromone_strength * 0.1)

            # Check if physically walked into food
            for food_blob in food_blobs:
                if food_blob.is_inside(self.x, self.y) and not food_blob.is_depleted():
                    depleted = food_blob.take_piece()
                    self.has_food = True
                    self.current_trip_start = frame_count
                    self.angle += math.pi

                    exploration_bonus = food_blob.get_exploration_bonus(food_blobs)
                    field.deposit(self.x, self.y, params.pheromone_strength * 2 * exploration_bonus, 'to_food')
                    return ('food_depleted' if depleted else 'food_taken', food_blob)

            # PROBABILISTIC trail following: only pheromones ahead of the ant
            # and leading away from the nest, so ants travel outward along a trail
            own_nest_dist_sq = (self.x - nest_x)**2 + (self.y - nest_y)**2
            candidates = []
            for pheromone in field.near(self.x, self.y):
                if pheromone.type != 'to_food':
                    continue
                dx = pheromone.x - self.x
                dy = pheromone.y - self.y
                dist_sq = dx*dx + dy*dy
                if dist_sq < SENSE_RADIUS ** 2:
                    dist = math.sqrt(dist_sq)
                    if not self.senses(dx, dy, dist):
                        continue
                    if (pheromone.x - nest_x)**2 + (pheromone.y - nest_y)**2 < own_nest_dist_sq:
                        continue
                    score = (pheromone.get_effective_strength() ** params.alpha) * ((1.0 / (1 + dist)) ** params.beta)
                    if score > 0:
                        candidates.append((pheromone, score))

            if candidates and random.random() > params.exploration_rate:
                target = self.pick_weighted(candidates)
                noise = random.uniform(-1, 1) * (params.trail_spread / 100)
                target_angle = math.atan2(target.y - self.y, target.x - self.x) + noise
            else:
                # No trail found - random walk exploration
                if random.random() < 0.05:
                    self.angle += random.uniform(-0.8, 0.8)
                target_angle = self.angle

            self.turn_towards(target_angle, 0.15, 0.15)

        # Move forward
        self.x += math.cos(self.angle) * params.ant_speed
        self.y += math.sin(self.angle) * params.ant_speed
        self.gait += params.ant_speed * 0.45

        # Track distance traveled
        dx_moved = self.x - self.last_x
        dy_moved = self.y - self.last_y
        self.total_distance_traveled += math.sqrt(dx_moved**2 + dy_moved**2)
        self.last_x = self.x
        self.last_y = self.y

        # Bounce off walls
        if self.x < 0 or self.x > SIMULATION_WIDTH:
            self.angle = math.pi - self.angle
            self.x = max(0, min(SIMULATION_WIDTH, self.x))
        if self.y < 0 or self.y > SIMULATION_HEIGHT:
            self.angle = -self.angle
            self.y = max(0, min(SIMULATION_HEIGHT, self.y))

        return result

    def get_efficiency_score(self):
        """Calculate ant efficiency for elite ant system"""
        if len(self.trip_times) == 0:
            return float('inf')  # Worst score for ants with no trips

        # Average trip time (lower is better)
        return sum(self.trip_times) / len(self.trip_times)

    def get_reinforce_amount(self, elite_ants):
        """Determine pheromone reinforcement amount based on elite status"""
        if len(self.trip_times) == 0:
            return params.pheromone_reinforce_amount * 0.5
        if self in elite_ants:
            return params.pheromone_reinforce_amount * 2.0
        return params.pheromone_reinforce_amount

    def try_reproduce(self):
        if (self.food_collected >= params.ant_reproduction_food and
            self.reproduction_timer == 0):
            self.food_collected -= params.ant_reproduction_food
            self.reproduction_timer = params.ant_reproduction_cooldown
            return Ant(self.x + random.randint(-10, 10),
                      self.y + random.randint(-10, 10))
        return None

    def draw(self, screen):
        ca, sa = math.cos(self.angle), math.sin(self.angle)
        x, y = self.x, self.y
        body = ANT_CARRY if self.has_food else ANT_SEARCH
        leg = scale_color(body, 0.6)

        # Six legs in a tripod gait
        swing = math.sin(self.gait) * 0.35
        for side in (-1, 1):
            for i, forward in enumerate((0.7, 0.0, -0.7)):
                phase = swing if (i % 2 == 0) == (side > 0) else -swing
                a = self.angle + side * (math.pi / 2 - forward - phase)
                pygame.draw.line(screen, leg, (x, y), (x + math.cos(a) * 4.5, y + math.sin(a) * 4.5))

        # Antennae
        hx, hy = x + ca * 3, y + sa * 3
        for side in (-0.5, 0.5):
            a = self.angle + side
            pygame.draw.line(screen, leg, (hx, hy), (hx + math.cos(a) * 3.5, hy + math.sin(a) * 3.5))

        # Abdomen, thorax, head
        pygame.draw.circle(screen, body, (x - ca * 3.2, y - sa * 3.2), 2.6)
        pygame.draw.circle(screen, body, (x, y), 1.5)
        pygame.draw.circle(screen, body, (hx, hy), 1.8)

        if self.has_food:
            pygame.draw.circle(screen, CRUMB, (x + ca * 5.5, y + sa * 5.5), 2)

# ============================================================================
# FOOD BLOB CLASS - WITH DEPLETION
# ============================================================================
class FoodBlob:
    PELLET_COUNT = 70

    def __init__(self, center_x, center_y, size=40, pieces=None, max_pieces=None):
        self.center_x = center_x
        self.center_y = center_y

        # Random piece count if not specified
        if pieces is None:
            if random.random() < 0.5:
                self.pieces = random.randint(50, 499)  # Small source
            else:
                self.pieces = random.randint(500, 1000)  # Large source
        else:
            self.pieces = pieces

        self.max_pieces = max_pieces or self.pieces

        # Track usage for balancing
        self.recent_visits = 0  # How many ants visited recently
        self.visit_decay = 0.95  # How fast visit counter decays

        self.resize(size)

    def resize(self, size):
        self.size = size
        self.glow = make_glow(int(size * 1.7), (45, 120, 30))

        # Pellets sorted inner-first so the outer ones vanish first as food runs out
        self.pellets = []
        for _ in range(self.PELLET_COUNT):
            a = random.uniform(0, 2 * math.pi)
            d = size * 0.85 * math.sqrt(random.random())
            self.pellets.append((math.cos(a) * d, math.sin(a) * d,
                                 random.uniform(2.5, 4.5), random.choice(FOOD_COLORS)))
        self.pellets.sort(key=lambda p: p[0]**2 + p[1]**2)

    def move_to(self, x, y):
        self.center_x = x
        self.center_y = y

    def is_inside(self, x, y):
        return (x - self.center_x)**2 + (y - self.center_y)**2 < self.size**2

    def take_piece(self):
        """Remove one piece from food source. Returns True if food depleted."""
        if self.pieces > 0:
            self.pieces -= 1
            self.recent_visits += 1  # Track visit
            return self.pieces == 0
        return False

    def update(self):
        """Decay visit counter over time"""
        self.recent_visits *= self.visit_decay

    def is_depleted(self):
        return self.pieces <= 0

    def get_exploration_bonus(self, all_food_blobs):
        """Calculate bonus for finding underutilized food source"""
        if self.is_depleted():
            return 1.0

        # Find how crowded this source is compared to others
        active_sources = [f for f in all_food_blobs if not f.is_depleted()]
        if len(active_sources) <= 1:
            return 1.0

        total_visits = sum(f.recent_visits for f in active_sources)
        if total_visits == 0:
            return 2.0  # Big bonus if no one using any source yet

        # Less visited = much higher bonus
        my_proportion = self.recent_visits / total_visits
        avg_proportion = 1.0 / len(active_sources)

        # If less visited than average, give BIG bonus (up to 3x)
        if my_proportion < avg_proportion:
            bonus = 3.0 - (my_proportion / avg_proportion * 2.0)
            return max(bonus, 1.0)
        else:
            # Penalize overused sources
            return 0.5

    def draw(self, screen, font):
        cx, cy = self.center_x, self.center_y
        frac = self.pieces / self.max_pieces
        glow_r = self.glow.get_width() // 2
        screen.blit(self.glow, (cx - glow_r, cy - glow_r), special_flags=pygame.BLEND_ADD)

        visible = max(1, math.ceil(frac * len(self.pellets)))
        for ox, oy, r, color in self.pellets[:visible]:
            px, py = cx + ox, cy + oy
            pygame.draw.circle(screen, (10, 18, 6), (px + 1, py + 1.5), r)
            pygame.draw.circle(screen, color, (px, py), r)
            pygame.draw.circle(screen, scale_color(color, 1.35), (px - r * 0.3, py - r * 0.3), r * 0.35)

        # Piece count in a pill under the pile
        text = font.render(str(self.pieces), True, TEXT)
        pill = text.get_rect(center=(cx, cy + self.size + 12)).inflate(12, 4)
        pygame.draw.rect(screen, (12, 12, 10), pill, border_radius=pill.height // 2)
        pygame.draw.rect(screen, (70, 130, 45), pill, 1, border_radius=pill.height // 2)
        screen.blit(text, text.get_rect(center=pill.center))

# ============================================================================
# PREDATOR CLASS
# ============================================================================
class Predator:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.angle = random.uniform(0, 2 * math.pi)
        self.size = 6
        self.food_timer = 0
        self.gait = 0
        self.hunting = False

    def update(self, ants, food_blobs):
        if self.food_timer > 0:
            self.food_timer -= 1
            return None

        closest_ant = None
        closest_dist = float('inf')

        for ant in ants:
            dx = ant.x - self.x
            dy = ant.y - self.y
            dist = math.sqrt(dx**2 + dy**2)

            if dist < params.predator_hunt_range and dist < closest_dist:
                closest_ant = ant
                closest_dist = dist

        self.hunting = closest_ant is not None
        if closest_ant:
            dx = closest_ant.x - self.x
            dy = closest_ant.y - self.y
            self.angle = math.atan2(dy, dx)

            if closest_dist < 5:
                return ('ant', closest_ant)
        else:
            if random.random() < 0.03:
                self.angle += random.uniform(-0.5, 0.5)

        self.x += math.cos(self.angle) * params.predator_speed
        self.y += math.sin(self.angle) * params.predator_speed
        self.gait += params.predator_speed * 0.3

        if self.x < 0 or self.x > SIMULATION_WIDTH:
            self.angle = math.pi - self.angle
            self.x = max(0, min(SIMULATION_WIDTH, self.x))
        if self.y < 0 or self.y > SIMULATION_HEIGHT:
            self.angle = -self.angle
            self.y = max(0, min(SIMULATION_HEIGHT, self.y))

        return None

    def draw(self, screen, glow):
        ca, sa = math.cos(self.angle), math.sin(self.angle)
        x, y = self.x, self.y
        digesting = self.food_timer > 0

        if self.hunting and not digesting:
            r = glow.get_width() // 2
            screen.blit(glow, (x - r, y - r), special_flags=pygame.BLEND_ADD)

        # Eight jointed legs
        leg = (70, 58, 80) if not digesting else (50, 46, 56)
        swing = math.sin(self.gait) * 0.25
        for side in (-1, 1):
            for i, forward in enumerate((1.0, 0.35, -0.35, -1.0)):
                phase = swing if (i % 2 == 0) == (side > 0) else -swing
                a = self.angle + side * (math.pi / 2 - forward - phase)
                knee = (x + math.cos(a) * 9, y + math.sin(a) * 9)
                fa = a - side * 0.5 * (1 if forward >= 0 else -1)
                foot = (knee[0] + math.cos(fa) * 8, knee[1] + math.sin(fa) * 8)
                pygame.draw.line(screen, leg, (x, y), knee, 2)
                pygame.draw.line(screen, leg, knee, foot, 1)

        # Abdomen, cephalothorax, eyes
        pygame.draw.circle(screen, SPIDER_BODY, (x - ca * 7, y - sa * 7), 7)
        pygame.draw.circle(screen, (80, 30, 40), (x - ca * 7, y - sa * 7), 7, 1)
        pygame.draw.circle(screen, SPIDER_BODY, (x, y), 4.5)
        eye = SPIDER_EYE if not digesting else (110, 50, 45)
        for side in (-1, 1):
            pygame.draw.circle(screen, eye, (x + ca * 3 - sa * 1.6 * side, y + sa * 3 + ca * 1.6 * side), 1.3)

# ============================================================================
# VISUAL EFFECTS
# ============================================================================
class Ripple:
    """Expanding, fading ring used for deliveries, pickups and kills"""
    def __init__(self, x, y, color, max_radius, life, width=1):
        self.x = x
        self.y = y
        self.color = color
        self.max_radius = max_radius
        self.life = life
        self.width = width
        self.age = 0

    def update(self):
        self.age += 1
        return self.age < self.life

    def draw(self, screen):
        t = self.age / self.life
        radius = 2 + self.max_radius * (1 - (1 - t) ** 2)
        pygame.draw.circle(screen, scale_color(self.color, 1 - t), (self.x, self.y), radius, self.width)

# ============================================================================
# CONTROL PANEL
# ============================================================================
def draw_section(screen, font, label, x, y, width):
    text = font.render(label, True, ACCENT_COOL)
    screen.blit(text, (x, y))
    line_y = y + text.get_height() // 2
    pygame.draw.line(screen, TRACK, (x + text.get_width() + 8, line_y), (x + width, line_y))

def draw_sparkline(screen, rect, values, font, label):
    pygame.draw.rect(screen, CARD_BG, rect, border_radius=8)
    current = values[-1] if values else 0
    screen.blit(font.render(label, True, TEXT_DIM), (rect.x + 12, rect.y + 8))
    value_surface = font.render(f"{current:.1f}", True, ACCENT)
    screen.blit(value_surface, (rect.right - 12 - value_surface.get_width(), rect.y + 8))

    chart = pygame.Rect(rect.x + 12, rect.y + 30, rect.width - 24, rect.height - 40)
    if len(values) > 1:
        peak = max(max(values), 1)
        step = chart.width / (len(values) - 1)
        points = [(chart.x + i * step, chart.bottom - v / peak * chart.height) for i, v in enumerate(values)]
        pygame.draw.polygon(screen, (60, 42, 22), points + [(chart.right, chart.bottom), (chart.x, chart.bottom)])
        pygame.draw.lines(screen, ACCENT, False, points, 2)
    else:
        pygame.draw.line(screen, TRACK, (chart.x, chart.bottom), (chart.right, chart.bottom))

def draw_panel(screen, fonts, sliders, sections, stats, food_blobs, delivery_history):
    title_font, label_font, small_font = fonts
    x = PANEL_X + 24
    width = PANEL_WIDTH - 48

    pygame.draw.rect(screen, PANEL_BG, (PANEL_X, 0, PANEL_WIDTH, WINDOW_HEIGHT))
    pygame.draw.line(screen, (40, 38, 46), (PANEL_X, 0), (PANEL_X, WINDOW_HEIGHT))

    screen.blit(title_font.render("ANT COLONY", True, TEXT), (x, 18))
    screen.blit(small_font.render("Probabilistic ACO  ·  blind foraging", True, TEXT_DIM), (x, 48))

    for label, y in sections:
        draw_section(screen, small_font, label, x, y, width)
    for slider in sliders.values():
        slider.draw(screen, label_font)

    draw_sparkline(screen, pygame.Rect(x, 624, width, 72), delivery_history, label_font, "Deliveries / sec")

    # Stats grid
    col_w = width // 2
    for i, (name, value) in enumerate(stats):
        sx = x + (i % 2) * col_w
        sy = 710 + (i // 2) * 22
        screen.blit(small_font.render(name, True, TEXT_DIM), (sx, sy))
        value_surface = label_font.render(value, True, TEXT)
        screen.blit(value_surface, (sx + col_w - 16 - value_surface.get_width(), sy - 1))

    # Food source bars
    y = 808
    for i, food_blob in enumerate(food_blobs):
        if food_blob.is_depleted():
            screen.blit(small_font.render(f"Source {i+1}  ·  regrowing", True, TEXT_DIM), (x, y))
        else:
            screen.blit(small_font.render(f"Source {i+1}", True, TEXT_DIM), (x, y))
            bar = pygame.Rect(x + 70, y + 6, width - 160, 6)
            pygame.draw.rect(screen, TRACK, bar, border_radius=3)
            fill = bar.copy()
            fill.width = max(2, int(bar.width * food_blob.pieces / food_blob.max_pieces))
            pygame.draw.rect(screen, (120, 205, 70), fill, border_radius=3)
            info = small_font.render(f"{food_blob.pieces} / {food_blob.max_pieces}", True, TEXT)
            screen.blit(info, (x + width - info.get_width(), y))
        y += 22

    hint = small_font.render("SPACE pause  ·  R reset  ·  drag nest & food", True, TEXT_DIM)
    screen.blit(hint, (PANEL_X + (PANEL_WIDTH - hint.get_width()) // 2, WINDOW_HEIGHT - 32))

# ============================================================================
# MAIN SIMULATION
# ============================================================================
def main():
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Ant Colony - Blind Foraging")
    clock = pygame.time.Clock()
    fonts = (load_font(24, bold=True), load_font(14), load_font(12))
    food_font = load_font(12, bold=True)
    pause_font = load_font(42, bold=True)

    background = make_background()
    nest_surface = make_nest_surface()
    nest_glow = make_glow(70, (90, 60, 30))
    spider_glow = make_glow(40, (120, 20, 20))
    pheromone_layer = pygame.Surface((SIMULATION_WIDTH // PHERO_SCALE, SIMULATION_HEIGHT // PHERO_SCALE))

    # Sliders grouped into panel sections
    x = PANEL_X + 24
    width = PANEL_WIDTH - 48
    spacing = 36
    layout = [
        ("COLONY", [
            ('ant_count', 10, 200, params.ant_count, "Ant count", 0),
            ('ant_speed', 0.5, 3, params.ant_speed, "Ant speed", 2),
            ('food_blob_size', 30, 80, params.food_blob_size, "Food size", 0),
        ]),
        ("PHEROMONES", [
            ('pheromone_decay', 0.980, 0.998, params.pheromone_decay, "Decay", 3),
            ('pheromone_reinforce_amount', 5, 50, params.pheromone_reinforce_amount, "Reinforce", 0),
            ('trail_spread', 0, 100, params.trail_spread, "Trail spread", 0),
        ]),
        ("ACO", [
            ('alpha', 0.1, 3.0, params.alpha, "Alpha  (trail weight)", 2),
            ('beta', 0.1, 5.0, params.beta, "Beta  (distance weight)", 2),
            ('elite_percentage', 0.1, 1.0, params.elite_percentage, "Elite share", 2),
            ('exploration_rate', 0.0, 0.5, params.exploration_rate, "Exploration", 2),
        ]),
        ("PREDATORS", [
            ('predator_count', 0, 8, params.predator_count, "Spiders", 0),
            ('predator_speed', 0.5, 2, params.predator_speed, "Spider speed", 2),
        ]),
    ]
    sliders = {}
    sections = []
    y = 82
    for section_label, entries in layout:
        sections.append((section_label, y))
        y += 22
        for key, lo, hi, init, label, decimals in entries:
            sliders[key] = Slider(x, y, width, lo, hi, init, label, decimals)
            y += spacing
        y += 6

    def spawn_ants(count):
        # Staggered ages so the founding generation doesn't all die at once
        return [Ant(params.nest_x + random.randint(-30, 30),
                    params.nest_y + random.randint(-30, 30),
                    random.randint(0, params.ant_max_age // 2))
                for _ in range(count)]

    def spawn_predator():
        return Predator(random.randint(20, SIMULATION_WIDTH-20), random.randint(20, SIMULATION_HEIGHT-20))

    def spawn_food_blob(existing_food_blobs=None):
        """Spawn a food blob in a random location away from nest and other food"""
        for _ in range(100):
            x = random.randint(100, SIMULATION_WIDTH - 100)
            y = random.randint(100, SIMULATION_HEIGHT - 100)

            # At least 200px from the nest
            if math.hypot(x - params.nest_x, y - params.nest_y) < 200:
                continue

            # At least 150px from other active food sources
            if existing_food_blobs and any(
                    not f.is_depleted() and math.hypot(x - f.center_x, y - f.center_y) < 150
                    for f in existing_food_blobs):
                continue

            return FoodBlob(x, y, params.food_blob_size)

        return FoodBlob(random.randint(100, SIMULATION_WIDTH - 100),
                       random.randint(100, SIMULATION_HEIGHT - 100),
                       params.food_blob_size)

    def reset():
        first_blob = spawn_food_blob(None)
        return ([first_blob, spawn_food_blob([first_blob])],
                spawn_ants(int(params.ant_count)),
                [spawn_predator() for _ in range(int(params.predator_count))],
                PheromoneField())

    food_blobs, ants, predators, field = reset()
    food_respawn_timers = [0, 0]  # 15 seconds = 900 frames at 60 FPS
    effects = []

    # Metrics tracking
    total_food_collected = 0
    total_trips_completed = 0
    delivery_history = []
    deliveries_this_window = 0

    frame_count = 0
    paused = False
    last_food_blob_size = params.food_blob_size

    # Dragging state
    dragging_nest = False
    dragging_food = None  # Index of food blob being dragged

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_r:
                    food_blobs, ants, predators, field = reset()
                    food_respawn_timers = [0, 0]
                    effects = []
                    frame_count = 0

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_x, mouse_y = event.pos
                if math.hypot(mouse_x - params.nest_x, mouse_y - params.nest_y) < 36:
                    dragging_nest = True
                else:
                    for i, food_blob in enumerate(food_blobs):
                        if not food_blob.is_depleted() and food_blob.is_inside(mouse_x, mouse_y):
                            dragging_food = i
                            break

            elif event.type == pygame.MOUSEBUTTONUP:
                dragging_nest = False
                dragging_food = None

            elif event.type == pygame.MOUSEMOTION and (dragging_nest or dragging_food is not None):
                mouse_x = max(30, min(SIMULATION_WIDTH - 30, event.pos[0]))
                mouse_y = max(30, min(SIMULATION_HEIGHT - 30, event.pos[1]))
                if dragging_nest:
                    params.nest_x = mouse_x
                    params.nest_y = mouse_y
                else:
                    food_blobs[dragging_food].move_to(mouse_x, mouse_y)

            for slider in sliders.values():
                slider.handle_event(event)

        # Update parameters
        for key, slider in sliders.items():
            setattr(params, key, slider.value)

        if params.food_blob_size != last_food_blob_size:
            for food_blob in food_blobs:
                food_blob.resize(params.food_blob_size)
            last_food_blob_size = params.food_blob_size

        # Match predator population to slider
        while len(predators) < int(params.predator_count):
            predators.append(spawn_predator())
        del predators[int(params.predator_count):]

        if not paused:
            frame_count += 1

            field.update()
            for food_blob in food_blobs:
                food_blob.update()
            effects = [e for e in effects if e.update()]

            # Elite ants (fastest average trips) are computed once per frame
            ants_with_trips = sorted((a for a in ants if a.trip_times), key=Ant.get_efficiency_score)
            elite_ants = set(ants_with_trips[:max(1, int(len(ants_with_trips) * params.elite_percentage))])

            new_ants = []
            dead_ants = set()
            food_deliveries = 0

            for ant in ants:
                result = ant.update(elite_ants, food_blobs, field, params.nest_x, params.nest_y, frame_count)

                if result is False:
                    dead_ants.add(ant)
                    continue

                if result == 'food_delivered':
                    food_deliveries += 1
                    total_food_collected += 1
                    total_trips_completed += 1
                    effects.append(Ripple(params.nest_x, params.nest_y, ANT_CARRY, 30, 40))
                elif isinstance(result, tuple):
                    kind, food_blob = result
                    effects.append(Ripple(ant.x, ant.y, CRUMB, 8, 20))
                    if kind == 'food_depleted':
                        # Start respawn timer for this slot
                        for i, blob in enumerate(food_blobs):
                            if blob is food_blob:
                                food_respawn_timers[i] = 900
                                effects.append(Ripple(blob.center_x, blob.center_y, CRUMB, 70, 60, 2))
                                break

                baby = ant.try_reproduce()
                if baby:
                    new_ants.append(baby)

            # Respawn depleted food when its timer expires
            for i in range(len(food_respawn_timers)):
                if food_respawn_timers[i] > 0:
                    food_respawn_timers[i] -= 1
                    if food_respawn_timers[i] == 0:
                        food_blobs[i] = spawn_food_blob(food_blobs)
                        effects.append(Ripple(food_blobs[i].center_x, food_blobs[i].center_y, CRUMB, 60, 45, 2))

            for _ in range(food_deliveries):
                new_ants.append(Ant(params.nest_x + random.randint(-15, 15),
                                    params.nest_y + random.randint(-15, 15)))

            ants = [a for a in ants if a not in dead_ants]
            ants.extend(new_ants)

            # The nest keeps hatching workers up to the target; food lets it grow 50% past it
            target = int(params.ant_count)
            if len(ants) < target and frame_count % 4 == 0:
                ants.append(Ant(params.nest_x + random.randint(-8, 8), params.nest_y + random.randint(-8, 8)))
            del ants[int(target * 1.5):]

            for predator in predators:
                result = predator.update(ants, food_blobs)
                if result:
                    prey_type, prey = result
                    if prey_type == 'ant' and prey in ants:
                        ants.remove(prey)
                        predator.food_timer = 120
                        effects.append(Ripple(prey.x, prey.y, DANGER, 14, 30, 2))

            deliveries_this_window += food_deliveries
            if frame_count % 30 == 0:
                delivery_history.append(deliveries_this_window * 2)
                deliveries_this_window = 0
                del delivery_history[:-90]

        # Draw world
        screen.blit(background, (0, 0))
        field.draw(screen, pheromone_layer)

        for food_blob in food_blobs:
            if not food_blob.is_depleted():
                food_blob.draw(screen, food_font)

        screen.blit(nest_glow, (params.nest_x - 70, params.nest_y - 70), special_flags=pygame.BLEND_ADD)
        nest_half = nest_surface.get_width() // 2
        screen.blit(nest_surface, (params.nest_x - nest_half, params.nest_y - nest_half))

        for effect in effects:
            effect.draw(screen)
        for ant in ants:
            ant.draw(screen)
        for predator in predators:
            predator.draw(screen, spider_glow)

        if paused:
            shade = pygame.Surface((SIMULATION_WIDTH, SIMULATION_HEIGHT), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 110))
            screen.blit(shade, (0, 0))
            text = pause_font.render("PAUSED", True, TEXT)
            screen.blit(text, text.get_rect(center=(SIMULATION_WIDTH // 2, SIMULATION_HEIGHT // 2)))

        # Panel
        ants_with_data = sorted((a for a in ants if a.trip_times), key=Ant.get_efficiency_score)
        if ants_with_data:
            avg_trip = sum(a.get_efficiency_score() for a in ants_with_data) / len(ants_with_data)
            best_trip = ants_with_data[0].get_efficiency_score()
            elite_count = max(1, int(len(ants_with_data) * params.elite_percentage))
        else:
            avg_trip = best_trip = elite_count = 0

        stats = [
            ("Ants", str(len(ants))),
            ("Pheromones", str(len(field))),
            ("Food collected", str(total_food_collected)),
            ("Trips", str(total_trips_completed)),
            ("Elite ants", str(elite_count)),
            ("Spiders", str(len(predators))),
            ("Avg trip", f"{int(avg_trip)}f"),
            ("Best trip", f"{int(best_trip)}f"),
        ]
        draw_panel(screen, fonts, sliders, sections, stats, food_blobs, delivery_history)
        fps = fonts[2].render(f"{int(clock.get_fps())} fps", True, TEXT_DIM)
        screen.blit(fps, (WINDOW_WIDTH - 24 - fps.get_width(), 24))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
