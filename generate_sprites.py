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
    "ranger_side": "Toyota Hilux SR5 lifted 4x4 dual-cab work ute "
                   "seen from a STRICT DIRECT side profile view, "
                   "the truck is FACING RIGHT — nose / front bumper / headlights on the RIGHT, "
                   "REAR / tray-back / taillights on the LEFT, "
                   "FLOATING in empty space with NOTHING below the wheels — "
                   "ZERO ground shadow, ZERO drop shadow, ZERO ground line, "
                   "the four wheels touch FULLY EMPTY TRANSPARENT BACKGROUND directly, "
                   "absolutely no shading or pixels anywhere below the bottom of the tyres, "
                   "camera positioned exactly perpendicular to the truck at ground level on the driver side, "
                   "both passenger-side wheels visible at the bottom — OVERSIZED chunky knobbly MUD TYRES "
                   "(35-inch, deep aggressive lugs) on BLACK MAG RIMS, "
                   "the entire ute length visible from bullbar to towbar — classic Hilux SR5 silhouette "
                   "with a stubby dual-cab + short tray back, "
                   "MATTE DARK GREY paint with subtle weathering and minor dust streaks, "
                   "tall steel BULLBAR at front with twin LED light bars on top, "
                   "tall SNORKEL intake mounted along the driver-side A-pillar, "
                   "JACKED-UP lifted suspension giving very HIGH stance (taller than a person standing), "
                   "tray back at rear with a black toolbox lid, "
                   "subtle HILUX decal on the rear door, mud splatter along the lower body panels and wheel arches, "
                   "Australian country-boy work-ute pixel art game sprite, "
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
        "standing on a dirt patch beside his JACKED-UP Ford Ranger Wildtrak pickup ute "
        "(matte dark grey paint, tall steel bullbar with twin LED light bars, oversized chunky knobbly mud tyres "
        "on black mag rims, snorkel intake along driver side, lifted suspension, tray back with toolbox), "
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
        "pixel art EXTREME CLOSE-UP PORTRAIT of a young white Australian "
        "ESHAY teenager named Brenno, his FACE FILLS THE FRAME, "
        "wearing a NAVY BLUE NIKE TN CAP with a YELLOW swoosh pulled low, "
        "a MUSTARD YELLOW crewneck JUMPER visible at his collar, "
        "BRIGHT GINGER hair sticking out untidily under the cap brim and at the sides, "
        "freckled pale skin flushed red from stress with light acne visible, "
        "his EXPRESSION IS UTTER HORROR + DISMAY — "
        "EYES WIDE OPEN with pupils tiny in pure shock, "
        "MOUTH HANGING OPEN in a silent stretched 'NOOO', teeth visible, "
        "eyebrows raised HIGH in panic, deep wrinkles of distress on his forehead, "
        "sweat beads forming on his forehead and temples, "
        "BOTH HANDS raised gripping the brim of his TN CAP pulling it down over his eyes in despair, "
        "knuckles white, "
        "the cap brim casts deep shadow over his eyes amplifying the dread, "
        "background blurred Blacktown Maccas carpark at night — deep navy, "
        "warm streetlamp halos and McDonalds golden arches glow softly out of focus, "
        "the iconic 'BRA. BRAAAAAAA. ME PIECE!' moment of devastating realisation, "
        "16-bit pixel art with HIGH DETAIL on the face + cap + jumper, "
        "comedic-tragic close-up portrait, NO other characters, "
        "Brenno's face must DOMINATE the frame from chin to cap"
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
        "DARK BROWN messy hair partly visible under his dusty wide-brim AKUBRA cowboy hat brim "
        "(matching his portrait look), sun-tanned weathered face with sharp angular cheekbones "
        "and a lopsided friendly grin (face is a small detail in the wider shot, not the focus), "
        "the Akubra brim casting shadow over his eyes, "
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
        "the prize-handover moment after the hill climb victory, "
        "Penrith country-edge atmosphere, "
        "NO face close-up, NO portrait crop — the bong + scene context are the focus"
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
    make_city_twinkle_gif(
        os.path.join(OUT_DIR, "travel_src.png"),
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

