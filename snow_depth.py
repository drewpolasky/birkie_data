#daily snow depth at every skier's hometown, from SNODAS (NOAA's 1 km snow model, NSIDC dataset G02158)
#
#SNODAS comes as one tar per day with a full continental US grid of 8 variables. this pulls snow depth at each
#hometown out of those once, so the snow vs performance analysis never has to touch the 300 GB of grids again.
#outside the lower 48 (canada, alaska, europe) SNODAS has no data, so those hometowns get no snow.
#
#hometowns are placed with the census gazetteer (cities, villages, towns, townships) and the USGS list of named
#places (for spots like harshaw or hubertus), both downloaded on first use into snow_data/gazetteer.
#
#example usage:
#python snow_depth.py download --start 2023-01-01 --end 2026-03-31     daily tars from NSIDC, winter months only
#python snow_depth.py build                                             writes snow_data/hometowns.csv and
#                                                                        snow_data/hometown_snow_depth.parquet
import argparse
import concurrent.futures
import glob
import gzip
import os
import re
import tarfile
import time
import urllib.error
import urllib.request
import zipfile

import numpy as np
import pandas as pd

URL = 'https://noaadata.apps.nsidc.org/NOAA/G02158/masked/{d:%Y}/{d:%m_%b}/SNODAS_{d:%Y%m%d}.tar'
TAR_DIR = 'E:/snowdas_data/tar_files'
NEW_TAR_DIR = 'E:/snowdas_data/tar_files_2023-2026'
WINTER_MONTHS = [10, 11, 12, 1, 2, 3]
OUT_DIR = 'snow_data'

#the masked SNODAS grid: 30 arc second cells over the lower 48, first row is the north edge.
#before october 2013 the headers put it 1/20 of a cell (40 m) further northwest, which doesn't matter here
N_ROWS, N_COLS = 3351, 6935
CELL = 1 / 120
WEST_CENTER, NORTH_CENTER = -124.729166666662, 52.8708333333312
NO_DATA = -9999
DEPTH_FILE = re.compile(r'us_ssmv11036tS__T0001TTNATS\d{10}HP001\.dat\.gz')
RADIUS_KM = 10                  #the "near town" depth averages the land within this distance
MAX_GAP_DAYS = 2                #days missing from NSIDC's archive up to this long are filled in from either side

#where hometowns are: census places (cities, villages, census designated places), then census towns and townships,
#then the USGS list of every named populated place for the unincorporated spots
CENSUS_URL = 'https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_Gaz_{}_national.zip'
GNIS_URL = ('https://prd-tnm.s3.amazonaws.com/StagedProducts/GeographicNames/DomesticNames/'
            'DomesticNames_National_Text.zip')
#what kind of place the census says it is, dropped from the name for matching
PLACE_TYPES = (r' (city and borough|charter township|township|town|village|city|borough|municipality|CDP|CCD|'
               r'plantation|UT)( \(balance\))?$')
#spellings in the results that differ from the gazetteer
WORDS = {'saint': 'st', 'sainte': 'ste', 'mount': 'mt', 'fort': 'ft', 'spgs': 'springs', 'spg': 'springs',
         'spr': 'springs', 'hts': 'heights', 'hgts': 'heights', 'fls': 'falls', 'lk': 'lake', 'cty': 'city',
         'jct': 'junction', 'minn': 'minnesota', 'twp': '', 'tp': '', 'township': ''}
LEADING = {'n': 'north', 'no': 'north', 's': 'south', 'so': 'south', 'e': 'east', 'w': 'west'}
SAME_PLACE_KM = 25              #two towns, townships or settlements with one name in a state are one place if this close
MIN_PREFIX = 6                  #"marine" for marine on st. croix, when only one place in the state starts that way
BORDER_KM = 50                  #a town listed in the wrong state is accepted when it's this close to that state

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    dl = sub.add_parser('download', help='fetch daily SNODAS tars from NSIDC')
    dl.add_argument('--start', type=str, required=True)
    dl.add_argument('--end', type=str, required=True)
    dl.add_argument('--out', type=str, default=NEW_TAR_DIR)
    dl.add_argument('--all_months', action='store_true', help='not just october through march')
    build_args = sub.add_parser('build', help='daily snow depth at every hometown')
    build_args.add_argument('--linked', type=str, default='linked_data/linked_results.csv')
    build_args.add_argument('--tars', type=str, nargs='+', default=[TAR_DIR, NEW_TAR_DIR])
    build_args.add_argument('--workers', type=int, default=6)
    args = parser.parse_args()

    if args.command == 'download':
        months = range(1, 13) if args.all_months else WINTER_MONTHS
        download(pd.Timestamp(args.start), pd.Timestamp(args.end), args.out, months)
    else:
        build(args.linked, args.tars, args.workers)


def build(linked_path, tar_dirs, workers):
    results = pd.read_csv(linked_path, usecols=['athlete_id', 'city', 'state', 'country'], low_memory=False)
    towns = geocode_hometowns(results)
    located = towns['lat'].notna()
    print('{} US hometowns, {} located ({:.1%} of US results)'.format(
        len(towns), located.sum(), towns.loc[located, 'n_results'].sum() / towns['n_results'].sum()))
    print(towns.groupby('match', dropna=False)['n_results'].agg(['size', 'sum']).rename(
        columns={'size': 'hometowns', 'sum': 'results'}).to_string())

    paths = tar_files(tar_dirs)
    print('{} winter days of SNODAS, {:%Y-%m-%d} to {:%Y-%m-%d}'.format(len(paths), paths.index[0], paths.index[-1]))
    center, towns['cell_km'], near, near_town = town_cells(towns, land_cells(paths))
    towns['on_grid'] = center >= 0
    on_grid = np.flatnonzero(towns['on_grid'])
    town_depth = np.full((len(paths), len(on_grid)), np.nan, dtype=np.float32)
    near_depth = town_depth.copy()
    start = time.time()
    with concurrent.futures.ProcessPoolExecutor(workers, initializer=set_cells,
                                                initargs=(center[on_grid], near, near_town)) as pool:
        for i, (here, around) in enumerate(pool.map(town_depths, paths.values, chunksize=4)):
            town_depth[i], near_depth[i] = here, around
            if (i + 1) % 250 == 0:
                print('{}/{} days  {:.0f} s'.format(i + 1, len(paths), time.time() - start), flush=True)

    depth = to_table(paths.index, towns.index[on_grid], town_depth, near_depth)
    os.makedirs(OUT_DIR, exist_ok=True)
    towns.rename_axis('hometown_id').to_csv(os.path.join(OUT_DIR, 'hometowns.csv'))
    depth.to_parquet(os.path.join(OUT_DIR, 'hometown_snow_depth.parquet'), index=False)
    print('saved {} hometowns and {:,} hometown days to {}/'.format(len(towns), len(depth), OUT_DIR))


def download(start, end, out_dir, months=WINTER_MONTHS, workers=4):
    os.makedirs(out_dir, exist_ok=True)
    days = [d for d in pd.date_range(start, end) if d.month in months]
    todo = [d for d in days if not os.path.exists(tar_path(out_dir, d))]
    print('{} days in range, {} to fetch into {}'.format(len(days), len(todo), out_dir))
    missing, done, nbytes = [], 0, 0
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        for d, size in zip(todo, pool.map(lambda d: fetch(d, out_dir), todo)):
            done += 1
            if size is None:
                missing.append(d)
            else:
                nbytes += size
            if done % 50 == 0 or done == len(todo):
                print('{}/{}  {:.1f} GB  through {:%Y-%m-%d}'.format(done, len(todo), nbytes / 1e9, d), flush=True)
    #NSIDC's archive has a few days missing every winter
    print('not on the server:', ', '.join('{:%Y-%m-%d}'.format(d) for d in missing) or 'none')


def tar_path(tar_dir, day):
    return os.path.join(tar_dir, 'SNODAS_{:%Y%m%d}.tar'.format(day))


def fetch(day, out_dir, tries=4):
    path = tar_path(out_dir, day)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(URL.format(d=day), timeout=120) as response:
                expected = int(response.headers['Content-Length'])
                data = response.read()
            if len(data) != expected:
                raise IOError('short read')
            #write to a temp name first so an interrupted run never leaves a partial tar behind
            with open(path + '.part', 'wb') as f:
                f.write(data)
            os.replace(path + '.part', path)
            return len(data)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(5 * (attempt + 1))
        except (urllib.error.URLError, IOError, TimeoutError):
            time.sleep(5 * (attempt + 1))
    print('gave up on', path)
    return None


def tar_files(tar_dirs, months=WINTER_MONTHS):
    paths = {}
    for tar_dir in tar_dirs:
        for path in glob.glob(os.path.join(tar_dir, 'SNODAS_*.tar')):
            day = pd.Timestamp(os.path.basename(path)[7:15])
            if day.month in months:
                paths[day] = path
    return pd.Series(paths).sort_index()


def read_depth(path):
    #snow depth in mm over the whole grid, -9999 off land and outside the US
    with tarfile.open(path) as t:
        member = next(m for m in t.getmembers() if DEPTH_FILE.fullmatch(m.name))
        raw = gzip.decompress(t.extractfile(member).read())
    return np.frombuffer(raw, dtype='>i2').reshape(N_ROWS, N_COLS)


def land_cells(paths):
    #SNODAS's water and border mask has changed over the years (most in october 2013, when madison's cell went from
    #lake to land), so only cells that are land on february 1 of every season are used. that keeps each town's
    #snow comparable from one year to the next
    land = np.ones(N_ROWS * N_COLS, dtype=bool)
    for path in paths[(paths.index.month == 2) & (paths.index.day == 1)].values:
        land &= read_depth(path).ravel() != NO_DATA
    return land


def town_cells(towns, land):
    #for each town, the nearest land cell (-1 when there's no land within RADIUS_KM or it's off the grid) and how far
    #that is in km, plus every land cell within RADIUS_KM as flat grid indexes. near_town says which of the on grid
    #towns each near cell belongs to
    center = np.full(len(towns), -1, dtype=np.int64)
    cell_km = np.full(len(towns), np.nan)
    near, near_town = [], []
    km_per_row = 111.2 * CELL
    reach = int(np.ceil(RADIUS_KM / km_per_row))
    for i, (lat, lng) in enumerate(towns[['lat', 'lng']].values):
        row, col = np.round((NORTH_CENTER - lat) / CELL), np.round((lng - WEST_CENTER) / CELL)
        if not (0 <= row < N_ROWS and 0 <= col < N_COLS):     #also skips towns with no location
            continue
        km_per_col = km_per_row * np.cos(np.radians(lat))
        cols = int(np.ceil(RADIUS_KM / km_per_col))
        dr, dc = np.meshgrid(np.arange(-reach, reach + 1), np.arange(-cols, cols + 1), indexing='ij')
        km = np.hypot(dr * km_per_row, dc * km_per_col)
        r, c = row + dr, col + dc
        keep = (km <= RADIUS_KM) & (r >= 0) & (r < N_ROWS) & (c >= 0) & (c < N_COLS)
        cells, km = (r[keep] * N_COLS + c[keep]).astype(np.int64), km[keep]
        cells, km = cells[land[cells]], km[land[cells]]
        if len(cells) == 0:
            continue
        center[i], cell_km[i] = cells[np.argmin(km)], km.min()
        near.append(cells)
        near_town.append(np.full(len(cells), len(near) - 1, dtype=np.int32))
    return center, cell_km.round(2), np.concatenate(near), np.concatenate(near_town)


def set_cells(center, near, near_town):
    global CENTER, NEAR, NEAR_TOWN
    CENTER, NEAR, NEAR_TOWN = center, near, near_town


def town_depths(path):
    #one day: depth in each town's nearest land cell, and the mean over the land within RADIUS_KM
    grid = read_depth(path).ravel()
    here = grid[CENTER].astype(np.float32)
    here[here == NO_DATA] = np.nan
    around = grid[NEAR]
    land = around != NO_DATA
    total = np.bincount(NEAR_TOWN[land], around[land], minlength=len(CENTER))
    cells = np.bincount(NEAR_TOWN[land], minlength=len(CENTER))
    with np.errstate(invalid='ignore'):
        return here, (total / cells).astype(np.float32)


def to_table(days, town_ids, town_depth, near_depth):
    #long table, one row per hometown per winter day. each season is filled out to every day from october 1 to
    #march 31, short gaps are interpolated and flagged
    season = days.year + (days.month >= 10)
    calendar = pd.DatetimeIndex([d for s in np.unique(season)
                                 for d in pd.date_range('{}-10-01'.format(s - 1), '{}-03-31'.format(s))
                                 if days[0] <= d <= days[-1]])
    tables = []
    for name, values in [('depth_mm', town_depth), ('depth_{}km_mm'.format(RADIUS_KM), near_depth)]:
        wide = pd.DataFrame(values, index=days, columns=town_ids).reindex(calendar)
        filled = wide.groupby(calendar.year + (calendar.month >= 10)).transform(
            lambda s: s.interpolate(limit=MAX_GAP_DAYS, limit_area='inside'))
        tables.append(filled.round(1).stack(future_stack=True).rename(name))
    depth = pd.concat(tables, axis=1).rename_axis(['date', 'hometown_id']).reset_index()
    depth['filled'] = ~depth['date'].isin(days) & depth['depth_mm'].notna()
    return depth[['hometown_id', 'date', 'depth_mm', 'depth_{}km_mm'.format(RADIUS_KM), 'filled']]


def place_key(name):
    words = re.sub(r"[.,'\-/]", ' ', str(name).lower()).split()
    words = [WORDS.get(w, w) for w in words]
    if len(words) > 1:
        words[0] = LEADING.get(words[0], words[0])
    key = ''.join(words)
    half = len(key) // 2
    return key[:half] if len(key) % 2 == 0 and key[:half] == key[half:] else key     #"minneapolisminneapolis"


def edit_distance(a, b, limit):
    #levenshtein, giving up once every path is past the limit
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def km_between(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def gazetteer(cache=os.path.join(OUT_DIR, 'gazetteer')):
    #one location per place name per state, from the best source that has it. when a state has two cities with the
    #same name the bigger one (by area) is used. towns, townships and settlements share names all over a state, so
    #one of those is only used when every one with that name is in about the same spot
    def fetch_once(url):
        path = os.path.join(cache, os.path.basename(url))
        if not os.path.exists(path):
            os.makedirs(cache, exist_ok=True)
            urllib.request.urlretrieve(url, path)
        return path

    frames = []
    for kind in ['place', 'cousubs']:
        g = pd.read_csv(fetch_once(CENSUS_URL.format(kind)), sep='\t', dtype=str)
        g.columns = g.columns.str.strip()
        rank = 2 if kind == 'cousubs' else g['NAME'].str.endswith(' CDP').astype(int)
        frames.append(pd.DataFrame({'place': g['NAME'].str.replace(PLACE_TYPES, '', regex=True), 'state': g['USPS'],
                                    'lat': g['INTPTLAT'].astype(float), 'lng': g['INTPTLONG'].astype(float),
                                    'area': g['ALAND'].astype(float), 'rank': rank}))
    state_codes = dict(zip(g['GEOID'].str[:2], g['USPS']))
    with zipfile.ZipFile(fetch_once(GNIS_URL)) as z:
        g = pd.read_csv(z.open('Text/DomesticNames_National.txt'), sep='|', dtype=str, encoding='utf-8-sig',
                        usecols=['feature_name', 'feature_class', 'state_numeric', 'prim_lat_dec', 'prim_long_dec'])
    g = g[(g['feature_class'] == 'Populated Place') & (g['prim_lat_dec'].astype(float) != 0)]
    frames.append(pd.DataFrame({'place': g['feature_name'], 'state': g['state_numeric'].map(state_codes),
                                'lat': g['prim_lat_dec'].astype(float), 'lng': g['prim_long_dec'].astype(float),
                                'area': np.nan, 'rank': 3}))

    places = pd.concat(frames, ignore_index=True).dropna(subset=['state'])
    places['key'] = places['place'].map(place_key)
    places = places.sort_values(['rank', 'area'], ascending=[True, False])
    groups = [places['key'], places['state'], places['rank']]
    first = places.groupby(groups)[['lat', 'lng']].transform('first')
    together = pd.Series(km_between(places['lat'], places['lng'], first['lat'], first['lng']) <= SAME_PLACE_KM)
    places = places[(places['rank'] <= 1) | together.groupby(groups).transform('all')]
    return places.drop_duplicates(['key', 'state']).drop(columns='area')


def geocode_hometowns(results):
    #every US city/state skiers have listed, with a location from the gazetteer: the exact name, then a place in the
    #same state that starts with it, then a one or two letter typo, then the same name just across a state line
    places = gazetteer()
    by_state = {s: g for s, g in places.groupby('state')}
    census = {s: g[g['rank'] <= 2] for s, g in by_state.items()}
    us = results[results['state'].isin(by_state) & results['country'].fillna('USA').eq('USA') &
                 results['city'].notna()]
    towns = us.groupby(['city', 'state']).agg(n_results=('athlete_id', 'size'), n_athletes=('athlete_id', 'nunique'))
    towns = towns.reset_index()
    towns['key'] = towns['city'].map(place_key)
    towns = towns.merge(places.rename(columns={'state': 'place_state'}).drop(columns='rank'),
                        left_on=['key', 'state'], right_on=['key', 'place_state'], how='left')
    towns['match'] = np.where(towns['lat'].notna(), 'exact', None)

    for i in towns.index[towns['lat'].isna()]:
        key, state = towns.at[i, 'key'], towns.at[i, 'state']
        for how, find in [('prefix', lambda: prefix_match(key, census[state])),
                          ('typo', lambda: typo_match(key, census[state])),
                          ('other state', lambda: across_border(key, state, places, by_state))]:
            found = find()
            if found is not None:
                towns.loc[i, ['place', 'place_state', 'lat', 'lng', 'match']] = [
                    found['place'], found['state'], found['lat'], found['lng'], how]
                break
    towns[['lat', 'lng']] = towns[['lat', 'lng']].astype(float)
    return towns.drop(columns='key')


def prefix_match(key, places):
    if len(key) < MIN_PREFIX:
        return None
    found = places[places['key'].str.startswith(key)]
    return found.iloc[0] if len(found) == 1 else None


def typo_match(key, places):
    #only when one place is clearly meant: same first letter and no other name as close
    if len(key) < 5:
        return None
    limit = 1 if len(key) < 10 else 2
    near = places[((places['key'].str.len() - len(key)).abs() <= limit) & (places['key'].str[0] == key[0])]
    dist = near['key'].map(lambda k: edit_distance(key, k, limit))
    best = near[dist == dist.min()] if len(dist) else near
    return best.iloc[0] if len(best) == 1 and dist.min() <= limit else None


def across_border(key, state, places, by_state):
    same_name = places[(places['key'] == key) & (places['state'] != state)]
    if same_name.empty:
        return None
    home = by_state[state]
    gap = [km_between(p['lat'], p['lng'], home['lat'].values, home['lng'].values).min()
           for _, p in same_name.iterrows()]
    return same_name.iloc[int(np.argmin(gap))] if min(gap) <= BORDER_KM else None


if __name__ == '__main__':
    main()
