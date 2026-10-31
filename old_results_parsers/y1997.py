#1997 birch scroll: "MEN'S DYNO AMERICAN BIRKEBEINER RESULTS" on pages 28-31 and 36-51 (ranks 1-4229) and "WOMEN'S ..."
#on pages 52-55 (ranks 1-730), then the kortelopet (56-65), which is left out, as are the award lists before page 28.
#each page has two columns of RANK, a "C" for a classic skier (the key at the foot says C = CLASSICAL, so the rest
#skated), FINAL TIME (h:mm:ss.t), BIB (up to five digits), NAME, HOMETOWN, ST, NAT, CLASS ("M 25-29"), CL RANK, 25%
#("Y" for the 25 year club) and PACE TIME (minutes.seconds per km). classic and skate skiers share one list per gender,
#and the class ranks count both. a column holds 106 results, or 107; one man (page 45) is listed with a time and no
#rank or class rank
#
#the page-wide OCR mixes the two columns up, so each column is read on its own: the half page is turned upright (the
#scans lean by up to 2 degrees, more than a line over a column), its lines found from the ink in the time column, and
#each line's columns placed by where its time, class and pace actually start (the right hand pages lean a few pixels
#more). the numbers are read glyph by glyph: every line's rank is known (the ranks count up by one down a column, and
#each column must start where the one before it ended), so the rank digits label some 17,000 samples of the table's
#own digits, and each digit of a time, bib, class rank and pace is the nearest of those samples; touching digits that
#read badly are cut again where they read best. the words, and the numbers a second time, are read by tesseract from
#strips of one field each, the strip's lines stacked apart and read at three times the size with only the characters
#the field can hold; the names and towns four ways, voted on with the names and towns of the clean results. tesseract
#drops the narrow I (WI as "W", GRABOWSKI as "GRABOWSK"), which comes back from the letters' widths, and a state still
#unread is the one whose printed pictures its own is nearest. the C is found from the ink between the rank and the
#time. a time is checked against its neighbours (times never go down as the ranks go up) and its pace (the time over
#52 km), a class rank against the ranks before it in its class
#
#example usage:
#python -m old_results_parsers.y1997 ocr          the strips' OCR, 4 tesseracts at once (kept in old_results/ocr/1997/)
#python birkie_archive.py parse --years 1997      the results into old_results/1997/
import concurrent.futures
import functools
import json
import os
import re
import subprocess
import sys

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage

from birkie_archive import OCR_DIR, PAGE_DIR, TESSERACT, OUT_COLUMNS, known_towns
from results_loader import load_all_results, compact, split_first_last, normalize_location, US_STATES, CA_PROVINCES

YEAR = 1997
LISTS = {'M': [28, 29, 30, 31] + list(range(36, 52)), 'F': [52, 53, 54, 55]}
#where each field's strip sits, in pixels from the left of the FINAL TIME column (the time's first digit)
STRIPS = {'rank': (-112, -47), 'time': (-6, 88), 'bib': (82, 152), 'name': (152, 638), 'pace': (938, 1004),
          'st': (634, 696), 'nat': (697, 752), 'class': (752, 836), 'crank': (834, 886)}
WHITELIST = {'rank': '0123456789', 'time': '0123456789:.', 'bib': '0123456789', 'pace': '0123456789.',
             'name': "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-'.& ",
             'st': 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'nat': 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'class': 'MF0123456789-+ ',
             'crank': '0123456789'}
#the names and towns are read four ways, voted on line by line: (strip, scale, whitelist)
NAME_READINGS = {'name_s4': ('name', 4, True), 'name': ('name', 3, True), 'name_s2': ('name', 2, True),
                 'name_nw': ('name', 3, False)}
STRIPS.update({k: STRIPS[strip] for k, (strip, _, _) in NAME_READINGS.items()})
#the strips are read with each line moved by its shift (the right hand columns lean), as <page>_<side>_<field>_v2.tsv;
#the ranks were read without (<page>_<side>_rank.tsv), which is enough to find a column's first rank
VERSION = {'rank': ''}
SCALE = 3
STACK = 40
MAX_TESSERACT = 4
#the HOMETOWN column starts here (a name ends by 410)
TOWN_EDGE = 425
NAME_CROP = (150, 430)
#glyph windows, from the time's left: the rank, the C (between the rank's right edge and the time), the bib, the
#pace's left edge, and the class's M or F, from which the class rank, state and nation are placed
RANK_INK = (-100, -46)
MARK = (-42, -10)
BIB = (87, 152)
PACE_LEFT = 957
CLASS_LEFT = 760
CRANK = (834, 886)
LETTERS = {'st': (632, 698), 'nat': (698, 754)}
#a time's six digits and its pace's three, as the centers of their cells from the time's (pace's) left edge, and the
#punctuation's
TIME_SLOTS = [3.75, 19.25, 29.75, 45.25, 55.75, 71.25]
TIME_PUNCT = [11.5, 37.5, 63.5]
PACE_SLOTS = [3.5, 19.0, 29.5]
PACE_PUNCT = [11.0]
#rows of page above and below a line's band
PAD = 12
DARK = 128
INK = 150
ADVANCE = 10.5
GLYPH = (22, 16)
DISTANCE_KM = 52
CLASSES = ['18-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', '65-69', '70-74', '75-79',
           '80-84']
PROVINCES = {'ONT': 'ON', 'QUE': 'QC', 'MAN': 'MB', 'SAS': 'SK', 'ALB': 'AB', 'BRC': 'BC', 'NFL': 'NL'}


def ocr_base(page, side=''):
    return os.path.join(OCR_DIR, str(YEAR), '{:03d}{}'.format(page, '_' + side if side else ''))


#---------------------------------------------------------------- each column upright, and its lines

@functools.lru_cache(maxsize=4)
def page_image(page):
    return np.asarray(Image.open(os.path.join(PAGE_DIR, str(YEAR), '{:03d}.png'.format(page))).convert('L'))


@functools.lru_cache(maxsize=8)
def upright(page, angle):
    #the page turned by angle degrees (counterclockwise) about its center
    return np.asarray(Image.fromarray(page_image(page)).rotate(angle, resample=Image.BICUBIC, fillcolor=255))


def sharpness(dark, angle):
    #how crisply the lines of text separate when the ink is turned by angle: the summed squared change of the ink
    #per pixel row
    turned = Image.fromarray(dark.astype(np.uint8) * 255).rotate(angle, resample=Image.NEAREST, fillcolor=0)
    profile = np.asarray(turned, dtype=np.float32).sum(1)
    return float(np.sum(np.diff(profile) ** 2))


def best_angle(dark, low, high, step):
    angles = np.arange(low, high + step / 2, step)
    return float(angles[int(np.argmax([sharpness(dark, a) for a in angles]))])


def geometry(page):
    #each half page's turn, x range, FINAL TIME left and lines, kept as <page>_geom.json next to the OCR
    path = ocr_base(page) + '_geom.json'
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    image = page_image(page)
    dark = image < DARK
    body = dark[300:3250]
    coarse = best_angle(body[::4, ::4], -3, 3, 0.1)
    angle = best_angle(body[::2, ::2], coarse - 0.1, coarse + 0.1, 0.02)
    #the rule between the two columns
    turned = upright(page, angle) < DARK
    middle = turned[600:3000, 1100:1450].sum(0)
    rule = 1100 + int(np.argmax(middle))
    halves = []
    for side, (x0, x1) in (('L', (0, rule - 8)), ('R', (rule + 8, image.shape[1]))):
        a = best_angle(dark[300:3250, x0:x1][::2, ::2], angle - 0.4, angle + 0.4, 0.02)
        half = upright(page, a)[:, x0:x1] < DARK
        t0 = time_left(half)
        halves.append({'side': side, 'angle': a, 'x0': x0, 'x1': x1, 't0': t0, 'lines': text_lines(half, t0)})
    out = {'page': page, 'angle': angle, 'rule': rule, 'halves': halves}
    with open(path, 'w') as f:
        json.dump(out, f)
    return out


def time_left(half):
    #the FINAL TIME column's left edge: where the left-aligned columns (time, name, nation, class) all start
    profile = half[450:3150].mean(0)
    cum = np.concatenate([[0], np.cumsum(profile)])
    mean = lambda a, b: (cum[b] - cum[a]) / (b - a)
    best, best_x = -1, None
    for x in range(20, half.shape[1] - 1010):
        score = sum(mean(x + o, x + o + 12) - mean(x + o - 14, x + o - 2) for o in (0, 164, 706, 760))
        if score > best:
            best, best_x = score, x
    return int(best_x)


def text_lines(half, t0):
    #the results' lines, as (top, bottom) pixel rows: runs of ink in the time column, below the rule under the
    #headings, until a gap of several lines
    width = half[:, max(t0 - 100, 0):t0 + 1000].mean(1)
    rules = [y for y in range(250, 800) if width[y] > 0.6]
    start = max(rules) + 3 if rules else 400
    ink = half[:, t0 - 2:t0 + 84].sum(1)
    runs, y, n = [], start, len(ink)
    while y < n:
        if ink[y] >= 2:
            top = y
            while y < n and ink[y] >= 1:
                y += 1
            runs.append([top, y - 1])
        y += 1
    #pieces of one line (a dot, a stroke) joined, specks dropped
    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] <= 3:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    merged = [r for r in merged if r[1] - r[0] >= 7]
    if not merged:
        return []
    height = np.median([b - a + 1 for a, b in merged])
    pitch = np.median(np.diff([a for a, _ in merged])) if len(merged) > 1 else 2 * height
    lines = []
    for a, b in merged:
        #the end of the table: a gap of more than a line, a rule (the box of an ad below the results), or a line of
        #text much shorter than a result's (the "C = CLASSICAL" key)
        if lines and (a - lines[-1][0] > 1.7 * pitch or not 0.12 < width[a:b + 1].max() < 0.45):
            break
        k = max(1, int(round((b - a + 1 + 6) / (height + 6))))
        step = (b - a + 1) / k
        lines += [[int(round(a + i * step)), int(round(a + (i + 1) * step)) - 1] for i in range(k)]
    return lines


def line_left(band, t0):
    #where the time starts on one line, from t0: the leftmost tall glyph just about t0 (the C sits further left)
    sub = band[:, t0 - 14:t0 + 20] < INK
    labels, _ = ndimage.label(sub, structure=np.ones((3, 3)))
    xs = [s[1].start for s in ndimage.find_objects(labels) if s[0].stop - s[0].start >= 10]
    return min(xs) - 14 if xs else np.nan


@functools.lru_cache(maxsize=None)
def line_shifts(page, side):
    #how far each line's columns sit right of the half page's (the right hand pages lean, by up to 6 pixels at the
    #top and bottom of a column): the time's left edge, smoothed over nine lines
    half = next(h for h in geometry(page)['halves'] if h['side'] == side)
    gray = column_gray(page, half)
    lefts = pd.Series([line_left(band_of(gray, line), half['t0']) for line in half['lines']], dtype=float)
    smooth = lefts.rolling(9, center=True, min_periods=1).median().interpolate().bfill().ffill().fillna(0)
    return tuple(int(round(v)) for v in smooth)


def columns():
    #every column of results in order: (gender, page, half)
    return [(gender, page, half) for gender, pages in LISTS.items() for page in pages
            for half in geometry(page)['halves']]


def column_gray(page, half):
    return upright(page, half['angle'])[:, half['x0']:half['x1']]


def to_page(page, half, x, y):
    #a point of the upright half page back on the page image
    a = np.radians(half['angle'])
    h, w = page_image(page).shape
    cx, cy = w / 2, h / 2
    x = x + half['x0'] - cx
    y = y - cy
    #PIL turns counterclockwise by angle, so undo it clockwise
    return cx + x * np.cos(a) - y * np.sin(a), cy + x * np.sin(a) + y * np.cos(a)


#---------------------------------------------------------------- glyphs

def band_of(gray, line, pad=3):
    a, b = line
    return gray[a - pad:b + 1 + pad]


def line_ink(band, x0, x1, mid, small=False):
    #the ink between x0 and x1 (from the band's left) of the pieces whose middle row is within 6.5 rows of mid (the
    #line's middle), less the specks and punctuation (unless small, for fields with no punctuation, where a faint
    #digit can come apart in pieces), as a mask over the band; and the punctuation's middles
    x0 = max(x0, 0)
    sub = band[:, x0:x1] < INK
    labels, _ = ndimage.label(sub, structure=np.ones((3, 3)))
    keep, dots = [], []
    for j, s in enumerate(ndimage.find_objects(labels), 1):
        middle = (s[0].start + s[0].stop - 1) / 2 - mid
        if s[0].stop - s[0].start <= 7 and s[1].stop - s[1].start <= 7:
            #a colon's dots sit 4 rows either side of the middle, a period 7 below
            if -6.5 <= middle <= 9:
                dots.append((s[1].start + s[1].stop - 1) / 2 + x0)
            if small and abs(middle) <= 6.5:
                keep.append(j)
        elif abs(middle) <= 6.5:
            keep.append(j)
    mask = np.zeros(band.shape, bool)
    mask[:, x0:x1] = np.isin(labels, keep)
    #a digit is 17 rows tall: a speck touching it above or below is cut off
    mask[:max(int(round(mid - 9.5)), 0)] = False
    mask[int(round(mid + 10.5)):] = False
    return mask, dots


def box_of(mask, x0, x1):
    #the box of the mask's ink between x0 and x1, or None if it's too short to be a digit
    x0, x1 = max(int(x0), 0), max(int(x1), 0)
    ink = mask[:, x0:x1]
    rows, cols = np.where(ink.any(1))[0], np.where(ink.any(0))[0]
    if not len(rows) or rows.max() - rows.min() < 10:
        return None
    return [x0 + cols.min(), x0 + cols.max() + 1, rows.min(), rows.max() + 1]


def components(band, x0, x1, mid, blobs=None):
    #the digit boxes between x0 and x1 (from the band's left), left to right, as [left, right, top, bottom]: ink
    #pieces on the line overlapping in x joined, digits printed touching cut apart at the thinnest column near each
    #advance
    mask, _ = line_ink(band, x0, x1, mid, small=True)
    labels, _ = ndimage.label(mask, structure=np.ones((3, 3)))
    pieces = sorted([s[1].start, s[1].stop, s[0].start, s[0].stop] for s in ndimage.find_objects(labels))
    merged = []
    for c in pieces:
        if merged and min(c[1], merged[-1][1]) - max(c[0], merged[-1][0]) >= 0.5 * min(c[1] - c[0],
                                                                                       merged[-1][1] - merged[-1][0]):
            m = merged[-1]
            merged[-1] = [min(m[0], c[0]), max(m[1], c[1]), min(m[2], c[2]), max(m[3], c[3])]
        else:
            merged.append(c)
    out = []
    for c in merged:
        w = c[1] - c[0]
        k = max(1, int(round((w + 1) / ADVANCE)))
        if c[3] - c[2] < 11:
            continue
        cuts = [c[0]] + [thinnest(mask, c[0] + int(round(j * w / k))) for j in range(1, k)] + [c[1]]
        boxes = [box_of(mask, cuts[j], cuts[j + 1]) for j in range(k)]
        if blobs is not None and k > 1 and None not in boxes:
            blobs.append((len(out), c[0], c[1], k))
        out += boxes
    if blobs is not None:
        blobs.insert(0, mask)
    return [c for c in out if c is not None]


def thinnest(mask, x, reach=3):
    #the column within reach of x with the least ink, a column further from x counting half a pixel more per step:
    #where two touching digits meet (the inside of a 0 has as little ink as the join)
    cols = np.arange(max(x - reach, 1), min(x + reach, mask.shape[1] - 1) + 1)
    score = mask[:, cols].sum(0) + 0.5 * np.abs(cols - x)
    return int(cols[np.argmin(score)])


def cells(band, left, centers, punct, mid):
    #the digit boxes of a fixed format number (a time, a pace) starting at left, one per digit: each digit's cell
    #runs from the punctuation (or the thinnest column halfway) before it to the one after it, all moved by how far
    #the punctuation sits from where it should. the punctuation is left out, also where it touches a digit
    x0, x1 = int(left - 10), int(left + max(centers) + 16)
    mask, dots = line_ink(band, x0, x1, mid)
    shifts = [d - left - p for d in dots for p in punct if abs(d - left - p) <= 4]
    dx = float(np.median(shifts)) if shifts else 0.0
    edges = [x0]
    for a, b in zip(centers, centers[1:]):
        between = [p for p in punct if a < p < b]
        if between:
            edges += [left + dx + between[0] - 2, left + dx + between[0] + 3]
        else:
            cut = thinnest(mask, int(round(left + dx + (a + b) / 2)))
            edges += [cut, cut]
    edges.append(x1)
    boxes = [box_of(mask, edges[2 * j], edges[2 * j + 1]) for j in range(len(centers))]
    #the pairs of cells split at the thinnest column, for cutting again where the split reads badly
    pairs = [(j, edges[2 * j], edges[2 * j + 1], edges[2 * j + 3]) for j in range(len(centers) - 1)
             if edges[2 * j + 1] == edges[2 * j + 2]]
    return boxes, (mask, pairs)


def feature(band, box):
    x0, x1, y0, y1 = box
    crop = 1 - band[y0:y1, x0:x1].astype(np.float32) / 255
    canvas = np.zeros(GLYPH, np.float32)
    h, w = min(crop.shape[0], GLYPH[0]), min(crop.shape[1], GLYPH[1])
    ox = (GLYPH[1] - w) // 2
    canvas[:h, ox:ox + w] = crop[:h, :w]
    return canvas.ravel()



#---------------------------------------------------------------- ranks, and the digits they label

def has_ink(band, x0, x1, mid, min_height=11):
    #a mark at least min_height pixels tall on the line between x0 and x1
    mask, _ = line_ink(band, x0, x1, mid)
    rows = np.where(mask.any(1))[0]
    return bool(len(rows)) and rows.max() - rows.min() + 1 >= min_height


def line_bands(page, half):
    #each line's band of the upright half page, PAD rows above and below it, and its middle row in the band
    gray = column_gray(page, half)
    return [band_of(gray, line, PAD) for line in half['lines']], [PAD + (b - a) / 2 for a, b in half['lines']]


@functools.lru_cache(maxsize=None)
def column_ranks():
    #{(page, side): [rank or None for each line]}: the ranks count up by one down a column, so a column's are its
    #first rank (the one most of its OCR'd ranks agree on) plus the ranked lines above. a line with no ink where the
    #rank goes has none. each column must start where the one before it ended
    out, expected = {}, {}
    for gender, page, half in columns():
        bands, mids = line_bands(page, half)
        t0s = [half['t0'] + d for d in line_shifts(page, half['side'])]
        ranked = [has_ink(band, t0 + RANK_INK[0], t0 + RANK_INK[1], mid) for band, mid, t0 in zip(bands, mids, t0s)]
        index = np.cumsum(ranked) - 1
        votes = {}
        for i, words in enumerate(strip_lines(page, half, 'rank')):
            text = ''.join(t for t, _, _, _ in words)
            if ranked[i] and text.isdigit():
                votes[int(text) - index[i]] = votes.get(int(text) - index[i], 0) + 1
        start = max(votes, key=votes.get)
        if start != expected.get(gender, 1):
            raise ValueError('page {} {} starts at rank {}, not {}'.format(page, half['side'], start,
                                                                         expected.get(gender, 1)))
        expected[gender] = start + sum(ranked)
        out[(page, half['side'])] = [int(start + k) if r else None for r, k in zip(ranked, index)]
    return out


@functools.lru_cache(maxsize=None)
def digit_samples():
    #the rank digits' glyphs (features) and what they are, from every line whose rank splits into as many glyphs as
    #it has digits
    feats, labels, pages = [], [], []
    ranks = column_ranks()
    for gender, page, half in columns():
        bands, mids = line_bands(page, half)
        for band, mid, rank, d in zip(bands, mids, ranks[(page, half['side'])], line_shifts(page, half['side'])):
            if rank is None:
                continue
            t0 = half['t0'] + d
            boxes = components(band, t0 + RANK_INK[0], t0 + RANK_INK[1], mid)
            if len(boxes) == len(str(rank)):
                feats += [feature(band, b) for b in boxes]
                labels += list(str(rank))
                pages += [page] * len(boxes)
    return np.array(feats, np.float32), np.array(labels), np.array(pages)


class Digits:
    #the nearest samples' vote for each glyph, with the runner up and how sure the vote is
    def __init__(self, feats, labels, pages, k=3):
        self.feats, self.labels, self.pages, self.k = feats, labels, pages, k
        self.norms = (feats ** 2).sum(1)

    def read(self, feats, exclude=None):
        feats = np.asarray(feats, np.float32)
        out = []
        for i in range(0, len(feats), 2000):
            chunk = feats[i:i + 2000]
            d = self.norms[None, :] - 2 * chunk @ self.feats.T + (chunk ** 2).sum(1)[:, None]
            if exclude is not None:
                d[:, exclude] = np.inf
            near = np.argpartition(d, 12, axis=1)[:, :12]
            for row, idx in zip(d, near):
                idx = idx[np.argsort(row[idx])]
                votes = {}
                for j in idx[:self.k]:
                    votes[self.labels[j]] = votes.get(self.labels[j], 0) + 1
                best = max(votes, key=lambda c: (votes[c], -row[idx[[self.labels[j] == c for j in idx]][0]]))
                other = next((self.labels[j] for j in idx if self.labels[j] != best), '')
                d_best = row[idx[0]]
                d_other = next((row[j] for j in idx if self.labels[j] != best), np.inf)
                out.append((best, other, votes[best], float(np.sqrt(max(d_best, 0))),
                            float(np.sqrt(max(d_other, 0)))))
        return out


@functools.lru_cache(maxsize=None)
def digit_model():
    return Digits(*digit_samples())


#---------------------------------------------------------------- each line's numbers, glyph by glyph

def smooth(values, window=9):
    #a running median down the column, gaps filled from the lines around them
    out = pd.Series(values, dtype=float).rolling(window, center=True, min_periods=1).median()
    return out.interpolate().bfill().ffill().fillna(0).tolist()


def letter_widths(band, x0, x1, mid):
    #the widths of the letters between x0 and x1, left to right: an I is 2 to 4 pixels wide, every other letter 9 or
    #more. pieces less than 11 rows tall are specks
    mask, _ = line_ink(band, x0, x1, mid)
    labels, _ = ndimage.label(mask, structure=np.ones((3, 3)))
    boxes = sorted([s[1].start, s[1].stop] for s in ndimage.find_objects(labels) if s[0].stop - s[0].start >= 11)
    merged = []
    for a, b in boxes:
        if merged and a < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [b - a for a, b in merged]


def narrow_letters(band, t0, mid):
    #the middles of the I's (letters 2 to 5 pixels wide and full height) in the name and town, from t0
    mask, _ = line_ink(band, t0 + STRIPS['name'][0], t0 + STRIPS['name'][1], mid)
    labels, _ = ndimage.label(mask, structure=np.ones((3, 3)))
    return [(s[1].start + s[1].stop - 1) / 2 - t0 for s in ndimage.find_objects(labels)
            if s[0].stop - s[0].start >= 15 and s[1].stop - s[1].start <= 5]


def field_image(band, x0, x1, mid, size=(21, 56)):
    #a field's ink as a picture of the given size, from its first inked column, for comparing whole fields
    mask, _ = line_ink(band, x0, x1, mid)
    cols = np.where(mask.any(0))[0]
    out = np.zeros(size, np.float32)
    if len(cols):
        top = int(round(mid)) - size[0] // 2
        crop = 1 - band[max(top, 0):top + size[0], cols[0]:cols[0] + size[1]].astype(np.float32) / 255
        crop = crop * mask[max(top, 0):top + size[0], cols[0]:cols[0] + size[1]]
        out[:crop.shape[0], :crop.shape[1]] = crop
    return out.ravel()


def own_or_smooth(values):
    #each line's own value, or where it has none the running median's
    smoothed = smooth(values)
    return [s if np.isnan(v) else v for v, s in zip(values, smoothed)]


def middle_offset(band, x0, x1, mid):
    #how far below mid the middles of the tall glyphs between x0 and x1 sit, looking up to 10 rows either way
    labels, _ = ndimage.label(band[:, x0:x1] < INK, structure=np.ones((3, 3)))
    middles = [(s[0].start + s[0].stop - 1) / 2 for s in ndimage.find_objects(labels) if 11 <= s[0].stop - s[0].start <= 19]
    middles = [m for m in middles if abs(m - mid) <= 10]
    return float(np.median(middles)) - mid if middles else np.nan


def read_column(gender, page, half):
    #each line's rank, C and the glyphs of its time, bib, class rank and pace, as {field: [box or None]}. the right
    #hand end of a line can sit a few pixels off its left end (and a column's paces, on one page, 8 pixels lower and 5
    #to the right), so the class rank and pace are placed by where the class and pace sit, smoothed over nine lines
    bands, mids = line_bands(page, half)
    ranks = column_ranks()[(page, half['side'])]
    t0s = [half['t0'] + d for d in line_shifts(page, half['side'])]
    drop_class = own_or_smooth([middle_offset(b, t0 + 740, t0 + 900, m) for b, m, t0 in zip(bands, mids, t0s)])
    drop_pace = own_or_smooth([middle_offset(b, t0 + PACE_LEFT - 30, t0 + PACE_LEFT + 55, m) for b, m, t0 in
                               zip(bands, mids, t0s)])
    right = []
    for band, mid, t0, d in zip(bands, mids, t0s, drop_pace):
        boxes = components(band, t0 + PACE_LEFT - 30, t0 + PACE_LEFT + 55, mid + d)
        right.append(boxes[0][0] - t0 - PACE_LEFT if boxes else np.nan)
    right = [int(round(v)) for v in smooth(right)]
    #and the class column by where its M or F starts
    shift = []
    for band, mid, t0, d in zip(bands, mids, t0s, drop_class):
        boxes = components(band, t0 + CLASS_LEFT - 15, t0 + CLASS_LEFT + 30, mid + d)
        shift.append(boxes[0][0] - t0 - CLASS_LEFT if boxes else np.nan)
    shift = [int(round(v)) for v in smooth(shift)]
    rows = []
    for i, (line, rank, band, mid, t0, r) in enumerate(zip(half['lines'], ranks, bands, mids, t0s, right)):
        x, y = to_page(page, half, t0, line[0])
        time = cells(band, t0, TIME_SLOTS, TIME_PUNCT, mid)
        bib, crank = [], []
        pace = cells(band, t0 + PACE_LEFT + r, PACE_SLOTS, PACE_PUNCT, mid + drop_pace[i])
        rows.append({'gender': gender, 'page': page, 'side': half['side'], 'line': i, 'top': int(round(y)),
                     'rank': rank, 'classic': has_ink(band, t0 + MARK[0], t0 + MARK[1], mid), 'right': r,
                     'glyphs': {'time': time[0], 'bib': components(band, t0 + BIB[0], t0 + BIB[1], mid, bib),
                                'crank': components(band, t0 + shift[i] + CRANK[0], t0 + shift[i] + CRANK[1],
                                                    mid + drop_class[i], crank),
                                'pace': pace[0]},
                     'splits': {'time': time[1], 'pace': pace[1]}, 'blobs': {'bib': bib, 'crank': crank},
                     'letters': {f: letter_widths(band, t0 + shift[i] + a, t0 + shift[i] + b, mid + drop_class[i])
                                 for f, (a, b) in LETTERS.items()},
                     'st_image': field_image(band, t0 + shift[i] + LETTERS['st'][0], t0 + shift[i] + LETTERS['st'][1],
                                             mid + drop_class[i]),
                     'narrow': narrow_letters(band, t0, mid),
                     'name_crop': band[int(mid) - 11:int(mid) + 12, t0 + NAME_CROP[0]:t0 + NAME_CROP[1]].copy(),
                     'band': band})
    return rows


def read_numbers(rows):
    #every glyph read by the digit model: each field becomes a list of (digit, runner up, sure, distance to the
    #nearest sample, distance to the nearest other digit's) or None for a missing glyph. two touching digits whose
    #split reads badly (a glyph far from every sample) are cut again where the two read best
    feats, where = [], []
    for r in rows:
        for field, boxes in r['glyphs'].items():
            for j, box in enumerate(boxes):
                if box is not None:
                    feats.append(feature(r['band'], box))
                    where.append((r, field, j))
    reads = digit_model().read(feats) if feats else []
    for r in rows:
        r['digits'] = {field: [None] * len(boxes) for field, boxes in r['glyphs'].items()}
    for (r, field, j), (best, other, votes, d_best, d_other) in zip(where, reads):
        r['digits'][field][j] = (best, other, votes == 3 and d_other - d_best > 0.5, d_best, d_other)
    recut(rows)
    resplit(rows)
    for r in rows:
        del r['band'], r['splits'], r['blobs']
    return rows


def resplit(rows, suspect=3.2, reach=4):
    #a bib or class rank's touching digits that read badly are split again where they read best: every way of
    #moving each cut up to reach pixels, the one whose glyphs are nearest their samples in all
    model = digit_model()
    for r in rows:
        for field, blobs in r['blobs'].items():
            if not blobs:
                continue
            mask, digits = blobs[0], r['digits'][field]
            for first, x0, x1, k in blobs[1:]:
                if all(d and d[3] <= suspect for d in digits[first:first + k]):
                    continue
                even = [x0 + int(round(j * (x1 - x0) / k)) for j in range(1, k)]
                options = [[x0]] + [list(range(e - reach, e + reach + 1)) for e in even] + [[x1]]
                segments = sorted({(a, b) for j in range(k) for a in options[j] for b in options[j + 1] if b - a >= 3})
                boxes = {seg: box_of(mask, *seg) for seg in segments}
                segments = [seg for seg in segments if boxes[seg] is not None]
                if not segments:
                    continue
                reads = dict(zip(segments, model.read([feature(r['band'], boxes[seg]) for seg in segments])))
                #the best path through the cuts
                best = {x0: (0.0, [])}
                for j in range(k):
                    nxt = {}
                    for a, (cost, path) in best.items():
                        for b in options[j + 1]:
                            if (a, b) in reads and (b not in nxt or cost + reads[(a, b)][3] < nxt[b][0]):
                                nxt[b] = (cost + reads[(a, b)][3], path + [reads[(a, b)]])
                    best = nxt
                if x1 not in best:
                    continue
                cost, path = best[x1]
                if cost < sum(d[3] if d else 2 * suspect for d in digits[first:first + k]):
                    for n, (d, other, votes, d_best, d_other) in enumerate(path):
                        digits[first + n] = (d, other, votes == 3 and d_other - d_best > 0.5, d_best, d_other)


def recut(rows, suspect=3.0, reach=6):
    feats, where = [], []
    for r in rows:
        for field, (mask, pairs) in r['splits'].items():
            digits = r['digits'][field]
            for j, left, cut, right in pairs:
                if all(digits[k] and digits[k][3] <= suspect for k in (j, j + 1)):
                    continue
                for c in range(cut - reach, cut + reach + 1):
                    boxes = [box_of(mask, left, c), box_of(mask, c, right)]
                    if None not in boxes:
                        feats += [feature(r['band'], b) for b in boxes]
                        where.append((r, field, j, c))
    if not feats:
        return
    reads = digit_model().read(feats)
    best = {}
    for n, (r, field, j, c) in enumerate(where):
        a, b = reads[2 * n], reads[2 * n + 1]
        key = (id(r), field, j)
        score = a[3] + b[3]
        if key not in best or score < best[key][0]:
            best[key] = (score, r, a, b)
    for (_, field, j), (score, r, a, b) in best.items():
        digits = r['digits'][field]
        old = sum(digits[k][3] if digits[k] else 2 * suspect for k in (j, j + 1))
        if score < old:
            for k, (d, other, votes, d_best, d_other) in zip((j, j + 1), (a, b)):
                digits[k] = (d, other, votes == 3 and d_other - d_best > 0.5, d_best, d_other)


#---------------------------------------------------------------- the results

def parse(year=YEAR):
    #every finisher in the men's and women's lists, in the order printed
    df = results()
    return df[[c for c in OUT_COLUMNS if c in df.columns]]


def results():
    #the results with the readings behind them
    rows = []
    for gender, page, half in columns():
        texts = {f: strip_lines(page, half, f) for f in STRIPS if f != 'rank'}
        for r in read_numbers(read_column(gender, page, half)):
            rows.append(record(r, {f: lines[r['line']] for f, lines in texts.items()}))
    df = pd.DataFrame(rows)
    df['name'] = letter_initials(df)
    df['country'] = repair_nations(df['country'])
    df['state'] = [repair_state(s, c, n) for s, c, n in zip(df['state'], df['city'], df['country'])]
    df['state'] = states_by_picture(df)
    df['city'] = [vote_town(t, s, c) for t, s, c in zip(df['towns'], df['state'], df['country'])]
    df = pd.concat([repair_times(lst) for _, lst in df.groupby('gender', sort=False)])
    df = pd.concat([repair_classes(lst) for _, lst in df.groupby('gender', sort=False)])
    df['place'] = df['place'].map(lambda p: '' if pd.isna(p) else str(int(p)))
    df['time'] = df['seconds'].map(hms)
    return df.assign(status='finished')


def number(digits):
    #a glyph by glyph reading as text, '?' for a glyph that couldn't be read
    return ''.join(d[0] if d else '?' for d in digits)


def tess_digits(words):
    return re.sub(r'\D', '', ''.join(t for t, _, _, _ in words))


def record(r, words):
    #one line's result, from its glyphs and its strips' words
    names = [clean_words(with_last_i([w for w in words[f] if w[1] < TOWN_EDGE], r['narrow'])) for f in NAME_READINGS]
    towns = [clean_words(with_last_i([w for w in words[f] if w[1] >= TOWN_EDGE], r['narrow'])) for f in NAME_READINGS]
    group, cls = read_class(' '.join(t for t, _, _, _ in words['class']), r['gender'])
    crank = read_count(r['digits']['crank'], tess_digits(words['crank']))
    if '999' in crank and len(crank) >= 3 and int(crank) > 990:
        #NO AGE, class rank 9999
        group, crank = (), ''
    time = number(r['digits']['time'])
    pace = number(r['digits']['pace'])
    name = vote_name(names)
    return {'place': r['rank'], 'gender': r['gender'], 'page': r['page'], 'top': r['top'],
            'tech': 'classic' if r['classic'] else 'skate',
            'bib': read_count(r['digits']['bib'], tess_digits(words['bib'])),
            'name': name, 'names': names, 'city': towns[0], 'towns': towns,
            'initials': initials(r, words[list(NAME_READINGS)[names.index(name)]]) if name else [],
            'state': with_narrow(letters_of(words['st']), r['letters']['st']),
            'state_sure': min([c for _, _, c, _ in words['st']] or [0]) >= 90 and len(r['letters']['st']) == 2,
            'st_image': r['st_image'],
            'country': with_narrow(letters_of(words['nat']), r['letters']['nat'])[:3],
            'classes': group, 'class_text': cls,
            'class_rank': crank,
            'time_glyphs': r['digits']['time'], 'time_tess': tess_digits(words['time']),
            'seconds': seconds(time), 'pace': pace_seconds(pace)}


@functools.lru_cache(maxsize=None)
def known():
    #the first and last names, and the (town, state)s, in the clean results
    clean = load_all_results()
    return (frozenset(clean['first'].map(compact)), frozenset(clean['last'].map(compact)),
            frozenset(zip(clean['city'], clean['state'])))


def initials(r, words):
    #the name's one letter words after the first (its middle initials), as (word number, text, picture)
    out, n = [], 0
    for text, left, _, right in words:
        if left >= TOWN_EDGE:
            continue
        text = clean_words([text])
        if not text:
            continue
        if n and len(text) == 1:
            crop = r['name_crop'][:, max(int(left) - NAME_CROP[0] - 2, 0):max(int(right) - NAME_CROP[0] + 2, 0)]
            mask = crop < INK
            cols, rows = np.where(mask.any(0))[0], np.where(mask.any(1))[0]
            if len(cols) and len(rows):
                glyph = 1 - crop[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1].astype(np.float32) / 255
                canvas = np.zeros((22, 20), np.float32)
                h, w = min(glyph.shape[0], 22), min(glyph.shape[1], 20)
                canvas[:h, (20 - w) // 2:(20 - w) // 2 + w] = glyph[:h, :w]
                out.append((n, text, canvas.ravel()))
        n += 1
    return out


def letter_initials(df, k=3):
    #every reading gives some middle initials as a digit (D as 0, B as 8, H as 4, L as 1): such an initial is the
    #letter of the initials every reading reads as letters whose pictures are nearest it, when its k nearest agree
    samples = [(text, image) for found, names in zip(df['initials'], df['names']) if len(set(names)) == 1
               for _, text, image in found if text.isalpha()]
    if not samples:
        return df['name']
    labels = np.array([t for t, _ in samples])
    images = np.stack([i for _, i in samples])
    out = []
    for name, found in zip(df['name'], df['initials']):
        words = name.split()
        for n, text, image in found:
            if text.isdigit() and n < len(words) and words[n] == text:
                near = labels[np.argsort(((images - image) ** 2).sum(1))[:k]]
                if len(set(near)) == 1:
                    words[n] = near[0]
        out.append(' '.join(words))
    return out


def vote_name(readings):
    #the name tesseract's readings give: the one whose last and first names are known from the clean results, then
    #the one with no digits (a D read as 0, specks read as numbers), then the one most readings give, then the first
    #reading's
    readings = [r for r in readings if r]
    if not readings:
        return ''
    firsts, lasts, _ = known()

    def score(name):
        first, last = [compact(n) for n in np.array(split_first_last(name))[[0, 2]]]
        return (2 * (last in lasts and last != '') + (first in firsts and first != ''),
                -len(re.findall(r'\d', name)), readings.count(name))
    return max(readings, key=score)


def vote_town(readings, state, country):
    #the same for the town: the reading that is a known town in its state, then the most common
    readings = [r for r in readings if r]
    if not readings:
        return ''
    cities = known()[2]
    return max(readings, key=lambda t: ((normalize_location(t, state, country)[0], state) in cities,
                                        readings.count(t)))


def read_count(glyphs, tess):
    #a bib or class rank: the glyphs' reading, unless a glyph couldn't be read and tesseract's reading has as many
    #digits
    text = number(glyphs)
    if '?' in text and len(tess) == len(text):
        text = ''.join(t if g == '?' else g for g, t in zip(text, tess))
    return text.lstrip('0') if text and '?' not in text else ''


def seconds(text):
    #h:mm:ss.t from its six digits, minutes and seconds under 60
    if not re.fullmatch(r'\d{6}', text) or int(text[1:3]) > 59 or int(text[3:5]) > 59:
        return np.nan
    return int(text[0]) * 3600 + int(text[1:3]) * 60 + int(text[3:5]) + int(text[5]) / 10


def hms(s):
    if pd.isna(s):
        return ''
    tenths = int(round(s * 10))
    return '{}:{:02d}:{:02d}.{}'.format(tenths // 36000, tenths // 600 % 60, tenths // 10 % 60, tenths % 10)


def pace_seconds(text):
    #the pace, minutes.seconds per km, in seconds
    if not re.fullmatch(r'\d{3}', text) or int(text[1:]) > 59:
        return np.nan
    return int(text[0]) * 60 + int(text[1:])


def pace_fits(s, pace):
    #the pace printed is the time over the 52 km, cut to the second
    return not np.isnan(pace) and int(s // DISTANCE_KM) == pace


def with_last_i(words, narrow):
    #tesseract drops an I at the end of a word ("GRABOWSK" for GRABOWSKI, the word's box still taking it in): a word
    #that ends with an I's ink, but not with an I, gets it back
    out = []
    for n, (text, left, _, right) in enumerate(words):
        following = words[n + 1][1] if n + 1 < len(words) else np.inf
        if any(right - 5 <= x <= right + 7 and x < following for x in narrow) and re.search(r'[A-HJ-Za-hj-z]$', text):
            text += 'I'
        out.append(text)
    return out


def clean_words(words):
    out = []
    for w in words:
        w = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9.]+$", '', w.upper())
        if w:
            out.append(w)
    return ' '.join(out)


def letters_of(words):
    return re.sub(r'[^A-Z]', '', ''.join(t for t, _, _, _ in words).upper())


def with_narrow(text, widths):
    #tesseract drops most of the I's in the state and nation columns ("W" for WI, "L" for IL, "SU" for SUI), or reads
    #them as the letter before ("MM" for MI): an I goes back in wherever a letter is 2 to 4 pixels wide
    narrow = [w <= 5 for w in widths]
    if len(text) == len(narrow):
        #one letter for each: an I wherever the letter is narrow ("LA" for IA)
        return ''.join('I' if n else c for c, n in zip(text, narrow))
    if text.count('I') >= sum(narrow):
        return text
    letters = [c for c in text if c != 'I']
    wide = len(narrow) - sum(narrow)
    if wide != len(letters) and not (0 < wide < len(letters) and len(set(letters)) == 1):
        return text
    letters = iter(letters)
    return ''.join('I' if n else next(letters) for n in narrow)


def repair_state(state, city, country):
    #the Canadian provinces as two letters. a state that isn't one, for a skier from the US or Canada, is the state
    #it could be (its letters in order, less or plus an I) whose towns include this one, when only one is; or the
    #only state it could be
    state = PROVINCES.get(state, state)
    valid = US_STATES | CA_PROVINCES
    if not state or state in valid or country not in ('USA', 'CAN', ''):
        return state
    letters = state.replace('I', '')
    could = {s for s in valid if subsequence(s, state) or subsequence(letters, s)}
    towns = {s for s in could if (compact(city), s) in known_towns()}
    if len(towns) == 1:
        return towns.pop()
    return could.pop() if len(could) == 1 else state


def states_by_picture(df, k=3):
    #a US or Canadian skier's state that still isn't one, read as the state whose printed pictures (where tesseract
    #read a two letter state with confidence) its own picture is nearest, when its k nearest all agree
    valid = US_STATES | CA_PROVINCES
    sure = df['state_sure'] & df['state'].isin(valid)
    todo = ~df['state'].isin(valid) & df['country'].isin(['USA', 'CAN', ''])
    if not sure.any() or not todo.any():
        return df['state']
    samples = np.stack(df.loc[sure, 'st_image'].values)
    labels = df.loc[sure, 'state'].values
    out = df['state'].copy()
    for i in df.index[todo]:
        image = df.at[i, 'st_image']
        if not image.any():
            continue
        d = ((samples - image) ** 2).sum(1)
        near = labels[np.argsort(d)[:k]]
        if len(set(near)) == 1:
            out[i] = near[0]
    return out


def subsequence(short, long):
    it = iter(long)
    return all(c in it for c in short)


def repair_nations(nations):
    #a nation read with one letter wrong ("JSA", "GEA") is the one nation, of those printed at least twice, it is one
    #letter from
    counts = nations.value_counts()
    common = set(counts[counts >= 2].index) - {''}
    out = []
    for n in nations:
        near = {c for c in common if len(c) == len(n) and sum(a != b for a, b in zip(c, n)) == 1}
        out.append(near.pop() if n and n not in common and len(near) == 1 else n)
    return out


def read_class(text, gender):
    #the classes ("M 25-29") the class strip can be: the one it reads, or where one bound is misread every class the
    #other bound fits. none for a skier with no age ("NO AGE", class rank 9999)
    t = re.sub(r'\s', '', text.upper())
    if 'AGE' in t or 'NO' in t:
        return (), text
    m = re.search(r'(\d\d)-(\d\d)', t) or re.search(r'(\d\d)-(\d)?', t) or re.search(r'(\d?\d)-?(\d\d)', t)
    if not m:
        return tuple(gender + ' ' + c for c in CLASSES), text
    low, high = m.group(1), m.group(2) or '_'
    if low + '-' + high in CLASSES:
        return (gender + ' ' + low + '-' + high,), text
    return tuple(gender + ' ' + c for c in CLASSES if c.startswith(low + '-') or c.endswith('-' + high)), text


#---------------------------------------------------------------- checks against the table

def rising(values):
    #which of the values (nan for none) are in the longest run that never goes down
    idx = [i for i, v in enumerate(values) if not np.isnan(v)]
    tails, prev, ends = [], {}, []
    for i in idx:
        v = values[i]
        k = int(np.searchsorted([values[j] for j in ends], v, side='right'))
        prev[i] = ends[k - 1] if k else None
        if k == len(ends):
            ends.append(i)
        else:
            ends[k] = i
    keep = np.zeros(len(values), bool)
    i = ends[-1] if ends else None
    while i is not None:
        keep[i] = True
        i = prev[i]
    return keep


def time_candidates(glyphs, tess):
    #readings of a time other than the glyphs' best: each glyph's runner up, a glyph that couldn't be read as any
    #digit, and tesseract's reading
    best = [g[0] if g else '?' for g in glyphs]
    out = set()
    for j, g in enumerate(glyphs):
        for alt in ([g[1]] if g else list('0123456789')):
            if alt:
                out.add(''.join(best[:j] + [alt] + best[j + 1:]))
    if len(tess) == 6:
        out.add(tess)
    return {c for c in out if not np.isnan(seconds(c))}


def repair_times(lst):
    #the times never go down as the places go up, and the pace is the time over 52 km. a time that agrees with its
    #pace and with the others is an anchor; a time that is unreadable, out of order between the anchors around it,
    #or off its pace is replaced by the one other reading (a glyph's runner up, tesseract's) that fits between those
    #anchors and its pace, when there is exactly one. a time out of order with no such reading is dropped
    lst = lst.copy()
    secs = lst['seconds'].values.astype(float).copy()
    paces = lst['pace'].values.astype(float)
    fits = np.array([not np.isnan(s) and pace_fits(s, p) for s, p in zip(secs, paces)])
    anchor = fits & rising(np.where(fits, secs, np.nan))
    lst['time_repair'] = ''
    for i in range(len(lst)):
        before = secs[:i][anchor[:i]]
        after = secs[i + 1:][anchor[i + 1:]]
        low = before.max() if len(before) else 0
        high = after.min() if len(after) else np.inf
        s = secs[i]
        if not np.isnan(s) and low <= s <= high and (fits[i] or np.isnan(paces[i])):
            continue
        options = {c for c in time_candidates(lst['time_glyphs'].iloc[i], lst['time_tess'].iloc[i])
                   if low <= seconds(c) <= high and (np.isnan(paces[i]) or pace_fits(seconds(c), paces[i]))}
        if len({seconds(c) for c in options}) == 1:
            secs[i] = seconds(options.pop())
            lst.iloc[i, lst.columns.get_loc('time_repair')] = 'repaired'
        elif not np.isnan(s) and not low <= s <= high:
            secs[i] = np.nan
            lst.iloc[i, lst.columns.get_loc('time_repair')] = 'dropped'
    lst['seconds'] = secs
    return lst


def repair_classes(lst):
    #the class ranks count up by one within each class, in the order printed. a class that can't be read (or only
    #one of its bounds) is the one of those it could be whose last class rank so far is one less than its own, when
    #only one is
    lst = lst.copy()
    last, groups, ranks = {}, [], []
    lst['crank_read'] = lst['class_rank']
    for classes, text, rank, place in zip(lst['classes'], lst['class_text'], lst['class_rank'], lst['place']):
        rank = int(rank) if rank else None
        if not classes and re.search(r'\d', text):
            #neither bound reads as a class's
            classes = tuple(c for c in last if c[0] == lst['gender'].iloc[0])
        fit = [c for c in classes if rank is not None and last.get(c, 0) + 1 == rank]
        group = classes[0] if len(classes) == 1 else fit[0] if len(fit) == 1 else ''
        if group and not pd.isna(place):
            #(the man listed without a rank has no class rank either)
            last[group] = rank if rank is not None else last.get(group, 0) + 1
        groups.append(group)
        ranks.append('' if not group or rank is None else str(rank))
    lst['age_group'] = groups
    lst['class_rank'] = ranks
    #a class rank that couldn't be read, or doesn't follow the one before it, is the one between its neighbours in the
    #class when they are two apart
    for _, members in lst[lst['age_group'] != ''].groupby('age_group'):
        r = pd.to_numeric(members['class_rank'], errors='coerce').values
        for i in range(len(r)):
            before = r[i - 1] if i else 0
            after = r[i + 1] if i + 1 < len(r) else np.nan
            if r[i] != before + 1 and after == before + 2 and not np.isnan(after):
                r[i] = before + 1
                lst.loc[members.index[i], 'class_rank'] = str(int(r[i]))
    return lst

#---------------------------------------------------------------- tesseract, one field's strip at a time

def strip_scale(field):
    return NAME_READINGS[field][1] if field in NAME_READINGS else SCALE


def strip_path(page, side, field):
    return ocr_base(page, side) + '_' + field + VERSION.get(field, '_v2')


def read_strip(job):
    #one field's strip of a half page, its lines stacked STACK pixels apart, read at SCALE times the size (or the
    #name reading's scale) as <page>_<side>_<field>_v2.tsv
    page, half, field = job
    out = strip_path(page, half['side'], field)
    if os.path.exists(out + '.tsv'):
        return out
    gray = column_gray(page, half)
    a, b = STRIPS[field]
    shifts = line_shifts(page, half['side']) if VERSION.get(field, '_v2') else [0] * len(half['lines'])
    t0, margin = half['t0'], 12
    canvas = np.full((len(half['lines']) * STACK + 2 * margin, b - a + 2 * margin), 255, np.uint8)
    for i, (y0, y1) in enumerate(half['lines']):
        band = gray[y0 - 3:min(y1 + 4, y0 - 3 + STACK - 4), t0 + shifts[i] + a:t0 + shifts[i] + b]
        canvas[margin + i * STACK:margin + i * STACK + band.shape[0], margin:margin + band.shape[1]] = band
    scale = strip_scale(field)
    image = Image.fromarray(canvas)
    image = image.resize((image.width * scale, image.height * scale), Image.LANCZOS)
    png = out + '.png'
    image.save(png)
    whitelist = NAME_READINGS[field][2] if field in NAME_READINGS else True
    chars = ['-c', 'tessedit_char_whitelist=' + WHITELIST['name' if field in NAME_READINGS else field]]
    subprocess.run([TESSERACT, png, out, '--psm', '6', '--dpi', str(300 * scale)] + (chars if whitelist else []) +
                   ['tsv'], capture_output=True)
    os.remove(png)
    return out


def strip_words(page, side, field, n_lines):
    #the strip's words, each with the line it sits on and its left in pixels from the FINAL TIME column
    words = pd.read_csv(strip_path(page, side, field) + '.tsv', sep='\t', quoting=3, dtype={'text': str},
                        keep_default_na=False)
    words = words[(words['level'] == 5) & (words['text'].str.strip() != '')].copy()
    scale = strip_scale(field)
    center = (words['top'] + words['height'] / 2) / scale - 12
    words['line'] = (center // STACK).astype(int)
    words['x'] = words['left'] / scale - 12 + STRIPS[field][0]
    words['x_end'] = (words['left'] + words['width']) / scale - 12 + STRIPS[field][0]
    return words[(words['line'] >= 0) & (words['line'] < n_lines)].sort_values(['line', 'left'])


def strip_lines(page, half, field):
    #each line's words in the strip: [[(text, left, conf, right)], ...]
    n = len(half['lines'])
    out = [[] for _ in range(n)]
    for w in strip_words(page, half['side'], field, n).itertuples():
        out[w.line].append((w.text, w.x, float(w.conf), w.x_end))
    return out


def ocr(year=YEAR, pages=None):
    #every strip of every page read, MAX_TESSERACT at a time
    pages = pages or [p for ps in LISTS.values() for p in ps]
    jobs = [(page, half, field) for page in pages for half in geometry(page)['halves'] for field in STRIPS]
    with concurrent.futures.ThreadPoolExecutor(MAX_TESSERACT) as pool:
        for n, out in enumerate(pool.map(read_strip, jobs), 1):
            if n % 20 == 0:
                print(n, 'of', len(jobs), out, flush=True)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
