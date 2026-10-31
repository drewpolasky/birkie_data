#download the birkie's results from before 2009 into yearly_data/<year>/ as 'birkie <tech> <year>.csv':
#   2002-2005: results pdfs on birkie.com (white river sports timing for 2002-2004, finish line sports for 2005)
#   2006:      one results pdf on birkie.com, two columns a page, with classic skiers printed in blue
#   2008:      the old searchable results site (results.birkie.com), which 2009-2015 also came from, written in the same
#              format as those years. it has no ages, and gender comes from the places as it does for 2009-2015
#before 2008 classic and skate skiers raced one 51 km race (46.7 km in 2002), with classic as its own division. 2008
#was the first separate classic race (53 km), and 2007 was cut to 25 km for skate only, so it isn't here.
#2002-2006 are written in the plain format results_loader reads for the pre-birkie. the pdfs are kept in birkie_pdfs/
#
#example usage:
#python get_old_birkie_data.py                 every year
#python get_old_birkie_data.py --years 2006    one year
import argparse
import os
import re
import time

import pandas as pd
import pdfplumber

from get_prebirkie_data import COLUMNS, TIME, get

OUT_DIR = 'yearly_data'
PDF_DIR = 'birkie_pdfs'
BIRKIE_URL = 'https://www.birkie.com/'
SEARCH_URL = 'https://results.birkie.com/index.php?page_number={page}&event_id={event}&test=1'
SOURCES = {2002: ('division_list', ['Results/2002/Birkie/birkie_m_gender.pdf', 'Results/2002/Birkie/birkie_f_gender.pdf']),
           2003: ('division_list', ['Results/2003/Birkie/b_m_gender_03.pdf', 'Results/2003/Birkie/b_f_gender_03.pdf']),
           2004: ('division_list', ['Results/2004/Birkie/b_m_gender_04.pdf', 'Results/2004/Birkie/b_f_gender_04.pdf']),
           2005: ('division_list', ['Results/2005/Birkie/birkie_overall_05.pdf']),
           2006: ('two_column', ['wp-content/uploads/2025/02/2006-RESULTS-ONLY-002.pdf']),
           2008: ('searchable', {'skate': 30, 'classic': 20})}
LEGACY_HEADER = 'Name, Overall Place, Gender Place, Division Place, Finish Time, Bib Number, City, State \n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, nargs='*', default=sorted(SOURCES))
    parser.add_argument("--out", type=str, default=OUT_DIR)
    args = parser.parse_args()

    for year in args.years:
        source, where = SOURCES[year]
        os.makedirs(os.path.join(args.out, str(year)), exist_ok=True)
        if source == 'searchable':
            for tech, event in where.items():
                write_legacy(searchable(event), os.path.join(args.out, str(year), 'birkie {} {}.csv'.format(tech, year)))
            continue
        reader = {'division_list': division_list, 'two_column': two_column}[source]
        results = pd.concat([reader(pdf_path(p)) for p in where], ignore_index=True)
        results['status'] = 'finished'
        for tech, rows in results.groupby('tech'):
            #overall place among this technique's finishers, by time
            rows = rows.assign(place=rows['time'].map(seconds).rank(method='min').astype(int))
            path = os.path.join(args.out, str(year), 'birkie {} {}.csv'.format(tech, year))
            rows.sort_values('place').reindex(columns=COLUMNS).to_csv(path, index=False)
            print('{}: {} finishers ({} men, {} women)'.format(path, len(rows), (rows['gender'] == 'M').sum(),
                                                               (rows['gender'] == 'F').sum()))


def pdf_path(url_path):
    #kept after the first download
    path = os.path.join(PDF_DIR, os.path.basename(url_path))
    if not os.path.exists(path):
        os.makedirs(PDF_DIR, exist_ok=True)
        with open(path, 'wb') as f:
            f.write(get(BIRKIE_URL + url_path))
    return path


def seconds(t):
    parts = [float(p) for p in t.split(':')]
    return sum(p * 60 ** i for i, p in enumerate(reversed(parts)))


def hometown(words):
    #'Moena Tn, , ITA', 'Boulder, CO, USA', and with the city left out, 'MI, USA'
    parts = [p.strip() for p in ' '.join(words).split(',')]
    if len(parts) == 2 and re.fullmatch(r'[A-Za-z]{3}', parts[1]):
        parts = [''] + parts if re.fullmatch(r'[A-Z]{2}', parts[0]) else [parts[0], ''] + parts[1:]
    parts += [''] * (3 - len(parts))
    return {'city': parts[0], 'state': parts[1], 'country': parts[-1]}


def lines_of(page, **kwargs):
    #the words on a page grouped into lines, each sorted left to right
    lines = {}
    for w in page.extract_words(**kwargs):
        lines.setdefault(round(w['top']), []).append(w)
    return [sorted(lines[top], key=lambda w: w['x0']) for top in sorted(lines)]


#---------------------------------------------------------------- 2002-2005 division lists

DIVISION = re.compile(r"^(Men|Women)\W?s$")

def division_list(path):
    #one result a line: places, bib, "Last, First", "City, State, Nation", division ("Men's Birkebeiner", "Men's
    #Classic", "Women's Freestyle"), age, time, pace. name and hometown are split by the hometown column's left edge
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            city_x = min((w['x0'] for w in page.extract_words() if w['text'] == 'City,'), default=None)
            for words in lines_of(page):
                text = [w['text'] for w in words]
                t = next((i for i, x in enumerate(text) if TIME.match(x)), None)
                if t is None or city_x is None or not text[0].isdigit():
                    continue
                g = next((i for i, x in enumerate(text[:t]) if DIVISION.match(x)), None)
                end = g if g is not None else t
                age = text[t - 1] if t - 1 > (g if g is not None else 0) and text[t - 1].isdigit() else ''
                division = ' '.join(text[g:t - 1 if age else t]) if g is not None else ''
                first_word = next(i for i, x in enumerate(text) if not x.isdigit())
                town = [w for w in words[first_word:end] if w['x0'] >= city_x - 5 and w['text'] != age]
                name = ' '.join(w['text'] for w in words[first_word:end] if w['x0'] < city_x - 5)
                last, _, first = [p.strip() for p in name.partition(',')]
                rows.append({'places': [int(x) for x in text[:first_word - 1]], 'bib': text[first_word - 1],
                             'name': name, 'first': first, 'last': last, 'age': age, 'time': text[t],
                             'gender': ('F' if text[g].startswith('Women') else 'M') if division else '',
                             'tech': ('classic' if 'Classic' in division else 'skate') if division else '',
                             **hometown([w['text'] for w in town])})
    return blank_divisions(pd.DataFrame(rows))


def blank_divisions(df):
    #2002 and 2003 leave the division blank for some of the classic skiers. walking down the list in place order, each
    #division's places count up on their own, so a blank one belongs to whichever division its place continues
    counts = {'skate': 0, 'classic': 0}
    gender = df.loc[df['gender'] != '', 'gender'].mode()[0]     #each list is one gender
    for i in df.index[df['places'].str.len() >= 2][df.loc[df['places'].str.len() >= 2, 'places'].str[0].argsort()]:
        div_place = df.at[i, 'places'][1]
        if not df.at[i, 'tech']:
            df.at[i, 'tech'] = min(counts, key=lambda k: abs(div_place - (counts[k] + 1)))
            df.at[i, 'gender'] = gender
        counts[df.at[i, 'tech']] = max(counts[df.at[i, 'tech']], div_place)
    return df[df['tech'] != ''].drop(columns='places')


#---------------------------------------------------------------- 2006 two columns a page

TIME_IN = re.compile(r'(\d{2}:\d{2}:\d{2}\.\d)')

def two_column(path):
    #RK, TIME, BIB, NAME, HOMETOWN, ST, CO, CLASS ("M 30-34"), class rank, 25% club, pace, in each half of the page.
    #classic skiers are printed in blue, with a Y in the CL column that runs into the time ("1045Y03:23:19.8").
    #the kortelopet starts partway down the last women's page and fills the pages after
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            lines = lines_of(page, extra_attrs=['non_stroking_color'])
            if not any('BIRKEBEINER' in w['text'] for w in lines[0]):
                continue
            korte = next((i for i, l in enumerate(lines) if any('KORTELOPET' in w['text'] for w in l)), len(lines))
            lines = lines[:korte]
            header = next(l for l in lines if any(w['text'] == 'HOMETOWN' for w in l))
            middle = page.width / 2
            for half in (lambda x: x < middle, lambda x: x >= middle):
                cols = {w['text']: w['x0'] - 3 for w in header if half(w['x0'])}
                for line in lines:
                    words = [w for w in line if half(w['x0'])]
                    row = two_column_row(words, cols)
                    if row:
                        rows.append(row)
    return pd.DataFrame(rows)


def two_column_row(words, cols):
    t = next((i for i, w in enumerate(words) if TIME_IN.search(w['text'])), None)
    if t is None or t + 1 >= len(words):
        return None
    before = ' '.join(w['text'] for w in words[:t]) + TIME_IN.split(words[t]['text'])[0]
    color = words[t]['non_stroking_color']
    blue = bool(color) and len(color) == 4 and color[0] > 0.5
    between = lambda lo, hi: [w['text'] for w in words[t + 2:] if cols[lo] <= w['x0'] < cols[hi]]
    name = ' '.join(between('NAME', 'HOMETOWN'))
    group = [w['text'] for w in words if w['x0'] >= cols['CLASS']][:2]
    if len(group) < 2 or group[0] not in ('M', 'F'):
        return None
    last, _, first = [p.strip() for p in name.partition(',')]
    return {'bib': words[t + 1]['text'], 'name': name, 'first': first, 'last': last, 'gender': group[0],
            'age_group': ' '.join(group), 'time': TIME_IN.search(words[t]['text']).group(1),
            'tech': 'classic' if blue or 'Y' in before else 'skate', 'city': ' '.join(between('HOMETOWN', 'ST')),
            'state': ' '.join(between('ST', 'CO')), 'country': ' '.join(between('CO', 'CLASS'))}


#---------------------------------------------------------------- 2008 searchable results

def searchable(event):
    #100 results a page: overall, gender and age group place, bib, name, "City, ST USA", time
    rows, page = [], 1
    while True:
        html = get(SEARCH_URL.format(page=page, event=event)).decode('utf-8', errors='replace')
        found = re.findall(r'<tr[^>]*class="dataRow".*?</tr>', html, re.S)
        for block in found:
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<td[^>]*>(.*?)</td>', block, re.S)]
            rows.append(cells[:7])
        total = int(re.search(r'Records \d+ to (\d+) of (\d+)', html).group(2))
        if not found or len(rows) >= total:
            return rows
        page += 1
        time.sleep(1)


def write_legacy(rows, path):
    #the 2009-2015 files' format: no quoting, read back by anchoring on the time
    with open(path, 'w', encoding='utf-8') as f:
        f.write(LEGACY_HEADER)
        for overall, gender_place, division_place, bib, name, town, finish in rows:
            f.write('{}, {}, {}, {}, {}, {}, {} \n'.format(name, overall, gender_place, division_place, finish, bib, town))
    print('{}: {} finishers'.format(path, len(rows)))


if __name__ == '__main__':
    main()
