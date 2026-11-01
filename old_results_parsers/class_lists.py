#the result lists of 1973 to 1977, printed class by class: under each class's heading its skiers in order of time,
#numbered from 1 (1st, 2nd... in 1973 and 1974), a skier a line (1976 puts a club on a line of its own under the name),
#in one or two columns down a page, a class going on down the next column or page. 1973-1976 are typewritten, 1977 a
#computer's printout. each year's module (y1973.py to y1977.py) says which pages and columns hold the lists, where each
#field sits in a column, and where each class's heading is, and so which race (the birkebeiner, or the shorter race
#for juniors and, until 1974, for women) and which class each line is in. its HAND sets what pens' marks on the scan
#change or leave unreadable, and lines typed too far askew to read
#
#each page is turned level, its rules and long pen strokes made paper, and each column's lines found by the rows of
#ink where the place and name are; each other field's own rows are those of its ink nearest the line (a typist's town
#and time can sit a little below the name). tesseract reads each line whole and each field on its own, at two sizes
#(old_results/ocr/<year>/lines.tsv; "python -m old_results_parsers.y<year> ocr" makes it, in a few minutes), and a
#name or town is taken from the reading with the most words seen in the clean results. it reads a time's colons and
#points as digits now and then, so each time is read digit by digit instead (see read_times), and a class's times are
#then put in order at least cost (see repair_times)
#
#a class rank is the line's count in its class, a tie (two lines with one number and one time) sharing it. the place is
#the skier's among their gender in the birkebeiner, by time. 'top' is the line's y pixel on the page turned level
import collections
import concurrent.futures
import csv
import difflib
import functools
import importlib
import io
import itertools
import os
import re
import subprocess

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage

from birkie_archive import PAGE_DIR, OCR_DIR, TESSERACT, RESULT_CHARACTERS
from old_results_parsers.line_printer import (word_counts, town_counts, expand_town, first_name_first, runs, SUFFIXES,
                                              PARTICLES, DIGITS, network, scores, shifted)
from results_loader import US_STATES, CA_PROVINCES

OCR_WORKERS = 12
#a digit glyph, scaled to this many pixels wide and high to be matched
GLYPH = (16, 24)
#neighbours a digit is matched to, and how far (in log odds) each of tesseract's readings of a digit, its neighbours'
#all agreeing, and the class's order pinning it sway the network
NEIGHBOURS = 5
TESSERACT_SWAY = 3
NEIGHBOUR_SWAY = 4
PIN_SWAY = 4
#states and countries as the typists wrote them
STATE_WORDS = {'WIS': 'WI', 'WISC': 'WI', 'WISCONSIN': 'WI', 'MINN': 'MN', 'MINNESOTA': 'MN', 'MICH': 'MI',
               'MICHIGAN': 'MI', 'ILL': 'IL', 'ILLINOIS': 'IL', 'COLO': 'CO', 'COLORADO': 'CO', 'ALASKA': 'AK',
               'IOWA': 'IA', 'IND': 'IN', 'OHIO': 'OH', 'MASS': 'MA', 'WASH': 'WA', 'ORE': 'OR', 'CALIF': 'CA',
               'CAL': 'CA', 'MONT': 'MT', 'WYO': 'WY', 'IDAHO': 'ID', 'UTAH': 'UT', 'NEB': 'NE', 'KANS': 'KS',
               'PENN': 'PA', 'CONN': 'CT', 'VERMONT': 'VT', 'MAINE': 'ME', 'ONT': 'ON', 'ONTARIO': 'ON', 'MAN': 'MB',
               'MANITOBA': 'MB', 'QUE': 'QC', 'SASK': 'SK', 'ALTA': 'AB', 'ALBERTA': 'AB', 'BC': 'BC', 'ND': 'ND',
               'SD': 'SD', 'NY': 'NY', 'NH': 'NH', 'NJ': 'NJ'}
COUNTRY_WORDS = {'NORWAY': 'NOR', 'NORGE': 'NOR', 'SWEDEN': 'SWE', 'CANADA': 'CAN', 'CAN': 'CAN', 'FINLAND': 'FIN',
                 'USA': 'USA', 'US': 'USA', 'GERMANY': 'GER', 'SWITZERLAND': 'SUI', 'AUSTRIA': 'AUT', 'FRANCE': 'FRA',
                 'JAPAN': 'JPN', 'ITALY': 'ITA', 'NOR': 'NOR', 'SWE': 'SWE', 'FIN': 'FIN'}
#letters tesseract reads for digits in a place
PLACE_LOOKS = str.maketrans({'l': '1', 'i': '1', 'I': '1', 'L': '1', '|': '1', 'O': '0', 'o': '0', 'S': '5', 's': '5',
                             'B': '8', '&': '8', 'Z': '2', 'z': '2', 'G': '6', 'b': '6', 'g': '9', 'q': '9'})


def layout(year):
    return importlib.import_module('old_results_parsers.y{}'.format(year))


def setting(year, name, page=None, default=None):
    #a year's setting, or its page's own where the module's PAGE_<name> has one
    if page is not None and page in getattr(layout(year), 'PAGE_' + name, {}):
        return getattr(layout(year), 'PAGE_' + name)[page]
    return getattr(layout(year), name, default)


def fields_of(year, page, col):
    #each field's left and right edge in pixels from the column's left: the year's FIELDS, or the column's own where it
    #gives one for each column
    fields = setting(year, 'FIELDS', page)
    return fields[col] if isinstance(fields, (list, tuple)) else fields


def ocr_dir(year):
    path = os.path.join(OCR_DIR, str(year))
    os.makedirs(path, exist_ok=True)
    return path


#---------------------------------------------------------------- pages and lines

@functools.lru_cache(maxsize=4)
def level_page(year, page):
    #the page in grays, turned upright and level, without its rules down the page (or a pen's long strokes): ink
    #running down more than four lines' height is made paper,
    im = Image.open(os.path.join(PAGE_DIR, str(year), '{:03d}.png'.format(page))).convert('L')
    turn = layout(year).TURN.get(page)
    if turn is not None:
        im = im.transpose(turn)
    im = im.rotate(layout(year).ANGLE[page], resample=Image.BICUBIC, fillcolor=255)
    scale = getattr(layout(year), 'SCALE', {}).get(page)
    if scale:
        #(a page printed larger than the rest, shrunk to their size)
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    gray = np.array(im)
    ink = gray < 160
    longest = 4 * setting(year, 'LINE_PITCH', page)
    for x in np.nonzero(ink.sum(0) > longest)[0]:
        for start, end in runs(ink[:, x]):
            if end - start > longest:
                gray[start:end, max(0, x - 1):x + 2] = 255
    #and its rules across, underlines and lines struck through: ink running across more than three characters
    widest = 3 * setting(year, 'PITCH', page)
    for y in np.nonzero(ink.sum(1) > widest)[0]:
        for start, end in runs(ink[y]):
            if end - start > widest:
                gray[max(0, y - 1):y + 2, start:end] = 255
    return gray


@functools.lru_cache(maxsize=None)
def column_lines(year, page, col):
    #(top, bottom) of each line of print in a column: runs of rows with ink where the place and name are (a typist's
    #town and time can sit a little lower or higher), a run a few lines high (lines joined by a pen's mark or a speck)
    #cut at its thinnest rows a line apart
    gray = level_page(year, page)
    x0 = setting(year, 'COLUMNS', page)[col][0]
    fields = fields_of(year, page, col)
    ink = gray[:, x0 + fields['place'][0]:x0 + fields['name'][1]] < 128
    profile = ink.sum(1)
    least, most = setting(year, 'LINE_HEIGHT', page)
    pitch = setting(year, 'LINE_PITCH', page)
    out = []
    for s, e in runs(profile > 2):
        if e - s < least:
            continue
        if e - s <= most:
            out.append((s, e))
            continue
        n = max(2, int(round((e - s) / pitch)))
        cuts = [s]
        for k in range(1, n):
            guess = s + k * (e - s) / n
            lo, hi = int(guess - pitch / 3), int(guess + pitch / 3)
            cuts.append(lo + int(np.argmin(profile[lo:hi])))
        cuts.append(e)
        out += [(a, b) for a, b in zip(cuts, cuts[1:]) if b - a >= least]
    #a part cut off a run with next to no ink, or with its ink in a few rows (a pen's line under a name), is no line
    inks = [profile[a:b].sum() for a, b in out]
    typical = np.median(inks) if inks else 0
    tall = [(profile[a:b] > 0.3 * profile[a:b][profile[a:b] > 0].mean()).sum() >= least for a, b in out]
    return tuple(l for l, ink, t in zip(out, inks, tall) if ink >= typical / 4 and t)


def split_runs(profile, offset, least, most, pitch):
    #runs of rows with ink in a profile, a run taller than `most` (lines touching) cut at its thinnest rows a line
    #apart, and a piece still too tall cut again
    def cut(s, e, depth=0):
        if e - s <= most or depth > 3:
            return [(s, e)]
        n = max(2, int(round((e - s) / pitch)))
        cuts = [s]
        for k in range(1, n):
            guess = s + k * (e - s) / n
            lo, hi = max(s + 1, int(guess - pitch / 3)), min(e - 1, int(guess + pitch / 3))
            if hi > lo:
                cuts.append(lo + int(np.argmin(profile[lo:hi])))
        cuts.append(e)
        return [piece for a, b in zip(cuts, cuts[1:]) for piece in cut(a, b, depth + 1)]
    return [(offset + a, offset + b) for s, e in runs(profile > 1) if e - s >= least
            for a, b in cut(s, e) if b - a >= least]


def field_runs(year, page, col, line, field):
    #the runs of rows with ink across a field within a line and a third of the line's middle (a run of two lines'
    #touching ink cut between them), but specks: (top, bottom, middle less the line's)
    gray = level_page(year, page)
    x0 = setting(year, 'COLUMNS', page)[col][0]
    a, b = fields_of(year, page, col)[field]
    pitch = setting(year, 'LINE_PITCH', page)
    least, most = setting(year, 'LINE_HEIGHT', page)
    if field == 'time':
        #digits have no tails below the line: a time is about a character and a fifth high, and no shorter than a line
        least, most = least, min(most, 1.55 * setting(year, 'PITCH', page))
    else:
        least = least / 2
    lo = max(0, line[0] - int(pitch))
    profile = (gray[lo:line[1] + int(pitch), x0 + a:x0 + b] < 150).sum(1)
    centre = (line[0] + line[1]) / 2
    return [(t, bt, (t + bt) / 2 - centre) for t, bt in split_runs(profile, lo, least, most, pitch)
            if abs((t + bt) / 2 - centre) <= pitch / 2]


@functools.lru_cache(maxsize=None)
def field_offsets(year, page, col, field):
    #how far a column's field sits below each of its lines (a typist's times can sit a little low, and lower or higher
    #down a page): (each line's top, the field's offset from the line's middle where it has one run of ink within half
    #a line of it)
    out = []
    for line in column_lines(year, page, col):
        near = field_runs(year, page, col, line, field)
        if len(near) == 1:
            out.append((line[0], near[0][2]))
    return out


def field_offset(year, page, col, field, line, around=6):
    #the offset of a field at a line: the middle of those of the lines nearest it
    samples = field_offsets(year, page, col, field)
    if not samples:
        return 0.0
    nearest = sorted(samples, key=lambda s: abs(s[0] - line[0]))[:2 * around]
    return float(np.median([o for _, o in nearest]))


@functools.lru_cache(maxsize=None)
def column_field_rows(year, page, col, field):
    #{line: the rows of a field's own ink in it}: the run of rows with ink across the field nearest where the offset of
    #the lines about it puts it, within a third of a line; then for a line with none (a class typed with its towns and
    #times half a line low), the nearest run within half a line that no line has taken. a line left with none gets
    #its own rows, or none for the time
    reach = setting(year, 'LINE_PITCH', page) / 3
    lines = column_lines(year, page, col)
    out, taken = {}, set()
    for line in lines:
        offset = field_offset(year, page, col, field, line)
        near = [r for r in field_runs(year, page, col, line, field) if abs(r[2] - offset) <= reach]
        if near:
            best = min(near, key=lambda r: abs(r[2] - offset))
            out[line] = (best[0], best[1])
            taken.add(out[line])
    for line in lines:
        if line in out:
            continue
        offset = field_offset(year, page, col, field, line)
        free = [r for r in field_runs(year, page, col, line, field) if (r[0], r[1]) not in taken]
        if free:
            best = min(free, key=lambda r: abs(r[2] - offset))
            out[line] = (best[0], best[1])
            taken.add(out[line])
        else:
            out[line] = (line[0], line[0]) if field == 'time' else line
    return out


def field_rows(year, page, col, line, field):
    rows = column_field_rows(year, page, col, field)
    if line in rows:
        return rows[line]
    #(a line not found in its column: a heading's, say)
    return (line[0], line[0]) if field == 'time' else line


def line_crop(year, page, col, line, pad=10, span=None):
    #the line's rows of the column (or of `span`, pixels from the column's left), with white about them in place of the
    #lines either side
    gray = level_page(year, page)
    x0, x1 = setting(year, 'COLUMNS', page)[col]
    if span:
        x0, x1 = x0 + span[0], x0 + span[1]
    top, bottom = line
    return np.pad(gray[top:bottom, x0:x1], ((pad, pad), (pad, pad)), constant_values=255), x0 - pad


#---------------------------------------------------------------- tesseract

def tesseract(img, scale):
    im = Image.fromarray(img)
    #in black and white: tesseract can read nothing at all of a line in grays with specks about it
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    im = im.point(lambda v: 0 if v < 160 else 255)
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    out = subprocess.run([TESSERACT, 'stdin', 'stdout', '--psm', '7', '-c',
                          'tessedit_char_whitelist=' + RESULT_CHARACTERS, 'tsv'],
                         input=buf.getvalue(), capture_output=True).stdout.decode('utf8', 'replace')
    t = pd.read_csv(io.StringIO(out), sep='	', quoting=csv.QUOTE_NONE, keep_default_na=False, dtype={'text': str})
    return t[(t['level'] == 5) & (t['text'].str.strip() != '')]


def read_line(year, page, col, line):
    #tesseract's words in a line, read whole at each of the year's scales ('1', '1.5'), and each field but the time
    #read on its own, in its own rows ('f1', 'f1.5'): tesseract now and then reads nothing of a line, or of the rest of
    #it after a pen's mark
    out = []
    x_col = setting(year, 'COLUMNS', page)[col][0]
    fields = fields_of(year, page, col)
    gray = level_page(year, page)

    def add(img, x0, key, scale):
        for _, w in tesseract(img, scale).iterrows():
            out.append({'page': page, 'col': col, 'top': line[0], 'bottom': line[1], 'reading': key,
                        'left': x0 + w['left'] / scale, 'right': x0 + (w['left'] + w['width']) / scale,
                        'conf': w['conf'], 'text': w['text']})

    img, x0 = line_crop(year, page, col, line)
    for scale in setting(year, 'SCALES', page, (2, 3)):
        add(img, x0, str(scale), scale)
    for field, (a, b) in fields.items():
        rows = field_rows(year, page, col, line, field)
        if field != 'time' and (gray[rows[0]:rows[1], x_col + a:x_col + b] < 128).sum() >= 20:
            img, x0 = line_crop(year, page, col, rows, span=(a, b))
            for scale in setting(year, 'SCALES', page, (2, 3)):
                add(img, x0, 'f' + str(scale), scale)
    #and the time on its own, character by character, at twice and three times the size ('c2', 'c3'): each digit
    #tesseract reads where it is, whatever it makes of the colons
    a, b = fields['time']
    img, x0 = line_crop(year, page, col, field_rows(year, page, col, line, 'time'), span=(a, b))
    for scale in (2, 3):
        for ch, left, right in characters(img, scale):
            out.append({'page': page, 'col': col, 'top': line[0], 'bottom': line[1], 'reading': 'c' + str(scale),
                        'left': x0 + left, 'right': x0 + right, 'conf': -1, 'text': ch})
    return out


def characters(img, scale):
    #tesseract's characters in a time, and where each is across (in the image's pixels): (character, left, right)
    im = Image.fromarray(img)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    im = im.point(lambda v: 0 if v < 160 else 255)
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    out = subprocess.run([TESSERACT, 'stdin', 'stdout', '--psm', '7', '-c', 'tessedit_char_whitelist=0123456789:.',
                          'makebox'], input=buf.getvalue(), capture_output=True).stdout.decode('utf8', 'replace')
    boxes = [line.split() for line in out.splitlines()]
    return [(b[0], int(b[1]) / scale, int(b[3]) / scale) for b in boxes if len(b) == 6]


def ocr(year):
    #tesseract's readings of every line, as old_results/ocr/<year>/lines.tsv
    jobs = [(page, col, line) for page in layout(year).PAGES for col in range(len(setting(year, 'COLUMNS', page)))
            for line in column_lines(year, page, col)]
    with concurrent.futures.ThreadPoolExecutor(OCR_WORKERS) as pool:
        words = [w for ws in pool.map(lambda job: read_line(year, *job), jobs) for w in ws]
    pd.DataFrame(words).to_csv(os.path.join(ocr_dir(year), 'lines.tsv'), sep='	', index=False)
    print(year, len(jobs), 'lines read')


@functools.lru_cache(maxsize=None)
def readings(year):
    #{(page, col, top): {reading: [(left, right, text)]}}, the whole line's readings first
    t = pd.read_csv(os.path.join(ocr_dir(year), 'lines.tsv'), sep='	', quoting=csv.QUOTE_NONE,
                    keep_default_na=False, dtype={'text': str, 'reading': str})
    out = {}
    for row in t.itertuples():
        out.setdefault((row.page, row.col, row.top), {}).setdefault(row.reading, []).append(
            (row.left, row.right, row.text))
    return {k: dict(sorted(v.items(), key=lambda kv: (kv[0][0].isalpha(), kv[0])))
            for k, v in out.items()}


def word_readings(reading):
    #a line's readings as words (the whole line's and lone fields'), not the time's characters
    return [words for key, words in reading.items() if not key.startswith('c')]


def field_words(words, field, x0, fields):
    #the words whose middle is in a field (pixels from the column's left)
    a, b = fields[field]
    return [text for left, right, text in words if a <= (left + right) / 2 - x0 < b]


#---------------------------------------------------------------- classes

def sections(year):
    #each result line, in reading order, with its class: a heading's class runs down each column below it to the next
    #heading on the page (or to the page's foot, and on down the next page's columns above its first heading)
    out = []
    current = None
    headings = getattr(layout(year), 'HEADINGS')
    for page in layout(year).PAGES:
        mine = sorted((y, label) for p, y, label in headings if p == page)
        bands = [(0, current)] + [(y, label) for y, label in mine]
        ends = [y for y, _ in bands[1:]] + [10 ** 6]
        for (start, label), end in zip(bands, ends):
            if label is None:
                continue
            for col in range(len(setting(year, 'COLUMNS', page))):
                for line in column_lines(year, page, col):
                    if line[0] < getattr(layout(year), 'TABLE_TOP', {}).get(page, 0):
                        continue
                    #a heading's own lines start within most of a line below its top (or of its HEADING_LINES)
                    below = (setting(year, 'HEADING_LINES', page, 1) - 0.2) * setting(year, 'LINE_PITCH', page)
                    below = below if start else 0
                    if start + below <= line[0] < end - 6:
                        out.append((page, col, line, label))
        if mine:
            current = mine[-1][1]
    return out


#---------------------------------------------------------------- times

def glyphs(year, page, col, line):
    #the time's glyphs, left to right: (left, right, top, bottom, the tallest of its pieces, image), a glyph being the
    #pieces of ink that overlap across (a colon's two dots, a digit broken in two), in the time's own rows (a typed
    #line isn't always level, so its time can sit a little above or below the rest of it), counted from their top
    #less 2
    gray = level_page(year, page)
    x0 = setting(year, 'COLUMNS', page)[col][0]
    a, b = fields_of(year, page, col)['time']
    rows = field_rows(year, page, col, line, 'time')
    top = max(0, rows[0] - 2)
    crop = gray[top:rows[1] + 2, x0 + a:x0 + b].copy()
    if not crop.size:
        return []
    #a pen's line under or through a time, ink running across more than a character and a half
    for y in range(crop.shape[0]):
        for s, e in runs(crop[y] < 150):
            if e - s > 1.5 * setting(year, 'PITCH', page):
                crop[y, s:e] = 255
    lab, n = ndimage.label(crop < 150, structure=np.ones((3, 3)))
    boxes = sorted((sl[1].start, sl[1].stop, sl[0].start, sl[0].stop) for k, sl in enumerate(ndimage.find_objects(lab))
                   if (lab[sl] == k + 1).sum() >= 4)
    middle = lambda t, bt: top + (t + bt) / 2
    centre = (rows[0] + rows[1]) / 2
    boxes = [bx for bx in boxes if abs(middle(bx[2], bx[3]) - centre) <= 0.35 * setting(year, 'LINE_PITCH', page)]
    merged = []
    for l, r, t, bt in boxes:
        if merged and l < merged[-1][1] - 1:
            m = merged[-1]
            merged[-1] = (m[0], max(m[1], r), min(m[2], t), max(m[3], bt), max(m[4], bt - t))
        else:
            merged.append((l, r, t, bt, bt - t))
    return [(l, r, t, bt, h, crop[t:bt, l:r]) for l, r, t, bt, h in merged]


def normalized(img):
    #a digit's cell as a vector to match: cut to its ink (less specks at the cell's edges, a neighbouring colon's dots),
    #padded to the cell's shape about its middle, scaled to GLYPH, blurred a little so a stroke a pixel
    #off still matches, dark as 1, of length 1
    img = np.ascontiguousarray(img)
    ink = img < 150
    lab, n = ndimage.label(ink, structure=np.ones((3, 3)))
    keep = np.zeros_like(ink)
    pieces = [(sl, lab[sl] == k + 1) for k, sl in enumerate(ndimage.find_objects(lab))]
    pieces = [(sl, piece) for sl, piece in pieces if piece.sum() >= 4
              and not ((sl[1].start == 0 or sl[1].stop == img.shape[1]) and piece.sum() < 0.15 * ink.sum())]
    if pieces:
        #the biggest piece, and those within a few pixels of it up and down (a faint digit's other pieces)
        main = max(pieces, key=lambda p: p[1].sum())[0]
        for sl, piece in pieces:
            if sl[0].start <= main[0].stop + 3 and sl[0].stop >= main[0].start - 3:
                keep[sl] |= piece
    cols, rows = np.nonzero(keep.any(0))[0], np.nonzero(keep.any(1))[0]
    if len(cols):
        img = np.where(keep, img, 255)[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    h, w = img.shape
    want = int(round(h * GLYPH[0] / GLYPH[1]))
    if w < want:
        left = (want - w) // 2
        img = np.pad(img, ((0, 0), (left, want - w - left)), constant_values=255)
    elif w > want:
        extra = int(round(w * GLYPH[1] / GLYPH[0])) - h
        img = np.pad(img, ((extra // 2, extra - extra // 2), (0, 0)), constant_values=255)
    im = Image.fromarray(img.astype(np.uint8)).resize(GLYPH, Image.BILINEAR)
    v = ndimage.gaussian_filter(1 - np.asarray(im, dtype=float) / 255, 0.8).ravel()
    return v / (np.linalg.norm(v) + 1e-9)


#where a time's digits are, in characters from its last: h:mm:ss, h:mm:ss.h, h:mm:ss.hh
DIGIT_CELLS = {5: (6, 4, 3, 1, 0), 6: (8, 6, 5, 3, 2, 0), 7: (9, 7, 6, 4, 3, 1, 0)}


def time_counts(year, page=None):
    #the counts of digits the year's times have: TIME_DIGITS, a number or a tuple (1976 types some with tenths and some
    #with hundredths)
    n = setting(year, 'TIME_DIGITS', page)
    return tuple(n) if isinstance(n, (tuple, list)) else (n,)


def time_digits(year, page, col, line):
    #the time's digits, cut out on the typewriter's (or printer's) grid: the grid set by where the time's glyphs of a
    #character's width sit (a copy can be a little larger or smaller than another), its last digit the last cell with
    #ink, its other digits so many cells before it. a list of (left, right, top, bottom, image) for each, empty when
    #there's too little ink
    gs = glyphs(year, page, col, line)
    pitch = setting(year, 'PITCH', page)
    #a pen's line down the page is taller than a line
    gs = [g for g in gs if g[3] - g[2] <= setting(year, 'LINE_HEIGHT', page)[1] and (g[5] < 150).sum() >= 6]
    single = np.array([(g[0] + g[1]) / 2 for g in gs if g[1] - g[0] <= 1.2 * pitch])
    if len(single) < 3:
        return []
    #the pitch, within 8% of the year's (or 15%, where none within 8% fits well: a line typed on another machine), and
    #the phase that the glyphs' middles fit best
    fit_of = lambda q: abs(np.exp(2j * np.pi * single / q).mean())
    pitch0, pitch = pitch, max(pitch * np.arange(0.92, 1.0801, 0.004), key=fit_of)
    if fit_of(pitch) < 0.85:
        pitch = max(pitch0 * np.arange(0.85, 1.1501, 0.004), key=fit_of)
    phase = (np.angle(np.exp(2j * np.pi * single / pitch).mean()) / (2 * np.pi)) % 1 * pitch
    gray = level_page(year, page)
    x0 = setting(year, 'COLUMNS', page)[col][0]
    a, _ = fields_of(year, page, col)['time']
    #the digits' own rows: from the top of the tallest glyphs to their foot
    tall = [g for g in gs if g[3] - g[2] >= 0.75 * max(h[3] - h[2] for h in gs)]
    origin = max(0, field_rows(year, page, col, line, 'time')[0] - 2)
    top = origin + min(g[2] for g in tall)
    bottom = origin + max(g[3] for g in tall)
    ink = gray[max(0, top):bottom] < 150
    full = 0.15 * (bottom - top) * (pitch - 4)

    def cell(k):
        l = x0 + a + phase + k * pitch - pitch / 2
        return int(round(l)), int(round(l + pitch))

    def inked(k):
        l, r = cell(k)
        return ink[:, max(0, l + 2):max(0, r - 2)].sum()

    #the time's digits and last digit: of the counts the year's times have, and the cells up to the last with ink, the
    #pair that puts digits where there's ink (as much as a digit's, and none with less than half that) and no more
    #than a colon's where the colons and points are, and leaves the least ink after it (where a point typed after the
    #time, a speck or a pen's mark can be)
    right = int(np.floor((max(g[1] for g in gs) - 2 - phase + pitch / 2) / pitch))
    first = int(np.ceil((-pitch / 3 - phase + pitch / 2) / pitch))

    def fit(option):
        n, e = option
        digits = DIGIT_CELLS[n]
        marks = [k for k in range(max(digits)) if k not in digits]
        return (sum(min(inked(e - k), full) - full * (inked(e - k) < full / 2) for k in digits)
                - 2 * sum(max(0, inked(e - k) - 0.9 * full) for k in marks)
                - sum(min(inked(e + k), full) for k in (1, 2)))

    options = [(n, e) for n in time_counts(year, page) for e in range(right - 6, right + 1)
               if e - max(DIGIT_CELLS[n]) >= first]
    if not options:
        return []
    n, last = max(options, key=fit)
    cells = []
    for k in DIGIT_CELLS[n]:
        l, r = cell(last - k)
        cells.append((l, r, top, bottom, gray[max(0, top):bottom, l:r]))
    return cells


def digit_text(words):
    text = ''.join(words).translate(str.maketrans({'O': '0', 'o': '0', 'l': '1', 'I': '1', 'S': '5', 'B': '8'}))
    return re.sub(r'\D', '', text)


def digit_image(img):
    #a digit's cell as the network sees it: normalized, as an image with ink 1 at its darkest
    v = normalized(img).reshape(GLYPH[1], GLYPH[0])
    return (v / (v.max() + 1e-9)).astype(np.float32)


def cell_digits(chars, cells, pitch):
    #tesseract's digit in each cell: the digit whose box starts in it (its boxes' right edges are loose), but a box as
    #wide as two characters (two read as one)
    digits = [(left, t) for left, right, t in chars if t.isdigit() and right - left <= 1.5 * pitch]
    return [next((t for left, t in digits if l <= left + 0.4 * pitch < r), '') for l, r, *_ in cells]


def pinned(lines, firsts):
    #the leading digits a class's order pins: where the times either side of a line (as first read, of those in order
    #in its class) share an hour, or an hour and a minute's tens, or the whole minute, so does the line's. {(line,
    #digit's place): digit}
    out = {}
    for label in set(l[3] for l in lines):
        members = [n for n in range(len(lines)) if lines[n][3] == label]
        secs = [seconds(formatted(firsts[n])) if len(firsts[n]) >= 5 else np.nan for n in members]
        ok = [n for n, keep in zip(members, in_order(secs)) if keep]
        for n in members:
            before = [m for m in ok if m < n]
            after = [m for m in ok if m > n]
            if not before or not after:
                continue
            a, b = firsts[before[-1]], firsts[after[0]]
            for k in range(3):
                if a[:k + 1] == b[:k + 1]:
                    out[(n, k)] = a[k]
    return out


def read_times(year, lines):
    #each line's time digits: (digits, second choices, how sure each is (0-9), each digit's cost in log odds against
    #the best at each place). each digit cell has its readings: tesseract's two (character by character, at twice and
    #three times the size), its nearest neighbours' among the cells whose digit is known (tesseract read it the same at
    #both sizes, or the class's order pins it), and in a year of 600 such cells or more, a small network's
    #(line_printer's) learned from those whose nearest neighbours agree (tesseract reads a faint 3 as a 5 or a 2 as a 7
    #now and then, and some typewriters' 4 as almost anything). a digit takes the one the readings lean to most, the
    #network's in log odds, each of tesseract's and its pinned digit counting for so many more. the cells are read
    #twice, the second time with the digits the first reading pins
    cells, tess, owner = [], [], []
    for n, (page, col, line, _) in enumerate(lines):
        reading = readings(year).get((page, col, line[0]), {})
        found = time_digits(year, page, col, line)
        readings_here = [cell_digits(reading.get(key, []), found, setting(year, 'PITCH', page)) for key in ('c2', 'c3')]
        for k, (l, r, *_rest, img) in enumerate(found):
            cells.append(digit_image(img))
            tess.append([digits[k] for digits in readings_here])
            owner.append((n, k))
    out = [['', '', '', []] for _ in lines]
    if not cells:
        return out
    cells = np.array(cells)
    flat = cells.reshape(len(cells), -1)
    unit = flat / (np.linalg.norm(flat, axis=1, keepdims=True) + 1e-9)
    chars = list(DIGITS)
    pins = {}
    for _ in range(2):
        labels = np.array([pins.get(o, t[0] if t[0] and t[0] == t[1] else '') for o, t in zip(owner, tess)])
        known = np.nonzero(labels != '')[0]
        neighbours = np.zeros((len(cells), len(chars)))
        for i in range(len(cells)):
            sims = unit[known] @ unit[i]
            sims[known == i] = -1
            for d in labels[known[np.argsort(-sims)[:NEIGHBOURS]]]:
                neighbours[i, chars.index(d)] += 1
        agree = [i for i in known if chars[int(np.argmax(neighbours[i]))] == labels[i]]
        score = neighbours / NEIGHBOURS * NEIGHBOUR_SWAY
        for i, t in enumerate(tess):
            for d in t:
                if d:
                    score[i, chars.index(d)] += TESSERACT_SWAY
            if owner[i] in pins:
                score[i, chars.index(pins[owner[i]])] += PIN_SWAY
        if len(agree) >= 600:
            final = {d: np.array([(i, 0) for i in agree if labels[i] == d]) for d in DIGITS}
            final = {d: v for d, v in final.items() if len(v) >= 8}
            #a year's few thousand digits, in small batches so the network takes enough steps. a digit it hasn't
            #learned scores below its every other choice
            model = network(cells[:, None], final, batch=16, epochs=25)
            learned = np.stack([scores(x, model) for x in shifted(cells)]).max(0)
            net = np.repeat(learned.min(1, keepdims=True) - 1, len(chars), 1)
            for j, d in enumerate(model[1]):
                net[:, chars.index(d)] = learned[:, j]
            score += net
        best = np.array(chars)[score.argmax(1)]
        firsts = [''] * len(lines)
        for i, (n, k) in enumerate(owner):
            firsts[n] += best[i]
        pins = pinned(lines, firsts)
    order = np.argsort(-score, 1)
    top = np.take_along_axis(score, order[:, :2], 1)
    for i, (n, k) in enumerate(owner):
        out[n][0] += chars[order[i, 0]]
        out[n][1] += chars[order[i, 1]]
        #the log odds of the best over the runner-up, in steps of 2
        out[n][2] += str(min(9, int((top[i, 0] - top[i, 1]) / 2)))
        #and what each digit would cost, against the best
        out[n][3].append({d: float(top[i, 0] - score[i, j]) for j, d in enumerate(chars)})
    return out


def formatted(digits, n=None):
    #'44805' as 4:48:05, '4481523' as 4:48:15.23: a time of as many digits as the year's times have (any count when n
    #is None)
    if (n is not None and len(digits) not in (n if isinstance(n, tuple) else (n,))) or len(digits) < 5:
        return ''
    t = '{}:{}:{}'.format(digits[0], digits[1:3], digits[3:5])
    if len(digits) > 5:
        t += '.' + digits[5:]
    return t


def seconds(t):
    if not t:
        return np.nan
    h, m, s = t.split(':')
    if int(m) > 59 or float(s) >= 60:
        return np.nan
    return int(h) * 3600 + int(m) * 60 + float(s)


def in_order(secs, weights=None):
    #which times are in order: those in the run of times that never go down with the most weight (by default, the
    #longest), the rest being misread or out of place. unreadable ones never are
    secs = list(secs)
    weights = [1.0] * len(secs) if weights is None else list(weights)
    best, prev = [], []
    for i, s in enumerate(secs):
        if np.isnan(s):
            best.append(0.0)
            prev.append(-1)
            continue
        options = [(best[j], j) for j in range(i) if not np.isnan(secs[j]) and secs[j] <= s]
        total, j = max(options) if options else (0.0, -1)
        best.append(total + weights[i])
        prev.append(j)
    keep = set()
    if best and max(best):
        i = int(np.argmax(best))
        while i >= 0:
            keep.add(i)
            i = prev[i]
    return [i in keep for i in range(len(secs))]


#what leaving a time out of a class's order costs, against changing its digits (in log odds), and how many times in a
#row can be left out
LEFT_OUT = 25
MOST_LEFT_OUT = 3


def repair_times(times, digits):
    #a class's times put in order at least cost: each time as read (costing nothing), or with one digit changed
    #(costing what the reading says that digit costs), or two of its three least sure, or left out of the order as it
    #is (costing LEFT_OUT), the times kept in order never going down
    options = []
    for t, d in zip(times, digits):
        here = [(0.0, t)] if not np.isnan(seconds(t)) else []
        if d[0] and d[3]:
            text, costs = d[0], d[3]
            here += [(costs[j][c], formatted(text[:j] + c + text[j + 1:])) for j in range(len(text)) for c in costs[j]
                     if c != text[j]]
            #and two digits changed, of the three least sure, each to one of its next three choices
            weak = sorted(range(len(text)), key=lambda j: int(d[2][j]))[:3]
            for j, k in itertools.combinations(sorted(weak), 2):
                for a in sorted(costs[j], key=costs[j].get)[1:4]:
                    for b in sorted(costs[k], key=costs[k].get)[1:4]:
                        here.append((costs[j][a] + costs[k][b],
                                     formatted(text[:j] + a + text[j + 1:k] + b + text[k + 1:])))
        options.append([(c, t, seconds(t)) for c, t in here if not np.isnan(seconds(t))])
    #best[i][k]: the least cost of times 0..i with time i taking its option k, and the option before it kept
    best, back = [], []
    for i, opts in enumerate(options):
        best.append([])
        back.append([])
        for cost, t, sec in opts:
            here, came = cost + LEFT_OUT * i, None
            for j in range(max(0, i - MOST_LEFT_OUT - 1), i):
                for k, (c2, t2, sec2) in enumerate(options[j]):
                    if sec2 <= sec and best[j][k] + cost + LEFT_OUT * (i - j - 1) < here:
                        here, came = best[j][k] + cost + LEFT_OUT * (i - j - 1), (j, k)
            best[-1].append(here)
            back[-1].append(came)
    end = [(best[i][k] + LEFT_OUT * (len(times) - i - 1), i, k) for i in range(len(times))
           for k in range(len(best[i]))]
    out = list(times)
    if not end:
        return out
    _, i, k = min(end)
    while True:
        out[i] = options[i][k][1]
        if back[i][k] is None:
            break
        i, k = back[i][k]
    return out


#---------------------------------------------------------------- names and towns

def best_words(reading, field, x0, fields, counts):
    #a field's words from the reading with the most words seen in the clean results, less half the words of two
    #letters or more that aren't (the first reading on a tie)
    best, score = [], -np.inf
    for words in word_readings(reading):
        words = field_words(words, field, x0, fields)
        keys = [re.sub(r'[^A-Z]', '', w.upper()) for w in words]
        s = sum(counts[k] > 0 for k in keys) - 0.5 * sum(counts[k] == 0 for k in keys if len(k) > 1)
        if s > score:
            best, score = words, s
    return best


def clean_word(word):
    #a word without the specks tesseract reads either side of it as marks
    return re.sub(r"^[^A-Z]+|[^A-Z.]+$", '', word.upper())


#letters tesseract reads for others in the typewriters' faces
LOOKALIKES = {'V': 'Y', 'Y': 'V', 'I': 'LT', 'L': 'I', 'T': 'I', 'R': 'K', 'K': 'R', 'E': 'C', 'C': 'EO', 'O': 'C',
              'N': 'HU', 'H': 'N', 'U': 'N', 'M': 'N'}


def known_name(word, counts, common=3):
    #a name not seen in the clean results, as the one seen there at least `common` times that up to two of its letters
    #read as their lookalikes make (TAVIOR: TAYLOR, RERN: KERN)
    if len(word) < 3 or counts[word] or not word.isalpha():
        return word
    options = [[(c, 0)] + [(o, 1) for o in LOOKALIKES.get(c, '')] for c in word]
    fits = {''.join(c for c, _ in v) for v in itertools.product(*options) if 0 < sum(k for _, k in v) <= 2}
    fits = [f for f in fits if counts[f] >= common]
    return fits[0] if len(fits) == 1 else word


def separated(text):
    #a printout's name, surname first, with what tesseract makes of its separator (s, +, *, ?) as a comma
    if ',' in text:
        return text
    marks = '[+*?•·�.]'
    return re.sub(r'(?<=[A-Z])\s*(?:{0}+s?|s){0}*\s*(?=[A-Z])'.format(marks), ',', text, count=1)


@functools.lru_cache(maxsize=None)
def name_vocabulary(least=3):
    #the names seen at least `least` times in the clean results, by length
    first, last, either, town = word_counts()
    out = {}
    for w, n in either.items():
        if n >= least and len(w) >= 3:
            out.setdefault(len(w), []).append(w)
    return out


@functools.lru_cache(maxsize=None)
def near_name(word, ratio=0.84, margin=0.04):
    #a name word of five letters or more not seen in the clean results, as the one seen there that's nearest it (a
    #letter or two misread, dropped or doubled), where one is clearly nearest: SCHNEITOER: SCHNEIDER. for a year
    #tesseract reads badly (NEAR_NAMES), since it makes a rare name a common one now and then (BOHMER: BOEHMER)
    first, last, either, town = word_counts()
    if len(word) < 5 or either[word] or not word.isalpha():
        return word
    scored = []
    for n in range(len(word) - 2, len(word) + 3):
        for w in name_vocabulary().get(n, []):
            m = difflib.SequenceMatcher(None, word, w)
            if m.real_quick_ratio() >= ratio and m.quick_ratio() >= ratio:
                r = m.ratio()
                if r >= ratio:
                    scored.append((r, either[w], w))
    scored.sort(reverse=True)
    if scored and (len(scored) == 1 or scored[0][0] - scored[1][0] >= margin):
        return scored[0][2]
    return word


def name_parts(text, order, points=False):
    #a name as the other years print it (first names, then surname), and its first and last names. 'first': "Ernie St.
    #Germaine", 'last': "HARJU, Dave" or "ARVNES,BJORN". a lone letter after a surname printed last is a speck, and
    #one before the first name without a point after it
    text = re.sub(r'\s+', ' ', text.upper().replace('.', '. ')).strip(' ,')
    if order == 'last':
        last, _, first = text.partition(',')
        if not _:
            return first_name_first(' '.join(w for w in (clean_word(w).strip('.') for w in text.split()) if w))
        last = [w for w in (clean_word(w).strip('.') for w in last.split()) if w]
        #a lone letter before a surname is a speck by the place (28' J DUEDE)
        while len(last) > 1 and len(last[0]) == 1:
            last.pop(0)
        last = ' '.join(last)
        first = [clean_word(w) for w in first.split()]
        #where the typist put a point after each initial (POINTS), a lone letter without one is a speck
        first = [w.strip('.') for w in first if w.strip('.') and not (points and len(w) == 1)]
        suffix = [w for w in first if w in SUFFIXES]
        first = [w for w in first if w not in SUFFIXES]
        last = ' '.join([last] + suffix)
        return {'name': ' '.join(first + [last]), 'first': ' '.join(first), 'last': last}
    words = [w for w in (clean_word(w).strip('.') for w in text.split()) if w]
    suffix = [w for w in words[1:] if w in SUFFIXES]
    words = [w for w in words if w not in SUFFIXES]
    while len(words) > 2 and len(words[-1]) == 1:
        words.pop()
    if len(words) > 2 and len(words[0]) == 1 and not re.match(r'\W*[A-Z]\.', text):
        words.pop(0)
    if not words:
        return {'name': '', 'first': '', 'last': ''}
    n = len(words) - 1
    while n > 1 and words[n - 1] in PARTICLES:
        n -= 1
    first, last = words[:n], ' '.join(words[n:] + suffix)
    return {'name': ' '.join(first + [last]), 'first': ' '.join(first), 'last': last}


#letters tesseract reads for others in a state's name
STATE_LOOKS = {'T': 'I', '1': 'IL', 'L': 'I', 'I': 'L', '0': 'O', '5': 'S', 'N': 'M', 'M': 'N', 'H': 'N', 'V': 'W',
               'U': 'N'}


def region(key, city=''):
    #a state or country as typed (WIS, Minn, Norway, MN), or as its letters misread make it (the one, or the one the
    #town is seen in in the clean results): (state, country)
    if key in COUNTRY_WORDS:
        return '', COUNTRY_WORDS[key]
    state = key if key in US_STATES | CA_PROVINCES else STATE_WORDS.get(key, '')
    if not state and 2 <= len(key) <= 7:
        variants = {''.join(v) for v in itertools.product(*[{c} | set(STATE_LOOKS.get(c, '')) for c in key])}
        fits = {STATE_WORDS.get(v, v) for v in variants
                if v in STATE_WORDS or (len(v) == 2 and v in US_STATES | CA_PROVINCES)}
        if len(fits) > 1:
            town = re.sub(r'[^A-Z ]', '', city.upper().replace('ST. ', 'ST '))
            fits = {f for f in fits if town_counts().get(f, collections.Counter())[town]}
        state = fits.pop() if len(fits) == 1 else ''
    if not state:
        return '', ''
    return state, 'USA' if state in US_STATES else 'CAN'


def place_of(words):
    #where a skier's from: "Wausau, Wi.", "Minneapolis, MN", "Norway", "Winnipeg, Canada": (city, state, country). a
    #club typed after it in brackets, or a speck or two after the state, is left out
    text = re.sub(r'\(.*', '', ' '.join(words))
    words = [w for w in (clean_word(w) for w in text.replace(',', ', ').split()) if w]
    text = re.sub(r'\s+', ' ', ' '.join(words)).strip(' ,.')
    if not text:
        return '', '', ''
    parts = text.split()
    for end in range(len(parts), max(0, len(parts) - 2), -1):
        head = ' '.join(parts[:end])
        if ',' in head:
            city, typed = head.rsplit(',', 1)
        else:
            city, typed = ' '.join(parts[:end - 1]), parts[end - 1]
        if end < len(parts) and any(len(re.sub(r'[^A-Z]', '', w)) > 2 for w in parts[end:]):
            break
        state, country = region(re.sub(r'[^A-Z0-9]', '', typed.upper()), city)
        if country:
            city = city.strip(' ,.').upper()
            #a lone letter before a town known in its state is a speck (E MINNEAPOLIS)
            if re.match(r'[A-Z] ', city) and town_counts().get(state, collections.Counter())[city[2:]]:
                city = city[2:]
            return known_town(city, state), state, country
    return text.replace(',', ' ').upper(), '', ''


def printed_place(reading, x0, fields, town):
    #a printout's town, state and country in their own columns (1977's: STEVENS PT, WI, USA; OSLO 3, , NORWAY)
    city = ' '.join(best_words(reading, 'town', x0, fields, town)).upper()
    st = re.sub(r'[^A-Z0-9]', '', ''.join(next((field_words(w, 'st', x0, fields) for w in word_readings(reading)
                                                  if field_words(w, 'st', x0, fields)), [])).upper())
    nat = re.sub(r'[^A-Z]', '', ''.join(next((field_words(w, 'nat', x0, fields) for w in word_readings(reading)
                                               if field_words(w, 'nat', x0, fields)), [])).upper())
    state, country = region(st, city) if st else ('', '')
    if nat:
        country = COUNTRY_WORDS.get(nat, region(nat)[1] or country)
    if country not in ('USA', 'CAN', ''):
        state = ''
    city = re.sub(r'[^A-Z. ]', '', city).strip(' .')
    #a lone letter after the town is the edge of the next column's, and one before it the bib's, where the rest is a
    #town known in its state
    city = re.sub(r' [A-Z]$', '', city)
    if re.match(r'[A-Z] ', city) and town_counts().get(state, collections.Counter())[city[2:]]:
        city = city[2:]
    return (known_town(city, state) if state else city), state, country


def known_town(city, state, common=3):
    #a town not seen in its state in the clean results, as the one town seen there at least `common` times that's a
    #letter off it (TRONWOOD: IRONWOOD)
    towns = town_counts().get(state)
    key = re.sub(r'[^A-Z ]', '', city.replace('ST. ', 'ST '))
    if not towns or not key or towns[key]:
        return city
    fits = [t for t, n in towns.items() if n >= common and len(t) == len(key) and len(key) >= 5
            and sum(a != b for a, b in zip(t, key)) == 1]
    return fits[0] if len(fits) == 1 else city


#---------------------------------------------------------------- parse

def hand(year, page, col, top):
    #what the year's HAND says of a line (keyed by page, column and the line's top, give or take half a line): what's
    #written on the page by hand, or can't be read for a pen's marks
    for (p, c, y), what in getattr(layout(year), 'HAND', {}).items():
        if p == page and c == col and abs(y - top) <= setting(year, 'LINE_PITCH', page) / 2:
            return what
    return {}


def read_lines(year):
    #every result line read, in each race: a row each, with its class, its column and its digits' readings
    unnumbered = getattr(layout(year), 'UNNUMBERED', set())
    #a line HAND gives a time, or says is a result, is one whatever its ink
    lines = [l for l in sections(year) if not hand(year, l[0], l[1], l[2][0]).get('drop')
             and (is_result(year, *l[:3], numbered=l[3] not in unnumbered)
                  or {'time', 'result'} & set(hand(year, l[0], l[1], l[2][0])))]
    digits = read_times(year, lines)
    n = time_counts(year)
    for i, (page, col, line, _) in enumerate(lines):
        if not digits[i][0]:
            #no cells to read (a pen's mark across the time): tesseract's digits, where there are as many as a time has
            reading = readings(year).get((page, col, line[0]), {})
            x0 = setting(year, 'COLUMNS', page)[col][0]
            for words in [reading.get('c2', []), reading.get('c3', [])] + word_readings(reading):
                d = digit_text(field_words(words, 'time', x0, fields_of(year, page, col)))
                if len(d) in n:
                    digits[i] = [d, d, '0' * len(d), [{ch: 0.0 if ch == c else 1.0 for ch in DIGITS} for c in d]]
                    break
    classes = layout(year).CLASSES
    first, last, either, town = word_counts()
    rows = []
    for (page, col, line, label), d in zip(lines, digits):
        x0 = setting(year, 'COLUMNS', page)[col][0]
        fields = fields_of(year, page, col)
        reading = readings(year).get((page, col, line[0]), {})
        mine = hand(year, page, col, line[0])
        name = mine.get('name') or ' '.join(best_words(reading, 'name', x0, fields, either))
        if 'town' in mine:
            where = place_of(mine['town'].split())
        elif 'st' in fields:
            where = printed_place(reading, x0, fields, town)
        elif 'town' in fields:
            where = place_of(best_words(reading, 'town', x0, fields, town))
        else:
            where = ('', '', '')
        bib = ''
        if 'bib' in fields:
            #the bib its readings agree on most, where two or more do
            reads = collections.Counter(d for d in (digit_text(field_words(w, 'bib', x0, fields))
                                                    for w in word_readings(reading))
                                        if len(d) == setting(year, 'BIB_DIGITS', page, 4))
            if reads and reads.most_common(1)[0][1] >= 2:
                bib = reads.most_common(1)[0][0].lstrip('0')
        printed = next((''.join(field_words(words, 'place', x0, fields)) for words in word_readings(reading)
                        if field_words(words, 'place', x0, fields)), '').translate(PLACE_LOOKS)
        gender, age_group, race = classes[label]
        rows.append({'label': label, 'race': race, 'gender': mine.get('gender', gender),
                     'age_group': mine.get('age_group', age_group),
                     'printed': printed, 'raw_name': name, 'bib': bib, 'city': where[0], 'state': where[1],
                     'country': where[2],
                     'time': formatted(d[0], n), 'digits': d, 'hand_time': mine.get('time', ''), 'page': page,
                     'col': col, 'top': line[0]})
    df = pd.DataFrame(rows)
    df['time'] = df['time'].astype(object)
    for label, c in df.groupby('label', sort=False):
        df.loc[c.index, 'time'] = repair_times(list(c['time']), list(c['digits']))
    #a time written in by hand, and the line moved to where that time puts it in its class
    df['time'] = df['hand_time'].where(df['hand_time'] != '', df['time'])
    for label, c in df.groupby('label', sort=False):
        moved = c[c['hand_time'] != '']
        order = [i for i in c.index if i not in moved.index]
        for i in moved.index:
            t = seconds(df.at[i, 'time'])
            at = next((k for k, j in enumerate(order) if seconds(df.at[j, 'time']) > t), len(order))
            order.insert(at, i)
        df.loc[order, 'class_rank'] = class_ranks(df.loc[order])
    #a skier listed in a class not theirs (1974's women's champion, among the men) has no class rank
    df.loc[df['age_group'] != [classes[l][1] for l in df['label']], 'class_rank'] = np.nan
    order = setting(year, 'NAME_ORDER')
    if order == 'last':
        df['raw_name'] = [separated(name).replace(',', ', ') for name in df['raw_name']]
    df['raw_name'] = [' '.join(known_name(w, either) for w in name.upper().split()) for name in df['raw_name']]
    if setting(year, 'NEAR_NAMES', default=False):
        df['raw_name'] = [re.sub(r'[A-Z]+', lambda m: near_name(m.group()), name) for name in df['raw_name']]
    points = setting(year, 'POINTS', default=False)
    parts = pd.DataFrame([name_parts(t, order, points) for t in df['raw_name']], index=df.index)
    df[['name', 'first', 'last']] = parts[['name', 'first', 'last']]
    df['city'] = [expand_town(c, st) for c, st in zip(df['city'], df['state'])]
    #a bib read for two skiers is one misread, which, unknown
    if 'bib' in df:
        df.loc[df['bib'].duplicated(keep=False) & (df['bib'] != ''), 'bib'] = ''
    return df


def parse(year):
    df = read_lines(year)
    birkie = df[df['race'] == 'birkie'].copy()
    birkie['secs'] = birkie['time'].map(seconds)
    birkie['place'] = birkie.groupby('gender')['secs'].rank(method='first').astype('Int64')
    birkie = birkie.sort_values(['gender', 'place'], ascending=[False, True])
    birkie['age'] = ''
    birkie['status'] = 'finished'
    birkie['tech'] = ''
    birkie['class_rank'] = birkie['class_rank'].astype('Int64')
    return birkie[['place', 'bib', 'name', 'first', 'last', 'gender', 'age', 'age_group', 'city', 'state', 'country',
                   'time', 'status', 'tech', 'class_rank', 'page', 'top']].reset_index(drop=True)


def field_ink(year, page, col, line, field):
    #the ink in a field's own rows of a line
    gray = level_page(year, page)
    x0 = setting(year, 'COLUMNS', page)[col][0]
    a, b = fields_of(year, page, col)[field]
    top, bottom = field_rows(year, page, col, line, field)
    return int((gray[top:bottom, x0 + a:x0 + b] < 150).sum())


@functools.lru_cache(maxsize=None)
def typical_time_ink(year, page, col):
    #how much ink a time has in a column: the middle of its lines' times'
    inks = [field_ink(year, page, col, line, 'time') for line in column_lines(year, page, col)]
    inks = [i for i in inks if i > 50]
    return float(np.median(inks)) if inks else 0.0


def is_result(year, page, col, line, numbered=True):
    #a result line has a time (a third of a time's ink or more, in its own rows: a club's line below a name can catch
    #the edge of a time typed askew) and ink where the place is (or, in a class whose places aren't printed, the name)
    if field_ink(year, page, col, line, 'time') < max(20, typical_time_ink(year, page, col) / 3):
        return False
    return field_ink(year, page, col, line, 'place' if numbered else 'name') >= 20


def class_ranks(c):
    #each line's count in its class, a line with the number and time of the line before it sharing its rank
    ranks, rank = [], 0
    prev_printed, prev_time = None, None
    for printed, t in zip(c['printed'], c['time']):
        if printed and printed == prev_printed and t == prev_time:
            ranks.append(rank)
        else:
            rank = len(ranks) + 1
            ranks.append(rank)
        prev_printed, prev_time = printed, t
    return ranks


#---------------------------------------------------------------- surveying a year's pages

def survey(year, page):
    #each line on a page, column by column, with tesseract's reading at twice the size: for finding the headings
    for col in range(len(setting(year, 'COLUMNS', page))):
        for line in column_lines(year, page, col):
            img, x0 = line_crop(year, page, col, line)
            text = ' '.join(tesseract(img, 2)['text'])
            print(page, col, line[0], line[1] - line[0], 'R' if is_result(year, page, col, line) else ' ', text)
