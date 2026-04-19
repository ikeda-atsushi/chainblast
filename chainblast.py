#!/usr/bin/env python3
"""Chain Blast – pixel-art chain-explosion puzzle  (pygame-ce)"""

import sys
import random
from collections import deque

import pygame

pygame.init()

# ── constants ──────────────────────────────────────────────────────────────────
GRID   = 8
CELL   = 64
PAD    = 3
GX     = 44        # grid left
GY     = 130       # grid top
W      = GX * 2 + GRID * CELL   # 552
H      = GY + GRID * CELL + 90  # 732
FPS    = 60

# Cross (+) arm lengths: W1=bright=volatile(arm2=9cells), W2=medium(arm1=5cells), W3=rock(arm0=self only)
EXPL_RANGE = {1: 2, 2: 1, 3: 0}
N_COLORS   = 6

# ── palette ────────────────────────────────────────────────────────────────────
C_BG    = (14, 14, 22)
C_PANEL = (26, 26, 42)
C_GRID  = (42, 42, 66)
C_TEXT  = (210, 210, 235)
C_DIM   = ( 90,  90, 130)
C_BTN   = ( 50,  85, 150)
C_BTHOV = ( 70, 110, 185)
C_BTTXT = (235, 235, 255)
C_WIN   = (100, 255, 130)
C_EXPL1 = (255, 215,  55)
C_EXPL2 = (255, 110,  25)
C_HOVER = (255, 255, 255, 40)

# Block face colors by weight (bright → medium → dark rock)
PALETTES = {
    1: [(255,85,85),(90,255,110),(80,145,255),(255,235,65),(65,225,255),(220,85,255)],
    2: [(185,55,55),(55,175,70),(55,98,188),(185,162,48),(48,158,185),(158,55,188)],
    3: [(112,44,44),(44,112,54),(44,64,132),(122,112,48),(48,118,128),(118,48,132)],
}

# ── fonts ──────────────────────────────────────────────────────────────────────
F_BIG = pygame.font.Font(None, 38)
F_MED = pygame.font.Font(None, 28)
F_SM  = pygame.font.Font(None, 21)

# ── helpers ────────────────────────────────────────────────────────────────────

def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i]-a[i])*t) for i in range(3))


def draw_block(surf, bx, by, color, weight):
    """Pixel-art block with highlight + shadow + weight pips."""
    r, g, b = color
    x, y, s = bx + PAD, by + PAD, CELL - PAD * 2

    hi  = (min(255,r+90), min(255,g+90), min(255,b+90))
    sh  = (max(0,r-75),   max(0,g-75),   max(0,b-75))
    mid = (max(0,r-30),   max(0,g-30),   max(0,b-30))

    # drop shadow
    pygame.draw.rect(surf, sh, (x+3, y+3, s, s))
    # face
    pygame.draw.rect(surf, color, (x, y, s, s))
    # inner bevel top-left
    pygame.draw.rect(surf, hi,  (x,   y,   s, 2))
    pygame.draw.rect(surf, hi,  (x,   y,   2, s))
    # inner bevel bottom-right
    pygame.draw.rect(surf, sh,  (x+s-2, y,   2, s))
    pygame.draw.rect(surf, sh,  (x,     y+s-2, s, 2))
    # inner face tone
    pygame.draw.rect(surf, mid, (x+2, y+2, s-4, s-4))

    # pips (weight indicator)
    cx, cy = x + s//2, y + s//2
    pip_r  = 5
    pip_c  = hi
    positions = {
        1: [(cx,  cy)],
        2: [(cx-8, cy), (cx+8, cy)],
        3: [(cx-10, cy), (cx, cy), (cx+10, cy)],
    }
    for px, py in positions[weight]:
        pygame.draw.circle(surf, (0,0,0,120), (px+1, py+1), pip_r)
        pygame.draw.circle(surf, pip_c, (px, py), pip_r)


def draw_btn(surf, rect, label, hovered=False):
    c = C_BTHOV if hovered else C_BTN
    pygame.draw.rect(surf, c, rect, border_radius=5)
    dark = (max(0,c[0]-40), max(0,c[1]-40), max(0,c[2]-40))
    pygame.draw.rect(surf, dark, rect, 2, border_radius=5)
    txt = F_MED.render(label, True, C_BTTXT)
    surf.blit(txt, txt.get_rect(center=rect.center))


def cross_cells(r, c, er):
    """Return cells in a + (cross/plus) shape with arm length er."""
    cells = [(r, c)]
    for d in range(1, er + 1):
        cells += [(r+d, c), (r-d, c), (r, c+d), (r, c-d)]
    return [(nr, nc) for nr, nc in cells if 0 <= nr < GRID and 0 <= nc < GRID]


def cell_rect(row, col):
    return pygame.Rect(GX + col*CELL, GY + row*CELL, CELL, CELL)


def grid_from_pixel(mx, my):
    col = (mx - GX) // CELL
    row = (my - GY) // CELL
    if 0 <= col < GRID and 0 <= row < GRID:
        return row, col
    return None


# ── game logic ─────────────────────────────────────────────────────────────────

class Block:
    __slots__ = ("weight", "cidx")
    def __init__(self, w, c):
        self.weight = w
        self.cidx   = c

    @property
    def color(self): return PALETTES[self.weight][self.cidx]

    @property
    def er(self):    return EXPL_RANGE[self.weight]


class Game:
    def __init__(self, seed=None):
        if seed is None:
            seed = random.randint(0, 999999)
        self.seed   = seed
        self.rng    = random.Random(seed)
        self.clicks = 0
        self.won    = False
        self.anims  = []   # [cx, cy, r_max, age, ttl]
        self.grid   = [[None]*GRID for _ in range(GRID)]
        self._fill()

    def _fill(self):
        for r in range(GRID):
            for c in range(GRID):
                w = self.rng.choices([1,2,3], weights=[50,33,17])[0]
                i = self.rng.randrange(N_COLORS)
                self.grid[r][c] = Block(w, i)

    # ── click ──
    def click(self, row, col):
        if self.won or self.grid[row][col] is None:
            return
        self.clicks += 1
        removed = self._chain(row, col)
        self._gravity()
        self._check_win()
        return removed

    def _chain(self, sr, sc):
        # Chain rule: a block in the blast zone only re-explodes if it shares
        # the same color as the block that detonated it (sympathetic detonation).
        # W3 rocks (arm 0) never propagate chain – they only remove themselves.
        q       = deque([(sr, sc)])
        seen    = set()
        remove  = set()

        while q:
            r, c = q.popleft()
            if (r,c) in seen or self.grid[r][c] is None:
                continue
            seen.add((r,c))

            blk          = self.grid[r][c]
            er           = blk.er
            chain_cidx   = blk.cidx   # only same-color blocks will chain

            for nr, nc in cross_cells(r, c, er):
                remove.add((nr, nc))
                nb = self.grid[nr][nc]
                if (nr,nc) not in seen and nb is not None:
                    if nb.cidx == chain_cidx:   # same color → chain
                        q.append((nr, nc))

            px = GX + c*CELL + CELL//2
            py = GY + r*CELL + CELL//2
            self.anims.append([px, py, max(er,1)*CELL//2 + CELL//3, 0, 22])

        for r, c in remove:
            self.grid[r][c] = None
        return remove

    # ── gravity ──
    def _gravity(self):
        for col in range(GRID):
            changed = True
            while changed:
                changed = False
                for row in range(GRID-1, 0, -1):
                    above = self.grid[row-1][col]
                    here  = self.grid[row][col]
                    if above is None:
                        continue
                    if here is None:
                        self.grid[row][col]   = above
                        self.grid[row-1][col] = None
                        changed = True
                    elif above.weight > here.weight:
                        # crush lighter block
                        self.grid[row][col]   = above
                        self.grid[row-1][col] = None
                        changed = True

    def _check_win(self):
        self.won = all(self.grid[r][c] is None
                       for r in range(GRID) for c in range(GRID))

    def update(self):
        next_a = []
        for a in self.anims:
            a[3] += 1
            if a[3] < a[4]:
                next_a.append(a)
        self.anims = next_a

    def hover_cells(self, row, col):
        """Cross-shaped blast preview."""
        blk = self.grid[row][col]
        if blk is None:
            return set()
        return set(cross_cells(row, col, blk.er))


# ── main loop ──────────────────────────────────────────────────────────────────

def main():
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Chain Blast")
    clock  = pygame.time.Clock()

    game  = Game()
    hover = None    # (row, col) under cursor

    # button rects
    btn_new   = pygame.Rect(GX,           H-68, 130, 44)
    btn_retry = pygame.Rect(GX + 148,     H-68, 130, 44)
    btn_copy  = pygame.Rect(GX + 296,     H-68, 130, 44)

    # hover overlay surface (per-cell)
    hover_surf = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
    hover_surf.fill((255,255,255, 35))

    running = True
    while running:
        mx, my = pygame.mouse.get_pos()
        hover   = grid_from_pixel(mx, my)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    game = Game(seed=game.seed)
                elif event.key == pygame.K_n:
                    game = Game()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if hover:
                    game.click(*hover)
                if btn_new.collidepoint(mx, my):
                    game = Game()
                if btn_retry.collidepoint(mx, my):
                    game = Game(seed=game.seed)
                if btn_copy.collidepoint(mx, my):
                    try:
                        pygame.scrap.init()
                        pygame.scrap.put(pygame.SCRAP_TEXT,
                                         str(game.seed).encode())
                    except Exception:
                        pass   # clipboard not available in all envs

        game.update()

        # ── draw ──────────────────────────────────────────────────────────────
        screen.fill(C_BG)

        # top panel
        pygame.draw.rect(screen, C_PANEL, (0, 0, W, GY - 10))

        # title
        t = F_BIG.render("CHAIN BLAST", True, C_TEXT)
        screen.blit(t, (GX, 14))

        # click counter
        cc = F_BIG.render(f"CLICKS: {game.clicks}", True, C_TEXT)
        screen.blit(cc, (W - GX - cc.get_width(), 14))

        # seed
        seed_s = F_SM.render(f"SEED  {game.seed}", True, C_DIM)
        screen.blit(seed_s, (GX, 54))

        # legend
        legend_x = GX
        for w in (1, 2, 3):
            samp = PALETTES[w][0]
            pygame.draw.rect(screen, samp, (legend_x, 78, 13, 13))
            labels = {1:"LIGHT +2(9)", 2:"MED +1(5)", 3:"ROCK self"}
            lt = F_SM.render(labels[w], True, C_DIM)
            screen.blit(lt, (legend_x+17, 78))
            legend_x += lt.get_width() + 34

        # grid bg
        pygame.draw.rect(screen, C_PANEL,
                         (GX, GY, GRID*CELL, GRID*CELL))

        # grid lines
        for i in range(GRID+1):
            pygame.draw.line(screen, C_GRID,
                             (GX + i*CELL, GY),
                             (GX + i*CELL, GY + GRID*CELL))
            pygame.draw.line(screen, C_GRID,
                             (GX, GY + i*CELL),
                             (GX + GRID*CELL, GY + i*CELL))

        # hover range preview
        if hover and not game.won:
            hr, hc = hover
            for (rr, rc) in game.hover_cells(hr, hc):
                screen.blit(hover_surf, cell_rect(rr, rc))

        # blocks
        for row in range(GRID):
            for col in range(GRID):
                blk = game.grid[row][col]
                if blk:
                    draw_block(screen, GX + col*CELL, GY + row*CELL,
                               blk.color, blk.weight)

        # cursor highlight on hovered block
        if hover and not game.won:
            hr, hc = hover
            if game.grid[hr][hc]:
                cr = cell_rect(hr, hc)
                pygame.draw.rect(screen, (255,255,255), cr, 2)

        # explosion rings
        for cx, cy, r_max, age, ttl in game.anims:
            t  = age / ttl
            r  = int(r_max * t)
            al = int(255 * (1 - t))
            if r < 2:
                continue
            s = pygame.Surface((r*2+6, r*2+6), pygame.SRCALPHA)
            c1 = (*lerp_color(C_EXPL1, C_EXPL2, t), al)
            c2 = (*C_EXPL1, al // 3)
            pygame.draw.circle(s, c1, (r+3, r+3), r, 4)
            if r > 10:
                pygame.draw.circle(s, c2, (r+3, r+3), max(1, r-12), 2)
            screen.blit(s, (cx - r - 3, cy - r - 3))

        # bottom buttons
        draw_btn(screen, btn_new,   "NEW (N)",   btn_new.collidepoint(mx,my))
        draw_btn(screen, btn_retry, "RETRY (R)", btn_retry.collidepoint(mx,my))
        draw_btn(screen, btn_copy,  "COPY SEED", btn_copy.collidepoint(mx,my))

        # win overlay
        if game.won:
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 170))
            screen.blit(ov, (0, 0))
            wt = F_BIG.render("✨ CLEARED! ✨", True, C_WIN)
            ct = F_MED.render(f"{game.clicks} click{'s' if game.clicks!=1 else ''}  ·  seed {game.seed}", True, C_TEXT)
            ht2 = F_SM.render("Press N for new game  /  R to retry", True, C_DIM)
            screen.blit(wt,  wt.get_rect(center=(W//2, H//2 - 36)))
            screen.blit(ct,  ct.get_rect(center=(W//2, H//2 + 6)))
            screen.blit(ht2, ht2.get_rect(center=(W//2, H//2 + 38)))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
