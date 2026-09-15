"""生成 PromptForge 应用图标（科技风：深色圆角底 + 青色闪电 + 提示词尖括号）。"""
from PIL import Image, ImageDraw

S = 256  # 基准画布


def rounded_bg(draw, size, radius, top, bottom):
    # 垂直渐变背景
    for y in range(size):
        t = y / (size - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (size, y)], fill=(r, g, b))


def make(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # 圆角蒙版
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    radius = int(size * 0.22)
    md.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)

    # 渐变底色
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg)
    rounded_bg(bd, size, radius, (13, 27, 42), (27, 38, 59))
    img = Image.composite(img, bg, mask)
    d = ImageDraw.Draw(img)

    cyan = (0, 212, 255, 255)
    cyan_dim = (0, 150, 200, 255)

    u = size / 256.0  # 缩放系数

    # 左右尖括号 < >（代表提示词/代码）
    lw = max(2, int(14 * u))
    # 左 <
    d.line([(78 * u, 96 * u), (46 * u, 128 * u)], fill=cyan, width=lw, joint="curve")
    d.line([(46 * u, 128 * u), (78 * u, 160 * u)], fill=cyan, width=lw, joint="curve")
    # 右 >
    d.line([(178 * u, 96 * u), (210 * u, 128 * u)], fill=cyan, width=lw, joint="curve")
    d.line([(210 * u, 128 * u), (178 * u, 160 * u)], fill=cyan, width=lw, joint="curve")

    # 中央闪电（代表一键增强/锻造）
    bolt = [
        (140 * u, 52 * u),
        (96 * u, 140 * u),
        (124 * u, 140 * u),
        (112 * u, 204 * u),
        (162 * u, 112 * u),
        (132 * u, 112 * u),
    ]
    d.polygon(bolt, fill=(255, 214, 10, 255), outline=(255, 170, 0, 255))

    # 应用圆角蒙版裁掉溢出部分
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def main():
    sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
    imgs = [make(s) for s in sizes]
    out = r"D:\PromptForge\assets\icon.ico"
    imgs[-1].save(out, format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs[:-1])
    # 同时存一张 256 png 供预览
    imgs[-1].save(r"D:\PromptForge\assets\icon.png")
    print("icon saved:", out)


if __name__ == "__main__":
    main()