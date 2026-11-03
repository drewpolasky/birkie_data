#download the hayward lions pre-birkie results into yearly_data/<year>/, as 'prebirkie <tech> <year>.csv' for the long
#race (42 km, 46 km in 2019) and 'prebirkie_short <tech> <year>.csv' for the short one (26 km, 24 km in 2019).
#the pre-birkie is on the birkie trail about two weeks before the birkie, so it's another race day on the same trail.
#the results are spread over four timing sites:
#   2009-2011: white river sports timing pdfs, from the internet archive since itiming.com is gone. 42 and 26 km
#              with no technique split, written as skate
#   2015-2020: chronotrack
#   2021:      runsignup (held march 6, after that year's birkie)
#   2022+:     raceresult (primetime timing)
#no full results turned up for 2012-2014 or 2016 (2014 only has award winners), and 2024 and 2025 weren't held.
#the course has moved: through at least 2011 it ran north from lake hayward towards OO ("hayward to OO"), by 2015 it
#started and finished at birkie ridge with the long race going south to the gravel pit, and since 2022 it goes out and
#back from birkie ridge, south to OO and then north up the classic trail (prebirkie.com, new moon ski shop blog 2022)
#every file is written in one plain format (COLUMNS), read by results_loader.load_prebirkie
#
#example usage:
#python get_prebirkie_data.py                 every year
#python get_prebirkie_data.py --years 2023    one year
import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd
import pdfplumber

OUT_DIR = 'yearly_data'
COLUMNS = ['place', 'bib', 'name', 'first', 'last', 'gender', 'age', 'age_group', 'city', 'state', 'country', 'time',
           'status']
SOURCES = {2009: ('itiming', 'http://www.itiming.com:80/raceresults/479-prebirkie09_div.pdf', '20090424012736'),
           2010: ('itiming', 'http://itiming.com/raceresults/600-pre-birkie-ovl10.pdf', '20101009215413'),
           2011: ('itiming', 'http://itiming.com/raceresults/703-prebirkie11_ovl.pdf', '20110419202348'),
           2015: ('chronotrack', 10729), 2017: ('chronotrack', 26134), 2018: ('chronotrack', 34719),
           2019: ('chronotrack', 46677), 2020: ('chronotrack', 55433),
           2021: ('runsignup', 102024),
           2022: ('raceresult', 191949), 2023: ('raceresult', 233524), 2026: ('raceresult', 382262)}
LONG_KM = 35                    #the long race is 42 or 46 km, the short one 24 or 26
WAYBACK_URL = 'https://web.archive.org/web/{stamp}id_/{url}'
PDF_DIR = 'prebirkie_pdfs'
CHRONOTRACK_URL = 'https://results.chronotrack.com/embed/results/'
RUNSIGNUP_URL = 'https://runsignup.com/Rest/race/{race}'
RACERESULT_URL = 'https://my.raceresult.com/{event}/RRPublish/data/'
PAGE_SIZE = 500


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, nargs='*', default=sorted(SOURCES))
    parser.add_argument("--out", type=str, default=OUT_DIR)
    args = parser.parse_args()

    readers = {'itiming': itiming, 'chronotrack': chronotrack, 'runsignup': runsignup, 'raceresult': raceresult}
    for year in args.years:
        source, *where = SOURCES[year]
        results = readers[source](year, *where)
        os.makedirs(os.path.join(args.out, str(year)), exist_ok=True)
        for (race, tech), rows in results.groupby(['race', 'tech']):
            path = os.path.join(args.out, str(year), '{} {} {}.csv'.format(race, tech, year))
            rows = rows.assign(place=pd.to_numeric(rows['place'], errors='coerce').astype('Int64'))
            rows.reindex(columns=COLUMNS).to_csv(path, index=False)
            print('{}: {} results, {} finished'.format(path, len(rows), (rows['status'] == 'finished').sum()))


def race_name(event):
    #'42 km Freestyle', '26k Classic', '42K Men/Women Classic' -> ('prebirkie', 'classic')
    km = int(re.search(r'(\d+)\s*k', event, re.IGNORECASE).group(1))
    return 'prebirkie' if km > LONG_KM else 'prebirkie_short', 'classic' if 'classic' in event.lower() else 'skate'


def city_state(hometown):
    #'Minneapolis, MN' -> ('Minneapolis', 'MN')
    city, _, state = (hometown or '').rpartition(',')
    return (city.strip(), state.strip()) if city else (state.strip(), '')


def get(url, tries=5):
    #the internet archive turns away quick repeat requests (429), so wait and try again
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
            time.sleep(15 * 2 ** attempt)


#---------------------------------------------------------------- 2009-2011 white river sports pdfs

TIME = re.compile(r'^\d{1,2}:\d{2}:\d{2}(\.\d+)?$')

def itiming(year, url, stamp):
    #every result is one line of words. the words are placed by position: name and hometown are separated by the
    #hometown column's left edge, and the division ("Male 26 km", or "M 40-44" in the 2009 division list) by its words
    rows = []
    km = None
    #kept after the first download, since the archive is slow and turns away repeat requests
    path = os.path.join(PDF_DIR, os.path.basename(url))
    if not os.path.exists(path):
        os.makedirs(PDF_DIR, exist_ok=True)
        with open(path, 'wb') as f:
            f.write(get(WAYBACK_URL.format(stamp=stamp, url=url)))
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            lines = {}
            page_words = page.extract_words()
            for w in page_words:
                lines.setdefault(round(w['top']), []).append(w)
            city_x = min((w['x0'] for w in page_words if w['text'] == 'City,'), default=None)
            for top in sorted(lines):
                words = sorted(lines[top], key=lambda w: w['x0'])
                text = [w['text'] for w in words]
                times = [i for i, t in enumerate(text) if TIME.match(t)]
                if not times:
                    #event headers carry the distance for the division list
                    m = re.search(r'(\d+) km', ' '.join(text))
                    km = int(m.group(1)) if m else km
                    continue
                row = itiming_row(words, text, times[0], city_x, km)
                if row:
                    rows.append(row)
    df = pd.DataFrame(rows)
    df['race'] = ['prebirkie' if k > LONG_KM else 'prebirkie_short' for k in df.pop('km')]
    df['tech'] = 'skate'
    df['status'] = 'finished'
    #the division list has no overall place
    df['place'] = pd.to_numeric(df['place']).fillna(df.groupby('race')['time'].rank(method='min'))
    return df


def itiming_row(words, text, t, city_x, km):
    #division: 'Male 26 km' then the age, or 'M 40-44'. a line with a time but no division is the page footer
    g = next((i for i, x in enumerate(text[:t]) if x in ('Male', 'Female', 'M', 'F') and i > 0
              and (re.fullmatch(r'\d+-\d+', text[i + 1]) or text[i + 2:i + 3] == ['km'])), None)
    if g is None:
        return None
    row = {'gender': text[g][0], 'time': text[t], 'km': km, 'age': None, 'age_group': None, 'place': None}
    if text[g + 2:g + 3] == ['km']:
        row['km'] = int(text[g + 1])
        row['age'] = text[g + 3] if g + 3 < t else None
        row['place'] = text[0]          #the overall list starts with overall / division / age place
    else:
        row['age_group'] = text[g] + ' ' + text[g + 1]
    #the numbers before the name are places, then the bib
    first_word = next(i for i, x in enumerate(text) if not x.isdigit())
    row['bib'] = text[first_word - 1]
    name = [w['text'] for w in words[first_word:g] if city_x is None or w['x0'] < city_x - 5]
    town = [w['text'] for w in words[first_word:g] if city_x is not None and w['x0'] >= city_x - 5]
    row['name'] = ' '.join(name)
    row['last'], _, row['first'] = [p.strip() for p in row['name'].partition(',')]
    row['city'], row['state'] = city_state(' '.join(town))
    return row


#---------------------------------------------------------------- 2015-2020 chronotrack

def jsonp(url):
    text = get(url).decode('utf-8')
    return json.loads(text[text.index('(') + 1:text.rindex(')')])


def chronotrack(year, event):
    model = jsonp(CHRONOTRACK_URL + 'load-model?modelID=event&eventID={}'.format(event))['model']
    frames = []
    for race in model['races'].values():
        interval = next(i['id'] for i in race['intervals'] if i['is_full'] == '1')
        rows, start = [], 0
        while True:
            grid = jsonp(CHRONOTRACK_URL + 'results-grid?' + urllib.parse.urlencode(
                {'eventID': event, 'raceID': race['id'], 'bracketID': race['default_bracket_id'],
                 'intervalID': interval, 'iDisplayStart': start, 'iDisplayLength': PAGE_SIZE}))
            rows += grid['aaData']
            start += PAGE_SIZE
            if start >= int(grid['iTotalDisplayRecords']):
                break
        #entry id, place, name, bib, time, pace, hometown, age, gender, division, division place
        df = pd.DataFrame([r[:10] for r in rows], columns=['entry', 'place', 'name', 'bib', 'time', 'pace', 'hometown',
                                                           'age', 'gender', 'age_group'])
        df['city'], df['state'] = zip(*df['hometown'].map(city_state)) if len(df) else ([], [])
        df['race'], df['tech'] = race_name(race['name'])
        df['status'] = ['finished' if re.fullmatch(r'\d+', str(p)) and TIME.match(str(t)) else 'DNF'
                        for p, t in zip(df['place'], df['time'])]
        frames.append(df)
    return pd.concat(frames, ignore_index=True).reindex(columns=COLUMNS + ['race', 'tech'])


#---------------------------------------------------------------- 2021 runsignup

def runsignup(year, race):
    info = json.loads(get(RUNSIGNUP_URL.format(race=race) + '?format=json&future_events_only=F'
                          '&most_recent_events_only=F'))['race']
    frames = []
    for event in info['events']:
        if not event['start_time'].split()[0].endswith(str(year)):
            continue
        rows, page = [], 1
        while True:
            data = json.loads(get(RUNSIGNUP_URL.format(race=race) + '/results/get-results?' + urllib.parse.urlencode(
                {'format': 'json', 'event_id': event['event_id'], 'results_per_page': PAGE_SIZE, 'page': page})))
            batch = [r for s in data['individual_results_sets'] for r in s['results']]
            rows += batch
            if len(batch) < PAGE_SIZE:
                break
            page += 1
        df = pd.DataFrame(rows).rename(columns={'first_name': 'first', 'last_name': 'last', 'country_code': 'country',
                                                'chip_time': 'time'})
        df['name'] = df['first'].str.strip() + ' ' + df['last'].str.strip()
        df['race'], df['tech'] = race_name(event['name'])
        df['status'] = ['finished' if pd.notna(p) and isinstance(t, str) and TIME.match(t) else 'DNF'
                        for p, t in zip(df['place'], df['time'])]
        frames.append(df)
    return pd.concat(frames, ignore_index=True).reindex(columns=COLUMNS + ['race', 'tech'])


#---------------------------------------------------------------- 2022+ raceresult

def raceresult(year, event):
    base = RACERESULT_URL.format(event=event)
    config = json.loads(get(base + 'config?page=results&noVisitor=1'))
    lists = [l for l in config['lists'] if l['Name'].startswith('Result Lists|Overall')]
    #one overall list for each contest, or one list for all of them (contest 0) with a group for each contest
    chosen = {l['Contest']: l for l in lists if l['Contest'] in config['contests']}
    if len(chosen) < len(config['contests']):
        chosen = {'0': next(l for l in lists if l['Contest'] == '0')}
    frames = []
    for contest, chosen_list in chosen.items():
        data = json.loads(get(base + 'list?' + urllib.parse.urlencode(
            {'key': config['key'], 'listname': chosen_list['Name'], 'page': 'results', 'contest': contest, 'r': 'all',
             'l': 0})))
        groups = data['data'] if isinstance(data['data'], dict) else {config['contests'][contest]: data['data']}
        for group, rows in groups.items():
            #'#1_42K Skate'
            df = pd.DataFrame(list(flatten(rows)), columns=data['DataFields'])
            df = df.rename(columns={'BIB': 'bib', 'WithStatus([OverallRank.p])': 'place', 'DisplayName': 'name',
                                    'AGE': 'age', 'GenderMF': 'gender', 'AGEGROUP.NAME': 'age_group',
                                    'Finish.CHIP': 'time'})
            df['last'], df['first'] = zip(*df['name'].map(lambda n: [p.strip() for p in n.partition(',')[::2]]))
            df['city'], df['state'] = zip(*df['CityState'].map(city_state))
            df['race'], df['tech'] = race_name(group.split('_', 1)[-1])
            place = df['place'].str.strip(' .')
            df['status'] = ['finished' if p.isdigit() and TIME.match(t or '') else p or 'DNF'
                            for p, t in zip(place, df['time'])]
            df['place'] = pd.to_numeric(place, errors='coerce')
            frames.append(df)
    return pd.concat(frames, ignore_index=True).reindex(columns=COLUMNS + ['race', 'tech'])


def flatten(data):
    #raceresult nests its rows in groups ('#1_42K Skate', and sometimes by gender inside that)
    if isinstance(data, dict):
        for value in data.values():
            yield from flatten(value)
    elif data and isinstance(data[0], (list, dict)):
        for value in data:
            yield from flatten(value)
    elif data:
        yield data


if __name__ == '__main__':
    main()
