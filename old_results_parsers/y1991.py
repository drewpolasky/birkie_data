#1991 birch scroll: the birkebeiner results are pages 26-39 (men, places 1-3278) and 40-41 (women, places 1-441), the
#kortelopet's 42-49. page 25 says 3720 finished the birkebeiner (3719 are printed). each results page is printed sideways
#(page 34 is also upside down), with three blocks of a line printer's fixed pitch table side by side, 80 lines a block:
#RANK, SEX ("M"/"F"), FINAL TIME, BIB, NAME, HOMETOWN (15 characters, so often shortened: STVNS POINT), ST, ZIP, NAT,
#CLASS ("M25-29"), CL RANK, 25% ("Y"), PACE (the time over 46 km). no technique column: classic and skate skiers share
#one list per gender, and the places count up by one down it
#
#tesseract reads the printer's dotted letters badly (M as H or W, 3, 8 and 9 for each other), so the pages are read
#character by character instead: each page is turned upright and straightened, each block's lines found, and each
#character cell on the printer's grid (about 8.74 pixels a character at 300 dpi, set line by line and nudged where the
#copy is stretched) read by a small neural network learned from the cells themselves: the places, the sex, the time's
#punctuation, the digits the tables pin down, tesseract's letters where its reading of the block
#(old_results/ocr/1991/<page>_b<n>.tsv) lines up with the grid, and the names and towns read as words seen in the clean
#results. the reading, with each character's runner-up, third choice and how sure it is, is kept as
#old_results/ocr/1991/<page>_grid.tsv; "python -m old_results_parsers.y1991 ocr" makes them (about four minutes)
#
#parse() then repairs what the tables pin down: a time out of order gets the digit swap that puts it in order, a class
#that can't be read the one its class ranks leave a gap for, a class rank the count within its class, a state its zip
#code's state, a repeated bib the runner-up digit that makes an unused one, a name or town word not seen in the clean
#results the runner-up letter that makes a common one, and a shortened town the one town in that state it shortens
#
#'top' is the line's y pixel in the page turned upright (clockwise a quarter turn) and straightened by ANGLE, which is
#the x pixel from the left in the stored page image; each such x holds three results, one in each block. page 34 is
#stored upside down, and its 'top' is the line's y pixel in the stored image, counted from the top
import bisect
import collections
import concurrent.futures
import functools
import itertools
import os
import re
import subprocess
import sys

import numpy as np
import pandas as pd
from PIL import Image

from birkie_archive import PAGE_DIR, OCR_DIR, TESSERACT, parse_seconds
from results_loader import load_all_results, US_STATES, CA_PROVINCES

PAGES = {**{p: 'M' for p in range(26, 40)}, **{p: 'F' for p in range(40, 42)}}
#each page's turn to upright, and then the small turn (degrees counterclockwise) that makes its lines level, found by
#the sharpest profile of ink by row
TURN = {34: Image.ROTATE_180}
ANGLE = {26: -0.19, 27: 0.37, 28: -1.32, 29: -0.4, 30: -1.47, 31: -0.68, 32: -1.45, 33: -0.1, 34: -0.09, 35: -0.27,
         36: -0.66, 37: 0.06, 38: -0.62, 39: 0.28, 40: -0.87, 41: -0.01}
PITCH = 8.742
PITCHES = np.arange(8.62, 8.92, 0.002)
BLOCK_WIDTH = 985
BLOCK_CHARS = 112
#each field's character columns in a block, from the left of the block's grid
FIELDS = {'rank': (2, 7), 'sex': (9, 12), 'time': (13, 25), 'bib': (25, 31), 'name': (31, 57), 'town': (57, 74),
          'st': (74, 77), 'zip': (77, 84), 'nat': (84, 88), 'cls': (88, 95), 'crank': (95, 101), 'club': (101, 104),
          'pace': (104, 111)}
OCR_CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:.-/%'&"
#the columns of the time's six digits, the pace's minutes and seconds (the colon in column 107) and the class's age
TIME_COLUMNS = (15, 17, 18, 20, 21, 23)
PACE_COLUMNS = (105, 106, 108, 109)
AGE_COLUMNS = (90, 91, 93, 94)
OCR_WORKERS = 4


def ocr_dir(year):
    return os.path.join(OCR_DIR, str(year))


#---------------------------------------------------------------- geometry

@functools.lru_cache(maxsize=None)
def upright(year, page):
    #the page as ink (True) and paper, upright and level
    im = Image.open(os.path.join(PAGE_DIR, str(year), '{:03d}.png'.format(page)))
    im = im.transpose(TURN.get(page, Image.ROTATE_270)).rotate(ANGLE[page], resample=Image.NEAREST, fillcolor=255)
    return np.array(im) < 128


def column_profile(ink):
    #ink in each pixel column, below the titles
    return ink[330:ink.shape[0] - 40].sum(0).astype(float)


@functools.lru_cache(maxsize=None)
def blocks(year, page):
    #the left edge of each of the three blocks: where the page's column profile best matches the first block of the
    #first page, one block width apart give or take
    ref = column_profile(upright(year, min(PAGES)))[170:170 + BLOCK_WIDTH]
    ref = ref - ref.mean()
    prof = column_profile(upright(year, page))
    n = len(ref)
    windows = np.lib.stride_tricks.sliding_window_view(prof, n)
    corr = (windows - windows.mean(1, keepdims=True)) @ ref
    out = []
    for k in range(3):
        if not out:
            lo, hi = 60, 260
        else:
            lo, hi = out[-1] + 960, out[-1] + 1020
        hi = min(hi, len(corr))
        out.append(lo + int(np.argmax(corr[lo:hi])))
    return tuple(out)


def block_image(year, page, k, scale=2):
    x0 = blocks(year, page)[k]
    ink = upright(year, page)
    crop = ink[:, max(0, x0 - 20):x0 + BLOCK_WIDTH + 15]
    im = Image.fromarray(np.where(crop, 0, 255).astype(np.uint8))
    return im.resize((im.width * scale, im.height * scale), Image.LANCZOS), max(0, x0 - 20)


LINE_PITCH = 25.2
#the strips of a block in which each line's height is measured, since a line can bend by up to 9 pixels across a
#block near the foot of a page. the first holds the rank, sex and time, which every result has
STRIPS = [(15, 225), (225, 420), (420, 620), (620, 800), (800, 975)]
GLYPH_W, GLYPH_H = 9, 26


def runs(on):
    out, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(on)))
    return out


def line_runs(profile):
    #rows of print: runs of rows with ink, a line high, and runs a few lines high (lines joined by specks) cut at their
    #thinnest rows
    out = []
    for s, e in runs(profile > 3):
        h = e - s
        if 13 <= h <= 24:
            out.append((s, e))
        elif 24 < h <= 80:
            n = int(round((h + 7) / LINE_PITCH))
            if n < 2:
                out.append((s, e))
                continue
            cuts = [s]
            for i in range(1, n):
                guess = s + int(round(i * (h + 7) / n)) - 4
                lo, hi = max(s + 1, guess - 5), min(e - 1, guess + 6)
                cuts.append(lo + int(np.argmin(profile[lo:hi])) if hi > lo else guess)
            cuts.append(e)
            for a, b in zip(cuts[:-1], cuts[1:]):
                part = np.nonzero(profile[a:b] > 3)[0]
                if len(part) and 12 <= part[-1] - part[0] + 1 <= 24:
                    out.append((a + part[0], a + part[-1] + 1))
    return out


def smooth_offsets(tops, offsets, window=4):
    #each strip's height against the first strip's, as the median over the nearby lines, so a strip a line has
    #nothing in (or a speck in) takes its neighbours'
    out = np.zeros_like(offsets)
    for j in range(offsets.shape[1]):
        col = offsets[:, j]
        for i in range(len(tops)):
            near = col[max(0, i - window):i + window + 1]
            near = near[~np.isnan(near)]
            out[i, j] = np.median(near) if len(near) else 0
    return out


@functools.lru_cache(maxsize=None)
def block_lines(year, page, k):
    #each line of a block: its top in each strip, and where its character grid starts (x of column 0's centre)
    ink = upright(year, page)
    x0 = blocks(year, page)[k]
    tops = []
    per_strip = []
    for a, b in STRIPS:
        prof = ink[:, x0 + a:x0 + b].sum(1)
        per_strip.append(np.array([s for s, e in line_runs(prof)]))
    tops = per_strip[0]
    offsets = np.full((len(tops), len(STRIPS)), np.nan)
    offsets[:, 0] = 0
    for i, t in enumerate(tops):
        for j in range(1, len(STRIPS)):
            other = per_strip[j]
            if len(other):
                m = np.argmin(abs(other - t))
                if abs(other[m] - t) <= 10:
                    offsets[i, j] = other[m] - t
    offsets = smooth_offsets(tops, offsets)
    centres = np.array([x0 + (a + b) / 2 for a, b in STRIPS])
    #each line's character pitch and grid phase, from the centres of its glyphs. the pitch changes a little from line to
    #line (the copy was stretched unevenly), so it's taken as the median over the nearby lines
    lines, centres_x = [], []
    for i, t in enumerate(tops):
        line_tops = t + offsets[i]
        xs = []
        for j, (a, b) in enumerate(STRIPS):
            y0 = int(round(line_tops[j]))
            band = ink[y0:y0 + 19, x0 + a:x0 + b].any(0)
            xs += [a + (u + v - 1) / 2 for u, v in runs(band) if 4 <= v - u <= 9]
        if len(xs) < 3:
            continue
        lines.append({'top': int(t), 'tops': line_tops, 'centres': centres, 'glyph_x': x0 + np.array(xs)})
        centres_x.append(np.array(xs))
    if not lines:
        return []
    fitted = np.full(len(lines), np.nan)
    for i, xs in enumerate(centres_x):
        if len(xs) >= 20:
            z = np.abs(np.exp(2j * np.pi * xs[None, :] / PITCHES[:, None]).mean(1))
            if z.max() > 0.8:
                fitted[i] = PITCHES[np.argmax(z)]
    if np.isnan(fitted).all():
        fitted[:] = PITCH
    pitches = []
    for i in range(len(lines)):
        near = fitted[max(0, i - 4):i + 5]
        near = near[~np.isnan(near)]
        pitches.append(np.median(near) if len(near) else np.nanmedian(fitted))
    #which column is which: the sex (column 10) and the time (15-23) are always printed, with blanks around them. a line
    #without them (a heading) keeps to the line above's grid
    previous = None
    for line, xs, pitch in zip(lines, centres_x, pitches):
        phase = np.angle(np.exp(2j * np.pi * xs / pitch).mean()) / (2 * np.pi) * pitch
        best = None
        for s in range(-2, 3):
            cells = inked(line_glyphs(ink, {**line, 'x0': x0 + phase + s * pitch, 'pitch': pitch}, 26))
            score = cells[[10, *range(15, 24)]].sum() - cells[[8, 9, 11, 12, 13, 14, 24]].sum()
            if best is None or score > best[0]:
                best = (score, x0 + phase + s * pitch)
        if best[0] < 8 and previous is not None:
            start = previous + np.round((x0 + phase - previous) / pitch) * pitch
        else:
            start = best[1]
        line.update({'x0': start, 'pitch': pitch, 'anchored': bool(best[0] >= 8)})
        previous = start
    return drift(reanchor(ink, lines))


def reanchor(ink, lines, rounds=2):
    #a line whose sex and time are smudged can be placed a column off. so each line's grid is moved by up to two
    #columns to where its inked cells best fit the share of the block's lines with ink in each column
    width = BLOCK_CHARS + 4
    occ = np.array([inked(line_glyphs(ink, {**l, 'x0': l['x0'] - 2 * l['pitch']}, width)) for l in lines])
    rows = [i for i, l in enumerate(lines) if l['anchored']]
    if len(rows) < 10:
        return lines
    shift = np.zeros(len(lines), int)
    for _ in range(rounds):
        p = np.mean([occ[i, 2 + shift[i]:2 + shift[i] + BLOCK_CHARS] for i in rows], 0).clip(0.01, 0.99)
        hit, miss = np.log(p), np.log(1 - p)
        for i in range(len(lines)):
            scores = [(occ[i, 2 + s:2 + s + BLOCK_CHARS] * hit + ~occ[i, 2 + s:2 + s + BLOCK_CHARS] * miss).sum()
                      for s in range(-2, 3)]
            shift[i] = int(np.argmax(scores)) - 2
    for line, s in zip(lines, shift):
        line['x0'] += s * line['pitch']
        line['shift'] = int(s)
    return lines


def drift(lines, reach=6, most=3.5):
    #the copy is stretched unevenly along a line too, so a stretch of glyphs can sit a pixel or two off the line's grid:
    #each column's offset is the median of the glyphs' offsets from the grid within a few columns of it
    for line in lines:
        gx = line['glyph_x']
        c = np.round((gx - line['x0']) / line['pitch'])
        r = gx - (line['x0'] + c * line['pitch'])
        offset = np.full(BLOCK_CHARS, np.nan)
        for col in range(BLOCK_CHARS):
            near = r[np.abs(c - col) <= reach]
            if len(near) >= 3:
                offset[col] = np.clip(np.median(near), -most, most)
        known = ~np.isnan(offset)
        #a column with too few glyphs near it takes its neighbours' offset
        line['offset'] = np.interp(np.arange(BLOCK_CHARS), np.nonzero(known)[0], offset[known]) if known.any()             else np.zeros(BLOCK_CHARS)
    return lines


def inked(cells):
    #the cells that hold a character: ink inside the cell's edge columns, which pick up the edges of the glyphs on
    #either side, wide ones like M and W especially
    return cells[..., 1:GLYPH_W - 1].sum((-2, -1)) > 3


def line_glyphs(ink, line, chars=BLOCK_CHARS):
    #the ink of each of the line's character cells, GLYPH_H by GLYPH_W, the top row 3 pixels above the line's top
    out = np.zeros((chars, GLYPH_H, GLYPH_W), bool)
    offset = line.get('offset')
    for c in range(chars):
        cx = line['x0'] + c * line.get('pitch', PITCH) + (offset[c] if offset is not None and c < len(offset) else 0)
        top = np.interp(cx, line['centres'], line['tops'])
        x, y = int(round(cx)) - GLYPH_W // 2, int(round(top)) - 3
        if y < 0 or x < 0:
            continue
        cell = ink[y:y + GLYPH_H, x:x + GLYPH_W]
        out[c, :cell.shape[0], :cell.shape[1]] = cell
    return out


@functools.lru_cache(maxsize=None)
def block_glyphs(year, page, k):
    #the block's result lines (those with a sex and a time where they belong) and their cells' ink
    ink = upright(year, page)
    lines = [l for l in block_lines(year, page, k) if l['anchored']]
    glyphs = np.array([line_glyphs(ink, l) for l in lines]) if lines else np.zeros((0, BLOCK_CHARS, GLYPH_H, GLYPH_W))
    return lines, glyphs


def tesseract_words(year, page, k, scale=2):
    #tesseract's words in the block, boxes in the upright page's pixels
    path = os.path.join(ocr_dir(year), '{:03d}_b{}.tsv'.format(page, k + 1))
    if not os.path.exists(path):
        return pd.DataFrame(columns=['text', 'left', 'top', 'width', 'height', 'conf'])
    words = pd.read_csv(path, sep='\t', quoting=3, dtype={'text': str}, keep_default_na=False)
    words = words[(words['level'] == 5) & (words['text'].str.strip() != '')].copy()
    xoff = max(0, blocks(year, page)[k] - 20)
    words[['left', 'top', 'width', 'height']] = words[['left', 'top', 'width', 'height']] / scale
    words['left'] += xoff
    return words


def tesseract_labels(year, page, k, lines, glyphs):
    #{(line, column): character} where one of tesseract's words covers as many inked cells as it has characters
    ink = inked(glyphs)
    out = {}
    for _, w in tesseract_words(year, page, k).iterrows():
        yc = w['top'] + w['height'] / 2
        xl, xr = w['left'], w['left'] + w['width']
        for i, line in enumerate(lines):
            top = np.interp((xl + xr) / 2, line['centres'], line['tops'])
            if abs(yc - (top + 9)) <= 7:
                cols = [c for c in range(BLOCK_CHARS) if ink[i, c]
                        and xl - 3 <= line['x0'] + c * line['pitch'] <= xr + 3]
                if len(cols) == len(w['text']):
                    out.update({(i, c): ch for c, ch in zip(cols, w['text'])})
                break
    return out


#---------------------------------------------------------------- reading the glyphs

#the characters each column can hold, so a 0 isn't read as a D in a time, or an M as an N in the sex column
DIGITS = '0123456789'
LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
COLUMN_CHARACTERS = ([DIGITS] * 9 + ['MF'] * 3 + [DIGITS + ':.'] * 13 + [DIGITS] * 6 + [LETTERS + "-.'&"] * 43
                     + [LETTERS] * 3 + [LETTERS + DIGITS] * 7 + [LETTERS] * 4
                     + [LETTERS] + ['MF'] + [DIGITS] * 2 + ['-+'] + [DIGITS] * 2
                     + [DIGITS] * 6 + [LETTERS] * 3 + [DIGITS + ':'] * 8)


def result_lines(year):
    #every result line, in order: (page, block, line, gender, line geometry) and the ink of its cells
    keys, glyphs = [], []
    for page, gender in PAGES.items():
        for k in range(3):
            lines, g = block_glyphs(year, page, k)
            keys += [(page, k, i, gender, line) for i, line in enumerate(lines)]
            glyphs.append(g)
    return keys, np.concatenate(glyphs)


def shifted(cells):
    #each cell moved by up to a pixel each way: 9 arrays of flattened cells
    padded = np.pad(cells, ((0, 0), (1, 1), (1, 1)))
    return [padded[:, dy:dy + GLYPH_H, dx:dx + GLYPH_W].reshape(len(cells), -1).astype(np.float32)
            for dy in range(3) for dx in range(3)]


def aligned(cells, template):
    #each cell at the shift that best matches the template
    moved = np.stack(shifted(cells))
    d = ((moved - template.reshape(-1)) ** 2).sum(2)
    return moved[d.argmin(0), np.arange(len(cells))].reshape(cells.shape)


def nearest_template(cells, templates, chunk=20000):
    flat = templates.reshape(len(templates), -1).astype(np.float32)
    out = []
    for a in range(0, len(cells), chunk):
        d = np.stack([(s ** 2).sum(1)[:, None] - 2 * s @ flat.T + (flat ** 2).sum(1)
                      for s in shifted(cells[a:a + chunk])]).min(0)
        out.append(d.argmin(1))
    return np.concatenate(out)


def training_cells(year, keys):
    #(line, column, character) known for sure: the places (which count up by one in each gender's list, so the n-th
    #line holds place n), the sex and the class's first letter, and the time's colons and point. and the letters
    #tesseract read, where its words line up with the grid
    sure, read = [], []
    place = {'M': 0, 'F': 0}
    labels = {}
    for n, (page, k, i, gender, line) in enumerate(keys):
        if (page, k) not in labels:
            labels[(page, k)] = {}
            for (i2, c), ch in tesseract_labels(year, page, k, *block_glyphs(year, page, k)).items():
                labels[(page, k)].setdefault(i2, []).append((c, ch))
        place[gender] += 1
        for c, ch in zip(range(3, 7), str(place[gender]).rjust(4)):
            if ch != ' ':
                sure.append((n, c, ch))
        sure += [(n, 10, gender), (n, 89, gender), (n, 16, ':'), (n, 19, ':'), (n, 22, '.')]
        read += [(n, c, ch) for c, ch in labels[(page, k)].get(i, []) if ch in LETTERS + '-&' and ch not in 'MF']
    return sure, read


def by_char(cells):
    out = {}
    for n, c, ch in cells:
        out.setdefault(ch, []).append((n, c))
    return {ch: np.array(v) for ch, v in out.items() if len(v) >= 15}


def learn(year, keys, glyphs, rounds=2):
    #first a linear discriminant over the cells' pixels (each character's mean cell and the cells' shared spread about
    #their means), learned from the cells known for sure and tesseract's letters where the nearest mean cell agrees
    #with it. tesseract mixes up M, H, N and W, and D and O, so the letters are then learned again from the names and
    #towns read as a word seen in the clean results, or one letter off one, the letter off being the reading's
    #runner-up. the discriminant mixes up the printer's 5 and 6, 6 and 8, 1 and 7, so last a small neural network is
    #learned from those cells and the digits the tables pin down whatever the reading (pinned_cells)
    sure, read = training_cells(year, keys)
    ink = inked(glyphs)
    sure = [s for s in sure if ink[s[0], s[1]]]
    read = [r for r in read if ink[r[0], r[1]]]
    first = by_char(sure + read)
    chars = sorted(first)
    templates = np.array([glyphs[first[ch][:, 0], first[ch][:, 1]].mean(0) for ch in chars])
    idx = np.array([(n, c) for n, c, _ in read])
    nearest = np.array(chars)[nearest_template(glyphs[idx[:, 0], idx[:, 1]], templates)]
    letters = [r for r, ch in zip(read, nearest) if r[2] == ch]
    model = discriminant(glyphs, by_char(sure + letters))
    for _ in range(rounds):
        words = lexicon_cells(glyphs, model)
        #the rare letters keep tesseract's too
        counts = by_char(words)
        rare = [r for r in letters if r[2] not in counts or len(counts[r[2]]) < 200]
        model = discriminant(glyphs, by_char(sure + words + rare))
    #the network learns twice, the second time from the names, towns and pinned digits as the first network reads them
    for _ in range(2):
        pinned = [p for p in pinned_cells(keys, read_text(glyphs, model)[0]) if ink[p[0], p[1]]]
        model = network(glyphs, by_char(sure + pinned + words + rare))
        words = lexicon_cells(glyphs, model)
        counts = by_char(words)
        rare = [r for r in letters if r[2] not in counts or len(counts[r[2]]) < 200]
    return model


def read_text(glyphs, model):
    #every line's 112 characters, their runners-up, the margins between them and the third choices
    ink = inked(glyphs)
    n, c = np.nonzero(ink)
    best, second, margin, third = read_cells(glyphs[n, c], c, model, third=True)
    text = np.full(ink.shape, ' ', dtype='<U1')
    alt = np.full(ink.shape, ' ', dtype='<U1')
    alt2 = np.full(ink.shape, ' ', dtype='<U1')
    sure = np.full(ink.shape, np.inf)
    text[n, c], alt[n, c], sure[n, c], alt2[n, c] = best, second, margin, third
    return text, alt, sure, alt2


VALID_AGES = ['1824', '2529', '3034', '3539', '4044', '4549', '5054', '5559', '6064', '6569']


def pinned_cells(keys, text):
    #(line, column, digit) that the tables pin down whatever the reading: the leading digits of a time that the times
    #placed just before and after it share, the PACE column's digits that every time within a second or so of the
    #line's gives, and the class's age digits where the reading is one digit off one class only
    out = []
    lines = [''.join(t) for t in text]
    genders = [k[3] for k in keys]
    for gender in sorted(set(genders)):
        rows = [n for n, g in enumerate(genders) if g == gender]
        d = [''.join(lines[n][c] for c in TIME_COLUMNS) for n in rows]
        secs = np.array([seconds(time_text(x)) if x.isdigit() and time_text(x) else np.nan for x in d])
        keep = longest_rising(secs)
        for i, n in enumerate(rows):
            if 0 < i < len(rows) - 1 and i - 1 in keep and i + 1 in keep:
                a, b = d[i - 1], d[i + 1]
                for k in range(6):
                    if a[:k + 1] != b[:k + 1]:
                        break
                    out.append((n, TIME_COLUMNS[k], a[k]))
            if i in keep and i - 1 in keep and i + 1 in keep:
                paces = {'{:>2}:{:02d}'.format(*divmod(int(round(q)), 60))
                         for q in np.arange(secs[i] / PACE_KM - 1.6, secs[i] / PACE_KM + 1.65, 0.1)}
                for j, col in enumerate(PACE_COLUMNS):
                    chars = {p[j + (j >= 2)] for p in paces}
                    if len(chars) == 1 and chars != {' '}:
                        out.append((n, col, chars.pop()))
    for n, line in enumerate(lines):
        age = ''.join(line[c] for c in AGE_COLUMNS)
        close = [a for a in VALID_AGES if sum(x == y for x, y in zip(a, age)) >= 3]
        if len(close) == 1:
            out += [(n, c, ch) for c, ch in zip(AGE_COLUMNS, close[0])]
    return out


@functools.lru_cache(maxsize=None)
def lexicon():
    #every word of the names and towns in the clean results, upper case: {word}, and {(length, position, word with that
    #letter blanked): [words]}
    clean = load_all_results()
    words = set()
    for col in ('first', 'middle', 'last', 'city'):
        for text in clean[col].dropna().unique():
            words.update(w.upper() for w in re.findall(r'[a-z]+', str(text).lower()) if len(w) >= 3)
    near = {}
    for w in words:
        for i in range(len(w)):
            near.setdefault(w[:i] + '?' + w[i + 1:], []).append(w)
    return frozenset(words), near


def lexicon_cells(glyphs, model):
    #(line, column, letter) for the name and town words read as a known word, or as one letter off exactly one known
    #word where that letter's runner-up makes it
    words, near = lexicon()
    cols = np.arange(FIELDS['name'][0], FIELDS['town'][1])
    cells = glyphs[:, cols]
    ink = inked(cells)
    n, c = np.nonzero(ink)
    best, second, _ = read_cells(cells[n, c], cols[c], model)
    text = np.full(ink.shape, ' ', dtype='<U1')
    alt = np.full(ink.shape, ' ', dtype='<U1')
    text[n, c], alt[n, c] = best, second
    out = []
    for i in range(len(cells)):
        line = ''.join(text[i])
        for m in re.finditer(r'[A-Z]{3,}', line):
            word, start = m.group(), m.start()
            if word in words:
                fixed = word
            else:
                fits = {w for j in range(len(word)) for w in near.get(word[:j] + '?' + word[j + 1:], [])
                        if w[j] == alt[i, start + j]}
                if len(fits) != 1:
                    continue
                fixed = fits.pop()
            out += [(i, cols[start + j], ch) for j, ch in enumerate(fixed)]
    return out


def discriminant(glyphs, final):
    chars = sorted(final)
    rng = np.random.RandomState(0)
    mus, spread = [], []
    for ch in chars:
        cells = final[ch]
        if len(cells) > 3000:
            cells = cells[rng.choice(len(cells), 3000, replace=False)]
        x = glyphs[cells[:, 0], cells[:, 1]]
        x = aligned(x, aligned(x, x.mean(0)).mean(0)).reshape(len(x), -1)
        mus.append(x.mean(0))
        spread.append(x - x.mean(0))
    spread = np.concatenate(spread)
    inv = np.linalg.inv(spread.T @ spread / len(spread) + 0.02 * np.eye(spread.shape[1]))
    mus = np.array(mus)
    weights = mus @ inv
    return 'lda', chars, weights.astype(np.float32), (-0.5 * (weights * mus).sum(1)).astype(np.float32)


def network(glyphs, final, hidden=128, epochs=20, per_char=4000, batch=256, seed=0):
    #a network with one hidden layer, learned from each character's cells (up to per_char of them), each moved by up to
    #a pixel each way at random
    chars = sorted(final)
    rng = np.random.RandomState(seed)
    idx, target = [], []
    for k, ch in enumerate(chars):
        cells = final[ch]
        if len(cells) > per_char:
            cells = cells[rng.choice(len(cells), per_char, replace=False)]
        idx.append(cells)
        target.append(np.full(len(cells), k))
    idx, target = np.concatenate(idx), np.concatenate(target)
    padded = np.pad(glyphs[idx[:, 0], idx[:, 1]], ((0, 0), (1, 1), (1, 1)))
    n, size, classes = len(idx), GLYPH_H * GLYPH_W, len(chars)
    params = [rng.randn(size, hidden).astype(np.float32) * np.sqrt(2 / size), np.zeros(hidden, np.float32),
              rng.randn(hidden, classes).astype(np.float32) * np.sqrt(1 / hidden), np.zeros(classes, np.float32)]
    moments = [(np.zeros_like(p), np.zeros_like(p)) for p in params]
    step = 0
    for epoch in range(epochs):
        rate = 1e-3 * 0.85 ** epoch
        order, moves = rng.permutation(n), rng.randint(0, 9, n)
        for a in range(0, n, batch):
            b = order[a:a + batch]
            x = np.empty((len(b), size), np.float32)
            for m in range(9):
                sel = moves[b] == m
                x[sel] = padded[b[sel], m // 3:m // 3 + GLYPH_H, m % 3:m % 3 + GLYPH_W].reshape(-1, size)
            h = np.maximum(x @ params[0] + params[1], 0)
            p = softmax(h @ params[2] + params[3])
            p[np.arange(len(b)), target[b]] -= 1
            p /= len(b)
            dh = (p @ params[2].T) * (h > 0)
            grads = [x.T @ dh, dh.sum(0), h.T @ p, p.sum(0)]
            step += 1
            for param, grad, (m1, m2) in zip(params, grads, moments):
                m1 *= 0.9
                m1 += 0.1 * grad
                m2 *= 0.999
                m2 += 0.001 * grad ** 2
                param -= rate * (m1 / (1 - 0.9 ** step)) / (np.sqrt(m2 / (1 - 0.999 ** step)) + 1e-8)
    return ('net', chars, *params)


def softmax(z):
    z = np.exp(z - z.max(1, keepdims=True))
    return z / z.sum(1, keepdims=True)


def scores(flat, model):
    #each cell's score for each character: the discriminant's, or the network's log probability
    if model[0] == 'lda':
        _, _, weights, bias = model
        return flat @ weights.T + bias
    if model[0] == 'nets':
        return np.mean([scores(flat, m) for m in model[2]], 0)
    _, _, w1, b1, w2, b2 = model
    z = np.maximum(flat @ w1 + b1, 0) @ w2 + b2
    z = z - z.max(1, keepdims=True)
    return z - np.log(np.exp(z).sum(1, keepdims=True))


def read_cells(cells, columns, model, chunk=20000, third=False):
    #each cell's character, the runner-up and the margin between their scores, among the characters its column holds,
    #at the best of the cell's moves by up to a pixel each way. and the third choice, when asked
    chars = model[1]
    allowed = np.array([[ch in COLUMN_CHARACTERS[c] for ch in chars] for c in range(BLOCK_CHARS)])
    best, second, margin, thirds = [], [], [], []
    for a in range(0, len(cells), chunk):
        score = np.stack([scores(s, model) for s in shifted(cells[a:a + chunk])]).max(0)
        score = np.where(allowed[columns[a:a + chunk]], score, -np.inf)
        order = np.argsort(-score, 1)[:, :3]
        top = np.take_along_axis(score, order, 1)
        best.append(order[:, 0])
        second.append(np.where(np.isfinite(top[:, 1]), order[:, 1], order[:, 0]))
        thirds.append(np.where(np.isfinite(top[:, 2]), order[:, 2], order[:, 0]))
        margin.append(np.where(np.isfinite(top[:, 1]), top[:, 0] - top[:, 1], np.inf))
    chars = np.array(chars)
    out = chars[np.concatenate(best)], chars[np.concatenate(second)], np.concatenate(margin)
    return out + (chars[np.concatenate(thirds)],) if third else out


def read_year(year):
    #every result line's characters as <page>_grid.tsv: the line's top, its 112 characters, each one's runner-up and
    #how sure the reading is (0-9: the network's log probability over the runner-up's, capped)
    keys, glyphs = result_lines(year)
    model = learn(year, keys, glyphs)
    text, alt, margin, alt2 = read_text(glyphs, model)
    sure = np.clip(np.nan_to_num(margin, posinf=99), 0, 9).astype(int).astype(str)
    rows = [{'page': page, 'block': k + 1, 'line': i + 1, 'gender': gender, 'top': line['top'],
             'text': '|' + ''.join(text[m]) + '|', 'alt': '|' + ''.join(alt[m]) + '|',
             'sure': '|' + ''.join(sure[m]) + '|', 'alt2': '|' + ''.join(alt2[m]) + '|'}
            for m, (page, k, i, gender, line) in enumerate(keys)]
    df = pd.DataFrame(rows)
    for page, lines in df.groupby('page'):
        lines.to_csv(grid_path(year, page), sep='\t', index=False)
    return df.astype(str)


def grid_path(year, page):
    return os.path.join(ocr_dir(year), '{:03d}_grid.tsv'.format(page))


def grid(year):
    #the glyph reading, made once (about two minutes) and kept in old_results/ocr/<year>/
    if not all(os.path.exists(grid_path(year, page)) for page in PAGES):
        df = read_year(year)
    else:
        df = pd.concat([pd.read_csv(grid_path(year, page), sep='\t', dtype=str, keep_default_na=False, quoting=3)
                        for page in PAGES], ignore_index=True)
    for col in ('text', 'alt', 'sure', 'alt2'):
        df[col] = df[col].str[1:-1]
    return df


#---------------------------------------------------------------- the results

#the PACE column is the final time over 46 km, to the second
PACE_KM = 46
AGES = ['18-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', '65-69', '70+']
PROVINCES = {'ONT': 'ON', 'MAN': 'MB', 'QUE': 'QC', 'SAS': 'SK', 'SASK': 'SK', 'ALT': 'AB', 'ALB': 'AB', 'BC': 'BC',
             'NB': 'NB', 'NS': 'NS', 'PEI': 'PE', 'NFL': 'NL'}
#the first three digits of each state's zip codes
ZIP3 = [(10, 27, 'MA'), (28, 29, 'RI'), (30, 38, 'NH'), (39, 49, 'ME'), (50, 59, 'VT'), (60, 69, 'CT'), (70, 89, 'NJ'),
        (100, 149, 'NY'), (150, 196, 'PA'), (197, 199, 'DE'), (200, 205, 'DC'), (206, 219, 'MD'), (220, 246, 'VA'),
        (247, 268, 'WV'), (270, 289, 'NC'), (290, 299, 'SC'), (300, 319, 'GA'), (320, 349, 'FL'), (350, 369, 'AL'),
        (370, 385, 'TN'), (386, 397, 'MS'), (400, 427, 'KY'), (430, 458, 'OH'), (460, 479, 'IN'), (480, 499, 'MI'),
        (500, 528, 'IA'), (530, 549, 'WI'), (550, 567, 'MN'), (570, 577, 'SD'), (580, 588, 'ND'), (590, 599, 'MT'),
        (600, 629, 'IL'), (630, 658, 'MO'), (660, 679, 'KS'), (680, 693, 'NE'), (700, 714, 'LA'), (716, 729, 'AR'),
        (730, 749, 'OK'), (750, 799, 'TX'), (800, 816, 'CO'), (820, 831, 'WY'), (832, 838, 'ID'), (840, 847, 'UT'),
        (850, 865, 'AZ'), (870, 884, 'NM'), (889, 898, 'NV'), (900, 961, 'CA'), (967, 968, 'HI'), (970, 979, 'OR'),
        (980, 994, 'WA'), (995, 999, 'AK')]
#a province's postal codes start with its letter
POSTAL = {'A': 'NL', 'B': 'NS', 'C': 'PE', 'E': 'NB', 'G': 'QC', 'H': 'QC', 'J': 'QC', 'K': 'ON', 'L': 'ON', 'M': 'ON',
          'N': 'ON', 'P': 'ON', 'R': 'MB', 'S': 'SK', 'T': 'AB', 'V': 'BC'}


def zip_state(z):
    z = z.replace('D', '0').replace('O', '0')
    if re.fullmatch(r'\d{5}', z):
        return next((s for a, b, s in ZIP3 if a <= int(z[:3]) <= b), '')
    if re.fullmatch(r'[A-Z]\d[A-Z]\d[A-Z]\d', z):
        return POSTAL.get(z[0], '')
    return ''


def cells(row, field, third=False):
    a, b = FIELDS[field]
    out = row['text'][a:b], row['alt'][a:b], row['sure'][a:b]
    return out + (row['alt2'][a:b],) if third else out


def clean_words(text):
    #a field's words, without specks read as stray points at their ends
    return ' '.join(w.strip(".'-") for w in text.split() if w.strip(".'-"))


def seconds(t):
    return parse_seconds(t) if t else np.nan


def time_text(d):
    return '{}:{}{}:{}{}.{}'.format(*d) if len(d) == 6 and int(d[1]) < 6 and int(d[3]) < 6 else ''


def pace_seconds(text):
    m = re.fullmatch(r'(\d{1,2}):(\d\d)', text.strip())
    return int(m.group(1)) * 60 + int(m.group(2)) if m and int(m.group(2)) < 60 else np.nan


def time_readings(row):
    #the time as read, and every reading with one or two of its digits swapped for their runner-up, the least sure
    #first
    text, alt, sure = row['text'], row['alt'], row['sure']
    best = [text[c] for c in TIME_COLUMNS]
    out = []
    if all(ch.isdigit() for ch in best):
        out.append(''.join(best))
    order = sorted(range(6), key=lambda j: sure[TIME_COLUMNS[j]])
    swaps = [[j] for j in order] + [[i, j] for n, i in enumerate(order[:3]) for j in order[n + 1:4]]
    for js in swaps:
        d = list(best)
        for j in js:
            d[j] = alt[TIME_COLUMNS[j]]
        if all(ch.isdigit() for ch in d):
            out.append(''.join(d))
    return [t for t in dict.fromkeys(time_text(d) for d in out) if t]


def swaps_from(t, row):
    #how many of the time's digits differ from the reading
    return sum(a != row['text'][c] for a, c in zip(re.sub(r'\D', '', t), TIME_COLUMNS))


def fits_pace(t, pace):
    return np.isnan(pace) or abs(seconds(t) / PACE_KM - pace) <= 1.5


def longest_rising(secs):
    #indexes of the longest run (not necessarily adjacent) of times that never go down
    idx = [i for i, s in enumerate(secs) if np.isfinite(s)]
    tails, prev, at = [], {}, []
    for i in idx:
        k = bisect.bisect_right(tails, secs[i])
        if k == len(tails):
            tails.append(secs[i])
            at.append(i)
        else:
            tails[k] = secs[i]
            at[k] = i
        prev[i] = at[k - 1] if k else None
    out, i = [], at[-1] if at else None
    while i is not None:
        out.append(i)
        i = prev[i]
    return set(out)


def repair_list_times(lst):
    #a list's times: the reading, where it lies between the times placed around it; otherwise the one reading with a
    #digit or two swapped for its runner-up that does, and, of several that do, the one that fits the PACE column. a
    #time no reading fits is left blank
    readings = [time_readings(r) for _, r in lst.iterrows()]
    paces = [pace_seconds(cells(r, 'pace')[0]) for _, r in lst.iterrows()]
    first = [rs[0] if rs and rs[0] == time_text([r['text'][c] for c in TIME_COLUMNS]) else ''
             for rs, (_, r) in zip(readings, lst.iterrows())]
    secs = np.array([seconds(t) for t in first])
    keep = longest_rising(secs)
    times = [t if i in keep else '' for i, t in enumerate(first)]
    secs = np.array([seconds(t) for t in times])
    for i in range(len(times)):
        if times[i]:
            continue
        before, after = secs[:i][np.isfinite(secs[:i])], secs[i + 1:][np.isfinite(secs[i + 1:])]
        lo = before.max() if len(before) else 0
        hi = after.min() if len(after) else np.inf
        fits = [t for t in readings[i] if lo <= seconds(t) <= hi]
        if len(fits) > 1:
            #the fewest digits changed
            fewest = min(swaps_from(t, lst.iloc[i]) for t in fits)
            fits = [t for t in fits if swaps_from(t, lst.iloc[i]) == fewest]
        if len(fits) > 1:
            fits = [t for t in fits if not np.isnan(paces[i]) and fits_pace(t, paces[i])]
        if len(fits) == 1:
            times[i] = fits[0]
            secs[i] = seconds(fits[0])
    return times


def class_label(row, gender):
    #"M 30-34" from the CLASS column, its letter being the list's: the reading, or the class that the fewest of its least
    #sure characters swapped for their runner-up make, when only one does
    text, alt, sure = cells(row, 'cls')
    weak = [j for j in range(len(text)) if sure[j] <= '4' and alt[j] != ' ']
    found = {}
    for k in range(len(weak) + 1):
        for js in itertools.combinations(weak, k):
            t = ''.join(alt[j] if j in js else ch for j, ch in enumerate(text))
            m = re.fullmatch(r'\s*[MF](\d\d-\d\d|70[-+])\s*', t)
            if m and m.group(1).replace('70-', '70+') in AGES:
                found.setdefault(k, set()).add(m.group(1).replace('70-', '70+'))
        if len(found.get(k, ())) == 1:
            return '{} {}'.format(gender, found[k].pop())
        if found.get(k):
            return ''
    return ''


def fill_classes(df):
    #a class that can't be read is the one class whose ranks, placed around the skier's, leave a gap for the skier's
    #class rank
    out = df['age_group'].copy()
    rank = pd.to_numeric(df['class_rank'], errors='coerce')
    for i in df.index[df['age_group'] == '']:
        fits = []
        for age, c in df[(df['gender'] == df.at[i, 'gender']) & (df['age_group'] != '')].groupby('age_group'):
            before = rank[c.index[c['place'] < df.at[i, 'place']]]
            after = rank[c.index[c['place'] > df.at[i, 'place']]]
            if len(before) == rank[i] - 1 and (not len(before) or before.iloc[-1] == rank[i] - 1)                     and len(after) and after.iloc[0] == rank[i] + 1:
                fits.append(age)
        if len(fits) == 1:
            out[i] = fits[0]
    return out


def repair_class_ranks(df):
    #the class ranks count up by one within each class, in place order: a rank that doesn't is replaced by the count
    #when the ranks read on either side of it in the class agree with the count
    out = df['class_rank'].copy()
    for _, c in df[df['age_group'] != ''].groupby(['gender', 'age_group']):
        c = c.sort_values('place')
        read = pd.to_numeric(c['class_rank'], errors='coerce').values
        n = np.arange(1, len(c) + 1)
        for i in range(len(c)):
            if read[i] == n[i]:
                continue
            ok_before = i == 0 or read[i - 1] == n[i - 1]
            ok_after = i == len(c) - 1 or read[i + 1] == n[i + 1]
            if ok_before and ok_after:
                out[c.index[i]] = str(n[i])
    return out


#the nations' codes, as the list writes them
NATIONS = {'USA', 'CAN', 'FIN', 'SUI', 'FRA', 'BRD', 'SWE', 'URS', 'AUS', 'POL', 'AUT', 'NOR', 'ITA', 'GER', 'JPN', 'NET',
           'NED', 'SLO', 'TCH', 'GBR', 'DEN', 'ISL', 'ESP', 'YUG', 'DDR', 'EST', 'HUN', 'BEL', 'NZL'}


def nation(row):
    #NAT: three letters, or the code the runner-up of its least sure letter makes. a speck is no nation
    text, alt, sure = cells(row, 'nat')
    nat = text.strip()
    if not re.fullmatch(r'[A-Z]{3}', nat):
        return ''
    if nat not in NATIONS:
        a = text.index(nat)
        fits = {nat[:j] + alt[a + j] + nat[j + 1:] for j in range(3) if sure[a + j] <= '2'} & NATIONS
        if len(fits) == 1:
            return fits.pop()
    return nat


def state_and_country(row):
    #ST, with the provinces' codes as Canada Post writes them, and NAT, USA or CAN when it's blank
    st = clean_words(cells(row, 'st')[0]).replace(' ', '')
    nat = nation(row)
    z = cells(row, 'zip')[0].strip()
    st = PROVINCES.get(st, st)
    from_zip = zip_state(z) if not nat or nat == 'CAN' else ''
    if from_zip and st != from_zip:
        #the zip pins the state when the state as read is one letter off it (MM, NI, II), or has a speck after it
        if (len(st) == len(from_zip) and sum(a != b for a, b in zip(st, from_zip)) == 1) or st[:2] == from_zip \
                or st not in US_STATES | CA_PROVINCES:
            st = from_zip
    if st in US_STATES and not nat:
        nat = 'USA'
    if st in CA_PROVINCES and nat in ('', 'CAM', 'CAA', 'CAN'):
        nat = 'CAN'
    return st, nat


@functools.lru_cache(maxsize=None)
def word_counts():
    #how often each word turns up in the clean results as a first name, a last name and in a town, upper case
    clean = load_all_results()
    count = lambda col: collections.Counter(w.upper() for text in clean[col].dropna()
                                            for w in re.findall(r'[a-z]+', str(text).lower().replace("'", '')))
    first, last, town = count('first'), count('last'), count('city')
    return first, last, first + last, town


SUFFIXES = {'JR', 'SR', 'II', 'III', 'IV'}


def field_text(row, field, unsure=2, common=3):
    #a name or town as printed. a point with a letter right after it is a speck in the space between two words. a word
    #not seen in the clean results (as a first name, for a name's first word, as a last name for its last) becomes the
    #one word seen there at least `common` times that the second choice for one of its letters read least surely makes
    #(or failing any, the third choice). the network never learned the apostrophe, which it reads as I or T: O'HARA comes out OIHARA
    text, alt, sure, alt2 = cells(row, field, third=True)
    chars = list(text)
    for j in range(len(chars) - 1):
        if chars[j] == '.' and chars[j + 1].isalpha():
            chars[j] = ' '
    first, last, either, town = word_counts()
    words = list(re.finditer(r"[A-Z][A-Z'-]*", ''.join(chars)))
    named = [m for m in words if m.group() not in SUFFIXES]
    for m in words:
        word, start = m.group(), m.start()
        if len(word) < 3 or not word.isalpha():
            continue
        if field == 'town':
            counts = town
        else:
            counts = first if named and m is named[0] else last if named and m is named[-1] else either
        if counts[word]:
            continue
        if field == 'name' and re.match(r'O[IT]', word) and sure[start + 1] <= '4' and counts['O' + word[2:]] >= common:
            chars[start + 1] = "'"
            continue
        weak = [j for j in range(len(word)) if sure[start + j] <= str(unsure)]
        for choice in (alt, alt2):
            fits = {word[:j] + choice[start + j] + word[j + 1:] for j in weak
                    if choice[start + j].isalpha() and choice[start + j] != word[j]}
            fits = {w for w in fits if counts[w] >= common}
            if fits:
                break
        if len(fits) == 1:
            chars[start:start + len(word)] = fits.pop()
    return clean_words(''.join(chars))


@functools.lru_cache(maxsize=None)
def town_counts():
    #{state: {town: how often it turns up in the clean results}}, upper case, for US states and Canadian provinces.
    #a few towns there are written twice over (MILWAUKEEMILWAUKEE)
    clean = load_all_results()
    out = {}
    for (city, state), n in clean.groupby(['city', 'state']).size().items():
        town = re.sub(r'[^A-Z ]', '', str(city).upper()).strip()
        if town and state in US_STATES | CA_PROVINCES and not re.fullmatch(r'(.+)\1', town.replace(' ', '')):
            out.setdefault(state, collections.Counter())[town] += n
    return out


def shortened(short, full):
    #the printer's 15 characters shorten a town's words: STVNS for STEVENS, PK for PARK, SHORE for SHORES
    return short == full or (short[0] == full[0] and len(short) < len(full)
                             and re.fullmatch('.*'.join(short) + '.*', full) is not None)


def expand_town(city, state, common=2, ahead=10):
    #a town not seen in that state, written out as the town seen there (at least `common` times) that it shortens,
    #when there's one, or one seen `ahead` times as often as the others (the clean results misspell a few)
    towns = town_counts().get(state)
    key = city.upper().replace('ST. ', 'ST ')
    if not towns or not city or towns[key]:
        return city
    words = key.split()
    fits = sorted(((n, t) for t, n in towns.items() if n >= common and len(t.split()) == len(words)
                   and all(shortened(a, b) for a, b in zip(words, t.split()))), reverse=True)
    if len(fits) == 1 or (len(fits) > 1 and fits[0][0] >= ahead * fits[1][0]):
        return fits[0][1]
    return city


def without_postcode(row, city, nat):
    #a European town is printed after its postal code (15870 HOLLOLA) and sometimes before a district (0861 OSLO 1),
    #which the town's columns read as letters, none of them surely: those are dropped
    if nat in ('USA', 'CAN', ''):
        return city
    text, _, sure = cells(row, 'town')
    raw = [(m.group(), np.mean([int(c) for c in sure[m.start():m.end()]])) for m in re.finditer(r'\S+', text)]
    words = city.split()
    if len(raw) != len(words) or len(words) < 2:
        return city
    if 4 <= len(raw[0][0]) <= 5 and raw[0][1] <= 2:
        words[0] = ''
    if len(raw[-1][0]) == 1 and raw[-1][1] <= 2.5:
        words[-1] = ''
    return ' '.join(w for w in words if w)


def repair_bibs(res, bibs):
    #no two skiers share a bib: of two that read the same, the one read less surely gets its least sure digit's runner-
    #up when that makes a bib nobody has, and loses its bib when nothing does
    out = res['bib'].copy()
    used = set(out[out != ''])
    for bib, group in res[res['bib'] != ''].groupby('bib'):
        if len(group) < 2:
            continue
        weakest = {i: min(bibs[i][2]) for i in group.index}
        order = sorted(group.index, key=lambda i: weakest[i])
        for i in order[:-1]:
            if weakest[i] >= weakest[order[-1]]:
                continue
            text, alt, sure = bibs[i]
            fits = set()
            for j in sorted(range(len(text)), key=lambda j: sure[j]):
                if text[j].isdigit() and alt[j].isdigit() and sure[j] < '9':
                    b = digits_only(text[:j] + alt[j] + text[j + 1:])
                    if b and b not in used:
                        fits.add(b)
                    break
            out[i] = fits.pop() if len(fits) == 1 else ''
            used.add(out[i])
    return out


def parse(year):
    df = grid(year)
    df['page'] = df['page'].astype(int)
    df['top'] = df['top'].astype(int)
    out, bibs = [], []
    for gender, lst in df.groupby('gender', sort=False):
        lst = lst.reset_index(drop=True)
        times = repair_list_times(lst)
        for i, row in lst.iterrows():
            st, nat = state_and_country(row)
            city = without_postcode(row, field_text(row, 'town'), nat)
            top = row['top']
            if TURN.get(row['page']) == Image.ROTATE_180:
                top = Image.open(os.path.join(PAGE_DIR, str(year), '{:03d}.png'.format(row['page']))).height - top - 18
            out.append({'place': i + 1, 'bib': digits_only(cells(row, 'bib')[0]),
                        'name': field_text(row, 'name'), 'gender': gender,
                        'age_group': class_label(row, gender), 'class_rank': digits_only(cells(row, 'crank')[0]),
                        'city': city, 'state': st, 'country': nat,
                        'time': times[i], 'status': 'finished', 'tech': '', 'page': row['page'], 'top': top})
            bibs.append(cells(row, 'bib'))
    res = pd.DataFrame(out)
    res['age_group'] = fill_classes(res)
    res['class_rank'] = repair_class_ranks(res)
    res['bib'] = repair_bibs(res, bibs)
    res['city'] = [expand_town(c, st) for c, st in zip(res['city'], res['state'])]
    return res


def digits_only(text):
    text = text.strip()
    return text if text.isdigit() else ''


#---------------------------------------------------------------- tesseract, for learning the glyphs

def ocr_block(year, page, k, scale=2):
    #tesseract's reading of one block, at twice the size, as <page>_b<k>.tsv (boxes in the doubled crop's pixels)
    out = os.path.join(ocr_dir(year), '{:03d}_b{}'.format(page, k + 1))
    if os.path.exists(out + '.tsv'):
        return out
    im, _ = block_image(year, page, k, scale)
    im.save(out + '.png')
    subprocess.run([TESSERACT, out + '.png', out, '--psm', '6', '-c', 'tessedit_char_whitelist=' + OCR_CHARACTERS,
                    'tsv'], capture_output=True)
    os.remove(out + '.png')
    return out


def ocr(year=1991):
    #tesseract on each block, then the glyph reading of every line
    jobs = [(page, k) for page in PAGES for k in range(3)]
    with concurrent.futures.ThreadPoolExecutor(OCR_WORKERS) as pool:
        for out in pool.map(lambda job: ocr_block(year, *job), jobs):
            print(out)
    read_year(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
