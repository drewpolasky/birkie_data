#1994 birch scroll: "MEN'S DYNO AMERICAN BIRKEBEINER RESULTS" on pages 35-51 (places 1-3547) and "WOMEN'S ..." on pages
#52-54 (places 1-543). the kortelopet follows on 55-63 ("... HERITAGE BANK OF HAYWARD KORTELOPET RESULTS") and the class
#award lists (top three in each class) are on pages 6-7; both are left out. each results page has two columns of 110
#results (the last page of each list fewer), one result to a column's line:
#   RANK, FINAL TIME (h:mm:ss.t), BIB, NAME, HOMETOWN, ST, NAT, CLASS ("M40-44", "M70+"), CLASS RANK, 25% club ("Y"),
#   PACE MN/KM (the time over 52 km in min.sec, cut to the second: 2:51:44.6 -> 3.18)
#places run per gender, one list for each; classic and skate skiers are listed together with no technique marked, so
#tech is left blank
#
#each column's rows are numbered by where they sit (the rows are evenly spaced, so a row's place follows from its height
#once the readable ranks fix the spacing), which keeps a row whose rank OCR lost and merges a row tesseract split in two.
#each column is read by four OCRs: birkie_archive's two of the whole page (NNN.tsv, NNN_x2.tsv) and this year's own of
#each column cropped, turned level and read at three and four times the size with a character whitelist
#(NNN_c<column>d3.tsv, NNN_c<column>d4.tsv, made by column_ocr when missing, boxes in page pixels). each field takes the
#reading with the most weight (WEIGHTS), preferring readings that make sense: a time that fits its pace, a valid bib, a
#known first and last name, a known town in its state, a valid NAT code. names read with a lost space ('PAULAL
#KASTENSON') get it back when the page shows a word gap there and the split makes the name known. then the tables' own
#constraints repair what is pinned down:
#   times rise with place: the heaviest rising run of times is kept, and a time out of order gets the one reading, or
#       reading with one digit misread, that fits between its kept neighbours and its pace; with none or several it is
#       left blank
#   class ranks count up within each class: a class or class rank OCR lost or misread is the one that fits between the
#       ranks before and after it in that class
#   bibs are not shared: of two rows reading one bib, the one reading it with less weight takes its next reading
import bisect
import collections
import concurrent.futures
import functools
import glob
import os
import re
import subprocess

import numpy as np
import pandas as pd
from PIL import Image

from birkie_archive import (OCR_DIR, PAGE_DIR, TESSERACT, RESULT_CHARACTERS, ocr_words, digits, read_time, TIME_LIKE,
                            parse_seconds)
from results_loader import load_all_results, compact, split_first_last, US_STATES, CA_PROVINCES

#each field's left edge, in page pixels, from the left of the FINAL TIME column
FIELDS = [('rank', -100), ('time', -12), ('bib', 75), ('name', 150), ('town', 452), ('st', 670), ('nat', 733),
          ('cls', 798), ('crank', 866), ('club', 930), ('pace', 962), ('end', 1045)]
#a time as printed: 2:16:52.6
STRICT_TIME = re.compile(r'\d[:;.,]\d\d[:;.,]\d\d[.,]\d')
CLASSES = ['18-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', '65-69', '70+']
KM = 52
#the OCRs read, in the order their readings win ties
SOURCES = ['x2', 'd3', 'x1', 'd4']
#the tables' province codes
PROVINCES = {'ONT': 'ON', 'QUE': 'QC', 'MAN': 'MB', 'SAS': 'SK', 'ALB': 'AB'}
#the last places printed: page 51's 3547 for the men, page 54's 543 for the women
LAST_PLACE = {'M': 3547, 'F': 543}


def parse(year, names=None, pages=None, raw=False):
    names = names or SOURCES
    pages = [(p, g) for p, g in results_pages(year) if not pages or p in pages]
    column_ocr(year, [p for p, _ in pages])
    records, start = [], {}
    for page, gender in pages:
        words = pd.concat([w.assign(source=source) for source, w in sources(year, page, names)], ignore_index=True)
        recs, start[gender] = page_records(page, words, start.get(gender, 1))
        records += [{**r, 'gender': gender} for r in recs]
    rows = merge(pd.DataFrame(records), names)
    rows = pd.concat([repair_classes(choose_times(lst)) for _, lst in rows.groupby('gender', sort=False)],
                     ignore_index=True)
    return rows if raw else finish(rows)


#---------------------------------------------------------------- pages and words

def results_pages(year):
    #(page, gender) for each birkebeiner results page: a page of times under a RANK ... HOMETOWN header, titled
    #MEN'S/WOMEN'S ... BIRKEBEINER RESULTS (not KORTELOPET). a title OCR garbled carries over from the page before
    out, race, gender = [], None, None
    for path in sorted(glob.glob(os.path.join(OCR_DIR, str(year), '[0-9][0-9][0-9].tsv'))):
        page = int(os.path.basename(path)[:3])
        words = ocr_words(year, page, scaled=False)
        if words.empty:
            continue
        timed = words['text'].str.contains(TIME_LIKE)
        top = words.loc[timed, 'top'].min() if timed.any() else words['top'].max()
        title = ' '.join(words.loc[words['top'] < top, 'text']).upper()
        if 'KORTE' in title:
            race = 'kortie'
        elif 'BIRKE' in title and 'RESULTS' in title:
            race = 'birkie'
        if 'WOMEN' in title:
            gender = 'F'
        elif re.search(r'\bMEN', title):
            gender = 'M'
        if timed.sum() >= 20 and race == 'birkie' and words['text'].str.contains('HOMETOWN').any():
            out.append((page, gender))
        elif timed.sum() < 20:
            race = None
    return out


def sources(year, page, names):
    #each OCR of the page, as words in page pixels: tesseract's own (birkie_archive's, the page as it is and at twice
    #the size) and this year's of each column on its own (old_results/ocr/1994/<page>_c<column><suffix>.tsv)
    out = []
    for name in names:
        if name in ('x2', 'x1'):
            if name == 'x2' and not os.path.exists(os.path.join(OCR_DIR, str(year), '{:03d}_x2.tsv'.format(page))):
                continue
            w = ocr_words(year, page, scaled=name == 'x2')
        else:
            paths = sorted(glob.glob(os.path.join(OCR_DIR, str(year), '{:03d}_c[0-9]{}.tsv'.format(page, name))))
            if not paths:
                continue
            w = pd.concat([pd.read_csv(p, sep='\t', quoting=3, dtype={'text': str}, keep_default_na=False)
                           for p in paths], ignore_index=True)
            w = w[(w['level'] == 5) & (w['text'].str.strip() != '')]
        out.append((name, w.reset_index(drop=True)))
    return out


def time_columns(words):
    #(column, line, times) for each results column: the FINAL TIME column's left edge as a line in y (x = line(y)), for
    #a page that sits a little crooked (up to 60 pixels from top to bottom), and the times in the column. the two columns' lefts
    #are the busiest 40 pixels of time lefts, and the busiest a column's width away; the times near those give the line,
    #and the line gives the rest
    words = words.assign(y=words['top'] + words['height'] / 2) if 'y' not in words else words
    t = words[words['text'].str.contains(STRICT_TIME)]
    if len(t) < 10:
        return []
    count = lambda x: (abs(t['left'] - x) < 20).sum()
    first = max(t['left'], key=count)
    second = max(t['left'], key=lambda x: count(x) if abs(x - first) > 900 else -1)
    modes = sorted({first, second} if abs(second - first) > 900 else {first})
    out = []
    for col, mode in enumerate(modes):
        side = t[abs(t['left'] - mode) < 30]
        if len(side) < 10 * words['source'].nunique():
            continue
        fit = np.polyfit(side['y'], side['left'], 1)
        side = t[abs(t['left'] - np.polyval(fit, t['y'])) < 20]
        fit = np.polyfit(side['y'], side['left'], 1)
        if abs(fit[0]) <= 0.05:
            #the column's rows: the times on the line, and those run on from their rank ('12:36:47.0')
            loose = words[words['text'].str.contains(TIME_LIKE)]
            dx = loose['left'] - np.polyval(fit, loose['y'])
            out.append((col, fit, loose[(dx > -70) & (dx < 20)]))
    return out


def page_records(page, words, start):
    #every result OCR found on the page, from each OCR of it: its column, place and the text under each field. each
    #word goes to the row its height gives it (not to tesseract's line, which can take half of one row and half of the
    #next on a crooked page), and to the field its distance from the FINAL TIME column gives it. start: the place the
    #page's first row should have, following on from the page before, for when OCR misread the ranks' first digits
    words = words[words['text'].str.contains(r'[0-9A-Za-z]')]
    words = words.assign(y=words['top'] + words['height'] / 2)
    out = []
    for col, fit, side in time_columns(words):
        w = words.assign(dx=words['left'] - np.polyval(fit, words['y']))
        w = w[(w['dx'] >= FIELDS[0][1]) & (w['dx'] < FIELDS[-1][1]) & (w['y'] > side['y'].min() - 30)
              & (w['y'] < side['y'].max() + 80)]
        w = w.assign(field=[[k for k, edge in FIELDS if d >= edge][-1] for d in w['dx']])
        #rows: the ranks' heights against their numbers give the spacing
        ranks = w[(w['field'] == 'rank') & w['text'].str.fullmatch(r'\d{1,4}')]
        line = robust_line(ranks['text'].astype(int).values, ranks['y'].values)
        if line is None:
            continue
        pitch, y0 = line
        #the tilt across the column: the one that puts the most words on a row
        right = w[w['dx'] > 300]
        ry, rdx = right['y'].values, right['dx'].values
        tilts = np.arange(-0.03, 0.0301, 0.0005)
        score = [np.mean(np.abs(frac((ry - tl * rdx - y0) / pitch))) for tl in tilts]
        tilt = tilts[int(np.argmin(score))]
        pos = (w['y'] - tilt * w['dx'] - y0) / pitch
        w = w.assign(place=np.round(pos).astype(int), off=frac(pos))
        w = w[abs(w['off']) < 0.35]
        #the column's first row follows on from the last one. OCR misreads a rank's first digit often enough ('9643'
        #for '2643') to throw the whole column out by thousands, so a column that doesn't follow on is moved to where
        #it does, when the ranks' last two digits agree
        lo = w.loc[w['field'].isin(['rank', 'time', 'bib']) & w['text'].str.contains(r'\d'), 'place'].min()
        if start is not None and lo != start:
            r = ranks.assign(place=np.round((ranks['y'] - y0) / pitch).astype(int))
            agree = lambda shift: (r['text'].str[-2:] == (r['place'] + shift).astype(str).str[-2:]).mean()
            if agree(start - lo) >= 0.5:
                w = w.assign(place=w['place'] + start - lo)
            else:
                print('page {} column {}: starts at {}, not {}'.format(page, col, lo, start))
        rows = collections.defaultdict(lambda: collections.defaultdict(list))
        tops = collections.defaultdict(list)
        boxes = collections.defaultdict(list)
        for source, place, field, text, top, d, left, width, height in sorted(
                zip(w['source'], w['place'], w['field'], w['text'], w['top'], w['dx'], w['left'], w['width'],
                    w['height']), key=lambda r: r[5]):
            rows[source, place][field].append(text)
            tops[place].append((d >= 150, top))
            if field == 'name':
                boxes[source, place].append((left, top, width, height))
        #where each row's name is printed: its words' median top and height, across the name field
        regions = {}
        for place in {p for _, p in boxes}:
            b = [x for (s, p), bs in boxes.items() if p == place for x in bs if x[3] <= 22]
            if b:
                top, height = np.median([x[1] for x in b]), np.median([x[3] for x in b])
                x = np.polyval(fit, top + height / 2)
                regions[place] = (int(x + 155), int(top), int(x + 445), int(top + height))
        for (source, place), row in rows.items():
            fields = {k: ' '.join(row[k]) for k, _ in FIELDS[:-1]}
            #a result has numbers in at least two of its number fields (not the header)
            if sum(bool(re.search(r'\d', fields[k])) for k in ('rank', 'time', 'bib', 'cls', 'crank', 'pace')) >= 2:
                out.append({'source': source, 'page': page, 'column': col, 'place': place, 'tilt': tilt,
                            'top': int(min(tops[place])[1]), 'name_region': regions.get(place), **fields})
                start = max(start or 0, place + 1)
    return out, start


def frac(x):
    return x - np.round(x)


def robust_line(x, y):
    #y = pitch * x + y0 through the most points, for ranks that agree on their spacing
    if len(x) < 5:
        return None
    best, best_n = None, 0
    rng = np.random.default_rng(0)
    for _ in range(300):
        i, j = rng.choice(len(x), 2, replace=False)
        if x[i] == x[j]:
            continue
        pitch = (y[j] - y[i]) / (x[j] - x[i])
        if not 15 < pitch < 35:
            continue
        y0 = y[i] - pitch * x[i]
        n = (abs(y - (pitch * x + y0)) < 0.25 * pitch).sum()
        if n > best_n:
            best, best_n = (pitch, y0), n
    if best is None:
        return None
    pitch, y0 = best
    inl = abs(y - (pitch * x + y0)) < 0.25 * pitch
    pitch, y0 = np.polyfit(x[inl], y[inl], 1)
    return pitch, y0


#---------------------------------------------------------------- this year's OCR of each column

#suffix: scale of the column OCRs
COLUMN_OCR = {'d3': 3, 'd4': 4}
OCR_WORKERS = 4
SCRATCH = os.path.join('old_results', 'scratch', '1994')


def column_ocr(year, pages):
    #each results column cropped from the page, turned level and read again at three and four times the size with the
    #results' characters (--psm 6), as old_results/ocr/1994/<page>_c<column><suffix>.tsv with its boxes put back in page
    #pixels. only the columns not read yet are read
    jobs = []
    for page in pages:
        words = ocr_words(year, page).assign(source='x2')
        for col, fit, side in time_columns(words):
            for suffix, scale in COLUMN_OCR.items():
                path = os.path.join(OCR_DIR, str(year), '{:03d}_c{}{}.tsv'.format(page, col, suffix))
                if not os.path.exists(path):
                    jobs.append((year, page, col, tuple(fit), side['y'].min(), side['y'].max(), path, scale))
    with concurrent.futures.ThreadPoolExecutor(OCR_WORKERS) as pool:
        for path in pool.map(read_column, jobs):
            print(path)


def read_column(job):
    year, page, col, fit, top, bottom, path, scale = job
    #the column from a row above its first time to a row below its last, from the rank to the pace
    y0, y1 = int(top - 50), int(bottom + 50)
    xs = [np.polyval(fit, y0), np.polyval(fit, y1)]
    x0, x1 = int(min(xs) + FIELDS[0][1] - 15), int(max(xs) + FIELDS[-1][1] + 13)
    image = Image.open(os.path.join(PAGE_DIR, str(year), '{:03d}.png'.format(page)))
    crop = image.crop((x0, y0, x1, y1))
    #the turn of its rows, from the page OCR's long lines in it
    words = ocr_words(year, page)
    words = words[(words['left'] >= x0) & (words['left'] < x1) & (words['top'] >= y0) & (words['top'] < y1)]
    tilts = [np.polyfit(line['left'], line['top'] + line['height'], 1)[0]
             for _, line in words.groupby(['block_num', 'par_num', 'line_num'])
             if len(line) >= 6 and line['left'].max() - line['left'].min() > 500]
    angle = float(np.degrees(np.arctan(np.median(tilts)))) if tilts else 0
    crop = crop.rotate(angle, resample=Image.BICUBIC, fillcolor=255)
    crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    tmp = os.path.join(SCRATCH, 'tmp_' + os.path.basename(path)[:-4])
    os.makedirs(SCRATCH, exist_ok=True)
    crop.save(tmp + '.png')
    subprocess.run([TESSERACT, tmp + '.png', tmp, '--psm', '6', '-c', 'tessedit_char_whitelist=' + RESULT_CHARACTERS,
                    'tsv'], capture_output=True)
    words = pd.read_csv(tmp + '.tsv', sep='	', quoting=3, dtype={'text': str}, keep_default_na=False)
    #back to page pixels: undo the scale, the turn about the crop's centre (PIL turns counterclockwise) and the crop
    cx, cy = (x1 - x0) / 2, (y1 - y0) / 2
    w, h = words['width'] / scale, words['height'] / scale
    mx, my = words['left'] / scale + w / 2 - cx, words['top'] / scale + h / 2 - cy
    a = np.radians(angle)
    words['left'] = (mx * np.cos(a) - my * np.sin(a) + cx - w / 2 + x0).round().astype(int)
    words['top'] = (mx * np.sin(a) + my * np.cos(a) + cy - h / 2 + y0).round().astype(int)
    words['width'], words['height'] = w.round().astype(int), h.round().astype(int)
    words.to_csv(path, sep='	', index=False, quoting=3)
    os.remove(tmp + '.png')
    os.remove(tmp + '.tsv')
    return path


#---------------------------------------------------------------- reading the fields

DIGIT_CHARS = str.maketrans({'O': '0', 'o': '0', 'D': '0', 'Q': '0', 'I': '1', 'l': '1', '|': '1', 'i': '1', 'L': '1',
                             'S': '5', 's': '5', 'B': '8', 'Z': '2', 'z': '2', 'G': '6'})
CLASS_DIGITS = {c.replace('-', ''): c for c in CLASSES if c != '70+'}


def time_reads(text):
    #the times a field could be: h:mm:ss.t where the marks between show it, or else six digits, or seven with a stray
    #mark read as a digit at either end
    text = str(text).translate(DIGIT_CHARS)
    m = re.search(r'(\d)\s?[:;.,\']\s?(\d\d)\s?[:;.,\']\s?(\d\d)\s?[.,]\s?(\d)', text)
    if m and int(m.group(2)) < 60 and int(m.group(3)) < 60:
        return ['{}:{}:{}.{}'.format(*m.groups())]
    d = digits(text)
    if len(d) == 6:
        return [t for t in [read_time(d)] if t]
    if len(d) == 7:
        return [t for t in {read_time(d[1:]), read_time(d[:-1])} if t]
    return []


def pace_read(text):
    #'3.18' as seconds per km
    m = re.search(r'(\d)\W{0,2}(\d\d)\W*$', str(text).translate(DIGIT_CHARS))
    if not m or int(m.group(2)) > 59:
        return np.nan
    return int(m.group(1)) * 60 + int(m.group(2))


def class_read(text):
    #'M40-44', 'M4044', '-M35-39', 'MS50-54' (S for 5 read twice), 'M704' (70+): the class, and what follows it
    d = digits(text)
    found = [(c, d.index(k)) for k, c in CLASS_DIGITS.items() if k in d]
    if len(found) == 1:
        c, i = found[0]
        return c, d[i + 4:]
    if re.search(r'7\s*0\s*[+4]', str(text)) or digits(text) == '70':
        return '70+', ''
    return '', ''


#digits read in place of letters in a name or town ('8RIAN', 'W 8ABCOCK', 'JAMES 1 MUDGETT')
LETTER_DIGITS = str.maketrans({'1': 'I', '0': 'O', '8': 'B', '5': 'S', '6': 'G', '2': 'Z'})


def name_clean(text):
    text = re.sub(r"[^A-Z0-9 '\-&]", ' ', str(text).upper()).translate(LETTER_DIGITS)
    return re.sub(r'\s+', ' ', text).strip(" -'")


def town_clean(text):
    town = name_clean(text)
    return town if re.search(r'[A-Z]{2}', town) else ''


def nat_read(text):
    m = re.findall(r'[A-Z]{2,3}', str(text).upper())
    return m[-1] if m else ''


def state_read(text):
    #'WI', OCR's 'Wi', 'Wl', '1L', 'ONT' (the tables' Ontario)
    s = re.sub(r'[^A-Za-z1|]', '', str(text)).upper().replace('|', 'I')
    for v in (s, s.replace('1', 'I'), s.replace('L', 'I').replace('1', 'I'), s.replace('1', 'L')):
        if v in US_STATES | CA_PROVINCES | set(PROVINCES):
            return PROVINCES.get(v, v)
    return ''


def record_fields(r):
    cls, rest = class_read(r['cls'])
    if not cls:
        cls, rest = class_read(r['nat'] + ' ' + r['cls'])
    crank = digits(r['crank']) or rest
    pace = pace_read(r['pace']) if r['pace'] else pace_read(r['club'])
    times = time_reads(r['time'])
    if not times and ':' in r['rank']:
        #the rank run into the time: '12:36:47.0'
        times = time_reads(r['rank'])
    return {'times': times, 'time_digits': digits(r['time']), 'bib': digits(r['bib']),
            'name': name_clean(r['name']), 'city': town_clean(r['town']), 'state': state_read(r['st']),
            'st_raw': re.sub(r'[^A-Z]', '', str(r['st']).upper()),
            'country': nat_read(r['nat']), 'cls': cls, 'class_rank': crank if 0 < len(crank) <= 3 else '',
            'pace': pace}


#how much each OCR's reading counts in a vote. the column crops (d3, d4) read more of the times and class ranks, but
#where they and the whole page (x2, x1) read a field two against two, the page is right more often (the crops read 1 as 4
#or 7, IA as LA, IOWA as LOWA, WV as WY); the page at twice the size reads bibs best. d3 and d4 are near copies of each
#other, so together they count for a little more than one OCR, and three OCRs always outvote one
WEIGHTS = {'x2': 1.0, 'd3': 0.8, 'x1': 0.7, 'd4': 0.4}
TEXT_WEIGHTS = {'x2': 1.0, 'x1': 0.8, 'd3': 0.7, 'd4': 0.4}
BIB_WEIGHTS = {'x2': 1.0, 'x1': 0.8, 'd3': 0.6, 'd4': 0.3}
#the bibs run 1 to 10437; longer readings are a digit read twice or a mark read as one
MAX_BIB = 10999


def blank(v):
    return v in ('', None) or (isinstance(v, float) and np.isnan(v))


def tally(values, weights):
    #each reading's total weight, in the order first read
    out = {}
    for v, w in zip(values, weights):
        if not blank(v):
            out[v] = out.get(v, 0) + w
    return out


def vote(values, weights):
    #the reading with the most weight; ties go to the first source's
    t = tally(values, weights)
    return max(t, key=t.get) if t else ''


def best(values, weights, score):
    #the reading with the best score, then the most weight
    t = tally(values, weights)
    return max(t, key=lambda v: (score(v), t[v])) if t else ''


#---------------------------------------------------------------- names and towns

@functools.lru_cache(maxsize=None)
def known_names():
    #first and last names in the clean results, letters only
    clean = load_all_results()
    return frozenset(clean['first'].map(compact)) - {''}, frozenset(clean['last'].map(compact)) - {''}


@functools.lru_cache(maxsize=None)
def town_spellings():
    #(town letters only, state) -> the town as the clean results spell it most often
    clean = load_all_results()
    clean = clean[clean['city'].fillna('') != '']
    counts = clean.groupby([clean['city'].map(compact), 'state'])['city'].agg(lambda s: s.str.upper().mode().iloc[0])
    return counts.to_dict()


def name_score(name):
    first, last = known_names()
    f, _, l, _ = split_first_last(name)
    return (compact(f) in first) + (compact(l) in last)


def name_spacings(name, words=None):
    #the name, and the name with a space OCR lost put back: where the page shows more words than were read, every way of
    #splitting an initial off the end of the first word or the start of the last ('PAULAL KASTENSON', 'HARRY MLENKE'),
    #or a one-word reading into two or three, that makes more of the name known (not 'JANE T MCKEE' for JANET E MCKEE
    #with the E lost); with no word count, only splits that make a first and last name known ('STEVED WIKNER')
    out = [name]
    tokens = name.split()
    if not tokens:
        return out
    first, last = known_names()
    if words and words > len(tokens):
        if len(tokens) == 1:
            t = tokens[0]
            out += [t[:i] + ' ' + t[i:] for i in range(2, len(t) - 1)]
            out += [t[:i] + ' ' + t[i] + ' ' + t[i + 1:] for i in range(2, len(t) - 2)]
        else:
            heads = [tokens[0]] + [tokens[0][:-1] + ' ' + tokens[0][-1]] * (len(tokens[0]) > 2)
            tails = [tokens[-1]] + [tokens[-1][0] + ' ' + tokens[-1][1:]] * (len(tokens[-1]) > 2)
            out += [' '.join([h] + tokens[1:-1] + [t]) for h in heads for t in tails]
        score = name_score(name)
        return [n for n in out if n == name or (len(n.split()) == words and name_score(n) > score)]
    if words:
        return out
    score = name_score(name)
    if score == 2:
        return out
    t = tokens[0]
    for i in range(2, len(t)):
        a, b = t[:i], t[i:]
        if compact(a) in first and compact(t) not in first:
            if len(b) == 1 and len(tokens) > 1:
                out.append(' '.join([a, b] + tokens[1:]))
            elif len(tokens) == 1:
                out += [a + ' ' + b, ' '.join([a, b[0], b[1:]])]
    if len(tokens) == 2 and len(tokens[-1]) > 4:
        b = tokens[-1]
        out.append(' '.join(tokens[:-1] + [b[0], b[1:]]))
    return [n for n in out if n == name or name_score(n) > score]


def name_shape(name, town):
    #a name shaped as printed: its middle names initials or known first names ('MARY JANE C WURSTER'), and not run on
    #into the town ('PAUL WOIT GRAYSLAKE')
    first, _ = known_names()
    tokens = name.split()
    if len(tokens) > 2 and town and tokens[-1] == town.split()[0]:
        return False
    return all(len(m) == 1 or compact(m) in first for m in tokens[1:-1])


#a space between words is 6-9 pixels of blank page, between letters 1-3
WORD_GAP = (5, 15)


@functools.lru_cache(maxsize=3)
def page_ink(page):
    return np.asarray(Image.open(os.path.join(PAGE_DIR, '1994', '{:03d}.png'.format(page)))) < 140


def words_printed(page, region):
    #how many words the name printed in region has, from the blank columns between them on the page
    if not region:
        return None
    x0, y0, x1, y1 = region
    cols = page_ink(page)[y0:y1 + 1, x0:x1].sum(axis=0)
    ink = np.where(cols > 0)[0]
    if len(ink) < 2:
        return None
    blank = np.diff(ink) - 1
    return 1 + int(((blank >= WORD_GAP[0]) & (blank < WORD_GAP[1])).sum())


def choose_name(values, weights, town, words=None):
    #the readings are grouped by their letters, so that 'LINDA LWAPPNER' and 'LINDA L WAPPNER' count together. the
    #group whose reading has known names and the printed shape wins, then the one read with the most weight. its
    #spelling (as read, or with a lost space put back) is the one with as many words as the page shows, then the best
    #scored, then the one with the most initials split off
    groups, spellings = {}, {}
    for v, w in zip(values, weights):
        if v:
            k = compact(v)
            groups[k] = groups.get(k, 0) + w
            spellings.setdefault(k, {})
            for n in name_spacings(v, words):
                spellings[k][n] = spellings[k].get(n, 0) + w
    if not groups:
        return ''
    key = lambda n: (name_score(n), name_shape(n, town))
    k = max(groups, key=lambda k: (max(key(n) for n in spellings[k]), groups[k]))
    return max(spellings[k], key=lambda n: (len(n.split()) == words, key(n), sum(len(t) == 1 for t in n.split()),
                                            spellings[k][n]))


#states few skiers come from that OCR reads in place of a common one: Iowa's IA as LA, IL as HI, MI as ME
STATE_LOOKALIKES = {'LA': 'IA', 'HI': 'IL', 'ME': 'MI', 'VI': 'VT'}


def choose_place(states, cities, weights, raw=()):
    #the state and town: the state reading in which a town reading is a known town, else the one with the most weight
    #(a little more for a state many skiers come from); a state no town is known in is swapped for its lookalike when the
    #town is known there. with no state read ('WE', 'Wt' and 'It' for WI and IL), the one state that shares a letter
    #with a reading and has the town
    spell, skiers = town_spellings(), state_skiers()
    known = lambda s: any((compact(c), s) in spell for c in cities if c)
    t = tally(states, weights)
    state = max(t, key=lambda s: (known(s), t[s] + 0.25 * np.log10(skiers.get(s, 0) + 1))) if t else ''
    if state and not known(state):
        alts = {STATE_LOOKALIKES[s] for s in states if s in STATE_LOOKALIKES}
        alts = [a for a in alts if known(a)]
        if len(alts) == 1:
            state = alts[0]
    if not state:
        alts = {s for r in raw if len(r) == 2 for s in US_STATES | CA_PROVINCES if s[0] == r[0] or s[1] == r[1]}
        alts = [a for a in alts if known(a)]
        if len(alts) == 1:
            state = alts[0]
    town = choose_town(cities, weights, state)
    #'WASHINGTON DC' is printed in the hometown column, with the state column blank
    if not state and re.fullmatch(r'WASHINGTON [DO]C', town):
        town, state = 'WASHINGTON', 'DC'
    return state, town


@functools.lru_cache(maxsize=None)
def state_skiers():
    #how many results in the clean years come from each state
    return load_all_results()['state'].value_counts().to_dict()


#the NAT codes the tables use, and OCR's misreadings of them (SUI as SUL, ITA as TA, CAN as GAN, NL as ONL)
NATIONS = {'USA', 'CAN', 'GER', 'ITA', 'SUI', 'AUS', 'SWE', 'AUT', 'FRA', 'CZ', 'UK', 'FIN', 'POL', 'NZ', 'SLO', 'NL',
           'NOR', 'JPN', 'RUS', 'EST', 'DEN', 'NED', 'GBR', 'CZE', 'ESP', 'BEL', 'SVK', 'LAT', 'LTU', 'UKR', 'BLR'}
NATION_LOOKALIKES = {'SUL': 'SUI', 'SU': 'SUI', 'TA': 'ITA', 'GAN': 'CAN', 'ONL': 'NL', 'USR': 'USA', 'UBA': 'USA'}


def choose_country(values, weights, state):
    country = best(values, weights, lambda c: c in NATIONS)
    if country not in NATIONS:
        country = NATION_LOOKALIKES.get(country, country)
    if country not in NATIONS and state:
        country = 'USA' if state in US_STATES else 'CAN' if state in CA_PROVINCES else country
    return country


def choose_town(values, weights, state):
    #the town reading that's a known town in that state, else the one with the most weight. a known town read without
    #its spaces ('NEWBRIGHTON') is spelt as the clean results spell it
    spell = town_spellings()
    town = best(values, weights, lambda v: (compact(v), state) in spell)
    known = spell.get((compact(town), state))
    if known and known.replace(' ', '') == town.replace(' ', ''):
        return known
    return town


#---------------------------------------------------------------- merging the OCRs

def merge(records, names):
    fields = pd.DataFrame([record_fields(r) for _, r in records.iterrows()], index=records.index)
    records = pd.concat([records[['page', 'column', 'top', 'source', 'gender', 'place', 'name_region']], fields], axis=1)
    order = {n: i for i, n in enumerate(names)}
    records = records.assign(rank_=records['source'].map(order).fillna(9)).sort_values(['rank_'], kind='stable')
    records = records.assign(weight=records['source'].map(WEIGHTS), bib_weight=records['source'].map(BIB_WEIGHTS),
                             text_weight=records['source'].map(TEXT_WEIGHTS))
    rows = []
    for (gender, place), recs in records.groupby(['gender', 'place']):
        page = recs['page'].iloc[0]
        w = recs['weight'].tolist()
        row = {'gender': gender, 'place': place, 'page': recs['page'].iloc[0], 'column': recs['column'].iloc[0],
               'top': int(recs['top'].median()), 'n': len(recs), 'name_region': recs['name_region'].iloc[0]}
        row['time_options'] = [(t, x) for ts, x in zip(recs['times'], w) for t in ts]
        row['time_digits'] = [(d, x) for d, x in zip(recs['time_digits'], w) if 6 <= len(d) <= 7]
        for f in ('bib', 'name', 'city', 'state', 'cls', 'class_rank'):
            row[f + '_reads'] = dict(zip(recs['source'], recs[f]))
        row['pace'] = vote(recs['pace'].tolist(), w)
        bibs = [b if b and int(b) <= MAX_BIB else '' for b in recs['bib']]
        row['bib_tally'] = tally(bibs, recs['bib_weight'].tolist())
        row['bib'] = vote(bibs, recs['bib_weight'].tolist())
        tw = recs['text_weight'].tolist()
        row['state'], row['city'] = choose_place(recs['state'].tolist(), recs['city'].tolist(), tw,
                                                 recs['st_raw'].tolist())
        row['name_words'] = words_printed(page, row['name_region'])
        row['name'] = choose_name(recs['name'].tolist(), tw, row['city'], row['name_words'])
        row['country'] = choose_country(recs['country'].tolist(), tw, row['state'])
        row['cls'] = vote(recs['cls'].tolist(), w)
        row['class_rank'] = vote(recs['class_rank'].tolist(), w)
        rows.append(row)
    return unique_bibs(pd.DataFrame(rows))


def unique_bibs(rows):
    #no two skiers wear the same bib: where two rows read the same one, the row that reads it with less weight takes
    #its next reading, when that one is no other row's
    for _ in range(2):
        used = collections.Counter(rows['bib'])
        for bib, group in rows[rows['bib'].map(used) > 1].groupby('bib'):
            if bib == '':
                continue
            support = group['bib_tally'].map(lambda t: t.get(bib, 0))
            for i in support.sort_values(ascending=False).index[1:]:
                others = [b for b in sorted(rows.at[i, 'bib_tally'], key=rows.at[i, 'bib_tally'].get, reverse=True)
                          if b != bib and not used[b]]
                if others and support[i] < support.max():
                    rows.at[i, 'bib'] = others[0]
                    used[others[0]] += 1
                    used[bib] -= 1
    return rows


#---------------------------------------------------------------- times

def pace_of(seconds):
    return int(seconds // KM) if np.isfinite(seconds) else np.nan


#digits OCR mixes up in these tables
LOOKALIKES = {'0': '689', '1': '47', '2': '7', '3': '8956', '4': '1', '5': '6382', '6': '5803', '7': '12', '8': '36059',
              '9': '083'}


def one_off(d, lookalikes=True):
    #a time's six digits with one of them misread (as a lookalike, or as any digit), or seven with one too many (a stray
    #mark or a colon read as a digit)
    if len(d) == 7:
        out = {d[:j] + d[j + 1:] for j in range(7)}
    elif len(d) == 6:
        out = {d[:j] + s + d[j + 1:] for j in range(6) for s in (LOOKALIKES[d[j]] if lookalikes else '0123456789')}
    else:
        out = set()
    return {t for t in map(read_time, out) if t}


def heaviest_rising(secs, weight):
    #the rows whose times rise with place that weigh the most together (blank times are left out)
    n = len(secs)
    score = np.full(n, -np.inf)
    back = np.full(n, -1)
    for i in range(n):
        if not np.isfinite(secs[i]):
            continue
        prev = np.where(np.isfinite(secs[:i]) & (secs[:i] <= secs[i]) & np.isfinite(score[:i]))[0]
        if len(prev):
            j = prev[np.argmax(score[prev])]
            score[i], back[i] = score[j] + weight[i], j
        else:
            score[i] = weight[i]
    keep = np.zeros(n, bool)
    if np.isfinite(score).any():
        i = int(np.nanargmax(np.where(np.isfinite(score), score, -np.inf)))
        while i >= 0:
            keep[i] = True
            i = back[i]
    return keep


def digitwise(options):
    #the time each digit of the readings votes for on its own ('9:13:51.3', '3:13:54.3' and '3:13:51.3' make
    #3:13:51.3), weighed by the least support any of its digits has
    if not options:
        return {}
    votes = [{} for _ in range(6)]
    for t, w in options:
        for j, c in enumerate(digits(t)):
            votes[j][c] = votes[j].get(c, 0) + w
    d = ''.join(max(v, key=v.get) for v in votes)
    t = read_time(d)
    return {t: min(max(v.values()) for v in votes)} if t else {}


def choose_times(lst):
    #each row's time: the reading (or digit by digit vote of the readings) that agrees with the row's pace and the most
    #OCRs. the rows whose times rise with place (the heaviest such run, weighed by agreement) are kept; a row out of
    #order gets the one reading or lookalike reading that fits between its kept neighbours and its pace, or none
    lst = lst.sort_values('place').reset_index(drop=True)
    chosen, weight = [], []
    for options, pace in zip(lst['time_options'], lst['pace']):
        t = tally([t for t, _ in options], [w for _, w in options])
        for x, w in digitwise(options).items():
            t[x] = max(t.get(x, 0), w)
        fits = lambda x: pace != '' and pace_of(parse_seconds(x)) == pace
        best_t = max(t, key=lambda x: (fits(x), t[x])) if t else ''
        chosen.append(best_t)
        weight.append(t[best_t] + 2 * fits(best_t) if best_t else 0)
    secs = np.array([parse_seconds(t) for t in chosen])
    keep = heaviest_rising(secs, np.array(weight, float))
    kept = np.where(keep)[0]
    how = np.where(keep, 'kept', '').astype(object)
    for i in np.where(~keep)[0]:
        before = kept[kept < i]
        after = kept[kept > i]
        lo = secs[before[-1]] if len(before) else 0
        hi = secs[after[0]] if len(after) else np.inf
        #the pace printed with it, unless that was misread too (no time between the neighbours has it)
        pace = lst['pace'].iloc[i]
        if pace != '' and not ((pace + 1) * KM > lo and pace * KM <= hi):
            pace = ''
        ok = lambda t: lo <= parse_seconds(t) <= hi and (pace == '' or pace_of(parse_seconds(t)) == pace)
        fits = tally([t for t, _ in lst['time_options'].iloc[i] if ok(t)],
                     [w for t, w in lst['time_options'].iloc[i] if ok(t)])
        #else a reading with one digit read as a lookalike, else with one digit read as any other
        for lookalikes in (True, False):
            if not fits:
                pairs = [(t, w) for d, w in lst['time_digits'].iloc[i] for t in one_off(d, lookalikes) if ok(t)]
                fits = tally([t for t, _ in pairs], [w for _, w in pairs])
        #one time fits, or several that differ only in the tenths, one of them read by more
        ranked = sorted(fits, key=fits.get, reverse=True)
        if len(ranked) == 1 or (len(ranked) > 1 and len({t[:-2] for t in ranked}) == 1
                                and fits[ranked[0]] > fits[ranked[1]]):
            chosen[i] = ranked[0]
            how[i] = 'repaired'
        else:
            how[i] = 'blanked' if chosen[i] else 'unread'
            chosen[i] = ''
    lst['time'] = chosen
    lst['time_how'] = how
    return lst


#---------------------------------------------------------------- classes

def repair_classes(lst):
    #class ranks count up by one within each class, down the list. a row whose class or class rank OCR lost or misread
    #gets the class (or rank) that fits between the ranked rows before and after it in that class, when exactly one does
    lst = lst.sort_values('place').reset_index(drop=True)
    cls = lst['cls'].tolist()
    rank = [int(r) if str(r).isdigit() and int(r) > 0 else None for r in lst['class_rank']]
    members = {c: [i for i, x in enumerate(cls) if x == c] for c in CLASSES}

    def expected(i, c):
        #the rank row i would have in class c, counted on from the nearest ranked row before it (or from the start of
        #the list) and back from the nearest ranked row after it (None when there's none)
        m = members[c]
        j = bisect.bisect_left(m, i)
        before, after = m[:j], [x for x in m[j:] if x != i]
        b = next((rank[x] + n + 1 for n, x in enumerate(reversed(before)) if rank[x] is not None), len(before) + 1)
        a = next((rank[x] - n - 1 for n, x in enumerate(after) if rank[x] is not None), None)
        return b, a

    def move(i, c):
        if cls[i]:
            members[cls[i]].remove(i)
        cls[i] = c
        bisect.insort(members[c], i)

    how = [''] * len(lst)
    for _ in range(3):
        changed = 0
        for i in range(len(lst)):
            k, c = rank[i], cls[i]
            here = expected(i, c) if c else None
            if k is not None and c and k in here:
                continue
            #the classes this row's rank fits, on both sides and on the one side there is
            both = [x for x in CLASSES if k is not None and x != c and expected(i, x) == (k, k)]
            one = [x for x in CLASSES if k is not None and x != c and expected(i, x) == (k, None)]
            if c and here[0] == here[1]:
                #the read class has room for exactly this row: its rank was misread
                if not both:
                    rank[i], how[i] = here[0], 'rank'
                    changed += 1
            elif c and here[1] is None and k is None:
                #the last of its class, rank unread
                rank[i], how[i] = here[0], 'rank'
                changed += 1
            elif k is not None and len(both) == 1 or (not both and len(one) == 1 and not c):
                move(i, (both or one)[0])
                how[i] = 'class'
                changed += 1
            elif k is None and not c:
                gaps = [x for x in CLASSES if expected(i, x)[0] == expected(i, x)[1]]
                if len(gaps) == 1:
                    move(i, gaps[0])
                    rank[i], how[i] = expected(i, gaps[0])[0], 'class and rank'
                    changed += 1
        if not changed:
            break
    #runs of ranks that don't follow on, between two that do: when the run is as long as the gap between them, its
    #ranks are the ones in the gap ('178, 479, 780, 181' is 178, 179, 180, 181)
    for c, m in members.items():
        r = [rank[i] for i in m]
        good = [r[j] is not None and ((j == 0 and r[j] == 1) or (j > 0 and r[j - 1] == r[j] - 1)
                                      or (j + 1 < len(r) and r[j + 1] == r[j] + 1)) for j in range(len(r))]
        j = 0
        while j < len(r):
            if good[j]:
                j += 1
                continue
            k = j
            while k < len(r) and not good[k]:
                k += 1
            before = r[j - 1] if j else 0
            if k < len(r) and r[k] - before - 1 == k - j:
                for n, x in enumerate(m[j:k]):
                    if rank[x] != before + 1 + n:
                        rank[x], how[x] = before + 1 + n, 'rank'
            j = k
    lst['cls'] = cls
    lst['class_rank'] = ['' if r is None else str(r) for r in rank]
    lst['class_how'] = how
    return lst


#---------------------------------------------------------------- output

def finish(rows):
    rows = rows.sort_values(['gender', 'place'], ascending=[False, True])
    country = rows['country'].where(rows['country'] != '', np.where(rows['state'].isin(US_STATES), 'USA', ''))
    return pd.DataFrame({
        'place': rows['place'].astype(int).astype(str), 'bib': rows['bib'], 'name': rows['name'],
        'gender': rows['gender'],
        'age_group': [g + ' ' + c if c else '' for g, c in zip(rows['gender'], rows['cls'])],
        'class_rank': rows['class_rank'], 'city': rows['city'], 'state': rows['state'], 'country': country,
        'time': rows['time'], 'status': 'finished', 'tech': '', 'page': rows['page'], 'top': rows['top']
    }).reset_index(drop=True)
