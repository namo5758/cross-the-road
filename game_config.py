"""Static configuration for Cross the Road.

Keeping immutable game tuning and palette data outside the runtime coordinator
makes those values available to simulation and rendering without a Game import.
"""

# Window size in screen pixels; the frame rate limits how often the game updates.
# ขนาดหน้าต่างมีหน่วยเป็นพิกเซล ส่วนอัตราเฟรมคือจำนวนรอบที่เกมทำงานต่อวินาที
SCREEN_WIDTH, SCREEN_HEIGHT = 1024, 720
FRAMES_PER_SECOND = 60

# 2.5D camera: shift the world down, compress ground depth, and draw height upward.
# ทำภาพให้ดูมีความลึกด้วยการบีบแกนพื้นถนน และเลื่อนสิ่งที่มีความสูงขึ้นด้านบนจอ
ORIGIN_Y = 54
VERTICAL_SCALE = 0.8
HEIGHT_SCALE = 0.8

# World boundaries: smaller y values are farther away; the safe side is above the road.
GOAL_Y = 120
ROAD_TOP, ROAD_BOTTOM = 120, 480
LANES = 4
# Lane height = total road depth / number of lanes; all four lanes have equal depth.
# แบ่งความลึกของถนนด้วยจำนวนเลน เช่น (480 - 120) / 4 ได้เลนละ 90 หน่วย
LANE_HEIGHT = (ROAD_BOTTOM - ROAD_TOP) / LANES
WORLD_BOTTOM = 620
# Only this horizontal interval allows pedestrians to enter and cross the road.
CROSSING_START_X, CROSSING_END_X = 420, 604
# Screen y coordinate where the bottom information panel begins.
HEADS_UP_DISPLAY_Y = 568

# Per-lane travel direction: +1 moves right and -1 moves left; speeds use world units/second.
# ค่า 1 ให้รถวิ่งไปทางขวา ค่า -1 ให้วิ่งไปทางซ้าย ตามลำดับเลนในรายการ
LANE_DIRECTION = [1, 1, -1, -1]
LANE_SPEED = [175, 215, 230, 165]

# Level settings: speed multiplier, spawn-delay range in seconds, and required survivors.
# Vehicle mix values are relative random-selection weights, not vehicle counts.
# น้ำหนักยิ่งมาก ยิ่งมีโอกาสสุ่มได้รถชนิดนั้น เช่น น้ำหนัก 55 จากผลรวม 100 คือโอกาส 55%
LEVELS = [
    dict(name="ด่าน 1 · ถนนสุขุมวิทชานเมือง", speed=1.0, gap=(3.0, 5.5), target=6,
         mix=dict(car=55, truck=6, moto=6, sidecar=14, icecream=12, tanker=7)),
    dict(name="ด่าน 2 · ถนนสุขุมวิทชั้นใน", speed=1.15, gap=(2.3, 4.4), target=6,
         mix=dict(car=45, truck=10, moto=18, sidecar=10, icecream=8, tanker=9)),
    dict(name="ด่าน 3 · แยกอโศกชั่วโมงเร่งด่วน", speed=1.35, gap=(1.7, 3.4), target=7,
         mix=dict(car=40, truck=12, moto=20, sidecar=8, icecream=8, tanker=12)),
]

# Colors use (red, green, blue), with each channel from 0 to 255.
# Higher channels are brighter; these values are chosen for appearance, not calculated.
# Road, pavement, safe-zone, and curb colors:
# กลุ่มสีถนนและทางเท้า: ตัวเลขเรียงเป็น แดง เขียว น้ำเงิน ค่ามากทำให้ช่องสีนั้นสว่างขึ้น
BACKGROUND_COLOR = (30, 33, 40)
ASPHALT = (62, 65, 72)
ASPHALT_SPECK = (70, 73, 80)
PAVEMENT_COLOR = (201, 194, 178)
PAVEMENT_LINE_COLOR = (182, 175, 160)
GOAL_PAVEMENT_COLOR = (178, 208, 168)
GOAL_LINE_COLOR = (160, 190, 150)
SLAB_FRONT_COLOR = (120, 114, 104)
# Road markings and character details:
WHITE = (238, 238, 232)
YELLOW = (240, 190, 40)
SKIN_COLOR = (238, 198, 160)
BLOOD = (128, 10, 18)
BLOOD_HIGHLIGHT = (178, 36, 42)
GLASS_COLOR = (70, 96, 120)
# Interface palette: panel backgrounds, readable text, and status colors.
# Green means success/healthy, yellow draws attention, and red means danger.
# สีส่วนติดต่อผู้เล่น: เขียวสื่อว่าปลอดภัย เหลืองใช้เน้น และแดงเตือนอันตราย
PANEL_COLOR = (23, 26, 32)
PANEL_2_COLOR = (36, 40, 49)
TEXT_COLOR = (232, 232, 226)
MUTED_COLOR = (150, 154, 162)
ACCENT_COLOR = (250, 204, 60)
GOOD_COLOR = (110, 200, 120)
BAD_COLOR = (230, 80, 70)

# Possible vehicle paint colors; each spawned vehicle randomly chooses from its palette.
CAR_COLORS = [(214, 62, 58), (58, 120, 210), (236, 236, 230), (40, 44, 52),
              (230, 170, 40), (70, 160, 120), (160, 166, 176)]
TRUCK_COLORS = [(60, 110, 170), (200, 90, 40), (90, 140, 70)]
MOTORCYCLE_COLORS = [(30, 30, 36), (180, 30, 40), (40, 70, 160)]
SIDECAR_COLORS = [(70, 120, 90), (60, 90, 150), (150, 110, 60)]
ICECREAM_COLORS = [(250, 196, 214), (190, 226, 246), (250, 236, 170)]
# Spilled ice cream uses these colors but shares the slippery-puddle behavior.
ICECREAM_GOO = [(250, 190, 212), (252, 246, 232), (140, 92, 62), (190, 230, 200)]

# Vehicle dimensions use world units; speed multiplies lane speed; damage is the base hit damage.
# ขนาดรถใช้หน่วยในโลกเกม ส่วน speed เป็นตัวคูณความเร็ว และ damage เป็นความเสียหายพื้นฐาน
VEHICLES = {
    "car": dict(length=84, width=48, height=30, speed=1.0, damage=45),
    "truck": dict(length=150, width=58, height=58, speed=0.85, damage=70),
    "moto": dict(length=38, width=16, height=30, speed=1.3, damage=28),
    "sidecar": dict(length=44, width=40, height=30, speed=0.95, damage=32),
    "icecream": dict(length=96, width=50, height=46, speed=0.8, damage=40),
    "tanker": dict(length=172, width=56, height=56, speed=0.75, damage=80),
}

# Character settings: starting health, walking speed, ability cooldown in seconds, and display text.
# ค่าประจำตัวละคร เช่น พลังชีวิต ความเร็วเดิน และเวลารอก่อนใช้ความสามารถอีกครั้ง
PERSON_TYPES = {
    "warden": dict(name="ตำรวจจราจร", health=100, short_name="ตำรวจ", color=(40, 86, 196), speed=70, cooldown=10.0,
                   skill_description="ยกป้ายหยุดรถ: หยุดรถเลนตัวเองและเลนถัดไปเป็นเวลา 3 วินาที"),
    "runner": dict(name="นักวิ่ง", health=80, short_name="นักวิ่ง", color=(40, 168, 92), speed=78, cooldown=6.0,
                   skill_description="วิ่งสปรินต์ x2.2 ชั่วคราว แต่จะเหนื่อยหลังจากนั้น"),
    "grandma": dict(name="คุณยาย", health=60, short_name="คุณยาย", color=(150, 92, 182), speed=36, cooldown=0.0,
                    skill_description="(ติดตัว) รถในระยะใกล้จะชะลอความเร็วลง"),
    "kid": dict(name="เด็ก", health=60, short_name="เด็ก", color=(236, 186, 36), speed=92, cooldown=0.0,
                skill_description="(ติดตัว) ถ้าอยู่คนเดียวเกิน 2 วิ จะตกใจเดินสะเปะสะปะ"),
    "strong": dict(name="คนแข็งแรง", health=150, short_name="จอมพลัง", color=(228, 118, 40), speed=64, cooldown=0.3,
                   skill_description="อุ้ม / วางคนอื่น (ช่วยพาคนเจ็บหรือเด็กข้ามถนนได้)"),
    "citizen": dict(name="ประชาชนทั่วไป", health=100, short_name="ทั่วไป", color=(124, 134, 146), speed=64, cooldown=0.0,
                    skill_description="คนเดินถนนทั่วไป บางคนอาจถือถังน้ำมัน"),
}
# The ten character types created each level; repeated entries create multiple people of that type.
ROSTER = ["warden", "runner", "grandma", "kid", "kid", "strong",
          "citizen", "citizen", "citizen", "citizen"]
