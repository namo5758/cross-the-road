"""Static configuration for Cross the Road.

Keeping immutable game tuning and palette data outside the runtime coordinator
makes those values available to simulation and rendering without a Game import.
"""

W, H = 1024, 720
FPS = 60

OY = 54
K = 0.8
HS = 0.8

GOAL_Y = 120
ROAD_TOP, ROAD_BOT = 120, 480
LANES = 4
LANE_H = (ROAD_BOT - ROAD_TOP) / LANES
WORLD_BOT = 620
CW_X0, CW_X1 = 420, 604
HUD_Y = 568

LANE_DIR = [1, 1, -1, -1]
LANE_SPEED = [175, 215, 230, 165]

LEVELS = [
    dict(name="ด่าน 1 · ถนนในหมู่บ้าน", speed=1.0, gap=(3.0, 5.5), target=6,
         mix=dict(car=55, truck=6, moto=6, sidecar=14, icecream=12, tanker=7)),
    dict(name="ด่าน 2 · ถนนในเมือง", speed=1.15, gap=(2.3, 4.4), target=6,
         mix=dict(car=45, truck=10, moto=18, sidecar=10, icecream=8, tanker=9)),
    dict(name="ด่าน 3 · ชั่วโมงเร่งด่วน", speed=1.35, gap=(1.7, 3.4), target=7,
         mix=dict(car=40, truck=12, moto=20, sidecar=8, icecream=8, tanker=12)),
]

BG = (30, 33, 40)
ASPHALT = (62, 65, 72)
ASPHALT_SPECK = (70, 73, 80)
PAVE = (201, 194, 178)
PAVE_LINE = (182, 175, 160)
GOAL_PAVE = (178, 208, 168)
GOAL_LINE = (160, 190, 150)
SLAB_FRONT = (120, 114, 104)
WHITE = (238, 238, 232)
YELLOW = (240, 190, 40)
SKIN = (238, 198, 160)
BLOOD = (128, 10, 18)
BLOOD_HI = (178, 36, 42)
GLASS = (70, 96, 120)
PANEL = (23, 26, 32)
PANEL_2 = (36, 40, 49)
TEXT = (232, 232, 226)
MUTED = (150, 154, 162)
ACCENT = (250, 204, 60)
GOOD = (110, 200, 120)
BAD = (230, 80, 70)

CAR_COLS = [(214, 62, 58), (58, 120, 210), (236, 236, 230), (40, 44, 52),
            (230, 170, 40), (70, 160, 120), (160, 166, 176)]
TRUCK_COLS = [(60, 110, 170), (200, 90, 40), (90, 140, 70)]
MOTO_COLS = [(30, 30, 36), (180, 30, 40), (40, 70, 160)]
SIDECAR_COLS = [(70, 120, 90), (60, 90, 150), (150, 110, 60)]
ICECREAM_COLS = [(250, 196, 214), (190, 226, 246), (250, 236, 170)]
ICECREAM_GOO = [(250, 190, 212), (252, 246, 232), (140, 92, 62), (190, 230, 200)]

VEHICLES = {
    "car": dict(length=84, width=48, height=30, speed=1.0, dmg=45),
    "truck": dict(length=150, width=58, height=58, speed=0.85, dmg=70),
    "moto": dict(length=38, width=16, height=30, speed=1.3, dmg=28),
    "sidecar": dict(length=44, width=40, height=30, speed=0.95, dmg=32),
    "icecream": dict(length=96, width=50, height=46, speed=0.8, dmg=40),
    "tanker": dict(length=172, width=56, height=56, speed=0.75, dmg=80),
}

TYPES = {
    "warden": dict(name="ตำรวจจราจร", hp=100, short="ตำรวจ", col=(40, 86, 196), speed=70, cd=10.0,
                   skill="ป้ายหยุด: รถเลนที่ใกล้ที่สุดหยุด 3 วินาที"),
    "runner": dict(name="นักวิ่ง", hp=80, short="นักวิ่ง", col=(40, 168, 92), speed=78, cd=6.0,
                   skill="วิ่งเร็ว x2.2 ช่วงสั้น ๆ แล้วต้องพัก"),
    "grandma": dict(name="คุณยาย", hp=60, short="คุณยาย", col=(150, 92, 182), speed=36, cd=0.0,
                    skill="(ติดตัว) รถที่อยู่ใกล้คุณยายจะชะลอ"),
    "kid": dict(name="เด็ก", hp=60, short="เด็ก", col=(236, 186, 36), speed=92, cd=0.0,
                skill="(ติดตัว) อยู่คนเดียวจะตกใจ เดินมั่ว"),
    "strong": dict(name="คนแข็งแรง", hp=150, short="แข็งแรง", col=(228, 118, 40), speed=64, cd=0.3,
                   skill="แบก / วางคนที่อยู่ข้าง ๆ (ช้าลงตอนแบก)"),
    "citizen": dict(name="ชาวบ้าน", hp=100, short="ชาวบ้าน", col=(124, 134, 146), speed=64, cd=0.0,
                    skill="ไม่มีความสามารถพิเศษ"),
}
ROSTER = ["warden", "runner", "grandma", "kid", "kid", "strong",
          "citizen", "citizen", "citizen", "citizen"]
