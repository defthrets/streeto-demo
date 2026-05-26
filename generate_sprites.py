#!/usr/bin/env python3
"""
Streeto Sprite Generator  -  uses PixelLab API to generate all game assets.

Run once from the preview directory:
    python generate_sprites.py

Re-running is safe - existing files are skipped (cached).
Sprites go into  preview/sprites/  and are loaded by index.html at runtime.

Requires:  requests   Pillow
  pip install requests Pillow
"""

import sys, os, base64, io, time

try:
    import requests
    from PIL import Image
except ImportError:
    print("Missing deps. Run:  pip install requests Pillow")
    sys.exit(1)

# -- Config ----------------------------------------------------------------?
API_KEY  = "7a95b423-3579-4dd0-9246-91a07893b964"
PIXFLUX  = "https://api.pixellab.ai/v1/generate-image-pixflux"
HEADERS  = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
OUT_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sprites")
os.makedirs(OUT_DIR, exist_ok=True)

ERRORS = []

# -- Core API helper --------------------------------------------------------
def gen_image(description, width, height,
              direction=None, view=None,
              outline="single color black outline",
              shading="medium shading",
              detail="highly detailed",
              no_background=True,
              retries=2):
    """Call PixelLab and return a PIL Image (RGBA), or None on failure."""
    payload = {
        "description":   description,
        "image_size":    {"width": width, "height": height},
        "outline":       outline,
        "shading":       shading,
        "detail":        detail,
        "no_background": no_background,
    }
    if direction: payload["direction"] = direction
    if view:      payload["view"]      = view

    for attempt in range(retries + 1):
        try:
            r = requests.post(PIXFLUX, headers=HEADERS, json=payload, timeout=60)
            r.raise_for_status()
            b64 = r.json()["image"]["base64"]
            return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
        except Exception as e:
            if attempt < retries:
                print(f"      retry {attempt+1}...")
                time.sleep(3)
            else:
                print(f"      FAIL FAILED: {e}")
                ERRORS.append(description[:60])
                return None


def save_img(img, filename):
    path = os.path.join(OUT_DIR, filename)
    img.save(path, "PNG")
    kb = os.path.getsize(path) // 1024
    print(f"      OK {filename}  ({img.width}x{img.height}, {kb}kb)")
    return path


def cached_or_gen(filename, gen_fn):
    path = os.path.join(OUT_DIR, filename)
    if os.path.exists(path):
        print(f"      -> {filename}  (cached)")
        return path
    img = gen_fn()
    return save_img(img, filename) if img else None


def make_hstrip(imgs, filename):
    """Stitch images into a horizontal sprite sheet."""
    w = imgs[0].width; h = imgs[0].height
    sheet = Image.new("RGBA", (w * len(imgs), h), (0,0,0,0))
    for i, im in enumerate(imgs):
        sheet.paste(im.resize((w, h)), (i * w, 0))
    return save_img(sheet, filename)


def strip_corner_bg(im, threshold=30):
    """PixelLab sometimes returns a solid near-white background even when we
    ask for transparency. Flood-fill from the four corners and turn any
    contiguous near-corner-colour region into alpha=0. Tuned threshold keeps
    car body details intact."""
    import collections
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    corner = px[0, 0][:3]
    # Quick exit if the corner is already transparent
    if px[0, 0][3] == 0:
        return im
    seen = bytearray(w * h)  # flat visited grid, 0/1
    q = collections.deque()
    for cx, cy in [(0, 0), (w-1, 0), (0, h-1), (w-1, h-1)]:
        q.append((cx, cy))
    def near(c, t):
        return abs(c[0]-t[0]) < threshold and abs(c[1]-t[1]) < threshold and abs(c[2]-t[2]) < threshold
    while q:
        x, y = q.popleft()
        if x < 0 or x >= w or y < 0 or y >= h:
            continue
        idx = y * w + x
        if seen[idx]:
            continue
        seen[idx] = 1
        cur = px[x, y]
        if not near(cur, corner):
            continue
        px[x, y] = (cur[0], cur[1], cur[2], 0)
        q.append((x+1, y)); q.append((x-1, y))
        q.append((x, y+1)); q.append((x, y-1))
    return im


def strip_ground_shadow(im, y_start_frac=0.35, lum_threshold=200):
    """Kill any near-white opaque pixels in the LOWER region of the image —
    PixelLab loves to bake a soft ground shadow under side-on cars that
    corner flood-fill can't reach because the wheels enclose it. Below
    y_start_frac of image height, any pixel brighter than lum_threshold on
    each channel gets alpha=0. Above that line we leave the car body alone."""
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    y_start = int(h * y_start_frac)
    for y in range(y_start, h):
        for x in range(w):
            p = px[x, y]
            if p[3] == 0:
                continue
            if p[0] > lum_threshold and p[1] > lum_threshold and p[2] > lum_threshold:
                px[x, y] = (p[0], p[1], p[2], 0)
    return im


# -- RACE SPRITES ----------------------------------------------------------?
print("\n===  RACE SPRITES  ===")

# Player car - north = facing away = we see the rear (exactly what driver sees)
cached_or_gen("race_player.png", lambda: gen_image(
    "pixel art Japanese sport tuner hatchback car, royal blue paint, wide body kit, "
    "carbon spoiler, dual chrome exhaust tips, LED red tail lights glowing, lowered suspension, "
    "retro 90s arcade racing game style, single vehicle centered",
    200, 150, direction="north", view="low top-down"))

# Habibi's AMG - rear view to chase down
cached_or_gen("race_amg.png", lambda: gen_image(
    "pixel art black Mercedes-AMG sports car, wide aggressive body kit, "
    "amber LED tail lights, chrome quad exhaust, dark tinted windows, "
    "luxury racing car, retro 90s arcade racing game, centered",
    200, 150, direction="north", view="low top-down"))

# Traffic cars - same direction as player (we see rears, player overtakes them)
cached_or_gen("race_traffic_camry.png", lambda: gen_image(
    "pixel art Toyota Camry sedan rear view, silver grey, ordinary family car, "
    "red brake lights on, retro arcade racing game sprite, centered",
    160, 110, direction="north", view="low top-down",
    shading="medium shading", detail="medium detail"))

cached_or_gen("race_traffic_van.png", lambda: gen_image(
    "pixel art white delivery van rear view, boxy tall vehicle, red brake lights, "
    "plain white panels, retro arcade racing game sprite, centered",
    170, 130, direction="north", view="low top-down",
    shading="medium shading", detail="medium detail"))

cached_or_gen("race_traffic_ute.png", lambda: gen_image(
    "pixel art old beaten-up ute pickup truck rear view, rusty brown, open tray back, "
    "Australian work ute, retro arcade racing game sprite, centered",
    160, 110, direction="north", view="low top-down",
    shading="medium shading", detail="medium detail"))

# -- RACE BACKGROUNDS ------------------------------------------------------?
print("\n===  BACKGROUNDS  ===")

# Opening — 22yo at the start of the Saturday night, before the chaos. Used
# as a full scene-overlay image during opening_intro, NOT a horizontal strip.
# Tall-ish square fills the upper portion of the phone screen. Mood: calm,
# anticipatory, suburban driveway at dusk, tuner car ready, single streetlight
# beginning to glow as the sky tilts from orange into purple-blue. Warm but
# quiet — the night hasn't started yet.
cached_or_gen("bg_opening.png", lambda: gen_image(
    "pixel art western sydney suburban driveway at golden hour dusk, "
    "sky a wash of deep orange fading up into purple-blue twilight, "
    "modified Japanese tuner sports car parked in a concrete driveway, "
    "rear brake lights glowing red, taillights warm, ready to roll, "
    "single warm amber street lamp just beginning to glow at the kerb, "
    "brick suburban house with red tile roof and a satellite dish behind, "
    "wheelie bins out by the kerb, empty quiet residential street, "
    "row of identical brick houses receding into the distance with their porch lights on, "
    "calm anticipatory mood, the night hasn't started yet, "
    "tall vertical phone-screen composition, "
    "16-bit pixel art, golden-orange + deep purple palette, highly detailed, atmospheric",
    400, 400, outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

# Parramatta - night skyline strip (used as parallax background in race)
cached_or_gen("bg_parramatta.png", lambda: gen_image(
    "pixel art western sydney Parramatta street at night, shop fronts, kebab shop neon sign, "
    "phone repair shop, Lebanese bakery, halal butcher, illuminated awnings, dark night sky, "
    "street lights glowing orange, urban western sydney, buildings, no cars on road, "
    "wide panoramic strip, 16-bit style",
    400, 150, outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

cached_or_gen("bg_blacktown.png", lambda: gen_image(
    "pixel art Blacktown western sydney street at night, discount shop, fast food, "
    "graffiti on walls, traffic lights, night sky, street lamps, suburban, "
    "gritty urban, 16-bit pixel art strip",
    400, 150, outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

cached_or_gen("bg_cabramatta.png", lambda: gen_image(
    "pixel art Cabramatta street night western sydney, Vietnamese restaurant, "
    "Asian grocery colourful neon signs, bubble tea shop, lanterns, market stalls, "
    "festive colourful lights, night sky, 16-bit pixel art strip",
    400, 150, outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

# Liverpool — south west syd, Lebanese / Pacific Islander hub, lit up at night.
cached_or_gen("bg_liverpool.png", lambda: gen_image(
    "pixel art Liverpool street at night in south west syd, "
    "main street with shisha lounges, late night kebab shops, Lebanese sweets shop, "
    "tobacco store with neon, Macedonia barber, busy footpath with men in collared shirts, "
    "AMGs and Hellcats lined up on the kerb, "
    "deep blue night sky with palms silhouetted against streetlamps, "
    "panoramic shopfront street strip, 16-bit pixel art, deep blue + warm amber palette",
    400, 150, outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

# Penrith — country edge of west syd, jacked utes and panel beaters.
cached_or_gen("bg_penrith.png", lambda: gen_image(
    "pixel art Penrith street at night, country edge of west syd, "
    "panel beater shop with roller doors, country pub with neon XXXX sign glowing, "
    "tyre shop, dirt patch carpark with jacked-up utes parked, "
    "tall gum trees silhouetted against the sky, "
    "big open dark sky above, distant Blue Mountains silhouette on the horizon, "
    "panoramic street strip, 16-bit pixel art, warm amber + deep blue palette",
    400, 150, outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

# Harris Park — Preet's home turf. Real-life Harris Park: Indian shops + 7-11.
cached_or_gen("bg_harrispark.png", lambda: gen_image(
    "pixel art Harris Park Wigram Street Sydney at night, Indian-Australian shopping strip, "
    "Indian sweets shop with bright yellow and red signage and trays of mithai in window, "
    "sari fabric store with colourful saris displayed in window, "
    "7-Eleven convenience store with the iconic red orange green logo glowing bright, "
    "Punjabi tandoori restaurant with neon sign, dosa place with chalk menu board, "
    "Indian grocery with bags of rice and spice stacked outside, "
    "street strung with fairy lights between shops, golden glow from windows, "
    "late night busy footpath, panoramic shopfront street strip, "
    "16-bit pixel art, warm yellow + deep navy night palette",
    400, 150, outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

# Eastern Creek Raceway dragstrip — the post-game finale.
cached_or_gen("bg_easterncreek.png", lambda: gen_image(
    "pixel art Eastern Creek Raceway dragstrip at night, "
    "wide straight asphalt drag strip stretching into the distance with painted white starting lines, "
    "Christmas tree drag starting light tree visible to one side, with stacked amber and green lights, "
    "tall grandstand bleachers on the left side with a crowd of spectators silhouetted, "
    "sponsor banners hanging from the fence, big floodlights blazing overhead, "
    "smoke and tyre marks on the strip, "
    "panoramic shopfront strip composition, deep blue night sky and a few stars, "
    "16-bit pixel art, dramatic floodlit drag racing atmosphere",
    400, 150, outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

# Side-on profile NSW Highway Patrol Holden Commodore SS — the cop car
# Sgt Snout rolls in. Generated BIG (400x200) for crisp rendering anywhere
# from the dialogue panel down to the drag-strip finish line.
cached_or_gen("car_police_side.png", lambda: gen_image(
    "NSW Highway Patrol Holden Commodore SS V8 sedan from year 2008, "
    "seen from a STRICT DIRECT side profile view, "
    "camera positioned exactly perpendicular to the car at ground level on the driver side, "
    "both passenger-side wheels visible at the bottom (front wheel and rear wheel), "
    "the entire car length visible from front bullbar to rear boot — long sleek four-door sedan silhouette, "
    "white paint as the base colour with an iconic NSW Police BATTENBURG CHEQUER pattern "
    "running horizontally along the doors (bright blue and white squares in a thick mid-body band), "
    "large bold blue 'POLICE' lettering across the front door clearly visible, "
    "smaller blue 'HIGHWAY PATROL' lettering near the rear door, "
    "blue NSW Police chevron logo crest on the front fender, "
    "official red-and-blue LED lightbar mounted on the roof clearly visible from the side, "
    "tall black UHF whip antenna sticking up from the boot lid, "
    "matte black official Australian police push bar / nudge bar at the front, "
    "twin spot lights mounted on the A-pillar, factory black 18-inch alloy wheels, "
    "low-profile performance tyres, slightly aggressive lowered stance, "
    "tinted rear windows but clear front windows showing dashboard radio gear, "
    "two-tone reflective stripes along the lower sills, "
    "iconic late-2000s Australian NSW Highway Patrol authentic livery and aesthetic, "
    "highly detailed retro pixel art game sprite, "
    "completely flat side-on silhouette, NO top-down, NO 3 quarter view, ONLY pure side profile",
    400, 200, view="side",
    outline="single color black outline", shading="detailed shading", detail="highly detailed"))

# Brenno's dodgy BMW E36 engine bay (RPG diagnostic scene).
# BMW M52B28 2.8L DOHC inline-six (the iconic late-90s straight-six).
# Captures the iconic visual elements then layers eshay grime.
cached_or_gen("engine_bay_src.png", lambda: gen_image(
    "pixel art bird's eye top down view straight down into a BMW E36 3-Series engine bay "
    "containing the iconic BMW M52B28 2.8 litre DOHC inline SIX cylinder engine, "
    "engine layout centred — long shiny matte black plastic engine cover stretching front to back in the middle "
    "with raised BMW text and roundel logo on it reading 'BMW 24V' in silver, "
    "six visible ignition coil packs in a row along the top of the engine head (one per cylinder), "
    "yellow oil filler cap on top of the engine cover, "
    "large black plastic air intake plenum on the right side with M50 stamped on it, "
    "smooth curved black plastic intake manifold runners arching across, "
    "ribbed black intake hose snaking from the airbox at the front, "
    "round black BMW air filter housing top-left, "
    "translucent white coolant overflow reservoir with green BMW cap on the upper right, "
    "white plastic brake master cylinder reservoir with black cap on the upper left, "
    "yellow ABS pump unit visible bottom-left, "
    "thick black wiring harnesses snaking everywhere, "
    "blue-grey-painted engine bay walls and strut towers visible around the edges, "
    "BMW strut tower brace bolted across the top, "
    "dodgy backyard mechanic mods layered on top: "
    "silver duct tape wrapped around exposed wire bundles, "
    "tek screws crudely driven into the plastic engine cover, "
    "one ignition coil pack visibly CRACKED in half on cylinder four with a wire dangling out the bottom, "
    "thick black oil stains and grime around the valve cover, "
    "an empty Bundaberg ginger beer can sitting on the strut tower, "
    "a half-smoked cigarette butt wedged in a hose, "
    "late night under a single workshop lamp casting deep shadows, "
    "1990s 2000s Western Sydney eshay backyard-mechanic aesthetic, gritty grimy, "
    "16-bit pixel art with high detail, no human, no hands, just the engine bay seen from directly above",
    400, 400, view="high top-down",
    outline="single color black outline", shading="detailed shading", detail="highly detailed",
    no_background=False))

# Generic kebab shop — Habibi's dialogue scene backdrop.
# Iconic west syd late-night Lebanese kebab joint.
cached_or_gen("bg_eljannah.png", lambda: gen_image(
    "pixel art Lebanese kebab shop in west syd at night, "
    "big rotating vertical kebab spit visible through the front window, "
    "stacked chicken and lamb on spits with red heat lamps glowing, "
    "neon sign that reads KEBAB in red and white letters above the awning, "
    "menu board with falafel rolls, HSP, garlic toum sauce, chilli sauce, tabouli, "
    "fluorescent white lights spilling onto the street, smoke from grill, "
    "queue of guys with snapbacks waiting outside, white plastic chairs on footpath, "
    "panoramic shopfront street strip, 16-bit pixel art, warm red and yellow + deep night blue palette",
    400, 150, outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

# -- CHARACTER SPRITE SHEETS (all 4 directions, 100x100 each -> 400x100 sheet) --
print("\n===  CHARACTER SPRITES  ===")

CHARS = {
    # All prompts target the same realism bar set by Moey (habibi). Each
    # entry packs: ethnicity & age + specific outfit + facial features +
    # distinctive accessory + confident pose + "REALISTIC detailed pixel
    # art highly detailed character sprite" suffix. Generated at 128x128
    # per frame so they downsample crisp at the 100x130 dialogue display.
    "habibi": (
        "Lebanese Australian man in his thirties, "
        "white open-collar button-up shirt with sleeves rolled up, thick gold chain necklace, "
        "designer sunglasses pushed up onto slicked black hair, well-groomed black stubble beard, "
        "olive skin, sharp jawline, confident relaxed stance, hands in pockets, "
        "designer watch on wrist, dark fitted trousers, polished leather loafers, "
        "REALISTIC detailed pixel art highly detailed character sprite, "
        "western Sydney Lebanese street culture, charismatic AGM-driving kebab shop owner"
    ),
    "pigcop": (
        "middle-aged stout Australian man in his fifties, regular HUMAN MAN, fully human face and body, "
        "balding head with a few wisps of grey hair, ruddy pink sunburnt complexion, "
        "small narrow human eyes, slightly upturned wide nose, double-chin jowls, thick neck, "
        "no facial hair, stern intimidating frown, "
        "NSW Police uniform — navy blue collared shirt with epaulettes and silver sergeant stripes, "
        "navy police pants, black duty belt with radio and baton, polished black boots, "
        "POLICE peaked cap with silver insignia, "
        "broad-shouldered authoritarian build, beer belly straining the uniform, "
        "hands resting on duty belt, "
        "REALISTIC detailed pixel art highly detailed HUMAN character sprite, "
        "Sergeant from NSW Highway Patrol — absolutely a real human person, "
        "NOT an animal, NOT a furry, NOT anthropomorphic"
    ),
    "bazza": (
        "tall slim young adult REDHEAD man (full-height standing figure NOT a bust NOT a child), "
        "BRIGHT GINGER ORANGE hair clearly visible — short ginger fringe poking out under the cap brim and ginger hair at the sides + back of head, "
        "wearing a navy blue baseball cap on top of the ginger hair, "
        "pale freckled skin (classic redhead complexion) with light acne and a slight smirk, "
        "wearing a baggy MUSTARD YELLOW crewneck jumper sweatshirt, "
        "black Adidas tracksuit pants with three white stripes, white sneakers, "
        "small black bum bag strapped diagonally across the chest over the yellow jumper, "
        "standing upright at full body height in a relaxed adult pose hands at sides, "
        "highly detailed realistic pixel art character"
    ),
    "khoa": (
        "REALISTIC GRITTY pixel art full-body character sprite of a real human person — "
        "absolutely NOT cartoony, NOT anime, NOT chibi — modelled at the same realism bar as the Moey character sprite, "
        "young Vietnamese Australian man in his late twenties, "
        "defined three-dimensional facial structure with sharp jawline, friendly almond-shaped brown eyes, smooth clean-shaven complexion, "
        "short black hair styled with a clean subtle undercut, "
        "slim athletic build, "
        "modern crisp light blue button-up shirt with sleeves neatly rolled up to the elbows, "
        "dark slim-fit jeans, fresh white low-top sneakers, "
        "slim silver chain at neck, modern designer watch on wrist visible, "
        "small dark canvas backpack slung over one shoulder, "
        "polite confident posture, hands relaxed at sides, hint of a warm smile, "
        "richly shaded with multiple tone bands, defined three-dimensional anatomy, "
        "Cabramatta west Sydney modern Vietnamese Australian street culture, "
        "the polite plug everyone knows"
    ),
    "player": (
        "REALISTIC GRITTY pixel art full-body character sprite of a real human person — "
        "absolutely NOT cartoony, NOT anime, NOT chibi — modelled at the same realism bar as the Moey character sprite, "
        "young mixed-background Australian street racer in his early twenties, "
        "short cropped dark hair, light stubble, sharp angular jawline, intense focused dark brown eyes, "
        "defined three-dimensional facial structure, tan complexion, "
        "black zip-up hoodie unzipped over a clean white tee, "
        "dark slim-fit jeans, black driving shoes, "
        "fingerless leather racing gloves on hands, subtle gold chain visible at collar, "
        "car keys clipped to a belt loop, confident neutral stance hands at sides, "
        "richly shaded with multiple tone bands, defined three-dimensional anatomy, "
        "west Sydney street racing protagonist, the silent driver"
    ),
    "preet": (
        "REALISTIC GRITTY pixel art full-body character sprite of a real human person — "
        "absolutely NOT cartoony, NOT anime, NOT chibi — modelled at the same realism bar as the Moey AND Brenno character sprites, "
        "TALL SLIM LEAN Indian Sikh Punjabi Australian man in his thirties "
        "(full-height standing figure NOT a bust NOT a child), "
        "slender build with narrow shoulders, lean frame, thin limbs — distinctly skinny not stocky, "
        "defined three-dimensional human face with sharp cheekbones, warm crinkled brown eyes, "
        "friendly wide grin showing teeth, brown skin, prominent angular jawline under the beard, "
        "FULL THICK well-groomed black beard tied neatly under the chin (proper Sikh beard, no patchy stubble), "
        "BRIGHT ROYAL BLUE dastar TURBAN neatly wrapped on his head with crisp visible folds and a neat pleat at the front, "
        "kara steel bracelet visible on one wrist, "
        "white kurta shirt with subtle gold embroidery at the collar, the kurta hanging loose on his slim frame, "
        "dark slim-fit trousers, simple sandals, "
        "BRIGHT FLUORESCENT GREEN UberEats food delivery insulated thermal backpack visibly strapped on his back, "
        "the rectangular green bag clearly poking up above both shoulders, the white UberEats logo subtly visible, "
        "a samosa held in one hand, standing upright at full body height in a relaxed adult pose hands at sides, "
        "richly shaded with multiple tone bands, defined three-dimensional anatomy, "
        "Harris Park west Sydney lovable Punjabi Australian — food-loving UberEats driver, mainy king"
    ),
    "macca": (
        "REALISTIC GRITTY pixel art full-body character sprite of a real human person — "
        "absolutely NOT cartoony, NOT anime, NOT chibi — modelled at the same realism bar as the Moey AND Brenno character sprites, "
        "TALL SLIM LEAN young white Australian country boy in his late twenties, real name Brett "
        "(full-height standing figure NOT a bust NOT a child), "
        "wiry stockman build with narrow shoulders, lean frame, ropey arms — distinctly skinny not stocky, "
        "deeply sun-tanned weathered face with sharp angular cheekbones and a strong jawline, "
        "scruffy blonde stubble along the jaw, lopsided friendly grin, "
        "squinting blue eyes crinkled from harsh sun, sun-bleached blonde-brown hair partly visible, "
        "defined three-dimensional facial structure, "
        "dusty wide-brim AKUBRA cowboy hat pushed back on his head with a leather band, "
        "faded light blue FLANNEL shirt unbuttoned over a clean white Bonds SINGLET visible at the chest, "
        "the flannel hanging loose on his slim frame, sleeves rolled up to the elbows, "
        "faded blue Wrangler JEANS slim through the leg tucked into worn brown leather steel-toe WORK BOOTS, "
        "big silver oval rodeo BELT BUCKLE clearly visible, leather wallet chain on hip, "
        "relaxed wide-stance stockman posture, thumbs hooked into the belt loops, "
        "richly shaded with multiple tone bands, defined three-dimensional anatomy, "
        "Penrith country-edge of west Sydney NSW, the jacked Ranger driver"
    ),
}

DIRS = ["east", "west", "south", "north"]

for char_id, char_desc in CHARS.items():
    sheet_file = f"char_{char_id}.png"
    if os.path.exists(os.path.join(OUT_DIR, sheet_file)):
        print(f"  -> {sheet_file}  (cached)")
        continue

    print(f"\n  {char_id} ->")
    frames = []
    for d in DIRS:
        print(f"    {d}...")
        img = gen_image(
            f"REALISTIC GRITTY pixel art full-body game character sprite, {char_desc}, "
            f"facing {d}, single character centred on transparent background, "
            f"top-down RPG perspective, highly detailed retro 16-bit style, "
            f"crisp clean linework, rich multi-tone shading with deep cast shadows, "
            f"vivid grounded colours, NO cartoony exaggeration, NO anime, NO chibi",
            160, 160, direction=d, view="low top-down",
            outline="single color black outline", shading="detailed shading", detail="highly detailed")
        frames.append(img if img else Image.new("RGBA", (160,160), (0,0,0,0)))

    if any(f.getbbox() for f in frames):  # at least one non-empty frame
        make_hstrip(frames, sheet_file)

# -- CAR SPRITE SHEETS (all 4 directions, 100x80 each -> 400x80 sheet) ------
print("\n===  CAR SPRITES  ===")

CARS = {
    "amg":    "black Mercedes-AMG sports car seen from directly above straight down, "
              "viewed from a strict bird's eye top-down perspective, sleek low profile, wide body, "
              "rectangular shape with hood at top and rear at bottom, "
              "luxury racing car, clearly oriented along the vertical axis",
    "player": "blue Japanese sport hatchback tuner car seen from directly above straight down, "
              "viewed from a strict bird's eye top-down perspective, "
              "lowered, widebody, modified exhaust, rectangular shape oriented vertically",
    "police": "NSW Highway Patrol Holden Commodore SS sedan seen from directly above straight down, "
              "STRICT bird's eye top-down view, camera looking straight at the roof, "
              "white paint with a thick blue and white chequer pattern strip down each side, "
              "red and blue light bar on roof clearly visible from above with both light pods, "
              "large POLICE lettering on the roof in white reflective stripes, "
              "white front bonnet with black push bar, antenna visible on the boot, "
              "windscreen at the TOP edge (car facing UP, hood pointing up), "
              "boot/rear at the BOTTOM edge, "
              "all four wheels visible at the corners, "
              "highly detailed 1990s/2000s Australian police car, rectangular shape oriented vertically",
    "e36": "BMW 3-Series E36 sedan from year 1996 seen from directly above straight down, "
                 "viewed from a strict bird's eye top-down perspective, faded Cosmos Black paint with peeling clearcoat patches, "
                 "the distinctive BMW kidney grille at the FRONT centre, "
                 "twin round headlights at the front corners (signature E36 face), "
                 "tinted rear windows, mismatched aftermarket black alloy wheels stretched on, "
                 "slammed low coilover suspension, M-Sport rear lip spoiler on the boot, "
                 "Australian eshay street car beaten up but tuned, rectangular shape oriented vertically",
    "camry":  "Toyota Camry SE V6 sedan seen from directly above straight down, "
              "viewed from a strict bird's eye top-down perspective, dark grey paint with subtle pearl, lowered suspension, "
              "clean black aftermarket alloy wheels, modest rear lip spoiler, sleeper street car, "
              "tinted windows, looks ordinary but tuned, rectangular shape oriented vertically",
    "wrx":    "Subaru WRX hatchback rally style seen from directly above straight down, "
              "viewed from a strict bird's eye top-down perspective, World Rally Blue paint, "
              "bonnet hood scoop visible from above, big black rear wing visible from above, "
              "sticker bombed sides, gold BBS wheels, "
              "rectangular shape oriented vertically with the hood at the top",
    "silvia": "Nissan Silvia S14 coupe seen from directly above straight down, "
              "viewed from a strict bird's eye top-down perspective, white pearl paint with subtle red accent stripe, "
              "low slung sleek body, aftermarket spoiler visible from above, deep dish Work Meister wheels, "
              "tinted windows, JDM drift street car, polished modified look, "
              "rectangular shape oriented vertically",
    "ranger":  "Ford Ranger Wildtrak 4x4 ute seen from directly above straight down, "
              "viewed from a strict bird's eye top-down perspective, dark grey or matte black paint, "
              "jacked up raised suspension, oversized mud terrain tyres clearly visible at all four corners, "
              "snorkel intake on side, roof rack with light bar visible from above, off-road bullbar at front, "
              "tray back at the rear, "
              "Australian country boy lifted ute, big aggressive looking, "
              "wide rectangular shape oriented vertically",
}

# Side-on profile sprites for dialogue scenes (one frame, 200x100 each).
# These show the car from the side like classic 2D platformer car art.
SIDE_CARS = {
    "amg_side":    "Mercedes-AMG C63S sports car seen from a strict side profile view, "
                   "viewed from directly beside the car at ground level, "
                   "two wheels visible (left side only), black paint, low slung, wide arches, "
                   "quad exhaust tips at rear, AMG aggressive aero, side profile silhouette, "
                   "no front view, no rear view, NO top-down, ONLY side-on profile",
    "camry_side":  "Toyota Camry XV40 sedan from year 2008, four-door sedan body, "
                   "seen from a STRICT DIRECT side profile view, "
                   "the car is FACING RIGHT — nose / front bumper / headlights on the RIGHT, "
                   "REAR / taillights on the LEFT, "
                   "FLOATING in empty space with NOTHING below the wheels — "
                   "ZERO ground shadow, ZERO drop shadow, ZERO ground line, "
                   "wheels touch FULLY EMPTY TRANSPARENT BACKGROUND directly, "
                   "long sleek 4-door sedan silhouette with smooth modern lines, "
                   "DARK METALLIC SILVER GREY paint with subtle highlights catching the light, "
                   "clean lowered coilover stance, slammed look but still daily-driveable, "
                   "black aftermarket alloy wheels with multi-spoke pattern, "
                   "low-profile tyres on the wheels, "
                   "tinted rear windows, subtle factory chrome trim around the windows, "
                   "Toyota emblem visible on the front guard, small Camry badge on the boot lid, "
                   "modest aftermarket lip kit at front, small lip spoiler on the boot, "
                   "the car looks like a tuned but understated sleeper — clean Punjabi-Aussie streetwise build, "
                   "highly detailed retro pixel art game sprite on a PURE TRANSPARENT empty background, "
                   "ONLY the car body and wheels drawn, nothing else, "
                   "completely flat side-on silhouette, NO top-down, NO 3-quarter view, ONLY pure side profile",
    "silvia_side": "Nissan Silvia S14 Kouki coupe seen from a strict side profile view, "
                   "viewed from directly beside the car at ground level, "
                   "two wheels visible (left side only), white pearl paint with subtle red stripe, "
                   "deep dish Work Meister wheels, aftermarket spoiler at rear, "
                   "low slung JDM drift car side profile, NO top-down, ONLY side-on profile",
    "wrx_side":    "Subaru WRX rally hatchback seen from a strict side profile view, "
                   "viewed from directly beside the car at ground level, "
                   "two wheels visible (left side only), World Rally Blue paint, "
                   "big black rear wing visible in side view, gold BBS wheels, "
                   "side profile silhouette, NO top-down, ONLY side-on profile",
    "ranger_side": "Ford Ranger Wildtrak lifted 4x4 ute seen from a STRICT DIRECT side profile view, "
                   "camera positioned exactly perpendicular to the truck at ground level on the driver side, "
                   "both passenger-side wheels visible at the bottom — oversized chunky knobbly mud tyres on black mag rims, "
                   "the entire ute length visible from bullbar to towbar, "
                   "matte dark grey/black paint with subtle red pinstripes, "
                   "tall steel bullbar at front with twin LED light bars on top, snorkel intake along driver side, "
                   "lifted suspension giving HIGH stance (taller than a person), "
                   "tray back at rear with toolbox, RANGER decal on door, mud splatter along lower panels, "
                   "Australian country boy work-ute pixel art game sprite, "
                   "highly detailed retro pixel art, "
                   "completely flat side-on silhouette, NO top-down, NO 3 quarter view, ONLY pure side profile"
    ,
    "player_side": "Mitsubishi Lancer Evolution Evo IX sedan seen from a STRICT DIRECT side profile view, "
                  "the car is FACING RIGHT — NOSE / front bumper / headlights on the RIGHT, REAR / taillights on the LEFT, "
                  "FOUR-DOOR SEDAN body style (classic Evo silhouette — boxy aggressive rally sedan), "
                  "pure WHITE paint, glossy and clean, "
                  "lowered coilover suspension, aggressive front bumper with large air intakes, vented bonnet with twin NACA ducts, "
                  "MASSIVE rear wing spoiler over the boot (the iconic Evo wing on tall risers), flared guards, "
                  "deep dish SILVER multi-spoke aftermarket wheels (Enkei RPF1-style), low-profile black tyres, "
                  "TWO CHARACTERS clearly visible inside the cabin through the side windows: "
                  "in the FRONT-LEFT passenger seat (closer to viewer) a young white REDHEAD ESHAY lad wearing a NAVY BLUE NIKE TN CAP with a YELLOW swoosh and a MUSTARD YELLOW JUMPER, head and shoulders visible through the front passenger window, "
                  "in the DRIVER seat (further from viewer, behind the front passenger from this angle) a young dark-haired PROTAGONIST DRIVER in a BLACK ZIP-UP HOODIE with a white tee at the collar, focused expression, hands on the steering wheel, head visible through the rear part of the side window, "
                  "warm orange interior dashboard glow lighting both characters' faces from below, "
                  "windscreen slightly tinted but the two heads clearly readable inside, "
                  "completely flat side-on silhouette, NO top-down, NO 3-quarter view, ONLY pure side profile, "
                  "highly detailed retro pixel art game sprite, "
                  "car FLOATING on a fully transparent background with ZERO ground shadow / ZERO ground line below the wheels",
    "e36_side": "BMW 3-Series E36 sedan from year 1996, four-door sedan body (NOT a coupe), "
                   "seen from a STRICT DIRECT side profile view, "
                   "FLOATING in the empty void with NOTHING below the wheels, "
                   "ZERO ground shadow, ZERO drop shadow, ZERO ground line, ZERO reflective surface, ZERO road, "
                   "the four wheels touch FULLY EMPTY TRANSPARENT BACKGROUND directly, "
                   "absolutely no shading or pixels anywhere below the bottom of the tyres, "
                   "camera positioned exactly perpendicular to the car at ground level on the driver side, "
                   "both passenger-side wheels visible at the bottom of the car body, "
                   "the entire car length visible from nose to boot — classic E36 sedan silhouette with iconic short overhangs and Hofmeister kink rear window, "
                   "faded Cosmos Black paint with peeling clearcoat showing patches of grey primer and lacquer fade, "
                   "distinctive BMW kidney grille at the front, twin round headlights with clear plastic covers, "
                   "black aftermarket wheels stretched on cheap tyres, slammed low coilover suspension, "
                   "M-Sport rear lip spoiler on the boot, M3-style side mirrors, "
                   "bonnet propped slightly open with a wisp of smoke curling up from the engine bay, "
                   "dented front quarter panel, scuffed rear bumper, BEEMER sticker on the boot, "
                   "broken-down Western Sydney eshay street BMW, "
                   "highly detailed retro pixel art game sprite on a PURE TRANSPARENT empty background, "
                   "ONLY the car body and wheels are drawn, nothing else, "
                   "completely flat side-on silhouette, NO top-down, NO 3 quarter view, ONLY pure side profile",
}

print("\n===  SIDE-ON DIALOGUE CARS  ===")
# Brenno's E36 Beemer + Macca's Ranger are showpieces — bigger native size
# (400x200) so they stay crisp when displayed large.
SIDE_CAR_BIG = {"e36_side", "ranger_side", "player_side", "camry_side"}

def _gen_side_car(prompt, w, h, skip_ground=False):
    """Generate a side-on car then strip PixelLab's near-white background +
    any baked-in ground shadow under the car. The shadow strip is critical
    because the wheels often enclose it, hiding it from corner flood-fill.

    skip_ground=True keeps the corner flood-fill (still safely erases the
    background around a centred car) but skips the ground-shadow killer —
    needed for white cars (e.g. player_side Evo) where the ground-shadow
    pass would also erase the lower half of the car body."""
    img = gen_image(prompt, w, h, view="side",
                    outline="single color black outline",
                    shading="medium shading", detail="highly detailed")
    if not img:
        return None
    img = strip_corner_bg(img)
    if not skip_ground:
        img = strip_ground_shadow(img)
    return img

# WHITE-BODIED cars: the ground-shadow killer destroys the car body's lower
# panels because they're also near-white. Corner flood-fill is still safe
# (only touches edge-connected pixels) so we keep that one.
SIDE_CAR_WHITE = {"player_side"}

for car_id, car_desc in SIDE_CARS.items():
    w, h = (400, 200) if car_id in SIDE_CAR_BIG else (200, 100)
    skip = car_id in SIDE_CAR_WHITE
    cached_or_gen(f"car_{car_id}.png",
                  lambda d=car_desc, w=w, h=h, s=skip: _gen_side_car(d, w, h, skip_ground=s))

for car_id, car_desc in CARS.items():
    sheet_file = f"car_{car_id}.png"
    if os.path.exists(os.path.join(OUT_DIR, sheet_file)):
        print(f"  -> {sheet_file}  (cached)")
        continue

    print(f"\n  {car_id} ->")
    frames = []
    for d in DIRS:
        print(f"    {d}...")
        img = gen_image(
            f"pixel art top-down vehicle sprite, {car_desc}, "
            f"facing {d}, single vehicle centered on transparent background, "
            f"overhead perspective, retro 16-bit racing game",
            100, 80, direction=d, view="high top-down",
            outline="single color black outline", shading="medium shading", detail="medium detail")
        frames.append(img.resize((100,80)) if img else Image.new("RGBA", (100,80), (0,0,0,0)))

    if any(f.getbbox() for f in frames):
        make_hstrip(frames, sheet_file)

# -- PORTRAIT BUSTS (for dialogue system) ----------------------------------
print("\n===  PORTRAIT BUSTS  ===")

PORTRAITS_AI = {
    # All portraits target Moey's realism bar — close-up bust, detailed face
    # and shoulders, plain dark navy background, REALISTIC highly detailed
    # pixel art with character-specific facial features and accessories.
    "habibi_smug": (
        "REALISTIC detailed portrait bust of a Lebanese Australian man in his thirties, "
        "olive skin, sharp jawline, well-groomed black stubble beard, slicked black hair, "
        "designer aviator sunglasses on, smug confident smirk showing slight teeth, "
        "white open-collar button-up shirt with sleeves rolled up visible at shoulders, "
        "thick gold chain necklace around neck, gold ring on visible finger, "
        "PLAIN SOLID DARK NAVY BACKGROUND behind the character, no scenery, "
        "close-up face and shoulders, highly detailed pixel art, "
        "64x64 pixel art game portrait, charismatic Liverpool kebab shop owner Moey"
    ),
    "pigcop_default": (
        "REALISTIC detailed portrait bust of a middle-aged stout HUMAN Australian police sergeant, "
        "regular human man face, ruddy pink sunburnt complexion, balding head with grey wisps, "
        "small narrow human eyes squinting, slightly upturned wide nose, double-chin jowls, thick neck, "
        "stern intimidating angry frown, no facial hair, "
        "wearing NSW Police peaked cap with silver insignia, navy blue police collared shirt, "
        "silver POLICE badge visible on chest, epaulettes with sergeant stripes, "
        "PLAIN SOLID DARK NAVY BACKGROUND behind the character, no scenery, "
        "highly detailed close-up bust portrait pixel art, "
        "absolutely a real human police officer, NOT an animal, NOT a furry, NOT anthropomorphic, "
        "64x64 pixel art game portrait, Sergeant from NSW Highway Patrol"
    ),
    "bazza_default": (
        "REALISTIC photo-quality detailed portrait bust of a young white Australian eshay man in his early twenties, "
        "modelled in the EXACT same realism style and detail level as the Moey and Khoa portrait busts, "
        "absolutely NOT cartoony, NOT anime, NOT chibi, "
        "weathered pale milky complexion with light acne scarring scattered across the cheeks, "
        "sharp angular cheekbones, narrow chin, hollow tired pale-blue eyes with dark circles, "
        "intense neutral street stare directly at the viewer, "
        "thin patchy ginger stubble along the jawline and upper lip, "
        "BRIGHT GINGER RED HAIR, messy red mullet haircut, the long thin red rats tail dangling visibly down the side of his neck past his collar onto his shoulder, ginger fringe of hair poking out under the cap brim, "
        "wearing a navy blue Nike TN baseball cap pulled LOW over the eyes casting a deep dramatic shadow across the upper face, "
        "the bright YELLOW Nike swoosh logo prominently visible on the front-side panel of the cap, "
        "a lit Winfield Blue cigarette held crooked in the corner of his mouth, ash glowing red at the tip, "
        "a thin curl of pale grey cigarette smoke trailing past his cheek, "
        "wearing a MUSTARD YELLOW oversized crewneck JUMPER / sweatshirt as the main top garment (NOT a polo shirt, an actual yellow jumper) visible at the shoulders, "
        "a thin tarnished silver chain hanging at the neck above the jumper, "
        "faded blue prison-style knuckle tattoos peeking up from the jumper collar onto the lower neck, "
        "a black Nike Crossbody bum bag strap clearly visible running diagonally across one shoulder over the jumper, "
        "PLAIN SOLID DARK NAVY BLUE BACKGROUND behind the character, no scenery, "
        "intense tight close-up face and shoulders framing, "
        "strong directional cinematic lamp lighting from above casting harsh dramatic shadows on the face, "
        "highly detailed GRITTY REALISTIC pixel art portrait, "
        "RICH MULTI-TONE PIXEL SHADING with at least 4-5 distinct tone bands per surface "
        "(deep shadow / shadow / midtone / highlight / specular catch-light), "
        "smooth pixel-level dithering between tones, defined highlights on the cheekbones, nose bridge, jawline, "
        "deep cast shadows under the cap brim, under the jaw, and inside the eye sockets, "
        "crisp clean linework, sub-pixel anti-aliased edges, harsh contrast shading like a hand-painted bust, "
        "vivid saturated yet grounded skin tones, defined three-dimensional facial structure with NO cartoony exaggeration, "
        "64x64 pixel art game portrait, "
        "gritty Western Sydney eshay BRENNO — the iconic Maccas-carpark hooligan look, "
        "his face should look like the SAME person as the matching full-body Brenno sprite, just zoomed in"
    ),
    "khoa_default": (
        "REALISTIC detailed portrait bust of a young Vietnamese Australian man in his late twenties, "
        "warm smile showing a hint of teeth, friendly brown eyes, "
        "short black hair styled with a subtle undercut, clean-shaven smooth complexion, "
        "slim athletic build, light blue button-up shirt with collar neatly visible at shoulders, "
        "slim silver chain at neck, modern designer watch strap visible, "
        "PLAIN SOLID DARK NAVY BACKGROUND behind the character, no scenery, "
        "close-up face and shoulders, highly detailed pixel art, "
        "64x64 pixel art game portrait, polite plug Khoa from Cabramatta"
    ),
    "player_default": (
        "EXTREME TIGHT CLOSE-UP REALISTIC portrait of a young Australian street racer in his mid-twenties, "
        "the FACE FILLS THE ENTIRE FRAME from forehead to chin, "
        "only the very top of the shoulders and collar visible at the bottom edge, "
        "tan olive skin with painterly subtle complexion detail and natural skin texture, "
        "strong defined jawline with light dark stubble clearly visible, "
        "thick black eyebrows with a thin scar slicing through one of them, "
        "intense focused dark brown eyes with a serious squint, prominent brow ridge, defined nose bridge with subtle nostril shadow, "
        "short cropped dark brown hair styled in a clean faded undercut on the sides, "
        "calm neutral expression with a slight confident smirk at the corner of the mouth, "
        "small gold stud earring visible in one ear, "
        "thick gold chain glimpse at the very bottom of the frame at the neckline, "
        "black zip-up hoodie collar peeking in at the bottom edge with a sliver of white tee, "
        "PLAIN SOLID DARK NAVY BACKGROUND behind the character, no scenery, "
        "richly shaded pixel art with painterly multi-tone skin shading "
        "(deep shadow, midtone, highlight, catchlight) — same realism style and detail level as the Moey portrait bust, "
        "absolutely NOT cartoony, NOT anime, NOT chibi, "
        "64x64 pixel art game portrait, the street-racing protagonist driver"
    ),
    "preet_default": (
        "REALISTIC detailed portrait bust of an Indian Sikh Punjabi Australian man in his thirties, "
        "warm wide friendly grin showing white teeth, kind crinkled brown eyes, brown skin, "
        "full thick well-groomed black beard tied neatly under the chin, "
        "bright royal blue dastar turban neatly wrapped on his head with crisp folds, "
        "kara steel bracelet visible on wrist, white kurta shirt collar with subtle gold embroidery, "
        "bright fluorescent green UberEats food delivery thermal backpack strap visible over shoulder, "
        "PLAIN SOLID DARK NAVY BACKGROUND behind the character, no scenery, "
        "close-up face and shoulders, highly detailed pixel art, "
        "64x64 pixel art game portrait, Harris Park lovable food-loving mainy king Rahul"
    ),
    "macca_default": (
        "REALISTIC detailed portrait bust of a young white Australian country boy in his late twenties, "
        "deeply sun-tanned weathered face, scruffy blonde stubble, "
        "lopsided friendly grin, squinting blue eyes from harsh sun, "
        "sun-bleached blonde-brown hair partly visible, "
        "dusty wide-brim Akubra-style cowboy hat pushed back on his head, "
        "faded light blue flannel shirt unbuttoned over a white Bonds singlet collar visible, "
        "small Southern Cross tattoo barely visible at neckline, "
        "PLAIN SOLID DARK NAVY BACKGROUND behind the character, no scenery, "
        "close-up face and shoulders, highly detailed pixel art, "
        "64x64 pixel art game portrait, Penrith Panthers country boy Macca"
    ),
    "narrator_default": (
        "an OPEN HARDCOVER BOOK lying open showing two visible pages of text, "
        "viewed from a slight three-quarter angle so both pages are visible, "
        "dark leather-bound burgundy cover edges visible, "
        "yellowed parchment pages with faint horizontal lines of black handwritten ink suggesting text, "
        "a small red ribbon bookmark draped across the right page, "
        "warm candlelight glow on the pages, dark ink wisps rising slightly from the page like smoke, "
        "PLAIN SOLID DARK NAVY BLUE BACKGROUND behind the book, no scenery, "
        "centered composition, book fills most of the frame, "
        "highly detailed retro pixel art icon, "
        "storyteller's tome, 64x64 pixel art game portrait icon, "
        "NO characters, NO people, ONLY the book"
    ),
}

for portrait_id, prompt in PORTRAITS_AI.items():
    cached_or_gen(f"portrait_{portrait_id}.png", lambda p=prompt: gen_image(
        p, 64, 64,
        outline="single color black outline", shading="detailed shading", detail="highly detailed",
        no_background=False))


# -- REWARD / TROPHY ITEMS --------------------------------------------------
# One unique item per character, awarded after their suburb is beaten.
# Displayed in the trophy / inventory modal accessible from suburb-select.
print("\n===  REWARD ITEMS  ===")
REWARDS = {
    "curry_powder": (
        "small detailed pixel art icon of a brown paper grocery bag from an Indian grocer, "
        "top folded over, colourful red and yellow spice packets visible peeking out of the top, "
        "small handwritten APNA DERA price sticker on the side of the bag, "
        "a faint trail of yellow turmeric dust around the bag, "
        "PLAIN SOLID DARK NAVY BLUE BACKGROUND, no scenery, "
        "centred composition, rich multi-tone shading, "
        "64x64 pixel art reward item icon, highly detailed realistic"
    ),
    "samosa": (
        "small detailed pixel art icon of a golden brown deep-fried Indian samosa pastry triangle, "
        "wrapped at the bottom in a sheet of greaseproof paper, steam wisp rising from the top, "
        "a small green coriander sprig and a dollop of red tamarind chutney on the paper next to it, "
        "PLAIN SOLID DARK NAVY BLUE BACKGROUND, no scenery, "
        "centred composition, rich multi-tone shading, "
        "64x64 pixel art reward item icon, highly detailed realistic food"
    ),
    "ongbay": (
        "small detailed pixel art icon of a clear plastic ziplock bag full of bright vivid green "
        "cannabis buds visible through the bag, the zip seal across the top of the bag, "
        "a small brass herb grinder sitting next to the bag, "
        "PLAIN SOLID DARK NAVY BLUE BACKGROUND, no scenery, "
        "centred composition, rich multi-tone shading, "
        "64x64 pixel art reward item icon, highly detailed realistic, NO faces NO people"
    ),
    "bong": (
        "small detailed pixel art icon of a tall vertical glass smoking waterpipe with a DOUBLE PERCOLATOR design "
        "(two stacked round percolators visible in the middle of the chamber), "
        "clear glass body with bright green water in the base chamber, blue glass downstem, "
        "small bowl piece sticking out the side of the lower stem, "
        "PLAIN SOLID DARK NAVY BLUE BACKGROUND, no scenery, "
        "centred composition, rich multi-tone shading with glassy highlights, "
        "64x64 pixel art reward item icon, highly detailed realistic glass object"
    ),
    "coil_pack": (
        "small detailed pixel art icon of a BMW M52 ignition coil pack automotive part, "
        "BLACK PLASTIC housing in a distinctive rectangular vertical-tower shape — "
        "tall narrow boxy form with a flared rectangular top cap and a tapered rubber boot at the bottom, "
        "RAISED WHITE 'BMW' lettering embossed on the front face of the upper section, "
        "a smaller 'M52' label below the BMW logo, "
        "small WHITE-PAINTED 3-pin electrical connector socket sticking out the upper SIDE of the housing, "
        "black rubber boot at the very bottom flaring open like a cup, "
        "subtle silver highlight along the edges showing the moulded plastic shape, "
        "shown standing UPRIGHT (boot at bottom, connector top), "
        "PLAIN SOLID DARK NAVY BLUE BACKGROUND, no scenery, "
        "centred composition, rich multi-tone shading with glossy plastic sheen, "
        "64x64 pixel art reward item icon, highly detailed realistic automotive part, "
        "should be CLEARLY recognisable as an ignition coil pack"
    ),
    "trophy": (
        "small detailed pixel art icon of a shiny gold metallic drag racing TROPHY, "
        "classic two-handled cup shape on a black marble base, "
        "a small gold V8 engraving on the cup, "
        "engraved silver plate on the base reading EASTERN CREEK DRAGS WINNER, "
        "warm gold reflective highlights catching the light, "
        "PLAIN SOLID DARK NAVY BLUE BACKGROUND, no scenery, "
        "centred composition, rich multi-tone shading with gold metallic shine, "
        "64x64 pixel art reward item icon, highly detailed realistic gold metallic object"
    ),
}
for reward_id, prompt in REWARDS.items():
    cached_or_gen(f"reward_{reward_id}.png", lambda p=prompt: gen_image(
        p, 64, 64,
        outline="single color black outline", shading="detailed shading", detail="highly detailed",
        no_background=False))


# -- TOP-DOWN RACE TILES (vertical scroll Spy-Hunter style) -----------------
print("\n===  TOP-DOWN RACE TILES  ===")

# NOTE: road_tile.png is no longer generated by PixelLab — the road in
# the race engine is now hand-drawn pixel art (see buildRoadTile() in
# index.html). The old road_tile.png file may still exist in sprites/
# but it's no longer loaded by the game.

# Western Sydney suburb roadside strips - tileable, vertical scroll.
# These show what's beside the road as you drive past it (buildings, shops, fences).
cached_or_gen("side_parra.png", lambda: gen_image(
    "pixel art aerial top down view of FLAT BUILDING ROOFTOPS seen from straight above, "
    "rectangular flat roofs of low shops and warehouses, "
    "air conditioning units, vents, skylights, parapets, water tanks, satellite dishes, "
    "patches of moss on the corrugated metal, "
    "warm orange streetlamp light bleeding onto roof edges, no road visible, no sidewalk visible, "
    "ONLY ROOFTOPS from a bird's eye view, "
    "tileable vertically so the top edge matches the bottom edge, "
    "Parramatta west syd late night, 16-bit retro pixel art",
    130, 320, view="high top-down",
    outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

cached_or_gen("side_blacktown.png", lambda: gen_image(
    "pixel art aerial top down view of FLAT BUILDING ROOFTOPS seen from straight above, "
    "rectangular flat roofs of discount shops and fast food stores, "
    "rusty air conditioning units, exhaust vents, graffiti tags on roof tar, "
    "broken skylights, rooftop bins, satellite dishes, "
    "no road, no sidewalk, ONLY ROOFTOPS from a bird's eye view, "
    "tileable vertically, "
    "Blacktown west syd late night, 16-bit retro pixel art, gritty urban",
    130, 320, view="high top-down",
    outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

cached_or_gen("side_cabramatta.png", lambda: gen_image(
    "pixel art aerial top down view of FLAT BUILDING ROOFTOPS seen from straight above, "
    "rectangular flat roofs of Asian markets and restaurants, "
    "air conditioning units, vents, large extractor fans for kitchens, "
    "red Chinese lanterns dangling between rooftops, strung fairy lights, "
    "warm coloured neon glow bleeding onto roof edges from streetlamps below, "
    "no road, no sidewalk, ONLY ROOFTOPS from a bird's eye view, "
    "tileable vertically, "
    "Cabramatta west syd late night, 16-bit retro pixel art, festive lights",
    130, 320, view="high top-down",
    outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

cached_or_gen("side_penrith.png", lambda: gen_image(
    "pixel art aerial top down view of FLAT BUILDING ROOFTOPS, "
    "corrugated iron roofs of country panel beater shops and tyre stores, "
    "round water tanks, satellite dishes, rust patches, exhaust vents, "
    "scattered gum trees and dirt patches between buildings, "
    "no road, no sidewalk, ONLY ROOFTOPS from a bird's eye view, "
    "tileable vertically, "
    "Penrith country edge of west syd at night, 16-bit retro pixel art",
    130, 320, view="high top-down",
    outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

# Penrith hill-climb parallax backdrop — wide side-on landscape strip
# showing Blue Mountains far horizon + middle-ground paddock with Penrith
# Panthers stadium lights + foreground gum trees + dusk sky. Tileable
# horizontally. Used by Macca's 4x4 hill climb mini-game.
cached_or_gen("bg_penrith_hill.png", lambda: gen_image(
    "pixel art side-on horizontal landscape backdrop for a 2D side-scrolling racing game, "
    "wide panoramic strip view at dusk, "
    "FAR DISTANT Blue Mountains silhouette across the entire horizon in deep purple-blue, "
    "MIDDLE GROUND large NSW country paddocks with sun-bleached yellow grass, "
    "wonky weathered timber fence posts and rusted barbed wire stretching across, "
    "a distant Penrith Panthers stadium with four tall floodlight pylons casting warm light, "
    "a couple of scattered tin-roof country sheds with corrugated iron, "
    "a windmill water pump turning slowly, scattered sheep tiny in the distance, "
    "FOREGROUND tall thin Australian gum trees with peeling white bark and red-orange leaves, "
    "a wooden dirt-track fence in the immediate foreground, "
    "dusky sky with warm orange sunset transitioning to deep purple high up, "
    "scattered pink-orange clouds, the first evening stars beginning to twinkle, "
    "NO road, NO cars, NO characters, ONLY the landscape, "
    "tileable horizontally so it can scroll seamlessly side-to-side, "
    "highly detailed retro 16-bit pixel art, Western Sydney country edge",
    400, 200, view="side",
    outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

cached_or_gen("side_liverpool.png", lambda: gen_image(
    "pixel art aerial top down view of FLAT BUILDING ROOFTOPS in Liverpool south west syd, "
    "rectangular flat roofs of late-night shisha lounges, kebab shops, sweets shops, "
    "shiny extractor fans for charcoal grills, large air conditioning units, "
    "fairy lights strung between rooftops, warm orange streetlamp glow on roof edges, "
    "no road, no sidewalk, ONLY ROOFTOPS from a bird's eye view, "
    "tileable vertically, "
    "Liverpool late night, 16-bit retro pixel art, warm Lebanese-Australian vibe",
    130, 320, view="high top-down",
    outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

# Traffic cars - high top-down north (facing up) for the new race engine.
# Sized to feel like civilian cars on the road.
cached_or_gen("traffic_camry_topdown.png", lambda: gen_image(
    "pixel art top-down view of a silver-grey Toyota Camry sedan, "
    "strict bird's-eye view looking straight down on the roof, "
    "the car is driving NORTH (UP the image), so we see the back of the car from above — "
    "the FRONT BONNET / WINDSCREEN is at the TOP of the image (far from viewer), "
    "the REAR BOOT / TAILLIGHTS / NUMBER PLATE are at the BOTTOM of the image (close to viewer), "
    "two red rectangular taillight blocks visible along the BOTTOM edge, "
    "four wheels visible at the corners, sunroof rectangle visible in the centre of the roof, "
    "long rectangular silhouette oriented vertically, "
    "centred on transparent background, retro 16-bit arcade racing game civilian car",
    80, 110, direction="north", view="high top-down",
    outline="single color black outline", shading="medium shading", detail="medium detail"))

cached_or_gen("traffic_van_topdown.png", lambda: gen_image(
    "pixel art top-down view of a plain white delivery van, "
    "strict bird's-eye view looking straight down on the roof, "
    "the van is driving NORTH (UP the image), so we see the rear of the van from above — "
    "the FRONT BONNET / WINDSCREEN is at the TOP of the image (far from viewer), "
    "the TWIN REAR DOORS / red taillights are at the BOTTOM of the image (close to viewer), "
    "boxy white roof panels with a cargo hatch, four wheels at the corners, "
    "long tall rectangular silhouette oriented vertically, "
    "centred on transparent background, retro 16-bit arcade racing game delivery van",
    90, 130, direction="north", view="high top-down",
    outline="single color black outline", shading="medium shading", detail="medium detail"))

cached_or_gen("traffic_ute_topdown.png", lambda: gen_image(
    "pixel art top-down view of an old beaten-up Australian Holden ute pickup truck, "
    "strict bird's-eye view looking straight down on the roof + tray, "
    "the ute is driving NORTH (UP the image), so we see the rear of the ute from above — "
    "the FRONT BONNET / CABIN ROOF / WINDSCREEN is at the TOP HALF of the image (far from viewer), "
    "the OPEN TRAY BACK with tools and a toolbox at the BOTTOM HALF of the image (close to viewer, with the tailgate at the very bottom edge), "
    "rusty brown paint, four wheels at the corners, "
    "long rectangular silhouette oriented vertically, "
    "centred on transparent background, retro 16-bit arcade racing game work ute",
    80, 110, direction="north", view="high top-down",
    outline="single color black outline", shading="medium shading", detail="medium detail"))


# -- TITLE-SCREEN ANIMATED GIFS --------------------------------------------
# Generate a perspective road + a city skyline at 400x400, then animate
# each into a looping GIF (road scrolls toward viewer, city twinkles).
print("\n===  TITLE-SCREEN GIFS  ===")

import random

def make_road_scroll_gif(src_path, out_path, frames=16, duration=70):
    """Scroll the source image down so it appears to move toward viewer."""
    src = Image.open(src_path).convert("RGB")
    w, h = src.size
    frame_imgs = []
    for i in range(frames):
        offset = int(i * h / frames)
        frame = Image.new("RGB", (w, h), (5, 6, 14))
        # Wrap-around: draw twice so the scroll loops seamlessly
        frame.paste(src, (0, offset))
        frame.paste(src, (0, offset - h))
        frame_imgs.append(frame.convert("P", palette=Image.ADAPTIVE, colors=128))
    frame_imgs[0].save(
        out_path, save_all=True, append_images=frame_imgs[1:],
        duration=duration, loop=0, optimize=True, disposal=2
    )
    kb = os.path.getsize(out_path) // 1024
    print(f"      OK {os.path.basename(out_path)}  ({w}x{h}, {frames}f, {kb}kb)")


def make_side_scroll_gif(src_path, out_path, frames=16, duration=70):
    """Scroll the source image LEFT (i.e. world moves RIGHT-to-LEFT so the
    viewer feels they are driving LEFT-to-RIGHT past stationary scenery).
    Source should be a wide tileable horizontal strip."""
    src = Image.open(src_path).convert("RGB")
    w, h = src.size
    frame_imgs = []
    for i in range(frames):
        offset = int(i * w / frames)
        frame = Image.new("RGB", (w, h), (5, 6, 14))
        # Draw twice so the horizontal wrap is seamless
        frame.paste(src, (-offset, 0))
        frame.paste(src, (w - offset, 0))
        frame_imgs.append(frame.convert("P", palette=Image.ADAPTIVE, colors=128))
    frame_imgs[0].save(
        out_path, save_all=True, append_images=frame_imgs[1:],
        duration=duration, loop=0, optimize=True, disposal=2
    )
    kb = os.path.getsize(out_path) // 1024
    print(f"      OK {os.path.basename(out_path)}  ({w}x{h}, {frames}f, {kb}kb)")


def make_city_twinkle_gif(src_path, out_path, frames=10, duration=180):
    """Add randomised window-light flicker on a static city image."""
    src = Image.open(src_path).convert("RGB")
    w, h = src.size
    # Find bright pixels (windows, neon signs) — these get the flicker treatment
    px = src.load()
    bright = []
    for y in range(int(h * 0.85)):  # avoid the very bottom (road area)
        for x in range(w):
            r, g, b = px[x, y]
            # warm bright pixel = likely a light
            if (r + g + b) > 480 and r > b:
                bright.append((x, y))
    rng = random.Random(42)  # deterministic so re-runs don't diff massively
    frame_imgs = []
    for i in range(frames):
        frame = src.copy()
        fpx = frame.load()
        # Randomly dim ~12% of bright pixels per frame
        for x, y in bright:
            if rng.random() < 0.12:
                r, g, b = fpx[x, y]
                fpx[x, y] = (max(0, r-90), max(0, g-90), max(0, b-90))
        frame_imgs.append(frame.convert("P", palette=Image.ADAPTIVE, colors=128))
    frame_imgs[0].save(
        out_path, save_all=True, append_images=frame_imgs[1:],
        duration=duration, loop=0, optimize=True, disposal=2
    )
    kb = os.path.getsize(out_path) // 1024
    print(f"      OK {os.path.basename(out_path)}  ({w}x{h}, {frames}f, {kb}kb)")


# Source images — generated by PixelLab. Both 400x400, same night palette so
# they tie together visually when stacked on the title screen.
cached_or_gen("title_road_src.png", lambda: gen_image(
    "pixel art perspective view of a four lane road at night going into the distance, "
    "looking down the road from the driver point of view, vanishing point near the top of the image, "
    "dark asphalt with dashed yellow lane lines down the middle, "
    "warm orange street lamp glow on the road surface, "
    "narrow strip of dark sidewalk on each side, no cars, no buildings, "
    "1990s arcade racing game pixel art, deep orange and dark blue colour palette",
    400, 400, view="side",
    outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

cached_or_gen("title_city_src.png", lambda: gen_image(
    "pixel art city skyline silhouette at night, just buildings against the sky, "
    "rooftops of mixed height apartment blocks and low rise office buildings, "
    "lit warm yellow windows scattered across the building faces, "
    "deep navy night sky filling the upper half with a scattering of small stars, "
    "no road visible, no street lamps, no shopfronts, no people, no signs — "
    "ONLY building silhouettes and the night sky above, "
    "warm orange glow from a distant horizon line at the very bottom edge, "
    "1990s arcade pixel art aesthetic, deep blue + warm amber palette",
    400, 400, view="side",
    outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

# Animate them
road_src = os.path.join(OUT_DIR, "title_road_src.png")
city_src = os.path.join(OUT_DIR, "title_city_src.png")
if os.path.exists(road_src):
    make_road_scroll_gif(road_src, os.path.join(OUT_DIR, "title_road.gif"))
if os.path.exists(city_src):
    make_city_twinkle_gif(city_src, os.path.join(OUT_DIR, "title_city.gif"))


# Transition driving animation — played between suburbs as a side-scrolling
# Sydney night cityscape. The player's car sprite is overlaid in JS while
# the city slides past behind it.
cached_or_gen("transition_drive_src.png", lambda: gen_image(
    "pixel art side-on Sydney night cityscape at 11pm, wide horizontal panoramic strip, "
    "tall high-rise apartment buildings and office towers of varying heights along the back, "
    "many warm yellow and cool white lit windows scattered randomly across the building faces, "
    "a few buildings with red neon signs on the rooftops and vertical neon shop signs, "
    "MIDDLE GROUND lower-rise late-night shop fronts at the street level with glowing yellow shop window glow, "
    "kebab shop and 7-Eleven type fluorescent signs, traffic light poles, "
    "tangled black power lines running across the middle of the frame between wooden poles, "
    "FOREGROUND a strip of road with warm orange streetlamp pools, "
    "a low concrete kerb along the very bottom, "
    "SKY deep navy blue night with a sprinkling of small white stars, "
    "a faint warm orange horizon glow at the building tops, "
    "tiny silhouettes of distant office tower aerials, "
    "NO cars, NO people, tileable horizontally for seamless side-scroll, "
    "highly detailed 16-bit pixel art, warm Sydney night urban aesthetic, "
    "deep navy + amber + magenta neon palette",
    400, 128, view="side",
    outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

transition_src = os.path.join(OUT_DIR, "transition_drive_src.png")
if os.path.exists(transition_src):
    make_side_scroll_gif(transition_src, os.path.join(OUT_DIR, "transition_drive.gif"),
                         frames=20, duration=60)


# Engine bay — animate with subtle electrical flicker (sparks from the
# dodgy coil pack) and a faint vibration jitter (cylinder misfire).
def make_engine_flicker_gif(src_path, out_path, frames=10, duration=120):
    src = Image.open(src_path).convert("RGB")
    w, h = src.size
    # Find brighter pixels (highlights, exposed wire ends) for spark flicker
    px = src.load()
    spark_candidates = []
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if r + g + b > 360 and r > b:  # warm bright = wire/spark candidate
                spark_candidates.append((x, y))
    rng = random.Random(7)
    frame_imgs = []
    for i in range(frames):
        # Slight horizontal jitter every other frame (vibration)
        jx = -1 if i % 3 == 0 else (1 if i % 3 == 1 else 0)
        frame = Image.new("RGB", (w, h), (5, 5, 10))
        frame.paste(src, (jx, 0))
        fpx = frame.load()
        # Random electrical sparks ~20 per frame
        for _ in range(20):
            if not spark_candidates: break
            x, y = rng.choice(spark_candidates)
            # Bright white-blue spark
            r2 = rng.random()
            col = (255, 255, 200) if r2 < 0.6 else (180, 220, 255)
            fpx[x, y] = col
            # Surrounding glow
            for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]:
                nx, ny = x+dx, y+dy
                if 0 <= nx < w and 0 <= ny < h:
                    cr, cg, cb = fpx[nx, ny]
                    fpx[nx, ny] = (
                        min(255, cr + 80),
                        min(255, cg + 80),
                        min(255, cb + 60),
                    )
        frame_imgs.append(frame.convert("P", palette=Image.ADAPTIVE, colors=128))
    frame_imgs[0].save(
        out_path, save_all=True, append_images=frame_imgs[1:],
        duration=duration, loop=0, optimize=True, disposal=2
    )
    kb = os.path.getsize(out_path) // 1024
    print(f"      OK {os.path.basename(out_path)}  ({w}x{h}, {frames}f, {kb}kb)")


engine_src = os.path.join(OUT_DIR, "engine_bay_src.png")
if os.path.exists(engine_src):
    make_engine_flicker_gif(engine_src, os.path.join(OUT_DIR, "engine_bay.gif"))


# -- CINEMATIC STORY-BEAT GIFs ---------------------------------------------?
# Big animated overlays at key narrative beats. Each is a 400x400 PixelLab
# source image post-processed with a fitting animation helper, then loaded
# at runtime via the SCENE_IMAGE_SRCS map in index.html.
print("\n===  STORY-BEAT GIFs  ===")

def make_siren_flash_gif(src_path, out_path, frames=8, duration=140):
    """Pulse alternating red and blue siren tint across the upper half of the
    image — sells the cop strobe. Source should already have the siren glow
    baked in; this just adds the rhythmic colour cycle on top."""
    src = Image.open(src_path).convert("RGB")
    w, h = src.size
    band_h = int(h * 0.55)
    frame_imgs = []
    for i in range(frames):
        frame = src.copy().convert("RGB")
        phase = i % 4
        tint = None
        if phase == 0: tint = (255, 40, 40)      # red beat
        elif phase == 2: tint = (60, 80, 255)    # blue beat
        if tint:
            overlay = Image.new("RGB", (w, band_h), tint)
            top = frame.crop((0, 0, w, band_h))
            blended = Image.blend(top, overlay, 0.20)
            frame.paste(blended, (0, 0))
        frame_imgs.append(frame.convert("P", palette=Image.ADAPTIVE, colors=128))
    frame_imgs[0].save(out_path, save_all=True, append_images=frame_imgs[1:],
                       duration=duration, loop=0, optimize=True, disposal=2)
    kb = os.path.getsize(out_path) // 1024
    print(f"      OK {os.path.basename(out_path)}  ({w}x{h}, {frames}f, {kb}kb)")


# Rahul's 720 burnout — plays on the rahul_arrival narrator beat in preet_intro
cached_or_gen("rahul_burnout_src.png", lambda: gen_image(
    "pixel art 3/4 top-down view of a heavily modified grey Toyota Camry sleeper sedan "
    "mid-burnout in a small suburban roundabout at night, the Camry spinning sideways "
    "with THICK WHITE TYRE SMOKE billowing in a wide circular arc behind the rear wheels, "
    "headlight beams cutting through the smoke cloud, the smoke catching warm orange streetlamp glow, "
    "the roundabout's brick centre island visible with a small painted-white kerb ring, "
    "Harris Park Wigram Street Indian shops in the background — sari fabric store with colourful saris in window, "
    "Indian sweets shop with bright yellow signage and trays of mithai in the window, "
    "narrow side street with fairy lights strung overhead, "
    "deep navy night sky with a sprinkling of small stars, "
    "dramatic dynamic action moment, motion blur lines on the spinning car body, "
    "1990s arcade racing pixel art aesthetic, deep navy + warm orange + thick white smoke palette, "
    "highly detailed atmospheric",
    400, 400, view="side",
    outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

rahul_src = os.path.join(OUT_DIR, "rahul_burnout_src.png")
if os.path.exists(rahul_src):
    # Engine-flicker effect sells the smoke shimmer + slight jitter for motion
    make_engine_flicker_gif(rahul_src, os.path.join(OUT_DIR, "rahul_burnout.gif"))


# Cop chase — plays on the Westfield brenno_sprint + cop_chase_intro beats.
cached_or_gen("cop_chase_src.png", lambda: gen_image(
    "pixel art rear-three-quarter view of a young runner sprinting away across a dark "
    "fluorescent-lit Westfield Mt Druitt bottom carpark at midnight, "
    "the back of the protagonist visible in the foreground mid-stride, arms pumping, "
    "beyond him TWO NSW POLICE OFFICERS in navy uniforms chasing with TORCH BEAMS sweeping across the bitumen, "
    "blue and red SIREN GLOW washing over the painted parking bay lines from a "
    "stationary NSW Highway Patrol Commodore parked at the edge with its lightbar on full, "
    "abandoned shopping trolleys scattered around the trolley bay, "
    "low fluorescent ceiling lights overhead casting harsh white pools, "
    "the closed Westfield mall facade silhouetted in the background, "
    "tense urgent action moment, motion blur on the runner's legs, "
    "1990s arcade pixel art chase scene, deep midnight blue + harsh fluorescent white "
    "+ red and blue siren highlights, highly detailed atmospheric",
    400, 400, view="side",
    outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

cop_src = os.path.join(OUT_DIR, "cop_chase_src.png")
if os.path.exists(cop_src):
    make_siren_flash_gif(cop_src, os.path.join(OUT_DIR, "cop_chase.gif"))


# Eastern Creek dragstrip — plays on the snout_intro opening narrator beat.
cached_or_gen("drag_strip_src.png", lambda: gen_image(
    "pixel art Eastern Creek Raceway drag strip on Saturday night, "
    "viewed from a low perspective behind the staging area looking DOWN two side-by-side lanes "
    "that vanish into the distance toward the quarter mile beam, "
    "the iconic CHRISTMAS TREE STARTING LIGHT TOWER on the right with stacked AMBER and GREEN bulbs glowing brightly, "
    "tall white floodlight pylons illuminating the strip in pools of harsh white light, "
    "distant grandstand silhouettes faintly visible, low-rise pit garages on the left, "
    "TWO RACE CARS at the staging line — a tuned white import on the near lane "
    "and a NSW Highway Patrol Commodore SS on the far lane with its lightbar off, "
    "thin exhaust heat haze rising off both bonnets, "
    "painted bright white start lines and quarter-mile markings on the tarmac, "
    "scattered orange flag markers along the strip edges, "
    "deep navy night sky above with a sprinkling of small stars, "
    "dramatic atmospheric anticipation moment, the final showdown about to start, "
    "1990s arcade racing pixel art, deep navy + warm amber + electric green "
    "+ harsh floodlight white palette, highly detailed",
    400, 400, view="side",
    outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

drag_src = os.path.join(OUT_DIR, "drag_strip_src.png")
if os.path.exists(drag_src):
    # Engine-flicker = christmas tree bulbs twinkle + faint heat shimmer
    make_engine_flicker_gif(drag_src, os.path.join(OUT_DIR, "drag_strip.gif"))


# -- Summary ----------------------------------------------------------------
print(f"\n{'-'*50}")
print(f"OK  Sprites saved to: {OUT_DIR}")
if ERRORS:
    print(f"FAIL  {len(ERRORS)} failed:")
    for e in ERRORS:
        print(f"   - {e}")
print("   Reload the game preview to use them.\n")

