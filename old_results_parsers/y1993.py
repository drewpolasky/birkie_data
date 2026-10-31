#1993 birch scroll: the men's dyno american birkebeiner results on pages 31-46 (places 1-3506) and the women's on pages
#47-49 (1-520); the kortelopet follows on 50-58 and the class award lists are on 7-8. each results page has two halves of
#110 rows (so two results to a printed line), each RANK, FINAL TIME, BIB, NAME, HOMETOWN, ST, NAT, CLASS ("M35-39"), class
#RANK, 25% club ("Y"), PACE (min.sec per km over 52 km). one list per gender, placed by time; the year has no technique
#column, so tech is left blank
#
#birkie_archive's twice-size OCR (NNN_x2.tsv), which its typeset parser prefers, reads the rows well enough, but its
#character list garbles the outlined page titles, so that parser never sees "BIRKEBEINER" and keeps nothing (the plain
#OCR, NNN.tsv, reads the titles). the pages were also scanned up to 1.5 degrees askew, so a row climbs most of a line
#from the rank to the pace. here each half of each results page is turned level, cut at the rule between the halves and
#read again at three times the size with only the characters the tables use (NNN_h3L.tsv, NNN_h3R.tsv, with the turn and
#cut in NNN_h3.json), and each word is put in its column by where it sits. then:
#   names and towns: the spaces the OCR missed ('DALE WCARLSTROM') are put back where the ink has a word's gap, and of
#       the three OCRs' readings the likeliest is kept (the one whose names, or town in its state, other years know)
#   times and bibs: read digit by digit against the year's own digit shapes (tesseract reads this face's flagged 1 as
#       4 and drops tenths), checked against tesseract, the pace and the order of the list
#   states: read whole against the shapes of the codes tesseract reads in towns known in that state
import concurrent.futures
import functools
import itertools
import json
import math
import os
import re
import subprocess

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage

from birkie_archive import (OCR_DIR, PAGE_DIR, TESSERACT, ocr_words, digits, known_towns, read_time, parse_seconds,
                            LOOKALIKE)
from results_loader import compact, load_all_results, split_first_last, US_STATES, CA_PROVINCES

SUFFIX = 'h3'
SCALE = 3
WHITELIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:.-'/& "
OCR_WORKERS = 4


#---------------------------------------------------------------- pages and OCR

def results_pages(year):
    #{page: gender} for the birkebeiner results pages: the title says BIRKEBEINER (not KORTELOPET) and a column heading
    #line (HOMETOWN) sits under it
    pages = {}
    for page in range(1, 200):
        path = os.path.join(OCR_DIR, str(year), '{:03d}.tsv'.format(page))
        if not os.path.exists(path):
            continue
        words = ocr_words(year, page, scaled=False)
        top = words.loc[words['top'] < 0.2 * words['top'].max(), 'text'].str.upper()
        title = ' '.join(top)
        if 'BIRKEBEINER' in title and 'KORTE' not in title and top.str.contains('HOMETOWN').any():
            pages[page] = 'F' if 'WOMEN' in title else 'M'
    return pages


def skew_angle(image, max_degrees=2.0):
    #the turn (degrees, for Image.rotate) that levels the rows: the slope whose sheared row profile is sharpest
    small = image.resize((image.width // 2, image.height // 2))
    ys, xs = np.nonzero(np.asarray(small) < 128)
    best = None
    for degrees in np.arange(-max_degrees, max_degrees + 1e-9, 0.02):
        rows = np.round(ys - xs * math.tan(math.radians(degrees))).astype(int)
        profile = np.bincount(rows - rows.min())
        score = np.var(np.diff(profile))
        if best is None or score > best[0]:
            best = (score, degrees)
    return float(best[1])


def half_paths(year, page):
    base = os.path.join(OCR_DIR, str(year), '{:03d}_{}'.format(page, SUFFIX))
    return base + '.json', {h: base + h + '.tsv' for h in 'LR'}


def find_rule(level, max_tilt=1.0):
    #the rule between the halves on a levelled half page: (x at mid height, tilt in degrees), the line near the middle
    #with the most ink. the halves of a page can be askew by different amounts (page 43's by 1.1 and 1.5 degrees), so
    #the rule can still lean once a half is level
    w, h = level.size
    ink = np.asarray(level)[int(0.15 * h):int(0.9 * h), :] < 128
    rows = np.arange(ink.shape[0])
    xs = np.arange(w // 2 - 300, w // 2 + 200)
    best = None
    for tilt in np.arange(-max_tilt, max_tilt + 1e-9, 0.05):
        off = np.round((rows - (0.525 * h - 0.15 * h)) * math.tan(math.radians(tilt))).astype(int)
        score = ink[rows[:, None], xs[None, :] + off[:, None]].mean(axis=0)
        k = int(np.argmax(score))
        if best is None or score[k] > best[0]:
            best = (score[k], int(xs[k]), round(float(tilt), 2))
    return best[1], best[2]


def rule_x(rule, tilt, y, height):
    #the rule's x at height y
    return rule + (y - 0.525 * height) * math.tan(math.radians(tilt))


def ocr_page(year, page):
    #each half of the page levelled, cut at the rule between the halves and read at SCALE times the size
    meta_path, tsv = half_paths(year, page)
    if os.path.exists(meta_path) and all(os.path.exists(p) for p in tsv.values()):
        return
    image = Image.open(os.path.join(PAGE_DIR, str(year), '{:03d}.png'.format(page)))
    w, h = image.size
    meta = {'width': w, 'height': h, 'scale': SCALE}
    jobs = []
    for half, box in (('L', (0, 0, w // 2, h)), ('R', (w // 2, 0, w, h))):
        angle = skew_angle(image.crop(box))
        level = image.rotate(angle, resample=Image.BICUBIC, fillcolor=255)
        rule, tilt = find_rule(level)
        #everything across the rule whitened, then the half cut out
        ends = [rule_x(rule, tilt, y, h) for y in (0, h)]
        x0, x1 = (0, int(max(ends)) - 3) if half == 'L' else (int(min(ends)) + 4, w)
        pixels = np.asarray(level).copy()
        edge = np.array([rule_x(rule, tilt, y, h) for y in range(h)])[:, None]
        cols = np.arange(w)[None, :]
        pixels[(cols >= edge - 3) if half == 'L' else (cols <= edge + 4)] = 255
        crop = Image.fromarray(pixels).crop((x0, 0, x1, h))
        crop = crop.resize((crop.width * SCALE, crop.height * SCALE), Image.LANCZOS)
        png = tsv[half][:-4] + '.png'
        crop.save(png)
        meta[half] = {'angle': angle, 'x0': x0, 'rule': rule, 'tilt': tilt}
        jobs.append((png, tsv[half][:-4]))
    for png, out in jobs:
        subprocess.run([TESSERACT, png, out, '--psm', '6', '-c', 'tessedit_char_whitelist=' + WHITELIST, 'tsv'],
                       capture_output=True)
        os.remove(png)
    with open(meta_path, 'w') as f:
        json.dump(meta, f)


def ocr(year):
    pages = sorted(results_pages(year))
    with concurrent.futures.ThreadPoolExecutor(OCR_WORKERS) as pool:
        list(pool.map(lambda p: ocr_page(year, p), pages))


#---------------------------------------------------------------- rows

#where each column starts, in page pixels from the left edge of the FINAL TIME column. a word goes in the last column
#starting at or left of its middle, or for the name and hometown columns its left edge
COLUMNS = [('rank', -1e9), ('time', -12), ('bib', 85), ('name', 155), ('city', 455), ('state', 675), ('country', 735),
           ('class', 805), ('class_rank', 875), ('club', 925), ('pace', 962), ('beyond', 1045)]
TEXT_FROM, TEXT_TO = 155, 675
#rows are 25 pixels apart
PITCH = 25


def to_page(x, y, angle, width, height):
    #a point on the levelled page back on the scan (Image.rotate turns about the middle)
    t = math.radians(angle)
    dx, dy = x - width / 2, y - height / 2
    return width / 2 + dx * math.cos(t) - dy * math.sin(t), height / 2 + dx * math.sin(t) + dy * math.cos(t)


def column_of(rel, mid):
    if TEXT_FROM <= rel < TEXT_TO:
        return 'name' if rel < COLUMNS[4][1] else 'city'
    return [c for c, x in COLUMNS if x <= mid][-1]


#the name and hometown columns' letters (a narrow condensed face) are about this wide, in page pixels, as fitted to the
#OCR's word boxes. a word's ink is the letters' widths added up, less 1.8
LETTER_WIDTHS = {'-': 7.1, 'A': 11.9, 'B': 11.2, 'C': 11.7, 'D': 12.8, 'E': 10.5, 'F': 9.1, 'G': 12.5, 'H': 12.5, 'I': 5.8,
                 'J': 8.2, 'K': 11.4, 'L': 10.4, 'M': 16.0, 'N': 12.3, 'O': 12.6, 'P': 11.5, 'Q': 12.6, 'R': 12.7,
                 'S': 11.6, 'T': 10.8, 'U': 12.6, 'V': 11.8, 'W': 17.5, 'X': 11.9, 'Y': 12.3, 'Z': 10.3, "'": 4.0}
DIGIT_WIDTH = 10
#letters are 1 to 3 pixels apart and words 5 to 8: a blank this wide is a space
SPACE = 5


def ink_words(a, y, x0, x1):
    #the words printed in a row between x0 and x1, as ink: (left, right) of each run of ink with no SPACE-wide gap
    band = a[int(round(y)) - 9:int(round(y)) + 10, int(x0):int(x1)] > 0.4
    cols = np.nonzero(band.sum(axis=0) > 0)[0]
    runs = []
    for c in cols:
        if runs and c - runs[-1][1] < SPACE:
            runs[-1][1] = c + 1
        else:
            runs.append([c, c + 1])
    #a speck (a few pixels) is not a word
    return [(int(x0) + l, int(x0) + r) for l, r in runs if band[:, l:r].sum() >= 12]


#how well letters fit a run of ink: the squared misfit in units of 1.5 pixels and 3% of the width, at most MISFIT (an OCR
#slip, a letter lost or added, costs no more than that). a run of ink left without letters (a letter the OCR lost, a
#speck) or an OCR word left out costs SKIP; a cut the OCR didn't make, or an OCR space inside one run, costs SEAM
MISFIT, SKIP, SEAM = 9.0, 6.0, 4.0


def split_words(words, inked):
    #the OCR's words (text, left) of the name and hometown columns, with the spaces it missed put back: the letters, in
    #order, are shared out among the runs of ink so each run's width best matches its letters' widths. a space the OCR
    #put inside one run is kept
    #a number (a postcode) keeps the OCR's reading and place, and the ink under it is set aside
    words = [(t.strip(), left, right) for t, left, right in words if t.strip()]
    number = lambda t: bool(re.fullmatch(r'\d{3,}', t))
    numbers = [(t, left) for t, left, _ in words if number(t)]
    inked = [(l, r) for l, r in inked if not any(left - 4 <= l < right + 4 for t, left, right in words if number(t))]
    words = [(t, left) for t, left, _ in words if not number(t)]
    if not words or not inked:
        return sorted(words + numbers, key=lambda w: w[1])
    chars = ''.join(t for t, _ in words)
    starts = [int(x) for x in np.cumsum([0] + [len(t) for t, _ in words])]
    breaks = set(starts[1:-1])
    edge = np.concatenate([[0], np.cumsum([LETTER_WIDTHS.get(c, DIGIT_WIDTH if c.isdigit() else 11.0) for c in chars])])
    n, m = len(chars), len(inked)
    best = {(0, 0): (0.0, None)}
    for i in range(n + 1):
        for j in range(m + 1):
            if (i, j) not in best:
                continue
            c0 = best[(i, j)][0]
            steps = []
            if j < m:
                width = inked[j][1] - inked[j][0]
                sigma = 1.5 + 0.03 * width
                steps.append(((i, j + 1), SKIP))
                for k in range(i + 1, n + 1):
                    pred = edge[k] - edge[i] - 1.8
                    if pred > 2 * width + 30:
                        break
                    seams = SEAM * (len([b for b in breaks if i < b < k]) + (k < n and k not in breaks))
                    steps.append(((k, j + 1), min(((pred - width) / sigma) ** 2, MISFIT) + seams))
            if i in starts[:-1]:
                steps.append(((starts[starts.index(i) + 1], j), SKIP))
            for state, c in steps:
                if state not in best or c0 + c < best[state][0]:
                    best[state] = (c0 + c, (i, j))
    if (n, m) not in best:
        return sorted(words + numbers, key=lambda w: w[1])
    groups, state = [], (n, m)
    while best[state][1] is not None:
        prev = best[state][1]
        if prev[1] < state[1] and prev[0] < state[0]:
            groups.append((prev[0], state[0], prev[1]))
        state = prev
    out = []
    for i, k, j in sorted(groups):
        cut = [i] + sorted(b for b in breaks if i < b < k) + [k]
        out.append((' '.join(chars[a:b] for a, b in zip(cut, cut[1:])), inked[j][0]))
    return sorted(out + numbers, key=lambda w: w[1])


def unread(pieces, inked, ref):
    #how many words of ink in the name column no reading's word sits on (a middle initial the OCR lost)
    lefts = {x for _, x in pieces}
    return sum(1 for l, _ in inked if l - ref < COLUMNS[4][1] and l not in lefts)


def half_rows(year, page, half):
    #one half page's results, top to bottom: each row's words by column, from the levelled OCR's lines
    meta_path, tsv = half_paths(year, page)
    with open(meta_path) as f:
        meta = json.load(f)
    words = pd.read_csv(tsv[half], sep='\t', quoting=3, dtype={'text': str}, keep_default_na=False)
    words = words[(words['level'] == 5) & (words['text'].str.strip() != '')].copy()
    s = meta['scale']
    words['x'], words['y'] = words['left'] / s + meta[half]['x0'], words['top'] / s
    words['w'], words['h'] = words['width'] / s, words['height'] / s
    times = words[words['text'].str.contains(r'\d[:.]\d\d[:.]\d\d')]
    if len(times) < 5:
        return []
    ref = times['x'].median()
    header = words.loc[words['text'].str.contains('HOMETOWN|FINAL'), 'y']
    start = header.max() + PITCH / 2 if len(header) else times['y'].min() - PITCH
    centre = lambda l: (l['y'] + l['h'] / 2).median()
    lines = []
    for _, line in words.groupby(['block_num', 'par_num', 'line_num']):
        line = line[line['text'].str.contains(r'[0-9A-Z]')]
        if line.empty or centre(line) < start:
            continue
        lines.append(line)
    #tesseract lines closer than half a row are one row
    lines.sort(key=centre)
    merged = []
    for line in lines:
        if merged and abs(centre(line) - centre(merged[-1])) < PITCH / 2:
            merged[-1] = pd.concat([merged[-1], line])
        else:
            merged.append(line)
    a = ink(year, page, half)
    rows = []
    for line in merged:
        y = centre(line)
        line = line.sort_values('x')
        rel = line['x'] - ref
        #(a word whose box starts a little left of the name column but is mostly in it is a name)
        in_text = (rel + line['w'] / 2 >= TEXT_FROM) & (rel + line['w'] / 2 < TEXT_TO)
        text = line[in_text]
        inked = ink_words(a, y, ref + TEXT_FROM - 5, ref + TEXT_TO)
        fields = {c: [] for c, _ in COLUMNS}
        pieces = split_words(list(zip(text['text'], text['x'], text['x'] + text['w'])), inked)
        for t, x in pieces:
            fields[column_of(x - ref, x - ref)].append(t)
        boxes = {}
        for _, w in line[~in_text].iterrows():
            r = w['x'] - ref
            column = column_of(r, r + w['w'] / 2)
            fields[column].append(w['text'])
            box = (w['x'], w['y'], w['x'] + w['w'], w['y'] + w['h'])
            old = boxes.get(column, box)
            boxes[column] = (min(old[0], box[0]), min(old[1], box[1]), max(old[2], box[2]), max(old[3], box[3]))
        #a result has a name and a time or pace
        if not (re.search('[A-Z]{2}', ' '.join(fields['name'])) and
                (len(digits(' '.join(fields['time']))) >= 4 or fields['pace'])):
            continue
        _, top = to_page(ref - 40, line['y'].min(), meta[half]['angle'], meta['width'], meta['height'])
        rows.append({'page': page, 'half': half, 'y': y, 'top': int(round(top)), 'ref': ref, 'boxes': boxes,
                     'text_raw': ' '.join(text['text']), 'unread': unread(pieces, inked, ref),
                     **{c: ' '.join(v) for c, v in fields.items()}})
    return rows


#---------------------------------------------------------------- the other readings of the names and towns

#the page was read twice before, unlevelled: by birkie_archive at its own size (NNN.tsv) and at twice the size with a
#character list (NNN_x2.tsv). each misreads names and towns the others get right ('ROCKFGRD', 'MADISGN' here), so their
#words are put in this parse's rows and columns too, and the likeliest reading of each name and town kept
OTHER_READINGS = [('x2', '_x2', 2), ('x1', '', 1)]


def other_readings(year, page, half, rows):
    #{reading: [(name, town) for each row]}: the other OCRs' words turned level with the half page, each in the row its
    #middle is nearest (within 9 pixels), the missed spaces put back from the ink as for this parse's own words
    meta_path, _ = half_paths(year, page)
    with open(meta_path) as f:
        meta = json.load(f)
    angle, width, height = meta[half]['angle'], meta['width'], meta['height']
    a = ink(year, page, half)
    ys = np.array([r['y'] for r in rows])
    out = {}
    for reading, suffix, scale in OTHER_READINGS:
        path = os.path.join(OCR_DIR, str(year), '{:03d}{}.tsv'.format(page, suffix))
        found = [[] for _ in rows]
        if os.path.exists(path) and len(rows):
            words = pd.read_csv(path, sep='\t', quoting=3, dtype={'text': str}, keep_default_na=False)
            words = words[(words['level'] == 5) & words['text'].str.contains('[A-Za-z0-9]')]
            for w in words.itertuples():
                mid = (w.top + w.height / 2) / scale
                lx, ly = to_page(w.left / scale, mid, -angle, width, height)
                rx, _ = to_page((w.left + w.width) / scale, mid, -angle, width, height)
                k = int(np.argmin(np.abs(ys - ly)))
                rel = (lx + rx) / 2 - rows[k]['ref']
                if abs(ys[k] - ly) < 9 and TEXT_FROM <= rel < TEXT_TO:
                    found[k].append((w.text.upper(), lx, rx))
        out[reading] = []
        for r, words in zip(rows, found):
            inked = ink_words(a, r['y'], r['ref'] + TEXT_FROM - 5, r['ref'] + TEXT_TO)
            pieces = split_words(sorted(words, key=lambda w: w[1]), inked)
            out[reading].append((' '.join(t for t, x in pieces if x - r['ref'] < COLUMNS[4][1]),
                                 ' '.join(t for t, x in pieces if x - r['ref'] >= COLUMNS[4][1]),
                                 unread(pieces, inked, r['ref'])))
    return out


@functools.lru_cache(maxsize=None)
def known_names():
    clean = load_all_results()
    return frozenset(clean['first'].map(compact)), frozenset(clean['last'].map(compact))


def likeliest(readings, score, unread=None):
    #of a field's readings (this parse's first), the one with the best score, readings the others agree with counting
    #half a point more each, and each word of ink a reading left unread 0.6 less; this parse's own on a tie
    votes = pd.Series(readings).value_counts()
    unread = unread or [0] * len(readings)
    return max(zip(readings, unread), key=lambda r: score(r[0]) + 0.5 * (votes[r[0]] - 1) - 0.6 * r[1]
               if r[0] else -9)[0]


def name_score(name):
    first, last = known_names()
    f, _, l, _ = split_first_last(name)
    return (compact(f) in first) + (compact(l) in last)


#---------------------------------------------------------------- digits by their shapes

#tesseract reads this font's flagged 1 as 4 and drops a time's tenths now and then. the times are typeset h:mm:ss.t with
#every digit the same width, so each digit sits at a fixed distance from the hour's left edge, and is read by
#matching it against the year's own digits: the mean shape of each digit where tesseract and the pace agree
TIME_CELLS = [0, 16, 26, 42, 52, 68]
GLYPH_H, GLYPH_W, SHIFT = 19, 12, 2


@functools.lru_cache(maxsize=4)
def ink(year, page, half):
    #the levelled page as ink, 0 (paper) to 1
    meta_path, _ = half_paths(year, page)
    with open(meta_path) as f:
        angle = json.load(f)[half]['angle']
    image = Image.open(os.path.join(PAGE_DIR, str(year), '{:03d}.png'.format(page)))
    return 1 - np.asarray(image.rotate(angle, resample=Image.BICUBIC, fillcolor=255), dtype=np.float32) / 255


def hour_corners(a, ref, box, y):
    #where the hour digit's top left corner may be: the first inked column right of the rank, and the first blot of ink
    #a digit's size (a speck of dirt before or above the hour fools the first, a broken digit the second)
    y0, y1 = (box[1], box[3]) if box else (y - 10, y + 10)
    y0, y1, x0 = int(y0) - 4, int(y1) + 4, int(ref) - 8
    out = []
    band = a[y0:y1, x0:x0 + 100] > 0.45
    cols = np.nonzero(band[:, :20].sum(axis=0) >= 2)[0]
    if len(cols):
        h0 = x0 + cols[0]
        rows = np.nonzero((a[y0:y1, h0:h0 + 10] > 0.45).sum(axis=1) >= 2)[0]
        if len(rows):
            out.append((h0, y0 + rows[0]))
    y0, x0 = int(y) - 16, int(ref) - 25
    labels, _ = ndimage.label(a[y0:int(y) + 16, x0:x0 + 110] > 0.45)
    blots = sorted((sl[1].start, sl[0].start) for sl in ndimage.find_objects(labels)
                   if 14 <= sl[0].stop - sl[0].start <= 24 and 4 <= sl[1].stop - sl[1].start <= 16)
    first = next(((x0 + x, y0 + t) for x, t in blots if x0 + x >= ref - 20), None)
    if first and first not in out:
        out.append(first)
    return out


def time_cells(a, corner):
    #the six digit cells of a time whose hour starts at corner, each with SHIFT pixels to spare all round, or None
    h0, top = corner
    out = []
    for cell in TIME_CELLS:
        left = h0 + cell - 1 - SHIFT
        patch = a[top - 1 - SHIFT:top - 1 + GLYPH_H + SHIFT, left:left + GLYPH_W + 2 * SHIFT]
        if patch.shape != (GLYPH_H + 2 * SHIFT, GLYPH_W + 2 * SHIFT):
            return None
        out.append(patch)
    return np.array(out)


def windows(patches, h=GLYPH_H, w=GLYPH_W):
    #every placement of an h by w box in each patch (SHIFT pixels bigger all round): (patches, shifts, h, w)
    n = 2 * SHIFT + 1
    return np.stack([patches[:, dy:dy + h, dx:dx + w] for dy in range(n) for dx in range(n)], axis=1)


def match(patches, templates, chunk=2000):
    #each patch's distance to each template at its best placement: (patches, templates), and that placement
    flat = templates.reshape(len(templates), -1)
    dist, at = [], []
    for k in range(0, len(patches), chunk):
        win = windows(patches[k:k + chunk], *templates.shape[1:])
        win = win.reshape(win.shape[0], win.shape[1], -1)
        d = (win ** 2).sum(axis=2)[:, :, None] - 2 * win @ flat.T + (flat ** 2).sum(axis=1)[None, None]
        dist.append(d.min(axis=1))
        at.append(d.argmin(axis=1))
    return np.concatenate(dist), np.concatenate(at)


def learn_templates(patches, labels, rounds=3):
    #each label's (0, 1, 2...) mean shape, each sample placed where it best fits the shape so far
    h, w = patches.shape[1] - 2 * SHIFT, patches.shape[2] - 2 * SHIFT
    classes = range(labels.max() + 1)
    centre = patches[:, SHIFT:SHIFT + h, SHIFT:SHIFT + w]
    templates = np.array([centre[labels == k].mean(axis=0) for k in classes])
    n = 2 * SHIFT + 1
    for _ in range(rounds):
        _, at = match(patches, templates)
        best = at[np.arange(len(patches)), labels]
        placed = np.array([p[dy:dy + h, dx:dx + w] for p, dy, dx in zip(patches, best // n, best % n)])
        templates = np.array([placed[labels == k].mean(axis=0) for k in classes])
    return templates


def read_glyph_times(df, year):
    #each row's time read digit by digit from the shapes: the digits, and for each cell the margin between its best and
    #second best digit and that second best. the shapes are learnt from rows whose tesseract time the pace confirms:
    #first from the hour and minute digits (which the pace pins), then from every digit the shapes and tesseract agree
    #on. of a row's places for the hour, the one whose cells the shapes fit best is read
    cells, owner, corners = [], [], []
    for i, r in enumerate(df.itertuples()):
        a = ink(year, r.page, r.half)
        for corner in hour_corners(a, r.ref, r.boxes.get('time'), r.y):
            c = time_cells(a, corner)
            if c is not None:
                cells.append(c)
                owner.append(i)
                corners.append(corner)
    owner = np.array(owner)
    first_try = np.concatenate([[True], owner[1:] != owner[:-1]])
    cells = np.array(cells)
    read = df['time_digits'].values[owner]
    pace = df['pace_s'].values[owner]
    sure = np.array([len(d) == 6 and bool(time_text(d)) and not np.isnan(p) and fits_pace(parse_seconds(time_text(d)), p)
                     for d, p in zip(read, pace)]) & first_try
    tess = np.array([[int(c) for c in d] if len(d) == 6 else [-1] * 6 for d in read])
    flat = cells.reshape(-1, *cells.shape[2:])
    position = np.tile(np.arange(6), len(cells))
    use = np.repeat(sure, 6) & (position < 3)
    templates = learn_templates(flat[use], tess.ravel()[use])
    for _ in range(2):
        dist, _ = match(flat, templates)
        agree = (dist.argmin(axis=1) == tess.ravel()) & np.repeat(first_try, 6)
        templates = learn_templates(flat[agree], tess.ravel()[agree])
    dist, _ = match(flat, templates)
    dist = dist.reshape(len(cells), 6, 10)
    total = dist.min(axis=2).sum(axis=1)
    out = [('', np.zeros(6), '', None)] * len(df)
    best_total = {}
    for k, i in enumerate(owner):
        if i in best_total and best_total[i] <= total[k]:
            continue
        best_total[i] = total[k]
        order = np.argsort(dist[k], axis=1)
        d = np.take_along_axis(dist[k], order, axis=1)
        out[i] = (''.join(str(x) for x in order[:, 0]), d[:, 1] - d[:, 0], ''.join(str(x) for x in order[:, 1]),
                  corners[k])
    return out, templates


#the bibs are set flush right in the same figures, the last one's cell BIB_RIGHT pixels right of the hour's
BIB_RIGHT = 133


def read_glyph_bibs(df, year, templates):
    #each row's bib read digit by digit from the shapes, right to left until a cell has no ink: (digits, each cell's
    #margin between its best and second best digit, the second best digits), or None where the time wasn't found
    out = []
    for r in df.itertuples():
        if r.corner is None:
            out.append(None)
            continue
        a = ink(year, r.page, r.half)
        h0, top = r.corner
        cells = []
        for k in range(5):
            left = h0 + BIB_RIGHT - 10 * k - 1 - SHIFT
            if (a[top:top + 18, left + SHIFT + 2:left + SHIFT + 10] > 0.45).sum() < 20:
                break
            cells.append(a[top - 1 - SHIFT:top - 1 + GLYPH_H + SHIFT, left:left + GLYPH_W + 2 * SHIFT])
        if not cells:
            out.append(('', np.zeros(0), ''))
            continue
        dist, _ = match(np.array(cells[::-1]), templates)
        order = np.argsort(dist, axis=1)
        d = np.take_along_axis(dist, order, axis=1)
        out.append((''.join(str(x) for x in order[:, 0]), d[:, 1] - d[:, 0], ''.join(str(x) for x in order[:, 1])))
    return out


def choose_bibs(glyphs, tess):
    #the shapes' bib where every cell was sure. where one wasn't, the first of: tesseract's reading if it's one the
    #shapes allow (a second best digit), the shapes' best, the shapes' other readings, that no sure bib already has
    sure = {g[0] for g in glyphs if g and g[0] and min(g[1]) >= SURE}
    out = []
    for g, t in zip(glyphs, tess):
        if g is None:
            out.append(t)
            continue
        digits_, margin, second = g
        if not digits_ or min(margin) >= SURE:
            out.append(digits_)
            continue
        unsure = [c for c in range(len(digits_)) if margin[c] < SURE]
        shapes = [digits_] + [''.join(second[c] if c in cells else digits_[c] for c in range(len(digits_)))
                              for n in (1, 2) for cells in itertools.combinations(unsure, n)]
        tries = ([t] if t in shapes else []) + shapes
        out.append(next((b for b in tries if b not in sure), digits_))
    return out


#the states and the nations are read whole, against the mean shape of each code the OCR read where it can be trusted
#(a state in a town known in that state, a nation's code): CODE_W pixels from the code's first letter (a state, set
#flush left) or last (a nation, set flush right), which sit in these columns right of the FINAL TIME column's left edge
CODE_W = 40
STATE_COLUMN, NATION_COLUMN = (655, 745), (725, 805)
#a code's shape fits this well (summed squared ink) when it's that code, and beats the next best by this much
CODE_FIT, CODE_MARGIN = 40.0, 5.0
#codes the tables use that aren't the usual two letters
PROVINCES = {'ONT': 'ON', 'MAN': 'MB', 'QUE': 'QC', 'PQ': 'QC', 'SAS': 'SK', 'SASK': 'SK', 'ALB': 'AB', 'ALTA': 'AB',
             'WIS': 'WI', 'ILL': 'IL', 'MINN': 'MN', 'MICH': 'MI'}
#the nations' codes in the tables (FR and CZ as printed)
NATIONS = {'USA', 'CAN', 'NOR', 'SWE', 'FIN', 'ITA', 'AUT', 'FRA', 'FR', 'SUI', 'AUS', 'FRG', 'BRD', 'GER', 'CIS', 'TCH',
           'CZ', 'BEL', 'LUX', 'IND', 'UK', 'GBR', 'JPN', 'DEN', 'NED', 'ESP', 'POL', 'RUS', 'EST', 'NZL', 'ISL'}


def code_patch(a, corner, ref, column, right=False):
    #a code's ink in a row, from the edge of its first (or last) letter-sized blot (a speck of dirt isn't one)
    h0, top = corner
    x0 = int(ref) + column[0]
    labels, _ = ndimage.label(a[top - 2:top + 21, x0:int(ref) + column[1]] > 0.45)
    blots = [sl[1] for sl in ndimage.find_objects(labels) if sl[0].stop - sl[0].start >= 12]
    if not blots:
        return None
    left = (x0 + max(b.stop for b in blots) - CODE_W if right else x0 + min(b.start for b in blots)) - 1 - SHIFT
    patch = a[top - 1 - SHIFT:top - 1 + GLYPH_H + SHIFT, left:left + CODE_W + 2 * SHIFT]
    return patch if patch.shape == (GLYPH_H + 2 * SHIFT, CODE_W + 2 * SHIFT) else None


def read_glyph_codes(df, year, sure, column, right=False):
    #each row's code read from its shape, the shapes learnt from the rows whose OCR reading is sure (else None): (code,
    #how far its shape is from the code's, the margin to the next best code), or None where there's no shape to read
    patches = [None if r.corner is None else code_patch(ink(year, r.page, r.half), r.corner, r.ref, column, right)
               for r in df.itertuples()]
    sure = [s if p is not None else None for s, p in zip(sure, patches)]
    codes = sorted({s for s in sure if s})
    train = [i for i, s in enumerate(sure) if s]
    templates = learn_templates(np.array([patches[i] for i in train]), np.array([codes.index(sure[i]) for i in train]))
    have = [i for i, p in enumerate(patches) if p is not None]
    dist, _ = match(np.array([patches[i] for i in have]), templates)
    order = np.sort(dist, axis=1)
    out = [None] * len(df)
    for k, i in enumerate(have):
        out[i] = (codes[int(dist[k].argmin())], float(order[k, 0]), float(order[k, 1] - order[k, 0]))
    return out, set(codes)


def choose_code(read, glyph, shapes, valid):
    #the shape's code where it fits well and clearly (or agrees with the OCR), else the OCR's. an OCR reading that is a
    #real code but one with no shape to match against ('BC', 'YT') is kept
    if read in valid and read not in shapes:
        return read
    if glyph and glyph[2] >= CODE_MARGIN and (glyph[1] < CODE_FIT or glyph[0] == read):
        return glyph[0]
    return read


def choose_state(read, glyph, shapes, country):
    #the tables' own codes for a few provinces and states ('ONT', 'WIS') are put in the usual two letters; AL in Canada
    #is Alberta
    read = choose_code(read, glyph, shapes, US_STATES | CA_PROVINCES | set(PROVINCES))
    read = PROVINCES.get(read, read)
    return 'AB' if read == 'AL' and country == 'CAN' else read


#---------------------------------------------------------------- fields

TIME_PARTS = re.compile(r'(\d+)\W+(\d\d)\W+(\d\d)\W+(\d)')


def split_time(text):
    #(rank digits run into the front, h:mm:ss.t digits): '32:05:12.0' is rank 3 and 2:05:12.0. the hours are one digit
    m = TIME_PARTS.search(text.translate(DIGIT_LETTERS))
    if m:
        return m.group(1)[:-1], m.group(1)[-1] + m.group(2) + m.group(3) + m.group(4)
    return '', digits(text)


DIGIT_LETTERS = str.maketrans({'O': '0', 'D': '0', 'Q': '0', 'I': '1', 'L': '1', 'S': '5', 'B': '8', 'Z': '2', 'G': '6'})


def time_text(d):
    return read_time(d) if len(d) == 6 else ''


def read_pace(text):
    #min.sec per km: '2.24', '241', '3-30'
    d = digits(text)
    if len(d) == 3 and int(d[1:]) < 60:
        return int(d[0]) * 60 + int(d[1:])
    return np.nan


GROUPS = ['18-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', '65-69', '70+']
UPPER = {g[-2:]: g for g in GROUPS[:-1]}
LOWER = {g[:2]: g for g in GROUPS}


def read_class(text):
    #the age class from 'M35-39', 'M3539', 'M85-39', '40-44', 'M70' (the whitelist has no '+'): the upper bound names
    #the class, failing that the lower bound
    t = re.sub(r'^[^0-9]*?[MFH](?=[0-9OSBG])', '', text.upper().replace(' ', ''))
    d = digits(t.translate(DIGIT_LETTERS))
    if len(d) < 2:
        return ''
    if d.startswith('70') and len(d) <= 3:
        return '70+'
    if len(d) >= 3 and d[-2:] in UPPER:
        return UPPER[d[-2:]]
    if len(d) >= 4 and d[:2] in LOWER:
        return LOWER[d[:2]]
    return ''


#---------------------------------------------------------------- the lists

def counted(read, window=10):
    #the numbers that count up by one down a list (places, or class ranks within a class), from what OCR read of them
    #(an int or None for each entry, in order). each entry's offset (reading minus position) is the one most entries
    #within window of it share, so misreads are outvoted. next to a change of offset (OCR lost or added an entry) an
    #entry keeps a number only if its own reading has the offset of one side
    n = len(read)
    offset = [r - i if r is not None else None for i, r in enumerate(read)]
    shared = []
    for i in range(n):
        near = sorted((abs(j - i), offset[j]) for j in range(max(0, i - window), min(n, i + window + 1))
                      if offset[j] is not None)
        shared.append(common([o for _, o in near]))
    out = [None] * n
    for i in range(n):
        if shared[i] is None:
            continue
        sides = {shared[j] for j in (i - 1, i + 1) if 0 <= j < n and shared[j] is not None}
        if sides - {shared[i]}:
            out[i] = read[i] if offset[i] in sides | {shared[i]} else None
        else:
            out[i] = i + shared[i]
    return out


def common(values):
    #the value most of them share, the nearest one breaking a tie
    if not values:
        return None
    counts = pd.Series(values).value_counts()
    top = counts[counts == counts.max()].index
    return next(v for v in values if v in top)


#the pace column is the time over 52 km, rounded to the second
KM = 52.0
PACE_SLACK = 0.6
#digits OCR mixes up: birkie_archive's LOOKALIKE, and this font's flagged 1 read as 4
SWAPS = {**{k: {v} for k, v in LOOKALIKE.items()}, '4': {'1'}, '1': {'7', '4'}}


def variants(d):
    #readings one OCR slip away from the digits d: one digit swapped for a lookalike, any of the 4s read for 1s put
    #back, a stray digit dropped (seven digits) or a lost one put back (five)
    if len(d) == 7:
        out = set()
        for j in range(7):
            out |= variants(d[:j] + d[j + 1:]) | {d[:j] + d[j + 1:]}
        return out
    if len(d) == 5:
        return {d[:j] + c + d[j:] for j in range(6) for c in '0123456789'}
    if len(d) != 6:
        return set()
    out = {d[:j] + c + d[j + 1:] for j, x in enumerate(d) for c in SWAPS.get(x, ())}
    fours = [j for j, x in enumerate(d) if x == '4']
    for mask in range(1, 2 ** len(fours)):
        e = list(d)
        for k, j in enumerate(fours):
            if mask >> k & 1:
                e[j] = '1'
        out.add(''.join(e))
    return out


def fits_pace(seconds, pace):
    return np.isnan(pace) or abs(seconds / KM - pace) <= PACE_SLACK


def nondecreasing(values):
    #positions of the longest run (not necessarily adjacent) of values that never go down
    import bisect
    tails, tails_at, prev = [], [], [-1] * len(values)
    for i, v in enumerate(values):
        k = bisect.bisect_right(tails, v)
        if k == len(tails):
            tails.append(v)
            tails_at.append(i)
        else:
            tails[k], tails_at[k] = v, i
        prev[i] = tails_at[k - 1] if k else -1
    out, i = [], tails_at[-1] if tails_at else -1
    while i >= 0:
        out.append(i)
        i = prev[i]
    return out[::-1]


def clean_paces(paces):
    #the paces never go down the list: one off the longest run of them that doesn't is a misreading ('9.03' for 5.03)
    at = [i for i, p in enumerate(paces) if np.isfinite(p)]
    out = np.full(len(paces), np.nan)
    for k in nondecreasing([paces[i] for i in at]):
        out[at[k]] = paces[at[k]]
    return out


#a cell whose best digit's shape fits this much better than the next best is read as that digit
SURE = 2.0


def time_candidates(glyph, margin, second, tess):
    #the readings of one time, likeliest first: the shapes' digits, then with the unsure cells' second best digits put
    #in (one or two of them), then tesseract's, then one OCR slip away from tesseract's
    out = [glyph] if glyph else []
    unsure = [c for c in range(6) if glyph and margin[c] < SURE]
    for n in (1, 2):
        for cells in itertools.combinations(unsure, n):
            out.append(''.join(second[c] if c in cells else glyph[c] for c in range(6)))
    out.append(tess)
    out += sorted(variants(tess))
    return [time_text(d) for d in dict.fromkeys(out) if time_text(d)]


def repair_times(lst):
    #a time the shapes and tesseract read alike, in order with the others read alike, is kept. any other time has to
    #fall between those around it and fit its pace: the shapes' reading is kept if it does and every cell was sure;
    #else of the readings that do, the one tesseract and the shapes (best or second best digits) agree on, failing that
    #the shapes' best, failing that the only one; else it's left blank
    n = len(lst)
    glyph, tess = lst['glyph'].tolist(), lst['time_digits'].tolist()
    margin, second = lst['glyph_margin'].tolist(), lst['glyph_second'].tolist()
    pace = lst['pace_s'].values.astype(float)
    alike = [i for i in range(n) if time_text(glyph[i]) and glyph[i] == tess[i]]
    alike = [alike[k] for k in nondecreasing([parse_seconds(time_text(glyph[i])) for i in alike])]
    anchor = np.full(n, np.nan)
    anchor[alike] = [parse_seconds(time_text(glyph[i])) for i in alike]
    before = pd.Series(anchor).ffill().fillna(0).values
    after = pd.Series(anchor).bfill().fillna(np.inf).values
    out, how = [], []
    for i in range(n):
        if np.isfinite(anchor[i]):
            out.append(time_text(glyph[i]))
            how.append('read')
            continue
        lo, hi = (before[i - 1] if i else 0), (after[i + 1] if i + 1 < n else np.inf)
        fits = lambda t: lo <= parse_seconds(t) <= hi and fits_pace(parse_seconds(t), pace[i])
        g = time_text(glyph[i])
        if g and fits(g) and min(margin[i]) >= SURE:
            out.append(g)
            how.append('shapes')
            continue
        good = [t for t in time_candidates(glyph[i], margin[i], second[i], tess[i]) if fits(t)]
        t = time_text(tess[i])
        shapes = time_candidates(glyph[i], margin[i], second[i], '')
        pick = t if t in good and t in shapes else g if g in good else good[0] if len(set(good)) == 1 else ''
        out.append(pick)
        how.append('repaired' if pick else 'blank')
    return out, how


def repair_classes(groups, ranks):
    #each class's ranks count up by one down the list. an entry whose class OCR lost or misread, so that its rank
    #fits neither neighbour in that class, goes in the one class whose entries just before and after it it fits
    #between (rank one more than the one before, one less than the one after). then each class's ranks are counted
    groups, ranks = list(groups), list(ranks)

    def neighbours(i, g):
        before = next((ranks[j] for j in range(i - 1, -1, -1) if groups[j] == g and ranks[j] is not None), 0)
        after = next((ranks[j] for j in range(i + 1, len(groups)) if groups[j] == g and ranks[j] is not None), None)
        return before, after

    for i in range(len(groups)):
        r = ranks[i]
        if r is None:
            continue
        if groups[i]:
            b, a = neighbours(i, groups[i])
            if r == b + 1 or (a is not None and r == a - 1):
                continue
        fits = [g for g in GROUPS if neighbours(i, g)[0] + 1 == r and neighbours(i, g)[1] == r + 1]
        if len(fits) == 1:
            groups[i] = fits[0]
    out = [None] * len(groups)
    for g in GROUPS:
        at = [i for i, x in enumerate(groups) if x == g]
        for i, r in zip(at, counted([ranks[i] for i in at])):
            out[i] = r
    return groups, out


STATE_LOOKS = {'MIN': 'MN', 'NIN': 'MN', 'VIN': 'MN', 'IVIN': 'MN', 'MNN': 'MN', 'W': 'WI', 'WL': 'WI', 'VI': 'WI',
               'LL': 'IL', 'L': 'IL', 'IIL': 'IL', 'M': 'MI|MN', 'N': 'MN', 'NM': 'MN|NM', 'MW': 'MN|MI'}


def read_state(text, city):
    #the state as printed, or the one its OCR slip points to: a lookalike reading ('MIN', 'W', 'LL') is mapped back, and
    #where that leaves a choice ('M': MI or MN) the one the town is known in
    s = re.sub(r'[^A-Z]', '', text.upper())
    if s in US_STATES | CA_PROVINCES or not s:
        return s
    choices = STATE_LOOKS.get(s, '').split('|') if s in STATE_LOOKS else []
    choices = [c for c in choices if c]
    if len(choices) > 1:
        towns = known_towns()
        choices = [c for c in choices if (compact(city), c) in towns]
    return choices[0] if len(choices) == 1 else s


def clean_words(text, keep_digits=False):
    allowed = r"[^A-Z0-9' -]" if keep_digits else r"[^A-Z' -]"
    words = [re.sub(allowed, '', w).strip("-'") for w in text.upper().split()]
    return ' '.join(w for w in words if w)


def parse(year):
    pages = results_pages(year)
    missing = [p for p in pages if not all(os.path.exists(f) for f in [half_paths(year, p)[0], *half_paths(year, p)[1].values()])]
    if missing:
        ocr(year)
    rows = []
    for page, gender in sorted(pages.items()):
        for half in 'LR':
            found = half_rows(year, page, half)
            others = other_readings(year, page, half, found)
            for k, r in enumerate(found):
                rows.append({**r, 'gender': gender, **{reading: v[k] for reading, v in others.items()}})
    df = pd.DataFrame(rows)
    parts = df['time'].map(split_time)
    df['rank_read'] = [digits(r) or pre for r, (pre, _) in zip(df['rank'], parts)]
    df['time_digits'] = [d for _, d in parts]
    df['pace_s'] = np.concatenate([clean_paces(lst['pace'].map(read_pace).values)
                                   for _, lst in df.groupby('gender', sort=False)])
    glyphs, templates = read_glyph_times(df, year)
    df['glyph'], df['glyph_margin'], df['glyph_second'], df['corner'] = [list(x) for x in zip(*glyphs)]
    out = []
    for gender, lst in df.groupby('gender', sort=False):
        lst = lst.reset_index(drop=True)
        ranks = [int(r) if r and len(r) <= 4 else None for r in lst['rank_read']]
        lst['place'] = counted(ranks)
        lst['time'], lst['time_how'] = repair_times(lst)
        lst['group'] = lst['class'].map(read_class)
        lst['class_rank_read'] = lst['class_rank'].map(lambda t: int(digits(t)) if 0 < len(digits(t)) <= 3 else None)
        lst['group'], lst['class_rank'] = repair_classes(lst['group'], lst['class_rank_read'])
        out.append(lst)
    df = pd.concat(out, ignore_index=True)
    df['age_group'] = np.where(df['group'] != '', df['gender'] + ' ' + df['group'], '')
    df['class_rank'] = df['class_rank'].map(lambda r: '' if r is None or pd.isna(r) else str(int(r)))
    df['place'] = df['place'].map(lambda r: '' if r is None or pd.isna(r) else str(int(r)))
    df['bib'] = choose_bibs(read_glyph_bibs(df, year, templates), df['bib'].map(digits).tolist())
    readings = [r for r, _, _ in OTHER_READINGS]
    df['name'] = [likeliest([clean_words(n)] + [clean_words(r[0]) for r in rs], name_score, [u] + [r[2] for r in rs])
                  for n, u, rs in zip(df['name'], df['unread'], df[readings].values)]
    df['cities'] = [[clean_words(c, keep_digits=True)] + [clean_words(r[1], keep_digits=True) for r in rs]
                    for c, rs in zip(df['city'], df[readings].values)]
    df['city'] = [c[0] for c in df['cities']]
    #(junk the OCR ran into a code: 'WOUSA')
    read = df['country'].map(lambda t: re.sub(r'^[A-Z]+(?=USA$|CAN$)', '', re.sub(r'[^A-Z]', '', t.upper())))
    glyphs, shapes = read_glyph_codes(df, year, [c if c in NATIONS else None for c in read], NATION_COLUMN, True)
    df['country'] = [choose_code(r, g, shapes, NATIONS) for r, g in zip(read, glyphs)]
    read = [read_state(t, c) for t, c in zip(df['state'], df['city'])]
    towns = known_towns()
    sure = [s if s and ((compact(c), s) in towns or s in PROVINCES) else None for s, c in zip(read, df['city'])]
    glyphs, shapes = read_glyph_codes(df, year, sure, STATE_COLUMN)
    df['state'] = [choose_state(r, g, shapes, c) for r, g, c in zip(read, glyphs, df['country'])]
    df['city'] = [likeliest(c, lambda t: (compact(t), s) in towns) for c, s in zip(df['cities'], df['state'])]
    df.loc[df['state'].isin(US_STATES) & (df['country'] == ''), 'country'] = 'USA'
    df.loc[df['state'].isin(CA_PROVINCES) & (df['country'] == ''), 'country'] = 'CAN'
    df['status'] = 'finished'
    df['tech'] = ''
    return df


if __name__ == '__main__':
    import sys
    ocr(int(sys.argv[1]) if len(sys.argv) > 1 else 1993)
