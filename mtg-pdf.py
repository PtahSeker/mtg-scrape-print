#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Convert card images to PDF for printing in natural size (63x88 mm)
# Requires: reportlab

import os, re, argparse, math
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4, LETTER, A3

CARD_W_MM = 63.0
CARD_H_MM = 88.0

PAPERS = {
    "a4": A4,         # 210 x 297 mm
    "letter": LETTER, # 8.5x11 in
    "a3": A3,
}
# reportlab reads png/jpg; webp support depends on the system
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

def natural_key(s):
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r'(\d+)', s)]

def list_images(folder):
    files = []
    for name in sorted(os.listdir(folder), key=natural_key):
        ext = os.path.splitext(name)[1].lower()
        if ext in IMG_EXTS:
            files.append(os.path.join(folder, name))
    return files

def parse_custom_paper(spec: str):
    # format "WxHmm" i.e. "210x297mm" or "279x216mm"
    m = re.match(r'^\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)(mm|cm|in)?\s*$',
                 spec, re.IGNORECASE)
    if not m:
        raise ValueError(
            "Invalid paper format. Example: 210x297mm or 8.5x11in")
    w, h, unit = m.groups()
    w = float(w); h = float(h)
    unit = (unit or "mm").lower()
    if unit == "mm":
        return (w*mm, h*mm)
    if unit == "cm":
        return (w*10*mm, h*10*mm)
    if unit in ("in", "inch", "inches"):
        return (w*25.4*mm, h*25.4*mm)
    raise ValueError("Unknown units (allowed: mm, cm, in)")

def draw_crop_marks(c: canvas.Canvas, x, y, w, h, mark_len=5*mm,
                    offset=0.3*mm):
    # draw crop marks outside the card corners
    c.setLineWidth(0.3)
    # bottom left
    c.line(x - offset - mark_len, y - offset, x - offset, y - offset)
    c.line(x - offset, y - offset - mark_len, x - offset, y - offset)
    # bottom right
    c.line(x + w + offset, y - offset, x + w + offset + mark_len, y - offset)
    c.line(x + w + offset, y - offset - mark_len, x + w + offset, y - offset)
    # top left
    c.line(x - offset - mark_len, y + h + offset, x - offset, y + h + offset)
    c.line(x - offset, y + h + offset, x - offset, y + h + offset + mark_len)
    # top right
    c.line(x + w + offset, y + h + offset, x + w + offset + mark_len,
           y + h + offset)
    c.line(x + w + offset, y + h + offset, x + w + offset,
           y + h + offset + mark_len)

def draw_black_borders(c: canvas.Canvas, rows, cols, x0, y0, w, h, dx, dy, gap_mm):
    # Draw black rectangles in the gaps between cards and around outer edges
    c.setFillColor((0, 0, 0))  # black
    
    gap = gap_mm * mm
    
    # Calculate the total grid dimensions
    total_width = cols * dx - gap
    total_height = rows * dy - gap
    
    # Draw outer border rectangles (extending beyond the card grid)
    border_extend = gap  # How far to extend the border
    
    # Top border
    c.rect(x0 - border_extend, y0 + total_height, 
           total_width + 2*border_extend, border_extend, fill=1, stroke=0)
    
    # Bottom border  
    c.rect(x0 - border_extend, y0 - border_extend,
           total_width + 2*border_extend, border_extend, fill=1, stroke=0)
    
    # Left border
    c.rect(x0 - border_extend, y0 - border_extend,
           border_extend, total_height + 2*border_extend, fill=1, stroke=0)
    
    # Right border
    c.rect(x0 + total_width, y0 - border_extend,
           border_extend, total_height + 2*border_extend, fill=1, stroke=0)
    
    # Horizontal gaps (between rows)
    for row in range(rows - 1):
        y_gap = y0 + (rows - 1 - row) * dy - gap
        c.rect(x0, y_gap, total_width, gap, fill=1, stroke=0)
    
    # Vertical gaps (between columns)
    for col in range(cols - 1):
        x_gap = x0 + col * dx + w
        c.rect(x_gap, y0, gap, total_height, fill=1, stroke=0)

def compute_grid(page_w, page_h, margin_mm, gap_mm, orientation="auto"):
    # Returns (pw, ph, rows, cols, x0, y0) where all values are in points
    # Try portrait and landscape and choose the one with more cards
    # (if orientation="auto")
    def attempt(pw, ph):
        usable_w = pw - 2*margin_mm*mm
        usable_h = ph - 2*margin_mm*mm
        cols = max(1, int((usable_w + gap_mm*mm)
                          // ((CARD_W_MM*mm) + gap_mm*mm)))
        rows = max(1, int((usable_h + gap_mm*mm)
                          // ((CARD_H_MM*mm) + gap_mm*mm)))
        x0 = (pw - (cols*CARD_W_MM*mm + (cols-1)*gap_mm*mm)) / 2.0
        y0 = (ph - (rows*CARD_H_MM*mm + (rows-1)*gap_mm*mm)) / 2.0
        return rows, cols, x0, y0

    if orientation == "portrait":
        return attempt(page_w, page_h) + (False,)
    if orientation == "landscape":
        rows, cols, x0, y0 = attempt(page_h, page_w)
        return rows, cols, x0, y0, True

    # auto
    r1, c1, x1, y1 = attempt(page_w, page_h)
    r2, c2, x2, y2 = attempt(page_h, page_w)
    n1, n2 = r1*c1, r2*c2
    if n2 > n1:
        return r2, c2, x2, y2, True  # landscape
    else:
        return r1, c1, x1, y1, False # portrait

def make_pdf(images, out_path, paper_size, margin_mm=5.0, gap_mm=3.0,
             cropmarks=False, orientation="auto", black_borders=False):
    c = canvas.Canvas(out_path, pagesize=paper_size)
    pw, ph = paper_size
    rows, cols, x0, y0, rotated = compute_grid(pw, ph, margin_mm, gap_mm,
                                               orientation)

    if rotated:
        # swap coordinate system: rotate page 90°
        c.translate(0, ph)
        c.rotate(90)
        pw, ph = ph, pw
        rows, cols, x0, y0, _ = compute_grid(pw, ph, margin_mm, gap_mm,
                                             "portrait")

    w = CARD_W_MM*mm
    h = CARD_H_MM*mm
    dx = w + gap_mm*mm
    dy = h + gap_mm*mm

    i = 0
    per_page = rows * cols
    for idx, img in enumerate(images):
        if i % per_page == 0:
            if i > 0:
                c.showPage()
                # reset the orientation on the new page
                if rotated:
                    c.translate(0, ph)
                    c.rotate(90)
            # Draw black borders for gaps on each page
            if black_borders:
                draw_black_borders(c, rows, cols, x0, y0, w, h, dx, dy, gap_mm)
            
            # Draw crop marks for all grid positions on each page
            if cropmarks:
                for grid_row in range(rows):
                    for grid_col in range(cols):
                        grid_x = x0 + grid_col*dx
                        grid_y = y0 + (rows-1-grid_row)*dy
                        draw_crop_marks(c, grid_x, grid_y, w, h, offset=0*mm)

        slot = i % per_page
        row = slot // cols
        col = slot % cols
        x = x0 + col*dx
        y = y0 + (rows-1-row)*dy  # from bottom to top

        # drawImage: preserveAspectRatio=True
        # (Scryfall PNG has ratio ~63x88 so it fits)
        try:
            c.drawImage(img, x, y, width=w, height=h,
                        preserveAspectRatio=True, anchor='sw')
        except Exception as e:
            print(f"[WARN] Cannot load image: {img} ({e})")

        i += 1

    c.save()
    return rows, cols, per_page

def main():
    p = argparse.ArgumentParser(
        description=("Create PDF for printing MTG cards in natural size "
                     "(63x88mm)"))
    p.add_argument("input_folder", help="Folder with images (.png/.jpg)")
    p.add_argument("--paper", default="a4",
                   help="a4, letter, a3 or custom npr. 210x297mm / 8.5x11in")
    p.add_argument("--out", default="cards_print.pdf", help="Output PDF")
    p.add_argument("--margin-mm", type=float, default=5.0,
                   help="Outer margin (mm)")
    p.add_argument("--gap-mm", type=float, default=3.0,
                   help="Gap between cards (mm)")
    p.add_argument("--cropmarks", action="store_true", help="Add crop marks")
    p.add_argument("--black-borders", action="store_true", 
                   help="Fill gaps with black color for easier cutting")
    p.add_argument("--orientation", choices=["auto", "portrait", "landscape"],
                   default="auto", help="Page orientation")
    args = p.parse_args()

    # Determine paper size
    paper_key = args.paper.strip().lower()
    if paper_key in PAPERS:
        paper_size = PAPERS[paper_key]
    else:
        paper_size = parse_custom_paper(args.paper)

    imgs = list_images(args.input_folder)
    if not imgs:
        raise SystemExit(
            "No images in the folder (supported: .png .jpg/.jpeg).")

    rows, cols, per_page = make_pdf(
        imgs,
        out_path=args.out,
        paper_size=paper_size,
        margin_mm=args.margin_mm,
        gap_mm=args.gap_mm,
        cropmarks=args.cropmarks,
        orientation=args.orientation,
        black_borders=args.black_borders,
    )

    total = len(imgs)
    pages = math.ceil(total / per_page)
    print((f"Done: {total} images → {args.out} | {rows}*{cols} per page "
           f"({per_page}/page), {pages} pages."))

if __name__ == "__main__":
    main()
