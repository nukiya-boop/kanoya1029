"""春日の森イメージ Instagram リール (1080x1920, 30秒) を生成する。

使い方: python3 reel/make_reel.py  → reel/kasuga_forest_reel.mp4
"""
import math
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, "images")
OUT = os.path.join(ROOT, "reel", "kasuga_forest_reel.mp4")

W, H, FPS, DURATION = 1080, 1920, 30, 30.0
GOLD = (201, 169, 110)
FONT_DIR = os.path.join(ROOT, "reel", "fonts")
FONT_JP = os.path.join(FONT_DIR, "ShipporiMincho-Medium.ttf")
FONT_EN = os.path.join(FONT_DIR, "CormorantGaramond[wght].ttf")
FONT_EN_IT = os.path.join(FONT_DIR, "CormorantGaramond-Italic[wght].ttf")

# (ファイル, 表示秒数, 和文コピー, 英文サブコピー, 次へのトランジション)
SLIDES = [
    ("S__63709238_0.jpg", 4.3, ["春日の森へ"], "Into the forest of Kasuga", "dissolve"),
    ("S__63709241_0.jpg", 4.3, [], None, "slide_up"),
    ("S__63709239_0.jpg", 4.3, ["深い緑に、", "夜がおりてくる"], "Night settles on deep green", "dip_black"),
    ("IMG_0258.jpg", 4.3, ["千年の杜に", "灯がともる"], "Lanterns in an ancient grove", "zoom_dissolve"),
    ("IMG_0261.jpg", 4.3, [], None, "light_sweep"),
    ("S__63709242_0.jpg", 4.3, ["静けさを、まとう"], "Wrapped in stillness", "dip_black"),
    ("S__63709243_0.jpg", 4.3, [], None, "iris"),
    ("S__63709244_0.jpg", 6.9, ["森を眺めて眠る、", "ひとときを。"], "Sleep beside the forest", None),
]
TRANS = 1.0  # トランジション秒数（前後スライドが重なる時間）

BOX_W, BOX_H = 940, 1300  # メイン画像の最大表示枠（画像は切らずにこの中に収める）
CENTER_Y = 840


_FONTS = {}


def font(path, size, weight=None):
    key = (path, size, weight)
    if key not in _FONTS:
        f = ImageFont.truetype(path, size)
        if weight:
            f.set_variation_by_axes([weight])
        _FONTS[key] = f
    return _FONTS[key]


GOLD_TOP = np.array([236, 214, 164], dtype=np.float32)
GOLD_BOTTOM = np.array([176, 140, 82], dtype=np.float32)
CREAM = (238, 230, 212)
_GLYPHS = {}


def glyph(ch, f, gold=True):
    """1文字分の RGBA タイル（金のグラデーション＋柔らかい影）。"""
    key = (ch, id(f), gold)
    if key in _GLYPHS:
        return _GLYPHS[key]
    asc, desc = f.getmetrics()
    pad = 12
    w = int(math.ceil(f.getlength(ch))) + pad * 2
    h = asc + desc + pad * 2
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((pad, pad), ch, font=f, fill=255)
    m = np.asarray(mask, dtype=np.float32) / 255.0
    if gold:
        g = np.linspace(0, 1, h)[:, None, None]
        rgb = GOLD_TOP * (1 - g) + GOLD_BOTTOM * g
        rgb = np.broadcast_to(rgb, (h, w, 3))
    else:
        rgb = np.broadcast_to(np.array(CREAM, dtype=np.float32), (h, w, 3))
    shadow = np.asarray(mask.filter(ImageFilter.GaussianBlur(6)), dtype=np.float32) / 255.0
    # 影(黒)の上に文字を合成
    sa = np.clip(shadow * 0.75, 0, 1)
    out_a = m + sa * (1 - m)
    out_rgb = rgb * m[..., None] / np.maximum(out_a, 1e-6)[..., None]
    tile = np.dstack([np.clip(out_rgb, 0, 255), out_a * 255]).astype(np.uint8)
    res = (Image.fromarray(tile, "RGBA"), pad, w - pad * 2)
    _GLYPHS[key] = res
    return res


def draw_line(layer, text, f, cx, y, tracking, t, start, stagger, gold=True, fade=0.7, rise=14, alpha=1.0):
    """1行を中央揃えで、1文字ずつふわっと浮かび上がらせる。"""
    chars = list(text)
    widths = [glyph(c, f, gold)[2] for c in chars]
    total = sum(widths) + tracking * (len(chars) - 1)
    x = cx - total / 2
    for i, c in enumerate(chars):
        tile, pad, adv = glyph(c, f, gold)
        k = ease((t - start - i * stagger) / fade)
        a = k * alpha
        if a > 0.003 and c != " ":
            tl = tile
            if a < 0.999:
                arr = np.asarray(tile).copy()
                arr[..., 3] = (arr[..., 3] * a).astype(np.uint8)
                tl = Image.fromarray(arr, "RGBA")
            layer.alpha_composite(tl, (int(round(x - pad)), int(round(y - pad + rise * (1 - k)))))
        x += adv + tracking
    return len(chars) * stagger + fade


def ornament(d, cx, y, k, alpha, half=90):
    """中央の菱形から左右へ伸びる金の細線。"""
    if alpha <= 0 or k <= 0:
        return
    col = (214, 188, 132, int(230 * alpha))
    L = half * k
    d.line([(cx - 12 - L, y), (cx - 12, y)], fill=col, width=1)
    d.line([(cx + 12, y), (cx + 12 + L, y)], fill=col, width=1)
    r = 4
    d.polygon([(cx, y - r), (cx + r, y), (cx, y + r), (cx - r, y)], outline=col)


def prepare(fname):
    src = Image.open(os.path.join(IMG_DIR, fname)).convert("RGB")
    # わずかに暖色寄り・落ち着いたトーンに
    arr = np.asarray(src).astype(np.float32)
    arr[..., 0] *= 1.03
    arr[..., 2] *= 0.95
    arr = np.clip((arr - 128) * 1.05 + 124, 0, 255)
    src = Image.fromarray(arr.astype(np.uint8))

    scale = min(BOX_W / src.width, BOX_H / src.height)
    fit = (round(src.width * scale), round(src.height * scale))
    main = src.resize((round(fit[0] * 1.06), round(fit[1] * 1.06)), Image.LANCZOS)

    # 背景: 同じ写真を大きくぼかして暗く敷く（メイン画像は切らない）
    bs = max(W / src.width, H / src.height) * 1.15
    bg = src.resize((round(src.width * bs), round(src.height * bs)), Image.BILINEAR)
    bg = bg.filter(ImageFilter.GaussianBlur(40))
    bg = Image.fromarray((np.asarray(bg) * 0.32).astype(np.uint8))
    return {"main": main, "fit": fit, "bg": bg}


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return 0.5 - 0.5 * math.cos(math.pi * x)


def vignette():
    y, x = np.ogrid[:H, :W]
    d = np.sqrt(((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2)
    return np.clip(1.0 - 0.45 * np.clip(d - 0.55, 0, 1) ** 1.5, 0, 1)[..., None]


VIG = vignette()


def render_slide(p, local_t, dur, extra_scale=1.0, dy=0):
    """1枚分のフレームを作る。local_t はスライド内の経過秒。"""
    prog = local_t / dur
    canvas = Image.new("RGB", (W, H))

    # 背景はゆっくり横に流す
    bg = p["bg"]
    ox = int((bg.width - W) * (0.3 + 0.4 * prog))
    oy = (bg.height - H) // 2
    canvas.paste(bg.crop((ox, oy, ox + W, oy + H)), (0, 0))

    # メイン画像: 全体を見せたままゆっくりズームイン (1.00 → 1.05)
    s = (1.0 + 0.05 * prog) * extra_scale
    fw, fh = p["fit"]
    size = (round(fw * s), round(fh * s))
    img = p["main"].resize(size, Image.BILINEAR)
    x = (W - size[0]) // 2
    y = CENTER_Y - size[1] // 2 + dy

    # 細いゴールドの額縁
    d = ImageDraw.Draw(canvas)
    pad = 14
    d.rectangle([x - pad, y - pad, x + size[0] + pad, y + size[1] + pad],
                outline=GOLD, width=1)
    canvas.paste(img, (x, y))
    return canvas, (y + size[1] + pad)


def draw_text(canvas, lines, en, local_t, dur, bottom):
    if not lines:
        return
    out = 1.0 - ease((local_t - (dur - 0.7)) / 0.7)
    if out <= 0 or local_t < 0.5:
        return
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    top = max(bottom + 80, 1270)
    ornament(d, W / 2, top, ease((local_t - 0.5) / 1.0), out)
    f = font(FONT_JP, 54)
    yy = top + 44
    start = 0.75
    for line in lines:
        draw_line(layer, line, f, W / 2, yy, 14, local_t, start, 0.07, alpha=out)
        start += 0.07 * len(line) * 0.6
        yy += 86
    if en:
        fe = font(FONT_EN_IT, 34, 400)
        draw_line(layer, en, fe, W / 2, yy + 14, 2, local_t, start + 0.6, 0.0,
                  gold=False, fade=1.2, rise=8, alpha=0.8 * out)
    canvas.paste(layer, (0, 0), layer)


def end_card(canvas, t_from_start):
    a = ease(t_from_start / 1.5)
    if a <= 0:
        return canvas
    dark = Image.new("RGB", (W, H), (8, 10, 8))
    canvas = Image.blend(canvas, dark, 0.62 * a)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    alpha = int(255 * a)
    # 公式サイト表記: 奈良春日 鹿のや / Nara Kasuga Kanoya
    t = t_from_start
    cy = 830
    draw_line(layer, "奈良春日", font(FONT_JP, 40), W / 2, cy - 120, 22, t, 0.4, 0.1, gold=False)
    draw_line(layer, "鹿のや", font(FONT_JP, 150), W / 2, cy - 60, 36, t, 0.8, 0.18, fade=1.0, rise=20)
    ornament(d, W / 2, cy + 190, ease((t - 1.6) / 1.2), a, half=120)
    draw_line(layer, "NARA KASUGA KANOYA", font(FONT_EN, 30, 500), W / 2, cy + 222, 9, t, 2.0, 0.0,
              gold=False, fade=1.2, rise=6, alpha=0.85)
    canvas.paste(layer, (0, 0), layer)
    return canvas


def soft_mask(kind, k):
    """トランジション用マスク (H, W, 1)。1 で次のスライド。"""
    if kind == "light_sweep":
        x = np.linspace(0, 1, W)[None, :]
        y = np.linspace(0, 1, H)[:, None]
        pos = x * 0.75 + y * 0.25  # 斜めにやわらかく流れる
        edge = -0.3 + 1.6 * k
        return np.clip((edge - pos) / 0.3, 0, 1)[..., None]
    if kind == "iris":
        yy, xx = np.ogrid[:H, :W]
        r = np.sqrt((xx - W / 2) ** 2 + (yy - CENTER_Y) ** 2) / math.hypot(W / 2, H / 2)
        edge = -0.2 + 1.5 * k
        return np.clip((edge - r) / 0.25, 0, 1)[..., None]
    return None


def main():
    preps = [prepare(s[0]) for s in SLIDES]
    starts, t = [], 0.0
    for _, dur, _, _, _ in SLIDES:
        starts.append(t)
        t += dur - TRANS
    total_frames = int(DURATION * FPS)

    ff = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-shortest", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "128k", OUT,
    ], stdin=subprocess.PIPE)

    def frame_of(i, t, **kw):
        fname, dur, lines, en, _ = SLIDES[i]
        lt = t - starts[i]
        c, bottom = render_slide(preps[i], lt, dur, **kw)
        draw_text(c, lines, en, lt, 3.0 if i == len(SLIDES) - 1 else dur, bottom)
        if i == len(SLIDES) - 1:
            c = end_card(c, lt - 2.4)
        return c

    for n in range(total_frames):
        t = n / FPS
        cur = max(i for i in range(len(SLIDES)) if starts[i] <= t)
        prev = cur - 1
        in_trans = prev >= 0 and t < starts[cur] + TRANS
        if not in_trans:
            img = frame_of(cur, t)
        else:
            k = (t - starts[cur]) / TRANS
            kind = SLIDES[prev][4]
            if kind == "dip_black":
                if k < 0.5:
                    img = Image.blend(frame_of(prev, t), Image.new("RGB", (W, H)), ease(k * 2))
                else:
                    img = Image.blend(Image.new("RGB", (W, H)), frame_of(cur, t), ease(k * 2 - 1))
            elif kind == "slide_up":
                e = ease(k)
                a = frame_of(prev, t, dy=int(-50 * e))
                b = frame_of(cur, t, dy=int(70 * (1 - e)))
                img = Image.blend(a, b, e)
            elif kind == "zoom_dissolve":
                e = ease(k)
                a = frame_of(prev, t, extra_scale=1 + 0.04 * e)
                b = frame_of(cur, t, extra_scale=1.06 - 0.06 * e)
                img = Image.blend(a, b, e)
            elif kind in ("light_sweep", "iris"):
                m = soft_mask(kind, ease(k))
                a = np.asarray(frame_of(prev, t), dtype=np.float32)
                b = np.asarray(frame_of(cur, t), dtype=np.float32)
                mix = a * (1 - m) + b * m
                if kind == "light_sweep":  # 境目にほのかな光
                    glow = (m * (1 - m) * 4) ** 2 * 40
                    mix = mix + glow * np.array([1.0, 0.9, 0.7])
                img = Image.fromarray(np.clip(mix, 0, 255).astype(np.uint8))
            else:  # dissolve
                img = Image.blend(frame_of(prev, t), frame_of(cur, t), ease(k))

        arr = np.asarray(img, dtype=np.float32) * VIG
        # 冒頭はフェードイン、最後は黒へフェードアウト
        fade = min(ease(t / 1.2), ease((DURATION - t) / 0.8))
        arr *= fade
        ff.stdin.write(np.clip(arr, 0, 255).astype(np.uint8).tobytes())
        if n % 150 == 0:
            print(f"{n}/{total_frames}", flush=True)

    ff.stdin.close()
    ff.wait()
    print("done:", OUT)


if __name__ == "__main__":
    main()
