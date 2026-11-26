#!/usr/bin/env python3
"""Generate the report figures (SVG) from the benchmark results. Standard library only.

Usage: python3 report/figures/make_figures.py
Writes report/figures/hinh-*.svg. Every number is read from benchmark/results/ except the disk sizes (figure 10.1),
which are the values quoted in chapter 10 of the report.
"""
import csv
import json
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent
RES = OUT.parents[1] / "benchmark" / "results"

MYSQL, MONGO = "#0072B2", "#009E73"
MYSQL_LIGHT, MONGO_LIGHT = "#8EC4E8", "#8FD8C0"
FONT = "DejaVu Sans, Arial, Helvetica, sans-serif"
W, H = 820, 470
LEFT, RIGHT, TOP, BOTTOM = 78, 24, 56, 104


class Svg:
    def __init__(self, w=W, h=H):
        self.w, self.h, self.parts = w, h, []

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, size=12, anchor="start", weight="normal", fill="#222", rotate=None):
        tr = f' transform="rotate({rotate} {x} {y})"' if rotate else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" fill="{fill}"{tr}>{escape(s)}</text>')

    def line(self, x1, y1, x2, y2, stroke="#bbb", width=1, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{width}"{d}/>')

    def rect(self, x, y, w, h, fill, stroke="none"):
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.1f}" height="{max(h, 0):.1f}" fill="{fill}" stroke="{stroke}"/>')

    def polyline(self, pts, stroke, width=2.4, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        p = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        self.add(f'<polyline points="{p}" fill="none" stroke="{stroke}" stroke-width="{width}" stroke-linejoin="round"{d}/>')

    def circle(self, x, y, r, fill):
        self.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}"/>')

    def save(self, name):
        body = "\n".join(self.parts)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" '
               f'font-family="{FONT}"><rect width="100%" height="100%" fill="#fff"/>\n{body}\n</svg>\n')
        (OUT / name).write_text(svg, encoding="utf-8")


def legend(svg, items, y, x0=LEFT):
    """items: (label, color, dash). Wraps into rows of two to keep labels readable."""
    col_w = (svg.w - x0 - RIGHT) / 2
    for i, (label, color, dash) in enumerate(items):
        x = x0 + (i % 2) * col_w
        yy = y + (i // 2) * 20
        if dash == "bar":
            svg.rect(x, yy - 10, 16, 12, color)
        else:
            svg.line(x, yy - 4, x + 22, yy - 4, stroke=color, width=2.6, dash=dash if dash else None)
        svg.text(x + 28, yy, label, size=12)


def fmt(v):
    """Vietnamese number format; values >= 100 are rounded half up (so 688.5 reads 689, as in the report tables)."""
    if v >= 100:
        return f"{int(v + 0.5):,}".replace(",", ".")
    return f"{v:.1f}".replace(".", ",") if v != int(v) else f"{v:.0f}"


def frame(svg, title, ylabel):
    svg.text(svg.w / 2, 26, title, size=15, anchor="middle", weight="bold")
    svg.text(18, (TOP + svg.h - BOTTOM) / 2, ylabel, size=12, anchor="middle", rotate=-90)


def linear_axis(svg, ymax, ticks, unit_fmt=lambda v: f"{v:,.0f}".replace(",", ".")):
    y0, y1 = svg.h - BOTTOM, TOP
    for t in ticks:
        y = y0 - (y0 - y1) * t / ymax
        svg.line(LEFT, y, svg.w - RIGHT, y, stroke="#e3e3e3")
        svg.text(LEFT - 8, y + 4, unit_fmt(t), size=11, anchor="end", fill="#555")
    svg.line(LEFT, y0, svg.w - RIGHT, y0, stroke="#555", width=1.2)
    svg.line(LEFT, y0, LEFT, y1, stroke="#555", width=1.2)
    return y0, y1


def line_chart(name, title, ylabel, xs, series, ymax, ticks, xlabel="Số người dùng ảo (VU)", labels=True):
    svg = Svg()
    frame(svg, title, ylabel)
    y0, y1 = linear_axis(svg, ymax, ticks)
    px = lambda i: LEFT + 40 + i * (svg.w - LEFT - RIGHT - 80) / (len(xs) - 1)
    py = lambda v: y0 - (y0 - y1) * v / ymax
    for i, x in enumerate(xs):
        svg.text(px(i), y0 + 18, str(x), size=12, anchor="middle")
    svg.text((LEFT + svg.w - RIGHT) / 2, y0 + 38, xlabel, size=12, anchor="middle")
    for label, color, dash, vals in series:
        pts = [(px(i), py(v)) for i, v in enumerate(vals)]
        svg.polyline(pts, color, dash=dash)
        for (x, y), v in zip(pts, vals):
            svg.circle(x, y, 3.4, color)
    if labels:  # value labels for the last series of each color pair only keeps the chart readable
        for label, color, dash, vals in series:
            if dash is None:
                for i, v in enumerate(vals):
                    svg.text(px(i), py(v) - 9, fmt(v), size=10, anchor="middle", fill=color)
    legend(svg, [(l, c, d) for l, c, d, _ in series], y0 + 62)
    svg.save(name)


def grouped_bars(name, title, ylabel, cats, series, ymax=None, ticks=None, log=None, cat_label=None):
    """series: (label, color, values). log=(ymin, ymax) for a base-10 logarithmic axis."""
    svg = Svg()
    frame(svg, title, ylabel)
    y0, y1 = svg.h - BOTTOM, TOP
    import math
    if log:
        lo, hi = math.log10(log[0]), math.log10(log[1])
        py = lambda v: y0 - (y0 - y1) * (math.log10(max(v, log[0])) - lo) / (hi - lo)
        t = log[0]
        while t <= log[1]:
            y = py(t)
            svg.line(LEFT, y, svg.w - RIGHT, y, stroke="#e3e3e3")
            svg.text(LEFT - 8, y + 4, fmt(t), size=11, anchor="end", fill="#555")
            t *= 10
    else:
        py = lambda v: y0 - (y0 - y1) * v / ymax
        for t in ticks:
            y = py(t)
            svg.line(LEFT, y, svg.w - RIGHT, y, stroke="#e3e3e3")
            svg.text(LEFT - 8, y + 4, fmt(t), size=11, anchor="end", fill="#555")
    svg.line(LEFT, y0, svg.w - RIGHT, y0, stroke="#555", width=1.2)
    svg.line(LEFT, y0, LEFT, y1, stroke="#555", width=1.2)
    gw = (svg.w - LEFT - RIGHT) / len(cats)
    bw = gw * 0.78 / len(series)
    for ci, cat in enumerate(cats):
        gx = LEFT + ci * gw + gw * 0.11
        for si, (label, color, vals) in enumerate(series):
            v = vals[ci]
            x = gx + si * bw
            svg.rect(x, py(v), bw - 2, y0 - py(v), color)
            svg.text(x + (bw - 2) / 2, py(v) - 4, fmt(v), size=9, anchor="middle", fill="#333")
        svg.text(LEFT + ci * gw + gw / 2, y0 + 18, cat, size=12, anchor="middle")
    if cat_label:
        svg.text((LEFT + svg.w - RIGHT) / 2, y0 + 38, cat_label, size=12, anchor="middle")
    legend(svg, [(l, c, "bar") for l, c, _ in series], y0 + 62)
    svg.save(name)


def tsv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def fig_8_1():
    rows = tsv(RES / "comparison.tsv")
    qs = ["q1_revenue_by_month", "q2_top_skus", "q3_revenue_by_category", "q4_top_customers", "q5_low_stock_by_warehouse"]
    get = lambda db, col: [float(next(r for r in rows if r["query"] == q and r["db"] == db)[col]) for q in qs]
    grouped_bars("hinh-8-1-class1-latency.svg", "Độ trễ p50 của năm truy vấn: baseline và sau tối ưu", "Độ trễ p50 (ms, thang logarit)",
                 ["q1 theo tháng", "q2 top SKU", "q3 theo danh mục", "q4 top khách", "q5 tồn kho thấp"],
                 [("MySQL baseline", MYSQL_LIGHT, get("mysql", "baseline_analyzed_p50_ms")),
                  ("MySQL sau tối ưu", MYSQL, get("mysql", "optimized_p50_ms")),
                  ("MongoDB baseline", MONGO_LIGHT, get("mongodb", "baseline_analyzed_p50_ms")),
                  ("MongoDB sau tối ưu", MONGO, get("mongodb", "optimized_p50_ms"))],
                 log=(10, 10000))


def fig_9_1():
    rows = tsv(RES / "load_comparison.search_products.tsv")
    vus = [4, 8, 16, 32, 64]
    get = lambda db, col: [float(next(r for r in rows if r["db"] == db and int(r["vus"]) == v)[col]) for v in vus]
    line_chart("hinh-9-1-search-tps.svg", "Thông lượng tìm kiếm theo số người dùng ảo", "Yêu cầu mỗi giây (TPS)", vus,
               [("MySQL baseline", MYSQL, "6 4", get("mysql", "baseline_r2_tps")),
                ("MySQL sau tối ưu", MYSQL, None, get("mysql", "optimized_tps")),
                ("MongoDB baseline", MONGO, "6 4", get("mongodb", "baseline_r2_tps")),
                ("MongoDB sau tối ưu", MONGO, None, get("mongodb", "optimized_tps"))],
               1400, [0, 200, 400, 600, 800, 1000, 1200, 1400])


def checkout_tps(phase, db, vus):
    out = []
    for v in vus:
        m = json.loads((RES / phase / "load" / f"checkout.{db}.vus{v}.summary.json").read_text())["metrics"]
        out.append(m["checkout_ok"]["rate"])
    return out


def fig_9_3():
    vus = [4, 8, 16, 32]
    line_chart("hinh-9-3-checkout-tps.svg", "Thông lượng đặt hàng theo số người dùng ảo (baseline, hai lần đo)", "Checkout thành công mỗi giây", vus,
               [("MySQL lần 1", MYSQL, "6 4", checkout_tps("baseline_checkout", "mysql", vus)),
                ("MySQL lần 2", MYSQL, None, checkout_tps("baseline_checkout_r2", "mysql", vus)),
                ("MongoDB lần 1", MONGO, "6 4", checkout_tps("baseline_checkout", "mongodb", vus)),
                ("MongoDB lần 2", MONGO, None, checkout_tps("baseline_checkout_r2", "mongodb", vus))],
               3000, [0, 500, 1000, 1500, 2000, 2500, 3000])


def fig_9_4():
    vus = [4, 8, 16, 32]
    avg = lambda db: [(a + b) / 2 for a, b in zip(checkout_tps("baseline_checkout", db, vus), checkout_tps("baseline_checkout_r2", db, vus))]
    grouped_bars("hinh-9-4-index-tax.svg", "Chi phí ghi của các chỉ mục tối ưu: thông lượng đặt hàng", "Checkout thành công mỗi giây",
                 [str(v) for v in vus],
                 [("MySQL baseline (trung bình hai lần)", MYSQL_LIGHT, avg("mysql")),
                  ("MySQL có chỉ mục", MYSQL, checkout_tps("indexed_checkout", "mysql", vus)),
                  ("MongoDB baseline (trung bình hai lần)", MONGO_LIGHT, avg("mongodb")),
                  ("MongoDB có chỉ mục", MONGO, checkout_tps("indexed_checkout", "mongodb", vus))],
                 ymax=3000, ticks=[0, 500, 1000, 1500, 2000, 2500, 3000], cat_label="Số người dùng ảo (VU)")


def fig_10_1():
    """Stacked bars: data and indexes in MB (values quoted in chapter 10)."""
    svg = Svg()
    frame(svg, "Dung lượng sau khi nạp 1.000.000 đơn hàng", "Dung lượng (MB)")
    cols = [("MySQL\n(trên đĩa)", 349.0, 215.3, MYSQL, MYSQL_LIGHT),
            ("MongoDB\n(dữ liệu chưa nén)", 875.8, 0.0, MONGO, MONGO_LIGHT),
            ("MongoDB\n(trên đĩa, nén)", 259.0, 58.3, MONGO, MONGO_LIGHT)]
    ymax = 1000
    y0, y1 = svg.h - BOTTOM + 30, TOP
    for t in range(0, ymax + 1, 200):
        y = y0 - (y0 - y1) * t / ymax
        svg.line(LEFT, y, svg.w - RIGHT, y, stroke="#e3e3e3")
        svg.text(LEFT - 8, y + 4, fmt(t), size=11, anchor="end", fill="#555")
    svg.line(LEFT, y0, svg.w - RIGHT, y0, stroke="#555", width=1.2)
    svg.line(LEFT, y0, LEFT, y1, stroke="#555", width=1.2)
    gw = (svg.w - LEFT - RIGHT) / len(cols)
    for i, (label, data, idx, c_data, c_idx) in enumerate(cols):
        x = LEFT + i * gw + gw * 0.25
        w = gw * 0.5
        yd = y0 - (y0 - y1) * data / ymax
        yi = y0 - (y0 - y1) * (data + idx) / ymax
        svg.rect(x, yd, w, y0 - yd, c_data)
        svg.rect(x, yi, w, yd - yi, c_idx)
        svg.text(x + w / 2, yi - 6, f"tổng {fmt(data + idx)}" if idx else f"{fmt(data)}", size=12, anchor="middle", weight="bold")
        svg.text(x + w / 2, (yd + y0) / 2 + 4, f"dữ liệu {fmt(data)}", size=11, anchor="middle", fill="#fff")
        if idx == 0:
            pass
        elif yd - yi > 14:
            svg.text(x + w / 2, (yd + yi) / 2 + 4, f"chỉ mục {fmt(idx)}", size=11, anchor="middle")
        else:
            svg.text(x + w + 6, (yd + yi) / 2 + 4, f"chỉ mục {fmt(idx)}", size=10, anchor="start")
        for k, part in enumerate(label.split("\n")):
            svg.text(x + w / 2, y0 + 18 + 15 * k, part, size=12, anchor="middle")
    legend(svg, [("Dữ liệu (màu đậm)", "#555", "bar"), ("Chỉ mục (màu nhạt)", "#bbb", "bar")], y0 + 56)
    svg.save("hinh-10-1-disk.svg")


if __name__ == "__main__":
    fig_8_1()
    fig_9_1()
    fig_9_3()
    fig_9_4()
    fig_10_1()
    print("written to", OUT)
