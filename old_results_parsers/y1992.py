#1992's birch scroll results (pages 26-45): one result to a line, two columns to a page, printed in a fixed-pitch font
#   RANK  CLS  FINAL TIME  BIB  NAME  HOMETOWN  ST  NAT  CLASS ("M25-29")  CL RANK  25%  PACE (MN/KM)
#the men's list (3471 places) runs from page 26 to the top of page 42, the women's (511) from the bottom of page 42 to
#page 45. each list places classic and skate skiers together; a C in the CLS column marks a classic skier. pages 46-54
#are the kortelopet, in the same font and read the same way (k1992.py), page 20 the birkie's age class awards
#
#tesseract reads this font poorly (a "2:" often comes out as "22:", 1 and 3 swap), so each character is cut out of the
#page by the font's fixed pitch and read by comparing it with characters whose reading is known: digits from the rank
#column (the ranks count up by one down each column, so every rank digit is known), letters from the words tesseract
#read that are names or towns in the clean results. some letter pairs are printed run together or one over the other
#("OM", "MN", "UR"); a name or town word that isn't a known one is checked against tesseract's reading and the known
#words, a hometown against its state's known towns. the tables' own rules then mend what they pin down: times rise
#with place, age class ranks count up by one
import bisect
import functools
import importlib
import os
import re
import subprocess

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage

from birkie_archive import OCR_DIR, PAGE_DIR, TESSERACT, RESULT_CHARACTERS, parse_seconds
from results_loader import US_STATES, CA_PROVINCES, normalize_location

YEAR = 1992
PAGES = range(26, 46)
#the lists' sizes, from the last places printed (3471 on page 42, 511 on page 45)
LIST_SIZES = {'M': 3471, 'F': 511}
#the women's list starts with the second run of rows on page 42
WOMEN_FROM = (42, 1)
COURSE_KM = 52
CANVAS = (20, 14)
#the font's capitals and digits are 11 or 12 pixels tall
CAP_HEIGHT = 12
#the list being read: the birkebeiner's, laid out by this module's PAGES, LIST_SIZES, WOMEN_FROM, COURSE_KM, FIELDS,
#PACE and UPSIDE_DOWN, or the kortelopet's, printed after it in the same font and laid out the same way by k1992.py.
#parse() and ocr() set it
RACE_MODULES = {'birkie': 'y', 'kortie': 'k'}
race = 'birkie'


def layout():
    return importlib.import_module('old_results_parsers.{}{}'.format(RACE_MODULES[race], YEAR))


def use_race(name):
    #the pages' readings are kept by page, and the two lists' pages are apart, so nothing kept needs clearing
    global race
    race = name


#---------------------------------------------------------------- page geometry

@functools.lru_cache(maxsize=2)
def page_dark(page):
    return np.asarray(Image.open(os.path.join(PAGE_DIR, str(YEAR), '{:03d}.png'.format(page)))) < 128


def runs(on):
    d = np.diff(np.concatenate([[0], np.asarray(on).astype(np.int8), [0]]))
    return list(zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]))


def skew_angle(dark):
    #the angle that lines the text rows up best: dark pixels sheared by it pile into the sharpest row profile
    ys, xs = np.nonzero(dark)
    if len(ys) > 200000:
        idx = np.random.default_rng(0).choice(len(ys), 200000, replace=False)
        ys, xs = ys[idx], xs[idx]

    def score(ang):
        yy = ys - xs * np.tan(np.radians(ang))
        return (np.bincount(np.round(yy - yy.min()).astype(int)).astype(float) ** 2).sum()
    best = max(np.arange(-2.5, 2.501, 0.1), key=score)
    return max(np.arange(best - 0.1, best + 0.1001, 0.01), key=score)


def time_starts(band, pitch=11.0):
    #where a time ("2:15:11.6") starts in one row: nine glyphs a pitch apart with colons second and fifth and a point
    #eighth, by their shapes
    segs = runs(band.any(0))
    out = []

    def shape(s, e):
        rows = runs(band[:, s:e].any(1))
        if e - s > 5:
            return 'wide'
        if len(rows) == 2:
            return ':'
        if len(rows) == 1 and rows[0][0] > band.shape[0] / 2:
            return '.'
        return 'narrow'
    shapes = [shape(s, e) for s, e in segs]
    centers = [(s + e) / 2 for s, e in segs]
    for i in range(len(segs) - 8):
        if shapes[i + 1] == ':' and shapes[i + 4] == ':' and shapes[i + 7] == '.' and \
                all(abs(centers[i + j + 1] - centers[i + j] - pitch) < 3 for j in range(8)):
            out.append(centers[i] - pitch / 2)
    return out


def despeckle(d, min_size=5):
    #without the specks: groups of fewer than min_size touching dark pixels
    labels, n = ndimage.label(d, structure=np.ones((3, 3)))
    sizes = np.bincount(labels.ravel())
    return d & (sizes >= min_size)[labels]


def vertical_lines(d, min_len=45):
    #pixels in vertical dark runs longer than min_len: rules and page edges, not text
    out = np.zeros_like(d)
    padded = np.vstack([np.zeros((1, d.shape[1]), bool), d, np.zeros((1, d.shape[1]), bool)]).astype(np.int8)
    diff = np.diff(padded, axis=0)
    for x in np.nonzero(d.sum(0) >= min_len)[0]:
        for a, b in zip(np.nonzero(diff[:, x] == 1)[0], np.nonzero(diff[:, x] == -1)[0]):
            if b - a >= min_len:
                out[a:b, x] = True
    return out


class Half:
    #one column of results on a page, turned upright: its rows, the font's pitch and each row's character grid, counted
    #in characters from the start of the FINAL TIME field (k = 0)
    def __init__(self, page, side):
        self.page, self.side = page, side
        dark = page_dark(page)
        h, w = dark.shape
        self.angle = skew_angle(dark[:, :w // 2] if side == 0 else dark[:, w // 2:])
        rot = np.asarray(Image.fromarray((~dark).astype(np.uint8) * 255).rotate(
            self.angle, resample=Image.NEAREST, fillcolor=255)) < 128
        rot = rot & ~vertical_lines(rot)
        raw, rot = rot, despeckle(rot)
        self.center = (w / 2, h / 2)
        #rows first from a stretch that lies inside this column on every page, to find the time field by its colons
        lo, hi = (380, 1100) if side == 0 else (1520, 2300)
        rows = [(a, b) for a, b in runs(rot[:, lo:hi].sum(1) > 8) if 9 <= b - a <= 19]
        search = (150, 700) if side == 0 else (1250, 1750)
        starts = [s for a, b in rows for s in time_starts(rot[a:b, search[0]:search[1]])]
        if not starts:
            raise ValueError('no times found on page {} side {}'.format(page, side))
        t = search[0] + np.median(starts)
        self.x0 = int(max(t - 14 * 11.0, 0))
        self.d = rot[:, self.x0:int(t + 89 * 11.0)]
        #the page before its specks were taken out, for a digit printed so faintly that only specks are left of it
        self.raw = raw[:, self.x0:int(t + 89 * 11.0)]
        self.t = t - self.x0
        self.rows = [(a, b) for a, b in runs(self.d.sum(1) > 8) if 9 <= b - a <= 19]
        self.glyphs = [self.row_glyphs(a, b) for a, b in self.rows]
        self.fit_grid()
        self.find_results()

    def row_glyphs(self, a, b):
        #ink across the row, without specks (a pixel or two wide and a few pixels in all)
        ink = self.d[a:b].sum(0)
        return [(s, e) for s, e in runs(ink > 0) if e - s > 2 or ink[s:e].sum() > 6]

    def fit_grid(self):
        #the pitch that best fits the narrow glyphs' centres, and each row's own offset (rows shift a pixel or two)
        c = np.array([(s + e) / 2 for segs in self.glyphs for s, e in segs if 2 <= e - s <= 11])
        row = np.array([n for n, segs in enumerate(self.glyphs) for s, e in segs if 2 <= e - s <= 11])
        counts = np.bincount(row, minlength=len(self.glyphs))

        def score(p):
            z = np.exp(2j * np.pi * c / p)
            per_row = np.bincount(row, z.real, len(counts)) ** 2 + np.bincount(row, z.imag, len(counts)) ** 2
            return np.sum(np.sqrt(per_row)[counts >= 5] / counts[counts >= 5])
        p = max(np.arange(10.85, 11.25, 0.01), key=score)
        p = self.pitch = max(np.arange(p - 0.01, p + 0.0101, 0.001), key=score)
        z = np.exp(2j * np.pi * c / p)
        zs = np.bincount(row, z.real, len(counts)) + 1j * np.bincount(row, z.imag, len(counts))
        #glyph centres sit half a pitch after the cell's start; k = 0 is the time field's first character
        overall = self.t + p / 2
        self.phases = []
        for z in zs:
            ph = (np.angle(z) / (2 * np.pi) * p) % p if z != 0 else overall
            self.phases.append(overall + ((ph - overall + p / 2) % p) - p / 2)

    def cells(self, i):
        #{k: (x0, x1)}: row i's glyphs by their place in the character grid. glyphs that touch are cut where the ink is
        #thinnest near the grid's cell edges; pieces in the same cell are joined
        p, ph = self.pitch, self.phases[i]
        a, b = self.rows[i]
        out = {}
        for s, e in self.glyphs[i]:
            pieces = [(s, e)]
            n = int(round((e - s) / p))
            if n >= 2:
                ink = self.d[a:b, s:e].sum(0)
                #the grid's cell edges inside the run when there are as many as the run's width says, else even shares
                edges = [ph + (k + 0.5) * p for k in range(int((s - ph) / p) - 2, int((e - ph) / p) + 2)]
                edges = [x for x in edges if s + 2 < x < e - 2]
                if len(edges) != n - 1:
                    edges = [s + (e - s) * j / n for j in range(1, n)]
                cuts = []
                for edge in edges:
                    lo, hi = max(int(round(edge)) - 2, s + 1), min(int(round(edge)) + 3, e - 1)
                    cuts.append(lo + int(np.argmin(ink[lo - s:hi - s])))
                bounds = [s] + cuts + [e]
                pieces = [(x0, x1) for x0, x1 in zip(bounds[:-1], bounds[1:]) if x1 > x0]
            for x0, x1 in pieces:
                k = int(round(((x0 + x1) / 2 - ph) / p))
                if k in out:
                    x0, x1 = min(x0, out[k][0]), max(x1, out[k][1])
                out[k] = (x0, x1)
        #no wider than its cell and a pixel and a half either side: some letter pairs ("OH", "OM") are printed run
        #together, with a stroke between them that would otherwise stick to one
        clipped = {k: (max(x0, int(np.ceil(ph + (k - 0.5) * p - 1.5))), min(x1, int(ph + (k + 0.5) * p + 1.5)))
                   for k, (x0, x1) in out.items()}
        out = {k: (x0, x1) for k, (x0, x1) in clipped.items() if x1 > x0}
        #a pair printed one over the other ("UR", "HA") makes one glyph no wider than one, leaving a cell empty that
        #has a letter's worth of ink in its middle
        for k in range(min(out, default=0) + 1, max(out, default=0)):
            if k not in out:
                core = self.d[a - 1:b + 1, int(round(ph + (k - 0.5) * p + 2)):int(round(ph + (k + 0.5) * p - 2))]
                if core.sum() >= 25:
                    out[k] = (int(np.ceil(ph + (k - 0.5) * p - 1.5)), int(ph + (k + 0.5) * p + 1.5))
        return out

    def faded_lead(self, i, field):
        #whether the cell before a right-aligned number's first digit, inside its field, holds a few specks of ink: a
        #leading digit printed too faintly to read
        k0, k1 = layout().FIELDS[field]
        c = self.cells(i)
        ks = [k for k in range(k0, k1 + 1) if k in c]
        if not ks or min(ks) == k0:
            return False
        k = min(ks) - 1
        a, b = self.rows[i]
        x0 = int(round(self.phases[i] + (k - 0.5) * self.pitch + 1))
        x1 = int(round(self.phases[i] + (k + 0.5) * self.pitch - 1))
        return bool(self.raw[a - 1:b + 1, x0:x1].sum() >= 5)

    def glyph(self, i, x0, x1):
        #a glyph as a CANVAS bitmap, its ink's box centred, and that box's top (from the row's top), height and width
        a, b = self.rows[i]
        img = self.d[max(a - 4, 0):b + 4, x0:x1]
        cols = np.nonzero(img.any(0))[0]
        rows = np.nonzero(img.any(1))[0]
        out = np.zeros(CANVAS, bool)
        if not len(cols):
            return out, (0, 0, 0)
        if rows[-1] - rows[0] + 1 > CAP_HEIGHT + 1:
            #a speck above or below: the glyph is the cap height's worth of rows holding the most ink
            ink = img.sum(1)
            start = max(range(rows[0], rows[-1] - CAP_HEIGHT + 2), key=lambda s: ink[s:s + CAP_HEIGHT].sum())
            img = img.copy()
            img[:start] = False
            img[start + CAP_HEIGHT:] = False
            cols = np.nonzero(img.any(0))[0]
            rows = np.nonzero(img.any(1))[0]
        img = img[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1][:CANVAS[0], :CANVAS[1]]
        top, left = (CANVAS[0] - img.shape[0]) // 2, (CANVAS[1] - img.shape[1]) // 2
        out[top:top + img.shape[0], left:left + img.shape[1]] = img
        return out, (rows[0] - (a - max(a - 4, 0)), rows[-1] - rows[0] + 1, cols[-1] - cols[0] + 1)

    def page_xy(self, x, y):
        #a point of this half (upright) in the page image's pixels
        cx, cy = self.center
        th = np.radians(self.angle)
        rx, ry = x + self.x0 - cx, y - cy
        return cx + rx * np.cos(th) - ry * np.sin(th), cy + rx * np.sin(th) + ry * np.cos(th)

    def time_pattern(self, i):
        #nine glyphs from k = 0 with nothing either side, the second, fifth and eighth narrow (colons and a point)
        c = self.cells(i)
        a, b = self.rows[i]
        if not all(k in c for k in range(9)) or any(
                k in c and self.d[a:b, c[k][0]:c[k][1]].sum() > 20 for k in (-1, 9)):
            return False
        w = [c[k][1] - c[k][0] for k in range(9)]
        return sum(w[k] <= 5 for k in (1, 4, 7)) >= 2 and all(w[k] >= 4 for k in (0, 2, 3, 5, 6, 8))

    def find_results(self):
        #the rows with a time. a row whose offset was taken a whole character off is moved back
        self.results = []
        for i in range(len(self.rows)):
            for shift in (0, -1, 1):
                self.phases[i] += shift * self.pitch
                if self.time_pattern(i):
                    self.results.append(i)
                    break
                self.phases[i] -= shift * self.pitch


#each field's characters, counted from the time's first (k = 0)
FIELDS = {'rank': (-12, -9), 'cls': (-7, -3), 'time': (0, 8), 'bib': (11, 14), 'name': (16, 41), 'city': (42, 58),
          'state': (59, 61), 'country': (62, 65), 'class': (67, 72), 'class_rank': (74, 77), 'club': (79, 81),
          'pace': (83, 88)}
#the PACE column's digits: the minutes' and the seconds' two. (a layout with room for a pace of ten minutes or more
#puts the tens of minutes' place first)
PACE = (84, 86, 87)
#the age classes the CLASS column prints
AGES = ('18-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', '65-69', '70+')


@functools.lru_cache(maxsize=None)
def half(page, side):
    return Half(page, side)


def result_rows():
    #every result row in reading order, split into runs where the rows stop (a table's end). the men's list fills
    #pages 26-41 and the first run of page 42, the women's list the rest (the kortelopet's split the same way on page
    #51); each list's places count up by one down the columns (the rows found match the last places printed exactly,
    #and the rank digits read back the same)
    lay = layout()
    out = []
    for page in lay.PAGES:
        for side in (0, 1):
            h = half(page, side)
            rows = h.results
            run = 0
            for n, i in enumerate(rows):
                if n and h.rows[i][0] - h.rows[rows[n - 1]][0] > 60:
                    run += 1
                a, _ = h.rows[i]
                out.append({'page': page, 'side': side, 'run': run, 'i': i, 'y': a,
                            'top': int(round(h.page_xy(h.phases[i], a)[1])), 'bib_faded': h.faded_lead(i, 'bib')})
    rows = pd.DataFrame(out)
    women_from = lay.WOMEN_FROM
    women = (rows['page'] > women_from[0]) | ((rows['page'] == women_from[0]) & (rows['run'] >= women_from[1]))
    rows['gender'] = np.where(women, 'F', 'M')
    rows['place'] = rows.groupby('gender').cumcount() + 1
    found = rows.groupby('gender').size().to_dict()
    if found != lay.LIST_SIZES:
        print('1992 {}: found {} results, the lists end at {}: places are off'.format(race, found, lay.LIST_SIZES))
    return rows


def glyph_table(rows):
    #every character of every result: its row, field, place in the field, bitmap, and centre in the page image
    out, bitmaps = [], []
    for r, (page, side, i) in enumerate(zip(rows['page'], rows['side'], rows['i'])):
        h = half(page, side)
        cells = h.cells(i)
        a, b = h.rows[i]
        for field, (k0, k1) in layout().FIELDS.items():
            for k in range(k0, k1 + 1):
                if k in cells:
                    bitmap, (top, height, width) = h.glyph(i, *cells[k])
                    px, py = h.page_xy((cells[k][0] + cells[k][1]) / 2, (a + b) / 2)
                    out.append((r, field, k, top, height, width, int(bitmap.sum()), px, py))
                    bitmaps.append(bitmap)
    table = pd.DataFrame(out, columns=['row', 'field', 'k', 'top', 'height', 'width', 'ink', 'px', 'py'])
    table['page'] = rows['page'].values[table['row']]
    return table, np.array(bitmaps).reshape(len(bitmaps), -1)


#---------------------------------------------------------------- reading the characters

def vocabulary(clean):
    #every word of three letters or more in the clean results' names and towns
    out = set()
    for col in ('first', 'middle', 'last', 'city'):
        for v in clean[col].dropna().unique():
            out.update(w for w in str(v).upper().split() if re.fullmatch('[A-Z]{3,}', w))
    return out


def town_list(clean):
    #{state: {length: [town, ...]}}: the clean results' towns in capitals, by state and length
    out = {}
    for city, state in set(zip(clean['city'].dropna(), clean['state'].dropna())):
        if re.fullmatch('[a-z ]+', city):
            out.setdefault(state, {}).setdefault(len(city), []).append(city.upper())
    return out


#tesseract's readings of each page: the pipeline's (psm 6) and its second at twice the size, and page 43 read again the
#right way up at twice the size (the pipeline turned it upside down, so its own reading is no use)
OCR_READINGS = (('', 1), ('_x2', 2), ('_x2r', 2))
UPSIDE_DOWN = [43]


def ocr(year=YEAR, race='birkie'):
    #the pages the pipeline turned upside down, read as they are at twice the size with the results' characters, as
    #<page>_x2r.tsv
    use_race(race)
    for page in layout().UPSIDE_DOWN:
        out = os.path.join(OCR_DIR, str(year), '{:03d}_x2r'.format(page))
        if os.path.exists(out + '.tsv'):
            continue
        image = Image.open(os.path.join(PAGE_DIR, str(year), '{:03d}.png'.format(page)))
        image.resize((image.width * 2, image.height * 2), Image.LANCZOS).save(out + '.png')
        subprocess.run([TESSERACT, out + '.png', out, '--psm', '6', '-c', 'tessedit_char_whitelist=' + RESULT_CHARACTERS,
                        'tsv'], capture_output=True)
        os.remove(out + '.png')


@functools.lru_cache(maxsize=None)
def page_words(page):
    #every word tesseract read on the page, in any of its readings, with its box in the page image's pixels
    out = []
    for suffix, scale in OCR_READINGS:
        path = os.path.join(OCR_DIR, str(YEAR), '{:03d}{}.tsv'.format(page, suffix))
        upside_down = os.path.exists(os.path.join(OCR_DIR, str(YEAR), '{:03d}_upright.png'.format(page)))
        if not os.path.exists(path) or (suffix == '' and upside_down):
            continue
        w = pd.read_csv(path, sep='\t', quoting=3, dtype={'text': str}, keep_default_na=False)
        w = w[(w['level'] == 5) & (w['text'].str.strip() != '')].copy()
        w[['left', 'top', 'width', 'height']] = w[['left', 'top', 'width', 'height']] / scale
        out.append(w[['text', 'left', 'top', 'width', 'height']])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=['text', 'left', 'top', 'width', 'height'])


def letter_labels(table, vocab):
    #letters whose reading is known: a word tesseract read (in any of its readings of the page) that is a name or a
    #town in the clean results, lying over exactly as many characters in one row of the grid. a character two words
    #read differently is left out
    labels = {}
    for page, g in table[table['field'].isin(['name', 'city'])].groupby('page'):
        px, py = g['px'].values, g['py'].values
        words = page_words(page)
        for text, left, top, width, height in zip(words['text'], words['left'], words['top'], words['width'],
                                                  words['height']):
            if not (text.isalpha() and text.isupper() and text in vocab):
                continue
            inside = g[(px >= left - 1) & (px <= left + width + 1) & (py >= top - 3) & (py <= top + height + 3)]
            if inside['row'].nunique() != 1 or len(inside) != len(text) or \
                    inside['k'].max() - inside['k'].min() != len(text) - 1:
                continue
            for idx, ch in zip(inside.sort_values('k').index, text):
                labels[idx] = ch if labels.get(idx, ch) == ch else '?'
    labels = pd.Series(labels, dtype=object)
    return labels[labels != '?']


def training_set(table, rows, letters, per_class=3000):
    #characters with a known reading: the rank digits (the places are known), the class column's M or F (the list), its
    #hyphen or plus, the time's point, and the letters from the OCR
    rank = table[table['field'] == 'rank']
    place = rows['place'].astype(str).values[rank['row']]
    pos = -9 - rank['k'].values
    digit = pd.Series([p[::-1][n] if n < len(p) else '' for p, n in zip(place, pos)], index=rank.index)
    cls = table[table['field'] == 'class']
    #(the M or F is the class field's first character, the hyphen or plus its fourth)
    c0 = layout().FIELDS['class'][0]
    long_class = set(cls.loc[cls['k'] == c0 + 5, 'row'])
    mf = cls[cls['k'] == c0]
    sign = cls[cls['k'] == c0 + 3]
    out = pd.concat([digit[digit != ''],
                     pd.Series(rows['gender'].values[mf['row']], index=mf.index),
                     pd.Series(['-' if r in long_class else '+' for r in sign['row']], index=sign.index),
                     pd.Series('.', index=table[(table['field'] == 'time') & (table['k'] == 7)].index),
                     letters])
    out = out[~out.index.duplicated(keep='last')]
    return out.groupby(out).head(per_class)


def class_distances(bitmaps, query, train, classes, nearest=3, chunk=2000):
    #each query character's distance (pixels that differ) to each class: the mean over that class's nearest few
    #characters, so a mislabelled one doesn't decide alone
    codes = pd.Categorical(train.values, categories=classes).codes
    order = np.argsort(codes, kind='stable')
    order = order[codes[order] >= 0]
    bounds = np.searchsorted(codes[order], np.arange(len(classes) + 1))
    R = bitmaps[train.index.values[order]].astype(np.float32)
    nr = (R ** 2).sum(1)
    out = np.full((len(query), len(classes)), np.inf, np.float32)
    for s in range(0, len(query), chunk):
        Q = bitmaps[query[s:s + chunk]].astype(np.float32)
        d = (Q ** 2).sum(1)[:, None] + nr[None, :] - 2 * Q @ R.T
        for j in range(len(classes)):
            lo, hi = bounds[j], bounds[j + 1]
            n = min(nearest, hi - lo)
            if n == 1:
                out[s:s + chunk, j] = d[:, lo:hi].min(1)
            elif n > 1:
                out[s:s + chunk, j] = np.partition(d[:, lo:hi], n - 1, axis=1)[:, :n].mean(1)
    return pd.DataFrame(np.maximum(out, 0), index=query, columns=classes)


def classify(bitmaps, query, train, classes, quick=300):
    #a first look against a few hundred characters of each class; the characters that aren't plainly one class are
    #compared again with every known character
    d = class_distances(bitmaps, query, train.groupby(train).head(quick), classes, nearest=1)
    s = np.sort(d.values, 1)
    unsure = s[:, 1] - s[:, 0] < 8
    if unsure.any():
        d.loc[query[unsure]] = class_distances(bitmaps, query[unsure], train, classes).values
    return d


def relearn(bitmaps, train, txt, changed):
    #the letters of words put right by the clean results' words (often a pair printed one over the other, as in "OM")
    #become known characters too, and the letters that weren't plainly one class are read again
    extra = pd.Series({i: b for idxs, old, new in changed if len(old) == len(new)
                       for i, a, b in zip(idxs, old, new) if a != b}, dtype=object)
    if extra.empty:
        return txt
    train = pd.concat([train, extra])
    train = train[~train.index.duplicated(keep='last')]
    s = np.sort(txt.values, 1)
    unsure = txt.index[s[:, 1] - s[:, 0] < 8].values
    txt = txt.copy()
    txt.loc[unsure] = class_distances(bitmaps, unsure, train, list(txt.columns)).values
    return txt


DIGITS = list('0123456789')
LETTERS = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
NUMERIC = ['rank', 'time', 'bib', 'class', 'class_rank', 'pace']


def read_glyphs(table, bitmaps, train):
    #each character's distance to every class it could be: the numeric fields' to the digits and signs, the rest's to
    #the letters, digits, hyphen and point
    numeric = table['field'].isin(NUMERIC)
    num = classify(bitmaps, table.index[numeric].values, train, DIGITS + ['-', '+', '.'])
    txt = classify(bitmaps, table.index[~numeric].values, train, LETTERS + DIGITS + ['-', '.'])
    return num, txt


#---------------------------------------------------------------- the fields

CLASSES = LETTERS + DIGITS + ['-', '+', '.']
PROVINCES_3 = {'ONT': 'ON', 'MAN': 'MB', 'QUE': 'QC', 'SAS': 'SK', 'ALB': 'AB'}
#how much worse (pixels that differ, over the word) a word tesseract read may fit the characters than their own reading
WORD_SLACK = 30
#the same for a whole hometown checked against the towns of its state
TOWN_SLACK = 16


class Reading:
    #every character's distance to each class, and each row's characters by field and grid place. with the clean
    #results' words, a name or town word is checked against them and against tesseract's readings of the same spot
    def __init__(self, table, num, txt, vocab=None, towns=None):
        self.towns = towns or {}
        self.town_sets = {st: {t for ts in by_len.values() for t in ts} for st, by_len in self.towns.items()}
        self.d = np.full((len(table), len(CLASSES)), np.inf, np.float32)
        for dist in (num, txt):
            self.d[np.ix_(dist.index.values, [CLASSES.index(c) for c in dist.columns])] = dist.values
        self.cells = {}
        for idx, r, f, k in zip(table.index, table['row'], table['field'], table['k']):
            self.cells.setdefault(r, {}).setdefault(f, {})[k] = idx
        self.px, self.py, self.page = table['px'].values, table['py'].values, table['page'].values
        self.top, self.height, self.width = table['top'].values, table['height'].values, table['width'].values
        self.vocab = vocab or set()
        by_len = {}
        for w in sorted(self.vocab):
            by_len.setdefault(len(w), []).append(w)
        self.by_len = {n: (ws, np.array([[LETTERS.index(c) for c in w] for w in ws])) for n, ws in by_len.items()}
        self.letter_cols = [CLASSES.index(c) for c in LETTERS]
        self.changed = []
        self.changed_towns = []

    def field(self, r, f):
        #{k: glyph index}
        return self.cells.get(r, {}).get(f, {})

    def read(self, idxs, classes):
        #the nearest class for each character, as a string
        cols = [CLASSES.index(c) for c in classes]
        if not len(idxs):
            return ''
        return ''.join(np.array(classes)[self.d[np.ix_(list(idxs), cols)].argmin(1)])

    def cost(self, idxs, text):
        #how far the characters are from reading as text
        return float(sum(self.d[i, CLASSES.index(c)] for i, c in zip(idxs, text)))

    def ocr_over(self, idxs):
        #tesseract's words (in capitals, letters only) whose box takes in all of these characters, and none other's
        words = page_words(self.page[idxs[0]])
        px, py = self.px[idxs], self.py[idxs]
        over = words[(words['left'] <= px.min() - 2) & (words['left'] + words['width'] >= px.max() + 2) &
                     (words['top'] <= py.mean()) & (words['top'] + words['height'] >= py.mean())]
        return [re.sub('[^A-Z]', '', t.upper()) for t in over['text']]

    def word(self, idxs, classes):
        #a word as read. one that isn't among the clean results' words becomes the one tesseract read there when that
        #is among them and the characters read nearly as well as it (WORD_SLACK); unless tesseract read it the same,
        #the nearest of the clean results' words when it's nearly as near and far nearer than any other
        text = self.read(idxs, classes)
        if not self.vocab or len(idxs) < 3 or not text.isalpha() or text in self.vocab:
            return text
        n = len(idxs)
        D = self.d[np.ix_(idxs, self.letter_cols)]
        base = D.min(1).sum()
        cost = lambda w: D[np.arange(n), [LETTERS.index(c) for c in w]].sum() - base
        seen = self.ocr_over(idxs)
        proposals = sorted((cost(t), t) for t in set(seen) if len(t) == n and t in self.vocab)
        if proposals and proposals[0][0] <= WORD_SLACK:
            out = proposals[0][1]
        elif text not in seen and n in self.by_len:
            ws, codes = self.by_len[n]
            c = D[np.arange(n), codes].sum(1) - base
            o = np.argsort(c)[:2]
            out = ws[o[0]] if c[o[0]] <= 5 and (len(o) < 2 or c[o[1]] - c[o[0]] >= 10) else text
        else:
            out = text
        if out != text:
            self.changed.append((list(idxs), text, out))
        return out


def words(cells):
    #a field's characters split where a cell is empty: [[glyph index, ...], ...]
    out, last = [], None
    for k in sorted(cells):
        if last is None or k != last + 1:
            out.append([])
        out[-1].append(cells[k])
        last = k
    return out


def postcode(reading, w):
    #a postcode ("7530", "N1349", "D-3370"): each character a digit unless it's plainly a letter or a hyphen
    out = []
    for i in w:
        digit = min(DIGITS, key=lambda c: reading.d[i, CLASSES.index(c)])
        letter = min(LETTERS + ['-'], key=lambda c: reading.d[i, CLASSES.index(c)])
        plain = reading.d[i, CLASSES.index(letter)] + 8 <= reading.d[i, CLASSES.index(digit)]
        out.append(letter if plain else digit)
    return ''.join(out)


def tidy(words):
    #a stray mark read as a point or hyphen at a word's end, or as a word of its own, is dropped
    return ' '.join(w for w in (w.strip('.-') for w in words) if w)


def read_town(reading, cells):
    #a hometown's words, each read as letters or, when most of its characters look like digits, as a postcode
    out = []
    for w in words(cells):
        n_digits = sum(reading.d[i, [CLASSES.index(c) for c in DIGITS]].min() <
                       reading.d[i, [CLASSES.index(c) for c in LETTERS]].min() for i in w)
        out.append(postcode(reading, w) if n_digits * 2 > len(w) else apostrophes(reading, w, LETTERS + ['-', '.']))
    return tidy(out)


def apostrophes(reading, w, classes):
    #a word that may hold an apostrophe ("O'CONNELL", "BRIGHT'S"): a small narrow mark at the top of the row, which has
    #no class of its own and would read as a point
    marks = [n for n, i in enumerate(w) if reading.height[i] <= 7 and reading.top[i] <= 2 and reading.width[i] <= 6]
    if not marks:
        return reading.word(w, classes)
    return "'".join(reading.word(w[a + 1:b], classes) for a, b in zip([-1] + marks, marks + [len(w)]))


def fix_town(reading, cells, city, state):
    #a hometown not seen in its state in the clean results becomes one that is, when its characters read nearly as well
    #as it (TOWN_SLACK, as in "HILTON" for a blotted "MILTON") and far better than as any other
    if not cells or not city or any(c.isdigit() for c in city):
        return city
    if normalize_location(city, state, '')[0].upper() in reading.town_sets.get(state, set()):
        return city
    ks = sorted(cells)
    letter_cols = [CLASSES.index(c) for c in LETTERS]
    floor = {k: reading.d[cells[k], letter_cols].min() for k in ks}
    costs = []
    for town in reading.towns.get(state, {}).get(ks[-1] - ks[0] + 1, []):
        cost = 0
        for k, ch in zip(range(ks[0], ks[-1] + 1), town):
            if (ch == ' ') != (k not in cells) or (ch != ' ' and ch not in CLASSES):
                cost = np.inf
                break
            if ch != ' ':
                cost += reading.d[cells[k], CLASSES.index(ch)] - floor[k]
        costs.append((cost, town))
    costs.sort()
    if costs and costs[0][0] <= TOWN_SLACK and (len(costs) < 2 or costs[1][0] - costs[0][0] >= 10):
        reading.changed_towns.append((city, costs[0][1]))
        return costs[0][1]
    return city


def read_name(reading, cells):
    #a name's words in letters and hyphens
    return tidy([apostrophes(reading, w, LETTERS + ['-']) for w in words(cells)])


def read_state(reading, cells, country):
    #a us or canadian skier's state is the nearest of the codes there are (a 3-letter province is the 2-letter code);
    #elsewhere (an australian state, a foreign region) the letters as read
    idxs = [cells[k] for k in sorted(cells)]
    free = reading.read(idxs, LETTERS)
    if not idxs or country not in ('', 'CAN', 'USA'):
        return free
    codes = list(PROVINCES_3) + sorted(CA_PROVINCES) + (sorted(US_STATES) if country != 'CAN' else [])
    codes = [c for c in codes if len(c) == len(idxs)]
    if not codes:
        return free
    code = min(codes, key=lambda c: reading.cost(idxs, c))
    return PROVINCES_3.get(code, code)


def read_age(reading, cells, c0, ages):
    #the class's ages ("25-29" from "M25-29", "70+"), its M or F at c0: the digits as read when they make one of the
    #race's classes, else the class they read nearest to (a blotted 3 read as a 4 makes "45-39")
    if all(k in cells for k in (c0 + 1, c0 + 2, c0 + 4, c0 + 5)):
        idxs = [cells[k] for k in (c0 + 1, c0 + 2, c0 + 4, c0 + 5)]
        age = '{}{}-{}{}'.format(*reading.read(idxs, DIGITS))
        alike = [a for a in ages if '-' in a]
    elif all(k in cells for k in (c0 + 1, c0 + 2, c0 + 3)) and c0 + 4 not in cells:
        idxs = [cells[k] for k in (c0 + 1, c0 + 2)]
        age = '{}{}+'.format(*reading.read(idxs, DIGITS))
        alike = [a for a in ages if a.endswith('+')]
    else:
        return ''
    if age in ages or not alike:
        return age
    return min(alike, key=lambda a: reading.cost(idxs, a.replace('-', '').rstrip('+')))


def assemble(rows, reading):
    #every row's fields as read
    lay = layout()
    c0 = lay.FIELDS['class'][0]
    #the pace's minute and seconds digits, after the tens of minutes' where the layout has room for them
    tens, units = lay.PACE[:-3], lay.PACE[-3:]
    recs = []
    for r in rows.index:
        f = lambda name: reading.field(r, name)
        t, p, c = f('time'), f('pace'), f('class')
        rec = {'time_glyphs': [t.get(k) for k in TIME_DIGITS]}
        rec['time'] = '{}:{}{}:{}{}.{}'.format(*reading.read([t[k] for k in TIME_DIGITS], DIGITS)) \
            if all(k in t for k in TIME_DIGITS) else ''
        rec['pace'] = reading.read([p[k] for k in tens if k in p], DIGITS) + \
            '{}:{}{}'.format(*reading.read([p[k] for k in units], DIGITS)) if all(k in p for k in units) else ''
        rec['bib'] = '' if rows.loc[r, 'bib_faded'] else number(reading, f('bib'), lay.FIELDS['bib'][1])
        rec['age'] = read_age(reading, c, c0, lay.AGES)
        rec['class_rank'] = number(reading, f('class_rank'), lay.FIELDS['class_rank'][1])
        rec['name'] = read_name(reading, f('name'))
        rec['city'] = read_town(reading, f('city'))
        rec['country'] = reading.read([v for _, v in sorted(f('country').items())], LETTERS)
        rec['state'] = read_state(reading, f('state'), rec['country'])
        rec['city'] = fix_town(reading, f('city'), rec['city'], rec['state'])
        rec['classic'] = 'C' in reading.read(list(f('cls').values()), LETTERS + ['-', '.'])
        recs.append(rec)
    return pd.concat([rows[['page', 'top', 'gender', 'place']], pd.DataFrame(recs, index=rows.index)], axis=1)


TIME_DIGITS = (0, 2, 3, 5, 6, 8)


def longest_rising(values):
    #positions of a longest run of values (not necessarily adjacent) that never goes down
    tails, prev = [], [-1] * len(values)
    for i, v in enumerate(values):
        j = bisect.bisect_right([values[t] for t in tails], v)
        if j == len(tails):
            tails.append(i)
        else:
            tails[j] = i
        prev[i] = tails[j - 1] if j else -1
    out, i = [], tails[-1] if tails else -1
    while i >= 0:
        out.append(i)
        i = prev[i]
    return out[::-1]


def pace_seconds(pace):
    if not pace:
        return np.nan
    m, s = pace.split(':')
    return int(m) * 60 + int(s)


def damaged(reading, idx):
    #a character in a digit's place that looks more like a point or a hyphen than any digit, or is far from every digit
    #and about as near two of them: a digit blotted or broken
    if idx is None or CLASSES[int(np.argmin(reading.d[idx]))] not in DIGITS:
        return True
    d = np.sort(reading.d[idx, [CLASSES.index(c) for c in DIGITS]])
    return d[0] >= 20 and d[1] - d[0] < 2


def repair_times(df, reading, margin=8):
    #a time out of order with the times around it (the longest rising run of each list) has each of its digits tried
    #as every other digit; a time with a damaged digit has that digit tried as every digit. a change is made when only
    #one fits between its neighbours and the printed pace (time / COURSE_KM, to the second), or one fits far better than
    #any other; otherwise the time is left blank
    course_km = layout().COURSE_KM
    df = df.copy()
    for _, lst in df.groupby('gender'):
        lst = lst.sort_values('place')
        secs = lst['time'].map(parse_seconds).values
        ok = np.nonzero(np.isfinite(secs))[0]
        trusted = set(ok[longest_rising(list(secs[ok]))])
        for n, (r, time, glyphs, pace) in enumerate(zip(lst.index, lst['time'], lst['time_glyphs'], lst['pace'])):
            broken = [j for j, g in enumerate(glyphs) if damaged(reading, g)]
            if not time or (n in trusted and not broken):
                continue
            lo = max([secs[m] for m in trusted if m < n and m != n], default=0)
            hi = min([secs[m] for m in trusted if m > n and m != n], default=np.inf)
            pace_s = pace_seconds(pace)
            now = time.replace(':', '').replace('.', '')
            tries = [(j, c) for j in (broken or range(len(now))) for c in DIGITS if broken or c != now[j]]
            fits = []
            for j, c in tries:
                d = now[:j] + c + now[j + 1:]
                if int(d[1:3]) > 59 or int(d[3:5]) > 59:
                    continue
                t = '{}:{}:{}.{}'.format(d[0], d[1:3], d[3:5], d[5])
                s = parse_seconds(t)
                if lo <= s <= hi and not (np.isfinite(pace_s) and abs(s / course_km - pace_s) > 1):
                    g = glyphs[j]
                    fits.append((reading.d[g, CLASSES.index(c)] - reading.d[g, CLASSES.index(now[j])], t))
            fits.sort()
            if len(fits) == 1 or (len(fits) > 1 and fits[1][0] - fits[0][0] >= margin and not broken):
                df.loc[r, 'time'] = fits[0][1]
            else:
                df.loc[r, 'time'] = ''
    return df


def number(reading, cells, last):
    #a right-aligned number's digits; blank when a digit inside it is missing or damaged
    ks = sorted(cells)
    if not ks:
        return ''
    if ks[-1] != last or ks[-1] - ks[0] + 1 != len(ks) or any(damaged(reading, cells[k]) for k in ks):
        return ''
    return reading.read([cells[k] for k in ks], DIGITS)


def repair_class_ranks(df):
    #each age class's ranks count up by one in place order. a rank that doesn't, between the two ranks around it that do
    #(one less before it, one more after it), is that count
    df = df.copy()
    for _, cls in df[df['age'] != ''].sort_values(['gender', 'place']).groupby(['gender', 'age']):
        ranks = pd.to_numeric(cls['class_rank'], errors='coerce').values
        for n, r in enumerate(cls.index):
            want = n + 1
            if ranks[n] == want:
                continue
            before = n == 0 or ranks[n - 1] == want - 1
            after = n == len(ranks) - 1 or ranks[n + 1] == want + 1
            if before and after:
                df.loc[r, 'class_rank'] = str(want)
    return df


#---------------------------------------------------------------- the results

def output(df):
    #the csv's columns. a us or canadian skier's nation is left blank in print, so it's taken from the state
    out = pd.DataFrame(index=df.index)
    out['place'] = df['place']
    out['bib'] = df['bib']
    out['name'] = df['name']
    out['gender'] = df['gender']
    out['age_group'] = [('{} {}'.format(g, a) if a else '') for g, a in zip(df['gender'], df['age'])]
    out['class_rank'] = df['class_rank']
    out['city'] = df['city']
    #a stray mark, or a state printed again, in the NAT column is no nation
    country = df['country'].where(df['country'].str.len() >= 2, '')
    country = country.where(~country.isin(US_STATES), '')
    out['country'] = np.where(country != '', country, np.where(df['state'].isin(US_STATES), 'USA',
                                                               np.where(df['state'].isin(CA_PROVINCES), 'CAN', '')))
    #a foreign skier's ST column holds a region of their own country ("VIC", "VD", "MI" for Milano), not a state
    out['state'] = np.where(out['country'].isin(['USA', 'CAN']), df['state'], '')
    out['time'] = df['time']
    out['status'] = 'finished'
    out['tech'] = np.where(df['classic'], 'classic', 'skate')
    out['page'] = df['page']
    out['top'] = df['top']
    return out.reset_index(drop=True)


def parse(year=YEAR, race='birkie'):
    from results_loader import load_all_results
    use_race(race)
    rows = result_rows()
    table, bitmaps = glyph_table(rows)
    clean = load_all_results()
    vocab, towns = vocabulary(clean), town_list(clean)
    train = training_set(table, rows, letter_labels(table, vocab))
    num, txt = read_glyphs(table, bitmaps, train)
    #a first reading to find the words the clean results' words put right, to learn their letters from
    first = Reading(table, num, txt, vocab=vocab, towns=towns)
    assemble(rows, first)
    reading = Reading(table, num, relearn(bitmaps, train, txt, first.changed), vocab=vocab, towns=towns)
    df = repair_class_ranks(repair_times(assemble(rows, reading), reading))
    return output(df)
