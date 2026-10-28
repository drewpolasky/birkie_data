#load every results file in yearly_data/ into one standardized table, one row per finisher
#the results site (and scraper) changed several times, so there are four file formats:
#   2009-2020: hand written csv "Name, Overall Place, Gender Place, Division Place, Finish Time, Bib Number, City, State"
#              2016-2020 division place also carries gender and age group ("34 M 35-39")
#              2020 names have the space between first and last name dropped ("KnuteSands")
#   2021:      runsignup export, split up by race day because of COVID, exact age and gender
#   2022-2026: raceresult export, names are "Last, First", exact age and gender
import functools
import glob
import os
import re
import unicodedata

import numpy as np
import pandas as pd

#standardized columns, in output order
COLUMNS = ['year', 'race', 'tech', 'variant', 'name', 'first', 'middle', 'last', 'suffix',
           'gender', 'age', 'age_min', 'age_max', 'city', 'state', 'country',
           'bib', 'overall_place', 'gender_place', 'time_s', 'status', 'source_file']

US_STATES = {'AL','AK','AZ','AR','CA','CO','CT','DE','DC','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD','MA',
             'MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX',
             'UT','VT','VA','WA','WV','WI','WY','PR','VI','GU'}
CA_PROVINCES = {'AB','BC','MB','NB','NL','NS','NT','NU','ON','PE','QC','SK','YT'}
COUNTRY_ALIASES = {'USA':'USA', 'US':'USA', 'UNITED STATES':'USA', 'CAN':'CAN', 'CA':'CAN', 'CANADA':'CAN',
                   'NOR':'NOR', 'NO':'NOR', 'NORWAY':'NOR', 'SWE':'SWE', 'SE':'SWE', 'FIN':'FIN', 'FI':'FIN',
                   'FRA':'FRA', 'FR':'FRA', 'FRANCE':'FRA', 'ITA':'ITA', 'IT':'ITA', 'GER':'GER', 'DEU':'GER', 'DE':'GER',
                   'SUI':'SUI', 'CHE':'SUI', 'CH':'SUI', 'AUT':'AUT', 'AT':'AUT', 'AUS':'AUS', 'AU':'AUS',
                   'CZE':'CZE', 'CZ':'CZE', 'EST':'EST', 'RUS':'RUS', 'JPN':'JPN', 'GBR':'GBR', 'UK':'GBR', 'NZL':'NZL',
                   'DEN':'DEN', 'DNK':'DEN', 'DK':'DEN', 'NED':'NED', 'NLD':'NED', 'POL':'POL', 'SLO':'SLO', 'SVN':'SLO'}
PROVINCE_NAMES = {'ALBERTA':'AB', 'BRITISH COLUMBIA':'BC', 'MANITOBA':'MB', 'ONTARIO':'ON', 'QUEBEC':'QC', 'QB':'QC',
                  'SASKATCHEWAN':'SK', 'SASKATCHEW':'SK', 'NOVA SCOTIA':'NS', 'NEW BRUNSWICK':'NB'}
SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv'}


def load_all_results(path='yearly_data/'):
    frames = []
    for f in sorted(glob.glob(os.path.join(path, '*', '*.csv'))):
        frame = load_file(f)
        if frame is not None and len(frame) > 0:
            frames.append(frame)
    results = pd.concat(frames, ignore_index=True)
    fix_squashed_names(results)
    results = results[COLUMNS]
    results = results[results['last'] != ''].reset_index(drop=True)
    return results


def parse_filename(filename):
    #'birkie skate openTrack 2024.csv' -> ('birkie', 'skate', 'openTrack', 2024)
    #'prince haakon 2012.csv' -> ('haakon', 'skate', 'main', 2012), the early haakon was a freestyle race
    words = os.path.splitext(os.path.basename(filename))[0].split()
    year = int([w for w in words if re.fullmatch(r'\d{4}', w)][0])
    race = 'haakon' if 'haakon' in words else words[0]
    tech = 'classic' if 'classic' in words else 'skate'
    extra = [w for w in words if w not in ('prince', 'haakon', 'birkie', 'kortie', 'skate', 'classic', 'freestyle', str(year))]
    variant = ' '.join(extra) if extra else 'main'
    return race, tech, variant, year


def load_file(filename):
    race, tech, variant, year = parse_filename(filename)
    if year <= 2020:
        df = load_legacy(filename, year)
    elif year == 2021:
        df = load_runsignup(filename)
    else:
        df = load_raceresult(filename)
    df['year'] = year
    df['race'] = race
    df['tech'] = tech
    df['variant'] = variant
    df['source_file'] = os.path.relpath(filename).replace('\\', '/')
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    return df


#---------------------------------------------------------------- legacy 2009-2020

def load_legacy(filename, year):
    #these files were written without quoting, so a comma inside a name or city shifts the columns.
    #anchor on the finish time field instead of trusting the column count
    rows = []
    with open(filename, encoding='utf-8', errors='replace') as f:
        next(f)
        for line in f:
            fields = [x.strip() for x in line.rstrip('\r\n').split(',')]
            time_idx = [i for i, x in enumerate(fields) if re.fullmatch(r'\d{1,2}:\d{2}:\d{2}(\.\d+)?', x)]
            if not time_idx or time_idx[0] < 4:
                continue
            t = time_idx[0]
            rows.append({'name_raw': ','.join(fields[:t-3]),
                         'overall_place': fields[t-3], 'gender_place': fields[t-2], 'division': fields[t-1],
                         'time_raw': fields[t], 'bib': fields[t+1] if len(fields) > t+1 else '',
                         'location_raw': ','.join(fields[t+2:])})
    df = pd.DataFrame(rows)
    df['overall_place'] = pd.to_numeric(df['overall_place'], errors='coerce')
    df['gender_place'] = pd.to_numeric(df['gender_place'], errors='coerce')
    df['bib'] = pd.to_numeric(df['bib'], errors='coerce')
    df['time_s'] = df['time_raw'].map(parse_time)
    df['status'] = 'finished'           #only finishers were listed

    #2020 names are squashed together ("KnuteSands"), those get split in fix_squashed_names once every year is loaded
    names = df['name_raw'].map(split_first_last)
    df = pd.concat([df, pd.DataFrame(names.tolist(), columns=['first', 'middle', 'last', 'suffix'])], axis=1)
    df['name'] = df['name_raw'].map(clean_whitespace)
    df['squashed'] = year == 2020

    #2016+ division field looks like "34 M 35-39", earlier years are only a number
    div = df['division'].str.extract(r'^\s*\d*\s*([MF])\s+(\d+)\s*-\s*(\d+)')
    df['gender'] = div[0]
    df['age_min'] = pd.to_numeric(div[1], errors='coerce')
    df['age_max'] = pd.to_numeric(div[2], errors='coerce')
    #open ended or catch-all divisions ("M 0-99", "M 18-24" for juniors is fine) carry no age information
    wide = (df['age_max'] - df['age_min']) > 10
    df.loc[wide, ['age_min', 'age_max']] = np.nan
    #no division before 2016, and the elite waves have a blank one after that
    df['gender'] = df['gender'].fillna(infer_gender_from_places(df))

    locs = df['location_raw'].map(lambda x: parse_legacy_location(x, year))
    df = pd.concat([df, pd.DataFrame(locs.tolist(), columns=['city', 'state', 'country'])], axis=1)
    return df


def infer_gender_from_places(df):
    #2009-2015 have no gender column, but overall place and gender place together give it away:
    #walking through the field in finishing order, men's and women's gender places count up independently.
    #assign each finisher to whichever count their gender place continues
    order = df.sort_values('overall_place').index
    gender = pd.Series(np.nan, index=df.index, dtype=object)
    counts = {'M': 0, 'F': 0}
    for i in order:
        gp = df.at[i, 'gender_place']
        if pd.isna(gp) or pd.isna(df.at[i, 'overall_place']):
            continue
        gap_m = abs(gp - (counts['M'] + 1))
        gap_f = abs(gp - (counts['F'] + 1))
        if gap_m == gap_f and counts['M'] == counts['F'] == 0:
            g = 'M'                     #the race winner
        elif gap_m == gap_f:
            continue                    #junk data, don't guess
        else:
            g = 'M' if gap_m < gap_f else 'F'
        if min(gap_m, gap_f) > 2:
            continue                    #doesn't continue either count, don't guess
        gender[i] = g
        counts[g] = max(counts[g], gp)
    return gender


@functools.lru_cache(maxsize=None)
def parse_legacy_location(raw, year):
    #2009-2015: "Edina, MN USA"     2016-2019: "Fairbanks  AK USA" (double space)     2020: "Rochester MNUSA"
    raw = raw.replace('"', '').strip(' ,')
    if not raw:
        return ('', '', '')
    if year == 2020:
        m = re.match(r'^(.*?)\s*([A-Z]{2,3})?\s*(USA|Can|CAN|[A-Z][a-z]{2})$', clean_whitespace(raw))
        if m:
            return normalize_location(m.group(1), m.group(2) or '', m.group(3))
        return normalize_location(raw, '', '')
    parts = [p.strip() for p in re.split(r',|\s{2,}', raw)]
    if len(parts) == 1:
        #city missing, e.g. "FRA Fra" or "Fra"
        parts = [''] + parts
    city = parts[0]
    tail = ' '.join(parts[1:]).split()
    country = tail[-1] if tail else ''
    state = tail[-2] if len(tail) >= 2 else ''
    return normalize_location(city, state, country)


#---------------------------------------------------------------- 2021 runsignup

def load_runsignup(filename):
    raw = pd.read_csv(filename, dtype=str)
    df = pd.DataFrame()
    df['name'] = raw['Participant Name'].fillna('').map(clean_whitespace)
    names = df['name'].map(split_first_last)
    df = pd.concat([df, pd.DataFrame(names.tolist(), columns=['first', 'middle', 'last', 'suffix'])], axis=1)
    place_col = 'Place' if 'Place' in raw.columns else 'Race Placement'
    df['overall_place'] = pd.to_numeric(raw[place_col], errors='coerce')
    df['bib'] = pd.to_numeric(raw['Bib Number'], errors='coerce')
    df['time_s'] = raw['Chip Time'].map(parse_time)
    df['status'] = np.where(df['time_s'].notna(), 'finished', 'DNF')
    df['gender'] = raw['Gender'].str.strip().str.upper().str[0]
    df['age'] = pd.to_numeric(raw['Age'], errors='coerce')
    df['gender_place'] = df.groupby('gender')['overall_place'].rank(method='min')
    locs = [normalize_location(c, s, '') for c, s in zip(raw['City'].fillna(''), raw['State / Province'].fillna(''))]
    df[['city', 'state', 'country']] = pd.DataFrame(locs, index=df.index)
    return df


#---------------------------------------------------------------- 2022+ raceresult

RACERESULT_HEADERS = {11: ['index', 'Ovr', 'Sex', 'Div', 'Bib', 'Name', 'City, State, Nation', 'Age', 'Gender', 'Time', 'Pace'],
                      9: ['index', 'Ovr', 'Bib', 'Name', 'City, State, Nation', 'Age', 'Gender', 'Time', 'Pace']}

def load_raceresult(filename):
    #the header row doesn't always match the data (2024 birkie classic has the 9 column header over 11 column rows),
    #so go by the number of fields in the data instead
    raw = pd.read_csv(filename, dtype=str, encoding='utf-8', header=None, skiprows=1)
    raw.columns = RACERESULT_HEADERS[raw.shape[1]]
    #DNS entries never started, so they say nothing about anyone's racing
    raw = raw[raw['Ovr'].str.strip() != 'DNS'].reset_index(drop=True)
    df = pd.DataFrame()
    #"Last, First"
    last_first = raw['Name'].fillna('').str.split(',', n=1, expand=True)
    if last_first.shape[1] == 1:
        last_first[1] = ''
    df['name'] = (last_first[1].fillna('').str.strip() + ' ' + last_first[0].str.strip()).map(clean_whitespace)
    names = [split_first_last(first, last=last) for first, last in zip(last_first[1].fillna(''), last_first[0].fillna(''))]
    df = pd.concat([df, pd.DataFrame(names, columns=['first', 'middle', 'last', 'suffix'])], axis=1)
    df['overall_place'] = pd.to_numeric(raw['Ovr'].str.strip('. '), errors='coerce')
    if 'Sex' in raw.columns:
        df['gender_place'] = pd.to_numeric(raw['Sex'].str.strip('. '), errors='coerce')
    df['bib'] = pd.to_numeric(raw['Bib'], errors='coerce')
    df['time_s'] = raw['Time'].map(parse_time)
    df['status'] = np.where(df['time_s'].notna(), 'finished', 'DNF')
    df['gender'] = raw['Gender'].str.strip().str.upper().str[0]
    df['age'] = pd.to_numeric(raw['Age'], errors='coerce')
    df.loc[df['age'] <= 0, 'age'] = np.nan
    if 'gender_place' not in df.columns:
        df['gender_place'] = df.groupby('gender')['overall_place'].rank(method='min')
    locs = raw['City, State, Nation'].fillna('').map(parse_csv_location)
    df[['city', 'state', 'country']] = pd.DataFrame(locs.tolist(), index=df.index)
    return df


@functools.lru_cache(maxsize=None)
def parse_csv_location(raw):
    #"North Pole, AK, US"  "La clusaz, , FR"  "FRANCE, FRA"  "Bozeman, "
    parts = [p.strip() for p in raw.split(',')]
    while len(parts) < 3:
        parts.insert(1, '')
    city, state, country = parts[0], ' '.join(parts[1:-1]).strip(), parts[-1]
    return normalize_location(city, state, country)


#---------------------------------------------------------------- shared helpers

def parse_time(raw):
    #"2:05:35.4", "02:55:14.5", "48:28" (minutes:seconds for the short races)
    if not isinstance(raw, str):
        return np.nan
    parts = raw.strip().split(':')
    try:
        parts = [float(p) for p in parts]
    except ValueError:
        return np.nan
    if len(parts) == 3:
        return parts[0]*3600 + parts[1]*60 + parts[2]
    if len(parts) == 2:
        return parts[0]*60 + parts[1]
    return np.nan


def clean_whitespace(s):
    return re.sub(r'\s+', ' ', str(s)).strip()


def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))


def split_first_last(name, last=None):
    #returns (first, middle, last, suffix), all lowercase ascii.
    #when last is given, name holds only the first (+middle) names
    name = strip_accents(clean_whitespace(name)).lower()
    tokens = [t for t in re.split(r'[\s."()]+', name) if t]
    suffix = ''
    if last is None:
        while tokens and tokens[-1].strip(',') in SUFFIXES:
            suffix = tokens.pop().strip(',')
        if len(tokens) < 2:
            return ('', '', ''.join(tokens), suffix)
        last_tokens = [tokens.pop()]
        #keep particles with the last name: "van der berg", "de la cruz", "st john"
        while len(tokens) > 1 and tokens[-1] in ('van', 'von', 'der', 'den', 'de', 'la', 'le', 'du', 'st', 'mc', 'mac', 'di', 'da'):
            last_tokens.insert(0, tokens.pop())
        last = ' '.join(last_tokens)
    else:
        last = strip_accents(clean_whitespace(last)).lower()
        last_tokens = last.split()
        if last_tokens and last_tokens[-1].strip('.,') in SUFFIXES:
            suffix = last_tokens.pop().strip('.,')
        last = ' '.join(last_tokens)
        while tokens and tokens[-1].strip(',') in SUFFIXES:
            suffix = tokens.pop().strip(',')
    first = tokens[0] if tokens else ''
    middle = ' '.join(tokens[1:])
    return (first, middle, last, suffix)


def fix_squashed_names(results):
    #2020 names lost the space between first and last name: "KnuteSands", "Fred JKueffer", "JulieVan Stappen",
    #"DuncanMcLean", "DeAnnSmith", "KenMc Adams". Any capital letter could be the start of the last name, so try
    #each one and keep the split where both the first and last name are most familiar from the other years
    squashed = results['squashed'].eq(True)
    known_first = results.loc[~squashed, 'first'].map(compact).value_counts().to_dict()
    known_last = results.loc[~squashed, 'last'].map(compact).value_counts().to_dict()
    fixed = {}
    for i, name in results.loc[squashed, 'name'].items():
        best, best_count = None, 1
        for j in range(1, len(name)):
            if name[j].isupper() and name[:j].strip():
                first_count = known_first.get(compact(name[:j].split()[0]), 0)
                last_count = known_last.get(compact(name[j:]), 0)
                count = (first_count + 1) * (last_count + 1)
                if count > best_count:
                    best, best_count = j, count
        if best is None:
            #nothing familiar, fall back to the first lower->upper boundary
            m = re.search(r"[a-z.][A-Z]", name)
            best = m.start() + 1 if m else None
        if best is None:
            continue
        fixed[i] = (clean_whitespace(name[:best] + ' ' + name[best:]),) + split_first_last(name[:best], last=name[best:])
    fixed = pd.DataFrame.from_dict(fixed, orient='index', columns=['name', 'first', 'middle', 'last', 'suffix'])
    results.loc[fixed.index, fixed.columns] = fixed


def compact(s):
    #letters only, for comparing names that differ in spacing, hyphens, accents or case
    return re.sub(r'[^a-z]', '', strip_accents(str(s)).lower())


@functools.lru_cache(maxsize=None)
def normalize_location(city, state, country):
    city = strip_accents(clean_whitespace(city)).lower().strip(' ,.')
    state = strip_accents(clean_whitespace(state)).upper().strip(' ,.')
    country = strip_accents(clean_whitespace(country)).upper().strip(' ,.')
    country = COUNTRY_ALIASES.get(country, country)
    state = PROVINCE_NAMES.get(state, state)
    if state not in US_STATES | CA_PROVINCES:
        #"NASHOTAH WI" -> "WI". foreign regions ("BAYERN") and junk ("OUS") are dropped, the country is enough
        state = state.split()[-1] if state else ''
        state = state if state in US_STATES | CA_PROVINCES else ''
    if state in US_STATES and not country:
        country = 'USA'
    if state in CA_PROVINCES and not country:
        country = 'CAN'
    #common spellings of the same place
    city = re.sub(r'^(st|saint|ste|sainte)\.?\s+', 'st ', city)
    city = re.sub(r'\bmpls\b', 'minneapolis', city)
    city = re.sub(r'\bft\.?\s', 'fort ', city)
    city = re.sub(r'\bmt\.?\s', 'mount ', city)
    city = re.sub(r'[^a-z ]', '', city).strip()
    if city in ('unknown', 'na', 'none'):
        city = ''
    return (city, state, country)
