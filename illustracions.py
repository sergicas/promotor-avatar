"""Il·lustracions simbòliques locals, sense text, com a última reserva."""

import math
import random
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw


ARREL = Path(__file__).resolve().parent
DIR_IMATGES = ARREL / "imatges_generades"
MIDES = {
    "instagram": (1080, 1080),
    "twitter": (1600, 900),
    "linkedin": (1200, 900),
}


def _net(text):
    text = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _gradient(ample, alt, superior, inferior):
    imatge = Image.new("RGB", (ample, alt))
    dibuix = ImageDraw.Draw(imatge)
    for y in range(alt):
        t = y / max(1, alt - 1)
        color = tuple(int(a * (1 - t) + b * t) for a, b in zip(superior, inferior))
        dibuix.line((0, y, ample, y), fill=color)
    return imatge


def _llibre(d, w, h, accent):
    cy = int(h * .58)
    d.polygon([(w*.12, cy-h*.18), (w*.48, cy-h*.10), (w*.48, cy+h*.20),
               (w*.12, cy+h*.10)], fill=(239, 224, 191), outline=accent)
    d.polygon([(w*.52, cy-h*.10), (w*.88, cy-h*.18), (w*.88, cy+h*.10),
               (w*.52, cy+h*.20)], fill=(246, 233, 204), outline=accent)
    d.line((w*.5, cy-h*.10, w*.5, cy+h*.20), fill=accent, width=max(4, w//250))
    for i in range(3):
        y = cy - h*.04 + i*h*.06
        d.arc((w*.17, y-h*.04, w*.44, y+h*.02), 190, 345, fill=(170, 145, 110), width=2)
        d.arc((w*.56, y-h*.04, w*.83, y+h*.02), 195, 350, fill=(170, 145, 110), width=2)


def _arbre(d, w, h, accent):
    terra = int(h*.72)
    d.ellipse((-w*.15, terra-h*.08, w*1.15, h*1.15), fill=(91, 116, 70))
    tronc = [(w*.44, terra), (w*.48, h*.31), (w*.53, h*.31), (w*.58, terra)]
    d.polygon(tronc, fill=(104, 70, 43))
    gruix = max(6, w//100)
    for dx in (-.24, -.13, .14, .25):
        d.line((w*.5, terra, w*(.5+dx), h*.94), fill=(91, 57, 39), width=gruix)
    for dx, dy in ((-.22,-.10),(.20,-.12),(-.13,-.25),(.12,-.27)):
        d.line((w*.5, h*.42, w*(.5+dx), h*(.42+dy)), fill=(104,70,43), width=gruix)
    for x, y, r in ((.35,.25,.18),(.53,.20,.21),(.66,.30,.17),(.46,.34,.20)):
        d.ellipse((w*(x-r), h*(y-r), w*(x+r), h*(y+r)), fill=accent)


def _papallona(d, w, h, accent):
    cx, cy = w*.5, h*.5
    fosc = (54, 45, 66)
    d.ellipse((cx-w*.035, cy-h*.17, cx+w*.035, cy+h*.18), fill=fosc)
    for signe in (-1, 1):
        punts1 = [(cx,cy-h*.10),(cx+signe*w*.27,cy-h*.28),(cx+signe*w*.32,cy-h*.02),(cx,cy+h*.03)]
        punts2 = [(cx,cy+h*.02),(cx+signe*w*.26,cy+h*.10),(cx+signe*w*.18,cy+h*.31),(cx,cy+h*.16)]
        d.polygon(punts1, fill=accent, outline=fosc)
        d.polygon(punts2, fill=(205, 122, 84), outline=fosc)
    d.arc((cx-w*.10, cy-h*.25, cx, cy-h*.08), 170, 300, fill=fosc, width=4)
    d.arc((cx, cy-h*.25, cx+w*.10, cy-h*.08), 240, 370, fill=fosc, width=4)


def _rellotge(d, w, h, accent):
    r = min(w, h)*.29
    cx, cy = w*.5, h*.5
    d.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(239,226,195), outline=accent, width=max(8,w//120))
    for i in range(12):
        a = 2*math.pi*i/12
        x1, y1 = cx+math.sin(a)*r*.82, cy-math.cos(a)*r*.82
        x2, y2 = cx+math.sin(a)*r*.93, cy-math.cos(a)*r*.93
        d.line((x1,y1,x2,y2), fill=(70,61,54), width=max(3,w//300))
    d.line((cx,cy,cx-r*.08,cy-r*.46), fill=(70,61,54), width=max(8,w//130))
    d.line((cx,cy,cx+r*.40,cy+r*.14), fill=(70,61,54), width=max(8,w//130))
    d.ellipse((cx-w*.015,cy-w*.015,cx+w*.015,cy+w*.015), fill=accent)


def _riu(d, w, h, accent):
    d.ellipse((-w*.25,h*.28,w*.55,h*.95), fill=(96,128,89))
    d.ellipse((w*.35,h*.22,w*1.2,h*.93), fill=(78,112,83))
    d.polygon([(w*.47,h*.35),(w*.60,h*.35),(w*.73,h),(w*.20,h)], fill=(78,142,166))
    d.line((w*.5,h*.38,w*.42,h*.95), fill=(182,221,224), width=max(5,w//160))
    d.ellipse((w*.72,h*.12,w*.86,h*.26), fill=accent)


def _finestra_pluja(d, w, h, accent):
    marge_x, marge_y = w*.19, h*.13
    d.rectangle((marge_x,marge_y,w-marge_x,h-marge_y), fill=(79,105,122), outline=(77,57,43), width=max(12,w//60))
    d.line((w*.5,marge_y,w*.5,h-marge_y), fill=(77,57,43), width=max(8,w//90))
    d.line((marge_x,h*.5,w-marge_x,h*.5), fill=(77,57,43), width=max(8,w//90))
    rng = random.Random(7)
    for _ in range(55):
        x = rng.uniform(marge_x+10,w-marge_x-10)
        y = rng.uniform(marge_y+10,h-marge_y-30)
        d.line((x,y,x-w*.012,y+h*.045), fill=(185,216,224), width=max(2,w//400))
    d.ellipse((w*.70,h*.19,w*.82,h*.31), fill=accent)


def _fanal(d, w, h, accent):
    d.rectangle((w*.48,h*.37,w*.52,h*.86), fill=(41,42,50))
    d.polygon([(w*.41,h*.39),(w*.59,h*.39),(w*.55,h*.20),(w*.45,h*.20)], fill=accent, outline=(41,42,50))
    d.ellipse((w*.43,h*.21,w*.57,h*.43), fill=(244,204,105))
    d.ellipse((w*.30,h*.84,w*.70,h*.91), fill=(42,52,60))
    for x in (.14,.78):
        d.ellipse((w*x,h*.70,w*(x+.11),h*.78), fill=(61,77,86))


def _xarxa(d, w, h, accent):
    punts = [(w*.2,h*.55),(w*.32,h*.25),(w*.48,h*.43),(w*.64,h*.20),(w*.80,h*.53),(w*.61,h*.72),(w*.36,h*.76)]
    for i, p in enumerate(punts):
        for q in punts[i+1:]:
            if math.dist(p,q) < min(w,h)*.38:
                d.line((*p,*q), fill=(96,118,124), width=max(2,w//350))
    for i,(x,y) in enumerate(punts):
        r = min(w,h)*(.035 if i != 2 else .055)
        d.ellipse((x-r,y-r,x+r,y+r), fill=accent if i%2 else (219,232,224), outline=(51,65,69), width=3)


def _motiu(descripcio):
    t = _net(descripcio)
    if any(x in t for x in ("arrel", "arbre", "bosc", "root", "tree", "forest")):
        return "arbre"
    if any(x in t for x in ("papallona", "ales", "butterfly", "wings")):
        return "papallona"
    if any(x in t for x in ("rellotge", "temps", "clock", "time")):
        return "rellotge"
    if any(x in t for x in ("riu", "aigua", "mar", "river", "water", "sea")):
        return "riu"
    if any(x in t for x in ("finestra", "pluja", "window", "rain")):
        return "finestra"
    if any(x in t for x in ("fanal", "carrer", "nit", "streetlamp", "night")):
        return "fanal"
    if any(x in t for x in ("cervell", "neur", "robot", "xarxa", "brain", "network")):
        return "xarxa"
    return "llibre"


def genera_illustracio(descripcio, data_iso, xarxa="instagram"):
    """Genera una escena simbòlica relacionada, mai una targeta de text."""
    DIR_IMATGES.mkdir(exist_ok=True)
    cami = DIR_IMATGES / "{}_{}_illustracio.png".format(data_iso, xarxa)
    if cami.exists():
        return cami
    w, h = MIDES.get(xarxa, MIDES["instagram"])
    motiu = _motiu(descripcio)
    paletes = {
        "fanal": ((19, 31, 49), (74, 82, 92), (211, 135, 72)),
        "finestra": ((113, 142, 156), (44, 63, 77), (225, 172, 91)),
        "riu": ((196, 220, 218), (238, 203, 146), (226, 153, 75)),
    }
    superior, inferior, accent = paletes.get(
        motiu, ((236, 221, 190), (167, 194, 180), (173, 100, 57)),
    )
    imatge = _gradient(w, h, superior, inferior)
    d = ImageDraw.Draw(imatge)
    {
        "arbre": _arbre,
        "papallona": _papallona,
        "rellotge": _rellotge,
        "riu": _riu,
        "finestra": _finestra_pluja,
        "fanal": _fanal,
        "xarxa": _xarxa,
        "llibre": _llibre,
    }[motiu](d, w, h, accent)
    imatge.save(cami, "PNG", optimize=True)
    print("[illustracions] {}: escena local '{}' sense text".format(xarxa, motiu))
    return cami
