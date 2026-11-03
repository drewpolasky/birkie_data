#how far can results read from old pdfs and scans be trusted? each check is the share of results that pass, run on
#old_results/ (birkie_archive.py) and, as a yardstick, on the clean birkie years in yearly_data/:
#   places   the places count 1, 2, 3... down each list (one per gender), with no gaps or repeats
#   order    the times never go down as the places go up
#   times    the time reads as h:mm:ss with minutes and seconds under 60, and is between 1:30 and 10 hours (the
#            shortest cut in step for a race cut short)
#   class    each age class rank is one more than the one before it in the class (where a list has them)
#   bibs     no bib turns up twice
#   last     the last name turns up in another year's clean results (2002 on, birkie weekend and pre-birkie)
#   first    the first name does
#   state    the state is a US state or Canadian province (US and Canadian skiers only)
#   town     the town turns up in that state in another year's clean results
#   winners  the fastest man and woman match the birkie's champions list, within a second
#a clean year is measured against the other clean years, so its name and town shares show what a reliable year looks like
#
#example usage:
#python check_results.py                   every old year and the clean years 2002-2008, written to old_results/reliability.csv
#python check_results.py --years 1999      one year
#python check_results.py --race kortie     the kortelopet's old years and its clean years 2002-2013, written to
#                                          old_results/reliability_kortie.csv
import argparse
import functools
import glob
import os
import re

import numpy as np
import pandas as pd
import pdfplumber

from get_prebirkie_data import get
from results_loader import (load_all_results, split_first_last, normalize_location, parse_time, compact, US_STATES,
                            CA_PROVINCES)

OLD_DIR = 'old_results'
CHAMPIONS_URL = 'https://www.birkie.com/wp-content/uploads/2019/02/Birkie-Champions-2019.pdf'
CHAMPIONS_PDF = os.path.join(OLD_DIR, 'pdfs', 'Birkie-Champions-2019.pdf')
BASELINE_YEARS = {'birkie': range(2002, 2009), 'kortie': range(2002, 2014)}
TIME_RANGE = (1.5 * 3600, 10 * 3600)
#races cut short, with their length in km, against the usual 51. 1991 started at an alternate start for lack of snow,
#and its pace column is the time over 46 km
SHORT_RACES = {1991: 46, 1998: 23}
FULL_KM = 51
WINNER_SECONDS = 1.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, nargs='*')
    parser.add_argument("--race", choices=['birkie', 'kortie'], default='birkie')
    args = parser.parse_args()

    clean = load_all_results()
    champs = champions(args.race)
    #the kortelopet's length each year from the champions list (29 km where it gives none), against the birkie's 51
    kms = SHORT_RACES if args.race == 'birkie' else {y: race_km('kortie').get(y, 29) for y in range(1973, 2030)}
    rows = []
    for year, results in old_years(args.race) + baseline_years(clean, args.race):
        if args.years and year not in args.years:
            continue
        rows.append({'year': year, 'source': results.attrs['source'], 'results': len(results),
                     **check(results, clean[clean['year'] != year], champs.get(year, []),
                             kms.get(year, FULL_KM) / FULL_KM)})
    report = pd.DataFrame(rows).sort_values(['source', 'year'])
    with pd.option_context('display.width', 200, 'display.max_columns', 30):
        print(report.round(3).to_string(index=False))
    if not args.years:
        name = 'reliability.csv' if args.race == 'birkie' else 'reliability_{}.csv'.format(args.race)
        report.round(4).to_csv(os.path.join(OLD_DIR, name), index=False)


#---------------------------------------------------------------- data

def old_years(race='birkie'):
    #old_results/<year>/<race> <year>.csv, put in the same shape as results_loader's
    out = []
    for path in sorted(glob.glob(os.path.join(OLD_DIR, '*', '{} *.csv'.format(race)))):
        raw = pd.read_csv(path, dtype=str, keep_default_na=False)
        if raw.empty:
            continue
        year = int(re.search(r'(\d{4})\.csv$', path).group(1))
        out.append((year, standardize(raw, 'archive')))
    return out


def standardize(raw, source):
    df = pd.DataFrame()
    names = [split_first_last(first, last=last) if last else split_first_last(name)
             for name, first, last in zip(raw['name'], raw['first'], raw['last'])]
    df[['first', 'middle', 'last', 'suffix']] = pd.DataFrame(names, index=raw.index)
    df['place'] = pd.to_numeric(raw['place'], errors='coerce')
    df['time_raw'] = raw['time']
    df['time_s'] = raw['time'].map(parse_time)
    df['gender'] = raw['gender']
    df['bib'] = pd.to_numeric(raw['bib'], errors='coerce')
    df['age_group'] = raw['age_group']
    df['class_rank'] = pd.to_numeric(raw.get('class_rank', pd.Series('', index=raw.index)), errors='coerce')
    #the old lists place classic and skate skiers together, one list for each gender
    df['list'] = raw['gender']
    locs = [normalize_location(c, s, n) for c, s, n in zip(raw['city'], raw['state'], raw['country'])]
    df[['city', 'state', 'country']] = pd.DataFrame(locs, index=raw.index)
    df.attrs['source'] = source
    return df


def baseline_years(clean, race='birkie'):
    #the clean birkie years before 2009 (the kortelopet's 2002-2013), each list placed by time
    out = []
    for year in BASELINE_YEARS[race]:
        r = clean[(clean['race'] == race) & (clean['year'] == year) & (clean['status'] == 'finished')].copy()
        if r.empty:
            continue
        r['list'] = r['gender'].fillna('') + ' ' + r['tech']
        r['place'] = r.groupby('list')['time_s'].rank(method='first')
        r['time_raw'] = r['time_s'].map(lambda s: '{}:{:02d}:{:04.1f}'.format(int(s // 3600), int(s % 3600 // 60), s % 60))
        r['class_rank'] = np.nan
        r['age_group'] = ''
        r.attrs['source'] = 'clean'
        out.append((year, r))
    return out


def champions(race='birkie'):
    #{year: [(gender, name, seconds)]} for the birkie or the kortelopet, men then women in each of the year's races
    return champion_list()[0].get(race, {})


def race_km(race):
    #{year: the race's length in km}, its first race's where a year has two (skate and classic), from the champions list
    return champion_list()[1].get(race, {})


@functools.lru_cache(maxsize=None)
def champion_list():
    if not os.path.exists(CHAMPIONS_PDF):
        os.makedirs(os.path.dirname(CHAMPIONS_PDF), exist_ok=True)
        with open(CHAMPIONS_PDF, 'wb') as f:
            f.write(get(CHAMPIONS_URL))
    out, kms, year, race, n = {}, {}, None, None, 0
    with pdfplumber.open(CHAMPIONS_PDF) as pdf:
        lines = [l for page in pdf.pages for l in (page.extract_text() or '').splitlines()]
    for line in lines:
        if re.fullmatch(r'\s*(19|20)\d{2}\s*', line):
            year = int(line)
        elif 'Haakon' in line:
            race = None
        elif ('Kortelopet' in line or 'Birkebeiner' in line) and year:
            race, n = 'kortie' if 'Kortelopet' in line else 'birkie', 0
            km = re.search(r'(\d+(?:[.,]\d+)?)\s*K', line)
            if km:
                kms.setdefault(race, {}).setdefault(year, float(km.group(1).replace(',', '.')))
        else:
            m = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)\W*$', line)
            if race and m and ',' in line:
                name = re.sub(r'^\W+|\*', '', line.split(',')[0]).strip()
                #(1998's kortelopet woman's 1:02.50 is 1:02:50)
                t = re.sub(r'^(\d:\d\d)\.(\d\d)$', r'\1:\2', m.group(1))
                out.setdefault(race, {}).setdefault(year, []).append(('M' if n % 2 == 0 else 'F', name, parse_time(t)))
                n += 1
    return out, kms


#---------------------------------------------------------------- checks

def check(r, others, champs, length=1):
    out = {}
    places = ordered = classes = 0
    for _, lst in r.groupby('list'):
        lst = lst.sort_values('place')
        p = lst['place'].dropna().astype(int).values
        places += np.isin(np.arange(1, len(lst) + 1), p).sum() - (len(p) - len(set(p)))
        t = lst['time_s'].values
        ordered += 1 + (np.diff(t) >= 0).sum() if len(t) else 0
        for _, c in lst.dropna(subset=['class_rank']).groupby('age_group'):
            #each rank one more than the one before it in the class, so one slip costs one result, not all after it
            ranks = c['class_rank'].astype(int).values
            classes += (ranks == np.concatenate([[0], ranks[:-1]]) + 1).sum()
    out['places'] = places / len(r)
    out['order'] = ordered / len(r)
    out['times'] = r['time_raw'].map(lambda t: valid_time(t, length)).mean()
    has_class = r['class_rank'].notna()
    out['class'] = classes / has_class.sum() if has_class.any() else np.nan
    bibs = r['bib'].dropna()
    out['bibs'] = 1 - bibs.duplicated(keep=False).mean() if len(bibs) else np.nan

    #names and towns against every other year's clean results
    out['last'] = r['last'].map(compact).isin(set(others['last'].map(compact))).mean()
    out['first'] = r['first'].map(compact).isin(set(others['first'].map(compact))).mean()
    north_american = r['country'].isin(['USA', 'CAN', ''])
    #(not for a list that gives no one's home, 1973's and 1974's)
    located = (r['state'] != '') | (r['country'] != '') | (r['city'] != '')
    out['state'] = r.loc[north_american, 'state'].isin(US_STATES | CA_PROVINCES).mean() if located.any() else np.nan
    towns = set(zip(others['city'], others['state']))
    known = r[r['state'].isin(US_STATES | CA_PROVINCES) & (r['city'] != '')]
    out['town'] = np.mean([t in towns for t in zip(known['city'], known['state'])]) if len(known) else np.nan
    out['winners'] = winners(r, champs)
    return out


def valid_time(raw, length=1):
    m = re.fullmatch(r'(\d{1,2}):(\d{2}):(\d{2})(\.\d+)?', str(raw).strip())
    if not m or int(m.group(2)) > 59 or int(m.group(3)) > 59:
        return False
    return TIME_RANGE[0] * length <= parse_time(raw) <= TIME_RANGE[1]


def winners(r, champs):
    #share of the genders whose fastest finisher matches the champions list's winner of one of that year's races (1981
    #lists the elite race the day before the citizens' first, whose results are only partly printed). 1974's women's
    #winner is listed with the time of the shorter race's
    if not champs:
        return np.nan
    hits = []
    for gender in ('M', 'F'):
        listed = [seconds for g, _, seconds in champs if g == gender]
        fastest = r.loc[r['gender'] == gender, 'time_s'].min()
        #a year whose list has no one of a gender (1973's women raced 22 km) checks the other only
        if listed and np.isfinite(fastest):
            hits.append(any(abs(fastest - seconds) <= WINNER_SECONDS for seconds in listed))
    return np.mean(hits) if hits else np.nan


if __name__ == '__main__':
    main()
