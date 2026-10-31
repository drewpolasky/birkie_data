#1996 birch scroll (the smaller "-s" scan): the birkebeiner's full results are pages 28-51, "DYNO AMERICAN BIRKEBEINER
#RESULTS", in alphabetical order of last name, men and women together, two results to a line. each result is RANK (the
#place within the skier's gender, or DNF), FINAL TIME, BIB, NAME ("LAST, FIRST M"), HOMETOWN, ST, NAT, CLASS
#("M40-44"), class rank, 25% club ("Y") and pace (min.sec per km: the time over 52 km, rounded down). there is no
#technique column. page 26 is the top 50 women and page 27 the top 200 men, in place order, both again in the full
#list; 22 is the top three in each class and 52-64 are the kortelopet
#
#'top' is a row's place in old_results/pages/1996/<page>.png. ocr() reads the pages several ways, all in
#old_results/ocr/1996/:
#   <page>_f2.tsv                    the whole page at twice the size
#   <page>_<L|R><field>_s2/_s3.tsv   each field's strip down each half of the upright page (<page>_level.png) at two
#                                    and three times the size with only the characters it can hold, <page>_strips.json
#                                    for where the strips are and the page's lean
#   <page>_<L|R><name|town>_c4/_n2   the name and hometown columns in chunks of 20 lines, at four times the size with
#                                    a whitelist and at twice the size without
#   <page>_glyphs.tsv                every character of the rank, time, bib, class, class rank and pace columns, told
#                                    apart by nearest neighbours among the characters the OCR readings agree on.
#                                    tesseract often reads this font's 1 as 4 in every reading at once; the glyphs don't
#the numbers come from the glyphs when every glyph is sure, else from a vote of the readings. a time must fit the pace
#(the time over 52 km, rounded down to the second, so a 52 second window). within each gender the places and times
#that rise together with the most others are kept, and the rest are placed between them where that's pinned down (the
#one free place among a line's readings, or as many free places as lines between two kept ones); the class ranks are
#checked the same way within each class. names and towns are picked from four readings: the known ones from other
#years first, else the one the others are the likeliest misreadings of
import concurrent.futures
import functools
import json
import math
import os
import re
import subprocess
from collections import Counter

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage

from birkie_archive import OCR_DIR, PAGE_DIR, TESSERACT, parse_seconds, state_code
from results_loader import compact, load_all_results, US_STATES, CA_PROVINCES

YEAR = 1996
PAGES = range(28, 52)
#characters OCR reads in place of digits; this font's 5 often comes out as a section sign
DIGITS = str.maketrans({'O': '0', 'o': '0', 'D': '0', 'Q': '0', 'I': '1', 'l': '1', '|': '1', '!': '1', 'i': '1',
                        'L': '1', 'S': '5', 's': '5', '$': '5', 'B': '8', 'Z': '2', 'z': '2', 'G': '6', 'g': '9',
                        '§': '5', '\ufffd': '5', ']': '1', '[': '1', '{': '1', '}': '1', 'J': '1', 'T': '7'})
#each field's left edge in pixels from the left of its line's nation code
EDGES = {'time': -767, 'bib': -673, 'name': -603, 'town': -300, 'st': -80, 'nat': -22, 'cls': 45, 'crank': 122,
         'y': 172, 'pace': 205, 'end': 290}
NATIONS = {'USA', 'CAN', 'GER', 'NOR', 'SWE', 'FIN', 'ITA', 'AUT', 'SUI', 'FRA', 'EST', 'RUS', 'CZE', 'JPN', 'GBR',
           'AUS', 'NZL', 'DEN', 'NED', 'POL', 'SLO', 'BEL', 'ESP', 'KOR', 'CHN', 'ISL', 'MEX', 'BRA', 'ARG', 'UKR',
           'BLR', 'LAT', 'LTU', 'KAZ', 'SVK', 'HUN', 'IRL', 'ISR', 'RSA', 'CHI', 'TAN'}
#canadian provinces as printed
PROVINCES = {'ONT': 'ON', 'MAN': 'MB', 'ALB': 'AB', 'SAS': 'SK', 'SASK': 'SK', 'QUE': 'QC', 'PQ': 'QC'}
AGES = ['18-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', '65-69', '70-74', '75-79',
        '80-84', '85-89']
#pace is the time over 52 km, in whole seconds per km rounded down
KM = 52
#readings of each strip, and the whole page's
SOURCES = ['s2', 's3', 'f2']
#readings of the name and hometown columns in chunks, and the order they're trusted in when they all differ (by the
#share of last names each one gets that are known from other years)
CHUNKS = ['c4', 'n2']
NAME_SOURCES = ['f2', 'n2', 'c4', 's3']


def num(text):
    return re.sub(r'\D', '', str(text).translate(DIGITS))


#---------------------------------------------------------------- reading the OCR

def read_tsv(path):
    w = pd.read_csv(path, sep='\t', quoting=3, dtype={'text': str}, keep_default_na=False, encoding='utf-8',
                    encoding_errors='replace')
    return w[(w['level'] == 5) & (w['text'].str.strip() != '')].copy()


def words(page, suffix='f2', scale=2):
    #the whole page's OCR, boxes in page pixels
    w = read_tsv(os.path.join(OCR_DIR, str(YEAR), '{:03d}_{}.tsv'.format(page, suffix)))
    for c in ['left', 'top', 'width', 'height']:
        w[c] = w[c] / scale
    return w.reset_index(drop=True)


def nat_lines(w):
    #the nation codes' left edge down each half of the page, as x = a + b * y
    nat = w[w['text'].str.upper().str.strip('.,-_=|').isin(NATIONS)]
    mid = w['left'].add(w['width']).max() / 2
    fits = []
    for half in (nat[nat['left'] < mid], nat[nat['left'] >= mid]):
        x, y = half['left'].values.astype(float), half['top'].values.astype(float)
        keep = np.abs(x - np.median(x)) < 40
        for _ in range(3):
            b, a = np.polyfit(y[keep], x[keep], 1)
            keep = np.abs(x - (a + b * y)) < 8
        fits.append((a, b))
    return fits


def geometry(page):
    with open(os.path.join(OCR_DIR, str(YEAR), '{:03d}_strips.json'.format(page))) as f:
        return json.load(f)


def to_upright(g, x, y):
    (cx, cy), t = g['center'], g['theta']
    return cx + (x - cx) * math.cos(t) + (y - cy) * math.sin(t), cy - (x - cx) * math.sin(t) + (y - cy) * math.cos(t)


def to_page(g, x, y):
    (cx, cy), t = g['center'], g['theta']
    return cx + (x - cx) * math.cos(t) - (y - cy) * math.sin(t), cy + (x - cx) * math.sin(t) + (y - cy) * math.cos(t)


def page_words(page):
    #every reading's words in the upright page: half (0 left, 1 right), x from the half's NAT column, y center, source
    g = geometry(page)
    out = []
    for name, box in g['strips'].items():
        half, field = int(name[0] == 'R'), name[1:]
        for scale in (2, 3):
            path = os.path.join(OCR_DIR, str(YEAR), '{:03d}_{}_s{}.tsv'.format(page, name, scale))
            if not os.path.exists(path):
                continue
            w = read_tsv(path)
            out.append(pd.DataFrame({'half': half, 'strip': field, 'source': 's{}'.format(scale), 'text': w['text'],
                                     'x': box[0] + w['left'] / scale - g['pad'] - g['nat'][half],
                                     'y': (w['top'] + w['height'] / 2) / scale}))
    #the name and hometown columns read again in chunks of 20 lines, boxes in the upright page's pixels: at four times
    #the size with a whitelist, and at twice the size without one
    for half, field, source in [(h, f, s) for h in (0, 1) for f in ('name', 'town') for s in CHUNKS]:
        path = os.path.join(OCR_DIR, str(YEAR), '{:03d}_{}{}_{}.tsv'.format(page, 'LR'[half], field, source))
        if os.path.exists(path):
            w = read_tsv(path)
            out.append(pd.DataFrame({'half': half, 'strip': field, 'source': source, 'text': w['text'],
                                     'x': w['left'] - g['nat'][half], 'y': w['top'] + w['height'] / 2}))
    f = words(page)
    x, y = to_upright(g, f['left'].values, (f['top'] + f['height'] / 2).values)
    split = (g['nat'][0] + EDGES['end'] + g['nat'][1] + EDGES['time'] - 60) / 2
    half = (x >= split).astype(int)
    out.append(pd.DataFrame({'half': half, 'strip': '', 'source': 'f2', 'text': f['text'].values,
                             'x': x - np.array(g['nat'])[half], 'y': y}))
    w = pd.concat(out, ignore_index=True)
    w['zone'] = w['x'].map(zone)
    #the strips' words by their strip, the page's by where they sit
    w.loc[w['source'] == 'f2', 'strip'] = w['zone']
    return w, g


def zone(rel):
    names = list(EDGES)
    for k in reversed(range(len(names))):
        if rel >= EDGES[names[k]]:
            return names[k]
    return 'rank'


def lines_of(w):
    #line centers down one half, from the strips' words: every result has a bib, a name and a class
    ys = np.sort(w.loc[w['source'].isin(['s2', 's3']) & w['strip'].isin(['bib', 'name', 'cls']), 'y'].values)
    centers, cur = [], []
    for y in ys:
        if cur and y - np.mean(cur) > 10:
            centers.append(np.median(cur))
            cur = []
        cur.append(y)
    if cur:
        centers.append(np.median(cur))
    return np.array(centers)


def glyph_words(page):
    #the page's glyphs, or None before they're read
    path = os.path.join(OCR_DIR, str(YEAR), '{:03d}_glyphs.tsv'.format(page))
    if not os.path.exists(path):
        return None
    g = pd.read_csv(path, sep='	', dtype={'text': str, 'second': str}, keep_default_na=False)
    g['yc'] = g['top'] + g['height'] / 2
    return g


def page_rows(page):
    w, g = page_words(page)
    gw = glyph_words(page)
    rows = []
    for half in (0, 1):
        hw = w[w['half'] == half]
        centers = lines_of(hw)
        if not len(centers):
            continue
        k = np.abs(hw['y'].values[:, None] - centers[None, :]).argmin(1)
        near = np.abs(hw['y'].values - centers[k]) <= 11
        hw = hw.assign(line=k)[near]
        glyphs = {}
        if gw is not None:
            hg = gw[gw['half'] == half]
            kg = np.abs(hg['yc'].values[:, None] - centers[None, :]).argmin(1)
            hg = hg.assign(line=kg)[np.abs(hg['yc'].values - centers[kg]) <= 10]
            for (line, field), fg in hg.sort_values('left').groupby(['line', 'field']):
                glyphs.setdefault(line, {})['g_' + field] = list(zip(fg['text'], fg['p1'], fg['second'], fg['p2'],
                                                                     fg['dist']))
        for line, lw in hw.groupby('line'):
            lw = lw.sort_values('x')
            reads = {}
            for (strip, source), sw in lw.groupby(['strip', 'source']):
                reads[strip + '_' + source] = ' '.join(sw['text'])
                if strip in ('pace', 'crank', 'y'):
                    reads.setdefault('tail_' + source, [])
                    reads['tail_' + source] += list(zip(sw['text'], sw['x']))
            #where the line's rank sits in the page image, for finding it by eye
            x, y = to_page(g, g['nat'][half] + EDGES['time'] - 40, centers[line])
            rows.append({**reads, **glyphs.get(line, {}), 'page': page, 'half': half, 'top': int(round(y - 10)),
                         'line_y': centers[line]})
    return rows


def raw_rows(pages=PAGES):
    return pd.DataFrame([r for p in pages for r in page_rows(p)])


#---------------------------------------------------------------- fields

def read_class(text):
    #('M', '40-44') from 'M40-44', 'MS50-54' (an S for a 5), 'M49-44', 'Fi8-24'; the age group whose four digits match
    #the ones read, or the one group a digit away
    m = re.search(r'([MF])(.*)', str(text).upper().replace('_', '').replace('§', '5'))
    if not m:
        bare = re.fullmatch(r'\s*(\d\d)-(\d\d)\s*', str(text))
        return '', '{}-{}'.format(*bare.groups()) if bare and '{}-{}'.format(*bare.groups()) in AGES else ''
    rest = m.group(2).split()
    d = num(rest[0]) if rest else ''
    if len(d) < 4:
        return m.group(1), ''
    tries = [d[:4]] + ([d[:2] + d[-2:], d[-4:]] if len(d) > 4 else [])
    for t in tries:
        best = [a for a in AGES if a.replace('-', '') == t]
        if best:
            return m.group(1), best[0]
    close = {a for t in tries[:1] for a in AGES if sum(x != y for x, y in zip(a.replace('-', ''), t)) == 1}
    if len(close) == 1:
        return m.group(1), close.pop()
    return m.group(1), ''


def read_pace(text):
    #'5.23', or '523' with the point lost
    t = str(text).translate(DIGITS)
    m = re.search(r'(\d{1,2})\s*[.,:]\s*(\d\d)', t)
    if not m:
        d = num(t)
        m = re.fullmatch(r'(\d{1,2})(\d\d)', d) if len(d) in (3, 4) else None
    if not m or int(m.group(2)) > 59 or not 2 <= int(m.group(1)) <= 12:
        return np.nan
    return int(m.group(1)) * 60 + int(m.group(2))


def read_tail(tokens):
    #class rank, 25% club and pace from the words right of the class, by where they sit; a word running from the class
    #rank into the pace ('27Y4.43') is split by its pattern
    crank, club, pace = '', '', ''
    for text, x in tokens:
        t = text.strip()
        m = re.fullmatch(r'(\d{0,3})(Y?)(\d{1,2}[.,]\d\d)', t)
        if m and (m.group(1) or m.group(2)):
            crank, club, pace = crank or m.group(1), club or m.group(2), m.group(3)
        elif x >= EDGES['pace'] - 5:
            pace = pace or t
        elif x >= EDGES['y'] - 5 or t.upper() in ('Y', 'YY'):
            club = club or ('Y' if 'Y' in t.upper() else '')
        else:
            m = re.fullmatch(r'(\d{1,3})(Y?)', t)
            if m:
                crank, club = crank or m.group(1), club or m.group(2)
            else:
                crank = crank or num(t)[:3]
    return crank, club, pace


def time_text(d):
    return '{}:{}:{}.{}'.format(d[0], d[1:3], d[3:5], d[5])


def ok_digits(d):
    return len(d) == 6 and int(d[1:3]) < 60 and int(d[3:5]) < 60 and 1 <= int(d[0]) <= 9


def vote(values):
    #the value most readings give; a tie goes to the earlier source
    values = [v for v in values if v]
    if not values:
        return ''
    c = Counter(values)
    top = max(c.values())
    return next(v for v in values if c[v] == top)


def name_parts(text):
    #(first and middle, last) from "LAST, FIRST M"
    text = re.sub(r"[^A-Za-z0-9,.'\- ]", ' ', str(text))
    text = re.sub(r'(?<=[A-Za-z])0|0(?=[A-Za-z])', 'O', text)
    text = re.sub(r'\s+', ' ', text).strip(' -.,')
    if ',' in text:
        last, first = text.split(',', 1)
    else:
        parts = text.split(' ', 1)
        last, first = parts[0], parts[1] if len(parts) > 1 else ''
    return split_initial(first.strip(' ,.').upper()), last.strip(' ,.').upper()


#what it costs to read a printed letter (first) as another (second, '' for none): the readings of this font often
#give G for C and O, O and B for D, S for B, K and R for H, and drop an I or add a space (measured on the last names
#known from other years where the readings disagree)
CHEAP = {('C', 'G'): 0.3, ('O', 'G'): 0.3, ('D', 'O'): 0.4, ('D', 'B'): 0.4, ('B', 'S'): 0.4, ('H', 'K'): 0.5,
         ('H', 'R'): 0.5, ('I', ''): 0.5, ('', ' '): 0.3, ('O', 'Q'): 0.5, ('B', '8'): 0.5, ('C', 'O'): 0.6, ('', 'O'): 0.6, ('I', 'L'): 0.5}


def misread(truth, reading):
    #the cheapest way to read truth as reading, letter by letter
    n, m = len(truth), len(reading)
    d = np.zeros((n + 1, m + 1))
    d[:, 0] = [sum(CHEAP.get((c, ''), 1) for c in truth[:i]) for i in range(n + 1)]
    d[0, :] = [sum(CHEAP.get(('', c), 1) for c in reading[:j]) for j in range(m + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            a, b = truth[i - 1], reading[j - 1]
            d[i, j] = min(d[i - 1, j] + CHEAP.get((a, ''), 1), d[i, j - 1] + CHEAP.get(('', b), 1),
                          d[i - 1, j - 1] + (0 if a == b else CHEAP.get((a, b), 1)))
    return d[n, m]


def pick(values, known):
    #among the readings known from other years, the one the most readings give; when none is known, the one the
    #readings are the cheapest misreadings of. a tie goes to the reading trusted first
    values = [v for v in values if v]
    pool = [v for v in values if known(v)]
    if pool:
        c = Counter(pool)
        top = max(c.values())
        return next(v for v in pool if c[v] == top)
    if not values:
        return ''
    cost = {v: sum(misread(v, w) for w in values) for v in dict.fromkeys(values)}
    return min(cost, key=lambda v: (cost[v], values.index(v)))


def choose_name(texts):
    #first name and last name each picked from the readings, the middle initial the one most readings give
    parts = [name_parts(t) for t in texts if str(t).strip()]
    last = pick([l for _, l in parts], lambda v: compact(v) in known_last())
    firsts = [f.split()[0] if f.split() else '' for f, _ in parts]
    first = pick(firsts, lambda v: compact(v) in known_first())
    middles = [' '.join(f.split()[1:]) for f, _ in parts if f.split() and f.split()[0] == first]
    middle = vote(middles) if sum(bool(m) for m in middles) * 2 >= len(middles) else ''
    return ' '.join(p for p in (first, middle, last) if p)


@functools.lru_cache(maxsize=None)
def clean():
    return load_all_results()


@functools.lru_cache(maxsize=None)
def known_first():
    return frozenset(clean()['first'].dropna().map(compact))


@functools.lru_cache(maxsize=None)
def known_last():
    return frozenset(clean()['last'].dropna().map(compact))


@functools.lru_cache(maxsize=None)
def known_places():
    return frozenset(zip(clean()['city'].map(compact), clean()['state']))


def split_initial(first):
    #"NEILA" for "NEIL A": a middle initial OCR ran into the first name, when the name without it is a known first name
    #and the name with it is not
    tokens = first.split()
    if len(tokens) == 1 and len(tokens[0]) > 3 and compact(tokens[0]) not in known_first() \
            and compact(tokens[0][:-1]) in known_first():
        tokens = [tokens[0][:-1], tokens[0][-1]]
    return ' '.join(tokens)


def read_state(text, town):
    #a lowercase l, a bracket or a bar in a state code is a capital I ('lA', 'Ml', '[A')
    s = re.sub(r'[l|!1\[{\\]', 'I', re.sub(r'[^A-Za-z!|1\[{\\]', '', str(text)))
    if not s:
        return ''
    up = s.upper()
    if up in PROVINCES:
        return PROVINCES[up]
    code = state_code(up.replace('!', 'I').replace('|', 'I'))
    if code in US_STATES | CA_PROVINCES:
        return code
    #a garbled code: the one valid code a letter away whose town is known there
    cands = {c for c in US_STATES | CA_PROVINCES if len(c) == len(code) and sum(a != b for a, b in zip(c, code)) == 1}
    if len(code) == 3:
        cands |= {c for c in US_STATES | CA_PROVINCES if c in (code[:2], code[1:], code[0] + code[2])}
    known = {c for c in cands if (compact(town), c) in known_places()}
    if len(known) == 1:
        return known.pop()
    return code


def read_nation(text):
    #a nation code, with a lowercase l, a bar or a ! read as I ('Sul', 'SU!'); a code with its I lost ('SU'), or one
    #letter off ('OZE'), when only one nation fits
    t = re.sub(r'[^A-Z]', '', re.sub(r'[l|!1]', 'I', str(text)).upper())
    for n in NATIONS:
        if n in t:
            return n
    near = [n for n in NATIONS if (len(t) == 3 and sum(a != b for a, b in zip(n, t)) == 1) or
            (len(t) == 2 and n.startswith(t) and n.endswith('I'))]
    if len(near) == 1:
        return near[0]
    return t[-3:] if len(t) >= 3 else ''


def split_town(text):
    #HOMETOWN, ST and NAT from the town strip's words: the nation is the last word, the state the one before it when
    #it's a short code
    words = str(text).split()
    nat = ''
    if words and read_nation(words[-1]) in NATIONS:
        nat = read_nation(words.pop())
    st = ''
    if words and len(words[-1]) <= 3 and len(words) > 1 and read_nation(words[-1]) not in NATIONS:
        st = words.pop()
    elif words and len(words) > 1 and read_nation(words[-1]) in NATIONS:
        #the nation read twice ('ZURICH SU SUI')
        words.pop()
    return ' '.join(words), st, nat


def clean_town(t):
    #a bracket or bar starting a word is a capital I ('[OWA CITY')
    t = re.sub(r'(?<![A-Za-z])[\[{|\\](?=[A-Za-z])', 'I', str(t))
    return re.sub(r'\s+', ' ', re.sub(r"[^A-Za-z.' \-]", ' ', t)).strip(" .-'")


def get(row, key):
    v = row.get(key, '')
    return v if isinstance(v, (str, list)) else ''




#---------------------------------------------------------------- one line's readings

#a glyph is sure when most of its nearest neighbours agree and it's close to them
GLYPH_SURE = 0.67
GLYPH_DIST = 2.2
#digits this font's glyphs and OCR mix up, for the times and places the readings don't settle
SWAPS = {'1': '47', '4': '1', '7': '1', '3': '8', '8': '396', '5': '6', '6': '58', '0': '9', '9': '08', '2': '3'}


def glyph_read(gl):
    #(text, sure, texts with one unsure glyph swapped for its second best)
    if not isinstance(gl, list) or not gl:
        return '', False, []
    text = ''.join(g[0] for g in gl)
    unsure = [k for k, g in enumerate(gl) if g[1] < GLYPH_SURE or g[4] > GLYPH_DIST]
    alts = [text[:k] + gl[k][2] + text[k + 1:] for k in unsure if gl[k][2]]
    return text, not unsure, alts


def numeric(gl, ocr):
    #(value, sure, candidates) of a numeric field: the glyphs' digits when every glyph is sure, else the value most
    #readings give (the glyphs' twice). when most OCR readings agree on a length the glyphs don't have, a glyph was lost
    #or split and the OCR's readings decide (all of them, against glyphs that are sure)
    g, sure, alts = glyph_read(gl)
    ocr = [d for d in ocr if d.isdigit()]
    lengths = Counter(len(d) for d in ocr).most_common(1)
    if g.isdigit() and lengths and lengths[0][0] != len(g) and \
            (lengths[0][1] == len(ocr) >= 2 if sure else lengths[0][1] >= 2):
        g, sure, alts = '', False, []
    reads = [d for d in [g] + alts + ocr if d.isdigit()]
    if g.isdigit() and sure:
        return g, True, reads
    return vote([d for d in [g, g] + ocr if d.isdigit()]), False, reads


def swaps(d):
    #a digit string with each digit swapped, one at a time, for one it's often mistaken for
    return {d[:j] + s + d[j + 1:] for j, c in enumerate(d) for s in SWAPS.get(c, '')}


def time_seconds(d):
    return int(d[0]) * 3600 + int(d[1:3]) * 60 + int(d[3:5]) + int(d[5]) / 10


def pace_seconds(d):
    #'451' (4.51 minutes a km) as 291 seconds
    if not d.isdigit() or len(d) not in (3, 4) or int(d[-2:]) > 59:
        return np.nan
    return int(d[:-2]) * 60 + int(d[-2:])


def in_pace(seconds, pace):
    #the pace is the time over 52 km, rounded down to the second
    return np.isnan(pace) or KM * pace <= seconds < KM * (pace + 1)


def parse_row(r):
    out = {'page': r['page'], 'top': r['top'], 'half': r['half'], 'line_y': r['line_y']}
    #rank: the glyphs, or the OCR's readings
    g_rank = glyph_read(get(r, 'g_rank'))[0]
    ocr_ranks = [num(get(r, 'rank_' + s)) for s in SOURCES]
    lead = ' '.join(get(r, 'rank_' + s) for s in SOURCES).upper()
    out['dnf'] = bool(re.search(r'[DN]', g_rank)) or (not g_rank.isdigit() and bool(re.search(r'DNF|[D0O]N[FE]', lead)))
    out['place_read'], _, reads = numeric(get(r, 'g_rank'), ocr_ranks)
    out['place_cands'] = sorted({int(p) for p in reads if 0 < int(p) < 6000})
    #pace, from the glyphs or the OCR's tail of the line
    g_pace, pace_sure, pace_alts = glyph_read(get(r, 'g_pace'))
    tails = {s: read_tail(get(r, 'tail_' + s) or []) for s in SOURCES}
    ocr_paces = [read_pace(tails[s][2]) for s in SOURCES]
    if pace_sure and not np.isnan(pace_seconds(g_pace)):
        paces = {pace_seconds(g_pace)}
    else:
        paces = {p for p in ocr_paces + [pace_seconds(d) for d in [g_pace] + pace_alts] if not np.isnan(p)}
    out['paces'] = paces
    fits_pace = lambda d: not paces or any(in_pace(time_seconds(d), p) for p in paces)
    #time: the glyphs' when they're sure and fit the pace, else the reading most readings give that fits
    g_time, time_sure, time_alts = glyph_read(get(r, 'g_time'))
    reads = [d for d in [g_time] * 2 + [num(get(r, 'time_' + s)) for s in SOURCES] if ok_digits(d)]
    fit = [d for d in reads if fits_pace(d)]
    time, how = '', 'none'
    if time_sure and ok_digits(g_time) and fits_pace(g_time):
        time, how = g_time, 'glyphs'
    elif fit:
        c = Counter(fit).most_common()
        if len(c) == 1 or c[0][1] > c[1][1]:
            time, how = c[0][0], 'voted'
        else:
            how = 'tied'
    elif reads:
        how = 'misfit'
    out['time'] = time_text(time) if time else ''
    out['time_how'] = how
    #every time the line could have that fits the pace: its readings, then their one-digit swaps
    first = set(reads) | set(time_alts)
    second = {a for d in first | {g_time} for a in swaps(d)} - first
    out['time_cands'] = [sorted(time_text(d) for d in level if ok_digits(d) and fits_pace(d))
                         for level in (first, second)]
    out['timed'] = bool(reads) or len(g_time) >= 5 or any(len(num(get(r, 'time_' + s))) >= 5 for s in SOURCES)
    #bib and class rank
    out['bib'], out['bib_sure'], out['bib_cands'] = numeric(get(r, 'g_bib'), [num(get(r, 'bib_' + s)) for s in SOURCES])
    out['class_rank'], _, reads = numeric(get(r, 'g_crank'), [num(tails[s][0])[:3] for s in SOURCES])
    out['crank_cands'] = sorted({int(d) for d in reads if 0 < int(d) < 2000})
    #class: the glyphs ('M4044'), or the OCR's
    g_cls, cls_sure, _ = glyph_read(get(r, 'g_cls'))
    m = re.fullmatch(r'([MF])(\d\d)(\d\d)', g_cls)
    if cls_sure and m and '{}-{}'.format(m.group(2), m.group(3)) in AGES:
        gender, age = m.group(1), '{}-{}'.format(m.group(2), m.group(3))
    else:
        #a line with a long foreign address has its class where the class rank would be
        classes = [read_class(get(r, 'cls_' + s)) for s in SOURCES] + [read_class(get(r, 'nat_f2'))] + \
                  [read_class(t) for s in SOURCES for t, _ in get(r, 'tail_' + s) or [] if re.match(r'[MF]\d', t)]
        if m:
            classes += [(m.group(1), '{}-{}'.format(m.group(2), m.group(3)))] * 2
        gender = vote([g for g, _ in classes])
        age = vote([a for g, a in classes if a in AGES and g in (gender, '')])
    out['gender'] = gender
    out['age_class'] = age
    out['age_group'] = gender + ' ' + age if gender and age else ''
    #name: first and last name each the one most readings give, among the ones known from other years if any are
    out['name'] = choose_name([get(r, 'name_' + s) for s in NAME_SOURCES])
    #hometown, state and nation: the state most readings give, then the town most give that's known in it
    reads = [(clean_town(get(r, 'town_f2')), get(r, 'st_f2'), read_nation(get(r, 'nat_f2')))]
    reads += [(clean_town(t), st, nat) for t, st, nat in
              (split_town(get(r, 'town_' + s)) for s in NAME_SOURCES[1:])]
    towns = [t.upper() for t, _, _ in reads]
    states = [read_state(st, t) for t, st, _ in reads]
    state = pick(states, lambda v: v in US_STATES | CA_PROVINCES)
    out['city'] = pick(towns, lambda v: (compact(v), state) in known_places())
    out['state'] = state if state in US_STATES | CA_PROVINCES else read_state(state, out['city'])
    #a line with a long foreign address has its nation where the class would be
    nations = [nat for _, _, nat in reads]
    if not any(n in NATIONS for n in nations):
        nations += [read_nation(t) for s in SOURCES for t, _ in get(r, 'tail_' + s) or []
                    if len(re.sub(r'[^A-Za-z]', '', t)) >= 2 and not re.match(r'[MF]\d', t)]
    out['country'] = pick(nations, lambda v: v in NATIONS)
    return out


#---------------------------------------------------------------- places against the times

def anchors(place, secs, weight):
    #the heaviest set of results whose places and times rise together (places strictly, times never falling): a
    #longest increasing subsequence, by a Fenwick tree over the times' ranks
    ok = np.where(~np.isnan(place) & ~np.isnan(secs))[0]
    order = ok[np.lexsort((secs[ok], place[ok]))]
    ranks = {t: k + 1 for k, t in enumerate(np.unique(secs[ok]))}
    n = len(ranks)
    tree_w, tree_i = np.zeros(n + 1), np.full(n + 1, -1)
    best_w, parent = {}, {}

    def query(k):
        w, i = 0.0, -1
        while k > 0:
            if tree_w[k] > w:
                w, i = tree_w[k], tree_i[k]
            k -= k & -k
        return w, i

    def update(k, w, i):
        while k <= n:
            if w > tree_w[k]:
                tree_w[k], tree_i[k] = w, i
            k += k & -k

    start = 0
    while start < len(order):
        end = start
        while end < len(order) and place[order[end]] == place[order[start]]:
            end += 1
        group = order[start:end]
        for i in group:
            w, j = query(ranks[secs[i]])
            best_w[i], parent[i] = w + weight[i], j
        for i in group:
            update(ranks[secs[i]], best_w[i], i)
        start = end
    keep = np.zeros(len(place), bool)
    if best_w:
        i = max(best_w, key=best_w.get)
        while i != -1:
            keep[i] = True
            i = parent[i]
    return keep


def kept(place, secs, keep):
    #the kept results' places and times, in place order, and the places they take
    ap, at = place[keep], secs[keep]
    o = np.argsort(ap)
    return ap[o], at[o], set(ap.astype(int))


def place_list(lst):
    #one gender's places and times, each read from the line, checked against each other: the results whose places
    #and times agree with the most others are kept as read, and the rest are placed between them where that's
    #pinned down: by the one free place among the readings, or by as many free places as results between two kept
    #ones. a time that can't be right for its place is taken from the readings that fit both
    lst = lst.copy()
    secs = lst['time'].map(parse_seconds).astype(float).values
    place = pd.to_numeric(lst['place_read'], errors='coerce').astype(float).values
    place[place <= 0] = np.nan
    weight = np.where(lst['time_how'].eq('glyphs').values, 2.0, 1.0)
    how = np.array([''] * len(lst), dtype=object)
    fixed = np.zeros(len(lst), bool)
    for _ in range(8):
        changed = False
        #a time that doesn't fit a free place: the one time among the readings and their swaps that fits between
        #the places around it
        keep = anchors(place, secs, weight + 4 * fixed)
        ap, at, taken = kept(place, secs, keep)
        for i in np.where(~keep)[0]:
            p = place[i]
            if np.isnan(p) or int(p) in taken:
                continue
            k = np.searchsorted(ap, p)
            lo = at[k - 1] if k > 0 else 0
            hi = at[k] if k < len(at) else np.inf
            if lo <= secs[i] <= hi:
                continue
            for level in lst['time_cands'].iat[i]:
                fits = {t for t in level if lo <= parse_seconds(t) <= hi}
                if fits:
                    break
            if len(fits) == 1:
                secs[i] = parse_seconds(fits.pop())
                how[i] = 'time from place'
                changed = True
        #the gaps between kept results: each other result in the gap its time falls in
        keep = anchors(place, secs, weight + 4 * fixed)
        ap, at, taken = kept(place, secs, keep)
        gaps = {}
        for i in np.where(~keep & ~np.isnan(secs))[0]:
            gaps.setdefault(np.searchsorted(at, secs[i], side='right'), []).append(i)
        for k, rows in gaps.items():
            lo = int(ap[k - 1]) if k > 0 else 0
            hi = int(ap[k]) if k < len(ap) else None
            rows = sorted(rows, key=lambda i: secs[i])
            if hi is not None and hi - lo - 1 == len(rows) and len(set(secs[rows])) == len(rows):
                for i, p in zip(rows, range(lo + 1, hi)):
                    if place[i] != p:
                        how[i] = 'between'
                        changed = True
                    place[i] = p
                    fixed[i] = True
                continue
            for i in rows:
                cands = [c for c in lst['place_cands'].iat[i] if c > lo and (hi is None or c < hi) and c not in taken]
                if len(cands) == 1 and place[i] != cands[0]:
                    place[i] = cands[0]
                    how[i] = 'read'
                    changed = True
        if not changed:
            break
    #what's still out of order can't be told: its place is left blank
    keep = anchors(place, secs, weight + 4 * fixed)
    for i in np.where(~keep & ~np.isnan(secs) & ~np.isnan(place))[0]:
        place[i] = np.nan
        how[i] = 'unplaced'
    lst['place'] = place
    lst['secs'] = secs
    lst['time'] = [time_text_s(s) if not np.isnan(s) else '' for s in secs]
    lst['place_how'] = how
    return lst


def time_text_s(s):
    t = int(round(s * 10))
    return '{}:{:02d}:{:02d}.{}'.format(t // 36000, t // 600 % 60, t // 10 % 60, t % 10)


#---------------------------------------------------------------- class ranks against the places

def class_ranks(df):
    #each class's ranks count up by place: the ranks that agree with the most others are kept, and the others are
    #filled in between them where as many ranks are free as results lie between, or the reading that fits its
    #position, or left blank
    df = df.copy()
    rank = pd.to_numeric(df['class_rank'], errors='coerce').astype(float)
    out = rank.copy()
    for _, c in df[df['age_group'] != ''].groupby('age_group'):
        c = c.sort_values(['place', 'secs'])
        idx = c.index.values
        r = rank[idx].values.copy()
        pos = np.arange(len(idx), dtype=float)
        keep = anchors(r, pos, np.ones(len(idx)))
        bounds = [(-1, 0)] + [(j, int(r[j])) for j in np.where(keep)[0]]
        for (j0, r0), (j1, r1) in zip(bounds, bounds[1:] + [(len(idx), None)]):
            between = list(range(j0 + 1, j1))
            if not between:
                continue
            pinned = r1 is not None and r1 - r0 - 1 == len(between)
            for n, j in enumerate(between, 1):
                out[idx[j]] = r0 + n if pinned or r0 + n in df.at[idx[j], 'crank_cands'] else np.nan
    df['class_rank'] = out.map(lambda v: '' if np.isnan(v) else str(int(v)))
    return df


def fits_list(row, lst):
    #whether a result could sit in a placed list: a place among its readings that's free, between the times of the
    #places around it
    secs = parse_seconds(row['time'])
    if np.isnan(secs):
        return False
    placed = lst.dropna(subset=['place'])
    taken = set(placed['place'].astype(int))
    for p in row['place_cands']:
        before = placed.loc[placed['place'] < p, 'secs'].max()
        after = placed.loc[placed['place'] > p, 'secs'].min()
        if p not in taken and not before > secs and not after < secs:
            return True
    return False


def unique_bibs(df):
    #a bib read twice: the unsure one takes the one other reading of it that no one else has
    df = df.copy()
    for bib, dup in df[df['bib'] != ''].groupby('bib'):
        if len(dup) < 2 or not dup['bib_sure'].any():
            continue
        used = set(df['bib'])
        for i in dup.index[~dup['bib_sure'].astype(bool).values]:
            others = {c for c in df.at[i, 'bib_cands'] if c not in used}
            if len(others) == 1:
                df.at[i, 'bib'] = others.pop()
    return df


def finish(raw):
    df = pd.DataFrame([parse_row(r) for r in raw.to_dict('records')])
    #results that finished: a time read, a name, not DNF
    df = df[~df['dnf'] & df['timed'] & (df['name'].str.len() > 3)]
    lists = {g: place_list(lst) for g, lst in df[df['gender'] != ''].groupby('gender')}
    #a result whose class letter wasn't read: the one list it fits in
    for i, row in df[df['gender'] == ''].iterrows():
        fits = [g for g, lst in lists.items() if fits_list(row, lst)]
        if len(fits) == 1:
            df.at[i, 'gender'] = fits[0]
            df.at[i, 'age_group'] = fits[0] + ' ' + row['age_class'] if row['age_class'] else ''
    df = df[df['gender'] != '']
    df = pd.concat([place_list(lst) for _, lst in df.groupby('gender')])
    df = class_ranks(df)
    df = unique_bibs(df)
    df['place'] = df['place'].map(lambda p: '' if np.isnan(p) else str(int(p)))
    df = df.sort_values(['page', 'half', 'line_y'])
    return df.assign(status='finished', tech='')


def parse(year=YEAR):
    return finish(raw_rows())


#---------------------------------------------------------------- this year's OCR

UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
#each field's strip, in pixels from the left of the NAT column, the characters it can hold and the sizes it's read at
STRIPS = {'rank': (-850, -767, '0123456789DNF', (2, 3)),
          'time': (-767, -673, '0123456789:.', (2, 3)),
          'bib': (-673, -603, '0123456789', (2, 3)),
          'name': (-603, -298, UPPER + ",.'-& ", (3,)),
          'town': (-300, 45, UPPER + ".'- ", (3,)),
          'cls': (45, 122, 'MF0123456789-', (2, 3)),
          'pace': (122, 275, '0123456789.Y', (2, 3))}
#the name and hometown columns read again in chunks of CHUNK_LINES lines, cut between the lines, so that one bad stretch
#(a photo beside the column, as on page 51) can't throw off the whole column's reading: each column's span from the NAT
#column's left edge and the characters it holds, and each reading's scale and whether it keeps to those characters
CHUNK_FIELDS = {'name': (-608, -298, UPPER + ",.'-& "), 'town': (-302, 42, UPPER + ".'- ")}
CHUNK_READINGS = {'c4': (4, True), 'n2': (2, False)}
CHUNK_LINES = 20
#white added around each strip and chunk, in page pixels
PAD = 12
#the glyphs' fields, in pixels from the NAT column's left edge, split in the gaps between the columns, the size they're
#compared at and how many nearest neighbours tell them apart
GLYPH_FIELDS = [('rank', -880, -768), ('time', -768, -676), ('bib', -676, -598), ('cls', 40, 118), ('crank', 118, 172),
                ('pace', 196, 300)]
GLYPH_H, GLYPH_W = 20, 14
NEIGHBOURS = 9
OCR_WORKERS = 4


def ocr(year=YEAR):
    #the whole page first, since the page's lean and its columns come from that reading, and the glyphs last, since
    #the characters they're told apart by are those the other readings agree on
    with concurrent.futures.ThreadPoolExecutor(OCR_WORKERS) as pool:
        list(pool.map(read_page, PAGES))
        jobs = [job for page in PAGES for job in strip_jobs(page)]
        list(pool.map(read_strip, jobs))
        for suffix in CHUNK_READINGS:
            read_chunks(pool, suffix)
    if not all(os.path.exists(ocr_path(page, 'glyphs')) for page in PAGES):
        read_glyphs()


def ocr_path(page, suffix, ext='.tsv'):
    return os.path.join(OCR_DIR, str(YEAR), '{:03d}_{}{}'.format(page, suffix, ext))


def tesseract(image, out, chars):
    image.save(out + '.png')
    whitelist = ['-c', 'tessedit_char_whitelist=' + chars] if chars else []
    subprocess.run([TESSERACT, out + '.png', out, '--psm', '6'] + whitelist + ['tsv'], capture_output=True)
    os.remove(out + '.png')


def read_page(page):
    out = ocr_path(page, 'f2', '')
    if not os.path.exists(out + '.tsv'):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        image = Image.open(os.path.join(PAGE_DIR, str(YEAR), '{:03d}.png'.format(page)))
        tesseract(image.resize((image.width * 2, image.height * 2), Image.LANCZOS), out, '')


def level(page):
    #the page turned upright by the lean of its NAT column (fitted from the whole page's reading), and where each
    #field's strip down each half sits in it
    if os.path.exists(ocr_path(page, 'level', '.png')) and os.path.exists(ocr_path(page, 'strips', '.json')):
        return
    (a0, b0), (a1, b1) = nat_lines(words(page))
    theta = -math.atan((b0 + b1) / 2)
    image = Image.open(os.path.join(PAGE_DIR, str(YEAR), '{:03d}.png'.format(page)))
    cx, cy = image.width / 2, image.height / 2
    upright = image.rotate(math.degrees(theta), resample=Image.BICUBIC, fillcolor=255)
    upright.save(ocr_path(page, 'level', '.png'))
    y = image.height / 2
    nats = [cx + (a + b * y - cx) * math.cos(theta) + (y - cy) * math.sin(theta) for a, b in ((a0, b0), (a1, b1))]
    g = {'angle': math.degrees(theta), 'theta': theta, 'center': [cx, cy], 'nat': nats, 'pad': PAD, 'strips': {}}
    for half, nat in zip('LR', nats):
        for field, (x0, x1, chars, scales) in STRIPS.items():
            box = [int(round(nat + x0)), 0, int(round(nat + x1)), upright.height]
            g['strips'][half + field] = [max(box[0], 0), box[1], min(box[2], upright.width), box[3]]
    with open(ocr_path(page, 'strips', '.json'), 'w') as f:
        json.dump(g, f, indent=1)


def strip_jobs(page):
    level(page)
    return [(page, name, box, STRIPS[name[1:]][2], scale) for name, box in geometry(page)['strips'].items()
            for scale in STRIPS[name[1:]][3]]


def read_strip(job):
    #one strip, with PAD white pixels added on its left and right; boxes in the strip's scaled pixels
    page, name, box, chars, scale = job
    out = ocr_path(page, '{}_s{}'.format(name, scale), '')
    if os.path.exists(out + '.tsv'):
        return
    strip = Image.open(ocr_path(page, 'level', '.png')).crop(box)
    padded = Image.new('L', (strip.width + 2 * PAD, strip.height), 255)
    padded.paste(strip, (PAD, 0))
    tesseract(padded.resize((padded.width * scale, padded.height * scale), Image.LANCZOS), out, chars)


def chunk_spans(page, half):
    #the line centers of a half page cut into runs of CHUNK_LINES, as (top, bottom) in the upright page
    centers = np.sort([r['line_y'] for r in page_rows(page) if r['half'] == half])
    out = []
    for k in range(0, len(centers), CHUNK_LINES):
        c = centers[k:k + CHUNK_LINES]
        top = (c[0] + centers[k - 1]) / 2 if k else c[0] - 20
        after = centers[k + CHUNK_LINES] if k + CHUNK_LINES < len(centers) else c[-1] + 40
        out.append((int(top), int(round((c[-1] + after) / 2))))
    return out


def read_chunks(pool, suffix):
    #each half's name and hometown columns, chunk by chunk, as <page>_<L|R><field>_<suffix>.tsv: tesseract's tsv with
    #the boxes turned back into the upright page's pixels and the chunk's top in 'chunk'
    columns = [(page, half, field) for page in PAGES for half in (0, 1) for field in CHUNK_FIELDS
               if not os.path.exists(ocr_path(page, '{}{}_{}'.format('LR'[half], field, suffix)))]
    jobs = [(page, half, field, top, bottom, suffix) for page, half, field in columns
            for top, bottom in chunk_spans(page, half)]
    out = {}
    for page, half, field, w in pool.map(read_chunk, jobs):
        out.setdefault((page, half, field), []).append(w)
    for (page, half, field), ws in out.items():
        path = ocr_path(page, '{}{}_{}'.format('LR'[half], field, suffix))
        pd.concat(ws, ignore_index=True).round(1).to_csv(path, sep='\t', index=False)


def read_chunk(job):
    page, half, field, top, bottom, suffix = job
    scale, whitelist = CHUNK_READINGS[suffix]
    x0, x1, chars = CHUNK_FIELDS[field]
    nat = geometry(page)['nat'][half]
    left, right = int(round(nat + x0)), int(round(nat + x1))
    chunk = Image.open(ocr_path(page, 'level', '.png')).crop((left, top, right, bottom))
    padded = Image.new('L', (chunk.width + 2 * PAD, chunk.height + 2 * PAD), 255)
    padded.paste(chunk, (PAD, PAD))
    tmp = ocr_path(page, 'tmp_{}{}_{}_{}'.format('LR'[half], field, suffix, top), '')
    tesseract(padded.resize((padded.width * scale, padded.height * scale), Image.LANCZOS), tmp,
              chars if whitelist else '')
    w = pd.read_csv(tmp + '.tsv', sep='\t', quoting=3, dtype={'text': str}, keep_default_na=False, encoding='utf-8',
                    encoding_errors='replace')
    os.remove(tmp + '.tsv')
    for c in ('left', 'top', 'width', 'height'):
        w[c] = w[c] / scale
    w['left'] += left - PAD
    w['top'] += top - PAD
    w['chunk'] = top
    return page, half, field, w


def glyph_feature(bitmap):
    c = np.zeros((GLYPH_H, GLYPH_W), float)
    h, w = min(bitmap.shape[0], GLYPH_H), min(bitmap.shape[1], GLYPH_W)
    oy, ox = (GLYPH_H - h) // 2, (GLYPH_W - w) // 2
    c[oy:oy + h, ox:ox + w] = bitmap[:h, :w]
    return ndimage.gaussian_filter(c, 0.8).ravel()


def split_glyphs(bitmap, n):
    #a component of n characters run together, cut at the emptiest columns near equal widths
    w = bitmap.shape[1]
    ink = bitmap.sum(0)
    cuts = [0]
    for k in range(1, n):
        guess = int(round(k * w / n))
        lo, hi = max(cuts[-1] + 3, guess - 3), min(w - 3, guess + 4)
        cuts.append(lo + int(np.argmin(ink[lo:hi])) if hi > lo else guess)
    cuts.append(w)
    return [(a, bitmap[:, a:b]) for a, b in zip(cuts[:-1], cuts[1:])]


def page_glyphs(page):
    #each character of the numeric columns: the pages are clean bilevel scans of one typeface at one size, so each is
    #its own connected component, about 16 pixels tall
    g = geometry(page)
    im = np.array(Image.open(ocr_path(page, 'level', '.png'))) < 128
    out = []
    for half in (0, 1):
        nat = g['nat'][half]
        for field, a, b in GLYPH_FIELDS:
            x0, x1 = int(round(nat + a)), int(round(nat + b))
            lab, n = ndimage.label(im[:, x0:x1], structure=np.ones((3, 3)))
            comps = []
            for k, (ys, xs) in enumerate(ndimage.find_objects(lab), 1):
                comps.append([ys.start, ys.stop, xs.start, xs.stop, [k]])
            #pieces of one broken character: boxes that overlap across most of the narrower one's width and touch or
            #nearly touch up and down
            comps.sort(key=lambda c: c[2])
            merged = []
            for c in comps:
                for m in merged[-4:]:
                    overlap = min(c[3], m[3]) - max(c[2], m[2])
                    gap = max(c[0], m[0]) - min(c[1], m[1])
                    if overlap >= 0.6 * min(c[3] - c[2], m[3] - m[2]) and gap <= 2 and \
                            max(c[1], m[1]) - min(c[0], m[0]) <= 20:
                        m[0], m[1], m[2], m[3] = min(c[0], m[0]), max(c[1], m[1]), min(c[2], m[2]), max(c[3], m[3])
                        m[4] += c[4]
                        break
                else:
                    merged.append(c)
            for t, bt, l, r, ks in merged:
                h, w = bt - t, r - l
                if not 11 <= h <= 21 or w < 2:
                    continue
                bitmap = np.isin(lab[t:bt, l:r], ks)
                n = 1 if w <= 14 else 2 if w <= 23 else 3 if w <= 33 else 0
                for dx, part in split_glyphs(bitmap, n) if n > 1 else [(0, bitmap)] if n else []:
                    cols = np.where(part.any(0))[0]
                    rows = np.where(part.any(1))[0]
                    if not len(cols):
                        continue
                    part = part[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
                    left = x0 + l + dx + cols[0]
                    out.append({'page': page, 'half': half, 'field': field, 'left': left, 'top': t + rows[0],
                                'width': part.shape[1], 'height': part.shape[0], 'rel': left - nat,
                                'yc': t + rows[0] + part.shape[0] / 2, 'split': n > 1, 'bitmap': part})
    return out


def glyph_labels(raw):
    #(page, half, line, field): the characters every OCR reading of the field agrees on
    out = {}
    for r in raw.to_dict('records'):
        line = (r['page'], r['half'], r['line_y'])
        for f in ('rank', 'time', 'bib', 'cls'):
            texts = [r.get(f + '_' + s) for s in ('s2', 's3', 'f2')]
            texts = [t if isinstance(t, str) else '' for t in texts]
            if f == 'cls':
                texts = [re.sub(r'[^MF0-9]', '', t.upper()) for t in texts]
            elif f == 'rank' and all(re.fullmatch(r'\s*DNF\s*', t) for t in texts):
                texts = ['DNF'] * 3
            else:
                texts = [num(t) if re.fullmatch(r'[\d:.\s]+', t) else '' for t in texts]
            if texts[0] and texts[0] == texts[1] == texts[2]:
                out[line + (f,)] = texts[0]
    return out


def read_glyphs():
    #every glyph told apart by its nearest neighbours among the glyphs whose field all three OCR readings agree on (5-fold
    #cross validation: 99.8% agree with those readings, and nearly all the rest are 1s the readings call 4s), as
    #<page>_glyphs.tsv: one row per glyph with its half, field, box in the upright page, x from the half's NAT column, the
    #best and second best class with their shares of the nearest neighbours, and the mean distance to them (large for a
    #smudge or a part of a letter)
    from sklearn.model_selection import cross_val_predict
    from sklearn.neighbors import KNeighborsClassifier
    raw = raw_rows()
    glyphs = pd.DataFrame([gl for p in PAGES for gl in page_glyphs(p)])
    #each glyph's line: the nearest line center
    glyphs['line_y'] = np.nan
    for (p, h), grp in glyphs.groupby(['page', 'half']):
        centers = np.sort(raw.loc[(raw['page'] == p) & (raw['half'] == h), 'line_y'].values)
        j = np.abs(grp['yc'].values[:, None] - centers[None, :]).argmin(1)
        near = np.abs(grp['yc'].values - centers[j]) <= 10
        glyphs.loc[grp.index[near], 'line_y'] = centers[j[near]]
    glyphs = glyphs.dropna(subset=['line_y'])
    lab = glyph_labels(raw)
    X = np.array([glyph_feature(b) for b in glyphs['bitmap']])
    glyphs['label'] = ''
    for key, grp in glyphs.sort_values('left').groupby(['page', 'half', 'line_y', 'field']):
        text = lab.get(key)
        if text and len(text) == len(grp):
            glyphs.loc[grp.index, 'label'] = list(text)
    train = (glyphs['label'] != '').values
    Xt, Yt = X[train], glyphs.loc[train, 'label'].values
    pred = cross_val_predict(KNeighborsClassifier(NEIGHBOURS), Xt, Yt, cv=5)
    print('glyphs: {} known, cross validated agreement {:.5f}'.format(len(Yt), (pred == Yt).mean()))
    knn = KNeighborsClassifier(NEIGHBOURS).fit(Xt, Yt)
    dist, idx = knn.kneighbors(X)
    best, p1, second, p2 = [], [], [], []
    for v in Yt[idx]:
        c = Counter(v).most_common(2) + [('', 0)]
        best.append(c[0][0])
        p1.append(c[0][1] / NEIGHBOURS)
        second.append(c[1][0])
        p2.append(c[1][1] / NEIGHBOURS)
    glyphs['text'], glyphs['p1'], glyphs['second'], glyphs['p2'] = best, p1, second, p2
    glyphs['dist'] = dist.mean(1).round(3)
    cols = ['half', 'field', 'left', 'top', 'width', 'height', 'rel', 'line_y', 'split', 'text', 'p1', 'second', 'p2',
            'dist']
    for p, grp in glyphs.groupby('page'):
        grp.sort_values(['half', 'line_y', 'left'])[cols].round(3).to_csv(ocr_path(p, 'glyphs'), sep='\t', index=False)
