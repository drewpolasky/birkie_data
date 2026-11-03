#the kortelopet's lists of 1979, 1980 and 1982, typed unlike the birkebeiner's printer tables of those years: 1979's
#and 1980's class by class, each class under a heading and numbered from 1 in order of time, typewritten; 1982's one
#list of men and women by overall place, on a dot matrix printer. each year's module (k1979.py, k1980.py, k1982.py)
#says which scan's pages hold its list, how each page is turned and levelled, its fields, and its sections: a box on
#the level page holding a class's lines (or the overall list's) in one to three columns, in the list's order. 1979's
#also gives a second copy of its pages, in another scan
#
#each section is levelled on its own, cut into its columns, and each column levelled again (the scans bend the pages).
#tesseract reads each column whole at twice the size, and again with only a time's characters where its times are
#(old_results/ocr/<scan>/<page>_kortie_<x>_<y>_<column>.tsv and ..._t.tsv; and ..._r.tsv, the column as scanned,
#where a dither is cleaned off it for the first reading). lines it loses are read again on their own. a line's fields
#are split at the column's tab stops (where most of its lines, near it and in all, have a word of the field's kind)
#
#a time is taken from its readings (and the second copy's) and its digits: each digit is cut out (by its marks, or on
#the printer's grid its points give) and matched to the digits of the times all of the readings agree on, and the
#times of each class (or the whole list) are put in order at least cost, a time no reading or digit makes fitting
#left unknown. a class code (1982's) and a printer's bib are read again the same way. a name or town is taken from
#the reading with most of its words seen in the clean results, a word a misread letter off a common one made that
#one. what the readings still get wrong, and what the scans cut off, is set from the scan in the module's HAND
import collections
import functools
import importlib
import itertools
import os
import re
import subprocess

import numpy as np
import pandas as pd
from PIL import Image, ImageFilter
from scipy import ndimage

from birkie_archive import PAGE_DIR, OCR_DIR, TESSERACT
from old_results_parsers.line_printer import word_counts, town_counts, SUFFIXES
from results_loader import US_STATES, CA_PROVINCES

SCALE = 2
NAME_CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:.,-'&#() "
TIME_CHARACTERS = '0123456789:.'
#characters tesseract reads in place of digits, and digits it mixes up with each other
DIGIT_LOOKS = str.maketrans({'O': '0', 'o': '0', 'D': '0', 'Q': '0', 'I': '1', 'l': '1', '|': '1', '!': '1', 'i': '1',
                             'L': '1', 'S': '5', 's': '5', '$': '5', 'B': '8', 'Z': '2', 'z': '2', 'G': '6', 'g': '9',
                             'q': '9', 'A': '4', 'b': '6', 'T': '7'})
LOOKALIKE = {'3': '85', '8': '360', '5': '63', '6': '58', '0': '986', '9': '0', '1': '74', '7': '1', '4': '1'}
#countries as the lists write them
COUNTRIES = {'NOR': 'NOR', 'NORWAY': 'NOR', 'NDR': 'NOR', 'CAN': 'CAN', 'CANADA': 'CAN', 'BRA': 'BRA', 'AUS': 'AUS',
             'FINLAND': 'FIN', 'FIN': 'FIN', 'SWE': 'SWE', 'SWEDEN': 'SWE', 'USA': 'USA', 'GER': 'GER', 'JPN': 'JPN'}
PROVINCES = {'MAN': 'MB', 'ONT': 'ON', 'ALTA': 'AB', 'SASK': 'SK', 'QUE': 'QC', 'ONTARIO': 'ON', 'MANITOBA': 'MB'}


def layout(year):
    return importlib.import_module('old_results_parsers.k{}'.format(year))


#---------------------------------------------------------------- pages and sections

#white added round a page before it's turned level, so that turning it doesn't cut off what's printed at its edges
PAD = 200


@functools.lru_cache(maxsize=4)
def level_page(scan, page, turn, angle):
    #the page in grays, turned upright and level, with PAD pixels of white round it
    im = Image.open(os.path.join(PAGE_DIR, str(scan), '{:03d}.png'.format(page))).convert('L')
    if turn is not None:
        im = im.transpose(turn)
    padded = Image.new('L', (im.width + 2 * PAD, im.height + 2 * PAD), 255)
    padded.paste(im, (PAD, PAD))
    return padded.rotate(angle, resample=Image.BICUBIC, fillcolor=255)


def page_crop(scan, page, turn, angle, box):
    #a box of the level page, in the pixels of the page as scanned (a box can reach into the white round it)
    return level_page(scan, page, turn, angle).crop(tuple(v + PAD for v in box))


def skew(img):
    #the angle that levels a piece of a page best: its rows of ink sharpest, from a quarter degree's steps to a
    #twentieth's
    small = img.resize((img.width // 2, img.height // 2))
    sharp = lambda a: (np.diff((np.array(small.rotate(a, resample=Image.NEAREST, fillcolor=255)) < 128)
                               .sum(1).astype(float)) ** 2).sum()
    coarse = max(np.arange(-2, 2.01, 0.25), key=sharp)
    return max(np.arange(coarse - 0.25, coarse + 0.26, 0.05), key=sharp)


def cleaned(img, clean):
    #clean (a blur's radius and a gray) makes a dither paper: the scan shades parts of some pages with a dither of dots
    #tesseract can't read through, which a blur turns a light gray and the print stays darker than
    if not clean:
        return img
    radius, gray = clean
    return Image.fromarray(np.where(np.array(img.filter(ImageFilter.GaussianBlur(radius))) < gray, 0, 255)
                           .astype(np.uint8))


def column_cuts(img, hints, reach=60):
    #where a section's columns part: the middle of the blank run (four pixels wide or more) nearest each hint, within
    #`reach` of it, or the column of pixels with least ink there
    ink = (np.array(img) < 128).sum(0)
    cuts = [0]
    for x in hints:
        lo, hi = max(0, x - reach), min(len(ink), x + reach)
        blank = [(s + lo, e + lo) for s, e in runs_of(ink[lo:hi] <= 1) if e - s >= 4]
        if blank:
            s, e = min(blank, key=lambda r: 0 if r[0] <= x < r[1] else min(abs(r[0] - x), abs(r[1] - x)))
            cuts.append(int(s + e) // 2)
        else:
            cuts.append(lo + int(np.argmin(ink[lo:hi])))
    return cuts + [img.width]


def runs_of(mask):
    #(start, end) of each run of True
    padded = np.concatenate([[False], mask, [False]]).astype(int)
    d = np.diff(padded)
    return list(zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]))


@functools.lru_cache(maxsize=4)
def section_columns(scan, page, turn, angle, box, hints, clean=None):
    #a section of the level page cut into its columns, each levelled on its own (the scans' pages are bent, so a
    #page's angle leaves its parts up to a degree off): the section is levelled, cut where its columns part, and each
    #column levelled again. each column's image (cleaned, and as scanned), where it was cut from the levelled section,
    #and the section's and column's angles
    raw = without_rules(page_crop(scan, page, turn, angle, box))
    img = cleaned(raw, clean)
    a1 = skew(img)
    img, raw = (i.rotate(a1, resample=Image.BICUBIC, fillcolor=255) for i in (img, raw))
    cuts = column_cuts(img, [h - box[0] for h in hints])
    out = []
    for c in range(len(cuts) - 1):
        column, column_raw = (i.crop((cuts[c], 0, cuts[c + 1], i.height)) for i in (img, raw))
        a2 = skew(column)
        column, column_raw = (i.rotate(a2, resample=Image.BICUBIC, fillcolor=255) for i in (column, column_raw))
        out.append({'image': column, 'raw': column_raw, 'cut': cuts[c], 'angles': (a1, a2), 'size': img.size})
    return out


def without_rules(img, longest=150):
    #a section without the rules printed down the page between its columns: ink running down more than `longest`
    #pixels is made paper
    gray = np.array(img)
    ink = gray < 160
    for x in np.nonzero(ink.sum(0) > longest)[0]:
        for start, end in runs_of(ink[:, x]):
            if end - start > longest:
                gray[start:end, max(0, x - 1):x + 2] = 255
    return Image.fromarray(gray)


def unrotate(x, y, size, angle):
    #a point of an image PIL turned by angle (degrees anticlockwise, about its middle) where it was before
    cx, cy = size[0] / 2, size[1] / 2
    t = np.radians(angle)
    dx, dy = x - cx, y - cy
    return cx + dx * np.cos(t) - dy * np.sin(t), cy + dx * np.sin(t) + dy * np.cos(t)


def page_point(column, box, x, y):
    #a point of a column's image (x, y as its words' boxes give them, less the section's left and top and the column's
    #cut) in the level page's pixels
    a1, a2 = column['angles']
    x, y = unrotate(x, y, column['image'].size, a2)
    x, y = unrotate(x + column['cut'], y, column['size'], a1)
    return x + box[0], y + box[1]


def section_path(scan, page, box, col, tag=''):
    return os.path.join(OCR_DIR, str(scan), '{:03d}_kortie_{}_{}_{}{}.tsv'.format(page, box[0], box[1], col, tag))


def tesseract(img, characters, psm='6', where=OCR_DIR):
    #the words tesseract reads in an image at SCALE times its size, with their boxes in the image's pixels (the image
    #saved in the directory `where` while it's read)
    out = os.path.join(where, 'kortie_{}'.format(os.getpid()))
    img.resize((img.width * SCALE, img.height * SCALE), Image.LANCZOS).save(out + '.png')
    subprocess.run([TESSERACT, out + '.png', out, '--psm', psm, '-c', 'tessedit_char_whitelist=' + characters, 'tsv'],
                   capture_output=True)
    words = pd.read_csv(out + '.tsv', sep='\t', quoting=3, dtype={'text': str}, keep_default_na=False)
    os.remove(out + '.png')
    os.remove(out + '.tsv')
    words = words[(words['level'] == 5) & (words['text'].str.strip() != '')].copy()
    words[['left', 'top', 'width', 'height']] = words[['left', 'top', 'width', 'height']] // SCALE
    return words


def with_lost_lines(img, words, where):
    #a column's words with those of the lines tesseract lost reading it whole (two lines' gap between the lines it
    #kept), each read again on its own
    lines = [l for l in text_lines(words) if is_entry(l)]
    ys = [middle(l) for l in lines]
    if len(ys) < 3:
        return words
    pitch = np.median(np.diff(ys))
    found = [words]
    for a, b in zip(ys, ys[1:]):
        for k in range(1, int(round((b - a) / pitch))):
            y = a + k * (b - a) / round((b - a) / pitch)
            top = int(y - 0.6 * pitch)
            w = tesseract(img.crop((0, top, img.width, int(y + 0.6 * pitch))), NAME_CHARACTERS, '7', where)
            if len(w):
                w['top'] += top
                w['block_num'] = 1000 + len(found)
                found.append(w)
    return pd.concat(found, ignore_index=True)


def ocr_section(scan, page, turn, angle, box, hints, fields, clean=None):
    #a section's columns, each read whole and then its time column alone (the rest of the column made paper), as
    #old_results/ocr/<scan>/<page>_kortie_<x>_<y>_<column>.tsv and ..._t.tsv, with the words' boxes in the column's
    #levelled image, moved by the section's left and top and the column's cut
    tags = ('', '_t', '_r') if clean else ('', '_t')
    paths = [section_path(scan, page, box, c, t) for c in range(len(hints) + 1) for t in tags]
    if all(os.path.exists(p) for p in paths):
        return
    where = os.path.dirname(paths[0])
    os.makedirs(where, exist_ok=True)
    for c, column in enumerate(section_columns(scan, page, turn, angle, tuple(box), tuple(hints), clean)):
        words = with_lost_lines(column['image'], tesseract(column['image'], NAME_CHARACTERS, where=where), where)
        lines = [l for l in text_lines(words) if is_entry(l)]
        #(the column's time alone, with the rest of it made paper)
        stop = tab_stops(lines, fields)['time']
        times = column['image'].copy()
        times.paste(255, (0, 0, max(0, stop - 10) if stop is not None else times.width, times.height))
        #(and where the scan is cleaned of a dither, the column as scanned too, whose names read better outside the
        #dither)
        readings = [('', words), ('_t', tesseract(times, TIME_CHARACTERS, where=where))]
        if clean:
            readings.append(('_r', tesseract(column['raw'], NAME_CHARACTERS, where=where)))
        for tag, w in readings:
            w['left'] += box[0] + column['cut']
            w['top'] += box[1]
            w.to_csv(section_path(scan, page, box, c, tag), sep='\t', index=False, quoting=3)


def section_words(scan, page, box, col, tag=''):
    return pd.read_csv(section_path(scan, page, box, col, tag), sep='\t', quoting=3, dtype={'text': str},
                       keep_default_na=False)


def text_lines(words):
    #tesseract's lines, top to bottom, each its words left to right
    lines = [l.sort_values('left') for _, l in words.groupby(['block_num', 'par_num', 'line_num'])]
    return sorted(lines, key=lambda l: l['top'].median())


def is_entry(line):
    #a line of the list, not a heading's: it starts with a number or has a time
    kinds = [word_kind(t) for t in line['text']]
    return len(kinds) > 1 and (kinds[0] == 'num' or 'time' in kinds)


#---------------------------------------------------------------- fields

#the kind of word that starts each field
KIND = {'place': 'num', 'bib': 'num', 'class': 'num', 'name': 'alpha', 'town': 'alpha', 'state': 'alpha',
        'time': 'time'}


def word_kind(text):
    digits = sum(c.isdigit() for c in text)
    if digits >= 3 and re.search(r'\d\s*[:.;,]\s*\d', text):
        return 'time'
    if digits and digits >= len(text.strip('.,')) - 1:
        return 'num'
    if sum(c.isalpha() for c in text) >= 2:
        return 'alpha'
    return ''


def tab_stops(lines, fields, least=0.5, near=16, tab=30):
    #each field's left edge in a column: the left of the first run `near` pixels wide that at least `least` of its
    #lines have a word of the field's kind starting in, in the fields' order, or None for a field it hasn't (a time the
    #scan cuts off). the first field (the place) starts at the column's left where its numbers are right aligned. a
    #town's words count only after a space at least `tab` pixels wide (the typists tab to it), so that the first names
    #after surnames of a length aren't taken for it
    words = pd.concat(lines) if lines else pd.DataFrame(columns=['text', 'left', 'width'])
    kinds = words['text'].map(word_kind).values
    lefts = words['left'].values
    space = np.concatenate([[np.inf] + list(l['left'].values[1:] - (l['left'] + l['width']).values[:-1])
                            for l in lines]) if lines else np.array([])
    stops, x = {}, -np.inf
    for field in fields:
        found = None
        ok = (kinds == KIND[field]) & ((space >= tab) if field == 'town' else True)
        for left in sorted(set(lefts[ok & (lefts > x)])):
            if ((lefts >= left) & (lefts <= left + near) & ok).sum() >= least * len(lines):
                found = left
                break
        if field == fields[0]:
            stops[field] = -np.inf
        else:
            stops[field] = found - 4 if found is not None else None
        x = found + near if found is not None else x
    return stops


def local_stops(lines, i, fields, reach=8, drift=60, least=(0.5, 0.65)):
    #a line's tab stops, from the lines up to `reach` either side of it: the scans stretch the print unevenly down a
    #column, its right fields drifting a few characters against its left. where those lines don't show a field's, or
    #show one more than `drift` pixels off the whole column's (a run of first names of a length), the whole column's
    whole = tab_stops(lines, fields, least[0])
    near = tab_stops(lines[max(0, i - reach):i + reach + 1], fields, least[1])
    return {f: whole[f] if x is None or (whole[f] is not None and abs(x - whole[f]) > drift) else x
            for f, x in near.items()}


def split_fields(line, stops, reach=80):
    #a line's words by field, each word in the field whose stop is the last left of it. a name and the town after it
    #are parted at the widest space between their words within `reach` pixels of the town's stop (a typist's town
    #sits a little off its tab now and then, and the stops of the lines either side can be off for a line)
    out = {f: [] for f in stops}
    order = sorted(((f, x) for f, x in stops.items() if x is not None), key=lambda kv: kv[1])
    words = list(zip(line['text'], line['left'], line['left'] + line['width']))
    for text, left, right in words:
        field = [f for f, x in order if left >= x][-1] if left >= order[0][1] else order[0][0]
        out[field].append((text, left, right))
    if out.get('name') and stops.get('town') is not None:
        both = out['name'] + out['town']
        #(a surname printed with its comma keeps a first name after it)
        comma = next((j for j, w in enumerate(both) if w[0].endswith(',')), None)
        least = comma + 2 if comma is not None and comma + 2 < len(both) else 1
        gaps = [(both[j][1] - both[j - 1][2], j) for j in range(least, len(both))
                if abs(both[j][1] - stops['town']) <= reach]
        if gaps:
            j = max(gaps)[1]
            out['name'], out['town'] = both[:j], both[j:]
    return {f: [(t, l) for t, l, _ in v] for f, v in out.items()}


#---------------------------------------------------------------- times

def time_candidates(text, groups, cut=None):
    #the digits a reading can be, each with whether the reading has the time's shape (its colons and points where
    #the list prints them): its digits in the groups the list prints (1, 2, 2, 2: h:mm:ss.hh), from the groups it
    #reads between its colons and points, where a colon or point read as a digit (3154:27.44) is the extra digit at a
    #group's join. a 9 where a ten of minutes or seconds is is a 0 (the 1980 scan's typewriter face reads so). where
    #the scan's edge cuts the time off (cut: the digits it leaves, or 'edge' for as many as are read, 3 or more), the
    #digits before the cut. not checked for being a time
    #(without the words of no digits read after it, specks or the edge of the column next to it)
    words = text.split()
    while words and not re.search(r'\d', words[-1]):
        words.pop()
    text = ' '.join(words)
    if not text:
        return {}
    #(an hour that isn't read as a digit or a lookalike: & or F for 5)
    lost_hour = bool(re.match(r'\W*[^\w\s:.;,]|\W*[A-Za-z]', text.strip()))
    text = re.sub(r'[^0-9:.;,]', lambda m: m.group(0).translate(DIGIT_LOOKS), text)
    parts = [p for p in re.split(r'[^0-9]+', text) if p]
    digits = ''.join(parts)
    n = sum(groups)
    if cut == 'edge':
        lengths = range(3, n + 1)
    elif cut:
        lengths, digits = [cut], digits[:cut] if len(parts) > 2 else digits
    else:
        lengths = [n]
    shaped = [len(p) for p in parts] == [g for g in groups][:len(parts)] and len(digits) in lengths
    out = {digits: shaped} if len(digits) in lengths else {}
    #an hour lost (":07:09", "&.10.10.8"): each hour, for the times either side to choose
    lost = re.match(r'\W*[:.;,]', text) or (lost_hour and not re.match(r'\d', text.strip()))
    if lost and len(digits) + groups[0] in lengths and parts and len(parts[0]) == 2:
        for h in range(1, 7):
            out.setdefault(str(h) + digits, False)
    elif lost and not cut and [len(p) for p in parts[:len(groups) - 1]] == list(groups[1:]):
        for h in range(1, 7):
            out.setdefault(str(h) + digits[:n - groups[0]], False)
    #a speck or the next column's edge read as more digits after the time (3.42.53.0 2): the digits the time's groups
    #take, where the reading's first groups are the time's
    if not cut and len(digits) > n and [len(p) for p in parts[:len(groups) - 1]] == list(groups[:-1]):
        out.setdefault(digits[:n], False)
    #a separator read as a digit: drop one digit at each join the reading doesn't separate
    bounds = np.cumsum(groups)[:-1]
    sep_at = set(np.cumsum([len(p) for p in parts])[:-1])
    for length in lengths:
        if len(digits) <= length or len(digits) > length + 3:
            continue
        for drop in itertools.combinations(range(len(digits)), len(digits) - length):
            #each dropped digit sits where a join is, counted in the kept digits, and where no separator was read
            if all(i - k in bounds and i not in sep_at for k, i in enumerate(drop)):
                out.setdefault(''.join(d for i, d in enumerate(digits) if i not in drop), False)
    tens = (groups[0], groups[0] + 2)
    return {''.join('0' if i in tens and c == '9' else c for i, c in enumerate(d)): v for d, v in out.items()}


def valid_digits(d, groups):
    i = groups[0]
    return len(d) > i and d[0] != '0' and int(d[i]) < 6 and (len(d) <= i + 2 or int(d[i + 2]) < 6)


#a time the scan cuts off after its minutes, tens of seconds, seconds or tenths is taken as the middle of what's cut
PARTS = {3: '{}:{}{}:30', 4: '{}:{}{}:{}5', 5: '{}:{}{}:{}{}', 6: '{}:{}{}:{}{}.{}', 7: '{}:{}{}:{}{}.{}{}'}


def time_text(d, groups):
    #digits as h:mm:ss.hh (or h:mm:ss.t, or as much of it as the scan shows)
    return PARTS[len(d)].format(*d)


def time_seconds(d, groups):
    h, m, s = time_text(d, groups).split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def swaps(d, groups):
    #one digit swapped for a lookalike
    out = set()
    for i, c in enumerate(d):
        for o in LOOKALIKE.get(c, ''):
            s = d[:i] + o + d[i + 1:]
            if valid_digits(s, groups):
                out.add(s)
    return out


AGREED, ONE_READING, SWAPPED, UNREAD = 0, 1, 3, 10


def time_options(readings, groups):
    #the times a line's readings ((text, cut) each) make, each at its cost: 2 less one for each other reading that
    #makes it too (a reading the scan cuts off counting for the longer ones it begins), and one more where no reading
    #making it has the time's shape; or 3 for one digit of any reading swapped for a lookalike
    made = [time_candidates(text, groups, cut) for text, cut in readings]
    options = {}
    for d in set().union(*made):
        if valid_digits(d, groups):
            support = sum(any(d.startswith(c) for c in m) for m in made)
            shaped = any(m.get(d) for m in made)
            options[d] = max(0, 2 - support) + (0 if shaped else 1)
    for d in set().union(*made):
        for s in swaps(d, groups):
            options.setdefault(s, SWAPPED)
    return options


def order_times(options, groups, unread=UNREAD):
    #each line's time from its options ({digits: cost}) so that the times never go down down the list, at least cost,
    #leaving a line's time unknown costing unread: (digits or '', cost) a line. the cheapest chain ending in each option
    #is found from the cheapest ending at any time up to it before (a prefix minimum over the times, as a fenwick tree)
    options = [[(d, c, time_seconds(d, groups)) for d, c in o.items()] for o in options]
    n = len(options)
    times = sorted({s for o in options for _, _, s in o})
    index = {s: i + 1 for i, s in enumerate(times)}
    tree = [(np.inf, None)] * (len(times) + 1)

    def query(i):
        out = (np.inf, None)
        while i > 0:
            out = min(out, tree[i], key=lambda v: v[0])
            i -= i & -i
        return out

    def update(i, value):
        while i <= len(times):
            if value[0] < tree[i][0]:
                tree[i] = value
            i += i & -i

    #a chain's cost is kept less unread for each line up to its end, so that lines left out between count
    best = {}
    for i in range(n):
        found = []
        for j, (d, c, s) in enumerate(options[i]):
            before, back = query(index[s])
            start = unread * i + c - unread * (i + 1)
            cost = min(start, before + c - unread) if back is not None else start
            best[(i, j)] = (cost, back if back is not None and before + c - unread < start else None)
            found.append((index[s], (cost, (i, j))))
        for at, value in found:
            update(at, value)
    out = [('', unread)] * n
    if best:
        end = min(best, key=lambda key: best[key][0])
        if best[end][0] + unread * n < unread * n:
            while end is not None:
                i, j = end
                out[i] = (options[i][j][0], options[i][j][1])
                end = best[end][1]
    return out


#---------------------------------------------------------------- digits

#a digit's image, scaled to this many pixels wide and high to be matched
GLYPH = (12, 18)
#neighbours a digit is matched to, how sure a reading of a digit can be, and the cost of a time no reading makes
NEIGHBOURS = 7
SUREST = 0.98
WORST = 4.0


def digit_marks(img, box, n, ink=140):
    #the time's digits in its box on a column's image, left to right: the marks at least 0.6 of the tallest's height
    #(two digits printed touching split in half), where there are n of them, each scaled to GLYPH by the digits'
    #height. None where there aren't
    x0, y0, x1, y1 = box
    crop = 1 - np.array(img.crop((x0 - 4, y0 - 6, x1 + 4, y1 + 6))).astype(float) / 255
    lab, _ = ndimage.label(crop > 1 - ink / 255, np.ones((3, 3)))
    objs = ndimage.find_objects(lab)
    if not objs:
        return None
    tallest = max(o[0].stop - o[0].start for o in objs)
    #(rows, x from, x to, the mark's label or 0 for all the ink there)
    marks = sorted([(o[0], o[1].start, o[1].stop, i + 1) for i, o in enumerate(objs)
                    if o[0].stop - o[0].start >= 0.6 * tallest and o[1].stop - o[1].start >= 2], key=lambda m: m[1])
    while 0 < len(marks) < n:
        widths = [m[2] - m[1] for m in marks]
        j = int(np.argmax(widths))
        if widths[j] < 1.6 * np.median(widths):
            break
        rows, a, b, _ = marks[j]
        marks[j:j + 1] = [(rows, a, (a + b) // 2, 0), (rows, (a + b) // 2, b, 0)]
    if len(marks) != n:
        return None
    top, bottom = min(m[0].start for m in marks), max(m[0].stop for m in marks)
    scale = GLYPH[1] / (bottom - top)
    out = []
    for _, a, b, i in marks:
        g = crop[top:bottom, a:b] if i == 0 else np.where(lab[top:bottom, a:b] == i, crop[top:bottom, a:b], 0)
        w = max(1, int(round(g.shape[1] * scale)))
        g = np.array(Image.fromarray((g * 255).astype(np.uint8)).resize((w, GLYPH[1]), Image.BILINEAR)) / 255
        canvas = np.zeros((GLYPH[1], GLYPH[0]))
        left = (GLYPH[0] - w) // 2
        canvas[:, max(0, left):max(0, left) + min(w, GLYPH[0])] = g[:, max(0, -left):max(0, -left) + GLYPH[0]]
        out.append(canvas.ravel())
    return np.array(out)


def time_grid(img, box, groups, ink=150):
    #the printer's grid on a line, from its time in its box on a column's image: its points (small marks about as wide
    #as high, sitting on the digits' baseline, a colon's lower dot) at their characters (1, 4 and 7 of h.mm.ss.t) give
    #the grid's pitch and offset, from the three that sit on a grid best. (top, bottom, pitch, offset), in the
    #column's pixels, or None where no three sit on a grid
    x0, y0, x1, y1 = box
    crop = 1 - np.array(img.crop((x0 - 6, y0 - 8, x1 + 8, y1 + 8))).astype(float) / 255
    lab, _ = ndimage.label(crop > 1 - ink / 255, np.ones((3, 3)))
    objs = ndimage.find_objects(lab)
    if not objs:
        return None
    tallest = max(o[0].stop - o[0].start for o in objs)
    tall = [o for o in objs if o[0].stop - o[0].start >= 0.6 * tallest]
    top, bottom = min(o[0].start for o in tall), max(o[0].stop for o in tall)
    dots = sorted((o[1].start + o[1].stop) / 2 for o in objs
                  if o[0].stop >= bottom - 1 and o[0].stop - o[0].start <= 0.45 * (bottom - top)
                  and 0.5 <= (o[1].stop - o[1].start) / (o[0].stop - o[0].start) <= 1.5)
    at = np.cumsum([g + 1 for g in groups])[:-1] - 1
    best = None
    for marks in itertools.combinations(dots, len(at)):
        pitch, offset = np.polyfit(at, marks, 1)
        miss = np.abs(offset + pitch * at - marks).max() / pitch if pitch > 0 else np.inf
        if pitch >= 4 and miss <= 0.2 and (best is None or miss < best[0]):
            best = (miss, pitch, offset)
    if best is None:
        return None
    _, pitch, offset = best
    return top + y0 - 8, bottom + y0 - 8, pitch, offset + x0 - 6


def grid_cells(img, grid, cells):
    #the characters in the given cells of a line's grid, each a pitch wide, scaled to GLYPH
    top, bottom, pitch, offset = grid
    crop = 1 - np.array(img).astype(float) / 255
    out = []
    for c in cells:
        left = int(round(offset + pitch * (c - 0.5)))
        g = crop[top:bottom, max(0, left):max(0, left + int(round(pitch)))]
        if g.size == 0:
            return None
        g = np.array(Image.fromarray((g * 255).astype(np.uint8)).resize(GLYPH, Image.BILINEAR)) / 255
        out.append(g.ravel())
    return np.array(out)


def digit_grid(img, box, groups):
    #the time's digits in its box on a column's image, cut out on the printer's grid (its digits print broken or
    #touching): None where its grid can't be found
    grid = time_grid(img, box, groups)
    at = np.cumsum([g + 1 for g in groups])[:-1] - 1
    return grid_cells(img, grid, [c for c in range(sum(groups) + len(groups) - 1) if c not in at]) if grid else None


def number_glyphs(img, grid, x0, x1, n, ink=150):
    #the digits of a number n characters long printed between x0 and x1 on a line: cells a pitch of the line's grid
    #wide (as its time's digits are cut), set about the middle of the number's ink, its own rows of ink high (a line
    #can sit a few pixels higher or lower at its left than at its time), each scaled to GLYPH
    top, bottom, pitch, _ = grid
    height = bottom - top
    crop = 1 - np.array(img.crop((int(x0), int(top) - 6, int(x1), int(bottom) + 6))).astype(float) / 255
    ink_rows = (crop > 1 - ink / 255).sum(1)
    start = max(range(len(ink_rows) - height + 1), key=lambda y: ink_rows[y:y + height].sum())
    crop = crop[start:start + height]
    cols = np.nonzero((crop > 1 - ink / 255).sum(0) >= 2)[0]
    if len(cols) < n * 3:
        return None
    middle = (cols[0] + cols[-1] + 1) / 2
    out = []
    for c in range(n):
        left = int(round(middle + (c - n / 2) * pitch))
        g = crop[:, max(0, left):max(0, left + int(round(pitch)))]
        if g.shape[1] == 0:
            return None
        g = np.array(Image.fromarray((g * 255).astype(np.uint8)).resize(GLYPH, Image.BILINEAR)) / 255
        out.append(g.ravel())
    return np.array(out)


def unit(x):
    x = x - x.mean(1, keepdims=True)
    return x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-9)


def digit_odds(glyphs, known, labels):
    #each digit's chance of being 0-9: the share of its nearest NEIGHBOURS among the digits of known value that are
    #each, at most SUREST
    known, out = unit(known), []
    for start in range(0, len(glyphs), 2000):
        near = np.argsort(-unit(glyphs[start:start + 2000]) @ known.T, axis=1)[:, :NEIGHBOURS]
        votes = np.array([np.bincount(labels[row], minlength=10) for row in near]) / NEIGHBOURS
        out.append(np.clip(votes, (1 - SUREST) / 9, SUREST))
    return np.concatenate(out) if out else np.zeros((0, 10))


def pinned(df, m):
    #the digits the order pins on each line: those its neighbours' times (the nearest above and below that all their
    #readings agree on) share from the hour on, {line: number of digits}
    out = {}
    for _, g in (df.groupby(m.ORDER_BY, sort=False) if m.ORDER_BY else [(None, df)]):
        sure = [(i, re.sub(r'\D', '', t)) for i, t, c in zip(g.index, g['time'], g['cost']) if c == AGREED and t]
        for (_, a), (i, _), (_, b) in zip(sure, sure[1:], sure[2:]):
            n = 0
            while n < min(len(a), len(b)) and a[n] == b[n]:
                n += 1
            out[i] = n
    return out


def learn_digits(df, groups, glyph_columns, pins, doubtful_nines=False):
    #the digits of known value: those of the times all of a line's readings agree on (in a face tesseract reads a 0
    #as 9 in, doubtful_nines, a 9 off the tens only where the order pins it, the times either side sharing it), and a
    #9 or 0 at a ten of minutes or seconds read as 0
    tens = (groups[0], groups[0] + 2)
    known, labels = [], []
    for i, r in df[df['cost'] == AGREED].iterrows():
        d = re.sub(r'\D', '', r['time'])
        if len(d) != sum(groups):
            continue
        for col in glyph_columns:
            g = r[col]
            if g is None:
                continue
            for pos, (digit, glyph) in enumerate(zip(d, g)):
                if digit == '9' and pos in tens:
                    digit = '0'
                if digit != '9' or not doubtful_nines or pos < pins.get(i, 0):
                    known.append(glyph)
                    labels.append(int(digit))
    return np.array(known), np.array(labels)


def glyph_options(odds, groups):
    #the times a line's digits make, each at its cost: each digit's -log chance, no more than WORST, summed over the
    #copies' readings of it. the likeliest digits, and each with one digit its next likeliest
    if not odds:
        return {}
    cost = sum(np.minimum(-np.log(o), WORST) for o in odds)
    best = cost.argmin(1)
    out = {''.join(map(str, best))}
    for pos in range(len(best)):
        for alt in np.argsort(cost[pos])[1:3]:
            b = best.copy()
            b[pos] = alt
            out.add(''.join(map(str, b)))
    return {d: float(sum(cost[i, int(c)] for i, c in enumerate(d))) for d in out if valid_digits(d, groups)}


#---------------------------------------------------------------- names and towns

def name_parts(text):
    #a name printed surname first ("TRIEBOLD, Roxanne", "Fritzell Jr.,Peter A", "KOSCIK, Ken Jr.") as the other years
    #print it (first names, then surname, in capitals), and its first and last names. a word not seen in the clean
    #results that a misread letter makes one seen there is that one
    first_counts, last_counts, _, _ = word_counts()
    text = re.sub(r'\s+', ' ', text.upper().replace('.', ' ')).strip(' ,-')
    last, comma, first = text.partition(',')
    if not comma:
        last, first = text, ''
    clean = lambda s: [w.strip("'-") for w in re.sub(r"[^A-Z' -]", ' ', s).split() if w.strip("'-")]
    #(an initial read as a digit: 4 for A)
    first = ' '.join(INITIALS.get(w, w) for w in first.split())
    last, first = clean(last), clean(first)
    suffix = [w for w in last[1:] + first if w in SUFFIXES]
    last = [known_word(w, last_counts) for w in last if w not in SUFFIXES or w == last[0]]
    first = [known_word(w, first_counts) for w in first if w not in SUFFIXES]
    last = ' '.join(last + suffix)
    return {'name': ' '.join(first + [last]).strip(), 'first': ' '.join(first), 'last': last}


#initials tesseract reads as digits
INITIALS = {'4': 'A', '8': 'B', '6': 'G', '5': 'S', '0': 'O'}


#letters tesseract reads for others in a state's abbreviation
STATE_LOOKS = {'L': 'I', '1': 'I', 'T': 'I', 'I': 'L', '0': 'O', 'M': 'N', 'N': 'M', 'H': 'N', 'V': 'W', 'U': 'N',
               'J': 'I', 'F': 'L', 'S': 'I'}


def state_of(key, city, guess=False):
    #a state or province as printed (MN, Man), or as one or two of its letters misread make it, the one the town is
    #seen in in the clean results where there are several. or, guessing (a state in a column of its own, the printer's
    #letters read badly: WE, IK, TH), the state the town is seen in that has most of the letters read where they're
    #read, or failing any, most often
    key = PROVINCES.get(key, key)
    if key in US_STATES | CA_PROVINCES:
        return key
    town = re.sub(r'[^A-Z ]', '', city.replace('ST. ', 'ST '))
    if guess and key:
        #(the town a letter off one seen there, as known_town has it)
        seen = [(sum(a == b for a, b in zip(st, key)), n, st) for st in US_STATES | CA_PROVINCES
                for n in [town_counts().get(st, collections.Counter())[known_town(town, st)]] if n]
        if seen:
            return max(seen)[2]
    #(a speck read after it: W1L)
    if len(key) == 3 and key[2] in 'LI1':
        key = key[:2]
    if len(key) != 2:
        return ''
    fits = {''.join(v) for v in itertools.product(*[{c} | set(STATE_LOOKS.get(c, '')) for c in key])}
    fits &= US_STATES | CA_PROVINCES
    if len(fits) > 1:
        fits = {f for f in fits if town_counts().get(f, collections.Counter())[town]}
    return fits.pop() if len(fits) == 1 else ''


def place_parts(text, guess=False):
    #where a skier's from: "Minneapolis, MN", "Oslo 2, NOR", "Winnipeg, Man CAN", "Grand Marais, MN USA", "Lakeville M
    #N", "Winona, MN FINLAND": (city, state, country). guess: see state_of
    #(a point between two words parts them: St.Paul, W.Allis)
    text = re.sub(r'(?<=[A-Za-z])\.(?=[A-Za-z])', '. ', text)
    words = [w.strip('.') for w in text.replace(',', ' , ').split()]
    words = [w for w in (re.sub(r"[^A-Za-z0-9'-]", '', w).strip("'-") for w in words) if w]
    country = ''
    if words and words[-1].upper() in COUNTRIES and len(words) > 1:
        country = COUNTRIES[words.pop().upper()]
    #a state spaced out (M N)
    if len(words) > 2 and len(words[-1]) == 1 and len(words[-2]) == 1:
        words[-2:] = [words[-2] + words[-1]]
    state = ''
    if len(words) > 1:
        city = ' '.join(words[:-1]).upper()
        state = state_of(words[-1].upper(), city, guess)
        if state:
            words.pop()
    city = ' '.join(words).upper()
    if not state and not country and city in COUNTRIES:
        return '', '', COUNTRIES[city]
    if state and country in ('', 'USA', 'CAN'):
        country = 'USA' if state in US_STATES else 'CAN'
    return known_town(city, state), state, country


def name_score(text):
    #a name's words seen in the clean results, less half of those of two letters or more that aren't
    first, last, either, _ = word_counts()
    words = [re.sub(r'[^A-Z]', '', w) for w in text.upper().replace(',', ' ').split()]
    return sum(either[w] > 0 for w in words if w) - 0.5 * sum(either[w] == 0 for w in words if len(w) > 1)


#a name as the lists print it, surname first
NAME = re.compile(r"^\W*[A-Za-z][A-Za-z'. -]*,[^,]*$")


def is_name(text):
    #a reading that's a name alone (where the second copy blanks out the names, its reading is the town)
    words = re.sub(r'[^A-Za-z ]', ' ', text).split()
    return bool(NAME.match(text)) and not any(w in US_STATES | CA_PROVINCES | set(COUNTRIES) for w in words[1:])


#letters tesseract reads for others in the typewriters' and the printer's faces
LETTER_LOOKS = {'T': 'IJF', 'I': 'TL', 'L': 'I', 'C': 'GE', 'G': 'CM', 'E': 'CAOB', 'K': 'RHB', 'R': 'KB', 'M': 'N',
                'N': 'MH', 'H': 'N', 'V': 'UY', 'U': 'V', 'Y': 'V', 'O': 'DNA', 'D': 'O', 'B': 'EH', 'P': 'R',
                'A': 'MO', 'F': 'PT', 'Q': 'O'}


def known_word(word, counts, common=3):
    #a name word of four letters or more not seen in the clean results, as the one seen there at least `common` times
    #that one letter read as its lookalike, or an X read in a speck of the dither, makes (HETDI: HEIDI, GROSHEXK:
    #GROSHEK)
    if len(word) < 4 or counts[word] or not word.isalpha():
        return word
    fits = {word[:i] + o + word[i + 1:] for i, c in enumerate(word) for o in LETTER_LOOKS.get(c, '')}
    fits |= {word[:i] + word[i + 1:] for i, c in enumerate(word) if c in 'XQ'}
    fits = [f for f in fits if counts[f] >= common]
    return fits[0] if len(fits) == 1 else word


def town_score(text):
    #2 for a town seen in its state in the clean results, 1 for a state or country alone, and a half more for a state
    #read as printed
    city, state, country = place_parts(text)
    exact = 0.5 * bool(re.search(r'\b{}\b'.format(state), text)) if state else 0
    if state and town_counts().get(state, collections.Counter())[re.sub(r'[^A-Z ]', '', city)]:
        return 2 + exact
    return (1 if country else 0) + exact


def known_town(city, state, common=3):
    #a town not seen in its state in the clean results, as the one town seen there at least `common` times that's a
    #letter off it (MINNEAPOLIE: MINNEAPOLIS)
    towns = town_counts().get(state)
    key = re.sub(r'[^A-Z ]', '', city.replace('ST. ', 'ST '))
    if not towns or len(key) < 4 or towns[key]:
        return city
    fits = [t for t, n in towns.items()
            if n >= common and len(t) == len(key) and sum(a != b for a, b in zip(t, key)) == 1]
    return fits[0] if len(fits) == 1 else city


#---------------------------------------------------------------- lists

def middle(line):
    return float((line['top'] + line['height'] / 2).median())


def sections(year):
    #the year's sections, each (index, scan, page, turn, angle, box, hints, class): its list's, then the second copy's
    #(TWINS, by the index of the section of the list they copy)
    m = layout(year)
    out = [(i, m.SCAN, page, m.TURN.get(page), m.ANGLE.get(page, 0), box, hints, cls)
           for i, (page, box, hints, cls) in enumerate(m.SECTIONS)]
    twins = [(i, m.TWIN_SCAN, page, m.TWIN_TURN.get(page), m.TWIN_ANGLE.get(page, 0), box, hints, m.SECTIONS[i][3])
             for i, (page, box, hints) in getattr(m, 'TWINS', {}).items()]
    return out, twins


def ocr(year):
    m = layout(year)
    for _, scan, page, turn, angle, box, hints, _ in sum(sections(year), []):
        ocr_section(scan, page, turn, angle, box, hints, m.FIELDS, getattr(m, 'CLEAN', None))


def section_rows(year, index, scan, page, turn, angle, box, hints, cls):
    #a section's lines, column by column, top to bottom: each field's text, the time's reading with only a time's
    #characters, where the line is in its column's image (y, the middle, and the time's box) and on the level page
    #(top, left and right)
    m = layout(year)
    clean = getattr(m, 'CLEAN', None)
    ocr_section(scan, page, turn, angle, box, hints, m.FIELDS, clean)
    columns = section_columns(scan, page, turn, angle, tuple(box), tuple(hints), clean)
    rows = []
    for col, column in enumerate(columns):
        lines = [l for l in text_lines(section_words(scan, page, box, col)) if is_entry(l)]
        times = text_lines(section_words(scan, page, box, col, '_t'))
        raw = text_lines(section_words(scan, page, box, col, '_r')) if clean else []
        dx, dy = box[0] + column['cut'], box[1]
        for i, line in enumerate(lines):
            stops = local_stops(lines, i, m.FIELDS, least=getattr(m, 'TAB_SHARES', (0.5, 0.65)))
            fields = split_fields(line, stops)
            y = middle(line)
            near = [t for t in times if abs(middle(t) - y) < 0.4 * line['height'].median()]
            left, top = int(line['left'].min()), int(line['top'].min())
            right = int((line['left'] + line['width']).max())
            x0, y0 = page_point(column, box, left - dx, top - dy)
            x1, _ = page_point(column, box, right - dx, top - dy)
            #(the time's box from the line's own reading where it reads one, the time column's otherwise)
            own = line[line['left'] >= stops['time']] if stops['time'] is not None else line.iloc[:0]
            digit_words = own['text'].str.contains(r'\d').values
            own = own.iloc[:np.nonzero(digit_words)[0].max() + 1] if digit_words.any() else own.iloc[:0]
            time_words = own if len(own) else (near[0] if near else own)
            #(the line as scanned, its fields split at the same stops)
            same = [r for r in raw if abs(middle(r) - y) < 0.4 * line['height'].median()]
            raw_fields = split_fields(same[0], stops) if same else {}
            rows.append({'name_r': ' '.join(t for t, _ in raw_fields.get('name', [])),
                         'town_r': ' '.join(t for t, _ in raw_fields.get('town', [])),
                         'section': index, 'column': col, 'page': page, 'top': int(y0), 'left': int(x0),
                         'right': int(x1), 'y': y, 'section_class': cls,
                         #(each field's stop and the line's top and bottom, in the column's image)
                         'stops': {f: (x - dx if x is not None and np.isfinite(x) else x) for f, x in stops.items()},
                         'line_box': (int(line['top'].min()) - dy, int((line['top'] + line['height']).max()) - dy),
                         'time_box': (int(time_words['left'].min()) - dx, int(time_words['top'].min()) - dy,
                                      int((time_words['left'] + time_words['width']).max()) - dx,
                                      int((time_words['top'] + time_words['height']).max()) - dy)
                         if len(time_words) else None,
                         **{f: ' '.join(t for t, _ in v) for f, v in fields.items()},
                         'time_t': ''.join(near[0]['text']) if near else ''})
    return rows


def place_digits(text):
    return re.sub(r'\D', '', text.translate(DIGIT_LOOKS))


def full_times(row, groups):
    return set(time_candidates(row['time'], groups)) | set(time_candidates(row['time_t'], groups))


def match_twin(main, twin, near=12, reach=8):
    #the line of the list each line of its second copy is (the copies' scans are at different sizes, and some of the
    #second copy's lines are blanked out): its top in the first copy's pixels from its top in its own, by the scale
    #between them (the straight line most of the lines whose places or times read the same in both lie within `near`
    #pixels of) and the offset of those lines up to `reach` lines either side (the scans bend the pages differently),
    #and it's the line nearest there
    anchors = []
    for _, t in twin.iterrows():
        for _, l in main.iterrows():
            same_place = t['place_digits'] and t['place_digits'] == l['place_digits']
            if same_place or (t['full'] & l['full']):
                anchors.append((t['y'], l['y']))
    anchors = np.array(anchors)
    if len(anchors) < 3:
        return {}
    best, fit = -1, None
    for i, j in itertools.combinations(range(len(anchors)), 2):
        if abs(anchors[i][0] - anchors[j][0]) < 50:
            continue
        a = (anchors[j][1] - anchors[i][1]) / (anchors[j][0] - anchors[i][0])
        if not 0.5 < a < 2:
            continue
        b = anchors[i][1] - a * anchors[i][0]
        inliers = (np.abs(a * anchors[:, 0] + b - anchors[:, 1]) <= near).sum()
        if inliers > best:
            best, fit = inliers, (a, b)
    if fit is None:
        return {}
    a, b = fit
    pitch = np.median(np.diff(sorted(main['y'])))
    offsets = anchors[:, 1] - a * anchors[:, 0]
    good = np.abs(offsets - b) < 1.5 * pitch
    out = {}
    for ti, t in twin.iterrows():
        local = good & (np.abs(anchors[:, 0] - t['y']) <= reach * pitch / a)
        at = a * t['y'] + (np.median(offsets[local]) if local.sum() >= 2 else b)
        li = (main['y'] - at).abs().idxmin()
        if abs(main.loc[li, 'y'] - at) < 0.4 * pitch:
            out[li] = ti
    return out


def joined(rows, fields):
    #the lines with the end of a line tesseract reads as a line of its own (a place, bib and name, and then the rest
    #a little lower) put back on the line before
    out = []
    for r in rows:
        rest = [f for f in fields[fields.index('name') + 1:] if r.get(f)]
        before = out[-1] if out else {}
        if before and rest and not any(r.get(f) for f in fields[:fields.index('name') + 1]) \
                and not re.search(r'\d', before.get(fields[-1], '')) and before['column'] == r['column']:
            for f in rest + ['time_t', 'time_box']:
                out[-1][f] = r[f]
            continue
        out.append(r)
    return out


def read_lines(year):
    #every line of the year's list in its order, with its second copy's readings of its time where there's one
    m = layout(year)
    main_sections, twin_sections = sections(year)
    df = pd.DataFrame(joined([r for sec in main_sections for r in section_rows(year, *sec)], m.FIELDS))
    df['place_digits'] = df['place'].map(place_digits)
    df['full'] = [full_times(r, m.TIME_GROUPS) for _, r in df.iterrows()]
    df[['time_2', 'time_2t', 'twin_page', 'twin_top', 'twin_left', 'twin_right']] = ''
    df['twin_box'] = None
    df[['name_2', 'town_2']] = ''
    if twin_sections:
        twin = pd.DataFrame([r for sec in twin_sections for r in section_rows(year, *sec)])
        twin['place_digits'] = twin['place'].map(place_digits)
        twin['full'] = [full_times(r, m.TIME_GROUPS) for _, r in twin.iterrows()]
        for (sec, col), t in twin.groupby(['section', 'column']):
            main = df[(df['section'] == sec) & (df['column'] == col)]
            for li, ti in match_twin(main, t).items():
                df.loc[li, ['time_2', 'time_2t', 'twin_page', 'twin_top', 'twin_left', 'twin_right']] = (
                    t.loc[ti, 'time'], t.loc[ti, 'time_t'], t.loc[ti, 'page'], t.loc[ti, 'top'], t.loc[ti, 'left'],
                    t.loc[ti, 'right'])
                df.at[li, 'twin_box'] = t.loc[ti, 'time_box']
                df.loc[li, ['name_2', 'town_2']] = t.loc[ti, 'name'], t.loc[ti, 'town']
    return df


def class_ranks(read):
    #each line's number in its class: one more than the line before's, or two or three more where the numbers read
    #there and on the next line say lines are missing
    out, prev = [], 0
    nums = [int(d) if d else None for d in read]
    for i, n in enumerate(nums):
        after = nums[i + 1] if i + 1 < len(nums) else None
        if n is not None and prev + 2 <= n <= prev + 3 and after == n + 1:
            prev = n
        else:
            prev += 1
        out.append(prev)
    return out


def code_glyph(img, x0, x1, top, bottom, ink=150):
    #the one character printed between x0 and x1 on a line of a column's image (a class code): all its ink but specks
    #(a printer's digit prints in broken pieces), scaled to GLYPH. None where there's none
    crop = 1 - np.array(img.crop((int(x0), int(top) - 4, int(x1), int(bottom) + 4))).astype(float) / 255
    lab, _ = ndimage.label(crop > 1 - ink / 255, np.ones((3, 3)))
    sizes = ndimage.sum(np.ones_like(crop), lab, range(1, lab.max() + 1))
    keep = np.isin(lab, np.nonzero(sizes >= 4)[0] + 1)
    if keep.sum() < 10:
        return None
    rows, cols = np.nonzero(keep.any(1))[0], np.nonzero(keep.any(0))[0]
    g = np.where(keep, crop, 0)[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    w = max(1, min(GLYPH[0], int(round(g.shape[1] * GLYPH[1] / g.shape[0]))))
    g = np.array(Image.fromarray((g * 255).astype(np.uint8)).resize((w, GLYPH[1]), Image.BILINEAR)) / 255
    canvas = np.zeros((GLYPH[1], GLYPH[0]))
    left = (GLYPH[0] - g.shape[1]) // 2
    canvas[:, left:left + g.shape[1]] = g
    return canvas.ravel()


def read_codes(year, df, field, codes, least=5):
    #a one-character field (the class code) read again from its glyph: matched to the NEIGHBOURS nearest of those
    #tesseract reads as a code alone (themselves left out), the code at least `least` of them are, or else tesseract's
    #reading where it's a code alone, or nothing
    main_sections, _ = sections(year)
    clean = getattr(layout(year), 'CLEAN', None)
    glyphs = []
    for _, r in df.iterrows():
        _, scan, page, turn, angle, sbox, hints, _ = main_sections[r['section']]
        column = section_columns(scan, page, turn, angle, tuple(sbox), tuple(hints), clean)[r['column']]
        #(its cell a set distance left of the time, where the time is found, and as high as the time's digits: a line's
        #box can take in its neighbours' ink)
        found = isinstance(r['time_box'], tuple)
        x0, x1 = (r['time_box'][0] + d for d in layout(year).CODE_CELL) if found else (None, None)
        grid = time_grid(column['raw'], r['time_box'], layout(year).TIME_GROUPS) if found else None
        rows = (grid[0] + 3, grid[1] - 3) if grid else r['line_box']
        glyphs.append(code_glyph(column['raw'], x0, x1, *rows) if found else None)
    #(tesseract's reading, a lookalike for a digit)
    read = df[field].map(lambda t: re.sub(r'\s', '', t).translate(DIGIT_LOOKS))
    known = [i for i, (g, t) in enumerate(zip(glyphs, read)) if g is not None and t in codes]
    if len(known) < 2 * NEIGHBOURS:
        return read.where(read.isin(codes), '')
    labels = np.array([read.iloc[i] for i in known])
    ref = unit(np.array([glyphs[i] for i in known]))
    out = []
    for j, g in enumerate(glyphs):
        if g is None:
            out.append(read.iloc[j] if read.iloc[j] in codes else '')
            continue
        sims = ref @ unit(g[None, :])[0]
        if j in known:
            sims[known.index(j)] = -np.inf
        votes = collections.Counter(labels[np.argsort(-sims)[:NEIGHBOURS]])
        code, n = votes.most_common(1)[0]
        out.append(code if n >= least else (read.iloc[j] if read.iloc[j] in codes else ''))
    return pd.Series(out, index=df.index)


def line_glyphs(year, df, n):
    #each line's time's digits' images, in its own copy's scan and in the second copy's
    main_sections, twin_sections = sections(year)
    clean = getattr(layout(year), 'CLEAN', None)
    out = {'glyphs': [], 'twin_glyphs': []}
    for _, r in df.iterrows():
        for key, secs, box in (('glyphs', main_sections, r['time_box']), ('twin_glyphs', twin_sections, r['twin_box'])):
            sec = [x for x in secs if x[0] == r['section']]
            if not sec or not isinstance(box, tuple):
                out[key].append(None)
                continue
            _, scan, page, turn, angle, sbox, hints, _ = sec[0]
            column = section_columns(scan, page, turn, angle, tuple(sbox), tuple(hints), clean)[r['column']]
            if getattr(layout(year), 'GLYPHS', 'marks') == 'grid':
                out[key].append(digit_grid(column['raw'], box, layout(year).TIME_GROUPS))
            else:
                out[key].append(digit_marks(column['raw'], box, n))
    return out


def read_bibs(year, df, known, labels, least=5):
    #a printer's bibs read again digit by digit, cut out on the line's grid (from its time) and matched to the time
    #digits of known value: the digits where each is at least `least` of its NEIGHBOURS' value, or else tesseract's
    m = layout(year)
    main_sections, _ = sections(year)
    out = []
    for _, r in df.iterrows():
        _, scan, page, turn, angle, sbox, hints, _ = main_sections[r['section']]
        column = section_columns(scan, page, turn, angle, tuple(sbox), tuple(hints), getattr(m, 'CLEAN', None))
        img = column[r['column']]['raw']
        grid = time_grid(img, r['time_box'], m.TIME_GROUPS) if isinstance(r['time_box'], tuple) else None
        x0, x1 = r['stops'].get('bib'), r['stops'].get('name')
        found = grid and x0 is not None and x1 is not None and np.isfinite(x0)
        glyphs = number_glyphs(img, grid, x0, x1 - 2, m.BIB_DIGITS) if found else None
        if glyphs is None:
            out.append(r['bib'])
            continue
        votes = digit_odds(glyphs, known, labels)
        #(the first digit one the year's bibs start with)
        first = [int(d) for d in getattr(m, 'BIB_FIRST', '0123456789')]
        votes[0, [d for d in range(10) if d not in first]] = 0
        sure = votes.max(1) >= least / NEIGHBOURS
        read = ''.join(str(v) for v in votes.argmax(1))
        out.append(read if sure.all() or len(r['bib']) != m.BIB_DIGITS else
                   ''.join(a if ok else b for a, b, ok in zip(read, r['bib'], sure)))
    return out


def put_in_order(df, m, unread=UNREAD):
    #(each class's times, or the whole list's)
    df['time'], df['cost'] = '', float(unread)
    for _, g in (df.groupby(m.ORDER_BY, sort=False) if m.ORDER_BY else [(None, df)]):
        for i, (d, c) in zip(g.index, order_times(g['options'].tolist(), m.TIME_GROUPS, unread)):
            #(a list that prints a few times out of order keeps a time read surely, KEEP_SURE, as printed)
            sure = min(g.at[i, 'options'].items(), key=lambda kv: kv[1], default=('', np.inf))
            if sure[1] <= getattr(m, 'KEEP_SURE', -1) and sure[0] != d and c - sure[1] >= SWAPPED:
                d, c = sure
            df.at[i, 'time'], df.at[i, 'cost'] = (time_text(d, m.TIME_GROUPS) if d else ''), float(c)


#once the digits are matched: the cost of leaving a line's time unknown, the weight of the readings' cost, and the
#most the digits' cost can be (where they're cut out badly)
GLYPH_UNREAD = 12
READING_WEIGHT = 0.5
GLYPH_CAP = 7


def parse(year):
    #the year's list: each line's fields, its time put in order, its class rank, gender and class, then the module's
    #HAND, and each skier's place by time among their gender
    m = layout(year)
    groups = m.TIME_GROUPS
    df = read_lines(year).reset_index(drop=True)
    #(each line's number down the list: a list known to be whole, LINES long, is checked for a line lost or read twice,
    #which would move the lines HAND sets by their number)
    df['line'] = range(1, len(df) + 1)
    if len(df) != getattr(m, 'LINES', len(df)):
        raise ValueError('{} lines read, {} printed'.format(len(df), m.LINES))
    if hasattr(m, 'CLASS_CODES'):
        df['class'] = read_codes(year, df, 'class', set(m.CLASS_CODES))
    df['age_group'] = df.apply(m.age_group, axis=1)
    df['gender'] = df['age_group'].str[0]
    cut, twin_cut = getattr(m, 'CUT', {}), getattr(m, 'TWIN_CUT', {})
    df['options'] = [time_options([(r['time'], cut.get((r['section'], r['column']))),
                                   (r['time_t'], cut.get((r['section'], r['column']))),
                                   (r['time_2'], twin_cut.get((r['section'], r['column']))),
                                   (r['time_2t'], twin_cut.get((r['section'], r['column'])))], groups)
                     for _, r in df.iterrows()]
    df['time_raw'] = df['time']
    #the times put in order from tesseract's readings alone, then again with each digit matched to those of the
    #times all the readings agree on
    put_in_order(df, m)
    for key, glyphs in line_glyphs(year, df, sum(groups)).items():
        df[key] = glyphs
    odds, pins = {}, pinned(df, m)
    for key in ('glyphs', 'twin_glyphs'):
        known, labels = learn_digits(df, groups, [key], pins, getattr(m, 'DOUBTFUL_NINES', False))
        rows = [i for i in df.index if df.at[i, key] is not None]
        if len(known) < 50 or not rows:
            continue
        flat = digit_odds(np.concatenate([df.at[i, key] for i in rows]), known, labels)
        for j, i in enumerate(rows):
            odds.setdefault(i, []).append(flat[j * sum(groups):(j + 1) * sum(groups)])
        if key == 'glyphs' and getattr(m, 'BIB_DIGITS', None) and getattr(m, 'GLYPHS', '') == 'grid':
            df['bib'] = read_bibs(year, df, known, labels)
    options = []
    differ = lambda a, b: sum(x != y for x, y in zip(a, b)) + abs(len(a) - len(b))
    for i, r in df.iterrows():
        reading = r['options']
        cost = sum(np.minimum(-np.log(o), WORST) for o in odds[i]) if i in odds else None
        likeliest = ''.join(map(str, cost.argmin(1))) if cost is not None else ''
        #(digits cut out badly, the likeliest of them three or more off every reading, aren't matched)
        if cost is None or (reading and min(differ(likeliest, d) for d in reading) >= 3):
            options.append({d: c / READING_WEIGHT for d, c in reading.items()})
            continue
        glyph_cost = lambda d: float(sum(cost[p, int(c)] for p, c in enumerate(d))) if len(d) == len(cost) else None
        made = glyph_options(odds[i], groups)
        out = {}
        for d in set(made) | set(reading):
            g = glyph_cost(d)
            if g is not None:
                out[d] = min(g, GLYPH_CAP) + READING_WEIGHT * reading.get(d, SWAPPED)
        options.append(out)
    df['options'] = options
    put_in_order(df, m, GLYPH_UNREAD)
    df['odds'] = [odds.get(i) for i in df.index]
    if m.CLASS_RANKS:
        df['class_rank'] = 0
        for _, g in df.groupby('age_group', sort=False):
            df.loc[g.index, 'class_rank'] = class_ranks(g['place_digits'].map(lambda d: d[-3:]).tolist())
    #a line with a bib in place of its name ("BIB # 7164")
    bibs = df['name'].str.extract(r'^\W*BIB\W+(?:\d\s+)?(\d{3,4})\b', expand=False)
    if 'bib' not in df:
        df['bib'] = ''
    df.loc[bibs.notna(), 'bib'] = bibs[bibs.notna()]
    df.loc[bibs.notna(), ['name', 'name_2']] = ''
    #a name or town from the copy whose reading has more words seen in the clean results
    df['name'] = [max([a] + [x for x in (r, b) if is_name(x)], key=name_score)
                  for a, r, b in zip(df['name'], df['name_r'], df['name_2'])]
    df['town'] = [max((a, r, b), key=town_score) for a, r, b in zip(df['town'], df['town_r'], df['town_2'])]
    names = df['name'].map(name_parts)
    df = df.assign(name=[n['name'] for n in names], first=[n['first'] for n in names], last=[n['last'] for n in names])
    places = [place_parts(t, getattr(m, 'GUESS_STATES', False))
              for t in df.apply(getattr(m, 'town_text', lambda r: r['town']), axis=1)]
    df['city'], df['state'], df['country'] = [p[0] for p in places], [p[1] for p in places], [p[2] for p in places]
    df['bib'] = df['bib'].map(lambda b: re.sub(r'\D', '', str(b).translate(DIGIT_LOOKS)))
    #(a list printing the bib right after the place, its bibs all BIB_DIGITS long: tesseract runs the two together
    #now and then, or splits a bib)
    n = getattr(m, 'BIB_DIGITS', None)
    if n and m.FIELDS[:2] == ('place', 'bib'):
        both = df['place_digits'] + df['bib']
        df['bib'] = both.map(lambda d: d[-n:] if len(d) >= n else d)
        df['place_digits'] = both.map(lambda d: d[:-n] if len(d) >= n else '')
    df = apply_hand(df, m)
    return finish(df, m)


def apply_hand(df, m):
    #the module's HAND, by each line's key (its class and class rank, or its printed place): what the scan shows that
    #the readings don't (a time to the digits the scan leaves, as 3:51:2, taken as the middle of what's cut)
    keys = df.apply(m.hand_key, axis=1)
    for key, what in getattr(m, 'HAND', {}).items():
        rows = df.index[keys == key]
        if len(rows) != 1:
            raise ValueError('HAND {} matches {} lines'.format(key, len(rows)))
        for field, value in what.items():
            if field == 'time' and value and not re.fullmatch(r'\d:\d\d:\d\d\.\d\d?', value):
                value = time_text(re.sub(r'\D', '', value), m.TIME_GROUPS)
            if field == 'name':
                df.loc[rows[0], ['first', 'last']] = name_parts(value)['first'], name_parts(value)['last']
                value = name_parts(value)['name']
            df.loc[rows[0], field] = value
            if field == 'class':
                df.loc[rows[0], 'age_group'] = m.age_group(df.loc[rows[0]])
                df.loc[rows[0], 'gender'] = df.loc[rows[0], 'age_group'][:1]
            if field == 'state':
                df.loc[rows[0], 'country'] = 'USA' if value in US_STATES else 'CAN'
        df.loc[rows[0], 'cost'] = 0.0
    return df


def finish(df, m):
    #each skier's place among their gender: by time in a list printed class by class (a line with no time has none),
    #or as printed in a list printed by overall place
    df = df.reset_index(drop=True)
    df['order'] = range(len(df))
    df['place'] = ''
    for _, g in df[df['gender'].isin(['M', 'F'])].groupby('gender'):
        if m.ORDER_BY == 'age_group':
            g = g[g['time'] != ''].assign(s=g['time'].map(lambda t: time_seconds(re.sub(r'\D', '', t), m.TIME_GROUPS)
                                                           if t else np.nan))
            g = g.sort_values(['s', 'order'])
            #a class the scan cuts short (the module's CUT_CLASSES) leaves the place of anyone slower than its last
            #line read unknown, so they have none
            cut = [g.loc[g['age_group'] == c, 's'].max() for c in getattr(m, 'CUT_CLASSES', ())]
            g = g[g['s'] <= min(cut)] if cut else g
        df.loc[g.index, 'place'] = [str(i + 1) for i in range(len(g))]
    df['status'], df['tech'] = 'finished', ''
    return df
