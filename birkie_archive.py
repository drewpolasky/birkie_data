#the birkie's results before 2002, kept apart from yearly_data/ and the models until they're known to be reliable:
#   1999, 2001: text pdfs on birkie.com, one list for men and one for women. no technique column
#   1973-1998:  scanned birch scroll magazines (or results booklets) linked from birkie.com's results page. images only,
#               so they need OCR
#2000 was cancelled. everything goes in old_results/: the downloads in old_results/pdfs/, each scanned page as an image in
#old_results/pages/ and its OCR (tesseract, with every word's box) in old_results/ocr/, none of them in git. the results go
#in old_results/<year>/birkie <year>.csv in the plain format results_loader reads (with a 'tech' column, since a year's
#list can mix techniques), checked by check_results.py. the kortelopet's results, in the same files, go in
#old_results/<year>/kortie <year>.csv, each scanned year's read by old_results_parsers/k<year>.py
#
#example usage:
#python birkie_archive.py download          every file, about 380 MB
#python birkie_archive.py pages             each scanned page as an image
#python birkie_archive.py ocr               OCR every page, about half an hour
#python birkie_archive.py parse             the text pdfs and the OCR into old_results/
import argparse
import concurrent.futures
import functools
import glob
import importlib
import io
import os
import re
import subprocess

import numpy as np
import pandas as pd
import pdfplumber
import pypdf
import pypdfium2 as pdfium
from PIL import Image

from get_old_birkie_data import lines_of
from get_prebirkie_data import COLUMNS, TIME, get
from results_loader import load_all_results, compact, US_STATES, CA_PROVINCES

OUT_DIR = 'old_results'
PDF_DIR = os.path.join(OUT_DIR, 'pdfs')
BIRKIE_URL = 'https://www.birkie.com/'
TEXT_PDFS = {1999: ['Results/1999/Birkie/99bmen.pdf', 'Results/1999/Birkie/99bfem.pdf'],
             2001: ['Results/2001/Birkie/Abmen2001.pdf', 'Results/2001/Birkie/Abfem2001.pdf']}
#and the kortelopet's, laid out the same way
KORTIE_TEXT_PDFS = {1999: ['Results/1999/Korte/99kmen.pdf', 'Results/1999/Korte/99kfem.pdf'],
                    2001: ['Results/2001/Korte/Akmen2001.pdf', 'Results/2001/Korte/Akfem2001.pdf']}
SCANS = {1973: 'wp-content/uploads/2020/05/1973-Results.pdf', 1974: 'wp-content/uploads/2020/05/1974-results.pdf',
         1975: 'wp-content/uploads/2020/05/1975-results.pdf', 1976: 'wp-content/uploads/2020/05/1976-results.pdf',
         1977: 'wp-content/uploads/2020/05/1977-results.pdf', 1979: 'wp-content/uploads/2023/05/1979-results.pdf',
         1995: 'wp-content/uploads/2020/05/1995-Birch-Scroll-s.pdf',
         1996: 'wp-content/uploads/2020/05/1996-Birch-Scroll-s.pdf',
         **{y: 'wp-content/uploads/2020/05/{}-Birch-Scroll.pdf'.format(y)
            for y in [1978] + list(range(1980, 1995)) + [1997, 1998]}}
#page and top: where a scanned result sits in old_results/pages/<year>/<page>.png, in pixels, for checking it by eye
OUT_COLUMNS = COLUMNS + ['tech', 'class_rank', 'page', 'top']
PAGE_DIR = os.path.join(OUT_DIR, 'pages')
OCR_DIR = os.path.join(OUT_DIR, 'ocr')
TESSERACT = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
OCR_WORKERS = 12
RESULT_CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789:.,-'& "


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=['download', 'pages', 'ocr', 'parse'])
    parser.add_argument("--years", type=int, nargs='*')
    args = parser.parse_args()
    years = lambda source: [y for y in sorted(source) if not args.years or y in args.years]

    if args.step == 'download':
        for year, paths in sorted({**TEXT_PDFS, **{y: [p] for y, p in SCANS.items()}}.items()):
            if not args.years or year in args.years:
                for p in paths + KORTIE_TEXT_PDFS.get(year, []):
                    print(year, pdf_path(p))
    elif args.step == 'pages':
        for year in years(SCANS):
            print(year, len(extract_pages(year)), 'pages')
    elif args.step == 'ocr':
        pages = [p for year in years(SCANS) for p in sorted(glob.glob(os.path.join(PAGE_DIR, str(year), '*.png')))]
        with concurrent.futures.ThreadPoolExecutor(OCR_WORKERS) as pool:
            for n, path in enumerate(pool.map(ocr_page, pages), 1):
                if n % 50 == 0:
                    print(n, 'of', len(pages), path)
        #the typeset years' results pages again, at twice the size
        pages = [os.path.join(PAGE_DIR, str(year), '{:03d}.png'.format(p)) for year in years(TYPESET_YEARS)
                 for p in results_pages(year)]
        with concurrent.futures.ThreadPoolExecutor(OCR_WORKERS) as pool:
            for n, path in enumerate(pool.map(functools.partial(ocr_page, scale=2), pages), 1):
                if n % 50 == 0:
                    print(n, 'of', len(pages), 'at twice the size', path)
        #then each year with its own parser reads its results pages again in its own ways
        for year in years(SCANS):
            for module in (year_module(year), year_module(year, 'k')):
                if module and hasattr(module, 'ocr'):
                    print(year, 'own OCR', module.__name__)
                    module.ocr(year)
    elif args.step == 'parse':
        for year, paths in TEXT_PDFS.items():
            if not args.years or year in args.years:
                write(year, pd.concat([division_text(pdf_path(p)) for p in paths], ignore_index=True))
                write(year, pd.concat([division_text(pdf_path(p)) for p in KORTIE_TEXT_PDFS[year]], ignore_index=True),
                      'kortie')
        for year in years(SCANS):
            parser = year_parser(year)
            if parser:
                write(year, parser(year))
            kortie = year_module(year, 'k')
            if kortie:
                write(year, kortie.parse(year), 'kortie')


def pdf_path(url_path):
    #kept after the first download
    path = os.path.join(PDF_DIR, os.path.basename(url_path))
    if not os.path.exists(path):
        os.makedirs(PDF_DIR, exist_ok=True)
        with open(path + '.part', 'wb') as f:
            f.write(get(BIRKIE_URL + url_path))
        os.replace(path + '.part', path)
    return path


#---------------------------------------------------------------- scans

def year_module(year, prefix='y'):
    #a year's own module, old_results_parsers/y<year>.py, when it has one: parse(year) for its results and, for some,
    #ocr(year) for the readings of its pages it needs beyond the plain ones. k<year>.py the same for its kortelopet
    name = 'old_results_parsers.{}{}'.format(prefix, year)
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as e:
        if e.name != name:
            raise
        return None


def year_parser(year):
    #a year's own parser when it has one. otherwise the typeset tables' parser for the 1990s, and nothing for the rest
    module = year_module(year)
    if module:
        return module.parse
    return typeset if year in TYPESET_YEARS else None


def extract_pages(year):
    #each page's scan (the largest image on it) as old_results/pages/<year>/<page>.png, in grayscale. pypdf gets the
    #byte-aligned CCITT scans (most of 1995's and 1996's pages) wrong, leaving them nearly blank, so pdfium decodes those
    out_dir = os.path.join(PAGE_DIR, str(year))
    os.makedirs(out_dir, exist_ok=True)
    pdf = pdfium.PdfDocument(pdf_path(SCANS[year]))
    paths = []
    for n, page in enumerate(pypdf.PdfReader(pdf_path(SCANS[year])).pages, 1):
        path = os.path.join(out_dir, '{:03d}.png'.format(n))
        if not os.path.exists(path):
            if byte_aligned(page):
                objects = [o for o in pdf[n - 1].get_objects() if o.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE]
                largest = max(objects, key=lambda o: o.get_px_size()[0] * o.get_px_size()[1])
                largest.get_bitmap(render=False).to_pil().convert('L').save(path)
            else:
                images = page.images
                if not images:
                    continue
                largest = max(images, key=lambda im: im.image.width * im.image.height)
                Image.open(io.BytesIO(largest.data)).convert('L').save(path)
        paths.append(path)
    return paths


def byte_aligned(page):
    #whether the page's largest image is a byte-aligned CCITT scan, from the pdf's description of it (decoding it with
    #pypdf only prints complaints)
    resources = page.get('/Resources') or {}
    xobjects = resources.get('/XObject') or {}
    images = [x.get_object() for x in xobjects.values() if x.get_object().get('/Subtype') == '/Image']
    if not images:
        return False
    largest = max(images, key=lambda im: im['/Width'] * im['/Height'])
    parms = largest.get('/DecodeParms') or {}
    parms = (parms[0] or {}) if isinstance(parms, list) else parms
    return largest.get('/Filter') == '/CCITTFaxDecode' and bool(parms.get('/EncodedByteAlign'))


def ocr_page(path, scale=1):
    #tesseract's words with their boxes and confidences, as old_results/ocr/<year>/<page>.tsv. a page turned on its
    #side (orientation detection says so with some confidence) is turned upright first. scale 2 is the results pages
    #read again at twice the size, keeping only the characters results use, as <page>_x2.tsv: on the typeset tables
    #that reads about a tenth more of the times cleanly
    year, name = path.split(os.sep)[-2:]
    out = os.path.join(OCR_DIR, year, name.replace('.png', '') + ('_x{}'.format(scale) if scale != 1 else ''))
    if os.path.exists(out + '.tsv'):
        return out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if scale != 1:
        image = Image.open(path)
        image.resize((image.width * scale, image.height * scale), Image.LANCZOS).save(out + '.png')
        subprocess.run([TESSERACT, out + '.png', out, '--psm', '6', '-c', 'tessedit_char_whitelist=' + RESULT_CHARACTERS,
                        'tsv'], capture_output=True)
        os.remove(out + '.png')
        return out
    osd = subprocess.run([TESSERACT, path, 'stdout', '--psm', '0'], capture_output=True).stdout.decode('utf-8', 'replace')
    rotate = re.search(r'Rotate: (\d+)', osd)
    confidence = re.search(r'Orientation confidence: ([\d.]+)', osd)
    if rotate and int(rotate.group(1)) and confidence and float(confidence.group(1)) > 2:
        upright = out + '_upright.png'
        Image.open(path).rotate(-int(rotate.group(1)), expand=True).save(upright)
        path = upright
    subprocess.run([TESSERACT, path, out, '--psm', '6', 'tsv'], capture_output=True)
    return out


def results_pages(year, min_times=20):
    #pages with at least min_times words that look like a finish time
    pages = []
    for path in sorted(glob.glob(os.path.join(OCR_DIR, str(year), '[0-9][0-9][0-9].tsv'))):
        page = int(os.path.basename(path)[:3])
        if ocr_words(year, page, scaled=False)['text'].str.contains(TIME_LIKE).sum() >= min_times:
            pages.append(page)
    return pages


def ocr_words(year, page, scaled=True):
    #one page's OCR words: text, box, confidence and tesseract's line within the page. the page read at twice the size
    #when there is one
    path = os.path.join(OCR_DIR, str(year), '{:03d}'.format(page))
    scale = 2 if scaled and os.path.exists(path + '_x2.tsv') else 1
    words = pd.read_csv(path + ('_x2.tsv' if scale == 2 else '.tsv'), sep='\t', quoting=3, dtype={'text': str},
                        keep_default_na=False)
    #boxes in the page image's pixels, whichever size was read
    words[['left', 'top', 'width', 'height']] = words[['left', 'top', 'width', 'height']] // scale
    return words[(words['level'] == 5) & (words['text'].str.strip() != '')].reset_index(drop=True)


#---------------------------------------------------------------- 1991-1998 typeset tables

TYPESET_YEARS = range(1991, 1999)
#characters OCR reads in place of digits
DIGITS = str.maketrans({'O': '0', 'o': '0', 'D': '0', 'Q': '0', 'I': '1', 'l': '1', '|': '1', '!': '1', 'i': '1',
                        'L': '1', 'S': '5', 's': '5', '$': '5', 'B': '8', 'Z': '2', 'z': '2', 'G': '6', 'g': '9'})
#digits OCR mixes up with each other, for repairing a time that doesn't fit its place
LOOKALIKE = {'3': '8', '8': '3', '5': '6', '6': '5', '0': '9', '9': '0', '1': '7', '7': '1', '4': '1'}
CLASS = re.compile(r'^([MFH])(\d\d)-?(\d\d|UP|\+)$')
NATION = re.compile(r'^[A-Z]{3}$')


def digits(text):
    return re.sub(r'\D', '', str(text).translate(DIGITS))


def read_time(text):
    #'2:37:40.2', or as OCR left it ('-242:51.7', '6:3040.4'): h:mm:ss.t from six digits, minutes and seconds under 60
    d = digits(text)
    if len(d) != 6 or int(d[1:3]) > 59 or int(d[3:5]) > 59:
        return ''
    return '{}:{}:{}.{}'.format(d[0], d[1:3], d[3:5], d[5])


TIME_LIKE = re.compile(r'\d{1,2}[:;.,]?\d\d[:;.,]\d\d')
CLASSIC_MARKS = {'C', 'c', 'G', '(', '©', '€'}


def typeset(year):
    #RANK, FINAL TIME, BIB, NAME, HOMETOWN, ST, NAT, CLASS ("M30-34"), class rank, 25% club, pace, two results to a
    #line. each result is found by its time, with its rank just before it. name and hometown are split at the HOMETOWN
    #heading, measured from the FINAL TIME heading above the same column, or as it sits on the year's other pages. a rank
    #OCR lost is the one above it in the same column plus one. the page title says birkebeiner or kortelopet, and carries
    #over to untitled pages
    rows, race, offsets = [], None, {}
    for path in sorted(glob.glob(os.path.join(OCR_DIR, str(year), '*.tsv'))):
        page = int(os.path.basename(path)[:3])
        words = ocr_words(year, page)
        height, width = words['top'].max(), words['left'].add(words['width']).max()
        title = ' '.join(words.loc[words['top'] < words['top'].min() + 0.12 * height, 'text']).upper()
        race = 'kortie' if 'KORTE' in title else 'birkie' if 'BIRKE' in title else race
        last_place = {}
        for _, line in words.groupby(['block_num', 'par_num', 'line_num']):
            line = line[line['text'].str.contains(r'[0-9A-Za-z]')].sort_values('left')
            if line['text'].str.contains('HOMETOWN').any():
                #each HOMETOWN heading against the nearest TIME heading to its left (FINAL TIME, not the pace's)
                times = line.loc[line['text'].str.contains('TIME'), 'left'].tolist()
                towns = line.loc[line['text'].str.contains('HOMETOWN'), 'left'].tolist()
                for i, town in enumerate(towns):
                    before = [t for t in times if t < town]
                    if before:
                        offsets[i] = town - max(before)
                continue
            for record in typeset_records(line, offsets, known_towns()):
                #the column by where its time sits, since a lost result shifts the ones after it on the line
                column = int(record.pop('x') >= width / 2)
                record['top'] = int(line['top'].min())
                if record['place'] == '' and column in last_place:
                    record['place'] = str(last_place[column] + 1)
                if record['place'].isdigit():
                    last_place[column] = int(record['place'])
                if race:
                    rows.append({**record, 'race': race, 'page': page, 'column': column})
    if not rows:
        return pd.DataFrame(columns=OUT_COLUMNS)
    df = full_lists(pd.DataFrame(rows))
    df = repair_times(df[df['race'] == 'birkie'])
    #a year that marks its classic skiers ("C = CLASSICAL") says the rest skated
    marked = df['classic'].any()
    df['tech'] = np.where(df.pop('classic'), 'classic', 'skate' if marked else '')
    return df.assign(status='finished')


def full_lists(df, min_run=5):
    #the full results count up by one down each column. award lists (1, 2, 3 in each class) and top ten lists restart, so
    #only runs of min_run or more places in a row are kept. a place OCR garbled between two that are two apart is repaired,
    #and a skier listed twice at the same place (a top ten list) is kept once
    keep = []
    for _, g in df.groupby(['page', 'column'], sort=False):
        p = pd.to_numeric(g['place'], errors='coerce').values.copy()
        for i in range(1, len(p) - 1):
            if p[i - 1] + 2 == p[i + 1] and p[i] != p[i - 1] + 1:
                p[i] = p[i - 1] + 1
        step = np.concatenate([[False], np.diff(p) == 1])
        run = np.cumsum(~step)
        size = pd.Series(run).map(pd.Series(run).value_counts()).values
        keep.append(g.assign(place=pd.Series(p, index=g.index).map(lambda v: '' if np.isnan(v) else str(int(v))))
                     [size >= min_run])
    df = pd.concat(keep)
    return df.drop_duplicates(['race', 'gender', 'place', 'name'])


@functools.lru_cache(maxsize=None)
def known_towns():
    #every (town, state) in the clean results, letters only, for telling a hometown from the end of a name
    clean = load_all_results()
    return frozenset(zip(clean['city'].map(compact), clean['state']))


def state_code(text):
    #OCR's 'Wi', 'iL', 'Wl', '1L'
    s = text.upper().replace('1', 'I')
    if s in US_STATES | CA_PROVINCES or not re.fullmatch(r'[A-Z]{2,3}', s.replace('L', 'I')):
        return s
    return s.replace('L', 'I') if s.replace('L', 'I') in US_STATES | CA_PROVINCES else s


def split_name_town(words, edge, state, towns):
    #the longest run at the end that's a known town in that state, leaving at least a first and last name; failing
    #that, the HOMETOWN column's edge
    texts = [w for w, _ in words]
    for k in range(2, len(texts)):
        if (compact(' '.join(texts[k:])), state) in towns:
            return ' '.join(texts[:k]), ' '.join(texts[k:])
    if edge is None:
        return ' '.join(texts), ''
    return ' '.join(w for w, x in words if x < edge), ' '.join(w for w, x in words if x >= edge)


def typeset_records(line, offsets, towns):
    #every result on one OCR line, left to right
    text, left = line['text'].tolist(), line['left'].tolist()
    starts = [i for i, t in enumerate(text) if TIME_LIKE.search(t)]
    out = []
    for n, t in enumerate(starts):
        #a classic skier's C sits between the rank and the time, or runs into the time
        classic = bool(re.match(r'^[Cc]\W*\d', text[t])) or (t > 1 and text[t - 1] in CLASSIC_MARKS)
        r = t - 2 if t > 1 and text[t - 1] in CLASSIC_MARKS else t - 1
        rank = r if r >= 0 and digits(text[r]) and len(digits(text[r])) <= 5 and r not in starts else None
        end = starts[n + 1] - (1 if starts[n + 1] - 1 > t and len(digits(text[starts[n + 1] - 1])) else 0) \
            if n + 1 < len(starts) else len(text)
        fields, x = text[t + 1:end], left[t + 1:end]
        #the class, as one word ("M30-34") or two ("M", "30-34")
        group, cls = None, None
        for i, f in enumerate(fields):
            for candidate in (f, f + (fields[i + 1] if i + 1 < len(fields) else '')):
                m = CLASS.match(candidate.upper().replace('O', '0').replace('S', '5'))
                if m and i > 1:
                    group, cls, width = i, m, 1 + (candidate != f)
                    break
            if group is not None:
                break
        if group is None or len(fields) < 4:
            continue
        nation = group - 1 if NATION.match(fields[group - 1].upper()[-3:]) else None
        state = nation - 1 if nation and re.fullmatch(r'[A-Za-z]{2,3}', fields[nation - 1]) else None
        middle = list(zip(fields, x))[1:state or nation or group]
        offset = offsets.get(n, np.median(list(offsets.values())) if offsets else None)
        edge = left[t] + offset - 10 if offset is not None else None
        gender = 'M' if cls.group(1) in 'MH' else 'F'
        after = fields[group + width:]
        st = state_code(fields[state]) if state else ''
        name, town = split_name_town(middle, edge, st, towns)
        out.append({'x': left[t], 'classic': classic,
                    'place': digits(text[rank]) if rank is not None else '', 'time': read_time(text[t]),
                    'time_raw': text[t], 'bib': digits(fields[0]), 'name': name, 'city': town,
                    'state': st, 'country': fields[nation].upper()[-3:] if nation else '',
                    'gender': gender, 'age_group': '{} {}-{}'.format(gender, cls.group(2), cls.group(3)),
                    'class_rank': digits(after[0])[:4] if after else ''})
    return out


def repair_times(df):
    #a time that couldn't be read, or doesn't fit between the times placed just before and after it, gets each one
    #digit lookalike swap tried. it's repaired only when exactly one fits
    out = []
    for _, lst in df.groupby('gender'):
        lst = lst.assign(place_n=pd.to_numeric(lst['place'], errors='coerce')).sort_values('place_n')
        secs = lst['time'].map(lambda t: parse_seconds(t)).values
        for i in range(len(lst)):
            prev = np.nanmax(secs[:i]) if i and np.isfinite(secs[:i]).any() else 0
            nxt = np.nanmin(secs[i + 1:]) if i + 1 < len(secs) and np.isfinite(secs[i + 1:]).any() else np.inf
            if np.isfinite(secs[i]) and prev <= secs[i] <= nxt:
                continue
            d = digits(lst['time_raw'].iloc[i])
            #one digit swapped for a lookalike, or a stray character read as an extra digit at either end
            candidates = [d[:j] + LOOKALIKE[c] + d[j + 1:] for j, c in enumerate(d) if c in LOOKALIKE]
            candidates += [d[1:], d[:-1]] if len(d) == 7 else []
            fits = set()
            for c in candidates:
                t = read_time(c)
                if t and prev <= parse_seconds(t) <= nxt:
                    fits.add(t)
            if len(fits) == 1:
                lst.iloc[i, lst.columns.get_loc('time')] = fits.pop()
                secs[i] = parse_seconds(lst['time'].iloc[i])
        out.append(lst.drop(columns='place_n'))
    return pd.concat(out, ignore_index=True) if out else df


def parse_seconds(t):
    if not t:
        return np.nan
    h, m, s = t.split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def write(year, results, race='birkie'):
    os.makedirs(os.path.join(OUT_DIR, str(year)), exist_ok=True)
    path = os.path.join(OUT_DIR, str(year), '{} {}.csv'.format(race, year))
    results.reindex(columns=OUT_COLUMNS).to_csv(path, index=False)
    print('{}: {} results ({} men, {} women)'.format(path, len(results), (results['gender'] == 'M').sum(),
                                                     (results['gender'] == 'F').sum()))


#---------------------------------------------------------------- 1999, 2001 text pdfs

def division_text(path):
    #RANK, TIME, BIB, NAME, HOMETOWN, STATE, NATION, CLASS ("M 25-29"), class rank, 25% club and (2001) pace. the
    #columns come from the header line, which only the first page has
    rows = []
    edges = None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            lines = lines_of(page)
            header = next((l for l in lines if any(w['text'] == 'HOMETOWN' for w in l)), None)
            if header is not None:
                cols = {w['text']: w['x0'] for w in header}
                #nation codes start a little left of their header
                edges = [('name', cols['NAME'] - 3), ('city', cols['HOMETOWN'] - 3), ('state', cols['STATE'] - 5),
                         ('country', (cols['STATE'] + cols['NATION']) / 2), ('class', cols['CLASS'] - 8)]
            if edges is None:
                continue
            for words in lines:
                text = [w['text'] for w in words]
                t = next((i for i, x in enumerate(text) if TIME.match(x)), None)
                if t is None or t == 0 or not text[0].isdigit() or t + 2 >= len(text):
                    continue
                fields = {k: [] for k, _ in edges}
                for w in words[t + 2:]:
                    fields[[k for k, x in edges if w['x0'] >= x][-1]].append(w['text'])
                group = fields['class']
                rows.append({'place': text[0], 'time': text[t], 'bib': text[t + 1], 'name': ' '.join(fields['name']),
                             'city': ' '.join(fields['city']), 'state': ' '.join(fields['state']),
                             'country': ' '.join(fields['country']),
                             'gender': group[0] if group and group[0] in ('M', 'F') else '',
                             'age_group': ' '.join(group[:2]) if len(group) > 1 else '',
                             'class_rank': group[2] if len(group) > 2 and group[2].isdigit() else ''})
    return pd.DataFrame(rows).assign(status='finished', tech='')


if __name__ == '__main__':
    main()
