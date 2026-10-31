#1995 birch scroll: "MEN'S DYNO AMERICAN BIRKEBEINER RESULTS" on pages 37-52 (places 1-3472) and "WOMEN'S ..." on pages
#53-55 (places 1-558), then the kortelopet (56-64), which is left out, as are the class winners (page 8). two results to
#a line, each with RANK, FINAL TIME (h:mm:ss, no tenths), BIB, NAME, HOMETOWN, ST, NAT, CLASS ("M30-34", "M70+"), CLASS
#RANK, 25% ("Y") and PACE MN/KM (the time over 52 km in min.sec, cut to the second). one list per gender, classic and
#skate skiers together with no technique marked, so tech is left blank. every full column holds 110 places, 25 pixels
#apart.
#
#the scans are two-tone (old_results/pages/1995/NNN.png; 'top' is in their pixels), and this parser reads them as well as
#the OCR. ocr() straightens each results page by its angle in SKEW (PIL: the page at twice or three times the size,
#LANCZOS, then rotated, BICUBIC, white fill) and reads it three times with tesseract --psm 6: the whole page at twice the
#size with a character whitelist (old_results/ocr/1995/NNN_d2.tsv), each column cropped at three times the size with the
#whitelist (NNN_c3_0.tsv, NNN_c3_1.tsv, crop boxes in NNN_c3.json) and each column's names and towns cropped at twice the
#size with no whitelist (NNN_n2_0.tsv, NNN_n2_1.tsv, boxes in NNN_n2.json). OCR places the rows and gives each field's
#readings.
#
#the scan itself then settles what the readings leave open (tesseract reads this condensed typeface's figures badly:
#'141' as '144', a final 1 as 4 in about one time in a hundred):
#- figures (times, bibs, class ranks, paces) are cut from the scan and matched against figures of known value, those of
#  the RANK column, whose values are the places. a sure match comes before the OCR readings
#- words: a space is 5 or more blank pixel columns and each capital's width is known, so a name or town reading has to
#  fit the scan's words; initials OCR dropped, a final I it dropped and D/O are read from the scan, and letters the
#  readings disagree on are matched against letters of names the readings all agree on
#- states are matched against state codes whose reading is sure; towns OCR misspelt are repaired only to the one known
#  town of that state within an edit that also fits the scan
#then the class ranks count up within each class, times never go down with place and fit the pace, and no two skiers
#share a bib. repairs are made only where these pin a value down; a bib that can't be read is left blank
import bisect
import concurrent.futures
import functools
import json
import math
import os
import re
import subprocess

import numpy as np
import pandas as pd

from birkie_archive import OCR_DIR, PAGE_DIR, TESSERACT, DIGITS, known_towns, state_code, parse_seconds
from results_loader import load_all_results, compact, normalize_location, US_STATES, CA_PROVINCES

YEAR = 1995
#page size, for undoing the rotation
WIDTH, HEIGHT = 2552, 3300
#each page's tilt in degrees (PIL's rotate, counterclockwise), found by the sharpest row profile
SKEW = {37: -0.35, 38: -0.4, 39: -0.3, 40: -1.0, 41: -1.8, 42: 0.2, 43: 0.1, 44: -0.95, 45: -1.15, 46: -0.65,
        47: -1.8, 48: -0.35, 49: -0.3, 50: -0.7, 51: -0.25, 52: -0.3, 53: -1.95, 54: -0.35, 55: -0.5}
LISTS = {'M': range(37, 53), 'F': range(53, 56)}
DISTANCE_KM = 52
#columns as offsets from the left edge of the FINAL TIME column, in page pixels (numbers are right aligned)
COLUMNS = [('rank', -130), ('time', -12), ('bib', 92), ('name', 158), ('town', 455), ('st', 678), ('nat', 742),
           ('cls', 800), ('crank', 880), ('y', 930), ('pace', 962), ('end', 1045)]
CLASSES = ['18-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', '65-69', '70+']
NATIONS = {'USA', 'CAN', 'SUI', 'SWE', 'CZE', 'CZ', 'NOR', 'AUT', 'GER', 'ITA', 'FIN', 'FRA', 'RUS', 'SLO', 'AUS',
           'JPN', 'DEN', 'NED', 'BEL', 'AND', 'POL', 'SVK', 'GBR', 'EST', 'KOR', 'ESP', 'KAZ', 'UKR', 'BLR', 'JAP',
           'ISL', 'NZL', 'ARG', 'CHI', 'MEX', 'IRL', 'HUN', 'SLK', 'LAT', 'LTU', 'CRO', 'BRA', 'RSA'}
STATES = US_STATES | CA_PROVINCES
#the tables' three-letter provinces
PROVINCES = {'ONT': 'ON', 'MAN': 'MB', 'QUE': 'QC', 'SAS': 'SK', 'ALB': 'AB'}
#strips of each column read on their own as well: 'n2' the names and towns at twice the size, no whitelist
STRIPS = ['n2']


def parse(year):
    return finish(read_lists())


def read_lists():
    #every column of every list as OCR read it, each row with every reading's values
    rows = []
    for gender, pages in LISTS.items():
        start = 1
        for page in pages:
            for i, edge in enumerate(range_halves(page)):
                column = read_column(page, i, edge, start)
                if column.empty:
                    continue
                start = int(column['place'].max()) + 1
                rows.append(column.assign(gender=gender, page=page, edge=edge))
    return pd.concat(rows, ignore_index=True)


def finish(df):
    #the scan's own figures and words, then each list's classes and times
    df = read_figures(df)
    df = read_words(df)
    out = []
    for gender, lst in df.groupby('gender', sort=False):
        lst = lst.sort_values('place').reset_index(drop=True)
        lst = repair_classes(lst, gender)
        lst = repair_times(lst)
        out.append(lst)
    df = pd.concat(out, ignore_index=True)
    df = unique_bibs(df)
    df['place'] = df['place'].astype(int).astype(str)
    return df.assign(status='finished', tech='')[['place', 'bib', 'name', 'gender', 'age_group', 'class_rank', 'city',
                                                 'state', 'country', 'time', 'status', 'tech', 'page', 'top']]


def unique_bibs(df):
    #two skiers can't share a bib: the surer reading keeps it, and the other takes another reading of its own that no
    #one else has, or none
    df = df.copy()
    for bib, g in df[df['bib'] != ''].groupby('bib'):
        if len(g) < 2:
            continue
        order = g.sort_values('bib_margin', ascending=False).index
        for i in order[1:]:
            taken = set(df['bib'])
            other = [b for b in df.at[i, 'bib_alts'] if b != bib and b not in taken]
            df.at[i, 'bib'] = other[0] if other else ''
    return df


#---------------------------------------------------------------- this year's OCR

OCR_CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:.,-'&+ "
#each column read again on its own: its suffix, scale, span from the FINAL TIME column's left edge, and whether it keeps
#to OCR_CHARACTERS
CROPS = [('c3', 3, -150, 1060, True), ('n2', 2, 150, 685, False)]
OCR_WORKERS = 4


def ocr(year=YEAR):
    #each results page read whole first, since where its columns are comes from that reading
    with concurrent.futures.ThreadPoolExecutor(OCR_WORKERS) as pool:
        list(pool.map(read_page, SKEW))
        jobs = [(page, i, crop) for page in SKEW for crop in CROPS for i in range(len(column_boxes(page, crop)))]
        for out in pool.map(lambda job: read_crop(*job), jobs):
            print(out)


def straightened(page, scale):
    from PIL import Image
    image = Image.open(os.path.join(PAGE_DIR, str(YEAR), '{:03d}.png'.format(page)))
    image = image.resize((image.width * scale, image.height * scale), Image.LANCZOS)
    return image.rotate(SKEW[page], resample=Image.BICUBIC, fillcolor=255)


def tesseract(image, out, whitelist):
    image.save(out + '.png')
    chars = ['-c', 'tessedit_char_whitelist=' + OCR_CHARACTERS] if whitelist else []
    subprocess.run([TESSERACT, out + '.png', out, '--psm', '6'] + chars + ['tsv'], capture_output=True)
    os.remove(out + '.png')


def read_page(page):
    out = os.path.join(OCR_DIR, str(YEAR), '{:03d}_d2'.format(page))
    if not os.path.exists(out + '.tsv'):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        tesseract(straightened(page, 2), out, True)


def column_boxes(page, crop):
    #each column's box in the straightened page's pixels, kept in <page>_<suffix>.json
    suffix, scale, x0, x1, whitelist = crop
    path = os.path.join(OCR_DIR, str(YEAR), '{:03d}_{}.json'.format(page, suffix))
    if not os.path.exists(path):
        boxes = [[max(0, int(e + x0)), 0, min(WIDTH, int(e + x1)), HEIGHT] for e in range_halves(page)]
        with open(path, 'w') as f:
            json.dump(boxes, f)
    with open(path) as f:
        return json.load(f)


def read_crop(page, i, crop):
    suffix, scale, x0, x1, whitelist = crop
    out = os.path.join(OCR_DIR, str(YEAR), '{:03d}_{}_{}'.format(page, suffix, i))
    if not os.path.exists(out + '.tsv'):
        box = column_boxes(page, crop)[i]
        tesseract(straightened(page, scale).crop([v * scale for v in box]), out, whitelist)
    return out


#---------------------------------------------------------------- words and rows

def page_words(page, reading='d2'):
    #one reading of a page's words, in the straightened page's pixels: the whole page at twice the size ('d2') or one
    #column cropped and read at three times the size ('c3_0', 'c3_1')
    base = os.path.join(OCR_DIR, str(YEAR), '{:03d}_'.format(page))
    if reading == 'd2':
        scale, x0, y0 = 2, 0, 0
    else:
        kind, i = reading.rsplit('_', 1)
        with open(base + kind + '.json') as f:
            box = json.load(f)[int(i)]
        scale, x0, y0 = int(kind[1:]), box[0], box[1]
    w = pd.read_csv(base + reading + '.tsv', sep='\t', quoting=3, dtype={'text': str}, keep_default_na=False)
    w = w[(w['level'] == 5) & (w['text'].str.strip() != '')].copy()
    for c in ['left', 'top', 'width', 'height']:
        w[c] = w[c] / scale
    w['left'] += x0
    w['top'] += y0
    w['x'] = w['left'] + w['width'] / 2
    w['y'] = w['top'] + w['height'] / 2
    return w.reset_index(drop=True)


def original_y(page, x, y):
    #a point on the straightened page back on the scan as it is
    t = math.radians(SKEW[page])
    dx, dy = x - WIDTH / 2, y - HEIGHT / 2
    return HEIGHT / 2 + dx * math.sin(t) + dy * math.cos(t)


TIME_WORD = re.compile(r'^\W*\d[:;.,]?\d\d[:;.,]?\d\d\W*$')


def range_halves(page):
    #the left edge of the FINAL TIME column in each half of the page, from where the times sit, split at the widest gap
    w = page_words(page)
    t = w[w['text'].str.match(TIME_WORD) & w['text'].str.contains(r'[:;]')]
    lefts = np.sort(t['left'].values)
    if len(lefts) < 3:
        return []
    cut = np.argmax(np.diff(lefts)) + 1
    groups = [lefts[:cut], lefts[cut:]] if lefts[cut] - lefts[cut - 1] > 300 else [lefts]
    return [float(np.median(g)) for g in groups if len(g) >= 3]


def half_rows(page, edge, reading, strip=False):
    #one column of results: words between the RANK and PACE columns, grouped into rows by height, each row's fields by
    #where its words sit
    w = page_words(page, reading)
    w = w[(w['x'] >= edge + COLUMNS[0][1]) & (w['x'] < edge + COLUMNS[-1][1])].sort_values('y')
    groups, current = [], []
    for _, word in w.iterrows():
        if current and word['y'] - np.mean([c['y'] for c in current]) > 9:
            groups.append(current)
            current = []
        current.append(word)
    if current:
        groups.append(current)
    rows = []
    for g in groups:
        g = sorted(g, key=lambda r: r['left'])
        fields = {name: [] for name, _ in COLUMNS[:-1]}
        for word in g:
            rel = word['x'] - edge
            fields[[n for n, off in COLUMNS[:-1] if rel >= off][-1]].append(word)
        record = read_row(fields, strip)
        if record:
            record['top'] = int(round(original_y(page, edge + 500, min(r['top'] for r in g))))
            record['y'] = float(np.mean([r['y'] for r in g]))
            #where the class rank and the 25% mark sit, for reading the class rank's figures from the scan
            crank = [r for r in fields['crank'] if re.search(r'\d', r['text'])]
            record['crank_l'] = min(r['left'] for r in crank) - edge if crank else np.nan
            record['crank_r'] = max(r['left'] + r['width'] for r in crank) - edge if crank else np.nan
            record['y_left'] = min(r['left'] for r in fields['y']) - edge if fields['y'] else np.nan
            rows.append(record)
    return pd.DataFrame(rows)


def text_of(words):
    return ' '.join(w['text'] for w in words)


def conf_of(words):
    return min([float(w['conf']) for w in words] or [0])


def read_row(fields, strip=False):
    #a result's fields, or None for a line that isn't one (headings, photo specks). a strip of the columns needs only
    #something in one of its columns
    time_raw = text_of(fields['time'])
    cls_text = text_of(fields['cls'])
    cls = read_class(cls_text) if cls_text else None
    pace = re.search(r'(\d)\W?(\d\d)\W*$', text_of(fields['pace']))
    clues = sum([bool(re.search(r'\d.*\d.*\d.*\d', time_raw)), cls is not None, pace is not None,
                 bool(digits(text_of(fields['bib']))), bool(fields['name'])])
    if clues < (1 if strip else 3):
        return None
    crank = digits(text_of(fields['crank']))
    if not crank:
        #a class rank run into the class ("M35-39.-172")
        m = re.search(r'\d\d(?:-?\d\d|\+)\W+(\d{1,3})$', cls_text)
        crank = m.group(1) if m else ''
    return {'rank_ocr': digits(text_of(fields['rank']))[-4:],
            'time_raw': time_raw, 'time': read_time(time_raw),
            'bib': digits(text_of(fields['bib']))[-5:], 'bib_conf': conf_of(fields['bib']),
            'name': clean_name(fields['name']), 'name_conf': conf_of(fields['name']),
            'city': clean_town(fields['town']), 'city_conf': conf_of(fields['town']),
            'state': state_code(re.sub(r'[^A-Za-z1]', '', text_of(fields['st']))),
            'country': read_nation(text_of(fields['nat'])),
            'cls': cls, 'class_rank': crank[:3] if 0 < len(crank) else '',
            'pace': int(pace.group(1)) * 60 + int(pace.group(2)) if pace and int(pace.group(2)) < 60 else np.nan}


def digits(text):
    return re.sub(r'\D', '', str(text).translate(DIGITS))


def read_time(text):
    #'2:10:15' as h:mm:ss, from five digits, or the last h:mm:ss in a word with a stray mark run into it ('93:11:43',
    #'41-2:16:00', '3:11:37 9')
    t = str(text).translate(DIGITS)
    m = re.search(r'(\d)[:;.,](\d\d)[:;.,]?(\d\d)(?!.*\d[:;.,]\d\d)', t)
    d = ''.join(m.groups()) if m else digits(text)
    if len(d) != 5 or int(d[1:3]) > 59 or int(d[3:5]) > 59:
        return ''
    return '{}:{}:{}'.format(d[0], d[1:3], d[3:5])


def read_class(text):
    #'M30-34' -> ('M', '30-34'), as printed or as OCR left it ('M3034', 'Ma30-34', 'MS50-54', '30-34', 'M85-39'); the
    #class is None when it can't be told
    t = text.upper().replace(' ', '')
    m = re.search(r'([MF]?)\W*[A-Z]?([0-9OSBILZ]{2})\W*-?\W*([0-9OSBILZ]{1,2}|\+)?', t)
    if not m or not re.search(r'\d', t):
        return None
    lo = m.group(2).translate(DIGITS)
    hi = (m.group(3) or '').translate(DIGITS) if m.group(3) != '+' else '+'
    if hi == '+':
        return (m.group(1), lo + '+' if lo + '+' in CLASSES else None)
    if '{}-{}'.format(lo, hi) in CLASSES:
        return (m.group(1), '{}-{}'.format(lo, hi))
    #one end read wrong: the other end names the class
    by_hi = [c for c in CLASSES if len(hi) == 2 and c.endswith('-' + hi)]
    by_lo = [c for c in CLASSES if c.startswith(lo + '-') or c == lo + '+']
    if len(by_hi) == 1 and not by_lo:
        return (m.group(1), by_hi[0])
    if len(by_lo) == 1 and not by_hi:
        return (m.group(1), by_lo[0])
    return (m.group(1), None)


def read_nation(text):
    t = re.sub(r'[^A-Z]', '', text.upper())
    if t in NATIONS:
        return t
    if len(t) > 3 and t[-3:] in NATIONS:
        return t[-3:]
    return t


def clean_town(words):
    #a town as printed (foreign towns keep their post codes, '5760 SAALFELDEN'), without OCR's stray marks
    out = []
    for w in words:
        t = re.sub(r"[^A-Za-z0-9'&.-]", '', w['text']).strip(".-'")
        if t and (len(t) > 1 or t.isalpha()):
            out.append(t.upper())
    return ' '.join(out)


def clean_name(words):
    #a name, letters only: OCR's digits in a name ('ROBERT 8B MCKAY') and stray marks dropped. a figure on its own is
    #an initial OCR took for one ('BRUCE 8 BERRY'); whether it is fits the scan's word widths is checked later
    out = []
    for w in words:
        t = re.sub(r"[^A-Za-z'-]", '', {'8': 'B', '0': 'O', '1': 'I', '5': 'S', '6': 'G'}.get(w['text'], w['text']))
        t = t.strip("-'")
        if t:
            out.append(t.upper())
    return ' '.join(out)


#---------------------------------------------------------------- one column, two readings

def read_column(page, i, edge, start):
    #the column read from the whole page and from its own crop. the reading with more ranks that count up (the whole
    #page, on a tie) places the rows; the other's rows take the place of the row at the same height. each field then
    #comes from the first reading that gives a valid value
    readings, strips = [], []
    for name in ['d2', 'c3_{}'.format(i)] + ['{}_{}'.format(s, i) for s in STRIPS]:
        if os.path.exists(os.path.join(OCR_DIR, str(YEAR), '{:03d}_{}.tsv'.format(page, name))):
            strip = name[:2] in STRIPS
            rows = half_rows(page, edge, name, strip)
            if not rows.empty:
                (strips if strip else readings).append(rows if strip else assign_places(rows, start))
    if not readings:
        return pd.DataFrame()
    readings.sort(key=lambda r: -r['place_agrees'].sum())
    main = readings[0]
    for other in readings[1:] + strips:
        other['place'] = [place_at(main, y) for y in other['y']]
    #a strip only adds to a place a full reading has: on its own, a line of names (a heading, a caption) isn't a result
    full = set(pd.concat(readings)['place'].dropna())
    strips = [s[s['place'].isin(full)] for s in strips]
    both = pd.concat(readings + strips, ignore_index=True)
    both = both[both['place'].notna()]
    return pd.DataFrame([merge(g) for _, g in both.groupby('place')])


def assign_places(column, start):
    #rows are 25 pixels apart and count up by one, so a row's place is the column's first place plus the rows above it
    #(a row OCR lost leaves a gap). the first place is the one most of the ranks OCR read agree on
    column = column.sort_values('y').reset_index(drop=True)
    gaps = np.diff(column['y'].values)
    pitch = np.median(gaps) if len(gaps) else 25
    steps = np.concatenate([[0], np.maximum(1, np.round(gaps / pitch))]).astype(int)
    row = np.cumsum(steps)
    ocr = pd.to_numeric(column['rank_ocr'], errors='coerce')
    offsets = (ocr - row).dropna()
    first = int(offsets.mode().iloc[0]) if len(offsets) else start
    column['place'] = first + row
    column['place_agrees'] = ocr.values == column['place'].values
    return column


def place_at(main, y, pitch=25.0):
    #the place of the row at height y, counted from the nearest row of the main reading
    j = (main['y'] - y).abs().idxmin()
    steps = (y - main.loc[j, 'y']) / pitch
    if abs(steps - round(steps)) > 0.3:
        return np.nan
    return main.loc[j, 'place'] + int(round(steps))


@functools.lru_cache(maxsize=None)
def known_names():
    clean = load_all_results()
    clean = clean[clean['year'] != YEAR]
    return (clean['first'].map(compact).value_counts().to_dict(), clean['last'].map(compact).value_counts().to_dict())


def name_score(name):
    first, last = known_names()
    tokens = name.split()
    if not tokens:
        return -1
    return (len(tokens) >= 2) + (compact(tokens[0]) in first) + (compact(tokens[-1]) in last)


def merge(g):
    #one place's readings: the first valid value of each field, readings in order
    g = g.reset_index(drop=True)
    pick = lambda col, ok: next((v for v in g[col] if ok(v)), g[col].iloc[0])
    out = {'place': int(g['place'].iloc[0]), 'top': int(g['top'].iloc[0]), 'y': float(g['y'].iloc[0])}
    for c in ['crank_l', 'crank_r']:
        out[c] = float(g[c].median()) if g[c].notna().any() else np.nan
    out['y_left'] = float(g['y_left'].min()) if g['y_left'].notna().any() else np.nan
    out['time_raws'] = list(g['time_raw'])
    out['time_alts'] = list(dict.fromkeys(t for t in g['time'] if t))
    out['paces'] = list(dict.fromkeys(p for p in g['pace'] if np.isfinite(p)))
    bibs = g[g['bib'] != ''].sort_values('bib_conf', ascending=False)
    out['bib_alts'] = list(dict.fromkeys(bibs['bib']))
    out['bib'] = out['bib_alts'][0] if out['bib_alts'] else ''
    #the name most like the names in other years, then the surer reading
    votes = g['name'].map(compact).map(g['name'].map(compact).value_counts())
    names = g.assign(score=g['name'].map(name_score) + 0.5 * votes).sort_values(['score', 'name_conf'], ascending=False)
    names = names[names['name'] != ''] if (names['name'] != '').any() else names
    out['name'] = fix_squashed(names['name'].iloc[0])
    out['name_alts'] = list(dict.fromkeys(names['name']))
    out['state_alts'] = list(dict.fromkeys(province(s) for s in g['state'] if s))
    valid = [s for s in out['state_alts'] if s in STATES]
    out['state'] = (valid or out['state_alts'] or [''])[0]
    out['state_n'] = sum(province(s) == out['state'] for s in g['state'])
    out['states_read'] = [province(s) for s in g['state'] if s]
    out['country'] = pick('country', lambda c: c in NATIONS)
    towns = known_towns()
    out['city'] = pick('city', lambda c: (compact(c), out['state']) in towns)
    if not out['city']:
        out['city'] = pick('city', lambda c: c != '')
    #the towns read, the one most readings agree on first
    cities = g[g['city'] != '']['city']
    out['city_alts'] = list(cities.map(lambda c: (-(cities == c).sum(), c)).sort_values().map(lambda t: t[1]).unique())
    out['cls'] = pick('cls', lambda c: c is not None and c[1] is not None)
    out['class_ranks'] = list(dict.fromkeys(r for r in g['class_rank'] if r))
    return out


def province(state):
    return PROVINCES.get(state, state)


def fix_squashed(name):
    #a middle initial OCR ran into a name: 'WILLIAML SMITH', 'ALLISON ABARTA', 'JIMARIDDER', 'DANIELLGERDTS'. split only
    #where the name as read isn't known from other years and the split one is
    first, last = known_names()
    tokens = name.split()
    if not tokens:
        return name
    if len(tokens) == 1:
        t = tokens[0]
        best, score = None, 0
        for a in range(2, len(t) - 1):
            for b in (a, a + 1):
                f, m, l = t[:a], t[a:b], t[b:]
                if len(l) >= 2 and compact(f) in first and compact(l) in last:
                    s = min(first[compact(f)], last[compact(l)])
                    if s > score:
                        best, score = ' '.join(x for x in (f, m, l) if x), s
        return best or name
    f, l = tokens[0], tokens[-1]
    if compact(f) not in first and len(f) >= 4 and compact(f[:-1]) in first:
        tokens = [f[:-1], f[-1]] + tokens[1:]
    if compact(l) not in last and len(l) >= 4 and compact(l[1:]) in last and len(tokens) == 2:
        tokens = tokens[:-1] + [l[0], l[1:]]
    return ' '.join(tokens)


#---------------------------------------------------------------- digits read from the scan itself

#tesseract misreads this condensed typeface's figures often enough ('141' as '144', '100' as '406') that the numbers are
#also read straight from the scan's pixels: the page is two-tone at 300 dpi and every figure is printed the same, so
#each figure (a run of inked pixel columns in the row) is matched against figures whose value is known. the RANK column
#supplies those: its values are the places, which count up by one down the column
GLYPH_W, GLYPH_H = 16, 22
#where each number sits, as offsets from the left edge of the FINAL TIME column (straightened page pixels)
NUMBER_BANDS = {'rank': (-135, -10), 'time': (-20, 72), 'bib': (55, 158), 'crank': (860, 945), 'pace': (955, 1032)}


@functools.lru_cache(maxsize=4)
def scan(page):
    from PIL import Image
    return np.array(Image.open(os.path.join(PAGE_DIR, str(YEAR), '{:03d}.png'.format(page)))) < 128


def original_xy(page, x, y):
    t = math.radians(SKEW[page])
    dx, dy = x - WIDTH / 2, y - HEIGHT / 2
    return WIDTH / 2 + dx * math.cos(t) - dy * math.sin(t), HEIGHT / 2 + dx * math.sin(t) + dy * math.cos(t)


def band(page, x0, x1, y, half=20):
    #the straightened strip x0..x1 around height y, cut from the scan as it is (no resampling), each pixel column moved
    #up or down for the page's tilt
    a = scan(page)
    t = math.radians(SKEW[page])
    xc, yc = original_xy(page, (x0 + x1) / 2, y)
    xs = np.arange(int(round(xc - (x1 - x0) / 2)), int(round(xc + (x1 - x0) / 2)))
    xs = xs[(xs >= 0) & (xs < a.shape[1])]
    ys = np.round(yc + (xs - xc) * math.tan(t)).astype(int)[None, :] + np.arange(-half, half + 1)[:, None]
    ok = (ys >= 0) & (ys < a.shape[0])
    return np.where(ok, a[np.clip(ys, 0, a.shape[0] - 1), xs[None, :]], False)


def figures(b, gap=6):
    #the figures of the right-most number in a band: the line of text nearest the band's middle (rules that run the
    #band's height left out), split into runs of inked pixel columns; specks under 11 pixels high are dropped, and only
    #the runs no more than gap pixels apart, counting from the right, are kept
    rule = b.mean(axis=0) > 0.8
    ink = b[:, ~rule].any(axis=1)
    runs = [(m.start(), m.end()) for m in re.finditer('1+', ''.join('1' if v else '0' for v in ink))]
    if not runs:
        return []
    mid = b.shape[0] // 2
    r0, r1 = min(runs, key=lambda r: 0 if r[0] <= mid < r[1] else min(abs(r[0] - mid), abs(r[1] - 1 - mid)))
    sub = b[r0:r1].copy()
    sub[:, rule] = False
    out = []
    for m in re.finditer('1+', ''.join('1' if v else '0' for v in sub.any(axis=0))):
        g = sub[:, m.start():m.end()]
        rows = np.where(g.any(axis=1))[0]
        g = g[rows[0]:rows[-1] + 1]
        if g.shape[0] >= 11:
            out.append((m.start(), m.end(), g))
    if not out:
        return []
    keep = [out[-1]]
    for g in reversed(out[:-1]):
        if keep[0][0] - g[1] > gap:
            break
        keep.insert(0, g)
    return [g for _, _, g in keep]


def glyph_vector(g):
    #a figure centred on a blank canvas and blurred a little, so a pixel's shift costs less
    h, w = g.shape
    if h > GLYPH_H or w > GLYPH_W:
        return None
    c = np.zeros((GLYPH_H, GLYPH_W))
    c[(GLYPH_H - h) // 2:(GLYPH_H - h) // 2 + h, (GLYPH_W - w) // 2:(GLYPH_W - w) // 2 + w] = g
    p = np.pad(c, 1)
    return ((p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] + 2 * p[1:-1, 1:-1]) / 6).ravel()


class FigureReader:
    #nearest known figure: the same number of known figures of each value (picked at random, the same each run) and,
    #for each value, the distance to its nearest one. a figure's margin is how much nearer its value's nearest figure is
    #than any other value's. a run too wide for one figure is two (or more) figures touching, split where both parts
    #are surest
    PER_VALUE = 250

    def __init__(self, vectors, labels):
        vectors, labels = np.array(vectors), np.array(labels)
        rng = np.random.default_rng(0)
        self.values = sorted(set(labels))
        n = min(self.PER_VALUE, min((labels == v).sum() for v in self.values))
        self.X = np.concatenate([vectors[rng.choice(np.where(labels == v)[0], n, replace=False)] for v in self.values])
        self.n = n
        self.n2 = (self.X ** 2).sum(axis=1)

    def nearest(self, vs):
        #(value, margin) for each vector
        vs = np.array(vs)
        d = self.n2[None, :] - 2 * vs @ self.X.T + (vs ** 2).sum(axis=1)[:, None]
        per = d.reshape(len(vs), len(self.values), self.n).min(axis=2)
        order = np.argsort(per, axis=1)
        best = per[np.arange(len(vs)), order[:, 0]]
        second = per[np.arange(len(vs)), order[:, 1]]
        return [(self.values[o], float((s - b) / (s + 1e-9))) for o, b, s in zip(order[:, 0], best, second)]

    def read(self, g):
        #(text, the least sure figure's margin) for one run of inked columns. a colon is two dots, one above the other
        if g.shape[1] <= 4 and not g.any(axis=1).all():
            return ':', 1.0
        if g.shape[1] <= 12:
            v = glyph_vector(g)
            return self.nearest([v])[0] if v is not None else ('?', 0.0)
        best = ('?', 0.0)
        for cut in range(5, g.shape[1] - 4):
            parts = [g[:, :cut], g[:, cut:]]
            parts = [p[:, p.any(axis=0)] for p in parts]
            if any(p.shape[1] == 0 for p in parts):
                continue
            reads = [self.read(trim(p)) for p in parts]
            text, margin = ''.join(r[0] for r in reads), min(r[1] for r in reads)
            if margin > best[1]:
                best = (text, margin)
        return best

    def number(self, figs):
        reads = [self.read(g) for g in figs]
        return ''.join(r[0] for r in reads), min([r[1] for r in reads] or [0.0])


def trim(g):
    rows = np.where(g.any(axis=1))[0]
    return g[rows[0]:rows[-1] + 1] if len(rows) else g


def figure_reader(rows):
    #the reader, from the RANK column of rows with a place, page, y and edge
    vectors, labels = [], []
    for page, edge, y, place in zip(rows['page'], rows['edge'], rows['y'], rows['place']):
        s = str(int(place))
        figs = figures(band(page, edge + NUMBER_BANDS['rank'][0], edge + NUMBER_BANDS['rank'][1], y))
        if len(figs) == len(s):
            for ch, g in zip(s, figs):
                v = glyph_vector(g)
                if v is not None:
                    vectors.append(v)
                    labels.append(ch)
    return FigureReader(vectors, labels)


def read_number(reader, page, edge, y, field, o0=None, o1=None, gap=6):
    o0 = NUMBER_BANDS[field][0] if o0 is None else o0
    o1 = NUMBER_BANDS[field][1] if o1 is None else o1
    return reader.number(figures(band(page, edge + o0, edge + o1, y), gap))


#a reading from the scan is put first when its least sure figure has at least this margin
SURE = 0.3


def read_figures(df):
    #each row's time, bib, class rank and pace read from the scan's figures. a sure reading goes first among the OCR
    #readings' alternatives (and is the bib); an unsure one is kept only as the last alternative
    reader = figure_reader(df)
    df = df.copy()
    cols = {c: [] for c in ['time_alts', 'time_raws', 'bib', 'bib_alts', 'bib_margin', 'class_ranks', 'paces']}
    for _, r in df.iterrows():
        page, edge, y = r['page'], r['edge'], r['y']
        text, m = read_number(reader, page, edge, y, 'time')
        t = read_time(text) if re.fullmatch(r'\d:\d\d:\d\d', text) else ''
        alts = [a for a in r['time_alts'] if a != t]
        cols['time_alts'].append(([t] + alts if m >= SURE else alts + [t]) if t else alts)
        cols['time_raws'].append(list(r['time_raws']) + ([text] if t else []))
        text, m = read_number(reader, page, edge, y, 'bib')
        alts = [a for a in r['bib_alts'] if a != text]
        if text.isdigit() and (m >= SURE or text in r['bib_alts']):
            cols['bib'].append(text)
            cols['bib_alts'].append([text] + alts)
            cols['bib_margin'].append(m)
        else:
            cols['bib'].append(r['bib'])
            cols['bib_alts'].append(list(r['bib_alts']))
            cols['bib_margin'].append(0.0)
        #the class rank: between where OCR found it and the 25% mark after it
        right = min(945, r['y_left'] - 3) if np.isfinite(r['y_left']) else 945
        if np.isfinite(r['crank_l']):
            o0, o1 = r['crank_l'] - 6, min(right, r['crank_r'] + 6)
        else:
            o0, o1 = 860, right
        text, m = read_number(reader, page, edge, y, 'crank', o0, o1)
        alts = [a for a in r['class_ranks'] if a != text]
        ok = text.isdigit() and len(text) <= 3
        cols['class_ranks'].append(([text] + alts if m >= SURE else alts + [text]) if ok else alts)
        #the pace, min.sec: the point is too small to be a figure, so the gap it leaves is allowed
        text, m = read_number(reader, page, edge, y, 'pace', gap=13)
        p = int(text[0]) * 60 + int(text[1:]) if re.fullmatch(r'\d\d\d', text) and int(text[1:]) < 60 else np.nan
        alts = [a for a in r['paces'] if a != p]
        cols['paces'].append(([p] + alts if m >= SURE else alts + [p]) if np.isfinite(p) else alts)
    for c, v in cols.items():
        df[c] = v
    return df


#---------------------------------------------------------------- words measured on the scan

#the same scan settles what OCR of the words leaves open. a space is a gap of 5 or more blank pixel columns (letters are
#1 to 4 apart), so the scan says how many words a name or town has and how wide each is. each capital's width (with the
#gap after it) was fitted on rows whose OCR words matched the scan's, to about a pixel a word, so a reading split in
#the wrong place, or one with a letter too many or too few, doesn't fit
LETTER_W = {'A': 11.9, 'B': 11.2, 'C': 11.6, 'D': 12.4, 'E': 10.5, 'F': 9.3, 'G': 12.5, 'H': 12.5, 'I': 5.8,
            'J': 9.7, 'K': 11.5, 'L': 10.3, 'M': 15.9, 'N': 12.4, 'O': 12.9, 'P': 11.2, 'Q': 12.0, 'R': 12.5, 'S': 11.5,
            'T': 10.7, 'U': 12.8, 'V': 11.5, 'W': 17.9, 'X': 11.6, 'Y': 11.8, 'Z': 10.7, "'": 0.0, '-': 6.8}
#marks and figures, not fitted
LETTER_W.update({'.': 3.0, '&': 12.0})
WORD_W0 = -2.1
WORD_BANDS = {'name': (150, 452), 'city': (452, 676), 'state': (676, 748)}
#a reading fits the scan when no word is more than this many pixels off
FIT_PX = 3.5


def ink_line(b):
    #the line of text nearest the band's middle, rules that run the band's height blanked
    rule = b.mean(axis=0) > 0.8
    ink = b[:, ~rule].any(axis=1)
    runs = [(m.start(), m.end()) for m in re.finditer('1+', ''.join('1' if v else '0' for v in ink))]
    if not runs:
        return b[:0]
    mid = b.shape[0] // 2
    r0, r1 = min(runs, key=lambda r: 0 if r[0] <= mid < r[1] else min(abs(r[0] - mid), abs(r[1] - 1 - mid)))
    sub = b[r0:r1].copy()
    sub[:, rule] = False
    return sub


def scan_words(page, edge, y, field, space=5):
    #(left, right) of each word in a field, specks (under 8 pixels high) left out
    o0, o1 = WORD_BANDS[field]
    sub = ink_line(band(page, edge + o0, edge + o1, y))
    words = []
    for m in re.finditer('1+', ''.join('1' if v else '0' for v in sub.any(axis=0))):
        if words and m.start() - words[-1][1] < space:
            words[-1] = (words[-1][0], m.end())
        else:
            words.append((m.start(), m.end()))
    tall = lambda w: np.ptp(np.where(sub[:, w[0]:w[1]].any(axis=1))[0]) + 1 >= 8
    return [w for w in words if tall(w)]


def fit_words(text, widths):
    #the text's letters split into as many words as the scan shows: (words, the worst word's misfit in pixels). the
    #split keeps the text's own spaces where it can (each space added or dropped costs a pixel)
    letters = [c for c in text if c != ' ']
    if not widths or not letters or len(letters) < len(widths):
        return text, np.inf
    spaces = set()
    i = 0
    for c in text:
        if c == ' ':
            spaces.add(i)
        else:
            i += 1
    cum = np.concatenate([[0], np.cumsum([LETTER_W.get(c, 11.5) for c in letters])])
    n, k = len(letters), len(widths)
    #best[j][b]: least cost of the first j words, the last ending after letter b
    best = np.full((k + 1, n + 1), np.inf)
    back = np.zeros((k + 1, n + 1), int)
    best[0][0] = 0
    for j in range(1, k + 1):
        for b in range(j, n + 1):
            for a in range(j - 1, b):
                if not np.isfinite(best[j - 1][a]):
                    continue
                miss = abs(cum[b] - cum[a] + WORD_W0 - widths[j - 1])
                cost = best[j - 1][a] + miss + sum(1 for s in spaces if a < s < b) + (a > 0 and a not in spaces)
                if cost < best[j][b]:
                    best[j][b], back[j][b] = cost, a
    cuts, b = [], n
    for j in range(k, 0, -1):
        a = back[j][b]
        cuts.insert(0, (a, b))
        b = a
    worst = max(abs(cum[b] - cum[a] + WORD_W0 - w) for (a, b), w in zip(cuts, widths))
    return ' '.join(''.join(letters[a:b]) for a, b in cuts), worst


def best_fit(alts, widths, rank):
    #of the readings, split to fit the scan, the best ranked of those that fit; failing that, the one that fits best
    fitted = [fit_words(a, widths) for a in alts]
    ok = [(t, e) for t, e in fitted if e <= FIT_PX]
    if ok:
        return max(ok, key=lambda te: rank(te[0]))[0], True
    if fitted and np.isfinite(min(e for _, e in fitted)):
        return min(fitted, key=lambda te: te[1])[0], False
    return None, False


def word_vector(g, w=48, h=22):
    hh, ww = g.shape
    if hh > h or ww > w:
        return None
    c = np.zeros((h, w))
    c[(h - hh) // 2:(h - hh) // 2 + hh, (w - ww) // 2:(w - ww) // 2 + ww] = g
    p = np.pad(c, 1)
    return ((p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] + 2 * p[1:-1, 1:-1]) / 6).ravel()


def state_image(page, edge, y):
    #the state as printed, cut to its ink
    o0, o1 = WORD_BANDS['state']
    sub = ink_line(band(page, edge + o0, edge + o1, y))
    words = scan_words(page, edge, y, 'state')
    if len(words) != 1:
        return None
    g = sub[:, words[0][0]:words[0][1]]
    rows = np.where(g.any(axis=1))[0]
    return g[rows[0]:rows[-1] + 1] if len(rows) else None


class WordReader:
    #nearest known word image, as FigureReader, with up to PER_VALUE examples of each value
    PER_VALUE = 120

    def __init__(self, vectors, labels):
        vectors, labels = np.array(vectors), np.array(labels)
        rng = np.random.default_rng(0)
        self.values = sorted(set(labels))
        idx = [rng.permutation(np.where(labels == v)[0])[:self.PER_VALUE] for v in self.values]
        self.X = np.concatenate([vectors[i] for i in idx])
        self.starts = np.concatenate([[0], np.cumsum([len(i) for i in idx])[:-1]])
        self.n2 = (self.X ** 2).sum(axis=1)

    def nearest(self, v, allowed=None):
        #(value, margin), the value one of those allowed (all, by default); the only one allowed is sure
        allowed = [k for k, x in enumerate(self.values) if allowed is None or x in allowed]
        if v is None or not allowed:
            return '', 0.0
        if len(allowed) == 1:
            return self.values[allowed[0]], 1.0
        d = self.n2 - 2 * self.X @ v + v @ v
        per = np.minimum.reduceat(d, self.starts)[allowed]
        order = np.argsort(per)
        return self.values[allowed[order[0]]], float((per[order[1]] - per[order[0]]) / (per[order[1]] + 1e-9))


def read_names(df):
    #each name split to fit the scan's words. OCR now and then drops an initial ('DALE THOMPSON' for 'DALE B THOMPSON');
    #when no reading fits, a reading that fits all but one narrow word of the scan gets that initial, read from the scan
    #against the initials of names that fit
    names, words, fits = [], [], []
    for _, r in df.iterrows():
        w = scan_words(r['page'], r['edge'], r['y'], 'name')
        #a speck well away from the name isn't a word
        while len(w) > 1 and w[-1][1] - w[-1][0] < 6 and w[-1][0] - w[-2][1] > 12:
            w = w[:-1]
        while len(w) > 1 and w[0][1] - w[0][0] < 6 and w[1][0] - w[0][1] > 12:
            w = w[1:]
        widths = [b - a for a, b in w]
        alts = list(r['name_alts'])
        votes = {compact(a): sum(compact(b) == compact(a) for b in alts) for a in alts}
        rank = lambda n: (name_score(n), votes.get(compact(n), 0), -alts.index(n) if n in alts else -99)
        name, fit = best_fit(alts, widths, rank)
        names.append(name if fit else r['name'])
        words.append(w)
        fits.append(fit)
    #the initials of the names that fit. OCR takes D and O for each other, and they are as wide: the scan tells them
    #apart by the D's upright left side
    vectors, labels, undecided = [], [], []
    for i, ((_, r), name, w, fit) in enumerate(zip(df.iterrows(), names, words, fits)):
        if fit:
            tokens = name.split()
            for j, (token, (a, b)) in enumerate(zip(tokens, w)):
                if len(token) == 1:
                    g = letter_glyph(r, a, b)
                    if g is None:
                        continue
                    if token in 'DO':
                        tokens[j] = d_or_o(g) or token
                        if not d_or_o(g):
                            #neither: OCR's D or O is some other letter ('TOM D DAILEY' for 'TOM J DAILEY')
                            undecided.append((i, j, g, b - a))
                            continue
                    vectors.append(word_vector(g, 22, 22))
                    labels.append(tokens[j])
            names[i] = ' '.join(tokens)
    reader = WordReader(vectors, labels)
    for i, j, g, width in undecided:
        allowed = [c for c in reader.values if c not in 'DO' and abs(LETTER_W.get(c, 99) + WORD_W0 - width) <= 2.5]
        letter, margin = reader.nearest(word_vector(g, 22, 22), allowed)
        if margin >= SURE:
            tokens = names[i].split()
            names[i] = ' '.join(tokens[:j] + [letter] + tokens[j + 1:])
    for i, ((_, r), w, fit) in enumerate(zip(df.iterrows(), words, fits)):
        if fit or not w:
            continue
        widths = [b - a for a, b in w]
        found = []
        for alt in r['name_alts']:
            tokens = alt.split()
            #a letter I OCR left off the end of a word ('SANTOSK' for 'SANTOSKI'): the scan's word ends in a bar
            if len(tokens) == len(w):
                for j, (a, b) in enumerate(w):
                    if ends_in_bar(r, a, b):
                        longer = ' '.join(tokens[:j] + [tokens[j] + 'I'] + tokens[j + 1:])
                        if fit_words(longer, widths)[1] <= FIT_PX:
                            found.append(fit_words(longer, widths)[0])
            if len(tokens) != len(w) - 1:
                continue
            #not the last word: a narrow word after the last name is more likely a suffix ('II') than an initial
            for j, (a, b) in enumerate(w[:-1]):
                if b - a > 16 or not fit_words(alt, widths[:j] + widths[j + 1:])[1] <= FIT_PX:
                    continue
                #only letters as wide as the word
                allowed = [c for c in reader.values if abs(LETTER_W.get(c, 99) + WORD_W0 - (b - a)) <= 2.5]
                g = letter_glyph(r, a, b)
                letter, margin = reader.nearest(word_vector(g, 22, 22) if g is not None else None, allowed)
                if letter in ('D', 'O'):
                    letter = d_or_o(g) or letter
                if margin >= SURE:
                    fitted = fit_words(alt, widths[:j] + widths[j + 1:])[0].split()
                    found.append(' '.join(fitted[:j] + [letter] + fitted[j:]))
        if found:
            names[i] = found[0]
            fits[i] = True
    names = resolve_letters(df, names, words, fits, reader)
    df = df.copy()
    df['name'], df['name_fits'] = names, fits
    return df


def letter_crops(sub, a, b, word):
    #each letter of a word the scan shows at a..b, cut where the letter widths put it
    cum = np.concatenate([[0], np.cumsum([LETTER_W.get(c, 11.5) for c in word])])
    s = (b - a) / (cum[-1] + WORD_W0)
    out = []
    for i in range(len(word)):
        g = sub[:, max(0, int(round(a + cum[i] * s)) - 1):int(round(a + (cum[i + 1] + WORD_W0) * s)) + 1]
        rows = np.where(g.any(axis=1))[0]
        out.append(word_vector(g[rows[0]:rows[-1] + 1], 24, 22) if len(rows) else None)
    return out


def resolve_letters(df, names, words, fits, initials):
    #where the readings of a word are as long but differ in letters ('SCHLAKT', 'SCHLAHT'), each letter in doubt is
    #the one whose look in the scan is nearest: letters cut from names the readings all agree on and that are known
    #from other years (initials, from the initials reader). a known name among the readings is kept over a mix that
    #isn't known
    first, last = known_names()
    lines = {}
    def line(r):
        o0, o1 = WORD_BANDS['name']
        return ink_line(band(r['page'], r['edge'] + o0, r['edge'] + o1, r['y']))
    samples = {}
    for (_, r), name, w, fit in zip(df.iterrows(), names, words, fits):
        tokens = name.split()
        if (not fit or len(set(compact(a) for a in r['name_alts'])) != 1 or len(tokens) < 2 or
                compact(tokens[0]) not in first or compact(tokens[-1]) not in last or len(tokens) != len(w)):
            continue
        sub = line(r)
        for t, (a, b) in zip(tokens, w):
            if len(t) < 2:
                continue
            for c, v in zip(t, letter_crops(sub, a, b, t)):
                if v is not None and len(samples.setdefault(c, [])) < 300:
                    samples[c].append(v)
    X = {c: np.array(v) for c, v in samples.items()}
    out = list(names)
    for i, ((_, r), name, w) in enumerate(zip(df.iterrows(), names, words)):
        tokens = name.split()
        if len(set(compact(a) for a in r['name_alts'])) < 2 or len(tokens) != len(w):
            continue
        widths = [b - a for a, b in w]
        readings = [fit_words(a, widths)[0].split() for a in r['name_alts']]
        sub = None
        for j, (a, b) in enumerate(w):
            cands = list(dict.fromkeys([tokens[j]] + [t[j] for t in readings if len(t) == len(w) and
                                                      len(t[j]) == len(tokens[j]) and
                                                      fit_words(t[j], [b - a])[1] <= FIT_PX]))
            if len(cands) < 2:
                continue
            sub = line(r) if sub is None else sub
            if len(tokens[j]) == 1:
                g = sub[:, a:b]
                rows = np.where(g.any(axis=1))[0]
                v = word_vector(g[rows[0]:rows[-1] + 1], 22, 22) if len(rows) else None
                letter, margin = initials.nearest(v, cands)
                if margin >= SURE:
                    tokens[j] = letter
                continue
            crops = letter_crops(sub, a, b, tokens[j])
            word = ''
            for k, v in enumerate(crops):
                letters = list(dict.fromkeys(c[k] for c in cands))
                ok = [c for c in letters if c in X]
                if len(letters) == 1 or v is None or len(ok) < len(letters):
                    word += tokens[j][k]
                    continue
                word += min(ok, key=lambda c: ((X[c] - v) ** 2).sum(axis=1).min())
            book = first if j == 0 else last if j == len(w) - 1 else {}
            if book and compact(word) not in book and any(compact(c) in book for c in cands):
                word = next(c for c in cands if compact(c) in book)
            tokens[j] = word
        out[i] = ' '.join(tokens)
    return recheck_letters(df, out, words, fits, X)


#wide letters OCR takes for each other ('TOOD', 'MABDOCK', 'BOKRER'); narrow ones (I, J, L, T) are cut from the scan
#too roughly to judge
WIDE = set('BCDEFGHKOPRSQ')
#how much nearer the other letter's look has to be
RECHECK = 0.45


def recheck_letters(df, names, words, fits, X):
    #every wide letter of a name that fits the scan, even one all the readings agree on, is checked against the letters
    #OCR confuses it with; it is changed only when the other letter's look in the scan is much nearer (no letter of the
    #names whose readings agree and are known was changed this way). a Q before a U stays
    partners = {}
    for pair in CONFUSED:
        a, b = sorted(pair)
        if a in WIDE and b in WIDE and a in X and b in X:
            partners.setdefault(a, []).append(b)
            partners.setdefault(b, []).append(a)
    out = list(names)
    for i, ((_, r), name, w, fit) in enumerate(zip(df.iterrows(), names, words, fits)):
        tokens = name.split()
        if not fit or len(tokens) != len(w) or not any(c in partners for c in name):
            continue
        o0, o1 = WORD_BANDS['name']
        sub = ink_line(band(r['page'], r['edge'] + o0, r['edge'] + o1, r['y']))
        for j, (a, b) in enumerate(w):
            t = tokens[j]
            if len(t) < 2 or not any(c in partners for c in t):
                continue
            crops = letter_crops(sub, a, b, t)
            word = list(t)
            for k, (c, v) in enumerate(zip(t, crops)):
                if c not in partners or v is None or (c == 'Q' and t[k + 1:k + 2] == 'U'):
                    continue
                d0 = ((X[c] - v) ** 2).sum(axis=1).min()
                near = [(((X[o] - v) ** 2).sum(axis=1).min(), o) for o in partners[c]]
                d, o = min(near)
                if (d0 - d) / (d0 + 1e-9) >= RECHECK:
                    word[k] = o
            tokens[j] = ''.join(word)
        out[i] = ' '.join(tokens)
    return out


def ends_in_bar(r, a, b):
    #the scan's word a..b ends in a letter I: a lone upright bar, 4 pixels wide at most and as tall as the letters
    o0, o1 = WORD_BANDS['name']
    sub = ink_line(band(r['page'], r['edge'] + o0, r['edge'] + o1, r['y']))[:, a:b]
    runs = [(m.start(), m.end()) for m in re.finditer('1+', ''.join('1' if v else '0' for v in sub.any(axis=0)))]
    if len(runs) < 2 or runs[-1][1] - runs[-1][0] > 4:
        return False
    bar = sub[:, runs[-1][0]:runs[-1][1]].any(axis=1)
    return bar.sum() >= 0.8 * sub.shape[0]


def letter_glyph(r, a, b):
    #the scan's word a..b of the name, cut to its ink
    o0, o1 = WORD_BANDS['name']
    sub = ink_line(band(r['page'], r['edge'] + o0, r['edge'] + o1, r['y']))[:, a:b]
    rows = np.where(sub.any(axis=1))[0]
    return sub[rows[0]:rows[-1] + 1] if len(rows) else None


def d_or_o(g):
    #a D's left side is an upright inked from top to bottom, with a square corner at the top; an O's is a curve
    fill = max(g[:, c].mean() for c in range(min(4, g.shape[1])))
    if fill >= 0.94 or (fill >= 0.8 and g[:2, :1].any()):
        return 'D'
    return 'O' if fill >= 0.6 else None


@functools.lru_cache(maxsize=None)
def town_names():
    #{state: {town, letters only: (the town as written, how many results give it)}} from the clean results
    clean = load_all_results()
    clean = clean[(clean['year'] != YEAR) & (clean['city'] != '')]
    out = {}
    for (city, state), n in clean.groupby(['city', 'state']).size().items():
        k = compact(city)
        if n > out.setdefault(state, {}).get(k, ('', 0))[1]:
            out[state][k] = (city.upper(), n)
    return out


@functools.lru_cache(maxsize=None)
def towns_as_written():
    clean = load_all_results()
    return frozenset(zip(clean.loc[clean['year'] != YEAR, 'city'], clean.loc[clean['year'] != YEAR, 'state']))


#letters OCR takes for each other in this typeface; swapping one for the other costs half an edit
CONFUSED = [set(p) for p in ['BD', 'CG', 'CO', 'GO', 'DO', 'OQ', 'IL', 'IT', 'IJ', 'LT', 'NM', 'NH', 'HK', 'EF', 'UV',
                              'RB', 'RP', 'BE', 'SB']]


def edits(a, b):
    #edits from a to b: a letter added, dropped, changed or two swapped cost one, a change to a letter OCR confuses
    #with it a half
    d = [[0.0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            sub = 0 if a[i - 1] == b[j - 1] else 0.5 if {a[i - 1], b[j - 1]} in CONFUSED else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + sub)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def town_spelling(city, state, widths):
    #a town known in that state, spaced as it is known ('DULUT H', 'LAKEOSWEGO'); else the one town of
    #that state, given by at least five results, that is one edit off (one and a half, for a long name: 'MENGMONEE
    #FALLS', 'FOND OUD LAC') and fits the scan's words as well
    known = town_names().get(state, {})
    k = compact(city)
    if not k or not re.fullmatch(r"[A-Z' .-]+", city):
        return city
    if k in known:
        #spaced as the clean results have it, unless they have it as it is ('LACROSSE')
        name = known[k][0]
        as_is = (normalize_location(city, state, '')[0], state) in towns_as_written()
        if as_is or not re.fullmatch(r"[A-Z' -]+", name):
            return city
        return name
    limit = 1 if len(k) < 8 else 1.5
    near = [(edits(k, t), name) for t, (name, n) in known.items() if n >= 5 and abs(len(t) - len(k)) <= 2]
    near = [(d, name) for d, name in near if d <= limit]
    if not near:
        return city
    best = min(d for d, _ in near)
    near = [name for d, name in near if d == best]
    if len(near) == 1 and re.fullmatch(r"[A-Z' -]+", near[0]) and fit_words(near[0], widths)[1] <= FIT_PX:
        return near[0]
    return city


def nation(country, state):
    #a nation no reading gave as printed, when one letter OCR confuses makes it one ('JSA', 'SUL'); 'NET' and 'UK' are
    #as printed
    if country in NATIONS or not country:
        return country
    near = [n for n in NATIONS if len(n) == len(country) and
            sum(a != b for a, b in zip(n, country)) == 1 and
            all(a == b or {a, b} in CONFUSED + [set('JU')] for a, b in zip(n, country))]
    return near[0] if len(near) == 1 else country


def lookalike(a, b):
    #two state codes OCR could take for each other: one letter different, dropped or added
    if a == b:
        return True
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long = sorted([a, b], key=len)
    return len(long) == len(short) + 1 and any(long[:i] + long[i + 1:] == short for i in range(len(long)))


def read_words(df):
    #names and towns split and chosen to fit the scan's words; states read from the scan against states whose reading
    #is sure (the readings agree and the town is known in that state)
    towns = known_towns()
    df = df.copy()
    vectors, labels, images = [], [], []
    for _, r in df.iterrows():
        g = state_image(r['page'], r['edge'], r['y'])
        v = word_vector(g) if g is not None else None
        images.append(v)
        sure = (r['state_n'] >= 2 and r['state'] in STATES and
                (compact(r['city']), r['state']) in towns)
        if v is not None and sure:
            vectors.append(v)
            labels.append(r['state'])
    reader = WordReader(vectors, labels)
    cities, states = [], []
    countries = []
    for (_, r), v in zip(df.iterrows(), images):
        country = nation(r['country'], r['state'])
        countries.append(country)
        if country in ('USA', 'CAN', ''):
            state, margin = reader.nearest(v)
            if margin < SURE or state not in STATES:
                state = r['state']
        else:
            #a region abroad ('VIC', 'BE'), as most readings have it
            read = list(r['states_read'])
            state = max(read, key=read.count) if read else ''
        words = scan_words(r['page'], r['edge'], r['y'], 'city')
        #a speck well after the town isn't a word
        while len(words) > 1 and words[-1][1] - words[-1][0] < 10 and words[-1][0] - words[-2][1] > 25:
            words = words[:-1]
        widths = [b - a for a, b in words]
        city_alts = [a for a in r['city_alts'] if a]
        #'WASHINGTON DC' is printed in the town column, with no state
        if state not in STATES and any(re.fullmatch(r'WASHINGTON\W*D\W*C', c) for c in city_alts):
            state = 'DC'
            city_alts, widths = ['WASHINGTON'], widths[:1]
        #a 1 in a word of letters is an I ('1OWA CITY')
        city_alts = list(dict.fromkeys(re.sub(r'(?<=[A-Z])1|1(?=[A-Z])', 'I', c) for c in city_alts))
        #'ST. PAUL': the point after a short word, which the readings leave out, counts in its width
        dotted = {re.sub(r'\b([A-Z]{1,2}) ', r'\1. ', c): c for c in city_alts}
        rank = lambda c: ((compact(c), state) in towns, -city_alts.index(dotted.get(c, c)) if dotted.get(c, c) in
                          city_alts else -99)
        city, _ = best_fit(city_alts + [d for d in dotted if d not in city_alts], widths, rank)
        city = dotted.get(city, city.replace('.', '') if city and city.replace('.', '') in city_alts else city)
        if city is None:
            city = city_alts[0] if city_alts else ''
        #a state OCR misread, when the town is known in just one state that looks like what OCR read
        if compact(city) and (compact(city), state) not in towns:
            homes = set(s for c, s in towns if c == compact(city))
            near = [s for s in homes if any(lookalike(s, a) for a in [state] + list(r['state_alts']) if a)]
            if len(near) == 1:
                state = near[0]
        city = town_spelling(city, state, widths)
        cities.append(re.sub(r'(?<=[A-Z])\.(?=[A-Z])', ' ', city))
        states.append(state)
    df['city'], df['state'], df['country'] = cities, states, countries
    return read_names(df)


#---------------------------------------------------------------- classes

def repair_classes(lst, gender):
    #the class from the CLASS column (the list says the gender). a class OCR couldn't read is the one class whose ranks
    #so far run up to one below this row's class rank. a class rank is the reading that follows on from the one before
    #it in the class; one that doesn't is repaired only when the ranks before and after it in the class are two apart
    lst = lst.copy()
    groups = [c[1] if c and c[1] else '' for c in lst['cls']]
    alts = [[int(r) for r in rs if r.isdigit()] for rs in lst['class_ranks']]
    ranks = [a[0] if a else None for a in alts]
    last = {}
    for i in range(len(lst)):
        if not groups[i] and ranks[i] is not None:
            fits = [g for g, k in last.items() if k + 1 in alts[i]]
            if len(fits) == 1:
                groups[i] = fits[0]
                ranks[i] = last[fits[0]] + 1
        if groups[i]:
            if last.get(groups[i], 0) + 1 in alts[i]:
                ranks[i] = last.get(groups[i], 0) + 1
            if ranks[i] is not None:
                last[groups[i]] = ranks[i]
    for i in range(len(lst)):
        if not groups[i]:
            continue
        before = next((j for j in range(i - 1, -1, -1) if groups[j] == groups[i]), None)
        after = next((j for j in range(i + 1, len(lst)) if groups[j] == groups[i]), None)
        k0 = ranks[before] if before is not None else 0
        k1 = ranks[after] if after is not None else None
        if k0 is not None and k1 == k0 + 2 and ranks[i] != k0 + 1:
            ranks[i] = k0 + 1
    lst['age_group'] = ['{} {}'.format(gender, g) if g else '' for g in groups]
    lst['class_rank'] = ['' if r is None else str(r) for r in ranks]
    return lst


#---------------------------------------------------------------- times

#digits OCR mixes up in this typeface
LOOKALIKE = {'0': '896', '1': '74', '2': '7', '3': '859', '4': '1', '5': '638', '6': '580', '7': '12', '8': '3605',
             '9': '034'}


def seconds(t):
    return parse_seconds(t) if t else np.nan


def hms(s):
    s = int(round(s))
    return '{}:{:02d}:{:02d}'.format(s // 3600, s % 3600 // 60, s % 60)


def pace_fits(s, pace):
    #PACE MN/KM is the time over 52 km, cut to whole seconds
    return not np.isfinite(pace) or int(s // DISTANCE_KM) == pace


def longest_rising(values):
    #which of the values (nan for none) are in the longest run, in order, that never goes down
    tails, prev = [], {}
    for i, v in enumerate(values):
        if not np.isfinite(v):
            continue
        k = bisect.bisect_right([values[j] for j in tails], v)
        prev[i] = tails[k - 1] if k else None
        if k == len(tails):
            tails.append(i)
        else:
            tails[k] = i
    keep = set()
    j = tails[-1] if tails else None
    while j is not None:
        keep.add(j)
        j = prev[j]
    return np.array([i in keep for i in range(len(values))])


def repair_times(lst):
    #each row's time is the reading that fits its pace (a pace out of order with the paces around it is ignored). a time
    #that doesn't fit, or isn't in order with the times around it, is repaired when exactly one reading fits between
    #them and its pace: another reading's time, else one digit swapped for a lookalike, else any one digit. a time
    #between two equal times is that time. a time that can't be pinned down is left blank
    lst = lst.copy()
    n = len(lst)
    times = list(lst['time_alts'])
    paces = []
    for alts, ps in zip(times, lst['paces']):
        fit = [p for p in ps if any(pace_fits(seconds(t), p) for t in alts)]
        paces.append((fit or ps or [np.nan])[0])
    paces = np.array(paces, dtype=float)
    paces[~longest_rising(paces) & np.isfinite(paces)] = np.nan
    secs = np.full(n, np.nan)
    ok = np.zeros(n, bool)
    for i, alts in enumerate(times):
        fit = [t for t in alts if pace_fits(seconds(t), paces[i])]
        if fit:
            secs[i], ok[i] = seconds(fit[0]), True
        elif alts:
            secs[i] = seconds(alts[0])
    good = longest_rising(np.where(ok, secs, np.nan))
    out, how = [''] * n, [''] * n
    for i in range(n):
        if good[i]:
            out[i] = hms(secs[i])
            continue
        lo = max([secs[j] for j in range(i) if good[j]] or [0])
        hi = min([secs[j] for j in range(i + 1, n) if good[j]] or [np.inf])
        fits = lambda t: bool(t) and lo <= seconds(t) <= hi and pace_fits(seconds(t), paces[i])
        found = None
        tiers = [set(t for t in times[i] if fits(t))]
        bases = set()
        for raw in lst['time_raws'].iloc[i]:
            d = ''.join(re.findall(r'\d', str(raw).translate(DIGITS)))
            bases |= {d[-5:], d[:5]} if len(d) > 5 else {d} if len(d) == 5 else set()
        tiers.append(set(t for b in bases for j, c in enumerate(b) for r in LOOKALIKE.get(c, '')
                         for t in [read_time(b[:j] + r + b[j + 1:])] if fits(t)))
        tiers.append(set(t for b in bases for j in range(5) for r in '0123456789'
                         for t in [read_time(b[:j] + r + b[j + 1:])] if fits(t)))
        for tier in tiers:
            if len(tier) == 1:
                found = tier.pop()
                break
            if tier:
                break
        if found is None and lo == hi:
            found = hms(lo)
        if found is None and np.isfinite(secs[i]) and lo <= secs[i] <= hi:
            #in order, but not at its pace: the pace is more likely misread
            found = hms(secs[i])
        out[i] = found or ''
        how[i] = 'repaired' if found else 'blank'
    lst['time'] = out
    lst['time_fix'] = how
    return lst
