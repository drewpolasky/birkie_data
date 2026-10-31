#1998: "Results by Burns Computer Services", one men's and one women's list, each placing classic and skate skiers
#together. the race was shortened to 23 km, so the times run from 50 minutes (printed m:ss) to a few hours (h:mm:ss),
#and the pace column is minutes per km. two results to a line:
#   RK, CL ("Y" for a classic skier), BIB, NAME, HOMETOWN (town and state), CO (nation), AGE, DIV. ("M35-39"),
#   DIV PL (class rank), DIV. TOTAL (finishers in the class), FINISH TIME, PACE
#every other row is shaded with a halftone that wrecks tesseract, so each page is cleaned of its dots and straightened
#first, then read four ways (two scales and filters, two page segmentation modes), and the name, hometown and bib
#columns are read again on their own (tesseract finds the narrow spaces after middle initials much better that way).
#the rows are found in the cleaned image, each OCR word goes to a row and column by its box, and each field is voted
#on, then checked against the table and the image: places count up by one down the list, times never go down, the
#pace is the time over 23 km rounded up, class ranks count up within a class, every row of a class shows the same
#class total, the age falls in the class, the gaps in a cell show how many words it holds, the width of a bib how many
#digits, and no two skiers share a bib
#
#example usage:
#python -m old_results_parsers.y1998 ocr          clean, straighten and OCR the results pages (4 tesseracts at once)
#python birkie_archive.py parse --years 1998      the results into old_results/1998/
import collections
import concurrent.futures
import functools
import itertools
import json
import os
import re
import subprocess
import sys

import numpy as np
import pandas as pd
from PIL import Image, ImageFilter
from scipy import ndimage

from birkie_archive import (OCR_DIR, PAGE_DIR, TESSERACT, DIGITS, LOOKALIKE, digits, known_towns, state_code,
                            OUT_COLUMNS)
from results_loader import load_all_results, compact, split_first_last, US_STATES, CA_PROVINCES

YEAR = 1998
MEN_PAGES = list(range(17, 25)) + list(range(29, 40))
WOMEN_PAGES = list(range(40, 44))
DISTANCE_KM = 23
SCRATCH = os.path.join('old_results', 'scratch', str(YEAR))
WORKERS = 4
#the OCR passes over each cleaned, straightened page: (suffix, scale, psm, filter)
PASSES = [('b2p6', 2, 6, 'blur'), ('b2p4', 2, 4, 'blur'), ('m1p6', 1, 6, 'median'), ('m1p4', 1, 4, 'median')]
#and single columns read on their own, the rest of the page blanked: (suffix, column, scale, psm, filter, whitelist)
STRIPS = [('nameb2', 'NAME', 2, 6, 'blur', ''), ('nameb3', 'NAME', 3, 6, 'blur', ''),
          ('townb2', 'HOMETOWN', 2, 6, 'blur', ''), ('townb3', 'HOMETOWN', 3, 6, 'blur', ''),
          ('bibb2', 'BIB', 2, 6, 'blur', '0123456789'), ('bibb3', 'BIB', 3, 6, 'blur', '0123456789')]
#how much a strip's reading counts against one page pass's, in its column
STRIP_WEIGHT = {'NAME': 2, 'HOMETOWN': 2, 'BIB': 1}
#what a name or a town seen in the clean results adds to a reading's weight
KNOWN_NAME = 1.0
KNOWN_TOWN = 1.5
#what fitting the words seen in the cell adds
IMAGE_FIT = 3
#column headings, and where each column's cells start, measured from the left of the RK heading (page 29)
HEADINGS = {'RK': 0, 'CL': 47, 'BIB': 99, 'NAME': 156, 'HOMETOWN': 419, 'CO': 664, 'AGE': 730, 'DIV.': 787,
            'PL': 872, 'TOTAL': 906, 'TIME': 983, 'PACE': 1044}
COLUMNS = [('RK', -25), ('CL', 47), ('BIB', 75), ('NAME', 149), ('HOMETOWN', 413), ('CO', 658), ('AGE', 720),
           ('DIV', 775), ('PL', 863), ('TOTAL', 915), ('TIME', 965), ('PACE', 1045)]
ROW_END = 1110
HALF_WIDTH = 1150
#the narrowest gap between words in a cell, in pixels (the gaps between letters are 1 to 3, between words 5 to 9)
WORD_GAP = 5
#a word narrower than this (pixels) is one letter: an initial is 8 to 18 wide, two letters mostly 20 or more
NARROW = 19


def column_weights(col):
    #each reading's weight in a column: the page passes', then its strips'
    return [1] * len(PASSES) + [STRIP_WEIGHT[col] for _, c, _, _, _, _ in STRIPS if c == col]


#---------------------------------------------------------------- images and OCR

def skew(ink, step=0.02, span=3.0):
    #the angle (degrees) whose sheared row sums vary the most: the rows of the tables lined up
    small = ink[::2, ::2]
    h, w = small.shape
    ys, xs = np.nonzero(small)
    best = None
    for a in np.arange(-span, span + step / 2, step):
        y = np.round(ys - xs * np.tan(np.radians(a))).astype(int) + w
        v = (np.bincount(y, minlength=h + 2 * w).astype(float) ** 2).sum()
        if best is None or v > best[0]:
            best = (v, a)
    return round(float(best[1]), 2)


def clean_page(page):
    #the shaded rows are a halftone of one to three pixel dots. a character's smallest piece (a colon's dot) is four
    #pixels or more. the page is then turned straight, so each row of the tables is level. the angle is kept, to put
    #rows back where they are on the page image
    path = os.path.join(SCRATCH, 'clean_{:03d}.png'.format(page))
    meta = os.path.join(SCRATCH, 'clean_{:03d}.json'.format(page))
    if not os.path.exists(path) or not os.path.exists(meta):
        os.makedirs(SCRATCH, exist_ok=True)
        ink = np.array(Image.open(os.path.join(PAGE_DIR, str(YEAR), '{:03d}.png'.format(page)))) < 128
        labels, _ = ndimage.label(ink, structure=np.ones((3, 3)))
        keep = np.bincount(labels.ravel()) > 3
        keep[0] = False
        ink = keep[labels]
        angle = skew(ink)
        image = Image.fromarray(np.where(ink, 0, 255).astype(np.uint8))
        if angle:
            image = image.rotate(angle, resample=Image.BICUBIC, fillcolor=255).point(lambda v: 0 if v < 128 else 255)
        image.save(path)
        with open(meta, 'w') as f:
            json.dump({'angle': angle, 'width': image.width, 'height': image.height}, f)
    return path


def page_meta(page):
    clean_page(page)
    with open(os.path.join(SCRATCH, 'clean_{:03d}.json'.format(page))) as f:
        return json.load(f)


def ocr_pass(page, suffix, scale, psm, filt):
    out = os.path.join(OCR_DIR, str(YEAR), '{:03d}_{}'.format(page, suffix))
    if os.path.exists(out + '.tsv'):
        return out
    image = Image.open(clean_page(page))
    if filt == 'median':
        image = image.filter(ImageFilter.MedianFilter(3))
    if scale != 1:
        image = image.resize((image.width * scale, image.height * scale), Image.BICUBIC)
    if filt == 'blur':
        image = image.filter(ImageFilter.GaussianBlur(0.7 * scale)).point(lambda v: 0 if v < 150 else 255)
    src = out + '.png'
    image.save(src)
    #written under another name and moved, so a pass cut short isn't taken for a finished one
    subprocess.run([TESSERACT, src, out + '_part', '--psm', str(psm), 'tsv'], capture_output=True)
    os.replace(out + '_part.tsv', out + '.tsv')
    os.remove(src)
    return out


def strip_bounds(page):
    #each half's (left, right) of each strip's column on the cleaned page, and the top of the tables. a name and a
    #hometown can run close together, so the edge between them is the faintest column of ink near where it should be
    words = {s: pass_words(page, s, scale) for s, scale, _, _ in PASSES}
    lefts, tops = header(page, words)
    ink = np.array(Image.open(clean_page(page))) < 128
    out = {}
    for half, (rk, top) in enumerate(zip(lefts, tops)):
        if np.isnan(rk):
            continue
        prof = np.convolve(ink[int(top + 40):, :].sum(0), np.ones(3), 'same')
        lo = int(rk + 385)
        split = lo + int(np.argmin(prof[lo:int(rk + 425)]))
        out[half] = {'BIB': (int(rk + 72), int(rk + 148)), 'NAME': (int(rk + 146), split + 2),
                     'HOMETOWN': (split - 2, int(rk + 652)), 'top': int(top + 30)}
    return out


def strip_pass(page, suffix, col, scale, psm, filt, whitelist):
    #one column of both halves read on its own, the rest of the page blanked: tesseract finds the spaces in a name
    #much better without the rest of the row beside it. the image keeps the cleaned page's size, so the boxes need
    #no moving
    out = os.path.join(OCR_DIR, str(YEAR), '{:03d}_{}'.format(page, suffix))
    if os.path.exists(out + '.tsv'):
        return out
    clean = np.array(Image.open(clean_page(page)))
    keep = np.full(clean.shape, 255, dtype=np.uint8)
    for b in strip_bounds(page).values():
        x0, x1 = b[col]
        keep[b['top']:, x0:x1] = clean[b['top']:, x0:x1]
    image = Image.fromarray(keep)
    if scale != 1:
        image = image.resize((image.width * scale, image.height * scale), Image.BICUBIC)
    if filt == 'blur':
        image = image.filter(ImageFilter.GaussianBlur(0.7 * scale)).point(lambda v: 0 if v < 150 else 255)
    src = out + '.png'
    image.save(src)
    args = [TESSERACT, src, out + '_part', '--psm', str(psm)]
    if whitelist:
        args += ['-c', 'tessedit_char_whitelist=' + whitelist]
    subprocess.run(args + ['tsv'], capture_output=True)
    os.replace(out + '_part.tsv', out + '.tsv')
    os.remove(src)
    return out


def ocr(year=YEAR):
    pages = MEN_PAGES + WOMEN_PAGES
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(clean_page, pages))
        jobs = [(p, *job) for job in PASSES for p in pages]
        list(pool.map(lambda j: ocr_pass(*j), jobs))
        jobs = [(p, *job) for job in STRIPS for p in pages]
        list(pool.map(lambda j: strip_pass(*j), jobs))


def pass_words(page, suffix, scale):
    #one pass's words, boxes in the cleaned page's pixels
    path = os.path.join(OCR_DIR, str(YEAR), '{:03d}_{}.tsv'.format(page, suffix))
    w = pd.read_csv(path, sep='\t', quoting=3, dtype={'text': str}, keep_default_na=False)
    w = w[(w['level'] == 5) & (w['text'].str.strip() != '')].copy()
    for c in ['left', 'top', 'width', 'height']:
        w[c] = w[c] / scale
    return w.reset_index(drop=True)


#---------------------------------------------------------------- the tables on a page

def header(page, words):
    #the left of each half's RK heading, from every heading any pass read, and the headings' line
    found = []
    for w in words.values():
        w = w[w['top'] < 700]
        for _, r in w.iterrows():
            t = r['text'].strip('_.,:;').upper()
            t = 'DIV.' if t == 'DIV' and r['text'].endswith('.') else t
            if t in HEADINGS and t not in ('DIV.', 'PL', 'TIME', 'TOTAL'):
                found.append((r['left'] - HEADINGS[t], r['top']))
    found = pd.DataFrame(found, columns=['rk', 'top'])
    lefts, tops = [], []
    for half in (0, 1):
        f = found[(found['rk'] >= half * HALF_WIDTH - 200) & (found['rk'] < (half + 1) * HALF_WIDTH - 200)]
        #the headings that agree with each other
        if len(f):
            m = f['rk'].median()
            f = f[(f['rk'] - m).abs() < 15]
        lefts.append(f['rk'].median() if len(f) else np.nan)
        tops.append(f['top'].median() if len(f) else np.nan)
    if np.isnan(lefts[0]) and not np.isnan(lefts[1]):
        lefts[0], tops[0] = lefts[1] - HALF_WIDTH, tops[1]
    if np.isnan(lefts[1]) and not np.isnan(lefts[0]):
        lefts[1], tops[1] = lefts[0] + HALF_WIDTH, tops[0]
    return lefts, tops


def row_bands(ink, rk, head_top):
    #each result's band of rows in one half: inked rows between the half's columns, below the headings, at the tables'
    #pitch (about 26 pixels). two rows run together are split at the faintest line between them
    x0, x1 = int(max(rk - 25, 0)), int(min(rk + ROW_END, ink.shape[1]))
    y0 = int(head_top + 40)
    prof = ink[y0:, x0:x1].sum(1)
    on = prof > 30
    bands, y = [], 0
    while y < len(on):
        if on[y]:
            s = y
            while y < len(on) and on[y]:
                y += 1
            bands.append([s, y])
        y += 1
    rows = []
    for s, e in bands:
        n = int(round((e - s + 6) / 26.3))
        if e - s < 10:
            continue
        if n > 1 and e - s <= 30 * n:
            #split at the faintest lines near each expected gap
            cuts = [s]
            for k in range(1, n):
                mid = s + k * (e - s) // n
                lo, hi = mid - 6, mid + 6
                cuts.append(lo + int(np.argmin(prof[lo:hi])))
            cuts.append(e)
            rows += [[a, b] for a, b in zip(cuts[:-1], cuts[1:])]
        else:
            rows.append([s, e])
    #the table: rows from just below the headings, at the pitch, until it breaks off
    out = []
    for s, e in rows:
        if not out:
            if s > 80 or e - s > 30:
                if s > 80:
                    break
                continue
            out.append((s, e))
        elif 21 <= s - out[-1][0] <= 32 and 10 <= e - s <= 30:
            out.append((s, e))
        else:
            break
    #a result has a name and a time (not the page number below the table)
    names = ink[y0:, int(rk + 149):int(rk + 300)]
    times = ink[y0:, int(rk + 965):int(min(rk + ROW_END, ink.shape[1]))]
    while out and (names[out[-1][0]:out[-1][1]].sum() < 30 or times[out[-1][0]:out[-1][1]].sum() < 30):
        out.pop()
    return [(s + y0, e + y0) for s, e in out]


def cells(words, bands, rk):
    #each word to its row (by its middle) and column (by its left), a word run across a column edge split there
    #in proportion to its width
    edges = [(c, rk + x) for c, x in COLUMNS]
    out = collections.defaultdict(list)
    if not bands:
        return out
    starts = np.array([s for s, _ in bands])
    ends = np.array([e for _, e in bands])
    w = words[(words['left'] + words['width'] / 2 >= rk - 30) & (words['left'] + words['width'] / 2 < rk + ROW_END)]
    for _, r in w.sort_values('left').iterrows():
        mid = r['top'] + r['height'] / 2
        i = np.nonzero((starts - 6 <= mid) & (mid <= ends + 6))[0]
        if not len(i):
            continue
        i = i[np.argmin(np.abs((starts[i] + ends[i]) / 2 - mid))]
        text, left, width = r['text'], r['left'], r['width']
        inside = [(c, x) for c, x in edges if left + 4 < x < left + width - 4]
        pieces, at = [], 0
        for c, x in inside:
            k = int(round((x - left) / width * len(text)))
            pieces.append((text[at:k], left + at / len(text) * width))
            at = k
        pieces.append((text[at:], left + at / len(text) * width))
        for piece, x in pieces:
            if piece.strip():
                col = [c for c, e in edges if x + 3 >= e]
                out[(i, col[-1] if col else 'RK')].append(piece)
    return out


def strip_cells(words, bands, rk):
    #a strip pass's words to their rows; the column is the strip's
    out = collections.defaultdict(list)
    if not bands:
        return out
    starts = np.array([s for s, _ in bands])
    ends = np.array([e for _, e in bands])
    w = words[(words['left'] + words['width'] / 2 >= rk - 30) & (words['left'] + words['width'] / 2 < rk + ROW_END)]
    for _, r in w.sort_values('left').iterrows():
        mid = r['top'] + r['height'] / 2
        i = np.nonzero((starts - 6 <= mid) & (mid <= ends + 6))[0]
        if len(i):
            out[int(i[np.argmin(np.abs((starts[i] + ends[i]) / 2 - mid))])].append(r['text'])
    return out


def image_words(ink, x0, x1, y0, y1, gap=WORD_GAP, height=10):
    #the words in a cell, as (left, right) on the cleaned page: runs of inked columns at least WORD_GAP blank columns
    #apart. specks, dots (less than height pixels high) and rules (under four pixels wide) are skipped
    prof = ink[y0:y1, x0:x1].sum(0)
    cols = np.nonzero(prof)[0]
    out = []
    if not len(cols):
        return out
    start = prev = cols[0]
    for c in list(cols[1:]) + [None]:
        if c is None or c - prev - 1 >= gap:
            rows = np.nonzero(ink[y0:y1, x0 + start:x0 + prev + 1].any(1))[0]
            if prof[start:prev + 1].sum() >= 12 and rows[-1] - rows[0] >= height and prev - start >= 3:
                out.append((x0 + int(start), x0 + int(prev) + 1))
            start = c
        prev = c
    return out


def ink_width(ink, x0, x1, y0, y1):
    #the width of the ink in a cell, from its first glyph to its last, specks, periods, colons and dashes (less than
    #a digit high) aside
    glyphs = image_words(ink, x0, x1, y0, y1, gap=2, height=14)
    return glyphs[-1][1] - glyphs[0][0] if glyphs else 0


def page_rows(page, gender):
    meta = page_meta(page)
    ink = np.array(Image.open(clean_page(page))) < 128
    words = {s: pass_words(page, s, scale) for s, scale, _, _ in PASSES}
    strips = {s: (col, pass_words(page, s, scale)) for s, col, scale, _, _, _ in STRIPS}
    lefts, tops = header(page, words)
    bounds = strip_bounds(page)
    rows = []
    for half, (rk, top) in enumerate(zip(lefts, tops)):
        if np.isnan(rk):
            continue
        bands = row_bands(ink, rk, top)
        per_pass = {s: cells(w, bands, rk) for s, w in words.items()}
        per_strip = {s: (col, strip_cells(w, bands, rk)) for s, (col, w) in strips.items()}
        for i, (s, e) in enumerate(bands):
            row = {'page': page, 'half': half, 'row': i, 'gender': gender, 'y0': s, 'y1': e,
                   'top': original_y(meta, rk, s)}
            for c, _ in COLUMNS:
                row[c] = [' '.join(per_pass[p].get((i, c), [])) for p, _, _, _ in PASSES]
                #a column read on its own, after the page passes
                row[c] += [' '.join(cl.get(i, [])) for col, cl in per_strip.values() if col == c]
            for c in ('NAME', 'HOMETOWN'):
                row[c + '_words'] = image_words(ink, *bounds[half][c], s, e)
            row['BIB_width'] = ink_width(ink, int(rk + 76), int(rk + 142), s, e)
            #the CL column holds only a Y, so a mark there as tall as a letter is a classic skier (some pages print
            #the Y faintly; the specks the cleaning leaves are small)
            cl = ink[s:e, int(rk + 50):int(rk + 74)]
            tall = np.nonzero(cl.any(1))[0]
            row['classic'] = bool(cl.sum() >= 15 and tall[-1] - tall[0] >= 10)
            rows.append(row)
    return rows


def original_y(meta, x, y):
    #a point on the straightened page back on the page image
    a = np.radians(meta['angle'])
    cx, cy = meta['width'] / 2, meta['height'] / 2
    return int(round(cy + (x - cx) * np.sin(a) + (y - cy) * np.cos(a)))


#---------------------------------------------------------------- fields

def vote(values, score=None):
    #the most common non-empty value, ties to the better scored, then the earlier pass
    values = [v for v in values if v]
    if not values:
        return ''
    count = collections.Counter(values)
    return max(count, key=lambda v: (count[v] + (score(v) if score else 0), -values.index(v)))


#more of OCR's readings of a digit: a 1 with a halftone dot left on it reads as t, f, } or )
MORE_DIGITS = str.maketrans({'t': '1', 'f': '1', '}': '1', ')': '1', ']': '1', '(': '1', '{': '1', 'J': '1'})


def bib_read(text):
    #a bib as read, a character that can't be a digit as '?' (it held one): "?22" for a 522 whose 5 was lost
    t = text.strip(" .,:;=~_-'\"`").translate(MORE_DIGITS).translate(DIGITS)
    t = re.sub(r'\s+', '', t)
    return re.sub(r'\D', '?', t) if 0 < len(t) <= 5 else ''


def bib_digits(lst):
    #how many digits each row's bib has by the width of its ink, from a line fitted to the widths of the bibs every
    #reading agrees on in the same half page (the scans' scale differs a little). None where the width falls between
    out = {}
    for _, g in lst.groupby(['page', 'half']):
        sure = [(len(r[0]), w) for r, w in zip(g['BIB'].map(lambda t: [bib_read(x) for x in t]), g['BIB_width'])
                if len(set(r)) == 1 and r[0] and '?' not in r[0] and w]
        if len(sure) < 10 or len(set(n for n, _ in sure)) < 2:
            continue
        slope, icept = np.polyfit([n for n, _ in sure], [w for _, w in sure], 1)
        for i, w in g['BIB_width'].items():
            x = (w - icept) / slope
            if w and abs(x - round(x)) < 0.3 and 1 <= round(x) <= 5:
                out[i] = int(round(x))
    return out


def bib_support(reads, weights, n):
    #each bib the readings give, with the weight of the readings that back it (a reading with a '?' backs every bib
    #it could be), most first, among the bibs with n digits (when the ink's width says)
    reads = [(bib_read(t), w) for t, w in zip(reads, weights)]
    cands = list(dict.fromkeys(r for r, _ in reads if r and '?' not in r and (n is None or len(r) == n)))
    support = [(sum(w for r, w in reads if len(r) == len(c) and all(a in (b, '?') for a, b in zip(r, c))), c)
               for c in cands]
    return sorted(support, key=lambda s: (-s[0], cands.index(s[1])))


def unique_bibs(bibs, support):
    #every skier had a bib of their own. where two rows read the same bib, it stays with the row whose readings back
    #it more, and the other takes the next bib its readings give, when at least two readings back that one and no
    #other row has it. rows equally sure of a bib keep it
    bibs = list(bibs)
    for _ in range(3):
        rows = collections.defaultdict(list)
        for i, b in enumerate(bibs):
            if b:
                rows[b].append(i)
        changed = False
        for b, idx in rows.items():
            if len(idx) < 2:
                continue
            backing = sorted(((dict((c, n) for n, c in support[i]).get(b, 0), i) for i in idx), reverse=True)
            if backing[0][0] == backing[1][0]:
                continue
            for _, i in backing[1:]:
                alt = [(n, c) for n, c in support[i] if c != b and n >= 2 and c not in rows]
                if alt:
                    bibs[i] = alt[0][1]
                    changed = True
        if not changed:
            break
    return bibs


def number(text, max_len):
    #the words with a digit in them (not the column rule or a stray mark beside the number), as digits
    d = digits(''.join(t for t in text.split() if re.search(r'\d', t)))
    return d if 0 < len(d) <= max_len else ''


def clean_text(text):
    #an I read as a bracket or a mark ("{RONWOOD", "(OWA CITY", "MAHTOMED!", "PAOL]", "W)") back to an I, then letters,
    #digits, hyphens and apostrophes in upper case (a period is a space: "STEVEND.WEISS", "N FOND.DU LAC"), words
    #without a letter dropped
    text = re.sub(r"[{(\[](?=[A-Za-z])", 'I', text)
    text = re.sub(r"(?<=[A-Za-z])[!\])}]", 'I', text)
    text = re.sub(r"[^A-Za-z0-9'\- ]", ' ', text).upper()
    tokens = [t.strip('.-') for t in text.split()]
    tokens = [t for t in tokens if re.search(r'[A-Z]', t)]
    return ' '.join(tokens)


@functools.lru_cache(maxsize=None)
def known_names():
    clean = load_all_results()
    return frozenset(clean['first'].map(compact)) - {''}, frozenset(clean['last'].map(compact)) - {''}


def name_score(name):
    #names seen in the clean results. and between readings otherwise alike, a middle initial D over an O: this face's
    #D often reads as O, and few middle names start with an O
    first, middle, last, _ = split_first_last(name)
    firsts, lasts = known_names()
    return KNOWN_NAME * (compact(first) in firsts) + KNOWN_NAME * (compact(last) in lasts) - 0.01 * (middle == 'o')


def one_letter(token):
    #what a narrow word of the cell can read as: one letter, or a few I's ("II")
    return len(token) == 1 or set(token) == {'I'}


def fits_image(text, words):
    #a reading whose words go onto the cell's words, each of the cell's words taking one or more of the reading's in
    #order (the space after an A or before a T can be too narrow to see), as long as their letters are about as many
    #as its width holds, and a narrow word of the cell only an initial
    tokens = text.split()
    k, m = len(words), len(tokens)
    if not words or m < k:
        return False
    widths = [e - s for s, e in words]
    per_char = sum(widths) / sum(len(t) for t in tokens)
    #ok[i][j]: the first j reading words fit the first i cell words
    ok = np.zeros((k + 1, m + 1), dtype=bool)
    ok[0][0] = True
    for i in range(1, k + 1):
        for j in range(i, m + 1):
            for a in range(i - 1, j):
                if not ok[i - 1][a]:
                    continue
                group = tokens[a:j]
                n = sum(len(t) for t in group)
                narrow = widths[i - 1] < NARROW
                if narrow and not (len(group) == 1 and one_letter(group[0])):
                    continue
                if not narrow and abs(n - widths[i - 1] / per_char) > max(1.0, 0.25 * n):
                    continue
                ok[i][j] = True
                break
    return bool(ok[k][m])


def weigh(reads, weights, score=None, words=()):
    #the reading with the most weight behind it, counting readings that differ only in their spaces together, plus
    #its score, plus IMAGE_FIT when it fits the cell's words. of the readings counted together, the one that fits the
    #cell, then the best scored, then the one with the most words: OCR runs words together far more often than it
    #splits one, and the spaces after middle initials are narrow
    groups = collections.defaultdict(list)
    for text, w in zip(reads, weights):
        if text:
            groups[text.replace(' ', '')].append((text, w))
    if not groups:
        return ''
    out = []
    for key, g in groups.items():
        total = sum(w for _, w in g)
        by_text = collections.Counter()
        for text, w in g:
            by_text[text] += w
        text = max(by_text, key=lambda t: (fits_image(t, words), score(t) if score else 0, len(t.split()), by_text[t]))
        bonus = (score(text) if score else 0) + IMAGE_FIT * fits_image(text, words)
        out.append((total + bonus, by_text[text], text))
    return max(out)[2]


def split_by_image(text, words, score=None, known=frozenset()):
    #a reading with fewer words than the cell shows ("PAULBLEMENS", "COTTAGEGROVEMN"): each word of the reading goes
    #to a run of the cell's words, by its length against their widths, and one that goes to several is cut where
    #their widths say, give or take a letter, as the score likes best. a word in known (a name seen in the clean
    #results) isn't cut: the cell's extra word is more likely a middle initial OCR dropped
    tokens = text.split()
    k, m = len(words), len(tokens)
    if not m or k <= m:
        return text
    widths = [e - s for s, e in words]
    per_char = sum(widths) / sum(len(t) for t in tokens)
    #best[j][i]: the cost of putting the first j reading words on the first i cell words
    best = np.full((m + 1, k + 1), np.inf)
    back = np.zeros((m + 1, k + 1), dtype=int)
    best[0][0] = 0
    for j in range(1, m + 1):
        for i in range(j, k + 1):
            for a in range(j - 1, i):
                if i - a > len(tokens[j - 1]):
                    continue
                cost = best[j - 1][a] + abs(len(tokens[j - 1]) - sum(widths[a:i]) / per_char)
                if cost < best[j][i]:
                    best[j][i], back[j][i] = cost, a
    if not np.isfinite(best[m][k]):
        return text
    groups, i = [], k
    for j in range(m, 0, -1):
        groups.append((back[j][i], i))
        i = back[j][i]
    options = [[]]
    for token, (a, b) in zip(tokens, reversed(groups)):
        if b - a == 1:
            options = [o + [token] for o in options]
            continue
        if compact(token) in known:
            return text
        share = np.array(widths[a:b]) / per_char
        share = share * len(token) / share.sum()
        cuts = []
        for counts in itertools.product(*[range(max(1, int(round(x)) - 1), int(round(x)) + 2) for x in share]):
            counts = np.array(counts)
            if counts.sum() != len(token) or np.abs(counts - share).max() > 1.5:
                continue
            if any((w < NARROW) != (n == 1) for w, n in zip(widths[a:b], counts)):
                continue
            pieces, at = [], 0
            for n in counts:
                pieces.append(token[at:at + n])
                at += n
            cuts.append((np.abs(counts - share).sum(), pieces))
        if not cuts:
            return text
        options = [o + pieces for o in options for _, pieces in sorted(cuts, key=lambda c: c[0])]
    #the cut the score likes best, then the one closest to the widths
    return ' '.join(max(options, key=lambda o: (score(' '.join(o)) if score else 0, -options.index(o))))


def unglue_name(name):
    #a middle initial A run into the last name ("JOHN AHOLLER") or the first ("DAVIDA SJOGREN"), split where that
    #leaves names seen in the clean results and the run-together word is not one. an A's slope leaves next to no gap
    #before the next letter, so the cell's words can't show these. and a name read as one word ("DEANNALETTS")
    firsts, lasts = known_names()
    tokens = name.split()
    c = [compact(t) for t in tokens]
    if (len(tokens) == 2 and c[1] not in lasts and len(c[1]) >= 4 and c[1][0] == 'a' and c[1][1:] in lasts
            and c[0] in firsts):
        return '{} {} {}'.format(tokens[0], tokens[1][0], tokens[1][1:])
    if (len(tokens) == 2 and c[0] not in firsts and len(c[0]) >= 3 and c[0][-1] == 'a' and c[0][:-1] in firsts
            and c[1] in lasts):
        return '{} {} {}'.format(tokens[0][:-1], tokens[0][-1], tokens[1])
    if len(tokens) == 1:
        #every name has a first and a last, so a name read as one word is split where it leaves known ones, when
        #only one place does
        w = tokens[0]
        splits = [(w[:i], w[i:]) for i in range(2, len(w) - 1) if compact(w[:i]) in firsts and compact(w[i:]) in lasts]
        if len(splits) == 1:
            return ' '.join(splits[0])
    return name


#OCR's misreadings of a state's letters: "Wt", "tL", "1A", "8C", "OC"
STATE_LOOKALIKE = {'T': 'IL', 'L': 'I', 'I': 'L', '1': 'I', '8': 'B', '0': 'O', 'Q': 'O', '5': 'S', 'O': 'D',
                   'G': 'C'}


def read_state(token):
    #the state a two letter word reads as: as it is, or failing that the one state a single misread letter gives
    st = state_code(token)
    if st in US_STATES | CA_PROVINCES:
        return st
    if len(token) != 2:
        return ''
    alts = {token[:i] + c + token[i + 1:] for i in range(2) for c in STATE_LOOKALIKE.get(token[i], '')}
    alts &= US_STATES | CA_PROVINCES
    return alts.pop() if len(alts) == 1 else ''


def split_town(text):
    #"EAST LANSING MI": the town, and the state when the last word is one, or the word before a scrap of the nation
    #beside it ("HINES IL OE"). a state run into the town ("STEVENS POINTWI") is split off when that leaves a town
    #seen in that state
    tokens = text.split()
    if len(tokens) >= 2 and state_code(tokens[-1]) in US_STATES | CA_PROVINCES:
        return ' '.join(tokens[:-1]), state_code(tokens[-1])
    if len(tokens) >= 3 and len(tokens[-1]) <= 3 and state_code(tokens[-2]) in US_STATES | CA_PROVINCES:
        return ' '.join(tokens[:-2]), state_code(tokens[-2])
    if len(tokens) >= 2:
        st = read_state(tokens[-1])
        if st:
            return ' '.join(tokens[:-1]), st
    if tokens and len(tokens[-1]) > 3:
        st = state_code(tokens[-1][-2:])
        city = ' '.join(tokens[:-1] + [tokens[-1][:-2]])
        if st in US_STATES | CA_PROVINCES and (compact(city), st) in known_towns():
            return city, st
    return text, ''


#letters this face is often misread as, and what they were: its D reads as O or Q ("OULUTH", "DAVIO", "LUNOBERG"),
#its R as A ("NAPEAVILLE", "GILBEAT"), and LI as U ("MINNEAPOUS")
MISREAD = {'O': ('D',), 'Q': ('D', 'O'), 'A': ('R',), 'U': ('LI',)}


def misread(word, known, ends_only=False):
    #a word not seen in the clean results that one misread letter put back turns into one that is
    if compact(word) in known:
        return word
    alts = set()
    for i, ch in enumerate(word):
        if not ends_only or i in (0, len(word) - 1):
            for was in MISREAD.get(ch, ()):
                alt = word[:i] + was + word[i + 1:]
                if compact(alt) in known:
                    alts.add(alt)
    return alts.pop() if len(alts) == 1 else word


def repair_name(name):
    firsts, lasts = known_names()
    tokens = name.split()
    if len(tokens) >= 2:
        tokens[0] = misread(tokens[0], firsts, ends_only=True)
        tokens[-1] = misread(tokens[-1], lasts)
    return ' '.join(tokens)


def repair_town(city, st):
    if not st:
        return city
    towns = {c for c, s in known_towns() if s == st}
    return misread(city, towns)


#the older abbreviations the results print for some provinces ("WINNIPEG MA", "CANMORE AL", "MT ST GREGOIRE QU")
PROVINCES_PRINTED = {'MA': 'MB', 'AL': 'AB', 'QU': 'QC', 'PQ': 'QC', 'SA': 'SK', 'NF': 'NL'}


def resolve_town(reads, weights, nation, words=()):
    #the state is voted on by the readings that end in one, the town by the readings that end in the state (or,
    #outside the US and Canada, by all of them), so a misread state ("EVANSTON tL") doesn't read as part of the town.
    #a Canadian hometown's province in its printed abbreviation is given its code. a reading is cut at the gaps the
    #cell shows only where that makes a town seen in its state: the end of a long name can reach into the cell
    def provinces(t):
        if nation != 'CAN' or not t:
            return t
        return ' '.join(t.split()[:-1] + [PROVINCES_PRINTED.get(t.split()[-1], t.split()[-1])])

    def known(city, st):
        return (compact(city), st) in known_towns()

    split = []
    for t, w in zip(reads, weights):
        text = provinces(clean_text(t))
        city, st = split_town(text)
        cut = split_town(provinces(split_by_image(clean_text(t), words)))
        if cut[1] and not known(city, st) and (known(*cut) or not st):
            city, st = cut
        split.append(((city, st), w))
    states = collections.Counter()
    for (_, st), w in split:
        if st:
            states[st] += w
    if nation in ('USA', 'CAN', '') and states:
        st = max(states, key=lambda s: (states[s], -list(states).index(s)))
        towns = [(c, w) for (c, s), w in split if s == st]
        city = weigh([c for c, _ in towns], [w for _, w in towns], lambda c: KNOWN_TOWN * known(c, st))
        return repair_town(city, st), st
    whole = [clean_text(t) for t in reads]
    return weigh(whole, weights), ''


def division(text):
    #"M35-39" as ('M', 35, 39), as OCR leaves it ("M3539", "Md0-44", "35-39")
    t = text.upper().replace(' ', '')
    m = re.fullmatch(r'([MF])?([0-9OSBDIL]{2})-?([0-9OSBDIL]{2}|\+|UP)', t)
    if not m:
        return None
    lo, hi = digits(m.group(2)), digits(m.group(3)) if m.group(3) not in ('+', 'UP') else '99'
    if len(lo) != 2 or len(hi) != 2:
        return None
    return (m.group(1) or '', int(lo), int(hi))


def time_reads(text):
    #seconds from a finish time as printed: "50:08" or "1:24:56"
    d = digits(text)
    out = []
    if len(d) == 6:
        out += time_reads(d[1:]) + time_reads(d[:-1])
    elif len(d) == 5:
        if int(d[1:3]) < 60 and int(d[3:5]) < 60:
            out.append(int(d[0]) * 3600 + int(d[1:3]) * 60 + int(d[3:5]))
    elif len(d) == 4:
        if int(d[:2]) < 60 and int(d[2:]) < 60:
            out.append(int(d[:2]) * 60 + int(d[2:]))
    return out


def pace_reads(text):
    d = digits(text)
    if len(d) == 3 and int(d[1:]) < 60:
        return [int(d[0]) * 60 + int(d[1:])]
    return []


def pace_fits(t, paces):
    #the pace is the time over the distance in seconds per km, rounded up, from the time to the tenth
    return any(DISTANCE_KM * (p - 1) - 1 <= t <= DISTANCE_KM * p for p in paces)


def lookalikes(t):
    #a time with one digit swapped for one OCR mixes it up with, or another hour
    h, m, s = t // 3600, t % 3600 // 60, t % 60
    d = '{}{:02d}{:02d}'.format(h, m, s)
    out = set()
    for j, c in enumerate(d):
        for alt in set(LOOKALIKE.get(c, '')) | ({'0', '1', '2', '3', '4', '5'} if j == 0 else set()):
            x = d[:j] + alt + d[j + 1:]
            if int(x[1:3]) < 60 and int(x[3:5]) < 60:
                out.add(int(x[0]) * 3600 + int(x[1:3]) * 60 + int(x[3:5]))
    out.discard(t)
    return out


def fmt_time(t):
    return '{}:{:02d}:{:02d}.0'.format(t // 3600, t % 3600 // 60, t % 60) if t is not None else ''


def longest_ordered(values, weights):
    #indices of the heaviest run of values that never goes down, the rest dropped
    n = len(values)
    best = np.array(weights, dtype=float)
    prev = np.full(n, -1)
    for i in range(n):
        for j in range(max(0, i - 400), i):
            if values[j] <= values[i] and best[j] + weights[i] > best[i]:
                best[i], prev[i] = best[j] + weights[i], j
    i = int(np.argmax(best)) if n else -1
    out = []
    while i >= 0:
        out.append(i)
        i = prev[i]
    return sorted(out)


def resolve_times(lst):
    #each row's time: a reading at least two passes agree on that fits the pace, kept where the times run in order;
    #then for the rest, the one reading (or one-digit lookalike of a reading) that fits between its neighbours and the
    #pace
    reads = [collections.Counter(t for txt in r for t in time_reads(txt)) for r in lst['TIME']]
    paces = [set(p for txt in r for p in pace_reads(txt)) for r in lst['PACE']]
    times = [None] * len(lst)
    strong = []
    for i, (c, p) in enumerate(zip(reads, paces)):
        good = [(n, t) for t, n in c.items() if (n >= 2 and (not p or pace_fits(t, p))) or (n >= 1 and pace_fits(t, p))]
        if good:
            n, t = max(good)
            strong.append((i, t, n + (2 if pace_fits(t, p) else 0)))
    keep = longest_ordered([t for _, t, _ in strong], [w for _, _, w in strong])
    for k in keep:
        i, t, _ = strong[k]
        times[i] = t
    #the rest, in order, each between the nearest times settled before and after it
    for i in range(len(lst)):
        if times[i] is not None:
            continue
        lower = max([t for t in times[:i] if t is not None], default=0)
        upper = min([t for t in times[i + 1:] if t is not None], default=10 ** 6)
        direct = {t for t in reads[i] if lower <= t <= upper and (not paces[i] or pace_fits(t, paces[i]))}
        if len(direct) == 1:
            times[i] = direct.pop()
            continue
        #a time most passes read the same, in order between its neighbours, over a pace that doesn't fit it: the
        #pace is the smaller print and the likelier misread ("214" for 3:14)
        agreed = [t for t, n in reads[i].items() if n >= 3 and lower <= t <= upper]
        if len(agreed) == 1 and not direct:
            times[i] = agreed[0]
            continue
        if direct:
            continue
        near = set()
        for t in reads[i]:
            near |= {x for x in lookalikes(t) if lower <= x <= upper and (not paces[i] or pace_fits(x, paces[i]))}
        if len(near) == 1 and paces[i]:
            times[i] = near.pop()
        elif not reads[i] and lower == upper and paces[i] and pace_fits(lower, paces[i]):
            times[i] = lower
    #what is left, where the neighbours leave a narrow window: the one time in it (and in its pace, when one fits)
    #that the readings' digits miss by the fewest (the closest reading, then all of them), by one at most, or by two
    #with the seconds right ("x:45" between 51:41 and 52:02 with a pace of 2:15 is 51:45)
    for i in range(len(lst)):
        if times[i] is not None:
            continue
        lower = max([t for t in times[:i] if t is not None], default=None)
        upper = min([t for t in times[i + 1:] if t is not None], default=None)
        if lower is None or upper is None or upper - lower > 120:
            continue
        texts = [digits(t) for t in lst['TIME'].iloc[i] if len(digits(t)) >= 3]
        if not texts:
            continue
        window = list(range(lower, upper + 1))
        cands = [t for t in window if paces[i] and pace_fits(t, paces[i])] or window
        scored = sorted((min(misses(t, d) for d in texts), sum(misses(t, d) for d in texts), t) for t in cands)
        best, total, t = scored[0]
        seconds = any(d[-2:] == '{:02d}'.format(t % 60) for d in texts)
        if (len(scored) == 1 or scored[1][:2] > (best, total)) and (best <= 1 or (best == 2 and seconds)):
            times[i] = t
    return times


def misses(t, read):
    #the digits a reading gets wrong of a time, counted from the right, a missing or extra digit as one
    printed = '{}{:02d}{:02d}'.format(t // 3600, t % 3600 // 60, t % 60).lstrip('0')
    return sum(a != b for a, b in zip(printed[::-1], read[::-1])) + abs(len(printed) - len(read))


def resolve_places(lst):
    #places count up by one down the list. each stretch of rows (a half page) starts where its readings say, and the
    #stretches should follow on from each other
    places = np.full(len(lst), -1)
    report = []
    for (page, half), g in lst.groupby(['page', 'half'], sort=False):
        idx = np.nonzero((lst['page'] == page).values & (lst['half'] == half).values)[0]
        offs = collections.Counter()
        for k, i in enumerate(idx):
            for txt in lst['RK'].iloc[i]:
                d = number(txt, 4)
                if d:
                    offs[int(d) - k] += 1
        start = offs.most_common(1)[0][0] if offs else None
        report.append((page, half, start, len(idx), offs.most_common(3)))
        if start is not None:
            places[idx] = start + np.arange(len(idx))
    return places, report


def resolve_divisions(lst):
    #each row's class, by its DIV reading, its age and its class total. the classes are 18-24 and the five year ones
    #from 25-29 up that are read cleanly at least twice, and each class's total is the one its rows show most
    reads = [[division(t) for t in r] for r in lst['DIV']]
    gender = lst['gender'].iloc[0]
    clean = collections.Counter((d[1], d[2]) for r in reads for d in r if d and d[0] == gender)
    classes = [c for c, n in clean.items() if n >= 2 and (c == (18, 24) or (c[0] % 5 == 0 and c[1] - c[0] == 4))]
    majority = []
    for r in reads:
        n = collections.Counter((d[1], d[2]) for d in r if d and (d[1], d[2]) in classes)
        majority.append(n.most_common(1)[0][0] if n else None)
    totals = {}
    for c in classes:
        n = collections.Counter(number(t, 4) for m, r in zip(majority, lst['TOTAL']) if m == c for t in r)
        n.pop('', None)
        totals[c] = n.most_common(1)[0][0] if n else ''
    out, ages = [], []
    for r, age_txt, tot_txt in zip(reads, lst['AGE'], lst['TOTAL']):
        agev = [int(a) for a in (number(t, 2) for t in age_txt) if len(a) == 2]
        totv = [number(t, 4) for t in tot_txt]
        score = {c: 2 * sum(1 for d in r if d and (d[1], d[2]) == c) + sum(1 for a in agev if c[0] <= a <= c[1])
                 + sum(1 for t in totv if t and t == totals[c]) for c in classes}
        best = sorted(score.items(), key=lambda kv: -kv[1])
        if best and best[0][1] > 0 and (len(best) == 1 or best[0][1] > best[1][1]):
            c = best[0][0]
            out.append(c)
            fits = [a for a in agev if c[0] <= a <= c[1]]
            ages.append(str(collections.Counter(fits).most_common(1)[0][0]) if fits else '')
        else:
            out.append(None)
            ages.append('')
    return out, ages, totals


def resolve_class_ranks(lst, classes):
    #the class rank each row reads most, then a rank between two of its class that are two apart is the one between
    ranks = []
    for r in lst['PL']:
        ranks.append(vote([number(t, 4) for t in r]))
    ranks = [int(r) if r else None for r in ranks]
    by_class = collections.defaultdict(list)
    for i, c in enumerate(classes):
        if c:
            by_class[c].append(i)
    for c, idx in by_class.items():
        for k in range(len(idx)):
            prev = ranks[idx[k - 1]] if k else 0
            nxt = ranks[idx[k + 1]] if k + 1 < len(idx) else None
            if prev is not None and nxt is not None and prev + 2 == nxt and ranks[idx[k]] != prev + 1:
                ranks[idx[k]] = prev + 1
            elif k + 1 == len(idx) and prev is not None and ranks[idx[k]] is None:
                pass
    return ranks


#the nations the results print, as their codes
NATIONS = {'USA', 'CAN', 'NOR', 'GER', 'EST', 'FIN', 'RUS', 'FRA', 'ITA', 'SWE', 'CZE', 'SUI', 'AUS', 'AUT', 'POL',
           'ISL', 'ESP', 'SVK', 'SLO', 'GBR', 'ENG', 'SCO', 'DEN', 'JPN', 'JAP', 'LAT', 'LIT', 'LTU', 'NZL', 'NED',
           'NET', 'BEL', 'HUN', 'KOR', 'ARG', 'BRA', 'IRL', 'UKR', 'BLR', 'KAZ', 'CRO', 'ROM', 'RSA', 'MEX', 'CHN'}


def country(texts):
    #the nation code the readings back most: a reading counts fully for its code, and half for the one code it is
    #a letter short of or one letter off from ("TA", "SUL", "OZE"). an I read as a bracket is put back first
    reads = [re.sub(r'[^A-Z]', '', re.sub(r'[{(\[|](?=[A-Za-z])', 'I', t).upper()) for t in texts]
    reads = [r for r in reads if 2 <= len(r) <= 3]
    support = collections.Counter()
    for r in reads:
        if r in NATIONS:
            support[r] += 1
            continue
        near = [c for c in NATIONS if (len(r) == 3 and sum(a != b for a, b in zip(r, c)) == 1)
                or (len(r) == 2 and r in (c[1:], c[:2]))]
        if len(near) == 1:
            support[near[0]] += 0.5
    if support:
        return max(support, key=lambda c: (support[c], -reads.index(c) if c in reads else -9))
    return vote(reads)


#---------------------------------------------------------------- the year

def read_lists():
    #every row of the men's and the women's lists, with each column's readings
    return {gender: pd.DataFrame([r for p in pages for r in page_rows(p, gender)])
            for gender, pages in (('M', MEN_PAGES), ('F', WOMEN_PAGES))}


def resolve(lists):
    out, support = [], []
    for gender, lst in lists.items():
        places, _ = resolve_places(lst)
        classes, ages, _ = resolve_divisions(lst)
        ranks = resolve_class_ranks(lst, classes)
        times = resolve_times(lst)
        ndigits = bib_digits(lst)
        support += [bib_support(r, column_weights('BIB'), ndigits.get(i)) for i, r in lst['BIB'].items()]
        for i, r in lst.iterrows():
            name = weigh([clean_text(t) for t in r['NAME']], column_weights('NAME'), name_score, r['NAME_words'])
            firsts, lasts = known_names()
            name = split_by_image(name, r['NAME_words'], name_score, firsts | lasts)
            name = repair_name(unglue_name(name))
            nation = country(r['CO'])
            city, st = resolve_town(r['HOMETOWN'], column_weights('HOMETOWN'),
                                    nation if nation in NATIONS else '', r['HOMETOWN_words'])
            if nation not in NATIONS and st:
                #a nation read as no code ("UKA") beside a hometown in a state
                nation = 'USA' if st in US_STATES else 'CAN'
            c = classes[i]
            out.append({'place': str(places[i]) if places[i] > 0 else '',
                        'bib': '',
                        'name': name, 'gender': gender, 'age': ages[i],
                        'age_group': '{} {:02d}-{:02d}'.format(gender, *c) if c else '',
                        'class_rank': str(ranks[i]) if ranks[i] else '',
                        'city': city, 'state': st, 'country': nation,
                        'time': fmt_time(times[i]), 'status': 'finished',
                        'tech': 'classic' if r['classic'] else 'skate', 'page': r['page'], 'top': r['top']})
    out = pd.DataFrame(out, columns=[c for c in OUT_COLUMNS if c not in ('first', 'last')])
    out['bib'] = unique_bibs([s[0][1] if s else '' for s in support], support)
    return out


def parse(year=YEAR):
    ocr(year)
    return resolve(read_lists())


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
