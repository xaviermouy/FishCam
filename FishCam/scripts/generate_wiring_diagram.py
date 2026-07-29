"""Generate a wiring diagram for the FishCam power saving mode hardware."""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

fig, ax = plt.subplots(figsize=(18, 11))
ax.set_xlim(0, 18)
ax.set_ylim(0, 11)
ax.axis('off')
ax.set_facecolor('#F5F5F0')
fig.patch.set_facecolor('#F5F5F0')

# ── Colours ────────────────────────────────────────────────────────────────
C_LED   = '#CC0000'
C_LATCH = '#1A5276'
C_VDD   = '#B7770D'
C_GND   = '#2C3E50'
C_PI    = '#2D6A2D'
C_U1    = '#1A5276'
C_PIN   = '#FFD700'
LW = 2.2

# ── Helpers ────────────────────────────────────────────────────────────────
def wire(pts, color=C_GND, lw=LW):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=color, lw=lw,
            solid_capstyle='round', solid_joinstyle='round', zorder=2)

def dot(x, y, color=C_PIN, size=7):
    ax.plot(x, y, 'o', color=color, markersize=size, zorder=6)

def txt(x, y, s, ha='center', va='center', size=9, color='#111',
        weight='normal', family='monospace', style='normal'):
    ax.text(x, y, s, ha=ha, va=va, fontsize=size, color=color,
            fontweight=weight, fontfamily=family, fontstyle=style, zorder=9)

def box(x, y, w, h, fc='#DDEBF7', ec='#2E6DA4', lw=1.8, r=0.12, z=3):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
        boxstyle=f"round,pad=0.04,rounding_size={r}",
        facecolor=fc, edgecolor=ec, linewidth=lw, zorder=z))

def resistor(cx, cy, label='', color='#7B3F00'):
    ax.add_patch(mpatches.FancyBboxPatch(
        (cx-0.42, cy-0.16), 0.84, 0.32,
        boxstyle="round,pad=0.02,rounding_size=0.04",
        facecolor='#FAF0DC', edgecolor=color, lw=1.8, zorder=4))
    txt(cx, cy+0.30, label, size=8.5, color=color, weight='bold')

def led_sym(cx, cy, color=C_LED):
    ax.add_patch(plt.Polygon(
        [[cx-0.24, cy-0.24], [cx-0.24, cy+0.24], [cx+0.18, cy]],
        closed=True, facecolor=color, edgecolor='#800000', lw=1.5, zorder=4))
    ax.plot([cx+0.18, cx+0.18], [cy-0.26, cy+0.26], color='#800000', lw=2.2, zorder=5)
    ax.plot([cx-0.36, cx-0.24], [cy, cy], color='#444', lw=LW, zorder=5)
    ax.plot([cx+0.18, cx+0.36], [cy, cy], color='#444', lw=LW, zorder=5)
    txt(cx-0.24, cy-0.40, '(+)', size=8, color='#555')
    txt(cx+0.18, cy-0.40, '(−)', size=8, color='#555')

def power_sym(x, y, label='+3.3 V', color=C_VDD):
    ax.plot([x, x], [y, y+0.38], color=color, lw=LW, zorder=5)
    ax.plot([x-0.20, x+0.20], [y+0.38, y+0.38], color=color, lw=LW, zorder=5)
    txt(x, y+0.62, label, size=8, color=color, weight='bold')

def gnd_sym(x, y, color=C_GND):
    ax.plot([x, x], [y, y-0.25], color=color, lw=LW, zorder=5)
    for i, hw in enumerate([0.20, 0.13, 0.06]):
        yy = y - 0.25 - i*0.10
        ax.plot([x-hw, x+hw], [yy, yy], color=color, lw=1.8, zorder=5)

def section_label(cx, cy, text, fc, ec, tcolor):
    box(cx-2.1, cy-0.25, 4.2, 0.50, fc=fc, ec=ec, lw=1.4, r=0.10, z=5)
    txt(cx, cy, text, size=10, weight='bold', color=tcolor, family='sans-serif')


# ══════════════════════════════════════════════════════════════════════════════
# TITLE
# ══════════════════════════════════════════════════════════════════════════════
txt(9, 10.70, 'FishCam – Power Saving Mode Wiring Diagram',
    size=15, weight='bold', color='#1a1a2e', family='sans-serif')
txt(9, 10.32, 'Config LED  &  Hall Effect Latch Switch (US1881LUA)',
    size=10.5, color='#444', family='sans-serif')

# ══════════════════════════════════════════════════════════════════════════════
# RASPBERRY PI ZERO 2W
# ══════════════════════════════════════════════════════════════════════════════
PI_X, PI_Y, PI_W, PI_H = 5.2, 2.5, 2.6, 7.5
box(PI_X, PI_Y, PI_W, PI_H, fc=C_PI, ec='#1a3d1a', lw=2.4, r=0.28, z=3)
txt(PI_X+PI_W/2, PI_Y+PI_H/2+0.5,  'Raspberry Pi',  size=10.5, color='white',  weight='bold', family='sans-serif')
txt(PI_X+PI_W/2, PI_Y+PI_H/2+0.02, 'Zero 2W',       size=10,   color='#aaffaa', family='sans-serif')
txt(PI_X+PI_W/2, PI_Y+PI_H/2-0.50, 'GPIO Header',   size=9,    color='#88cc88', family='sans-serif')

XL = PI_X
XR = PI_X + PI_W   # = 7.8

# Pins: (num, label, y, side, used?)
PINS = [
    (13, 'GPIO27', 9.35, 'L', False),
    (14, 'GND',    9.35, 'R', True),
    (15, 'GPIO22', 8.35, 'L', False),
    (16, 'GPIO23', 8.35, 'R', True),
    (17, '3.3 V',  7.35, 'L', True),
    (18, 'GPIO24', 7.35, 'R', True),
    (19, 'GPIO10', 6.35, 'L', False),
    (20, 'GND',    6.35, 'R', True),
    (21, 'GPIO9',  5.35, 'L', False),
    (22, 'GPIO25', 5.35, 'R', False),
]

for pnum, plabel, py, side, used in PINS:
    px = XL if side == 'L' else XR

    # Pad dot
    dot(px, py, color=C_PIN if used else '#BBBBBB', size=8 if used else 5)

    # Badge
    if side == 'L':
        nb_x = px - 0.38; lb_x = px - 1.0; lb_ha = 'right'
    else:
        nb_x = px + 0.38; lb_x = px + 1.0; lb_ha = 'left'

    badge_fc = '#FFD700' if used else '#DDDDDD'
    badge_ec = '#B8860B' if used else '#AAAAAA'
    ax.add_patch(FancyBboxPatch(
        (nb_x-0.26, py-0.20), 0.52, 0.40,
        boxstyle="round,pad=0.02,rounding_size=0.06",
        facecolor=badge_fc, edgecolor=badge_ec, lw=1, zorder=5))
    txt(nb_x, py, str(pnum), size=8, weight='bold', color='#1a1a1a')

    # Function label (outside Pi, dark text)
    lc = '#1a4d1a' if used else '#999999'
    txt(lb_x, py, plabel, ha=lb_ha, size=8.5,
        color=lc, weight='bold' if used else 'normal')


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG LED CIRCUIT
# GPIO23 Pin16 (y=8.35) → R2 → LED1 → GND drop → Pin14 (y=9.35)
# ══════════════════════════════════════════════════════════════════════════════
section_label(11.5, 9.72, 'CONFIG LED CIRCUIT', '#FDECEA', C_LED, C_LED)

R2_CX,  R2_CY  = 10.0, 8.35
LED_CX, LED_CY = 12.0, 8.35
GND_J_X        = 12.4

wire([(XR, 8.35), (R2_CX-0.42, 8.35)], color=C_LED)
resistor(R2_CX, R2_CY, label='R2  560 Ω', color='#800000')
wire([(R2_CX+0.42, 8.35), (LED_CX-0.36, 8.35)], color=C_LED)
led_sym(LED_CX, LED_CY)
txt(LED_CX, LED_CY+0.62, 'LED1 (Red)', size=9, color='#800000', weight='bold')
wire([(LED_CX+0.36, 8.35),
      (GND_J_X,     8.35),
      (GND_J_X,     9.35),
      (XR,          9.35)], color=C_GND)
gnd_sym(GND_J_X, 8.35)


# ══════════════════════════════════════════════════════════════════════════════
# US1881LUA
# ══════════════════════════════════════════════════════════════════════════════
U1_X, U1_Y, U1_W, U1_H = 11.2, 4.2, 3.4, 3.6
box(U1_X, U1_Y, U1_W, U1_H, fc='#EBF5FB', ec=C_U1, lw=2.2, r=0.22, z=3)
txt(U1_X+U1_W/2, U1_Y+U1_H-0.40, 'U1',             size=14,  weight='bold', color=C_U1)
txt(U1_X+U1_W/2, U1_Y+U1_H-0.85, 'US1881LUA',      size=10,  weight='bold', color=C_U1, family='sans-serif')
txt(U1_X+U1_W/2, U1_Y+U1_H-1.22, 'Hall Effect Latch', size=9, color='#555',  family='sans-serif')

U1_P1Y = U1_Y + 2.70   # VDD
U1_P2Y = U1_Y + 1.70   # GND
U1_P3Y = U1_Y + 0.70   # OUT

for py, pname in [(U1_P1Y,'Pin 1  VDD'),
                  (U1_P2Y,'Pin 2  GND'),
                  (U1_P3Y,'Pin 3  OUT')]:
    dot(U1_X, py, color=C_U1, size=7)
    txt(U1_X+0.22, py, pname, ha='left', size=9.5, color=C_U1)

# TO-92 note
txt(U1_X+U1_W/2, U1_Y-0.35,
    'TO-92 package  (flat face toward you)',
    size=8, color='#555', style='italic', family='sans-serif')
txt(U1_X+U1_W/2, U1_Y-0.65,
    'Left = VDD    Middle = GND    Right = OUT',
    size=8, color='#555', style='italic', family='sans-serif')

# Section label — placed ABOVE U1 box, below LED circuit area
section_label(U1_X+U1_W/2, 3.10, 'HALL EFFECT LATCH CIRCUIT', '#EBF5FB', C_U1, C_U1)


# ── 3.3 V power symbols ────────────────────────────────────────────────────
# At Pin17 left side: mark that it provides 3.3V
power_sym(XL-0.05, 7.35, label='+3.3 V\n→ U1 Pin 1\n  (see right)', color=C_VDD)
# At U1 Pin1: show power connection
power_sym(U1_X, U1_P1Y, label='+3.3 V\n(Pi Pin 17)', color=C_VDD)

# ── GPIO24 → R1 → U1 Pin3 OUT ─────────────────────────────────────────────
R1_CX, R1_CY = 10.0, 7.35
DOGLEG_X     = 10.65   # vertical segment x

wire([(XR, 7.35), (R1_CX-0.42, 7.35)], color=C_LATCH)
resistor(R1_CX, R1_CY, label='R1  500 Ω', color=C_U1)
wire([(R1_CX+0.42, 7.35),
      (DOGLEG_X,   7.35),
      (DOGLEG_X,   U1_P3Y),
      (U1_X,       U1_P3Y)], color=C_LATCH)

# ── GND Pin20 → U1 Pin2 ────────────────────────────────────────────────────
GND_J2_X = 10.65
wire([(XR,      6.35),
      (GND_J2_X, 6.35),
      (GND_J2_X, U1_P2Y),
      (U1_X,    U1_P2Y)], color=C_GND)
dot(GND_J2_X, 6.35,  color=C_GND, size=5)
dot(U1_X,     U1_P2Y, color=C_GND, size=5)


# ══════════════════════════════════════════════════════════════════════════════
# COMPONENT SUMMARY  (lower left)
# ══════════════════════════════════════════════════════════════════════════════
CS_X, CS_Y, CS_W, CS_H = 0.15, 5.4, 4.3, 3.2
box(CS_X, CS_Y, CS_W, CS_H, fc='#FDFEFE', ec='#888', lw=1.2, r=0.14, z=4)
txt(CS_X+CS_W/2, CS_Y+CS_H-0.35, 'COMPONENT SUMMARY',
    size=10, weight='bold', color='#222', family='sans-serif')

for i, (ref, val, desc) in enumerate([
    ('U1',   'US1881LUA', 'Hall effect latch sensor'),
    ('LED1', 'Red LED',   'Config mode status indicator'),
    ('R1',   '500 Ω',     'GPIO protection (U1 OUT → GPIO 24)'),
    ('R2',   '560 Ω',     'LED current limiter (GPIO 23 → LED)'),
]):
    yy = CS_Y + CS_H - 0.90 - i*0.60
    txt(CS_X+0.22, yy,       ref,  ha='left', size=9,   color=C_U1, weight='bold')
    txt(CS_X+0.88, yy,       val,  ha='left', size=9,   color='#222')
    txt(CS_X+0.22, yy-0.25,  desc, ha='left', size=7.8, color='#666',
        style='italic', family='sans-serif')


# ══════════════════════════════════════════════════════════════════════════════
# PI HEADER PIN SUMMARY  (lower left)
# ══════════════════════════════════════════════════════════════════════════════
PS_X, PS_Y, PS_W, PS_H = 0.15, 2.1, 4.3, 3.0
box(PS_X, PS_Y, PS_W, PS_H, fc='#FDFEFE', ec='#888', lw=1.2, r=0.14, z=4)
txt(PS_X+PS_W/2, PS_Y+PS_H-0.35, 'PI HEADER PINS USED',
    size=10, weight='bold', color='#222', family='sans-serif')

for i, (pn, fn, conn, col) in enumerate([
    ('Pin 14', 'GND',     '→ LED1 cathode (−)',     C_GND),
    ('Pin 16', 'GPIO 23', '→ R2 → LED1 anode (+)',  C_LED),
    ('Pin 17', '3.3 V',   '→ U1 Pin 1 VDD',         C_VDD),
    ('Pin 18', 'GPIO 24', '→ R1 → U1 Pin 3 OUT',    C_LATCH),
    ('Pin 20', 'GND',     '→ U1 Pin 2 GND',         C_GND),
]):
    yy = PS_Y + PS_H - 0.85 - i*0.44
    ax.plot([PS_X+0.20, PS_X+0.62], [yy, yy], color=col, lw=4.5,
            solid_capstyle='round', zorder=6)
    txt(PS_X+0.75, yy,       pn,   ha='left', size=9,   color=C_U1, weight='bold')
    txt(PS_X+1.55, yy,       fn,   ha='left', size=9,   color='#333')
    txt(PS_X+0.75, yy-0.20,  conn, ha='left', size=7.8, color='#666',
        style='italic', family='sans-serif')


# ══════════════════════════════════════════════════════════════════════════════
# WIRE COLOUR LEGEND  (bottom strip)
# ══════════════════════════════════════════════════════════════════════════════
box(0.15, 1.52, 17.7, 0.52, fc='#E8E8E3', ec='#AAAAAA', lw=1, r=0.08, z=4)
txt(1.0, 1.78, 'Wire colours:', size=9, color='#444', family='sans-serif')

for i, (col, lbl) in enumerate([
    (C_LED,   'LED signal (GPIO 23)'),
    (C_LATCH, 'Latch signal (GPIO 24)'),
    (C_GND,   'GND'),
    (C_VDD,   '3.3 V (power symbol, no wire drawn)'),
]):
    ox = 3.0 + i*3.8
    ax.plot([ox, ox+0.60], [1.78, 1.78], color=col, lw=4.5,
            solid_capstyle='round', zorder=6)
    txt(ox+0.76, 1.78, lbl, ha='left', size=9, color='#222', family='sans-serif')


# ══════════════════════════════════════════════════════════════════════════════
plt.tight_layout(pad=0.3)
out = r'C:\Users\xavier.mouy\Documents\GitHub\FishCam\FishCam\scripts\wiring_diagram.png'
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
print(f"Saved: {out}")
plt.show()
