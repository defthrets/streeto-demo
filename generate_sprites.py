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
              init_image=None,
              init_image_strength=300,
              retries=2):
    """Call PixelLab and return a PIL Image (RGBA), or None on failure.

    When `init_image` (PIL Image) is provided, it's passed as the PixelLab
    init_image for image-to-image consistency. `init_image_strength` is the
    PixelLab 0-999 noise floor: lower = more freedom from the reference,
    higher = stay closer. For character expression variation, 250-400 is
    a good range (keeps face/outfit consistent, lets expression change)."""
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

    if init_image is not None:
        # Pass the reference image as base64 for PixelLab to use as a starting
        # point. This produces character-consistent variations across states.
        buf = io.BytesIO()
        init_image.convert("RGBA").save(buf, format="PNG")
        b64_init = base64.b64encode(buf.getvalue()).decode("ascii")
        payload["init_image"] = {"type": "base64", "base64": b64_init}
        payload["init_image_strength"] = init_image_strength

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
    "pixel art bird's eye top down view straight down into a TRASHED BMW E36 3-Series engine bay, "
    "the surrounding car body / bonnet edges / fenders are FADED ROYAL BLUE paint "
    "(BMW Estoril Blue heavily oxidised — scuffed, scratched, patches of dull grey primer showing, "
    "sun-bleached uneven patches, thick black oil splatters streaked across the paint, "
    "dust + grime in the seams), "
    "engine bay walls + strut towers same FADED BLUE with brown rust-bloom around bolt heads, "
    "black grease handprints smeared everywhere, "
    "BMW kidney grille peeking in at the front edge with dead bugs splattered on it, "
    "containing the iconic BMW M52B28 2.8 litre DOHC inline SIX cylinder engine in the centre, "

    "ABSOLUTELY NO PLASTIC ENGINE COVER, NO COSMETIC COVER, NO BMW 24V badge plate, "
    "NO SMOOTH BLACK PLASTIC SHROUD over the top of the engine — that piece is OFF, missing, removed entirely, "
    "the engine is RAW + STRIPPED, "
    "what you see in the centre is the CAST ALUMINIUM VALVE COVER (rough silver-grey metal, "
    "with twelve hex-head bolts around its perimeter, some clearly aftermarket mismatched bolts), "
    "directly mounted on the valve cover are SIX BLACK PLASTIC IGNITION COIL PACKS standing UPRIGHT "
    "in a NEAT VERTICAL ROW (one per cylinder — small black rectangular blocks with electrical "
    "connectors plugged into the top, each maybe 1.5 inches across), "
    "the six coils are the dominant visual element in the middle of the bay, not hidden under anything, "
    "one coil on cylinder four is OBVIOUSLY CRACKED IN HALF with its spark plug wire dangling, "
    "the yellow plastic oil filler cap (with tiny BMW logo) sits in the FRONT-LEFT corner of the valve cover, "
    "thick black oil seepage staining down the side of the cast aluminium head, "
    "the exposed BMW M52 inline-six valve cover with raised cooling ribs running lengthwise visible to either side of the coil row, "

    "large black plastic air intake plenum on the right side with 'M50' stamped on it, "
    "curved black plastic intake manifold runners arching across into the head, "
    "ribbed black intake hose snaking from the airbox to the throttle body, "
    "round black BMW air filter housing top-left, "
    "translucent white coolant overflow reservoir with green BMW cap on the upper right, "
    "white plastic brake master cylinder reservoir with black cap on the upper left, "
    "yellow ABS pump unit visible bottom-left, "
    "BMW strut tower brace bolted across the top — rusty, crooked, smeared with black grease, "

    "VERY DODGY BACKYARD MECHANIC WIRING — exposed colourful wires sticking out everywhere, "
    "tangled bundles of red, yellow, blue and black wires NOT TUCKED IN PROPERLY, "
    "loose wire ends with stripped copper visible, alligator clips clamped on terminals, "
    "two random wires twisted together with electrical tape coming undone, "
    "silver duct tape going grey/yellow from age wrapped messily around big bundles, "
    "loose plastic zip-ties dangling, "
    "a mismatched aftermarket relay box hanging off the strut tower by one bolt, "

    "THICK BLACK OIL STAINS AND GREASE SPLATTERED EVERYWHERE — "
    "around the valve cover, dripping down the block, pooled in the strut towers, smeared on the wires, "
    "dust + cobwebs in every corner, leaves and bits of bark stuck in the cowl panel, "

    "a clearly visible RED-and-YELLOW BUNDABERG GINGER BEER can sitting on the strut tower "
    "(iconic Bundy polar bear mascot on the label, small can, dented/crushed, oily fingerprints), "
    "half-smoked cigarette butts stubbed out on the strut tower with grey ash, "
    "an oily rag draped over the air intake, "
    "scattered nuts and bolts loose on the engine bay, "
    "missing intake heat shield, missing engine ground strap (replaced by a piece of fence wire), "

    "late night under a single workshop lamp casting deep shadows + hard contrast, "
    "1990s 2000s Western Sydney eshay backyard-mechanic aesthetic, "
    "EXTREMELY GRIMY DODGY NEGLECTED — looks like it's been hammered for 20 years and never serviced, "
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
        "REALISTIC GRITTY pixel art full-body character sprite of a real human person, "
        "TALL LANKY SKINNY young white Australian country boy "
        "wearing a dusty wide-brim AKUBRA COWBOY HAT (the hat is essential — never omit it, brown felt with a leather band) "
        "and a faded light blue FLANNEL shirt unbuttoned over a clean white Bonds SINGLET, "
        "absolutely NOT cartoony, NOT anime, NOT chibi — modelled at the same realism bar as the Moey AND Khoa character sprites, "
        "real name Brett, late twenties (full-height standing figure NOT a bust NOT a child), "
        "very slim narrow build with thin lanky arms and thin legs, narrow shoulders, "
        "ABSOLUTELY NO stocky bulk, NO broad shoulders, NO muscle mass — wiry farm-thin proportions, "
        "rangy beanpole physique like he hasn't put on weight since high school, "
        "deeply sun-tanned weathered face with sharp angular cheekbones and a strong jawline, "
        "scruffy DARK BROWN stubble along the jaw, lopsided friendly grin, "
        "squinting blue eyes crinkled from harsh sun, DARK BROWN hair partly visible under the Akubra brim, "
        "defined three-dimensional facial structure, "
        "the Akubra brim shading his eyes, "
        "the flannel hanging LOOSE on his thin frame, sleeves rolled up to the elbows, "
        "faded blue Wrangler JEANS slim through the leg tucked into worn brown leather steel-toe WORK BOOTS, "
        "big silver oval rodeo BELT BUCKLE clearly visible, leather wallet chain on hip, "
        "relaxed posture, thumbs hooked into the belt loops, "
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
    "silvia_side": "Nissan Silvia S14 Kouki coupe from year 1998, two-door coupe body, "
                   "seen from a STRICT DIRECT side profile view, "
                   "the car is FACING RIGHT — nose / front bumper / headlights on the RIGHT, REAR / taillights on the LEFT, "
                   "FLOATING in empty space with NOTHING below the wheels — "
                   "ZERO ground shadow, ZERO drop shadow, ZERO ground line, ZERO road, ZERO reflective surface, "
                   "wheels touch FULLY EMPTY TRANSPARENT BACKGROUND directly, "
                   "absolutely no shading or pixels anywhere below the bottom of the tyres, "
                   "camera positioned exactly perpendicular to the car at ground level on the driver side, "
                   "both passenger-side wheels visible at the bottom of the car body, "
                   "the entire car length visible from nose to boot — iconic low-slung S14 Kouki silhouette "
                   "with sleek long roofline, short overhangs, and the distinctive Kouki projector headlights, "
                   "PEARL WHITE paint with subtle metallic shimmer catching the light, "
                   "S14 Kouki projector headlights with clear plastic covers and amber indicator strips at the front, "
                   "deep-dish gunmetal WORK MEISTER aftermarket alloy wheels (multi-spoke), low-profile black tyres, "
                   "slammed lowered coilover stance with aggressive negative camber on all four wheels, "
                   "aggressive aftermarket front lip splitter, aero side skirts, "
                   "modest GT-style rear wing on the boot lid, "
                   "tinted side windows, JDM drift car build but kept clean as a daily driver, "
                   "small Vietnamese flag sticker on the rear quarter window as a personal touch, "
                   "subtle Cabramatta street-tuner detailing, "
                   "highly detailed retro pixel art game sprite on a PURE TRANSPARENT empty background, "
                   "ONLY the car body and wheels are drawn, nothing else, "
                   "completely flat side-on silhouette, NO top-down, NO 3-quarter view, ONLY pure side profile",
    "wrx_side":    "Subaru WRX rally hatchback seen from a strict side profile view, "
                   "viewed from directly beside the car at ground level, "
                   "two wheels visible (left side only), World Rally Blue paint, "
                   "big black rear wing visible in side view, gold BBS wheels, "
                   "side profile silhouette, NO top-down, ONLY side-on profile",
    "ranger_side": "OLD 1990s-era classic Toyota Hilux 4x4 dual-cab work ute (NOT modern — late "
                   "80s / early 90s LN106 style with the iconic boxy chunky silhouette, "
                   "rectangular sealed-beam headlights, simple horizontal grille, slab-sided body), "
                   "seen from a STRICT DIRECT side profile view, "
                   "the truck is FACING RIGHT — nose / front bumper / headlights on the RIGHT, "
                   "REAR / tray-back / taillights on the LEFT, "
                   "FLOATING in empty space with NOTHING below the wheels — "
                   "ZERO ground shadow, ZERO drop shadow, ZERO ground line, "
                   "the four wheels touch FULLY EMPTY TRANSPARENT BACKGROUND directly, "
                   "absolutely no shading or pixels anywhere below the bottom of the tyres, "
                   "camera positioned exactly perpendicular to the truck at ground level on the driver side, "
                   "both passenger-side wheels visible at the bottom — MASSIVE 35-INCH MUD-TERRAIN TYRES "
                   "(huge knobbly aggressive lugs, very deep tread blocks, sidewall as tall as the door is "
                   "from the ground — these are STUPID-BIG tyres that look almost cartoonishly oversized), "
                   "tyres mounted on simple BLACK STEEL WHEELS (NOT fancy mags — plain bushie steelies), "
                   "the entire ute length visible from bullbar to towbar — classic OLD HILUX silhouette "
                   "with a square upright dual-cab cabin + short flat-sided tray back, "
                   "DARK GREY MATTE WEATHERED paint (faded, oxidised, dusty, sun-bleached patches, "
                   "minor rust spots around the wheel arches, subtle dust streaks down the doors), "
                   "looks like a TWENTY-YEAR-OLD farm ute that's seen serious bush work, "
                   "simple steel bull-bar at the front with a single round driving light on top, "
                   "no fancy LED bar, no roof light bar, no snorkel — just an HONEST old farm truck, "
                   "MASSIVELY JACKED-UP lifted suspension (long-travel shocks, large gap between the body "
                   "and the top of the tyre) giving an INSANELY HIGH stance — the truck's running boards are "
                   "at adult chest height, the bonnet is taller than a person — properly stupid lifted height, "
                   "flat tray back at rear with no canopy, a single rear UHF whip antenna, "
                   "small HILUX badge on the front guard, mud splatter caked along the lower body panels "
                   "and wheel arches, plenty of bush-bash scrapes on the bullbar, "
                   "Australian country-bloke OLD-SCHOOL bushie pixel art game sprite, "
                   "highly detailed retro pixel art game sprite on a PURE TRANSPARENT empty background, "
                   "ONLY the ute body and wheels are drawn, nothing else, "
                   "completely flat side-on silhouette, NO top-down, NO 3-quarter view, ONLY pure side profile"
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
SIDE_CAR_BIG = {"e36_side", "ranger_side", "player_side", "camry_side", "silvia_side"}

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
        "deeply sun-tanned weathered face, scruffy DARK BROWN stubble, "
        "lopsided friendly grin, squinting blue eyes from harsh sun, "
        "DARK BROWN hair partly visible under the Akubra brim, "
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


# -- CHARACTER v2 SYSTEM ---------------------------------------------------
# PixelLab character-consistency workflow. For each character we lock down
# a CANONICAL DESCRIPTION (immutable face + outfit + accessories), generate
# one master reference at high detail, then derive each emotion-state portrait
# from the master via init_image (strength ~300, so the face/outfit stays
# consistent and only the expression changes). This is how we keep eight
# different Brenno portraits looking like the same person.
print("\n===  CHARACTER v2 — BRENNO  ===")


# -------- STREETO PORTRAIT STYLE GUIDE -----------------------------------
# Locked-in style directives that get appended to EVERY character portrait
# generation. This is the look the game's character art was built around —
# Moey-tier gritty cinematic pixel art with rich multi-tone shading, NOT
# the soft anime/cell-shaded look PixelLab defaults to. Every state of every
# character runs through this style filter so the cast looks like it belongs
# together.
STREETO_PORTRAIT_STYLE_GUIDE = (
    "REALISTIC GRITTY HAND-PAINTED PIXEL ART portrait bust modelled in the EXACT same style and "
    "detail level as the Moey/Khoa established character portraits, "
    "absolutely NOT cartoon, NOT anime, NOT chibi, NOT cell-shaded flat-look — "
    "this is gritty REALISTIC RENAISSANCE-BUST style pixel art, "
    "PLAIN SOLID DARK NAVY BLUE BACKGROUND behind the character, no scenery, "
    "intense tight close-up bust framing showing face + shoulders only, the face DOMINATES the frame, "
    "STRONG DIRECTIONAL CINEMATIC LAMP LIGHTING FROM ABOVE casting harsh dramatic shadows on the face, "
    "RICH MULTI-TONE PIXEL SHADING with at least 4-5 distinct tone bands per surface "
    "(deep shadow / shadow / midtone / highlight / specular catch-light), "
    "smooth pixel-level dithering between tones, "
    "defined highlights on the cheekbones, nose bridge, jawline, brow ridge, "
    "deep cast shadows under the brow, under the jaw, inside the eye sockets, "
    "crisp clean linework, sub-pixel anti-aliased edges, harsh contrast shading like a hand-painted bust, "
    "vivid saturated yet grounded skin tones, "
    "defined three-dimensional facial structure with NO cartoony exaggeration, "
    "realistic adult proportions — face anatomy must look like a real photographed person, "
    "absolutely NO giant anime eyes, NO simplified flat shading, NO cute soft chibi style, "
    "the result should look like a SCREENGRAB FROM A 16-BIT JRPG CINEMATIC PORTRAIT — gritty, weathered, real, "
    "Western Sydney street-culture realism, weighty cinematic photographic lighting"
)


def make_character_states(char_id, canonical_desc, states, master_filename,
                           init_strength=300, master_size=128, state_size=64,
                           overwrite_default_filename=None):
    """Generate a master reference + N expression-state portraits that all
    look like the same character.

    Args:
      char_id: short id used for naming (e.g. 'eshay').
      canonical_desc: the immutable description of the character (face, hair,
        outfit, accessories — the bits we want consistent across all states).
      states: dict of {state_name: extra_prompt} — extra_prompt describes the
        expression/pose for that state (e.g. 'huge open-mouthed grin showing
        teeth, eyes wide with excitement').
      master_filename: the .png filename for the master reference.
      init_strength: PixelLab init_image_strength (0-999) for state generations.
      master_size: pixel size for the master reference (higher = more detail).
      state_size: pixel size for each state portrait.
      overwrite_default_filename: optional second .png to overwrite with the
        master so legacy dialogue keys still resolve.
    """
    # 1) Master reference at higher resolution for richer face detail.
    master_prompt = (
        canonical_desc
        + " calm neutral expression, mouth closed, looking straight at the camera, "
        + STREETO_PORTRAIT_STYLE_GUIDE
    )
    print(f"   -> {master_filename}  (master reference, {master_size}x{master_size})")
    master_img = gen_image(
        master_prompt, master_size, master_size,
        outline="single color black outline",
        shading="detailed shading",
        detail="highly detailed",
        no_background=False,
    )
    if master_img is None:
        print(f"      FAIL master generation failed — skipping {char_id} states")
        return
    master_path = os.path.join(OUT_DIR, master_filename)
    master_img.save(master_path, "PNG")
    print(f"      OK saved {master_filename}")

    # Resize the master to the state size for use as init_image — PixelLab
    # works best when init_image dimensions match the target image_size.
    init_ref = master_img.resize((state_size, state_size), Image.NEAREST)

    # Also save the master at the state size as the canonical 'default' state.
    default_state_path = os.path.join(OUT_DIR, f"portrait_{char_id}_default.png")
    init_ref.save(default_state_path, "PNG")
    print(f"      OK saved portrait_{char_id}_default.png  (downsampled from master)")

    if overwrite_default_filename:
        legacy_path = os.path.join(OUT_DIR, overwrite_default_filename)
        init_ref.save(legacy_path, "PNG")
        print(f"      OK overwrote {overwrite_default_filename}  (legacy fallback)")

    # 2) For each emotion state, regenerate using the master as init_image.
    for state_name, expression in states.items():
        if state_name == "default":
            continue  # already saved above
        out_filename = f"portrait_{char_id}_{state_name}.png"
        out_path = os.path.join(OUT_DIR, out_filename)
        state_prompt = (
            canonical_desc
            + f" {expression}, "
            + STREETO_PORTRAIT_STYLE_GUIDE
        )
        print(f"   -> {out_filename}")
        state_img = gen_image(
            state_prompt, state_size, state_size,
            outline="single color black outline",
            shading="detailed shading",
            detail="highly detailed",
            no_background=False,
            init_image=init_ref,
            init_image_strength=init_strength,
        )
        if state_img is None:
            print(f"      FAIL — skipping {out_filename}")
            continue
        state_img.save(out_path, "PNG")
        print(f"      OK saved {out_filename}")


# --- BRENNO ---------------------------------------------------------------
# Canonical Brenno description — locked-down face + outfit + accessories.
# Every state generation prepends this verbatim; only the expression varies.
BRENNO_CANONICAL = (
    "a wiry pale young white Australian street kid in his early twenties (NOT a young teenager, "
    "NOT a child, NOT cute — a weathered adult-faced street kid who has lived rough), "
    "GAUNT NARROW FACE with sharp angular cheekbones, hollow sunken cheeks under the cheekbones, "
    "narrow weak chin, sharp pointed nose, "
    "weathered pale MILKY COMPLEXION with visible LIGHT ACNE SCARRING scattered across the cheeks, "
    "FRECKLES across the nose and upper cheeks, "
    "HOLLOW TIRED PALE-BLUE EYES with prominent DARK CIRCLES underneath suggesting sleep deprivation, "
    "an intense neutral STREET STARE directly at the viewer (the look of a kid who has seen things), "
    "thin patchy GINGER STUBBLE along the jawline and upper lip (uneven adult stubble, not a baby face), "
    "BRIGHT GINGER ORANGE MESSY MULLET haircut — short on top, long thin GINGER RAT-TAIL dangling "
    "down the side of his neck past the collar onto his shoulder, ginger fringe poking out under cap brim, "
    "wearing a NAVY BLUE NIKE TN baseball cap pulled LOW over the eyes casting a DEEP DRAMATIC SHADOW "
    "across the upper face (the shadow obscures the eye sockets — the hollow black voids show beneath "
    "the cap brim), the bright YELLOW NIKE SWOOSH logo prominently visible on the side panel of the cap, "
    "FLAT cap brim with a small sticker still stuck on it, "
    "wearing a baggy MUSTARD YELLOW oversized crewneck JUMPER, the jumper collar visible at the shoulders, "
    "a thin tarnished SILVER CHAIN hanging at the neck above the jumper, "
    "faded blue PRISON-STYLE KNUCKLE TATTOOS visible peeking from the jumper collar onto the lower neck "
    "(stick-and-poke amateur ink — not professional), "
    "a black NIKE CROSSBODY BUMBAG STRAP clearly visible running diagonally across one shoulder over the "
    "jumper, "
    "his face must read like a DOCUMENTARY PHOTOGRAPH OF A REAL WESTERN SYDNEY ESHAY KID — gritty, "
    "lived-in, real adult features, NOT a stylised Pixar/anime character, "
)

BRENNO_STATES = {
    "default":   "calm neutral expression, mouth closed, eyes forward, relaxed face",
    "happy":     "broad genuine open-mouthed smile showing white teeth, "
                 "eyes scrunched in joy, cheek apples raised, eyebrows up and out",
    "sad":       "downturned mouth, lips pressed together, eyebrows drooping inward and down, "
                 "eyes glistening with the faintest tear in the corner, shoulders slumped",
    "angry":     "fierce snarling scowl with bared teeth, mouth twisted in a grimace, "
                 "thick eyebrows drawn together hard, eyes narrowed in aggression, "
                 "veins faintly visible at the temple",
    "excited":   "huge open-mouthed grin mid-yell showing teeth and tongue, "
                 "eyes wide open with pupils dilated, eyebrows raised HIGH in pure stoked hype, "
                 "mouth open wider than relaxed",
    "nervous":   "anxious worried face with mouth slightly open in concern, "
                 "eyes wide and darting, eyebrows raised together in the middle, "
                 "faint sweat beads on the forehead, lower lip caught between teeth",
    "smug":      "cocky smug smirk pulled to one side of the mouth, one eyebrow raised in arrogance, "
                 "eyes half-lidded in confident contempt, head tilted slightly back",
    "surprised": "wide-open shocked mouth in a clear 'O' shape, eyes WIDE OPEN with eyebrows "
                 "raised AT MAXIMUM, cheeks slack in surprise, whole face stretched in disbelief",
}

make_character_states(
    char_id="eshay",
    canonical_desc=BRENNO_CANONICAL,
    states=BRENNO_STATES,
    master_filename="portrait_eshay_master.png",
    init_strength=420,
    master_size=64,
    state_size=64,
    overwrite_default_filename="portrait_bazza_default.png",
)

# --- YOU / PLAYER ---------------------------------------------------------
# The protagonist. Locked-down description matches the established
# tight-close-up portrait look — face dominates the frame, scarred brow,
# intense focused stare, gold stud + chain glimpse, black hoodie + white
# tee collar at the bottom edge.
print("\n===  CHARACTER v2 — YOU / PLAYER  ===")

PLAYER_CANONICAL = (
    "a young mixed-background Australian street racer in his early-to-mid twenties, "
    "tan olive complexion with painterly subtle skin detail and natural skin texture, "
    "sharp strong defined jawline with short LIGHT DARK STUBBLE clearly visible across the chin "
    "and along the jaw, prominent brow ridge with thick black eyebrows, "
    "a small thin SCAR slicing diagonally through the OUTER END of one of his eyebrows, "
    "intense focused DARK BROWN EYES with a serious squint, defined nose bridge with subtle nostril shadow, "
    "calm neutral expression baseline with a hint of confident set at the corner of the mouth, "
    "SHORT CROPPED DARK BROWN HAIR styled in a clean faded undercut — short on the sides "
    "with slightly longer texture on top, "
    "a small GOLD STUD EARRING visible in one ear, "
    "wearing a BLACK ZIP-UP HOODIE unzipped at the collar showing a sliver of clean WHITE TEE underneath "
    "at the neckline, "
    "a thick subtle GOLD CHAIN visible at the collar between the hoodie and the white tee, "
)

PLAYER_STATES = {
    "default":   "calm neutral expression, mouth closed, eyes forward focused, "
                 "subtle confident set to the jaw, baseline serious driver face",
    "happy":     "genuine warm smile with the corners of the mouth pulled up, "
                 "slight teeth visible, eyes crinkled at the corners with mirth, "
                 "eyebrows relaxed up",
    "sad":       "downturned mouth, lips pressed together tight, eyebrows drooping "
                 "inward and down at the inner ends, eyes dimmed with a hint of "
                 "moisture at the corners, jaw slack",
    "angry":     "hard angry scowl, jaw clenched tight with bared teeth showing slightly, "
                 "mouth pulled into a snarl, thick eyebrows drawn down and together in fury, "
                 "eyes narrowed in aggression, vein faintly visible at the temple",
    "excited":   "open-mouthed exhilarated grin showing teeth, eyes wide with adrenaline, "
                 "eyebrows raised up, the pure thrill of a race well-driven face",
    "nervous":   "tense uncertain look with mouth slightly open in concern, "
                 "eyes wide and scanning, eyebrows raised together in the middle in worry, "
                 "faint sweat sheen on the forehead, lower lip caught between teeth",
    "smug":      "cocky smirk pulled to one side of the mouth, one eyebrow arched in arrogance, "
                 "eyes half-lidded in confident contempt, chin tilted slightly up",
    "surprised": "wide-open shocked mouth in a clear 'O' shape, eyes BLOWN WIDE with eyebrows "
                 "raised AT MAXIMUM, jaw dropped, face slack with pure disbelief",
}

make_character_states(
    char_id="player",
    canonical_desc=PLAYER_CANONICAL,
    states=PLAYER_STATES,
    master_filename="portrait_player_master.png",
    init_strength=420,
    master_size=64,
    state_size=64,
    overwrite_default_filename="portrait_player_default.png",
)


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
# Richer 800x240 panoramic strip — taller for more vertical detail, wider
# so the side-scroll doesn't repeat as obviously, with Sydney-specific
# landmarks (Centrepoint Tower) and proper layered foreground/midground/
# background depth.
cached_or_gen("transition_drive_src.png", lambda: gen_image(
    "side-scrolling pixel art Sydney night cityscape at midnight, wide horizontal panoramic strip view at street level, "
    "viewed from across the road so the whole scene is laid out flat on a side profile, "
    "BACKGROUND: tall Sydney CBD skyline silhouette in deep navy along the upper portion, "
    "high-rise apartment towers and office buildings of staggered varying heights, "
    "the iconic Sydney Centrepoint Tower with its golden turret poking up tall in the middle distance, "
    "many lit warm yellow and cool white windows scattered randomly across the building faces, "
    "a few rooftop NEON SIGNS in red and magenta (advertising signs), "
    "thin radio aerials and rooftop antennae silhouetted against the sky, "
    "MIDDLE GROUND: row of low-rise late-night shopfronts at the street level, "
    "kebab shop with rotating spit in window, 7-Eleven convenience store, Vietnamese pho restaurant, "
    "Lebanese bakery, sushi train, all with glowing neon signage and warm yellow shop window glow spilling onto the footpath, "
    "tangled black overhead power lines crossing between wooden telegraph poles, traffic light pole at one intersection, "
    "FOREGROUND: a narrow strip of asphalt road with warm orange streetlamp pools and a low concrete kerb along the very bottom, "
    "SKY: deep navy night above with a sprinkling of tiny white stars and a faint warm orange-pink horizon glow rising from behind the buildings, "
    "tileable horizontally — left edge matches right edge for seamless infinite side-scrolling, "
    "side-scroller arcade game aesthetic like 90s SEGA Outrun or Streets of Rage 2, "
    "NO cars, NO people, ONLY the environment, "
    "highly detailed 16-bit pixel art, warm Sydney night urban aesthetic, "
    "deep navy + amber + magenta neon palette, "
    "rich layered depth with clear separation between background skyline, middle ground shopfronts, and foreground road",
    400, 400, view="side",
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


# Full composite travel animation — replaces the old layered DOM
# (cityscape strip + road div + car img + wheel-blur divs). One GIF, all
# elements perfectly synchronised. Cityscape scrolls slow (parallax), road
# dashes scroll fast, Evo bobs gently in the middle with baked wheel blur.
def make_travel_gif_DEPRECATED(out_path, frames=30, duration=50):
    """[DEPRECATED] Composite travel scene built from layered sprites.
    Replaced by a single PixelLab-generated travel_src.png with window-
    twinkle animation (see SUBURB_SCENE_PROMPTS['travel'] entry below)."""
    import math, random
    from PIL import Image, ImageDraw, ImageFilter, ImageOps
    W, H = 400, 400

    # Layout bands — 400-tall square split into thirds-ish
    SKY_H        = 130             # sky band on top (stars + horizon glow)
    CITY_Y       = SKY_H
    CITY_BAND_H  = 110             # cityscape band
    GROUND_Y     = SKY_H + CITY_BAND_H   # 240
    LAMP_BAND    = 22              # mid-ground lamp posts above the road
    ROAD_Y       = GROUND_Y + LAMP_BAND  # 262
    ROAD_H       = H - ROAD_Y            # 138

    # ---- Source assets
    city_src = Image.open(os.path.join(OUT_DIR, "transition_drive_src.png")).convert("RGB")
    city_aspect = city_src.width / city_src.height
    city_scaled_w = int(CITY_BAND_H * city_aspect)
    city_scaled = city_src.resize((city_scaled_w, CITY_BAND_H), Image.NEAREST)

    car_src = Image.open(os.path.join(OUT_DIR, "car_player_side.png")).convert("RGBA")
    car_flipped = ImageOps.mirror(car_src)
    CAR_W, CAR_H = 200, 100
    car_disp = car_flipped.resize((CAR_W, CAR_H), Image.NEAREST)

    # Wheel rotation pipeline removed — use the car sprite as-is, the same
    # static car in every frame. Motion is sold by the parallax cityscape +
    # mid-ground lamps + scrolling road dashes behind it.

    # Car position — centered horizontally, wheels on the dashed centre line
    car_x = (W - CAR_W) // 2
    car_y_base = ROAD_Y + ROAD_H // 2 - CAR_H + 12

    # ---- Build static base (sky + stars + warm horizon glow + asphalt)
    base = Image.new("RGB", (W, H), (8, 10, 18))
    bd = ImageDraw.Draw(base)
    # Sky gradient — black up top fading to deep navy near horizon
    for y in range(SKY_H):
        t = y / SKY_H
        r = int(6 + t*12)
        g = int(8 + t*10)
        b = int(16 + t*26)
        bd.line([(0, y), (W, y)], fill=(r, g, b))
    # Warm amber horizon glow rising from cityscape
    for y in range(SKY_H - 70, SKY_H):
        t = (y - (SKY_H - 70)) / 70
        r = min(255, int(18 + t * 60))
        g = min(255, int(18 + t * 28))
        b = min(255, int(42 - t * 12))
        bd.line([(0, y), (W, y)], fill=(r, g, b))
    # Stars — denser near top, varied size + brightness
    rng = random.Random(42)
    for _ in range(110):
        sx = rng.randint(0, W-1)
        sy = rng.randint(2, SKY_H - 50)
        if rng.random() < (sy / SKY_H): continue
        size = rng.choice([1, 1, 1, 1, 2])
        bri = rng.choice([170, 200, 230, 255])
        bd.rectangle([(sx, sy), (sx+size-1, sy+size-1)], fill=(bri, bri, bri))
    # Asphalt ground band — proper gradient (lighter in centre)
    for y in range(ROAD_Y, H):
        t = (y - ROAD_Y) / ROAD_H
        lift = int(10 * (1 - abs(t - 0.45) * 2))
        col = (28 + lift, 30 + lift, 38 + lift)
        bd.line([(0, y), (W, y)], fill=col)
    # White edge stripes top + bottom of road
    bd.line([(0, ROAD_Y + 6), (W, ROAD_Y + 6)], fill=(180, 180, 180), width=2)
    bd.line([(0, H - 8), (W, H - 8)], fill=(160, 160, 160), width=2)
    # Scatter asphalt grit
    rng_grit = random.Random(13)
    for _ in range(180):
        gx = rng_grit.randint(0, W-1)
        gy = rng_grit.randint(ROAD_Y + 10, H - 12)
        c = 38 + rng_grit.choice([-6, -3, 3, 6])
        bd.point((gx, gy), fill=(c, c, c+3))

    # ---- Find bright cityscape window pixels for the twinkle effect
    # (we'll paste city_scaled per frame, but window twinkle modulates the
    # base copy below — measured once on the un-scrolled cityscape)
    rng_twinkle = random.Random(7)

    frame_imgs = []
    for i in range(frames):
        t = i / frames
        frame = base.copy()
        fd = ImageDraw.Draw(frame)

        # 1) Cityscape — slow leftward scroll, with per-frame window twinkle
        city_off = int(t * city_scaled_w)
        # Apply twinkle to the city band copy
        city_copy = city_scaled.copy()
        cpx = city_copy.load()
        for y in range(CITY_BAND_H):
            for x in range(0, city_scaled_w, 1):
                p = cpx[x, y]
                if (p[0] + p[1] + p[2]) > 480 and p[0] > p[2]:
                    if rng_twinkle.random() < 0.10:
                        cpx[x, y] = (max(0, p[0]-90), max(0, p[1]-90), max(0, p[2]-90))
        x = -city_off
        while x < W:
            frame.paste(city_copy, (x, CITY_Y))
            x += city_scaled_w

        # 2) Mid-ground lamp posts scrolling faster than the cityscape
        lamp_off = int(t * 600) % 130   # ~4.6 lamps per loop
        for lx in range(-lamp_off, W + 130, 130):
            # Halo glow on the road behind the lamp
            for r in range(28, 0, -3):
                a = int(28 * (1 - r/28))
                if a > 0:
                    fd.ellipse([(lx-r, GROUND_Y+8-r), (lx+r, GROUND_Y+8+r)],
                               fill=(min(255, 50 + a*3), min(255, 45 + a*2), min(255, 40 + a)))
            # Pole + arm
            fd.rectangle([(lx, GROUND_Y - 8), (lx+2, ROAD_Y - 2)], fill=(44, 44, 56))
            fd.rectangle([(lx-6, GROUND_Y - 10), (lx+2, GROUND_Y - 8)], fill=(44, 44, 56))
            # Warm bulb
            fd.ellipse([(lx-4, GROUND_Y - 13), (lx+2, GROUND_Y - 7)], fill=(255, 210, 110))

        # 3) Road dashes — scrolling fast (5 cycles per loop)
        dash_off = int(t * 360) % 72
        y_centre = ROAD_Y + ROAD_H // 2
        for dx in range(-dash_off - 72, W + 72, 72):
            fd.rectangle([(dx, y_centre-3), (dx+36, y_centre+3)], fill=(255, 204, 68))

        # 4) Car with gentle bob (~6px peak-to-peak, 1.5 cycles per loop).
        # Wheels stay crisp/static; motion is sold by the parallax behind.
        bob = int(math.sin(t * 2 * math.pi * 1.5) * 3)
        # Subtle shadow on the asphalt under the car
        fd.ellipse([(car_x + 22, car_y_base + CAR_H - 6 + bob),
                    (car_x + CAR_W - 22, car_y_base + CAR_H + 4 + bob)],
                   fill=(12, 14, 22))
        frame.paste(car_disp, (car_x, car_y_base + bob), car_disp)

        frame_imgs.append(frame.convert("P", palette=Image.ADAPTIVE, colors=192))

    frame_imgs[0].save(out_path, save_all=True, append_images=frame_imgs[1:],
                       duration=duration, loop=0, optimize=True, disposal=2)
    kb = os.path.getsize(out_path) // 1024
    print(f"      OK {os.path.basename(out_path)}  ({W}x{H}, {frames}f, {kb}kb)")


# travel.gif now generated as a per-beat PixelLab scene further down
# (alongside the other beat GIFs) — the composite pipeline above is kept
# as make_travel_gif_DEPRECATED for reference.


# Composite per-suburb scene GIFs — each one bakes the suburb's character +
# car + cityscape background into a single 400x400 animated overlay used by
# the dialogue scene-image system. Replaces the canvas-drawn composite for
# the dialogue scene's visual layer (the dialogue panel still draws on top).
def make_scene_gif(out_path, bg_file, char_file, char_frame, car_file,
                   car_w, car_h, char_w=130, char_h=170,
                   smoke_bonnet_xy=None, frames=24, duration=70):
    """Composite a 390x600 FULL-BLEED dialogue-scene GIF.

    Sits behind the dialogue panel covering the whole visual area (not a
    framed box). Layered atmosphere: starry sky, cityscape with twinkling
    windows, warm streetlamp pools on the asphalt, char + car standing on
    a ground line, optional smoke plume rising and drifting from the bonnet.

    - bg_file: a wide cityscape strip (e.g. bg_blacktown.png)
    - char_file + char_frame: pull frame_idx from the 4-frame char sheet
      (0=east, 1=west, 2=south, 3=north). South is the dialogue pose.
    - car_file + car_w/car_h: the side-on car sprite + display dimensions
    - smoke_bonnet_xy: optional (x, y) of bonnet center within the GIF —
      drives an animated multi-stream smoke plume
    """
    import math, random
    from PIL import Image, ImageDraw, ImageFilter
    W, H = 390, 600

    # ---- Load source assets
    bg = Image.open(os.path.join(OUT_DIR, bg_file)).convert("RGB")
    # Scale bg to W wide, keep aspect, then crop/place to fit the cityscape band
    bg_aspect = bg.width / bg.height
    bg_scaled_h = int(W / bg_aspect)
    bg_scaled = bg.resize((W, bg_scaled_h), Image.NEAREST)

    char_sheet = Image.open(os.path.join(OUT_DIR, char_file)).convert("RGBA")
    fw = char_sheet.width // 4
    char_frame_img = char_sheet.crop((fw*char_frame, 0, fw*(char_frame+1), char_sheet.height))
    char_disp = char_frame_img.resize((char_w, char_h), Image.NEAREST)

    car = Image.open(os.path.join(OUT_DIR, car_file)).convert("RGBA")
    car_disp = car.resize((car_w, car_h), Image.NEAREST)

    # ---- Layout: night sky / horizon glow / cityscape strip / asphalt ground.
    SKY_H        = 200             # tall dark sky on top with stars
    CITY_Y       = SKY_H           # cityscape band starts here
    CITY_BAND_H  = 180             # taller cityscape band for more detail
    GROUND_Y     = SKY_H + CITY_BAND_H   # 380
    FEET_Y       = H - 40          # ground line near the bottom
    # Scale cityscape strip to fit the band height while keeping its width
    city_band = bg_scaled.resize((W, CITY_BAND_H), Image.NEAREST)

    # Character + car positions (feet/wheels aligned with FEET_Y)
    char_x = 20
    char_y = FEET_Y - char_h
    car_x_pos = char_x + char_w + 6
    car_y_pos = FEET_Y - car_h

    # Pre-build a static base scene (everything that doesn't animate)
    # Sky gradient — black at top fading to deep navy near the horizon
    base = Image.new("RGB", (W, H), (8, 10, 18))
    bd = ImageDraw.Draw(base)
    for y in range(SKY_H):
        t = y / SKY_H
        # 8,10,18 at top -> 18,18,42 near horizon
        r = int(8 + t*10)
        g = int(10 + t*8)
        b = int(18 + t*24)
        bd.line([(0, y), (W, y)], fill=(r, g, b))
    # Warm horizon glow rising up from the cityscape (orange/pink amber)
    for y in range(SKY_H - 60, SKY_H):
        t = (y - (SKY_H - 60)) / 60
        # Lift warm amber tint
        r = min(255, int(18 + t * 55))
        g = min(255, int(18 + t * 25))
        b = min(255, int(42 - t * 10))
        bd.line([(0, y), (W, y)], fill=(r, g, b))
    # Stars in the sky — varied size + brightness, denser near top
    rng = random.Random(42)
    for _ in range(95):
        sx = rng.randint(0, W-1)
        sy = rng.randint(2, SKY_H - 30)
        # More stars higher up
        if rng.random() < (sy / SKY_H):
            continue
        size = rng.choice([1, 1, 1, 1, 2])
        bri = rng.choice([170, 200, 230, 255])
        bd.rectangle([(sx, sy), (sx+size-1, sy+size-1)], fill=(bri, bri, bri))
    # Cityscape strip
    base.paste(city_band, (0, CITY_Y))
    # Soft fade between cityscape + ground (subtle warm haze)
    for y in range(GROUND_Y - 14, GROUND_Y + 4):
        t = (y - (GROUND_Y - 14)) / 18
        alpha = (1 - abs(t - 0.5) * 2) * 0.4  # peak at midpoint
        # Blend with darker asphalt tone
        existing = base.getpixel((W//2, y))
        new = tuple(int(c * (1 - alpha) + 22 * alpha) for c in existing)
        bd.line([(0, y), (W, y)], fill=new)
    # Asphalt ground band — proper asphalt gradient (lighter centre)
    ground = Image.new("RGB", (W, H - GROUND_Y), (28, 30, 38))
    gr = ImageDraw.Draw(ground)
    gh = H - GROUND_Y
    for y in range(gh):
        t = y / gh
        # Lighter in middle, darker at edges
        lift = int(8 * (1 - abs(t - 0.4) * 2))
        col = (28 + lift, 30 + lift, 38 + lift)
        gr.line([(0, y), (W, y)], fill=col)
    # Warm streetlamp pools on the asphalt (three offset pools)
    for cx, intensity in [(70, 50), (200, 45), (340, 50)]:
        for r in range(80, 0, -3):
            a = max(0, int(intensity * (1 - r/80)))
            col_r = min(255, 28 + a*2)
            col_g = min(255, 30 + a*1)
            col_b = min(255, 38 - a//4)
            gr.ellipse([(cx-r, gh-20-r), (cx+r, gh-20+r)], outline=None, fill=(col_r, col_g, col_b))
    # Subtle asphalt texture scattered specks
    rng_grit = random.Random(13)
    for _ in range(140):
        gx = rng_grit.randint(0, W-1)
        gy = rng_grit.randint(0, gh-1)
        shade = rng_grit.choice([-6, -3, 3, 6])
        col = gr._image.getpixel((gx, gy)) if False else None
        # simpler: just place a 1px dot of slightly different tone
        c = 38 + shade
        gr.point((gx, gy), fill=(c, c, c+3))
    base.paste(ground, (0, GROUND_Y))
    # White edge stripes for the road kerb
    bd2 = ImageDraw.Draw(base)
    bd2.line([(0, GROUND_Y + 4), (W, GROUND_Y + 4)], fill=(180, 180, 180), width=1)
    bd2.line([(0, H - 6), (W, H - 6)], fill=(160, 160, 160), width=1)
    # Char + car shadows on the asphalt (long oval pools)
    sh = ImageDraw.Draw(base)
    sh.ellipse([(char_x+8, FEET_Y-4), (char_x+char_w-8, FEET_Y+6)], fill=(0, 0, 0))
    sh.ellipse([(car_x_pos+8, FEET_Y-3), (car_x_pos+car_w-8, FEET_Y+8)], fill=(0, 0, 0))

    # Pre-blit char + car onto the base (they don't change between frames)
    base_rgba = base.convert("RGBA")
    base_rgba.paste(car_disp, (car_x_pos, car_y_pos), car_disp)
    base_rgba.paste(char_disp, (char_x, char_y), char_disp)

    # ---- Per-frame animation: smoke plume + subtle window twinkle
    # Find bright cityscape window pixels for the twinkle effect
    cityscape_pixels = base_rgba.load()
    bright_windows = []
    for y in range(CITY_Y, GROUND_Y):
        for x in range(W):
            p = cityscape_pixels[x, y]
            # Warm-bright = likely a lit window
            if (p[0] + p[1] + p[2]) > 450 and p[0] > p[2]:
                bright_windows.append((x, y))

    rng_twinkle = random.Random(7)

    frame_imgs = []
    for i in range(frames):
        t = i / frames
        frame = base_rgba.copy()
        fpx = frame.load()

        # Window twinkle — dim ~10% of bright pixels per frame
        for x, y in bright_windows:
            if rng_twinkle.random() < 0.12:
                r, g, b, a = fpx[x, y]
                fpx[x, y] = (max(0, r-100), max(0, g-100), max(0, b-100), a)

        # Smoke plume — three layered streams of soft wisps rising from the bonnet
        if smoke_bonnet_xy is not None:
            sx, sy = smoke_bonnet_xy
            smoke_t = t * 2 * math.pi
            for stream_idx, (ox, speed, period) in enumerate(
                [(-6, 22, 22), (4, 17, 26), (12, 26, 18)]):
                for s in range(6):
                    phase = (i * speed / frames - s * 1.5 + period * 4) % period
                    life_t = phase / period
                    if life_t < 0 or life_t > 1:
                        continue
                    py = sy - int(life_t * 90)
                    px_smoke = sx + ox + int(math.sin(smoke_t + s*0.9 + ox) * (6 + life_t * 14))
                    pr = 4 + int(life_t * 14)
                    alpha = int((1 - life_t) * 180)
                    warmth = max(0.0, 1 - life_t * 2)
                    r = int(200 + warmth * 30)
                    g = int(200 + warmth * 10)
                    b = int(200 - warmth * 20)
                    # Paint a soft circle (use ellipse + alpha blending)
                    smoke_layer = Image.new("RGBA", (pr*2, pr*2), (0,0,0,0))
                    sd = ImageDraw.Draw(smoke_layer)
                    sd.ellipse([(0,0),(pr*2-1,pr*2-1)], fill=(r,g,b,alpha))
                    frame.alpha_composite(smoke_layer, (px_smoke - pr, py - pr))

        frame_imgs.append(frame.convert("P", palette=Image.ADAPTIVE, colors=192))

    frame_imgs[0].save(out_path, save_all=True, append_images=frame_imgs[1:],
                       duration=duration, loop=0, optimize=True, disposal=2)
    kb = os.path.getsize(out_path) // 1024
    print(f"      OK {os.path.basename(out_path)}  ({W}x{H}, {frames}f, {kb}kb)")


# =========================================================================
# PER-SUBURB SCENE GIFs — PixelLab-generated whole-scene compositions.
# One 400x400 source image per suburb showing the character + their car +
# the suburb's distinctive shopfronts/landmarks, then make_city_twinkle_gif
# applied for animated window flicker. These become the full-bleed dialogue
# scene backgrounds (sceneGif on STORY_SUBURB_DATA).
# =========================================================================
print("\n===  PER-SUBURB DIALOGUE SCENES  ===")

SUBURB_SCENE_PROMPTS = {
    "harrispark": (
        "pixel art side-on view of Harris Park Wigram Street at night — "
        "the street is COMPLETELY EMPTY, NO CARS, NO PEOPLE, ONLY the environment, "
        "row of late-night Indian-Australian shopfronts along the strip — "
        "Indian sweets shop with bright yellow signage and trays of mithai in the window, "
        "sari fabric store with colourful saris displayed, "
        "7-Eleven convenience store with the iconic red orange green logo glowing, "
        "Punjabi tandoori restaurant with neon sign, dosa place with chalk menu board, "
        "Indian grocery with bags of rice and spice stacked outside under the awning, "
        "FAIRY LIGHTS strung between shopfronts overhead glowing warm white, "
        "warm yellow shop window glow spilling onto the empty footpath, "
        "narrow asphalt road in the foreground completely empty, low concrete kerb, "
        "deep navy night sky above with stars and a faint warm orange horizon glow, "
        "Sunday night quiet vibe — peaceful, anticipatory, the street holds its breath waiting, "
        "16-bit pixel art side-scroller game aesthetic, late-night Harris Park atmosphere, "
        "ONLY pure side profile, NO 3/4 view"
    ),
    "blacktown": (
        "pixel art side-on view of Blacktown Maccas drive-thru carpark at night, "
        "SKINNY young white Australian eshay teenager in a NAVY BLUE NIKE TN CAP with a YELLOW swoosh "
        "and a MUSTARD YELLOW JUMPER, black tracksuit pants, small black bumbag strapped diagonally, "
        "standing on the kerb on the left, "
        "BESIDE HIM a faded BLACK BMW E36 sedan parked at the kerb with the BONNET PROPPED OPEN and "
        "THIN WHITE SMOKE wisping up from the engine bay, black aftermarket wheels, slammed coilover stance, "
        "McDonalds golden arches glowing yellow in the background, "
        "dim Blacktown shopfronts along the strip — discount shop, fast-food, kebab shop, graffiti on walls, "
        "warm orange streetlamp pools on the asphalt, deep navy night sky with stars + warm horizon glow, "
        "16-bit pixel art side-scroller game aesthetic, atmospheric Western Sydney late-night street, "
        "ONLY pure side profile, NO 3/4 view"
    ),
    "parramatta": (
        "pixel art side-on view of Harris Park Wigram Street at night, "
        "TALL SLIM Sikh Punjabi Australian man in his thirties wearing a BRIGHT ROYAL BLUE DASTAR turban "
        "with a thick full BLACK BEARD, white kurta shirt and dark slim trousers, "
        "holding a samosa, with a BRIGHT FLUORESCENT GREEN UberEats backpack visible behind his shoulders, "
        "standing on the footpath on the left, "
        "BESIDE HIM his grey Toyota Camry sleeper sedan parked low at the kerb, "
        "black aftermarket wheels, slammed coilover stance, small lip kit, "
        "Indian sweets shop with bright yellow signage and trays of mithai in the window behind, "
        "sari fabric store with colourful saris displayed, 7-Eleven convenience store with red orange green logo glowing, "
        "Punjabi tandoori restaurant with neon sign, fairy lights strung overhead between shopfronts, "
        "warm yellow window glow spilling onto the footpath, "
        "deep navy night sky with stars + warm orange-pink horizon glow, "
        "16-bit pixel art side-scroller game aesthetic, late-night Indian-Australian shopping strip, "
        "ONLY pure side profile, NO 3/4 view"
    ),
    "cabramatta": (
        "pixel art side-on view of Cabramatta Maccas drive-thru carpark at midnight, "
        "young Vietnamese Australian man in his late twenties wearing a crisp LIGHT BLUE BUTTON-UP SHIRT "
        "with sleeves rolled up, slim dark jeans, fresh white sneakers, polite confident stance, "
        "standing on the asphalt on the left, "
        "BESIDE HIM his PEARL WHITE Nissan S14 Silvia Kouki coupe parked low with the boot open showing "
        "brown paper bags inside, deep-dish gunmetal Work Meister wheels, slammed coilover stance, "
        "subtle GT-style rear wing, small VIETNAMESE FLAG sticker on rear quarter window, "
        "McDonalds golden arches glowing yellow in the background, "
        "painted parking bay lines on the asphalt, tall lamp poles with warm pools of light on the tarmac, "
        "distant Cabramatta Vietnamese restaurant neon signs and bubble tea shop colourful neon, "
        "deep navy night sky with stars, "
        "16-bit pixel art side-scroller game aesthetic, late-night Cabramatta drug-deal carpark atmosphere, "
        "ONLY pure side profile, NO 3/4 view"
    ),
    "penrith": (
        "pixel art side-on view of a Penrith country-edge street at night, "
        "TALL LANKY SKINNY young white Australian country boy in his late twenties wearing a dusty wide-brim "
        "AKUBRA cowboy hat, faded light blue FLANNEL shirt unbuttoned over a clean white Bonds SINGLET, "
        "faded blue Wrangler jeans tucked into brown leather steel-toe work boots, big silver rodeo belt buckle, "
        "thumbs hooked into belt loops, "
        "standing on a dirt patch beside his JACKED-UP MODERN 2018 Toyota Hilux SR5 dual-cab 4x4 ute "
        "(NOT an old Hilux, NOT a Ford Ranger — specifically the 2018-era Toyota Hilux SR5 with modern "
        "aggressive front grille, sleek modern slim headlights, four full-size doors in the cabin, "
        "short factory-style tray back at the rear, "
        "DARK GREY MATTE paint with subtle dust streaks, "
        "TALL STEEL BULLBAR at the front with TWIN BRIGHT LED LIGHT BARS mounted on top, "
        "tall BLACK SNORKEL intake mounted along the driver-side A-pillar, "
        "ROOF-MOUNTED LED LIGHT BAR running across the top of the cabin, "
        "MASSIVE CHUNKY BLACK MUD-TERRAIN TYRES (35-inch, deep knobbly aggressive lugs) on "
        "BLACK AFTERMARKET STEEL WHEELS, "
        "lifted long-travel suspension giving HIGH stance, "
        "ARB winch visible at the front, "
        "subtle HILUX SR5 badge on the front guard, mud splatter caked along the lower body panels), "
        "country pub with bright red XXXX neon sign glowing in the background, "
        "panel beater shop with roller doors, tyre shop, "
        "distant BLUE MOUNTAINS SILHOUETTE on the horizon, tall gum trees silhouetted against the sky, "
        "warm amber streetlamp pools on the dirt, "
        "deep navy night sky with stars + warm horizon glow, "
        "16-bit pixel art side-scroller game aesthetic, country-edge of west Sydney NSW atmosphere, "
        "ONLY pure side profile, NO 3/4 view"
    ),
    "liverpool": (
        "pixel art side-on view of Liverpool Macquarie Street kebab strip at night, "
        "LEBANESE Australian man in his thirties wearing a crisp WHITE OPEN-COLLAR BUTTON-UP SHIRT "
        "with thick GOLD CHAIN necklace and designer aviator SUNGLASSES pushed up onto slicked black hair, "
        "well-groomed black stubble beard, dark fitted trousers, polished leather loafers, "
        "confident relaxed stance with hands in pockets, "
        "standing on the footpath on the left, "
        "BESIDE HIM his BLACK Mercedes-AMG C63S sedan parked low with biturbo V8 QUAD CHROME EXHAUST tips at the rear, "
        "carbon front lip, AMG aggressive aero, deep-dish black wheels, dark tinted windows, "
        "late-night Lebanese kebab shop with a ROTATING VERTICAL KEBAB SPIT visible through the front window in the background, "
        "Lebanese sweets shop, shisha lounges with palm tree silhouettes, "
        "warm amber and magenta neon glow from shopfront signs, traffic light pole, "
        "deep navy night sky with stars + warm horizon glow, "
        "16-bit pixel art side-scroller game aesthetic, Liverpool late-night Lebanese street atmosphere, "
        "ONLY pure side profile, NO 3/4 view"
    ),
}

for suburb_key, prompt in SUBURB_SCENE_PROMPTS.items():
    src_filename = f"scene_{suburb_key}_src.png"
    out_filename = f"scene_{suburb_key}.gif"
    src_path = os.path.join(OUT_DIR, src_filename)
    out_path = os.path.join(OUT_DIR, out_filename)
    cached_or_gen(src_filename, lambda p=prompt: gen_image(
        p, 400, 400, view="side",
        outline="lineless", shading="detailed shading", detail="highly detailed",
        no_background=False))
    if os.path.exists(src_path):
        # Window twinkle animation: warm bright pixels (lit windows, neon
        # signs) randomly dim each frame to suggest the natural flicker of
        # apartment lights + glowing shop signage.
        make_city_twinkle_gif(src_path, out_path, frames=18, duration=110)


# =========================================================================
# PER-BEAT MOMENT GIFs — story-critical specific scenes that override the
# suburb default. Each is a single PixelLab 400x400 with window-twinkle
# animation, wired to a specific dialogue node via sceneImage.
# =========================================================================
print("\n===  PER-BEAT MOMENT GIFs  ===")

BEAT_PROMPTS = {
    # brenno_ongbay_realize: "BRA. BRAAAAA. ME PIECE. SHITTT, ME GLASS.
    # I LEFT THE ONGBAY IN THE BIMMER..." — EXTREME CLOSE-UP of Brenno's
    # face as he realises he left his bong behind. Pure comedic-tragic.
    "bong_panic": (
        "pixel art FULL-BODY WIDE SHOT of Brenno standing in the middle of the Cabra Maccas carpark "
        "at night — the camera is positioned FAR BACK showing Brenno's ENTIRE BODY from head to feet, "
        "Brenno occupies only about 40 percent of the frame height (he is NOT close-up — "
        "the carpark + the parked Beemer take up most of the composition), "
        "Brenno (skinny pale ginger Australian eshay teenager in his late teens, NAVY BLUE NIKE TN CAP "
        "pulled low with yellow swoosh, baggy MUSTARD YELLOW JUMPER, navy tracksuit pants tucked into "
        "white tube socks, white rubber slides) standing front-on to camera in a defeated devastated "
        "POSE — head HANGING DOWN slightly, BOTH HANDS RESTING DEFEATED on top of his TN cap, elbows "
        "pointing outward, shoulders SLUMPED in despair, knees slightly buckled, body language of a "
        "young man who just realised his worst mistake, "
        "Brenno's face is SMALL in the frame (because the camera is far back) — drawn with normal "
        "realistic human proportions matching the Moey/Khoa NPC style, NOT a cartoon close-up panel, "
        "NOT giant anime eyes, NOT a stretched cartoon mouth — just a small body in despair shown in "
        "the middle of a wider environmental scene, "
        "right behind Brenno (occupying the right half of the frame) his DEEP BLUE BMW E36 sedan "
        "parked at the curb with the BONNET PROPPED OPEN, faint white engine steam wisping up, "
        "behind the closed E36 driver-side window an empty space where the bong should be, "
        "stylised SMALL thought-bubble icon floating above his head showing a tiny outline of a glass "
        "DOUBLE-PERC BONG with a red X through it (visual storytelling for 'I left it in the Beemer'), "
        "BACKGROUND: the Cabramatta Maccas drive-thru carpark at night — McDonalds golden ARCHES "
        "glowing yellow on a tall pole in the middle distance, the restaurant facade with lit dining-"
        "room windows + drive-thru lane visible, scattered parking bay lines on the asphalt, a few "
        "abandoned shopping trolleys further back, warm amber streetlamp pools, "
        "deep navy night sky above with stars, "
        "the entire composition emphasises BRENNO IS SMALL + the carpark is WIDE — environmental "
        "storytelling, NOT a face panel, "
        "16-bit pixel art WIDE ESTABLISHING shot style, the 'I left the ongbay in the Beemer' "
        "devastating realisation moment told through SMALL-FIGURE-IN-WIDE-SCENE composition, "
        "atmospheric Cabramatta late-night disaster vibe, NPC realism not stylised cartoon"
    ),
    # preet_credits: "the door of the Indian grocer chimes open. Brenno
    # staggers out clutching a paper bag heavy with curry powder, garam
    # masala, and the three extras Mum tacked on. Eyes wide. Samosa
    # wedged in his mouth."
    "curry_emerge": (
        "pixel art side-on view of a skinny young white Australian ESHAY TEENAGER (Brenno) "
        "STAGGERING OUT of the open doorway of an Indian grocer in Harris Park at night, "
        "Brenno is wearing a NAVY BLUE NIKE TN CAP with a YELLOW swoosh and a MUSTARD YELLOW crewneck jumper, "
        "black tracksuit pants and a small black bumbag across his chest, ginger hair under the cap, "
        "his arms wrapped around a heavy brown paper grocery bag OVERFLOWING with "
        "packets of bright orange CURRY POWDER, GARAM MASALA jars, bags of cumin seeds, "
        "spilling out the top of the bag, "
        "a half-eaten SAMOSA wedged in his mouth like he forgot it was there, "
        "his eyes wide with the look of someone who barely survived shopping with mum's list, "
        "the grocer doorway behind him with warm yellow shop light spilling out onto the footpath, "
        "INDIAN GROCERY sign above the door, packets of rice and spice stacked outside under the awning, "
        "deep navy night sky, warm yellow shop window glow, atmospheric, "
        "16-bit pixel art, Harris Park Wigram Street at night"
    ),
    # falcon_return_1: "There she is bra! Me girl! ... I'm getting under
    # the bonnet adlay. Hold the torch up here." — the moment the
    # Beemer comes back to life
    "beemer_install": (
        "pixel art side-on view of a faded BLUE BMW E36 sedan parked at the Blacktown Maccas carpark "
        "at DAWN with the bonnet propped fully OPEN exposing the engine bay, "
        "the skinny eshay teenager Brenno (NAVY BLUE NIKE TN CAP, MUSTARD YELLOW JUMPER) "
        "leaning HEAD-FIRST DEEP into the engine bay with both arms inside working on the M52 inline-six, "
        "installing a brand new M52 IGNITION COIL PACK into cylinder four, "
        "a chrome torch beam illuminating the engine bay from a TORCH held by a hand "
        "visible at the edge of the frame (the player holding the torch for him), "
        "scattered tools on the asphalt (sockets, ratchet wrench, an empty BMW coil pack box), "
        "an empty Bundaberg ginger beer can on the strut tower beside him, "
        "BMW kidney grille visible at the front of the bonnet opening, "
        "warm orange-pink DAWN HORIZON GLOW rising on the right side of the sky, "
        "deep navy fading to amber, the last stars fading out at the top, "
        "Blacktown Maccas drive-thru sign visible in the soft early-morning background, "
        "16-bit pixel art, atmospheric working-late-into-dawn vibe, "
        "the satisfying moment the Beemer comes back to life"
    ),
    # preet_lets_go retry — tighter angle on the Camry at the launch line.
    "rahul_revving_v2": (
        "pixel art side-on close-up of Rahul's grey Toyota Camry sleeper sedan "
        "idling at the start line on Wigram Street Harris Park at night, "
        "the Camry centred in the frame as the main focal element, slammed "
        "coilover stance with black aftermarket multi-spoke wheels, small lip "
        "kit at the front bumper, modest rear lip spoiler on the boot, "
        "the driver's side window rolled DOWN — Rahul clearly visible inside, "
        "a Sikh Punjabi Australian man with a BRIGHT ROYAL BLUE dastar turban "
        "and a thick full BLACK BEARD, both hands gripping the steering wheel "
        "tight, focused intense stare straight ahead, slight grin of anticipation, "
        "stylised concentric music-wave ripple lines pouring out the open window "
        "(loud Punjabi rap on the subwoofer), "
        "thin curls of white tyre smoke wisping up from behind the rear wheels "
        "(brake-torquing, ready to launch), "
        "warm orange Harris Park streetlamp glow falling across the bonnet, "
        "Wigram Street shopfronts visible blurred behind — Indian sweets shop "
        "with bright yellow signage, sari fabric store, 7-Eleven glow, fairy "
        "lights strung overhead, "
        "deep navy night sky above, "
        "the TENSE moment right before launch, 16-bit pixel art side-scroller, "
        "atmospheric pre-race"
    ),
    # engine_diag_resolution + player_diag_response: tight close-up on
    # the cracked M52 coil pack — the smoking gun in Brenno's engine bay.
    "coil_pack_closeup": (
        "pixel art EXTREME CLOSE-UP of a SINGLE BMW M52 IGNITION COIL PACK in an engine bay at night, "
        "the coil pack DOMINATES the frame — a rectangular BLACK PLASTIC BLOCK with rounded edges "
        "standing upright on the cast aluminium valve cover, an electrical connector plugged into the top "
        "with a thick rubber boot covering a multi-pin connector, "
        "but the coil pack is OBVIOUSLY BROKEN — the plastic casing CRACKED CLEAN IN HALF down the middle "
        "with a jagged dark fissure running top-to-bottom, the inner COPPER WIRE WINDINGS visible through "
        "the crack like exposed guts, a single stripped copper wire dangling loose out the bottom, "
        "the spark plug bore in the valve cover visible directly below the coil, "
        "surrounding components blurred / out of focus in the background — the row of intact coil packs "
        "to either side, the aluminium head, faint blue body paint in the far background, "
        "OIL GRIME smeared on the cracked plastic, dust + grit on every surface, "
        "BROWN RUST bloom around the bolt heads and metal edges, "
        "thick black engine oil seeping out of the crack at the bottom, "
        "dim deep shadow lighting from a single workshop lamp casting hard contrast, "
        "the texture reading clearly as cheap brittle 90s BMW plastic at the end of its life, "
        "gritty grimy realistic backyard-mechanic detail, the smoking gun of the diagnosis, "
        "16-bit pixel art with HIGH DETAIL on the broken coil pack itself, "
        "tight crop, no human hands, no people, ONLY the coil pack in close-up"
    ),
    # preet_lets_go: the moment right before the Parramatta race triggers.
    # Rahul gripping the wheel, music slamming, Camry ready to launch.
    "rahul_revving": (
        "pixel art side-on view of Rahul's grey Toyota Camry sleeper sedan parked at the launch line "
        "on a quiet Harris Park suburban street at night, "
        "the Camry idling with the driver's window rolled DOWN, "
        "Rahul visible inside (a Sikh Punjabi Australian man wearing a BRIGHT ROYAL BLUE dastar turban "
        "with a thick full BLACK BEARD) gripping the steering wheel with both hands, "
        "focused intense stare ahead, music waves visible blasting from the open window with "
        "stylised concentric ripple lines suggesting heavy sub-woofer bass, "
        "thin white tyre smoke trail wisping from the rear wheels (ready to launch), "
        "small lip kit and rear spoiler on the Camry, slammed coilover stance, black aftermarket wheels, "
        "warm Harris Park streetlamp glow on the bonnet, "
        "Indian shopfronts blurred in the background — Sweet Punjab + sari fabric store + 7-Eleven, "
        "deep navy night sky, "
        "the TENSE moment just before launch — engine revving, beat about to drop, "
        "16-bit pixel art atmospheric pre-race moment"
    ),
    # khoa_respect_back: "Ongbay's in the brown paper, exactly like I
    # said. Stash it deep til you're home." — handoff moment between cars.
    "khoa_handoff": (
        "pixel art close-up view through the open driver's side window of the player's car, "
        "looking OUT at the parked WHITE PEARL Nissan S14 Silvia parked beside us, "
        "a hand extending in from the LEFT of frame (Khoa's hand, light blue button-up shirt sleeve "
        "rolled up at the wrist) reaching across the gap between cars HOLDING a small folded "
        "BROWN PAPER GROCERY BAG with the top crumpled and twisted closed, contents bulging slightly inside, "
        "the brown paper bag is the focal element — the iconic Cabramatta carpark drug deal, "
        "Khoa visible just past his open S14 window — Vietnamese Australian man in his late twenties "
        "with crisp light blue button-up shirt, friendly confident polite expression, "
        "the white pearl Silvia body visible in the background with its deep-dish gunmetal wheels, "
        "Cabramatta Maccas drive-thru carpark at night, McDonalds golden arches glowing yellow in the distance, "
        "painted parking bay lines on the asphalt below, lamp pool of warm orange light, "
        "the tense moment of the stealth deal handoff — slick, careful, eshay-cinema, "
        "deep midnight blue night sky, 16-bit pixel art with HIGH DETAIL on the brown paper bag, atmospheric"
    ),
    # macca_handover: post-hill-climb win. Brett presents the spare
    # double perc bong as the prize. Wider scene shot (NOT a face
    # close-up) — Brett mid-body in context, the bong is the focal
    # element, his face matches the portrait look (dark brown hair,
    # sun-tanned, lopsided grin, Akubra brim shading his eyes).
    "brett_handover": (
        "pixel art side-on WIDE SCENE shot of a Penrith country-edge dirt-patch carpark at night, "
        "a tall lanky young white Australian country boy (Brett) standing at MID-BODY framing "
        "(NOT a face close-up — show his upper body and arms holding the prize), "
        "wearing a DUSTY WIDE-BRIM AKUBRA cowboy hat PULLED DOWN LOW — the brim is angled DOWNWARD "
        "AND COVERS MOST OF HIS FACE, casting a DEEP DARK SHADOW that hides his ENTIRE UPPER FACE "
        "(eyes, nose bridge, forehead all in deep shadow — completely OBSCURED by the hat brim), "
        "ONLY the LOWER HALF of his face visible below the brim shadow line — sun-tanned weathered "
        "JAW + CHIN + MOUTH visible (a faint lopsided friendly grin showing white teeth at the corner, "
        "a hint of light stubble along the jaw), the rest of his face is INVISIBLE / SHADOW, "
        "a faint wisp of dark brown hair visible at the nape of his neck beneath the hat, "
        "wearing a faded LIGHT BLUE FLANNEL shirt unbuttoned over a clean white Bonds SINGLET, "
        "sleeves rolled to the elbows, faded blue Wrangler jeans, big silver rodeo BELT BUCKLE visible, "
        "Brett is HOLDING UP a tall GLASS DOUBLE PERCOLATOR BONG with one hand at chest height "
        "PRESENTING IT toward camera like a trophy, "
        "the BONG IS THE DRAMATIC FOCAL ELEMENT of the composition — clear glass shape with two "
        "percolator bubble chambers, ash + green herb residue at the bottom, "
        "BACKGROUND: country pub with bright RED XXXX NEON sign glowing on the wall, "
        "panel beater shop with roller doors, distant BLUE MOUNTAINS silhouette on the horizon, "
        "tall gum trees silhouetted against the deep navy night sky, "
        "warm amber streetlamp pools on the dirt patch, scattered tyre marks in the dirt, "
        "16-bit pixel art with wide-scene composition, "
        "the prize-handover moment after the hill climb victory, the MYSTERIOUS HAT-OBSCURED "
        "country boy silently presenting the bong — face hidden by the brim, "
        "Penrith country-edge atmosphere, "
        "the LOW AKUBRA BRIM HIDING THE FACE is the key visual hook"
    ),
    # habibi_show_vid: "Watch this cuz. Tony Tooks Two, Type R, doin'
    # donuts in MY suburb akhi." — Moey shoves his phone in your face.
    "moey_phone": (
        "pixel art close-up over-the-shoulder view of a Lebanese Australian man (Moey) "
        "wearing a crisp white open-collar button-up shirt with thick gold chain necklace and designer "
        "aviator sunglasses pushed up onto slicked black hair, well-groomed black stubble beard, "
        "his hand visible HOLDING UP a smartphone in portrait orientation in the centre of the frame, "
        "the PHONE SCREEN DOMINATES the centre of the frame — showing a frozen TIKTOK VIDEO frame: "
        "a red Honda Civic Type R hatchback doing wild donuts in an empty Penrith carpark "
        "with thick swirling white tyre smoke, '@TonyTooksTwo' username caption at the top, "
        "social-media UI (heart icon, comment icon, share icon, music note) stacked down the right side, "
        "view counter visible '600K' under the post, "
        "Moey angrily shoving the phone toward camera, the camera looking past his shoulder at his phone, "
        "his Liverpool kebab shop visible blurred in the background — vertical kebab spit, magenta neon, "
        "warm amber and magenta neon glow lighting the scene, deep navy night sky, "
        "16-bit pixel art with HIGH DETAIL on the phone screen content, the offending TikTok moment"
    ),
    # snout_race_offer_pre: "Tap that throttle HARD, sunshine." The
    # iconic drag-strip Christmas tree starting lights at the staging line.
    "drag_tree": (
        "pixel art EXTREME CLOSE-UP of an Eastern Creek Raceway drag-strip CHRISTMAS TREE STARTING LIGHT TOWER at night, "
        "the tall vertical metal pylon dominates the centre of the frame, "
        "stacked vertically from top to bottom on the pylon are FOUR LIGHT BULBS in metal hooded sockets: "
        "three large round AMBER yellow bulbs at the top all glowing brightly hot (the pre-stage / stage / "
        "3-amber countdown sequence) and below them a single LARGE GREEN bulb (waiting to light when the race starts), "
        "each bulb recessed in a black metal hood sticking out from the pylon, hard contrast lighting, "
        "thick black power cables running down the back of the pylon to a junction box at ground level, "
        "distant tarmac drag strip lanes visible blurred behind in the background with painted white start lines, "
        "tall white floodlight pylons standing in the distance silhouetted against the sky, "
        "deep navy night sky above with a sprinkling of stars, "
        "harsh stadium floodlights spilling cool white light into the scene, "
        "the TENSE moment before launch — staging area silence, all eyes on the tree, "
        "gritty 90s arcade racing aesthetic, 16-bit pixel art with HIGH DETAIL on the bulbs themselves, "
        "no human, no cars in shot, ONLY the Christmas tree light tower"
    ),
    # westfield_detour:player_decline — FIRST-PERSON POV: the protagonist
    # is sitting on the boot of his Evo at Westfield Mt Druitt carpark
    # scrolling his phone. Camera is looking DOWN at the phone screen
    # from his own eyes — we see his hands, his lap, the phone.
    "westfield_phone_pov": (
        "pixel art FIRST-PERSON POV looking DOWN at a smartphone held in TWO HANDS, "
        "the camera IS the protagonist's eyes — we see his own thumbs and fingers gripping "
        "a black smartphone in portrait orientation in the centre of the frame, "
        "the PHONE SCREEN FILLS THE CENTRE — showing a fictional Instagram-style social feed: "
        "thumbnail of a customised hatchback, a meme tile, scrolling timeline UI with rounded "
        "cards, small heart and comment icons, a notification badge at the top corner, "
        "the protagonist's HANDS visible at the bottom of the frame — male hands, tan complexion, "
        "thumbs hovering over the screen mid-scroll, simple black hoodie sleeves visible at the wrists, "
        "below the phone the protagonist's LAP visible — dark slim-fit jeans, "
        "and the WHITE PAINTED METAL SURFACE of his Evo's boot lid that he is sitting on, "
        "BLURRED PERIPHERAL BACKGROUND around the phone: the Westfield Mt Druitt carpark at midnight — "
        "out-of-focus rows of parked hatchbacks with faint neon underglow blurs (purple + blue), "
        "fluorescent ceiling-light pools spilling cool white onto the asphalt, "
        "a hint of the closed mall facade in the upper background, "
        "deep midnight blue night sky at the very top edge of the frame, "
        "the phone screen is the SHARP FOCAL ELEMENT — everything else is soft and blurred, "
        "16-bit pixel art first-person view, looking-down-at-phone composition, "
        "NO third-person body shot, NO face visible — just hands + phone + lap + ground, "
        "Western Sydney late-night quiet-moment atmosphere"
    ),
    # camry_tail_lights — replaces beat_rahul_revving on preet_lets_go.
    # The launch moment, but framed as just the back of Rahul's Camree
    # with the brake lights glowing red, viewed from behind / above.
    "camry_tail_lights": (
        "pixel art REAR view EXTREME CLOSE-UP of the back end of a grey Toyota Camry sedan "
        "at night on Wigram Street Harris Park, "
        "the camera positioned LOW and BEHIND the Camry, looking straight at the rear of the car, "
        "the BOOT LID AND BACK BUMPER FILL THE FRAME — only the rear half of the Camry visible, "
        "TWIN RED REAR TAIL LIGHT CLUSTERS dominate the composition, both glowing HOT RED — "
        "rectangular horizontal Camry tail lamps with red brake-light segments lit bright, "
        "small amber indicator panels at the outer edges, central CAMRY badge between them in chrome, "
        "white reverse-light panel below the brake lamps, RED INNER GLOW spilling onto the asphalt "
        "directly behind the car as a warm red puddle on the road surface, "
        "a small rear LIP SPOILER on the boot lid silhouetted at the top edge, "
        "a NSW number plate visible in the centre, dual chrome exhaust tips poking out beneath "
        "the rear bumper with faint white exhaust SMOKE drifting up between them, "
        "thin curls of white TYRE SMOKE wisping up at the lower corners (rear wheels brake-torquing), "
        "the grey Camry paintwork glistening faintly in the streetlamp glow, "
        "BACKGROUND: Wigram Street painted lane markings on the asphalt receding into the distance, "
        "Harris Park shopfronts blurred faintly in the far background — out-of-focus warm yellow "
        "and orange signage glow (Indian sweets shop, sari fabric store, 7-Eleven), "
        "warm amber streetlamp pools spilling onto the road, "
        "deep navy night sky above, "
        "NO driver visible, NO faces, ONLY the back end of the Camry — the moment right before "
        "Rahul drops the clutch and disappears, "
        "16-bit pixel art rear-view composition with HIGH DETAIL on the glowing red tail lights, "
        "cinematic launch-moment framing"
    ),
    # westfield_detour:start (+ pre-sprint beats): the establishing
    # shot of Westfield Mt Druitt bottom carpark — the calm-before-
    # the-cops scene. Row of customised hatchbacks, lads in the
    # trolley-bay circle, dim mall facade behind.
    "westfield_carpark": (
        "pixel art side-on view of the WESTFIELD MT DRUITT bottom carpark at midnight, "
        "a ROW OF CUSTOMISED HATCHBACKS parked sideways at angled stalls along the foreground edge — "
        "modified Honder Civics, Toyora Corollas, Mazadas, with neon underglow lighting (purple + blue), "
        "drop stances, sticker bombs on the rear windows, big rear wings, "
        "in the middle a LOOSE CIRCLE OF HALF A DOZEN HARDCORE WESTERN SYDNEY ESHAY LADS / DERROS "
        "loitering near the trolley bay — these are rough-as-guts CHEEKY LADS, not clean-cut kids: "
        "every one of them in a NAVY NIKE TN CAP pulled LOW over the eyes (peak FLAT, sticker still "
        "on the brim), MULLETS spilling out the back of the caps (long greasy hair at the neck, "
        "shaved sides), thin patchy CHIN-STRAP BEARDS or dirty stubble, sunken cheeks, "
        "PALE WASHED-OUT skin and SUN-BURNT red necks, hard-eyed lean expressions, "
        "outfits are FADED TN MAN polo shirts in red + navy + black with the Nike tick on the chest, "
        "or pilled-out NRL jerseys, paired with NAVY TRACKSUIT PANTS with the white Nike stripe "
        "tucked into long WHITE TUBE SOCKS pulled up to the calf, WHITE RUBBER SLIDES on the feet, "
        "a couple wearing baggy basketball shorts + sliders instead, "
        "neck and finger TATTOOS visible (cursive script tats), small SLEEPER EARRINGS in the ears, "
        "thin gold chains hanging at the collar, "
        "BODY LANGUAGE is loose loitering DERRO POSTURE — slouched shoulders, hands shoved deep in "
        "pockets, one leaning back against a trolley with arms crossed, one mid-spit on the asphalt, "
        "one with a bumbag slung across the chest, one CROUCHED on his heels in the iconic 'slav squat' "
        "next to the others, "
        "some holding tall cans of WICKED ICE-PINK PASSION POP or BUNDABERG rum, some smoking RYO rollies, "
        "one passing a small glass bong, one holding a bottle of cheap goon, "
        "a discarded MCDONALDS bag and scattered cigarette butts at their feet, "
        "loose boisterous menacing vibe but the music is LOW, calm-before-the-cops, "
        "scattered abandoned SHOPPING TROLLEYS around the trolley bay (one tipped on its side), "
        "the closed WESTFIELD MT DRUITT mall facade silhouetted in the background — wide concrete "
        "walls of a brutalist mall, dim 'WESTFIELD' sign on the wall facing the carpark, "
        "LOW FLUORESCENT CEILING LIGHTS spilling harsh white pools onto the asphalt, "
        "painted white parking bay lines on the asphalt with faded oil stains, "
        "deep midnight blue night sky above with stars + faint warm horizon glow, "
        "16-bit pixel art, GRITTY Western Sydney late-night ESHAY-DERRO carpark atmosphere, "
        "no close-up on individual faces, the rough crew + carpark vibe is the focus, "
        "this should look authentically WESTERN SYDNEY rough — not stylish, not fashion, "
        "these are dropkick lads + derros doing nothing of value in an empty carpark"
    ),
    # preet_credits_brenno_plea: "Oi lad, listen — the boys back at
    # the Westfield are gonna SMOKE without me bra. I NEED to get on.
    # Tonight. PLEEEASE bra. Just one more stop, swear down."
    # Brenno BEGGING outside Sweet Punjab post-race.
    "brenno_plead": (
        "pixel art MEDIUM CLOSE-UP of Brenno on Wigram Street Harris Park at night, "
        "Brenno is a skinny pale ginger Australian eshay teenager — short cropped GINGER ORANGE HAIR "
        "sticking out from under a NAVY BLUE NIKE TN CAP pulled low over his eyes (peak flat, "
        "yellow sticker still on the brim), faint patchy red-blond stubble, lots of FRECKLES across "
        "his cheeks and nose, long thin face, light blue eyes wide with desperate pleading, "
        "wearing a baggy MUSTARD YELLOW JUMPER + navy tracksuit pants tucked into white socks, "
        "BOTH HANDS CLASPED TOGETHER in front of his chest in a PRAYING / BEGGING POSE, "
        "leaning forward dramatically toward camera, eyebrows raised in puppy-dog desperation, "
        "mouth half open mid-plea, "
        "a brown paper grocery bag of curry powder + samosas tucked under one elbow, "
        "small CARTOON SPEECH BUBBLE 'PLEEEASE' near his head with hearts and exclamation marks, "
        "BACKGROUND: Wigram Street shopfronts blurred — SWEET PUNJAB Indian sweets shop with bright "
        "yellow neon signage and warm interior glow, sari fabric store with hanging colourful fabrics, "
        "7-Eleven glow further down, "
        "fairy lights strung across the street overhead, warm orange streetlamp glow, "
        "deep navy night sky above, "
        "16-bit pixel art mid-shot with HIGH DETAIL on Brenno's desperate pleading face + hands, "
        "the comic over-the-top BEGGING moment, Western Sydney post-race night atmosphere"
    ),
    # preet_post_lose:start: "AHAHA bhai it's okay! Chamkili dances
    # better, what can I say. Mainys are an artform, you'll get there.
    # Come — thali at Sweet Punjab is still on me. Loser still eats."
    # Rahul gestures warmly toward Sweet Punjab post-race.
    "rahul_thali_invite": (
        "pixel art WIDE SHOT side-on view of Wigram Street Harris Park at night outside SWEET PUNJAB, "
        "in the foreground centre Rahul standing on the footpath beside his parked grey Toyota Camry — "
        "Rahul is a Sikh Punjabi Australian man in his late twenties with a BRIGHT ROYAL BLUE DASTAR "
        "TURBAN and a thick full BLACK BEARD, friendly warm smile with teeth showing, head thrown "
        "slightly back mid-laugh, wearing a crisp LIGHT BLUE BUTTON-UP SHIRT with sleeves rolled to "
        "the elbows under an OPEN BLACK WAISTCOAT, dark jeans, "
        "ONE ARM EXTENDED OUT to the side gesturing OPEN-PALM TOWARD the open doorway of Sweet Punjab, "
        "the other hand resting friendly on the roof of his Camry, "
        "warm welcoming inviting body language, "
        "the OPEN DOORWAY of SWEET PUNJAB visible behind him as the focal element — bright golden "
        "interior glow spilling out onto the footpath, glimpse of stacked GOLDEN THALI PLATES on a "
        "counter inside with little metal bowls of curry + rice + naan, steam rising, "
        "the big bright yellow SWEET PUNJAB neon sign above the doorway, "
        "his grey Camry parked at the curb on the right side of the frame (just rear quarter visible), "
        "BACKGROUND: Wigram Street fairy lights strung overhead, sari fabric store glow further down, "
        "7-Eleven sign in the far distance, "
        "warm orange streetlamp pool, deep navy night sky above, "
        "16-bit pixel art wide composition, the WARM POST-RACE FRIENDSHIP moment — loser still eats, "
        "Harris Park late-night welcoming atmosphere"
    ),
    # khoa_explain_2: "Drive her every Sunday up Old Pacific Highway
    # with the crew. Then back to Cabra for phở. Best routine in the
    # country yeah." — Khoa's iconic Sunday cruise.
    "khoa_old_pacific": (
        "pixel art DYNAMIC ACTION side-on view of Khoa's WHITE PEARL Nissan S14 Silvia mid-CORNER on the "
        "OLD PACIFIC HIGHWAY — a sweeping windy forest road north of Sydney at GOLDEN HOUR Sunday morning, "
        "the S14 in the foreground centre tilted slightly LEANING into a corner with a hint of TAIL-OUT "
        "DRIFT angle, thin curls of WHITE TYRE SMOKE wisping from the rear wheels, the deep-dish "
        "gunmetal aftermarket wheels turning, slammed coilover stance, JDM tuner body with subtle aero, "
        "Khoa visible inside the cabin through the side window — a Vietnamese Australian man in his "
        "late twenties with crisp light blue button-up shirt, well-groomed black hair, AVIATOR SUNGLASSES "
        "on, polite focused confident expression, both hands on the steering wheel, "
        "TWO MORE TUNER CARS visible following further back along the road behind him (the Sunday crew) — "
        "a red Toyota Supra and a black RX-7 silhouetted in the distance, "
        "BACKGROUND: tall lush green EUCALYPTUS gum trees lining both sides of the road, dappled GOLDEN "
        "sunlight beams cutting through the tree canopy onto the asphalt in bright patches, "
        "the road curving up and around the side of a forested hill, painted white centre line, "
        "small road sign 'OLD PACIFIC HWY' visible beside the road, "
        "a glimpse of a distant deep BLUE COASTAL HORIZON visible between the trees, "
        "warm GOLDEN HOUR sky above with soft yellow + peach + light blue gradient, "
        "16-bit pixel art with HIGH DETAIL on the drifting S14 + golden sunlight, "
        "Sunday morning JDM crew cruise atmosphere, the iconic NSW touge spot"
    ),
    # khoa_geton_intro: "Bahaha Brenno told ya. Yeah I can sort ya.
    # Sticky green, $50 a gram, $200 a Q. Pickup happens HERE..."
    # Tight close-up on Khoa's hand showing a small zip-bag of green.
    "khoa_deal_hand": (
        "pixel art EXTREME CLOSE-UP from inside Khoa's white S14 Silvia at night in Cabra Maccas carpark, "
        "camera angle looking down into the centre console / passenger seat area, "
        "the FOCAL ELEMENT is Khoa's HAND HOLDING UP a small CLEAR ZIP-LOCK BAG of STICKY GREEN HERB — "
        "a translucent plastic baggie filled with SMALL ROUND LEAFY BUDS that look like TINY GREEN "
        "CABBAGES — each bud is a compact spherical ball of layered curled green leaves tightly "
        "clustered (think small brussels-sprouts / mini cabbage heads, NOT elongated pods, NOT cones), "
        "you can see distinct OVERLAPPING LEAFY OUTER LAYERS curling around each tight little bulb, "
        "five or six of these MINI-CABBAGE BUDS packed inside the bag in a loose pile, "
        "varied SHADES OF GREEN from light fresh-leaf green through deep forest green, the leaves "
        "have visible TEXTURE and tight curl pattern, frosted with subtle white TRICHOME crystals "
        "catching the light, sticky resin glinting on the leaf edges, the baggie tilted at an angle "
        "to camera so the small-cabbage buds read clearly, "
        "Khoa's hand visible — Vietnamese Australian man's hand, light blue button-up shirt sleeve rolled "
        "to the wrist, thumb and forefinger pinching the top of the baggie to dangle it forward, "
        "on the centre console below the baggie a small black DIGITAL POCKET SCALE with bright RED LED "
        "READOUT '28.0' glowing, beside the scale a folded stack of orange $50 + yellow $20 AUSTRALIAN "
        "BANKNOTES held by a black hair-tie band, "
        "the dashboard wood-grain visible at the bottom of the frame, S14 interior trim, gear shifter "
        "with a black aftermarket shift knob, "
        "BLURRED PERIPHERAL BACKGROUND through the windscreen — the Cabramatta Maccas drive-thru carpark, "
        "out-of-focus McDonalds GOLDEN ARCHES glowing yellow in the distance, warm amber carpark lamp glow, "
        "deep navy night sky above the dashboard line, "
        "the careful businesslike weed deal moment — calm, polite, well-run Cabra plug, "
        "16-bit pixel art with HIGH DETAIL on the SMALL CABBAGE-LIKE BUDS + scale display + cash, "
        "no human faces, ONLY the hand + product + counter-top items in close-up"
    ),
    # khoa_geton_q: "YEEEEEEEEW! Q the boys up adlay! ESHAYS. That'll
    # do us all weekend." — Brenno fist-pumping mid-YEEEEEW celebration.
    "brenno_yew_hype": (
        "pixel art MEDIUM SHOT of Brenno mid-CELEBRATION in the Cabra Maccas carpark at night, "
        "Brenno is the skinny pale ginger Australian eshay teenager — short cropped GINGER ORANGE HAIR "
        "sticking out from under a NAVY BLUE NIKE TN CAP pulled low (peak flat, yellow sticker on brim), "
        "FRECKLES across his cheeks and nose, baggy MUSTARD YELLOW JUMPER + navy tracksuit pants tucked "
        "into white tube socks, white rubber slides on his feet, "
        "Brenno is mid-FIST-PUMP — head THROWN BACK with mouth WIDE OPEN mid-yell of pure eshay joy, "
        "BOTH ARMS THRUST UP overhead in a victorious double-fist-pump pose, "
        "ONE HAND HOLDING UP a small BROWN PAPER GROCERY BAG (with a Q of green stashed inside, top "
        "crumpled closed) raised triumphantly in the air like a trophy, "
        "the OTHER HAND in a clenched FIST punching the air, "
        "bouncing on his toes, body language is PURE STOKED ESHAY HYPE, "
        "small STYLISED LIGHTNING BOLT + cartoon STAR sparkle effects radiating around his raised arms, "
        "small comic speech-bubble 'YEEEEEEW!' near his head, "
        "BACKGROUND: Khoa's WHITE PEARL Nissan S14 Silvia parked side-on behind him (just front quarter "
        "visible at the edge of frame), Cabra Maccas drive-thru carpark with the iconic golden ARCHES "
        "glowing bright yellow in the distance, painted white parking bay lines on the asphalt, "
        "warm amber and slight magenta neon glow from the carpark lamps, "
        "scattered abandoned shopping trolleys further off, deep navy night sky above, "
        "16-bit pixel art with HIGH DETAIL on Brenno's hyped pose + raised brown paper bag, "
        "the POST-DEAL ESHAY CELEBRATION moment — pure undiluted Cabra Maccas joy"
    ),
    # khoa_deal_setup: "Watch the spotlight bro. When it sweeps away —
    # TAP. When it's on us — WAIT. Six beats to the swap..." The tense
    # mini-game briefing — cop spotlight sweeping the carpark.
    "khoa_spotlight_brief": (
        "pixel art WIDE ELEVATED 3/4 view of the CABRAMATTA MACCAS DRIVE-THRU CARPARK at night, "
        "in the centre-foreground the player's WHITE Mitsubishi Lancer Evo IX and Khoa's WHITE PEARL "
        "Nissan S14 Silvia parked side-by-side in adjacent painted parking bays, both cars dark and "
        "stationary with headlights OFF, boots facing the camera, the small gap between the cars is "
        "the deal zone, "
        "a TALL BRIGHT WHITE COP SPOTLIGHT BEAM cuts diagonally across the carpark from the LEFT EDGE "
        "of the frame — a visible thick cone of stark white light slicing through the night air, "
        "DUST motes floating in the beam, the spotlight beam terminating as a bright white pool on the "
        "asphalt at the far side of the carpark (just past the two parked cars, NOT directly on them), "
        "a NSW POLICE PADDY WAGON parked at the LEFT edge of frame with the spotlight mounted on its "
        "roof rotating, blue + red dome lights OFF (silent mode), driver-side door open, "
        "a UNIFORMED FOOT-PATROL COP walking the lot in the MID-DISTANCE — silhouetted human pig-cop "
        "(Sgt Snout style: human shape with subtle pig snout) carrying a TORCH with a bright beam, "
        "the cop's torch beam sweeping a separate cone of light onto the asphalt as he patrols, "
        "BACKGROUND: McDonalds restaurant lit up at the back of the carpark — bright golden ARCHES sign "
        "glowing yellow, drive-thru lane visible, lit dining-room windows, "
        "deep navy night sky above, harsh fluorescent white pools mixed with warm amber lamp glow on "
        "the asphalt, painted white parking bay lines, "
        "TENSE STEALTH ATMOSPHERE — the careful 'watch the spotlight' moment, "
        "16-bit pixel art with HIGH DETAIL on the diagonal spotlight beam cutting across the scene, "
        "no human faces close-up, the spotlight + carpark layout is the focus, "
        "Cabramatta late-night carpark heist tension"
    ),
    # khoa_post_win:start — "Ahhh bro! That was SLICK. Six clean beats,
    # cop didn't even SNIFF us..." Slick post-deal celebration with cop
    # walking oblivious in the background.
    "khoa_slick_celebration": (
        "pixel art MEDIUM SHOT view through the open driver's-side window of the player's car looking "
        "OUT at Khoa standing on the asphalt beside his parked white pearl S14 Silvia in the Cabra "
        "Maccas carpark at night, "
        "Khoa is a Vietnamese Australian man in his late twenties leaning on his open S14 driver's door, "
        "crisp light blue button-up shirt with sleeves rolled to the elbows, well-groomed black hair "
        "(slightly mussed), small thin gold chain at the collar, friendly polite confident smile "
        "showing a faint GOLD CROWN on one of his upper teeth catching the light, "
        "his RIGHT HAND raised in a SLICK FINGER-GUN POINT at camera — index finger pointed straight at "
        "the player with thumb cocked up in playful 'we did it' approval, "
        "his other hand resting casually on the S14 door, body language is COOL SMOOTH-OPERATOR pride, "
        "in the BACKGROUND OUT-OF-FOCUS the uniformed FOOT-PATROL COP (Sgt Snout pig-cop) is visible "
        "walking AWAY across the carpark in the far distance — torch beam pointed the OTHER direction, "
        "his BACK to camera, oblivious, "
        "the carpark cop SPOTLIGHT visible sweeping ANOTHER part of the lot far away, "
        "the white S14 body visible behind Khoa with its deep-dish gunmetal wheels, "
        "BACKGROUND: McDonalds golden ARCHES glowing yellow further back, warm amber carpark lamp pools, "
        "painted white parking bay lines on the asphalt, "
        "deep navy night sky above, "
        "the SLICK 'we just got away with it' moment — businessman-cool celebration, "
        "16-bit pixel art with HIGH DETAIL on Khoa's finger-gun pose + gold tooth glint + cop walking "
        "away oblivious in the background, Cabra Maccas carpark stealth-deal aftermath atmosphere"
    ),
    # macca_country: "Aw mate, Penrith's the gateway to the bush. You
    # can SEE the Blue Mountains from here. Half me mates are out in
    # Lithgow, Bathurst, Dubbo. Spiritually I'm a bushie. Geographically
    # I'm next to a JB Hi-Fi." — the iconic city-meets-bush Penrith vista.
    "brett_penrith_vibe": (
        "pixel art WIDE ESTABLISHING shot of the western edge of PENRITH at dusk / early evening, "
        "the LEFT HALF of the frame is SUBURBAN STRIP-MALL Penrith — a wide intersection corner with "
        "a JB HI-FI storefront prominent (bright YELLOW JB HI-FI neon sign glowing against a black "
        "facade, big plate-glass display windows visible), beside it a Westfield carpark entrance, "
        "a Bunnings warehouse roof in the further distance, painted pedestrian crossing on the road, "
        "a tall flagpole with the Australian flag, "
        "the RIGHT HALF of the frame transitions immediately into COUNTRYSIDE — a worn bitumen country "
        "road heading away to the west with painted centre line, gum trees lining one side with "
        "drooping silver-green leaves, paddock barbed-wire fence on the other side, a faded ROAD SIGN "
        "'BLUE MOUNTAINS 30km / LITHGOW 120km / BATHURST 200km' beside the road, "
        "BACKGROUND: the iconic BLUE MOUNTAINS silhouetted on the FAR HORIZON — layered hazy ranges of "
        "deep blue-purple mountains receding into the distance, mist clinging to the lower slopes, "
        "the BLUE MOUNTAINS dominate the upper-right third of the composition, "
        "in the FOREGROUND off to one side a dark grey jacked-up Toyota Hilux SR5 (Brett's Hulix) "
        "parked at the edge of frame — chunky mud tyres, bullbar, snorkel, just a partial side view, "
        "SKY: dramatic dusk gradient — warm orange and pink along the horizon transitioning up to "
        "deep navy at the top of the frame, a few early stars beginning to twinkle, "
        "warm yellow streetlamps just starting to flicker on, "
        "the IDEOLOGICAL CONTRAST is the focus — suburban JB Hi-Fi on the left, vast Blue Mountains "
        "wilderness on the right, the 'gateway to the bush' moment, "
        "16-bit pixel art with HIGH DETAIL on the JB Hi-Fi sign + Blue Mountains layered horizon, "
        "Penrith dusk atmospheric establishing shot — Western Sydney edge-of-civilisation vibe"
    ),
    # macca_doubt: "Out the back of Penrith it's all dips, dirt, paddock
    # fences and dry creek beds. The Hulix eats that for breakfast."
    # Brett's Hilux mid-action bashing through bush terrain.
    "brett_hulix_offroad": (
        "pixel art DYNAMIC ACTION side-on view of Brett's dark grey jacked-up TOYOTA HILUX SR5 dual-cab "
        "ute MID-FLIGHT over a dirt mound on a bush track at sunset, "
        "the Hilux is the CENTRAL FOCAL ELEMENT — all four chunky BLACK MUD-TERRAIN TYRES OFF THE GROUND "
        "in mid-air leap (just past the apex of a jump), front of the truck slightly nose-up, "
        "thick clouds of brown DIRT and DUST kicking up behind and beneath the wheels in animated puffs, "
        "small chunks of mud and pebbles flying out the back, "
        "the Hilux has its full kit — heavy front BULLBAR, tall black SNORKEL on the A-pillar, light bar "
        "on the roof switched ON (two bright white beams pointing forward), aftermarket steel wheels, "
        "dirt + bushland grime caked along the lower body and rocker panels, headlights ON "
        "(yellow-white beams cutting forward), "
        "Brett visible inside the driver's cab through the side window — Akubra cowboy hat on, lopsided "
        "grin of pure 4WD JOY, both hands gripping the steering wheel tight, "
        "FOREGROUND: rugged DIRT TRACK with deep tyre ruts, dry rocky creek-bed crossing visible just "
        "ahead, scattered red gum branches and tussock grass, an old wooden PADDOCK FENCE with rusted "
        "barbed wire running parallel to the track on the right edge of frame, "
        "BACKGROUND: scrubby Australian BUSH paddock landscape — sparse gum trees with drooping leaves, "
        "tussock grass, dry yellow earth, a low ridge of hills further back, "
        "the BLUE MOUNTAINS layered silhouette on the FAR horizon in deep purple-blue, "
        "SKY: dramatic SUNSET gradient — warm orange + red on the horizon transitioning to deep purple "
        "and navy at the top of the frame, a few early stars appearing, "
        "BUSH OFF-ROAD MAYHEM atmosphere — 'eats it for breakfast' moment, "
        "16-bit pixel art with HIGH DETAIL on the jumping Hilux + dirt plume + sunset sky, "
        "Penrith country-edge 4WD action aesthetic"
    ),
    # mitcho_greet — "OI! Adlay! Bra, BRA... me Beemer is absolutely
    # cooked." First sight of Brenno gesturing wildly at his broken E36.
    "brenno_beemer_intro": (
        "pixel art WIDE SHOT REALISTIC scene of Blacktown Maccas drive-thru carpark at dusk, "
        "REALISTIC NPC STYLE matching the established Moey/Khoa/Rahul portrait fidelity — NOT cartoon, "
        "NOT anime, NOT chibi — proper proportioned human characters with realistic body anatomy, "
        "in the LEFT-CENTRE FOREGROUND Brenno standing in mid-rant — Brenno is a skinny pale ginger "
        "Australian eshay teenager in his late teens with realistic adult human proportions (NOT a "
        "chibi figure, NOT cute-style), short cropped ginger orange hair sticking out from under a "
        "NAVY BLUE NIKE TN CAP pulled low (peak flat, small yellow swoosh logo, sticker on brim), "
        "freckles across his nose and cheeks, faint patchy ginger stubble along the jaw, long narrow "
        "face with sharp pointed nose, "
        "Brenno's BODY angled toward camera mid-rant with BOTH ARMS THROWN OUT WIDE to the sides in "
        "animated frustrated gesture (palms upturned, elbows bent out, the 'WHAT DO YA RECKON BRA' "
        "stance), shoulders slightly hunched forward, mouth open mid-sentence showing teeth in genuine "
        "human expression, "
        "wearing a baggy MUSTARD YELLOW crewneck JUMPER, navy tracksuit pants tucked into long white "
        "tube socks pulled up to the calf, WHITE RUBBER SLIDES on his feet, "
        "to the RIGHT of Brenno his parked broken-down DEEP BLUE BMW E36 sedan taking up the right "
        "half of the frame — BONNET PROPPED FULLY OPEN above the engine bay, a THICK PLUME of "
        "DRAMATIC WHITE-GREY ENGINE STEAM billowing up out of the engine bay (the focal animation "
        "element — the steam plume rises and curls), the E36 is faded Cosmos blue paint with "
        "scuffs + a dented front quarter panel, slammed coilovers, black multi-spoke aftermarket "
        "wheels, M-Sport rear lip spoiler, looks WELL cooked, "
        "BACKGROUND: a NSW Maccas drive-thru restaurant facade visible in the middle ground — DO NOT "
        "render any text or letters on the building, instead show just the iconic LARGE BRIGHT "
        "YELLOW DOUBLE-ARCH 'M' LOGO standing on a tall metal pole glowing warm yellow against the "
        "dusk sky (no readable words, just the recognisable golden-arches silhouette), the restaurant "
        "is a low-slung brown brick building with lit dining-room windows visible, drive-thru lane "
        "marker, "
        "to the far right edge a small LEBANESE KEBAB SHOP next door with a glimpse of a magenta neon "
        "kebab-spit silhouette (NO readable text on the signs — just a stylised kebab-on-spit icon), "
        "DRAMATIC dusk sky — deep red and burnt orange gradient on the horizon transitioning up to "
        "navy at the top of the frame, a few early stars appearing, distant scrubby gum-tree "
        "silhouettes along the back fence, "
        "warm amber streetlamps just starting to come on with soft pools on the asphalt, "
        "painted white parking bay lines on the asphalt, faded oil stains, "
        "16-bit pixel art wide composition with HIGH DETAIL on Brenno's realistic body language + "
        "the smoking Beemer bonnet + the gold-M arches silhouette, "
        "REALISTIC PROPORTIONS — Brenno's body and face should look proportioned like the Moey/Khoa "
        "established characters, not chibi/anime, the iconic 'WHAT DO YA RECKON BRA' opening moment, "
        "Western Sydney late-arvo carpark drama, NO TEXT/LETTERS rendered on any signage"
    ),
    # waiting_alone (Harris Park) — "You sit alone in the driver's seat.
    # Engine ticking down. Distant Punjabi music drifts from a sari shop
    # across the road. A rat scuttles past a wheelie bin. Quiet."
    "harrispark_quiet_interior": (
        "pixel art FIRST-PERSON POV from inside the player's parked car looking THROUGH the WINDSCREEN "
        "out at Wigram Street Harris Park at night, "
        "the camera IS the protagonist's eyes — bottom third of the frame shows the inside of the car: "
        "the BLACK STEERING WHEEL (Momo-style aftermarket sports wheel) gripped lightly by the player's "
        "own HANDS at 9 and 3 o'clock (tan complexion, simple hands, no visible face), "
        "a curved DASHBOARD with warm orange-amber dashboard lights glowing — small CIRCULAR GAUGES "
        "(speedo + tacho) softly lit, "
        "WINDSCREEN FILLING THE UPPER TWO THIRDS of the frame with a faint reflection of the dash, "
        "looking out through the windscreen at WIGRAM STREET HARRIS PARK at night — empty street, "
        "warm yellow Indian shopfront glow across the road (SARI fabric store with hanging colourful "
        "fabrics visible through its window, INDIAN SWEETS shop next door, dim 7-Eleven sign further "
        "down), fairy lights strung overhead twinkling, "
        "a single SMALL STYLISED RAT scurrying low across the footpath past a green wheelie bin to "
        "one side (the rat is small but visible — the animation gif will show it scuttling), "
        "faint stylised MUSIC WAVE ripple lines drifting out the upper window of the sari shop "
        "(distant Punjabi music), "
        "deep navy night sky above with a few stars visible above the shopfronts, "
        "warm amber streetlamp pool on the asphalt below the windscreen view, "
        "the QUIET MOMENT — engine just cut, ticking down, the calm before Rahul arrives, "
        "16-bit pixel art first-person interior composition, "
        "the warm dashboard glow + sleepy quiet Harris Park street outside is the focus, "
        "no driver face visible — just hands + wheel + dash + view outside"
    ),
    # preet_food — "Aloo samosa from Apna Dera yaar, lifeblood..." Rahul
    # listing all the Harris Park Indian food spots. A montage spread.
    "rahul_food_spread": (
        "pixel art TOP-DOWN OVERHEAD view of a polished metal RESTAURANT TABLE laid out with a "
        "lavish INDIAN FOOD FEAST at Sweet Punjab Harris Park at night, "
        "the centrepiece is a large CIRCULAR STAINLESS-STEEL THALI PLATE covered in small metal bowls "
        "(katoris) of vibrant curries — bright orange BUTTER CHICKEN, yellow DAL, green PALAK PANEER, "
        "red ROGAN JOSH, white RAITA, with a mound of saffron-yellow BASMATI RICE in the centre and "
        "stacked GOLDEN-BROWN NAAN bread on the side, "
        "surrounding the thali on the table: a wrapped PAPER CONE of crispy GOLDEN TRIANGULAR SAMOSAS "
        "(steam rising from the cones), a long rolled MASALA DOSA on a banana leaf, a glass of mango "
        "LASSI with condensation droplets, a small terracotta cup of CHAI tea, two cones of pistachio "
        "and rose KULFI (Indian ice cream) on sticks beside, "
        "thin curls of STEAM rising from the hot curries (the animation focal element), "
        "small fresh CORIANDER LEAVES scattered as garnish, lemon wedges, sliced red onion + green chillies, "
        "the metal table polished and clean, "
        "the LIGHTING is warm golden interior glow spilling from above — Sweet Punjab restaurant "
        "ceiling lamps casting amber pools on the food, slight shadow under each dish, "
        "16-bit pixel art with HIGH DETAIL on the vibrant colourful food spread, "
        "the iconic 'come hungry' moment — Western Sydney Indian food porn composition, "
        "no human hands, no faces, ONLY the food laid out on the table"
    ),
    # preet_backstory — "My taya-ji has a mechanic shop on Marion Street...
    # UberEats by night - green bag never comes off, 4.94 star rating..."
    "rahul_ubereats_camry": (
        "pixel art INTERIOR view of Rahul's grey Toyota Camry, looking from the BACK SEAT FORWARD "
        "toward the dashboard and front seats at night, "
        "the FRONT PASSENGER SEAT (right side of frame) has a LARGE BRIGHT GREEN UberEats insulated "
        "DELIVERY BAG sitting on it as the focal element — the bag is a cubic black-and-NEON GREEN "
        "thermal bag with the UberEats logo printed boldly on the side (or 'EATS' in bold sans-serif "
        "letters on a vivid green panel), the strap dangling over the seat, "
        "MOUNTED on the dashboard in a phone cradle is a smartphone in landscape orientation showing "
        "an UBER-EATS DRIVER APP screen — a stylised map view with a glowing route line, a delivery "
        "status banner at the top, and a prominent RATING DISPLAY '4.94 ★' visible in the corner, "
        "HANGING from the rear-view mirror: a small framed SQUARE FAMILY PHOTO showing a Sikh family "
        "(small framed dangle), strung beside it a string of PRAYER BEADS / mala, "
        "the steering wheel + driver seat empty in the foreground left of frame, "
        "an open MECHANIC TOOLBOX visible on the floorboard with a few socket wrenches sticking out "
        "(taya-ji's influence), a torn carbie diagram + a small framed photo of a vintage car taped "
        "to the dashboard, "
        "warm WARM-ORANGE dashboard glow lighting the interior, "
        "through the windscreen at the front a glimpse of the warm yellow SWEET PUNJAB shopfront "
        "across the street and Wigram Street painted lane markings, deep navy night sky above, "
        "16-bit pixel art with HIGH DETAIL on the green UberEats bag + the 4.94 star app screen + "
        "the family photo dangling, the 'family man with TWO LIVES' moment, "
        "no human characters visible, just the meaningful objects in Rahul's car interior"
    ),
    # preet_mainy_intro — "And Saturday nights? Sacred bhai. App goes
    # OFFLINE. Mainys around Westmead, Marion Street round..." Saturday
    # night Rahul transformed into Parramatta street racer.
    "rahul_mainy_saturday": (
        "pixel art DYNAMIC HIGH-ANGLE 3/4 view of Rahul's grey Toyota Camry MID-DRIFT around a "
        "PARRAMATTA STREET ROUNDABOUT at night, the Camry pulling a hard tail-out slide around a "
        "small circular suburban roundabout with painted lane markings, "
        "THICK BILLOWING WHITE TYRE SMOKE pouring out from all four wheels as the Camry slides "
        "sideways across the asphalt — the smoke is the dramatic focal element (it will animate "
        "drifting and curling in the gif), "
        "the Camry visible at the centre with motion-blur on the wheels, slammed coilover stance, "
        "black aftermarket multi-spoke wheels, faint lip kit + rear lip spoiler, headlights ON with "
        "yellow-white beams cutting forward through the smoke, "
        "BLACK CURVED TYRE-MARKS painted on the asphalt all the way around the roundabout (multiple "
        "passes — this is a regular spot), "
        "Rahul visible through the driver-side window — Sikh Punjabi man with BRIGHT ROYAL BLUE "
        "dastar turban, BLACK BEARD, hands gripping the steering wheel, intense focused stare, "
        "a small STYLISED 'OFFLINE' BADGE floating in the upper-right corner of the frame (a black "
        "rounded pill with red 'OFFLINE' text — like a UI notification — visual storytelling for "
        "'app is off, racing mode on'), "
        "BACKGROUND: a tall WHITE GURDWARA (Sikh temple) with its iconic GOLDEN DOME visible "
        "silhouetted just past the roundabout, with warm illumination, a Sikh flag (nishan sahib) "
        "fluttering, a Parramatta suburban street with shops and tall light poles, "
        "deep navy night sky above with a few stars, "
        "warm amber streetlamps + cool fluorescent shopfront glow mixed lighting, "
        "16-bit pixel art with HIGH DETAIL on the drifting Camry + huge tyre smoke plume + "
        "gurdwara golden dome + OFFLINE badge, the 'Saturday nights are sacred' moment — "
        "Parramatta touge street-racing transformation"
    ),
    # brenno_grocer — "Alright bra, I'm duckin' in. Curry powder, garam
    # masala, plus two more Mum tacked on while we were drivin'. Won't
    # be ten minutes adlay. ESHAYS. Hold the fort." Brenno mid-stride
    # heading into the Indian grocer on Wigram Street to do Mum's run.
    "brenno_grocer_dash": (
        "pixel art REALISTIC SEMI-PHOTOREAL medium-shot side-on view of Wigram Street Harris Park "
        "at night, REALISTIC NPC PROPORTIONS matching the established Moey/Khoa/Rahul portrait "
        "fidelity — NOT cartoon, NOT anime, NOT chibi, proper proportioned human body anatomy, "
        "Brenno is a skinny pale ginger Australian eshay teenager in his late teens with realistic "
        "adult human proportions (head proportionally correct to body), short cropped ginger orange "
        "hair under a NAVY BLUE NIKE TN CAP pulled low (yellow swoosh, sticker on flat brim), "
        "freckles across nose + cheeks, faint patchy ginger stubble, long narrow face, "
        "Brenno caught MID-STRIDE pushing through the OPEN DOORWAY of an INDIAN GROCERY SHOP — "
        "body angled forward leaning into the doorway, one foot across the threshold inside the "
        "shop, the other foot still on the footpath behind, ONE HAND on the door handle pushing "
        "inward, OTHER HAND clutching a small CRUMPLED HANDWRITTEN SHOPPING LIST (no readable "
        "text — just scribble lines suggesting handwriting), head turned slightly back toward "
        "camera with a half-grin, mouth open mid-yell, "
        "wearing the MUSTARD YELLOW crewneck JUMPER, navy tracksuit pants tucked into white tube "
        "socks, WHITE RUBBER SLIDES on his feet, "
        "the GROCERY SHOPFRONT dominating the right half of the frame — glass-paned door propped "
        "open, glass display window beside showing bold iconic product silhouettes (NO readable "
        "text on any label/packaging): a tall sack of golden-yellow rice with twine tie, stacked "
        "red jars of pickle (shape only), hanging bunch of dried red chillies in the corner, "
        "pyramid of colourful spice packets with stylised dot/leaf icons (NO words), "
        "brightly-lit warm yellow shop INTERIOR visible through the open doorway with rows of "
        "spice shelves dimly visible inside, dim CRT TV mounted high inside flickering with "
        "Bollywood show, "
        "above the doorframe a NEON SIGN — only a stylised mortar-and-pestle icon shape glowing "
        "yellow-orange (NO readable letters or words), "
        "BACKGROUND: Wigram Street to the left — warm yellow lit shopfronts further down (only "
        "shape silhouettes, NO text on any signage), parked cars at the curb, fairy lights strung "
        "overhead twinkling, warm orange streetlamp pool on the footpath, deep navy night sky "
        "above with stars, "
        "16-bit pixel art with HIGH DETAIL on Brenno's realistic mid-stride pose + the open "
        "doorway + the shop interior glow, REALISTIC PROPORTIONS matching the Moey/Khoa NPC tier, "
        "the 'duckin' in for Mum's shopping' moment, NO TEXT/LETTERS rendered on any signs or list"
    ),
    # preet_greet — "Sat Sri Akal my friend! ... twelve years undefeated
    # on this street, twelve years. Chamkili has not lost ONCE. But come,
    # sit, eat, ask me anything bhai." Rahul's warm friendly intro.
    "rahul_greet_welcome": (
        "pixel art REALISTIC SEMI-PHOTOREAL medium-wide side-on shot of Rahul standing centred on "
        "WIGRAM STREET HARRIS PARK FOOTPATH at night with rich vibrant streetscape behind, "
        "REALISTIC pixel art style matching the established Moey/Khoa/Rahul portrait fidelity — "
        "NOT cartoon, NOT anime, NOT chibi, "
        "the setting must read clearly as INDIAN HARRIS PARK NIGHTLIFE — NOT a dark empty street, "
        "Rahul (Sikh Punjabi Australian man in his late twenties, BRIGHT ROYAL BLUE DASTAR turban, "
        "thick full BLACK BEARD, crisp light blue button-up shirt with sleeves rolled to the "
        "elbows under an OPEN BLACK WAISTCOAT, dark jeans, brown leather sandals) standing on the "
        "footpath with both arms OUTSTRETCHED in a wide welcoming gesture, palms up, head slightly "
        "tilted back, warm friendly grin showing teeth, "
        "ONE HAND lifted holding a styrofoam takeaway plate with a single GOLDEN-BROWN TRIANGULAR "
        "ALOO SAMOSA + a small smear of green mint chutney, presented toward camera, "
        "the GREY TOYOTA CAMRY 'CHAMKILI' parked at the curb DIRECTLY BEHIND Rahul — slammed "
        "coilover stance, BLACK AFTERMARKET multi-spoke wheels, small front lip kit + modest rear "
        "lip spoiler, headlights ON casting yellow beams forward, body clearly visible in detail, "
        "small STYLISED HEART + STAR sparkle icons drifting up around Rahul to suggest hospitality, "
        "RICH BUSY WIGRAM STREET BACKGROUND must be clearly visible (NOT just trees + dark sky): "
        "(1) directly across the road behind the Camry — the warm GOLDEN-YELLOW glowing facade of "
        "SWEET PUNJAB Indian sweets restaurant with bright illuminated SHOPFRONT WINDOWS showing "
        "stacks of colourful Indian sweets on shelves (mithai trays — colourful round + square + "
        "diamond shapes in pink, yellow, green, orange), warm interior lamp glow spilling out, "
        "(2) NEXT to Sweet Punjab a SARI FABRIC STORE with colourful hanging fabrics behind the "
        "front window glass — vivid pink, blue, gold draped silks visible, "
        "(3) further down a 7-ELEVEN convenience store glowing with cool white fluorescent light, "
        "the iconic 7-Eleven orange-green-red stripe band on the awning (NO readable text — only "
        "the recognisable striped colour pattern), "
        "(4) WARM YELLOW FAIRY LIGHTS strung in zigzag rows ACROSS the street overhead between "
        "shopfront balconies, multiple strands twinkling (the focal animation element — they "
        "twinkle), "
        "(5) the road's painted yellow lane-divider stripe visible in the middle ground, parked "
        "cars at the curb further down the road, "
        "(6) warm AMBER STREETLAMP POOLS spilling onto the asphalt + footpath, the warm tones "
        "saturating the scene (NOT cold dark navy isolated), "
        "deep navy night sky visible only at the top edge of the frame above the building lines, "
        "16-bit pixel art with HIGH DETAIL on Rahul's welcoming pose + Camry + samosa offered + "
        "the rich illuminated Wigram Street shopfronts + fairy lights overhead, REALISTIC "
        "proportions matching Moey/Khoa NPC tier, "
        "the 'Sat Sri Akal, come share food' moment, RICH ATMOSPHERIC Harris Park hospitality "
        "vibe — busy living street NOT empty road, NO readable text on signage anywhere"
    ),
    # preet_explain — "Bhai PLEASE do not insult Chamkili by saying 'just
    # a Camree'. 1MZ-FE V6, yes, but with Eaton supercharger off a Lotus,
    # custom intake I welded myself in taya-ji's shop, six-speed manual
    # swap, stripped interior. 320 horsepower in 1100 kilos."
    "chamkili_engine_specs": (
        "pixel art REALISTIC top-down view DOWN INTO the OPEN ENGINE BAY of a TOYOTA CAMRY SEDAN "
        "(specifically a CAMRY — NOT a truck, NOT a Hilux, NOT a ute) on Wigram Street Harris Park "
        "at night, the BONNET PROPPED OPEN above the frame revealing the engine bay below, "
        "the SHAPE of the engine bay MUST clearly read as a SEDAN engine bay — WIDE BUT SHALLOW "
        "(low bonnet line), with the FRONT FENDER TOPS visible left and right showing the SLOPED "
        "AERODYNAMIC CONTOURS of a Camry sedan (NOT the squared-off boxy contours of a ute bonnet), "
        "the engine bay DOMINATES the composition — a built TOYOTA 1MZ-FE V6 ENGINE in a TRANSVERSE "
        "FRONT-WHEEL-DRIVE LAYOUT (engine oriented SIDEWAYS across the bay, NOT longitudinal — this "
        "is what makes it clearly a Camry vs a Hilux which is longitudinal): cast aluminium V6 "
        "block sitting SIDEWAYS with the alternator on one end and the timing belt cover on the "
        "other, two banks of three cylinders visible from above, "
        "POLISHED ALUMINIUM EATON M62 SUPERCHARGER mounted on top with iconic ribbed silver case "
        "(off a Lotus — the focal element of the build), a HOMEMADE WELDED CUSTOM ALUMINIUM INTAKE "
        "MANIFOLD with visible TIG-weld bead lines snaking from the supercharger to the throttle "
        "body, POLISHED CHROME INTAKE PIPING with silver hose clamps, a black silicone hose, "
        "STAGGERED BLUE IGNITION COIL PACKS on each bank, polished aluminium rocker covers with "
        "raised 'TOYOTA' badging, an aftermarket aluminium INTAKE BREATHER FILTER (cone), "
        "a STAINLESS-STEEL HEADER WRAPPED in white heat tape running down to the manifold, "
        "a small CAMRY-LOGO DECAL clearly visible on the corner of the airbox or strut tower (the "
        "iconic stylised Camry script — small but readable as 'CAMRY' to confirm the car identity), "
        "a GLOSSY VINYL DECAL on the inside of the bonnet reading 'CHAMKILI' in flowing Punjabi-"
        "style script + '1MZ-FE V6 SUPERCHARGED 320HP', "
        "the FRONT EDGE of the bonnet aperture visible at the lower edge of the frame showing the "
        "TOP of the front grille — a CLASSIC CAMRY-SHAPED HORIZONTAL GRILLE (low wide rectangular "
        "sedan grille, NOT a tall aggressive truck grille) with the TOYOTA T-LOGO BADGE in the "
        "centre, "
        "between the front strut towers a stylised CAMRY-LOGO SHOCK TOWER BRACE bar visible "
        "horizontally across the bay (a sedan upgrade — confirms identity), "
        "small dust on the engine but otherwise meticulously CLEAN and POLISHED, "
        "loose POWER STEERING PUMP visible to one side, ABS unit, mass-airflow sensor, battery in "
        "the corner with red+black terminals, "
        "warm yellow Harris Park streetlamp glow + a single SHOP-MECHANIC DROPLIGHT clamped to the "
        "open bonnet casting bright contrast lighting on the engine, "
        "BACKGROUND: faint glimpse of WIGRAM STREET behind the open bonnet — warm yellow SWEET "
        "PUNJAB neon glow blurred far behind, fairy lights overhead twinkling, deep navy night sky, "
        "16-bit pixel art with HIGH DETAIL on the TRANSVERSE V6 + Eaton supercharger + Camry-shaped "
        "grille + Chamkili decal, REALISTIC pixel art style matching Moey/Khoa fidelity, "
        "the engine must CLEARLY belong to a CAMRY SEDAN (transverse FWD layout + low sedan grille "
        "+ Camry badging), the 'do NOT insult Chamkili' loving-engineering moment, no human hands"
    ),
    # preet_mainy_proud — "AHAHA you saw it! That was a clean 720 my
    # friend. Anti-clockwise too, against the camber... Mum was watching
    # from upstairs, gave me a thumbs up. Chamkili sliiiides like she's
    # dancing at a wedding yaar."
    "chamkili_720_spin": (
        "pixel art REALISTIC side-on view of Rahul's grey Toyota Camry 'Chamkili' STATIONARY in the "
        "middle of Wigram Street Harris Park at night, doing a HUGE BURNOUT — front wheels SPINNING "
        "violently with MASSIVE BILLOWING WHITE TYRE SMOKE pouring out from BOTH FRONT WHEEL WELLS, "
        "REALISTIC pixel art style matching Moey/Khoa NPC fidelity, "
        "the Camry visible side-on in the centre of the frame, slammed coilover stance, black "
        "aftermarket multi-spoke wheels, this is a FRONT-WHEEL-DRIVE car doing a stationary FWD "
        "BURNOUT — the rear wheels are still planted on the asphalt (parked), the front wheels are "
        "spinning fast (faint motion-blur lines on the front wheel spokes), "
        "the FRONT WHEELS LIT UP — thick clouds of WHITE TYRE SMOKE billowing UPWARD AND OUTWARD "
        "from BOTH front wheel arches in dramatic curling plumes (the focal animation element — "
        "the smoke billows and curls), the smoke entirely engulfs the front of the car obscuring "
        "the front bumper, headlights barely visible cutting yellow beams through the smoke, "
        "thick BLACK SKID MARKS on the asphalt directly under each front wheel (long parallel "
        "rubber streaks burnt into the road from sustained burnout), "
        "the body of the Camry tilted very slightly back (nose lifted from torque) — clearly a "
        "Camry sedan silhouette (NOT a coupe or wagon), front lip kit + small front splitter "
        "visible above the smoke, modest rear lip spoiler on the boot lid, "
        "Rahul visible through the driver-side window gripping the steering wheel with both hands, "
        "BIG GRIN showing teeth, blue dastar turban + black beard visible, head slightly back "
        "in laughter, "
        "in the UPPER LEFT corner of the frame a TWO-STOREY HARRIS PARK SHOPFRONT BALCONY visible "
        "with an open KITCHEN WINDOW above the shops, MUM (a Sikh Punjabi Australian woman in her "
        "fifties wearing a colourful patterned salwar kameez) leaning out the open kitchen window, "
        "ONE HAND extended giving a clear THUMBS-UP with a proud smile (small but clearly visible — "
        "key story detail), warm interior kitchen light spilling out behind her, "
        "BACKGROUND: Wigram Street shopfronts in the middle distance — SWEET PUNJAB warm yellow "
        "neon glow, sari fabric store with hanging colourful fabrics, 7-Eleven sign further down "
        "(only shape recognition — striped colour band, NO readable text), fairy lights strung "
        "overhead twinkling between shopfront balconies, "
        "warm orange streetlamp pools on the asphalt around the burnout smoke, deep navy night sky "
        "visible above the building lines, "
        "16-bit pixel art SIDE-ON composition with HIGH DETAIL on the Camry doing a violent FWD "
        "front-wheel burnout + huge billowing smoke + skid marks + Mum's thumbs-up balcony window, "
        "REALISTIC proportions NOT chibi, the 'Chamkili sliiiides like she's dancing at a wedding' "
        "stationary FRONT-WHEEL BURNOUT moment, NO TEXT/LETTERS on background signage"
    ),
    # preet_race_offer — "AAAAAHA! ... Wigram Street to the Westmead
    # roundabout, three full mainys at the end before we call it. If you
    # win, you are the king of Harris Park..." Race route map briefing.
    "rahul_race_route_map": (
        "pixel art STYLISED OVERHEAD MAP VIEW of the race route from Harris Park to Westmead at "
        "night, in the style of a vintage racing-game route briefing screen, "
        "a TOP-DOWN STREET MAP filling the frame — drawn in muted dark navy and slate grey blocks "
        "representing buildings + city blocks with thin yellow road lines weaving between them, "
        "thin Harris Park street grid with Wigram Street labelled with a small white text marker "
        "'WIGRAM ST' at the bottom-right, faded shopfront markers (small yellow squares labelled "
        "'SWEET PUNJAB' + '7-ELEVEN' along the road), "
        "a BOLD GLOWING DASHED ORANGE ROUTE LINE drawn over the top — starts at a bright STARTING-"
        "FLAG MARKER in the bottom-right corner on Wigram St, traces a winding path north-west "
        "through Parramatta side streets, crossing a small river bend, then ends at a clearly "
        "labelled 'WESTMEAD ROUNDABOUT' marker in the upper-left corner — a TIGHT CIRCULAR ROUNDABOUT "
        "in the middle of an intersection, with THREE CONCENTRIC CURVED ARROWS spinning around it "
        "(visual shorthand for 'three full mainys / three full circles'), "
        "small painted 'x3 MAINYS' label beside the roundabout in flickering yellow text, "
        "a small 'CHECKERED FLAG' icon next to the roundabout marking the finish, "
        "scattered along the route are small KEY POINT MARKERS — a tiny GURDWARA dome icon "
        "(labelled 'GURDWARA BACK LANE') showing the shortcut Rahul mentioned, "
        "a STYLISED CARTOON HAND-DRAWN COMPASS ROSE in one corner with N/S/E/W, "
        "subtle stylised STREETS GRID texture in the background, a thin trail of stylised dots "
        "tracing the route in animated pulse pattern (the focal animation element — the dashed line "
        "pulses orange/red along its length suggesting motion), "
        "BACKGROUND: muted dark night-time map palette — deep navy + slate grey + thin yellow road "
        "lines, the route dash pulsing bright orange, "
        "small overlaid text labels in stylised game-UI font, "
        "16-bit pixel art map-briefing aesthetic, the 'here's the race route' video-game pre-race "
        "briefing moment — no characters, no cars, ONLY the map + glowing route + key markers"
    ),
    # preet_music_pick — "Pre-loaded already my friend. 'Apna Time
    # Aayega' from Gully Boy. We hit launch when the beat drops at 0:34.
    # You'll hear it. Whole street will hear it."
    "rahul_stereo_apna_time": (
        "pixel art CLOSE-UP ANGLED view into the dashboard CENTRE-CONSOLE STEREO HEAD UNIT of Rahul's "
        "grey Toyota Camry interior at night, "
        "the AFTERMARKET PIONEER HEAD UNIT DOMINATES the centre of the frame — a black rectangular "
        "double-DIN car stereo with a bright LCD screen showing: at the top in bold WHITE TEXT the "
        "TRACK TITLE 'APNA TIME AAYEGA' and below in smaller text 'GULLY BOY OST', "
        "below that a HORIZONTAL EQ WAVEFORM bar with rainbow-coloured frequency bars dancing "
        "(animation focal element — the EQ bars pulse and bounce), "
        "a SCRUBBING PROGRESS BAR underneath at '0:33' position about to flip to 0:34 — RIGHT ON "
        "THE BEAT-DROP, with a small flashing 'PLAY' triangle indicator, the timestamp '0:33' shown "
        "in glowing blue digital readout, "
        "physical buttons + volume knob visible around the unit (chrome dials, rubber buttons), "
        "the FM/AUX/USB indicator lit, "
        "the stereo BACKLIGHT casting a cool BLUE-CYAN GLOW onto the surrounding dashboard textures, "
        "subtle PUNJABI BHANGRA MUSIC WAVE ripples drifting up from the speaker grilles on either "
        "side of the head unit (stylised concentric ripple lines), "
        "BACKGROUND: glimpse of the rest of the Camry interior — warm orange dashboard glow behind, "
        "the steering wheel partial in the upper-left corner of the frame, gear shifter with leather "
        "shift boot visible on the right, a small dangling family photo + prayer beads off the rear-"
        "view mirror at the top edge, through the windshield far in the background a faint blurred "
        "view of Wigram Street shopfronts, "
        "16-bit pixel art with HIGH DETAIL on the stereo screen + dancing EQ bars + 0:33 timestamp, "
        "the 'whole street will hear it' moment — pre-launch music cued, no human characters"
    ),
    # preet_post_win:start — "Arre wah! What driving my friend... Chamkili
    # is in shock only, I am also in shock! First time she has lost in
    # twelve years I am telling you." Rahul stunned-amazed reaction.
    "rahul_shock_amazed": (
        "pixel art MEDIUM CLOSE-UP front view of Rahul standing on Wigram Street Harris Park at night, "
        "Rahul (Sikh Punjabi Australian man in his late twenties, BRIGHT ROYAL BLUE DASTAR turban, "
        "thick full BLACK BEARD, crisp light blue button-up shirt with sleeves rolled to the elbows, "
        "OPEN BLACK WAISTCOAT, dark jeans) caught MID-REACTION of GENUINE STUNNED AMAZEMENT — "
        "BOTH HANDS RAISED to either side of his head (palms facing his cheeks, NOT touching, hovering "
        "about an inch out), fingers spread wide, elbows bent up, "
        "MOUTH WIDE OPEN in a HUGE SHOCKED SMILE showing teeth — the rare combination of disbelief + "
        "joy + 'I cannot believe what I just saw', eyebrows raised HIGH almost to the turban edge, "
        "wide-open EYES sparkling with admiration, "
        "small stylised CARTOON SPEECH BUBBLE 'WHAT?!' or '???' floating beside his head in animated "
        "wiggle motion, a few small white-burst SPARKLE STARS animated around his head suggesting "
        "the shock-pop moment, "
        "his GREY TOYOTA CAMRY 'CHAMKILI' parked side-on directly behind him taking up the middle "
        "ground — slammed coilover stance, black aftermarket wheels, white chalk '12-0' tally marks "
        "on the rear quarter panel (one of them STRUCK THROUGH with a fresh red X, the new '12-1' "
        "tally just being added), thin curl of white steam wisping up from the bonnet (from the race), "
        "BACKGROUND: Wigram Street shopfronts visible behind — SWEET PUNJAB warm yellow neon, fairy "
        "lights strung overhead, sari fabric store, 7-Eleven, "
        "warm amber streetlamp glow on the asphalt, deep navy night sky above, "
        "16-bit pixel art with HIGH DETAIL on Rahul's stunned-amazed face + raised hands + the "
        "freshly-struck-through tally on the Camry, the rare 'first loss in twelve years' moment, "
        "Western Sydney Harris Park humbled-by-the-young-blood vibe"
    ),
    # preet_chamkili_meaning — "Shiny one, in Punjabi! She has been with
    # me since I was tiny in Harris Park. Even when she loses she's
    # gorgeous yaar." A nostalgic flashback to young Rahul + Camry.
    "chamkili_nostalgic_flashback": (
        "pixel art SOFT SEPIA-TONED NOSTALGIC FLASHBACK panel — a memory from twelve years ago in "
        "Harris Park, the entire scene rendered in warm faded SEPIA-BROWN + GOLDEN tones with soft "
        "vignette edges (like an old polaroid), small stylised film-frame border around the scene, "
        "in the CENTRE of the composition stands YOUNG RAHUL (about TEN years old, small thin Sikh "
        "Punjabi boy with a SMALL BLUE PATKA child's turban tied on his head, fluffy black sideburns "
        "starting to come in, BIG WIDE EYES with absolute admiration, wearing a clean white school "
        "polo shirt and dark blue shorts, white school socks pulled to the knees), "
        "young Rahul's SMALL HAND resting reverently on the BONNET of a SHINY-NEW grey TOYOTA CAMRY "
        "(early-2000s vintage — boxier Camry shape than the current modified version, factory-fresh "
        "paint glinting, factory steel wheels with chrome caps, plain badging, NO modifications yet), "
        "the Camry parked in front of a HARRIS PARK DRIVEWAY (suburban brick-veneer family house with "
        "a yellow front door, neatly trimmed bottlebrush bush, white painted concrete drive), "
        "to one side of young Rahul stands his TAYA-JI (uncle figure) — an older Sikh Punjabi man "
        "in his forties with a tall ORANGE turban and a thick salt-and-pepper beard, wearing a grease-"
        "stained mechanic's overall, hand resting on young Rahul's shoulder with a proud warm smile, "
        "the uncle holding a polishing CLOTH in his other hand mid-handover, "
        "GENTLE WARM GOLDEN-HOUR SUNLIGHT spilling across the scene from the side, soft shadow stretching "
        "across the driveway, "
        "a few small stylised twinkle-sparkles around the polished Camry bonnet suggesting 'she shines', "
        "a tiny STYLISED HEART floating above young Rahul's head, "
        "BACKGROUND: blurred Harris Park suburban street with telegraph poles, gum trees in dappled "
        "golden light, a faded yellow Sweet Punjab shop sign tiny in the distance (showing it's the "
        "same street), "
        "the entire panel rendered in WARM SEPIA + GOLD tones (not the usual cool night palette), "
        "16-bit pixel art nostalgic-flashback aesthetic with HIGH DETAIL on young Rahul's reverent "
        "expression + the pristine factory Camry + taya-ji's proud smile, "
        "the 'she has been with me since I was tiny' tender backstory moment"
    ),
    # preet_tech — "Weight, bhai. ALL weight. Stripped interior,
    # lightweight Enkei wheels, carbon bonnet from a wrecker in Lidcombe.
    # 1100 kilos total. And the music — Divine on full volume."
    "chamkili_weight_breakdown": (
        "pixel art TECHNICAL CUTAWAY DIAGRAM view of Rahul's grey Toyota Camry 'Chamkili' on Wigram "
        "Street at night, the Camry shown side-on in the centre of the frame but with stylised "
        "DIAGRAM-STYLE LABEL CALLOUTS pointing to her key weight-reduction modifications, "
        "around the Camry are FOUR THIN DASHED-LINE CALLOUT ARROWS pointing from the relevant car "
        "parts out to small text-label cards in the corners: "
        "(1) UPPER-LEFT callout to the BONNET — labelled 'CARBON FIBRE BONNET' showing a small inset "
        "panel with the iconic CARBON WEAVE pattern (interwoven black + dark grey checkerboard), "
        "a small subtitle 'WRECKER, LIDCOMBE', "
        "(2) LOWER-LEFT callout to the FRONT WHEEL — labelled 'ENKEI RPF1' with a tiny inset close-up "
        "of the spoked Enkei wheel, subtitle 'LIGHTWEIGHT FORGED', "
        "(3) UPPER-RIGHT callout to the CABIN — labelled 'STRIPPED INTERIOR' with an inset showing "
        "the rear interior: NO BACK SEATS, just bare welded sheet metal floor with a small bolted-in "
        "fire extinguisher + a half cage of welded steel tubing, "
        "(4) LOWER-RIGHT callout to the BOOT — labelled 'SUBWOOFER' showing an inset of a giant black "
        "JL AUDIO subwoofer cone mounted in the boot with bright VIBRATING BASS RINGS animating "
        "around it (concentric sound-wave circles pulsing), "
        "in the BOTTOM-CENTRE a large stylised SCALE READOUT showing '1100 kg' in glowing yellow "
        "digital text with a small mass-icon, surrounded by a thin animated border that pulses, "
        "the Camry itself is rendered cleanly with all its mods visible — slammed stance, big rear "
        "spoiler, lip kit, the wheels matching the Enkei callout, the bonnet showing carbon weave, "
        "BACKGROUND: faint Wigram Street shopfronts in deep navy blur — Sweet Punjab + sari store "
        "behind, deep night sky, "
        "16-bit pixel art technical-diagram aesthetic with HIGH DETAIL on the four callout insets + "
        "1100 kg readout, the 'WEIGHT bhai, ALL weight' breakdown moment, no human characters"
    ),
    # preet_retry — "Harris Park remains Rahul's. Come back when you've
    # got more horsepower — and a louder stereo." Post-loss credits — the
    # 'king of Harris Park' victory icon shot.
    "rahul_king_harris_park": (
        "pixel art CINEMATIC WIDE LOW-ANGLE HERO SHOT of Rahul standing TRIUMPHANTLY ON TOP of the "
        "BOOT LID of his grey Toyota Camry 'Chamkili' parked in the middle of Wigram Street at night, "
        "the camera positioned LOW looking UP at him to make him look heroic, "
        "Rahul standing with feet planted shoulder-width apart on the Camry boot, "
        "BOTH ARMS RAISED HIGH OVERHEAD in a victorious V-shape, fists clenched, head tilted slightly "
        "back with a confident triumphant grin showing teeth, blue dastar turban + black beard + "
        "open black waistcoat over light blue shirt, "
        "a small stylised GOLDEN CROWN ICON FLOATING just above his head in the air (cartoon-style "
        "crown indicating 'king'), small RADIATING SUNRAY pixels behind him from the crown, "
        "a STYLISED FLAPPING PROUD BANNER in the upper portion of the frame reading 'KING OF HARRIS "
        "PARK' in bold yellow text against an orange background, the banner edges fluttering as if in "
        "the wind (the animation focal element — banner ripples), "
        "the Camry beneath him visible — slammed coilover stance, gleaming after a wash, '12-1 STILL "
        "KING' tally chalk-mark on the rear quarter panel, headlights ON casting bright forward beams, "
        "BACKGROUND: WIGRAM STREET behind him with all the Harris Park crew gathered watching — "
        "small silhouetted figures of locals raising their arms in cheer (a Sikh family on the upstairs "
        "balcony, shop owners in the doorways of Sweet Punjab and the sari fabric store, a couple "
        "of younger lads on the footpath), all watching the moment, "
        "the iconic GOLDEN GURDWARA DOME visible silhouetted on the horizon to the far back illuminated, "
        "fairy lights strung overhead twinkling brightly, warm amber streetlamps + cool fluorescent "
        "shopfront glow mixing, deep navy night sky with stars + a bright moon, "
        "16-bit pixel art with HIGH DETAIL on Rahul's hero pose + floating crown + KING OF HARRIS PARK "
        "banner + crowd cheering, the 'Harris Park remains Rahul's' eternal-undefeated moment"
    ),
    # brenno_leaves — "Brenno bowls into the Indian grocer. The door
    # chimes. The street falls completely silent." Empty street, alone.
    "wigram_street_empty_silence": (
        "pixel art WIDE EMPTY street view of Wigram Street Harris Park at night COMPLETELY DESERTED, "
        "the entire frame is a quiet eerie EMPTY STREET — no people, no other cars visible, no "
        "movement, the kind of stillness that follows a sudden silence after a door chimes shut, "
        "the centre of the frame shows the INDIAN GROCER SHOPFRONT with its small wooden door JUST "
        "SWINGING SLOWLY SHUT (the animation focal motion — the door slowly closing inch by inch back "
        "toward its frame, a small motion-arc line above it suggesting recent movement), "
        "warm yellow GROCER interior glow visible through the door's narrow gap as it nearly closes, "
        "a small SHOP BELL with a tiny stylised ding-sparkle still hanging in the air above the door "
        "(visual representation of the chime that just rang), "
        "in the FOREGROUND middle a SINGLE DRIED GUM LEAF tumbling slowly across the empty footpath "
        "carried by a faint breeze (another subtle animation element — slow drift across the asphalt), "
        "the player's WHITE EVO parked at the curb just past the grocer (driver door visible, empty "
        "inside, no Brenno), Rahul's grey Camry parked further down the street empty too, "
        "a single STREETLAMP overhead flickering — its warm orange light pulsing irregularly with a "
        "subtle electrical buzz (subtle flicker animation), casting a wavering pool on the asphalt, "
        "a small lone STYLISED RAT visible scurrying low along the gutter past a green wheelie bin "
        "(the only living thing in sight), "
        "BACKGROUND: the rest of the empty Wigram Street stretching out — Sweet Punjab restaurant in "
        "the distance with its lights now DIMMED low (closing up), sari fabric store window dark with "
        "metal security grille pulled down, distant 7-Eleven still glowing faintly red+green+orange, "
        "fairy lights strung across the street barely twinkling, "
        "deep navy night sky above with a few stars, a faint moon, "
        "the OVERWHELMING SILENCE of the moment visualised through emptiness — stylised SILENCE wave "
        "lines NOT present (negative space), the absence of all the usual life and noise, "
        "16-bit pixel art quiet-moment composition with HIGH DETAIL on the slowly-closing grocer door "
        "+ tumbling leaf + flickering streetlamp + scurrying rat, "
        "the 'street falls completely silent' eerie-empty aftermath atmosphere"
    ),
    # rahul_arrival_2 — "The driver's door swings open. A Sikh man in a
    # bright royal blue dastar hops out of the Camree grinning ear to
    # ear with a samosa in his hand." Rahul mid-exit from the Camry.
    "rahul_arrival_door": (
        "pixel art side-on view of Wigram Street Harris Park at night, "
        "Rahul's grey Toyota Camry 'Chamkili' parked at the curb, the DRIVER'S DOOR FULLY SWUNG OPEN "
        "outward toward camera (the focal element — the door open is dramatic), "
        "Rahul (Sikh Punjabi Australian man in his late twenties, BRIGHT ROYAL BLUE DASTAR turban, "
        "thick full BLACK BEARD, crisp light blue button-up shirt with sleeves rolled to the elbows, "
        "OPEN BLACK WAISTCOAT, dark jeans, brown leather sandals) caught MID-STEP HOPPING OUT of the "
        "open driver's door — ONE FOOT already planted on the asphalt, the OTHER LEG mid-air still "
        "swinging out from inside the car, his BODY leaning forward in the motion of standing up, "
        "ONE HAND on the open door frame as he pushes himself up, "
        "the OTHER HAND HOLDING UP a GOLDEN-BROWN TRIANGULAR ALOO SAMOSA at chin-height, a half-bite "
        "already taken out of one corner with crumbs falling, "
        "GRINNING EAR-TO-EAR — huge open-mouthed laugh showing teeth, eyes crinkled with mirth, "
        "small CARTOON LAUGH BUBBLE 'HEHE' floating beside his head, "
        "the Camry visible behind him — slammed coilover stance, black aftermarket wheels, the white "
        "'12-0 UNDEFEATED' tally marks scrawled on the rear quarter panel, faint heat shimmer rising "
        "from the bonnet (just been driven), interior dashboard glow visible inside through the open "
        "door — warm orange dash lights, hanging family photo + prayer beads from the rearview "
        "mirror visible, "
        "BACKGROUND: Wigram Street shopfronts in the middle ground — Sweet Punjab warm yellow neon, "
        "sari fabric store, 7-Eleven sign further down, fairy lights strung across the street "
        "overhead twinkling, "
        "warm orange streetlamp pool on the asphalt by Rahul's feet, deep navy night sky above, "
        "16-bit pixel art with HIGH DETAIL on Rahul mid-hop-out of the open driver's door + samosa "
        "in hand + grinning, the 'first sight of the legend himself' arrival moment"
    ),
    # khoa_explain — "SR20DET, big single Garrett, front mount, T56
    # conversion, hydraulic handbrake for the touges. She makes a smooth
    # 380 to the wheels."
    "khoa_s14_engine_bay": (
        "pixel art DETAILED 3/4 view down into the OPEN ENGINE BAY of Khoa's WHITE PEARL Nissan S14 "
        "Silvia at night in the Cabra Maccas carpark, the BONNET PROPPED OPEN above the frame, "
        "the engine bay DOMINATES the composition — a built NISSAN SR20DET INLINE FOUR-CYLINDER "
        "engine in a longitudinal rear-wheel-drive layout: BLACK CAST-IRON BLOCK with a polished "
        "aluminium VALVE COVER stamped 'NISSAN SR20DE' in raised letters, "
        "MASSIVE POLISHED BIG SINGLE GARRETT GT3071 TURBOCHARGER mounted on a stainless-steel TUBULAR "
        "EXHAUST MANIFOLD on the passenger side, the iconic snail-shape compressor housing chrome-"
        "polished + glinting (the focal element — animated heat shimmer rising from it), "
        "a BIG ALUMINIUM FRONT-MOUNT INTERCOOLER visible peeking up from behind the front bumper "
        "with thick black silicone hoses snaking to it, "
        "a BRIGHT POLISHED ALUMINIUM INTAKE PIPE running from the intercooler up to the throttle body, "
        "a chrome OIL-CATCH CAN with braided lines bolted to the strut tower, "
        "RED IGNITION COIL PACKS visible on top of the valve cover, "
        "a thick BLUE SILICONE TURBO INLET PIPE from the air filter cone, "
        "a heat-wrapped stainless DOWNPIPE running back from the turbo, "
        "the iconic NISSAN red-painted lower intake manifold visible underneath, "
        "GLOSSY VINYL DECAL on the inside of the bonnet reading 'SR20DET' in stylised JDM-style script "
        "+ '380WHP T56', "
        "below the engine peeking through gaps: the top of the T56 gearbox bell-housing visible "
        "(the focal upgrade Khoa mentioned), "
        "neat clean engine bay — no spaghetti wiring, polished + well-built JDM showroom-tier, "
        "a CABLE-OPERATED HYDRAULIC HANDBRAKE LEVER visible just sticking up over the passenger-side "
        "strut tower (vertical lever with rubber grip — the touge handbrake), "
        "warm WORKSHOP LAMP CLAMP-LIGHT hanging from the open bonnet casting bright white light on "
        "the engine, "
        "BACKGROUND: blurred Cabra Maccas drive-thru parking lot at night, faint golden arches glow "
        "in the distance, painted parking bay lines, deep navy night sky above, "
        "16-bit pixel art with HIGH DETAIL on the big Garrett turbo + intercooler + hydraulic e-brake "
        "+ SR20DET decal, the 'SR20DET big single Garrett T56' enthusiast moment, no human characters"
    ),
    # khoa_geton_g — "All good bro. Pop the boot — bag's in the brown
    # paper from the dosa place. Anyone asks, ya bought a samosa."
    "khoa_boot_brown_bag": (
        "pixel art DOWN-ANGLED 3/4 view looking INTO the OPEN BOOT of Khoa's WHITE PEARL Nissan S14 "
        "Silvia at night in Cabra Maccas carpark, the BOOT LID FULLY PROPPED OPEN above the frame, "
        "the BOOT INTERIOR visible — black carpet lining, a faint cargo light glowing in the corner, "
        "in the CENTRE of the boot a SMALL FOLDED BROWN PAPER GROCERY BAG sitting prominently — the "
        "bag has 'BILLU'S DOSA HOUSE' printed in faded red ink on the side (visible on the paper), "
        "the bag's top is CRUMPLED AND TWISTED CLOSED with a slight bulge of the green herb contents "
        "visible inside, "
        "ON TOP of the bag DECORATIVELY placed as a decoy: a SINGLE GOLDEN-BROWN TRIANGULAR SAMOSA "
        "in a small paper wrapper (the 'anyone asks, ya bought a samosa' cover story), a small "
        "smear of green mint chutney visible on the side of the wrapper, "
        "beside the bag in the boot: scattered EVERYDAY OBJECTS for cover — a microfibre car wash "
        "cloth, a small toolkit, a roll of paper towels, a yellow tow strap coiled in the corner, "
        "an empty Powerade bottle, "
        "the boot carpet has faint dust + small cigarette ash spots showing it gets regular use, "
        "small subtle UPWARD MOTION-LINE ARROWS visible on the boot lid above the frame (showing the "
        "boot was just popped open — the animation focal element will be subtle bag-paper-rustle), "
        "BACKGROUND: blurred Cabra Maccas drive-thru carpark visible behind the boot — Maccas golden "
        "arches glowing yellow in the far distance, fluorescent ceiling-lamp pool spilling cool "
        "white onto the asphalt beside the car, painted parking bay lines, "
        "deep navy night sky above the boot lid, "
        "16-bit pixel art with HIGH DETAIL on the brown paper bag + the decoy samosa + Billu's Dosa "
        "House print, the 'cover story handoff' Cabra plug moment, no human characters"
    ),
    # khoa_humble — "Tell me about it bro. HWP's been doin' this loop
    # every Saturday. We just gotta read the spotlight - once ya see the
    # rhythm, easy. You did good."
    "khoa_humble_spotlight": (
        "pixel art MEDIUM SHOT of Khoa leaning casually against the side of his WHITE PEARL Nissan "
        "S14 Silvia in the Cabra Maccas carpark at night, "
        "Khoa (Vietnamese Australian man in his late twenties, crisp light blue button-up shirt "
        "with sleeves rolled to the elbows, well-groomed black hair slightly mussed, polite gentle "
        "smile, thin gold chain at the collar) leaning his shoulder back against the S14's rear "
        "quarter panel with arms crossed in a relaxed COMPOSED 'all good' stance, "
        "head tilted slightly with a small wise smile + one INDEX FINGER raised pointing up toward "
        "his temple — the universal 'read it / use your head' gesture, "
        "small stylised CLOCK FACE ICON floating in the upper-right corner of the frame showing the "
        "spotlight rhythm — clock-hand sweep with a glowing arc indicating the cop spotlight rotation, "
        "a small dotted ARC LINE diagram floating in the air beside Khoa showing the cop spotlight's "
        "sweep pattern as a curved trajectory (visual storytelling for 'read the rhythm'), "
        "a HIGHWAY PATROL POLICE PADDY WAGON visible in the FAR BACKGROUND of the carpark with its "
        "spotlight beam sweeping AWAY from the camera in a wide arc, no aggression — just routine "
        "patrol pattern, the spotlight beam shown as a soft cone of light catching dust motes, "
        "the S14 Silvia parked side-on beside Khoa with slammed coilover stance, deep-dish gunmetal "
        "wheels, "
        "BACKGROUND: Cabra Maccas drive-thru with golden ARCHES glowing yellow in the middle distance, "
        "fluorescent ceiling lamps casting cool white pools on the asphalt, painted parking bay lines, "
        "scattered abandoned shopping trolleys further back, deep navy night sky above, "
        "the warm CALM 'we got this' moment after a clean deal — Cabra plug at his most zen, "
        "16-bit pixel art with HIGH DETAIL on Khoa's relaxed leaning pose + finger-to-temple gesture "
        "+ floating clock/sweep diagram + distant patrol spotlight, "
        "the 'just gotta read the spotlight rhythm' wisdom moment"
    ),
    # khoa_intro:start — "John St Cabramatta, behind the markets. Red
    # lanterns and fairy lights hang between the rooftops. A young Viet
    # Australian guy in a crisp light-blue shirt is leaning on a pearl
    # white S14 Silvio, vaping and scrolling his phone."
    "cabra_john_st_arrival": (
        "pixel art WIDE establishing shot of John Street Cabramatta at night, behind the Vietnamese "
        "markets, "
        "RED CHINESE / VIETNAMESE PAPER LANTERNS hanging strung between the rooftops above the street "
        "in long zigzag rows, glowing warm red+orange (the focal animation element — the lanterns "
        "sway gently in the breeze), interwoven with strings of small WHITE FAIRY LIGHTS twinkling, "
        "in the centre-foreground KHOA leaning casually against the side of his PEARL WHITE Nissan "
        "S14 Silvia parked at the curb — Khoa is a Vietnamese Australian man in his late twenties, "
        "crisp LIGHT-BLUE BUTTON-UP SHIRT with sleeves rolled to the elbows, well-groomed black hair, "
        "thin gold chain at the collar, dark slim-fit jeans, polished leather loafers, "
        "leaning his lower back against the S14's rear quarter panel with one foot up against the "
        "tyre, both arms relaxed, "
        "ONE HAND holding up a small SLEEK BLACK VAPE PEN to his mouth — a small WISP OF WHITE "
        "VAPOUR CLOUD curling up from his mouth into the air (the secondary animation element — "
        "the vape cloud drifts upward and dissipates), "
        "the OTHER HAND holding his SMARTPHONE in his palm at chest height, eyes lowered to the "
        "screen, faint blue glow from the phone screen lighting his face from below, "
        "the S14 Silvia parked side-on, slammed coilover stance, deep-dish gunmetal aftermarket "
        "wheels, smooth pearl white pearlescent paint catching the lantern glow, "
        "BACKGROUND: the back lane behind the Cabra Vietnamese markets — narrow lane with brick "
        "shopfront backs, a few rolled-down roller doors with stencilled Vietnamese shop names, "
        "scattered milk crates + plastic chairs, a faint glimpse of the Cabra market arches in the "
        "far background with their distinctive Asian-architecture roofline, "
        "a few small Vietnamese signs on shopfronts in red+gold lettering, "
        "warm RED + AMBER lighting from the hanging lanterns mixing with cool blue night sky shadow, "
        "deep navy night sky visible above between the strings of lights, "
        "16-bit pixel art establishing wide shot with HIGH DETAIL on the red lanterns + Khoa vaping "
        "+ pearl white S14, the 'Cabra plug at his office' introduction moment, "
        "Vietnamese Cabramatta after-hours back-lane atmosphere"
    ),
    # khoa_food — "That's what I'm talkin' about! Tái nạm, big bowl,
    # extra chilli, with the bánh quẩy for dippin'. We'll grab one after
    # I smoke ya, hahaha. Mum's special is the brisket."
    "khoa_pho_mum_special": (
        "pixel art TOP-DOWN OVERHEAD view of a large STEAMING BOWL OF VIETNAMESE PHO sitting on a "
        "tiled Cabramatta restaurant table at night, "
        "the centrepiece is a HUGE WHITE PORCELAIN BOWL FILLED with rich CARAMEL-BROWN PHO BROTH, "
        "thin slices of pink-grey RARE BRISKET + pale TENDON pieces floating on top (the tái nạm), "
        "thin RICE NOODLES tangled in the bottom visible through the clear broth, scattered chopped "
        "spring onion + coriander leaves floating on the surface, "
        "thin curls of WHITE STEAM rising up dramatically from the bowl (the focal animation "
        "element — the steam billows and curls upward), "
        "beside the pho bowl on the table: a small plate of FRESH HERB GARNISH (Vietnamese mint, "
        "Thai basil, bean sprouts, lime wedges, sliced red bird's-eye chilli, sliced jalapeño rings), "
        "a small BOWL OF HOISIN SAUCE in dark brown + a BOWL OF SRIRACHA in bright red, both with "
        "small spoons, "
        "a CRISPY GOLDEN-BROWN STICK OF BÁNH QUẨY (Vietnamese fried Chinese cruller / youtiao) on a "
        "small paper-lined plate beside the pho — the dough stick is roughly 20cm long with a "
        "twisted texture, ready for dipping, "
        "a pair of black wooden CHOPSTICKS + a Vietnamese spoon (the deep wide-bowled curved spoon) "
        "resting beside the bowl, "
        "small bottle of FISH SAUCE + a glass jar of pickled chillies in the corner, "
        "the table surface is a faded pink-and-cream tiled restaurant table-top with subtle wear, "
        "small EXTRA RED CHILLI FLAKES sprinkled boldly on top of the broth (Khoa specified 'extra chilli'), "
        "in the corner of the frame a small chalkboard sign visible reading 'MUM'S SPECIAL — BRISKET' "
        "in handwritten chalk, "
        "warm overhead amber RESTAURANT LAMP glow casting soft shadows around the bowl, "
        "16-bit pixel art top-down food composition with HIGH DETAIL on the pho bowl + brisket + "
        "bánh quẩy + steam, the 'Tái nạm with the bánh quẩy' Cabra pho moment, no human characters"
    ),
    # mitcho_intro_self + mitcho_intro_2 — "Big Brenno onerske adlay...
    # I run with the Mexican Hoon Cartel..." Brenno SMACK TALKING /
    # bullshitting hard, full BS bravado mode.
    "brenno_bullshitting": (
        "pixel art MEDIUM SHOT REALISTIC view of Brenno in the Blacktown Maccas carpark at dusk, "
        "REALISTIC NPC PROPORTIONS matching the established Moey/Khoa/Rahul portrait fidelity — "
        "NOT cartoon, NOT anime, NOT chibi — proper proportioned realistic human body, "
        "Brenno is the skinny pale ginger Australian eshay teenager — short cropped ginger orange "
        "hair under a NAVY BLUE NIKE TN CAP pulled low (yellow swoosh, sticker still on flat brim), "
        "freckles across his nose + cheeks, faint patchy ginger stubble, long narrow face, sharp "
        "pointed nose, light blue eyes, "
        "Brenno caught MID-SMACK-TALK in full bullshitting bravado — body angled toward camera, "
        "chest PUFFED OUT proudly, head tilted back with a COCKY GRIN showing teeth, eyebrows raised, "
        "ONE HAND pointing at his own chest with thumb (the universal 'me, this guy, real one' "
        "boastful gesture), the OTHER HAND making an EMPHATIC THREE-FINGER COUNT pointing up + out "
        "as he lists his bullshit achievements (the storytelling hand), elbows out, "
        "mouth open mid-monologue showing teeth, "
        "wearing a baggy MUSTARD YELLOW crewneck JUMPER, navy tracksuit pants tucked into white tube "
        "socks, WHITE RUBBER SLIDES on his feet, "
        "small stylised CARTOON DETAIL bubbles floating around his head suggesting BS bravado — a "
        "tiny 🤥 nose-growing trail visualised as a faint stretched line off his nose tip, a small "
        "cartoon 'BS' speech bubble in the upper-right corner with a wavy edge suggesting tall tale, "
        "small motion-line bursts around his pointing hand emphasising the smack-talking energy, "
        "behind Brenno parked the DEEP BLUE BMW E36 sedan visible to one side, BONNET STILL PROPPED "
        "OPEN with a faint wisp of white engine steam (consistent with the intro beemer scene), "
        "the E36 is faded blue paint, scuffs, dented quarter, slammed coilovers, black wheels, "
        "BACKGROUND: NSW Maccas drive-thru restaurant in the middle ground — only the LARGE YELLOW "
        "DOUBLE-ARCH 'M' LOGO silhouette glowing on a tall metal pole (NO readable text or letters "
        "anywhere on signage — only the iconic arches silhouette), low-slung brick restaurant facade "
        "with lit dining-room windows visible (NO text), to one side a Lebanese kebab shop with a "
        "stylised kebab-on-spit silhouette in magenta neon (NO text), "
        "DRAMATIC dusk sky — deep red and burnt orange gradient on the horizon transitioning to "
        "deep navy at the top of the frame, a few early stars, distant gum tree silhouettes, "
        "warm amber streetlamps just turning on with soft pools on the asphalt, painted parking bay "
        "lines, "
        "16-bit pixel art with HIGH DETAIL on Brenno's smack-talking realistic pose + chest-puff + "
        "pointing-at-self gesture + BS speech bubble + steaming Beemer behind, "
        "REALISTIC PROPORTIONS — Brenno's body and face proportioned like the Moey/Khoa NPC tier, "
        "NOT chibi / NOT anime, the iconic 'I run with the Mexican Hoon Cartel I SWEAR AY' tall-tale "
        "moment, Western Sydney late-arvo bullshitting energy, NO TEXT/LETTERS on any signage"
    ),
    # engine_diag_wires — "HAHA yeah the wires are FUCKED. But that's
    # just how I left em adlay, they been like that for ages."
    "brenno_wires_proud": (
        "pixel art DETAILED CLOSE-UP view down into Brenno's E36 engine bay at night, "
        "REALISTIC SEMI-PHOTOREAL pixel art style matching the established Moey/Khoa NPC fidelity, "
        "the engine bay dominates the centre of the frame — focused on a MESSY TANGLED nest of "
        "ENGINE WIRING (the focal element), exposed copper-coloured wires drooping out of their "
        "loom in a chaotic cascade, BLACK ELECTRICAL TAPE wrapped messily around the wire bundle in "
        "amateur repair-jobs, several wires reconnected with WHITE PLASTIC SCOTCH-LOK CONNECTORS, "
        "two of the wire ends BARE COPPER STRANDS twisted together without insulation, a dangling "
        "ZIP-TIE BUNDLE holding the loom up off the manifold, "
        "the WIRING HAS A CLEAR ELECTRICAL ARC SPARK animating between two exposed copper points "
        "(small bright BLUE-WHITE ELECTRICAL SPARK with stylised lightning-bolt rays — the focal "
        "animation element pulses on/off intermittently), thin wisps of grey smoke rising up from "
        "the spark, "
        "in the FOREGROUND a HAND visible at the edge of frame — Brenno's pale ginger-freckled hand "
        "with chipped fingernails reaching IN to the engine bay POINTING with one finger at the "
        "tangled wires, the thumb-up sign visible on his fist (proud 'see this is fine' gesture), "
        "the cuff of his MUSTARD YELLOW jumper visible at the wrist, "
        "in the upper-right corner a stylised cartoon SPEECH BUBBLE 'LIFETIME WARRANTY' with a "
        "wavy edge suggesting BS, "
        "the engine bay around the wiring is faded BMW E36 BLUE PAINT with grime + oil streaks, "
        "polished aluminium intake manifold + valve cover visible in the periphery, "
        "single workshop droplight clamped to the open bonnet casting bright hard contrast lighting, "
        "BACKGROUND: blurred dark Blacktown Maccas carpark at night with faint amber lamp glow, "
        "deep navy night sky barely visible at the top edge, "
        "16-bit pixel art with HIGH DETAIL on the messy wire-nest + electrical spark + Brenno's "
        "pointing hand, REALISTIC pixel art style, NOT chibi, NOT anime, "
        "the 'wires been like that for ages, not it bra' moment of dodgy backyard mechanic pride"
    ),
    # engine_diag_screws — "Tek screws are how all my plastics live adlay.
    # Lifetime warranty. Not it bra, keep lookin'."
    "brenno_tek_screws": (
        "pixel art REALISTIC close-up view of a BLACK PLASTIC ENGINE COVER held together with a "
        "cluster of OBVIOUS METAL HEX-HEAD TEK SCREWS, photographed from above at night under harsh "
        "workshop lighting, "
        "the COMPOSITION is simple and clear: a flat black plastic engine cover surface FILLS the "
        "centre two thirds of the frame, the surface has VISIBLE JAGGED CRACKS running diagonally "
        "across it like spider-web fractures in the plastic, "
        "DRIVEN THROUGH the cracks: SEVEN BRIGHT SILVER ZINC-PLATED HEX-HEAD TEK SCREWS clearly "
        "visible from above — each screw shown as a small SILVER HEXAGONAL HEAD with a thin SHADOW "
        "ring cast on the plastic around it, the metal threading just barely visible biting into "
        "the plastic, the screws are GLINTING bright against the matte black plastic, "
        "the screws are clustered in arrangement around the cracks holding pieces of broken plastic "
        "together — clearly an amateur ghetto-fix job, not a factory fix, "
        "ONE TEK SCREW positioned at the upper-right with a small ELECTRIC IMPACT DRIVER BIT held "
        "above it about to drive it in (the bit is a small silver hex driver attachment visible "
        "from above), faint white DRILL DUST motes kicking up around the screw head (the animation "
        "focal element — the screw rotates and dust particles puff up), "
        "scattered around the workspace on the plastic surface: a few LOOSE EXTRA TEK SCREWS lying "
        "to the side ready to be used, a small dropped HEX SOCKET, a curl of PLASTIC SHAVINGS, "
        "the engine cover plastic is matte black with subtle grey scratches and grime, "
        "the FRAMING is straightforward TOP-DOWN looking straight at the plastic surface — the "
        "cracks + cluster of silver screws is the unmistakable focal element, no ambiguous shapes, "
        "warm WORKSHOP DROPLIGHT casting bright white-yellow light from the upper-left edge causing "
        "the silver screw heads to GLINT with small bright highlights, "
        "BACKGROUND: deep dark engine bay shadows around the edges of the plastic cover suggesting "
        "the surrounding engine bay components, deep navy night sky barely visible at the very top "
        "edge through the open bonnet, "
        "16-bit pixel art SIMPLE CLEAR composition with HIGH DETAIL on the SEVEN bright silver hex "
        "screws driven into the cracked black plastic + the impact driver bit + dust particles, "
        "REALISTIC pixel art NOT chibi, the 'tek screws hold all my plastics' ghetto-mechanic "
        "pride moment, NO human characters in frame — only the plastic surface + screws + tool bit"
    ),
    # engine_diag_bundy — "Oi that's a half full one lad don't touch it.
    # Not the problem bra, but cheers for spotting."
    "brenno_bundy_bottle": (
        "pixel art DETAILED CLOSE-UP view of a HALF-FULL BUNDABERG RUM BOTTLE sitting WEDGED inside "
        "the E36 engine bay at night between the strut tower and the air-box, "
        "REALISTIC pixel art style matching Moey/Khoa NPC fidelity, "
        "the focal element is the AMBER BUNDABERG RUM BOTTLE — iconic stout square glass bottle with "
        "the deep amber-brown rum filling the bottom half, the iconic stylised POLAR BEAR mascot "
        "shape visible on the front label (NO readable text — just the recognisable polar bear + "
        "yellow + red label graphic with a banner shape), the bottle cap off / lying beside it, "
        "the BUNDY BOTTLE sits WEDGED between two engine components — clearly NOT supposed to be "
        "there but stable enough to ride, sticky amber residue dripping down the side of the bottle, "
        "small RUM DRIPS visible falling slowly from the bottle's mouth lip (the animation focal "
        "element — slow drips into the engine bay below), "
        "in the foreground TWO HANDS visible at the edge — Brenno's PALE GINGER-FRECKLED HANDS held "
        "up DEFENSIVELY in a 'no no no don't touch' gesture, palms out, mustard-yellow jumper cuffs "
        "visible at the wrists, "
        "a small stylised CARTOON 'NO TOUCH' EXCLAMATION ICON floating in the upper-right corner — "
        "a yellow triangle with a small graphic of a HAND with a red line through it (NO text — only "
        "shape recognition), "
        "the engine bay around is faded BMW E36 BLUE PAINT with grime + oil streaks, polished "
        "aluminium intake visible in the periphery, "
        "harsh workshop droplight casting bright contrast lighting on the rum bottle, "
        "BACKGROUND: blurred dark Maccas carpark at night, deep navy night sky at top edge, "
        "16-bit pixel art with HIGH DETAIL on the wedged Bundy rum bottle + slow drip + defensive "
        "hands, REALISTIC pixel art NOT chibi, the 'don't touch the bundy bra' protective moment, "
        "no full faces visible"
    ),
    # engine_diag_shit — "Hahaha fair call bra. It IS all shit. But the
    # actual culprit is the coil pack — see that cracked one on top of
    # cylinder four? Hangin' on by a prayer. Engine's runnin' on five
    # out of six."
    "brenno_points_coil": (
        "pixel art WIDE OVERHEAD view down into Brenno's E36 engine bay at night, the open bonnet "
        "framing the top of the shot, "
        "REALISTIC pixel art style matching Moey/Khoa NPC fidelity, "
        "the focal element is the ROW OF SIX BLACK PLASTIC IGNITION COIL PACKS standing upright in "
        "a NEAT VERTICAL ROW along the polished aluminium VALVE COVER of the BMW M52 inline-six "
        "engine — 6 rectangular black plastic coils with rubber boot connectors on top, "
        "the FOURTH COIL PACK FROM THE FRONT (cylinder 4 position) IS OBVIOUSLY THE BROKEN ONE — "
        "the plastic casing CRACKED CLEAN IN HALF down the middle with a jagged dark fissure, inner "
        "copper wire windings visible, oil grime seeping out the crack, "
        "a PULSING GLOWING RED CIRCLE / SPOTLIGHT RING animating around just the broken coil pack to "
        "highlight it as the culprit (the focal animation element — the red ring pulses bigger + "
        "smaller to draw the eye), "
        "small CARTOON LABEL FLOATING above the row showing '5/6' in stylised yellow digital text "
        "(engine running on five of six cylinders), with a small arrow pointing at the cracked coil, "
        "in the foreground a HAND visible at the edge of frame — Brenno's pale ginger-freckled hand "
        "reaching in pointing one INDEX FINGER directly at the broken coil pack, mustard-yellow "
        "jumper cuff visible at the wrist, his hand framed by the surrounding intact coil packs, "
        "polished aluminium valve cover with raised 'M52' badging beneath the coils, polished intake "
        "manifold visible in the periphery, "
        "the engine bay around is faded BMW E36 BLUE paint with grime, oil streaks, dust, "
        "harsh workshop droplight casting bright contrast lighting on the engine bay, "
        "BACKGROUND: blurred dark Maccas carpark, deep navy night sky at top edge, "
        "16-bit pixel art with HIGH DETAIL on the row of six coil packs + the pulsing red highlight "
        "on the broken one + Brenno's pointing finger + the '5/6' label, REALISTIC pixel art NOT "
        "chibi, the 'actual culprit is the coil pack' diagnostic reveal moment"
    ),
    # player_diag_response — "Hmmm M52 coil pack. Around a hundred bucks
    # from Bursons, eighty for aftermarket. Let me guess ... You don't
    # have eighty, do you."
    "player_burson_price": (
        "pixel art CLOSE-UP view of a SMARTPHONE held up in landscape orientation in the foreground, "
        "REALISTIC pixel art style, the phone screen DOMINATES the centre of the frame, "
        "the PHONE SCREEN displays a stylised AUSTRALIAN AUTO-PARTS WEBSITE / Burson's mobile app "
        "page for the BMW M52 IGNITION COIL PACK part — a clean white-and-orange mobile app layout, "
        "at the top a small ORANGE LOGO BANNER (just the shape, no readable text), "
        "in the centre of the screen a LARGE PRODUCT PHOTO TILE showing the iconic rectangular BLACK "
        "PLASTIC M52 COIL PACK on a clean white background (the same coil pack from the engine), "
        "below the product photo TWO PRICE TAGS displayed prominently: "
        "(1) a 'OEM GENUINE' badge with price '$100' in big bold black text (NO other text — just "
        "$100 as the readable element), "
        "(2) below it an 'AFTERMARKET' badge with price '$80' in big bold black text, "
        "small ADD-TO-CART button at the bottom in orange (just shape recognition), "
        "small grey 'IN STOCK' status indicator with a green dot, "
        "the player's hands visible at the edges holding the phone in landscape grip — tan complexion "
        "male hands, simple black hoodie sleeves visible at the wrists, thumbs hovering near the "
        "screen, "
        "the phone screen casts a cool BLUE-WHITE GLOW onto the player's hands + dashboard, "
        "BACKGROUND: blurred peripheral view of the E36 engine bay at night just visible behind the "
        "phone — out-of-focus glimpse of the row of coil packs in the engine bay below, faint "
        "Blacktown Maccas carpark glow further behind, deep navy night sky at the top edge, "
        "the player's slim silver dashboard visible at the bottom showing the calm focused "
        "researcher-mode lighting, "
        "16-bit pixel art with HIGH DETAIL on the phone screen showing the $100 / $80 price tags + "
        "the player's hands holding it + the blurred engine bay behind, REALISTIC pixel art NOT "
        "chibi, the 'pricing it up on the app' problem-solving moment, no face visible — just hands "
        "+ phone + price tags + blurred engine behind"
    ),
    # mitcho_real_ask — "Nah bra. Card declined three times this week.
    # Fukin cenno ain't come in yet, I only got enough for a stick AND
    # Mum needs curry powder for dinner — like RIGHT now."
    "brenno_card_declined": (
        "pixel art REALISTIC medium close-up view of Brenno standing on the Blacktown Maccas "
        "carpark footpath at dusk, REALISTIC pixel art style matching Moey/Khoa NPC fidelity — "
        "NOT cartoon, NOT anime, NOT chibi — proper proportioned human body, "
        "Brenno is the skinny pale ginger Australian eshay teenager — short cropped ginger orange "
        "hair under a NAVY BLUE NIKE TN CAP pulled low, freckles across nose + cheeks, faint "
        "patchy ginger stubble, long narrow face, "
        "Brenno standing front-on to camera with a DEJECTED RESIGNED look — shoulders slumped, "
        "head tilted slightly down, embarrassed sheepish expression, mouth open mid-confession, "
        "wearing the MUSTARD YELLOW crewneck JUMPER, navy tracksuit pants tucked into white tube "
        "socks, white slides, "
        "ONE HAND holding up a SMARTPHONE in portrait orientation — the PHONE SCREEN fills the "
        "centre of the frame showing a stylised mobile banking app: a clear BIG RED 'X' icon and "
        "the word 'DECLINED' in bold red text (only readable text), an amount '$5.00' below, a "
        "list of THREE previous declined transactions stacked below also marked with small red Xs, "
        "below the declined screen a small POP-UP NOTIFICATION BUBBLE showing a text-message "
        "preview from 'MUM' with tiny chilli-pepper + onion + clock emoji icons (NO readable "
        "words — just the symbolic emoji suggesting cooking urgency), "
        "the OTHER HAND holding up a SINGLE BLUE AUSTRALIAN $5 NOTE pinched between thumb and "
        "forefinger (the 'stick' money), his back pocket lining visibly pulled inside-out empty, "
        "small stylised SAD-FACE DROP icons / cartoon TEAR dots floating around the $5 note "
        "emphasising the brokeness, "
        "BACKGROUND: the cooked DEEP BLUE BMW E36 visible to the right with the BONNET still "
        "propped open + faint white engine steam wisp, blurred Blacktown Maccas drive-thru in the "
        "middle distance — only the iconic GOLDEN-M ARCH SILHOUETTE on a tall pole (NO text/"
        "letters), deep red-orange dusk sky transitioning up to navy, faint stars, amber "
        "streetlamp pools, painted parking bay lines, "
        "16-bit pixel art with HIGH DETAIL on the phone DECLINED screen + the $5 note + Brenno's "
        "dejected pose, REALISTIC proportions NOT chibi, the 'broke + Mum needs curry powder' "
        "confessional moment, NO TEXT/LETTERS on background signage"
    ),
    # player_offer — "Alright. Hop in. ... Coles is closer though, that'd
    # do, yeah?" YOU offers the ride.
    "player_offer_hop_in": (
        "pixel art REALISTIC first-person POV looking OUT through the open driver's-side window "
        "of the player's WHITE EVO IX sedan toward BRENNO standing on the footpath beside the car, "
        "REALISTIC pixel art style matching Moey/Khoa NPC fidelity, "
        "FOREGROUND lower portion of frame shows the inside of the player's Evo — the dark "
        "interior of the open driver's-side window frame, a glimpse of the BLACK STEERING WHEEL "
        "and the player's hand resting on it visible at the bottom edge (just hand + cuff of "
        "black hoodie sleeve, no face), the side-view mirror visible at the lower right edge, "
        "warm amber dashboard glow on the right, "
        "MIDDLE GROUND through the open window — BRENNO standing on the footpath about three "
        "metres from the car, full body visible (realistic adult proportions), ginger hair under "
        "TN cap, mustard yellow jumper, navy trackies tucked into white socks, white slides, "
        "head turned toward the player's window, body leaning slightly forward in anticipation, "
        "both hands held out palms-up in a 'really? for real?' grateful gesture, faint hopeful "
        "smile, "
        "the PASSENGER DOOR of the Evo (closer to camera, on the right side of frame) is SWUNG "
        "OPEN OUTWARD — the door is the focal element of the composition with a small stylised "
        "motion-arc above suggesting it just opened, "
        "small stylised CARTOON UP-ARROW / 'HOP IN' indicator icon floating beside the open "
        "passenger door, "
        "the Evo's iconic big REAR WING just visible at the right edge of frame, slammed coilover "
        "stance, deep-dish silver wheels, "
        "BACKGROUND: behind Brenno the cooked DEEP BLUE BMW E36 parked nearby with the bonnet "
        "propped open + faint white engine steam, blurred Blacktown Maccas drive-thru in the far "
        "background — only the GOLDEN-M ARCH SILHOUETTE on a tall pole (NO text/letters), dusk "
        "red-orange sky transitioning to navy at top, amber streetlamps just coming on, painted "
        "parking bay lines on the asphalt, "
        "16-bit pixel art with HIGH DETAIL on the OPEN passenger door + Brenno's hopeful body "
        "language + the player's hand on wheel, REALISTIC proportions not chibi, "
        "the 'Alright. Hop in.' generous moment, Western Sydney late-arvo good-samaritan vibe"
    ),
    # mitcho_curry_uber — "She's already chopped the onions bra. Onions
    # don't wait. And the boys at Westfield are busy. You're me last
    # hope adlay."
    "brenno_onions_dont_wait": (
        "pixel art REALISTIC composition: the LEFT TWO-THIRDS of the frame shows Brenno standing "
        "on the Blacktown Maccas footpath at dusk in DESPERATE PLEADING pose, the RIGHT ONE-THIRD "
        "shows a stylised THOUGHT-BUBBLE cloud floating beside his head with an inset KITCHEN "
        "scene, "
        "REALISTIC pixel art style matching Moey/Khoa NPC fidelity throughout — NOT chibi, NOT "
        "anime, "
        "Brenno in the foreground left (skinny pale ginger, NAVY NIKE TN CAP pulled low, MUSTARD "
        "YELLOW JUMPER, navy trackies + white socks + slides, freckles + ginger stubble) standing "
        "with BOTH HANDS CLASPED TOGETHER under his chin in PRAYING/BEGGING pose, eyes wide in "
        "desperate pleading, eyebrows raised high, mouth open mid-plea, body slightly bent forward "
        "at the waist, "
        "the THOUGHT BUBBLE on the right shows a top-down inset of a HOME KITCHEN COUNTER scene — "
        "a wooden cutting board with a MOUNTAIN OF FRESHLY CHOPPED WHITE ONIONS in a glistening "
        "pile, a kitchen knife resting on the board, visible cartoon TEAR DROPS hovering above "
        "the chopping zone (the focal animation element), a STAINLESS-STEEL POT on a stove element "
        "behind the board with red FLICKERING FLAMES underneath, MUM's hands (middle-aged Sikh "
        "Punjabi Australian woman's hands with bangles at the wrist) holding the knife mid-chop, "
        "an ANGRY STYLISED RED EMOJI icon floating above the cooking scene suggesting 'IMPATIENT', "
        "a faint dotted line connecting the thought-bubble back to Brenno's head, "
        "BACKGROUND behind Brenno: the cooked DEEP BLUE BMW E36 to the right with bonnet propped "
        "open + faint engine steam, blurred Blacktown Maccas drive-thru — only the GOLDEN-M ARCH "
        "SILHOUETTE on a tall pole (NO text/letters), dusk red-orange sky to navy gradient, amber "
        "streetlamps, painted parking bay lines, "
        "16-bit pixel art with HIGH DETAIL on Brenno's pleading hands + the thought-bubble kitchen "
        "scene with chopped onions + animated stove flames + tear drops, REALISTIC proportions not "
        "chibi, the 'Mum's already cooking, you're me last hope' desperate moment, NO TEXT/LETTERS"
    ),
    # player_harris_commit — "Alright. Harris Park, curry powder, then
    # back here to sort your engine. Get in." YOU commits to the trip.
    "player_route_commit": (
        "pixel art REALISTIC interior view from the BACK SEAT of the player's WHITE EVO IX looking "
        "FORWARD toward the dashboard, the player visible from BEHIND in the driver's seat, "
        "REALISTIC pixel art style matching Moey/Khoa NPC fidelity, "
        "the PLAYER visible from behind in the driver's seat — short cropped DARK BROWN hair, "
        "BLACK ZIP-UP HOODIE, both hands on the BLACK aftermarket STEERING WHEEL in 9-and-3 grip, "
        "head tilted slightly forward focused on the task, "
        "the EVO DASHBOARD is the FOCAL ELEMENT — the centre of the frame shows the dashboard "
        "phone-mount holding the player's smartphone in landscape, the phone screen displays a "
        "stylised GPS NAVIGATION APP view — a bold GLOWING ORANGE DASHED ROUTE LINE drawn on a "
        "small dark map, the route starting at a circular 'A' pin in the bottom-right corner of "
        "the map labelled 'BLACKTOWN' (the only readable text), winding north-west to a 'B' pin "
        "labelled 'HARRIS PARK' in the upper-left of the small map, a small CURRY-POWDER icon "
        "graphic at the B pin (just an icon shape — orange-red spice mound silhouette, NO words), "
        "an estimated time '14 MIN' floating above the route in stylised yellow digital text, "
        "below the GPS screen the Evo's iconic dashboard cluster — twin round analogue gauges "
        "(speedo + tacho) with warm orange-amber needle glow, fuel + temp gauges visible, "
        "a small dangling charm hanging off the rear-view mirror at the top edge of frame, "
        "through the WINDSCREEN faintly visible beyond the dashboard — the Blacktown Maccas car-"
        "park at dusk, the parked DEEP BLUE BMW E36 directly ahead with bonnet still propped open "
        "+ faint engine steam, a glimpse of the GOLDEN-M ARCH SILHOUETTE on a tall pole far in "
        "the middle distance (NO text/letters), dusk red-orange to navy sky gradient, "
        "16-bit pixel art with HIGH DETAIL on the GPS route display + Evo dashboard + player's "
        "hands on the wheel, REALISTIC proportions not chibi, the 'Harris Park, curry powder, "
        "then back here' decisive commitment moment, NO TEXT/LETTERS on background signage"
    ),
    # mitcho_curry_yes — "YEW LEGEND adlay! ESHAYS! Wigram St, full thing.
    # Mum will love ya. Let's roll bra." Brenno mid-celebration.
    "brenno_yew_legend": (
        "pixel art REALISTIC medium-shot of Brenno in Blacktown Maccas carpark at dusk caught "
        "MID-LEAP straight up in pure ESHAY CELEBRATION, both feet OFF THE GROUND in mid-jump, "
        "REALISTIC pixel art style matching Moey/Khoa NPC fidelity — NOT chibi, NOT anime, "
        "Brenno (skinny pale ginger eshay teenager, NAVY BLUE NIKE TN CAP pulled low with yellow "
        "swoosh, MUSTARD YELLOW JUMPER, navy tracksuit pants, white tube socks, white rubber "
        "slides) caught at the APEX OF A JUMP — body extended fully upright with both arms thrown "
        "UP overhead in a victorious V-shape, fists clenched and raised, head tilted back with a "
        "huge open-mouthed shouting GRIN, eyes scrunched in joy, "
        "BOTH FEET visibly off the asphalt with JUMP-MOTION DUST KICKING UP from where his slides "
        "just left the ground (the focal animation element — the dust puff blooms outward), "
        "small stylised LIGHTNING-BOLT STARBURST RAYS radiating around his body suggesting "
        "EXPLOSIVE ESHAY ENERGY, "
        "stylised CARTOON SPEECH BUBBLE 'YEW!' visible beside his head with a wavy excited edge "
        "(the only stylised text element — 'YEW!' shape rendered fine), "
        "in the FOREGROUND just beside Brenno the player's WHITE EVO IX sedan parked with the "
        "PASSENGER DOOR SWUNG OPEN ready for him to hop in, the door swung outward toward Brenno "
        "like an invitation, faint orange dashboard glow visible inside through the open door, "
        "BACKGROUND: the cooked DEEP BLUE BMW E36 further back with bonnet still propped open + "
        "faint engine steam (about to be left behind for the curry run), blurred Blacktown Maccas "
        "drive-thru in the middle distance — only the GOLDEN-M ARCH SILHOUETTE on a tall pole (NO "
        "text/letters), dusk red-orange sky transitioning to navy at the top, faint stars, amber "
        "streetlamps just coming on with soft pools on the asphalt, painted parking bay lines, "
        "16-bit pixel art with HIGH DETAIL on Brenno's mid-air victory jump + dust-puff + "
        "starburst rays + YEW speech bubble + open passenger door of the Evo, REALISTIC "
        "proportions not chibi, the explosive 'YEW LEGEND ESHAYS' celebration moment"
    ),
    # westfield_detour:brenno_off: "Brenno bounces across the carpark
    # with the paper bag from Khoa in one hand and Brett's double perc
    # in the other, both held up like trophies. The boys whoop."
    "westfield_boys": (
        "pixel art side-on view of Westfield Mt Druitt bottom carpark at midnight, "
        "in the foreground the skinny eshay teenager Brenno (NAVY BLUE NIKE TN CAP, "
        "MUSTARD YELLOW JUMPER, black trackies) is BOUNCING across the empty asphalt carpark mid-stride "
        "TOWARD a loose circle of four other eshay lads standing near the trolley bay, "
        "all the lads wear navy TN caps + polo shirts + tracksuit pants, some holding cans of Bundaberg rum, "
        "one passing around a glass bong, some laughing with mouths wide open, "
        "Brenno is holding the brown paper bag from Khoa in one hand and a tall GLASS DOUBLE PERC BONG "
        "in the other, both raised up like trophies victorious, "
        "closed Westfield Mt Druitt mall facade silhouetted in the background with the WESTFIELD sign visible, "
        "low fluorescent ceiling lights spilling harsh white pools onto the asphalt, "
        "scattered abandoned shopping trolleys around the trolley bay, painted parking bay lines, "
        "deep midnight blue night sky, harsh fluorescent white + warm streetlamp pools, "
        "16-bit pixel art, Western Sydney late-night eshay carpark sesh aesthetic"
    ),
}

for beat_key, prompt in BEAT_PROMPTS.items():
    src_filename = f"beat_{beat_key}_src.png"
    out_filename = f"beat_{beat_key}.gif"
    src_path = os.path.join(OUT_DIR, src_filename)
    out_path = os.path.join(OUT_DIR, out_filename)
    cached_or_gen(src_filename, lambda p=prompt: gen_image(
        p, 400, 400, view="side",
        outline="lineless", shading="detailed shading", detail="highly detailed",
        no_background=False))
    if os.path.exists(src_path):
        make_city_twinkle_gif(src_path, out_path, frames=18, duration=110)


# Travel scene — single PixelLab whole-scene composition replacing the
# previous composite pipeline. Generated separately because it lands as
# sprites/travel.gif (not beat_travel.gif) for backwards-compat with
# the transition-travel-gif HTML element.
TRAVEL_PROMPT = (
    "pixel art side-on action shot of a WHITE Mitsubishi Lancer Evo IX sedan "
    "DRIVING TO THE RIGHT on a road at night with the SYDNEY CBD SKYLINE filling "
    "the background — tall high-rise office towers and apartments in deep navy "
    "silhouette, the iconic Centrepoint Tower with golden turret in the middle "
    "distance, lit warm yellow + cool white windows scattered across the building "
    "faces, red and magenta neon signs on rooftops, low-rise shopfronts at street "
    "level with neon signage glowing, "
    "the white Evo is the main focal foreground element centred at the bottom of "
    "the frame, FACING RIGHT (nose on the right side, big rear wing on the left), "
    "slammed coilover stance, deep-dish silver wheels, motion-blur lines on the "
    "wheels and on the road dashes suggesting fast forward motion, "
    "TWO CHARACTERS visible inside the cabin through the side windows — a young "
    "REDHEAD ESHAY in a NAVY BLUE NIKE TN CAP and MUSTARD YELLOW JUMPER in the "
    "front passenger seat closer to viewer, a dark-haired DRIVER in a BLACK HOODIE "
    "behind him at the wheel, warm dashboard glow lighting their faces, "
    "asphalt road with dashed yellow centre line in the foreground, warm streetlamp "
    "pools, deep navy night sky with stars, "
    "side-scroller arcade racing game aesthetic, 90s SEGA Outrun atmosphere, "
    "BOTH the car AND the Sydney skyline must be clearly visible in the frame, "
    "16-bit pixel art"
)

cached_or_gen("travel_src.png", lambda: gen_image(
    TRAVEL_PROMPT, 400, 400, view="side",
    outline="lineless", shading="detailed shading", detail="highly detailed",
    no_background=False))

if os.path.exists(os.path.join(OUT_DIR, "travel_src.png")):
    # PixelLab ignores "FACING RIGHT" direction instructions in the prompt and
    # often produces a left-facing car. Pre-flip the source horizontally so
    # the Evo always faces RIGHT in the final gif. Uses a temp file so the
    # original PixelLab-cached _src.png is preserved untouched.
    from PIL import Image as _PILImage
    _travel_src_orig = os.path.join(OUT_DIR, "travel_src.png")
    _travel_src_flipped = os.path.join(OUT_DIR, "travel_src_flipped.png")
    _PILImage.open(_travel_src_orig).transpose(_PILImage.FLIP_LEFT_RIGHT).save(_travel_src_flipped)
    make_city_twinkle_gif(
        _travel_src_flipped,
        os.path.join(OUT_DIR, "travel.gif"),
        frames=18, duration=110,
    )


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

