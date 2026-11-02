#can the weather say how fast a birkie will be? each race's speed comes from the year to year model in
#performance_changes.py (the same skiers compared from one race to the next, so it isn't about who showed up), and
#is set against the weather around the course:
#   hourly: hayward municipal airport (HYR, at the finish end) from the iowa environmental mesonet, for temperature
#           and when it was snowing. its heated gauge reports most snow as a trace, so it can't say how much fell.
#           the ashland and rice lake airports fill the hours it's down
#   daily:  the hayward ranger station co-op (GHCN USC00473511) for snowfall at one spot, to count the thaw days since
#           the last snowfall. its daily totals end around midday, so the race day's report covers the race morning
#   SNODAS: NOAA's daily 1 km snow model (snowfall, rain, snow water, depth, snowpack temperature, melt), averaged
#           over the land within 5 km of a straight line from cable to hayward, so along the whole course. read once
#           from the daily tars (snow_depth.py downloads them) and cached. its snowfall is the new snow measure
#each race is one data point per technique. 2002 and 2021 are left out: they were different courses, so their speed
#isn't comparable, and SNODAS starts in the 2003-04 winter, so the birkie runs from 2004. the kortelopet is on the
#same trail, the same day as the birkie until 2016 and the friday before it since 2018, and the pre-birkie
#(get_prebirkie_data.py) about two weeks before, so they add race days, some in other weather. both have moved
#course, so each course gets a level of its own, as each technique does, and only the race days on one course are
#compared with each other. every model is judged by leaving out one race weekend at a time (the birkie and the
#kortelopet together, since they share the weather) and predicting it from the others.
#
#example usage:
#python weather_speed.py              downloads the weather into weather_data/ the first time
#python weather_speed.py --birkie_only     the birkie's race days alone
#python weather_speed.py --races birkie prebirkie     the birkie's and pre-birkie's, without the kortelopet
import argparse
import concurrent.futures
import glob
import gzip
import os
import tarfile
import urllib.request

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from front_back import place_labels
from performance_changes import load_linked, build_panel, fit_model, style, INK, INK_2, GRID, SURFACE
from snow_effect import RACE_DAYS
from snow_depth import TAR_DIR, NEW_TAR_DIR, N_ROWS, N_COLS, CELL, WEST_CENTER, NORTH_CENTER, NO_DATA, tar_files, \
    land_cells

WEATHER_DIR = 'weather_data'
ASOS_STATION = 'HYR'
ASOS_BACKUP = ['ASX', 'RPD']            #ashland and rice lake airports, either side of hayward, for hours HYR is missing
COOP_STATION = 'USC00473511'
ASOS_URL = ('https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station={station}&data=tmpf&data=wxcodes'
            '&year1={y0}&month1=11&day1=1&year2={y1}&month2=3&day2=15&tz=America%2FChicago&format=onlycomma'
            '&latlon=no&elev=no&missing=M&trace=T&direct=no&report_type=3&report_type=4')
COOP_URL = ('https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries&stations={station}'
            '&startDate={start}&endDate=2026-04-01&dataTypes=SNOW,SNWD,PRCP,TMAX,TMIN&format=csv&units=standard')
#SNODAS's daily grids by the code in each file name. each tar is dated at midnight central time: the snowpack then,
#and the totals over the 24 hours before. the scale comes from each grid's header (2026 stores temperature in tenths)
SNODAS_GRIDS = {'1025SlL01': 'snowfall_mm', '1025SlL00': 'rain_mm', '1034tS__': 'swe_mm', '1036tS__': 'depth_mm',
                '1038wS__': 'snowpack_k', '1044bS__': 'melt_mm', '1050lL00': 'sublimation_mm'}
UNIT_TO = {'Meters': 1000, 'Kilograms per square meter': 1, 'Kelvins': 1}       #to mm of water, mm, or kelvin
COURSE_LINE = [(46.2011, -91.2937), (46.0066, -91.4897)]       #cable to hayward
COURSE_KM = 5
#the birkie before 2009 (get_old_birkie_data.py). 2007 was cut to 25 km and isn't in the data
OLD_RACE_DAYS = {2002: '2002-02-23', 2003: '2003-02-22', 2004: '2004-02-21', 2005: '2005-02-26', 2006: '2006-02-25',
                 2008: '2008-02-23'}
BIRKIE_DAYS = {**OLD_RACE_DAYS, **RACE_DAYS}
LEAVE_OUT_YEARS = [2002, 2017, 2021, 2024]  #cut to 46.7 km, cancelled, a different course, and the shortened course
#classic skiers raced the skate course with the skaters until 2008, whose first separate classic race was 53 km. each
#is a course of its own for classic. SNODAS starts in the 2003-04 winter, so race days before that are left out
CLASSIC_COURSES = {'on the skate course': [2002, 2003, 2004, 2005, 2006], '53 km': [2008]}
RACE_HOURS = (8, 14)                    #the field is mostly on course from 8am to 2pm
NEW_SNOW_DAYS = 3                       #SNODAS's 3 days to race eve, or the co-op's race day report and the two before
SNOWFALL_IN = 1.0                       #a snowfall at the co-op, for counting thaw days since the last one
LOOKBACK_DAYS = 30
TECHS = ['skate', 'classic']
#the pre-birkie's race days, and its courses (get_prebirkie_data.py). a course raced on only one day (46 and 24 km in
#2019, and 2021, raced in march on a course I couldn't find) says nothing about the weather, so it's left out
PREBIRKIE_RACES = ['prebirkie', 'prebirkie_short']
PREBIRKIE_DAYS = {2009: '2009-02-07', 2010: '2010-02-13', 2011: '2011-02-12', 2015: '2015-02-07', 2017: '2017-02-11',
                  2018: '2018-02-10', 2019: '2019-02-09', 2020: '2020-02-08', 2021: '2021-03-06', 2022: '2022-02-12',
                  2023: '2023-02-11', 2026: '2026-02-07'}
PREBIRKIE_COURSES = {'north from lake hayward': [2009, 2010, 2011], 'from birkie ridge': [2015, 2017, 2018, 2020],
                     '46 and 24 km': [2019], 'in march': [2021], 'out and back from birkie ridge': [2022, 2023, 2026]}
#the kortelopet (get_old_birkie_data.py --race kortie before 2009). until 2016 it was raced the same day as the birkie,
#23 km from the birkie's start, splitting off at 9 km and back to telemark. its move to the friday before, on a new
#29 km course from OO to main street in hayward (the birkie's back half), was put off by 2017's cancelled race, so 2018
#was the first. 2021 was raced in waves over five days, and 2024 was cut to 20 km
KORTIE_FRIDAY_FROM = 2018
KORTIE_DAYS = {y: str((pd.Timestamp(d) - pd.Timedelta(days=int(y >= KORTIE_FRIDAY_FROM))).date())
               for y, d in BIRKIE_DAYS.items()}
KORTIE_LEAVE_OUT_YEARS = [2017, 2021, 2024]
KORTIE_COURSES = {'23 km to telemark': list(range(2002, 2017)), '29 km from OO': list(range(KORTIE_FRIDAY_FROM, 2027))}
#classic was a division of the one race, on the skate course, until 2008's first classic race, as in the birkie
KORTIE_CLASSIC_COURSES = {'on the skate course': [2002, 2003, 2004, 2005, 2006], 'first classic race': [2008],
                          '23 km to telemark': list(range(2009, 2017)),
                          '29 km from OO': list(range(KORTIE_FRIDAY_FROM, 2027))}
#each race: its race days, the years left out, its courses for each technique (one course where none are given), and
#its name and label prefix in the output
RACES = {'birkie': (BIRKIE_DAYS, LEAVE_OUT_YEARS, {'classic': CLASSIC_COURSES}, 'birkie', ''),
         'kortie': (KORTIE_DAYS, KORTIE_LEAVE_OUT_YEARS, {'skate': KORTIE_COURSES, 'classic': KORTIE_CLASSIC_COURSES},
                    'kortie', 'kortie '),
         **{race: (PREBIRKIE_DAYS, [], {'skate': PREBIRKIE_COURSES, 'classic': PREBIRKIE_COURSES}, 'pre-birkie', 'pre ')
            for race in PREBIRKIE_RACES}}
RACE_GROUPS = {'birkie': ['birkie'], 'kortie': ['kortie'], 'prebirkie': PREBIRKIE_RACES}
RACE_TITLES = {'birkie': 'Birkie', 'kortie': 'Kortelopet', 'pre-birkie': 'Pre-Birkie'}
#six series is too many to tell apart by color alone, so the color is the technique and the marker the race
TECH_COLORS = {'skate': '#2a78d6', 'classic': '#eb6834'}
RACE_MARKERS = {'birkie': ('o', 7), 'kortie': ('s', 6), 'pre-birkie': ('^', 8)}
#candidate models, each on top of a separate level for each technique. MAIN is the simple one plotted
MAIN = ['new_snow', 'thaws']
MAIN_NAME = 'new snow along the course + thaw days'
EXTRAS = {'+ race temperature, below and above freezing': ['below_freezing', 'above_freezing'],
          '+ race temperature, mean': ['t_race'], '+ overnight low': ['overnight_low'],
          '+ warming during the race': ['warming'], '+ froze overnight, thawed in the race': ['thaw_in_race'],
          '+ hours snowing in the race': ['snowing_in_race'], '+ snow on race day': ['race_day_snow'],
          '+ snowpack density': ['density'], '+ snowpack temperature': ['snowpack_c'],
          '+ melt in the week before': ['melt_7d'], '+ rain in the week before': ['rain_7d'],
          '+ snow depth': ['depth_10cm']}
MODELS = {'no weather': [], 'new snow along the course': ['new_snow'], MAIN_NAME: MAIN,
          'new snow at the hayward co-op + thaw days': ['coop_new_snow', 'thaws'],
          **{name: MAIN + extra for name, extra in EXTRAS.items()},
          'every one of the above': MAIN + [k for extra in EXTRAS.values() for k in extra]}
N_BOOTSTRAP = 1000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--linked", type=str, default='linked_data/linked_results.csv')
    parser.add_argument("--refresh", action='store_true', help='download the weather again')
    parser.add_argument("--reread_snodas", action='store_true', help='read the SNODAS tars again')
    parser.add_argument("--races", nargs='+', choices=list(RACE_GROUPS), default=list(RACE_GROUPS),
                        help='the races whose race days are compared')
    parser.add_argument("--birkie_only", action='store_true', help='the birkie alone, the same as --races birkie')
    args = parser.parse_args()
    groups = ['birkie'] if args.birkie_only else [g for g in RACE_GROUPS if g in args.races]

    download(args.refresh)
    weather = race_weather(hourly_weather(), daily_weather(), course_snowpack(args.reread_snodas))
    races = [race for g in groups for race in RACE_GROUPS[g]]
    data = comparable(race_speeds(load_linked(args.linked), races).join(weather, on='date', how='inner'))

    scores = {name: cross_validate(data, terms) for name, terms in MODELS.items()}
    fit = fit_terms(data, MAIN)
    boot = bootstrap_days(data, MAIN)
    data['predicted'] = scores[MAIN_NAME]['predicted']
    checks = {race: race_check(data, race) for race in ['birkie', 'kortie']
              if race in races and data['race'].nunique() > 1}
    print_summary(data, scores, fit, boot, checks)
    name = 'weather_speed' if len(groups) == len(RACE_GROUPS) else \
        'weather_speed_' + '_'.join(groups) + ('_only' if len(groups) == 1 else '')
    plot_weather(data, fit, scores, checks, name)
    data.round(3).to_csv(os.path.join(os.path.dirname(args.linked) or '.', name + '.csv'), index=False)


#---------------------------------------------------------------- weather

def download(refresh=False):
    os.makedirs(WEATHER_DIR, exist_ok=True)
    for station in [ASOS_STATION] + ASOS_BACKUP:
        for year in range(min(BIRKIE_DAYS), max(BIRKIE_DAYS) + 1):
            path = os.path.join(WEATHER_DIR, '{}_{}.csv'.format(station.lower(), year))
            if refresh or not os.path.exists(path):
                print('downloading', path)
                urllib.request.urlretrieve(ASOS_URL.format(station=station, y0=year - 1, y1=year), path)
    #again whenever the race days now start before the saved co-op record does
    path = os.path.join(WEATHER_DIR, 'ghcn_{}.csv'.format(COOP_STATION))
    start = '{}-10-01'.format(min(BIRKIE_DAYS) - 1)
    if refresh or not os.path.exists(path) or pd.read_csv(path, nrows=1)['DATE'][0] > start:
        print('downloading', path)
        urllib.request.urlretrieve(COOP_URL.format(station=COOP_STATION, start=start), path)


def hourly_weather():
    #one row per hour at hayward: temperature (C) and whether snow was falling. hours it's missing for more than a few
    #hours in a row (it was down feb 12-16 2022, through that pre-birkie) come from the backup airports' average,
    #shifted by how much warmer or colder hayward usually is than them
    h = station_hourly(ASOS_STATION)
    backup = [station_hourly(s) for s in ASOS_BACKUP]
    h = h.reindex(pd.date_range(min(b.index.min() for b in backup + [h]), max(b.index.max() for b in backup + [h]),
                                freq='h'))
    backup_t = pd.concat([b['t'] for b in backup], axis=1).reindex(h.index).mean(axis=1)
    backup_snowing = pd.concat([b['snowing'] for b in backup], axis=1).reindex(h.index).max(axis=1)
    h['t'] = h['t'].interpolate(limit=3)
    h['t'] = h['t'].fillna(backup_t + (h['t'] - backup_t).mean())
    h['snowing'] = h['snowing'].astype(float).fillna(backup_snowing.astype(float)).fillna(0) > 0
    return h


def station_hourly(station):
    #from the routine reports just before each hour
    paths = sorted(glob.glob(os.path.join(WEATHER_DIR, '{}_*.csv'.format(station.lower()))))
    h = pd.concat([pd.read_csv(p, na_values=['M']) for p in paths])
    h['valid'] = pd.to_datetime(h['valid'])
    h['snowing'] = h['wxcodes'].fillna('').str.contains(r'(?:^|\s)[-+]?(?:SH|BL|DR)?SN')
    h = h[h['valid'].dt.minute.between(50, 59)].copy()
    h['hour'] = h['valid'].dt.floor('h') + pd.Timedelta(hours=1)
    h['t'] = (h['tmpf'] - 32) / 1.8
    return h.groupby('hour').agg(t=('t', 'mean'), snowing=('snowing', 'max'))


def daily_weather():
    d = pd.read_csv(os.path.join(WEATHER_DIR, 'ghcn_{}.csv'.format(COOP_STATION)), parse_dates=['DATE'])
    #a missing day is usually folded into the next day's report, so it counts as no snow
    return d.set_index('DATE')['SNOW'].fillna(0)


def course_cells(land):
    #flat grid indexes of the land within COURSE_KM of the line from cable to hayward
    (lat0, lon0), (lat1, lon1) = COURSE_LINE
    rows = np.arange(int((NORTH_CENTER - max(lat0, lat1)) / CELL) - 60, int((NORTH_CENTER - min(lat0, lat1)) / CELL) + 60)
    cols = np.arange(int((min(lon0, lon1) - WEST_CENTER) / CELL) - 60, int((max(lon0, lon1) - WEST_CENTER) / CELL) + 60)
    r, c = np.meshgrid(rows, cols, indexing='ij')
    lat, lon = NORTH_CENTER - r * CELL, WEST_CENTER + c * CELL
    #distance to the segment, on a flat km grid around the course
    kx, ky = 111.2 * np.cos(np.radians((lat0 + lat1) / 2)), 111.2
    px, py, ax, ay, bx, by = lon * kx, lat * ky, lon0 * kx, lat0 * ky, lon1 * kx, lat1 * ky
    t = np.clip(((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2), 0, 1)
    km = np.hypot(px - (ax + t * (bx - ax)), py - (ay + t * (by - ay)))
    cells = (r * N_COLS + c)[km <= COURSE_KM].astype(np.int64)
    return cells[land[cells]]


def set_course(cells):
    global COURSE
    COURSE = cells


def grid_scale(header):
    #"Data units: Meters / 1000.000000" -> what to multiply the stored integers by
    line = next(l for l in header.splitlines() if l.lower().startswith('data units'))
    unit, _, divisor = line.split(':', 1)[1].partition('/')
    return UNIT_TO[unit.strip()] / float(divisor or 1)


def course_day(path):
    #one tar: each grid's average over the course
    out = {}
    with tarfile.open(path) as t:
        names = t.getnames()
        for code, name in SNODAS_GRIDS.items():
            data = next((n for n in names if code in n and n.endswith('.dat.gz')), None)
            if data is None:
                continue
            header = gzip.decompress(t.extractfile(data.replace('.dat.gz', '.txt.gz')).read()).decode('latin1')
            grid = np.frombuffer(gzip.decompress(t.extractfile(data).read()), dtype='>i2')
            values = grid[COURSE].astype(float)
            values = values[values != NO_DATA]
            out[name] = values.mean() * grid_scale(header) if len(values) else np.nan
    return out


def course_snowpack(refresh=False, workers=6):
    #SNODAS along the course for the LOOKBACK_DAYS before each race and the race day after, cached. days the cache
    #doesn't have yet (a race day added since) are read from the tars and added to it
    path = os.path.join(WEATHER_DIR, 'snodas_course.csv')
    cached = None
    if os.path.exists(path) and not refresh:
        cached = pd.read_csv(path, parse_dates=['date']).set_index('date')
    days = sorted({d for day in race_days() for d in pd.date_range(day - pd.Timedelta(days=LOOKBACK_DAYS),
                                                                    day + pd.Timedelta(days=1))})
    if cached is not None:
        days = [d for d in days if d not in cached.index]
        if not days:
            return cached
    paths = tar_files([TAR_DIR, NEW_TAR_DIR])
    #a few days have no SNODAS at all
    days = [d for d in days if d in paths.index]
    if not days:
        return cached
    cells = course_cells(land_cells(paths))
    print('reading SNODAS for {} days over {} course cells'.format(len(days), len(cells)))
    with concurrent.futures.ProcessPoolExecutor(workers, initializer=set_course, initargs=(cells,)) as pool:
        rows = list(pool.map(course_day, [paths[d] for d in days], chunksize=4))
    snow = pd.DataFrame(rows, index=pd.DatetimeIndex(days, name='date'))
    if cached is not None:
        snow = pd.concat([cached, snow]).sort_index()
    snow.round(3).to_csv(path)
    return snow


def race_days():
    #every race day of every race that's compared
    return sorted({pd.Timestamp(d) for days, leave_out, *_ in RACES.values() for y, d in days.items()
                   if y not in leave_out})


def race_weather(hourly, snowfall, snodas):
    #the weather for every race day, by date
    rows = {}
    daily_max = hourly['t'].resample('D').max()
    for day in race_days():
        start, end = day + pd.Timedelta(hours=RACE_HOURS[0]), day + pd.Timedelta(hours=RACE_HOURS[1] - 1)
        race = hourly.loc[start:end]
        night = hourly.loc[day - pd.Timedelta(hours=6):start - pd.Timedelta(hours=1), 't']
        #co-op snowfall reports back from the race day, and the thaw days since the last real snowfall
        back = snowfall.reindex(pd.date_range(day - pd.Timedelta(days=LOOKBACK_DAYS - 1), day))[::-1].fillna(0).values
        snowed = np.where(back >= SNOWFALL_IN)[0]
        since = int(snowed[0]) if len(snowed) else LOOKBACK_DAYS
        thaws = int((daily_max.loc[day - pd.Timedelta(days=since):day - pd.Timedelta(days=1)] > 0).sum()) if since else 0
        #SNODAS along the course, back from race eve (the tar dated race day: the snowpack at midnight before it)
        sn = snodas.reindex(pd.date_range(day - pd.Timedelta(days=LOOKBACK_DAYS - 1), day))[::-1]
        eve = sn.iloc[0]
        rows[day] = {
            'new_snow': sn['snowfall_mm'].iloc[:NEW_SNOW_DAYS].sum(),
            'coop_new_snow': back[:NEW_SNOW_DAYS].sum(), 'days_since_snowfall': since, 'thaws': thaws,
            't_race': race['t'].mean(), 'below_freezing': np.maximum(-race['t'], 0).mean(),
            'above_freezing': np.maximum(race['t'], 0).mean(), 'overnight_low': night.min(),
            'warming': hourly.loc[end, 't'] - hourly.loc[start, 't'],
            'thaw_in_race': float(night.min() < 0 and (race['t'] > 0).any()),
            'snowing_in_race': race['snowing'].sum(),
            'race_day_snow': snodas['snowfall_mm'].get(day + pd.Timedelta(days=1), np.nan),
            'density': 1000 * eve['swe_mm'] / eve['depth_mm'], 'snowpack_c': eve['snowpack_k'] - 273.15,
            'melt_7d': sn['melt_mm'].iloc[:7].sum(), 'rain_7d': sn['rain_mm'].iloc[:7].sum(),
            'depth_10cm': eve['depth_mm'] / 100}
    return pd.DataFrame(rows).T.astype(float)


#---------------------------------------------------------------- model

def race_speeds(linked, races):
    #% slower than the average race on the same course for the same skiers, every race day of each race and technique.
    #each has a level of its own (one for each course), so only the race days on one course are compared. the year to
    #year model measures each race from its average year, which mixes courses when a race has moved (the kortelopet's
    #29 km races are 25% slower than its 23 km ones), so each is measured again from its own course's average
    rows = []
    for race in races:
        days, leave_out, courses, name, prefix = RACES[race]
        for tech in TECHS:
            panel = build_panel(linked, race, tech)
            if panel.empty:
                continue
            fit = fit_model(panel)
            for condition, effect in fit['conditions']['effect'].items():
                year = int(condition.split()[0])
                if year in leave_out:
                    continue
                course = next((c for c, years in courses.get(tech, {}).items() if year in years), '')
                date = pd.Timestamp(days[year])
                rows.append({'race': race, 'tech': tech, 'condition': condition, 'effect': effect, 'date': date,
                             'weekend': weekend(date),
                             'label': prefix + condition + (' short' if race.endswith('short') else ''),
                             'series': name + ' ' + tech, 'level': ' '.join([race, tech, course]).strip()})
    rows = pd.DataFrame(rows)
    rows['slower'] = 100 * np.expm1(rows['effect'] - rows.groupby('level')['effect'].transform('mean'))
    return rows.drop(columns='effect')


def weekend(day):
    #the monday starting the week of a race day: the birkie and the kortelopet the day before it share one
    return day.to_period('W').start_time


def without_birkie_weekend(data, year):
    #every race day but that year's birkie and kortelopet
    return data['weekend'] != weekend(pd.Timestamp(BIRKIE_DAYS[year]))


def comparable(data):
    #race days with every weather measure (SNODAS starts in the 2003-04 winter), on a course raced on more than one of
    #them: a course with one race day says nothing about the weather
    terms = sorted({k for terms in MODELS.values() for k in terms})
    complete = data[terms].notna().all(axis=1)
    if (~complete).any():
        print('left out for missing weather:', ', '.join(sorted(set(data.loc[~complete, 'label']))))
    data = data[complete]
    return data[data.groupby('level')['date'].transform('nunique') > 1].reset_index(drop=True)


def design(data, terms):
    #a level for each race, technique and course, then the weather terms
    levels = sorted(data['level'].unique())
    X = np.column_stack([(data['level'] == l).astype(float) for l in levels] + [data[k] for k in terms])
    return X, levels + terms


def fit_terms(data, terms):
    X, names = design(data, terms)
    beta = np.linalg.lstsq(X, data['slower'].values, rcond=None)[0]
    return pd.Series(beta, index=names)


def explained(data, predicted):
    #share of the spread between races (within each race, technique and course) the model accounts for
    y = data['slower']
    return 1 - ((y - predicted) ** 2).sum() / ((y - y.groupby(data['level']).transform('mean')) ** 2).sum()


def cross_validate(data, terms):
    #predict each race weekend from a fit to all the other race weekends
    X, _ = design(data, terms)
    y = data['slower'].values
    predicted = np.empty(len(y))
    for week in data['weekend'].unique():
        out = (data['weekend'] == week).values
        predicted[out] = X[out] @ np.linalg.lstsq(X[~out], y[~out], rcond=None)[0]
    in_sample = X @ np.linalg.lstsq(X, y, rcond=None)[0]
    return {'predicted': predicted, 'cv': explained(data, predicted), 'in_sample': explained(data, in_sample),
            'rmse': np.sqrt(np.mean((y - predicted) ** 2))}


def race_check(data, race):
    #do the other races help predict this one? how far off each of its race days is when predicted from every other
    #race weekend, from its own other race days only, and with no weather at all
    own = comparable(data[data['race'] == race])
    on = (data['race'] == race).values
    return {'every race': np.sqrt(np.mean((data['slower'] - data['predicted'])[on] ** 2)),
            'own race': cross_validate(own, MAIN)['rmse'], 'no weather': cross_validate(own, [])['rmse']}


def bootstrap_days(data, terms, n=N_BOOTSTRAP, seed=0):
    #resample whole race weekends
    weeks = data['weekend'].unique()
    rows = data.groupby('weekend').indices
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n):
        pick = np.concatenate([rows[w] for w in rng.choice(weeks, len(weeks))])
        draws.append(fit_terms(data.iloc[pick], terms))
    return pd.DataFrame(draws)


#---------------------------------------------------------------- output

def print_summary(data, scores, fit, boot, checks):
    days = data.groupby('race')['date'].nunique()
    print('{} race days on {} weekends ({}), {} races. spread between race days on one course (sd):'.format(
        data['date'].nunique(), data['weekend'].nunique(), ', '.join('{} {}'.format(n, r) for r, n in days.items()),
        len(data)))
    spread = data['slower'] - data.groupby('level')['slower'].transform('mean')
    for series, s in spread.groupby(data['series']):
        print('  {:20s} {:.1f}% over {} races'.format(series, s.std(), len(s)))
    print('\nshare of the spread between races explained, fit to every race / predicting each race day from the rest:')
    for name, s in scores.items():
        print('  {:48s} {:5.2f}  {:5.2f}   (miss by {:.1f}% on average)'.format(name, s['in_sample'], s['cv'], s['rmse']))
    print('\n{}, % slower per mm of new snow water and per thaw day [95% CI over race days]:'.format(MAIN_NAME))
    for k in MAIN:
        print('  {:10s} {:+.2f} [{:+.2f}, {:+.2f}]'.format(k, fit[k], *boot[k].quantile([0.025, 0.975])))
    #a few race weekends carry each term: 2014 the new snow, 2010 and 2026 (7 and 10 thaw days) the thaws
    without = {'without {}'.format(y): without_birkie_weekend(data, y) for y in [2014, 2010, 2026]}
    subsets = [('birkie only', data['race'] == 'birkie'), ('kortie only', data['race'] == 'kortie'),
               ('pre-birkie only', data['race'].isin(PREBIRKIE_RACES)),
               ('birkie and kortie', data['race'].isin(['birkie', 'kortie'])),
               ('skate only', data['tech'] == 'skate'), ('classic only', data['tech'] == 'classic'), *without.items()]
    for label, keep in subsets:
        sub = data[keep].reset_index(drop=True)
        if sub['weekend'].nunique() < 4:
            continue
        f = fit_terms(sub, MAIN)
        cv = cross_validate(sub, MAIN)
        print('  {:22s} new snow {:+.2f}  thaws {:+.2f}  (explained {:.2f}, predicting {:.2f}, {} race days)'.format(
            label, f['new_snow'], f['thaws'], cv['in_sample'], cv['cv'], sub['date'].nunique()))
    for race, check in checks.items():
        print('\npredicting each {} race day: misses by {:.1f}% from its other race days, {:.1f}% with the other races '
              'too ({:.1f}% with no weather)'.format(race, check['own race'], check['every race'], check['no weather']))
    cols = ['label', 'tech', 'level', 'slower', 'predicted', 'new_snow', 'coop_new_snow', 'thaws', 't_race']
    print('\nevery race, % slower than average and the prediction from the other race days:')
    print(data[cols].sort_values(['level', 'label']).round(1).to_string(index=False))


def plot_series(ax, data, x, y):
    #every race and technique, each with its own marker and color
    for race, (marker, size) in RACE_MARKERS.items():
        for tech, color in TECH_COLORS.items():
            on = data['series'] == race + ' ' + tech
            if on.any():
                ax.plot(x[on], y[on], marker, color=color, markersize=size, markeredgecolor=SURFACE,
                        markeredgewidth=1.2, linestyle='none', label=race + ' ' + tech)


def plot_weather(data, fit, scores, checks=None, name='weather_speed'):
    fig = plt.figure(figsize=(14, 10), facecolor=SURFACE)
    grid = fig.add_gridspec(2, 2, hspace=0.38, wspace=0.22, top=0.9)

    #each term's share, with the other one taken out: partial residuals. and how much it leans on its extreme years
    level = data['level'].map(fit)
    leans = {}
    for term, years in [('new_snow', [2014]), ('thaws', [2010, 2026])]:
        parts = []
        for y in years:
            sub = data[without_birkie_weekend(data, y)].reset_index(drop=True)
            parts.append('without {}: {:+.1f}, misses unseen races by {:.1f}% (no weather: {:.1f}%)'.format(
                y, fit_terms(sub, MAIN)[term], cross_validate(sub, MAIN)['rmse'], cross_validate(sub, [])['rmse']))
        leans[term] = '\n'.join(parts)
    for i, (term, title, xlabel) in enumerate([
            ('new_snow', 'New snow slows the race: about {:.1f}% per mm of water',
             'new snow in the 3 days to race eve, mm of water (SNODAS, along the course)'),
            ('thaws', 'Thaws since the last snowfall speed it up: {:.1f}% a day',
             'days above freezing since the last 1"+ snowfall (Hayward airport)')]):
        ax = fig.add_subplot(grid[0, i])
        other = [k for k in MAIN if k != term]
        partial = data['slower'] - level - sum(fit[k] * data[k] for k in other)
        ax.axhline(0, color=INK_2, linewidth=0.8)
        xs = np.array([data[term].min(), data[term].max()])
        ax.plot(xs, fit[term] * xs - (fit[term] * data[term]).mean() + partial.mean(), color=INK_2, linewidth=1.2,
                linestyle='--')
        plot_series(ax, data, data[term], partial)
        for _, r in data.loc[partial.abs().sort_values().index[-4:]].iterrows():
            ax.annotate(r['label'], (r[term], partial[_]), xytext=(6, 2), textcoords='offset points', fontsize=7,
                        color=INK_2)
        lo_y, hi_y = ax.get_ylim()
        ax.set_ylim(lo_y - 0.2 * (hi_y - lo_y), hi_y)
        ax.text(0.97, 0.03, leans[term], transform=ax.transAxes, fontsize=8, color=INK_2, ha='right')
        style(ax, title.format(abs(fit[term])), '% slower than the average race, other term taken out', xlabel)

    #how well it predicts a race it hasn't seen
    ax = fig.add_subplot(grid[1, 0])
    lim = [min(data['slower'].min(), data['predicted'].min()) - 2, max(data['slower'].max(), data['predicted'].max()) + 2]
    ax.plot(lim, lim, color=GRID, linewidth=1.2)
    plot_series(ax, data, data['predicted'], data['slower'])
    s = scores[MAIN_NAME]
    ax.set_ylim(lim[0], lim[1] + 0.3 * (lim[1] - lim[0]))
    worst = data.loc[(data['slower'] - data['predicted']).abs().sort_values().index[-5:]]
    place_labels(ax, [((r['predicted'], r['slower']), '{} {}'.format(r['label'], r['tech']),
                       {'fontsize': 7, 'color': INK_2}) for _, r in worst.iterrows()], size=(80, 8))
    note = '{:.0%} of the spread between races explained fit to every race'.format(s['in_sample'])
    if checks:
        note = 'each race day missed by, predicted from every other race weekend /\nfrom its own race only / with no ' \
               'weather:\n' + '\n'.join('  {:8s} {:.1f}% / {:.1f}% / {:.1f}%'.format(
                   race, c['every race'], c['own race'], c['no weather']) for race, c in checks.items())
    ax.text(0.03, 0.97, note, transform=ax.transAxes, fontsize=8, color=INK_2, va='top')
    style(ax, 'Unseen race days: off by {:.1f}% on average, {:.1f}% with no weather'.format(
        s['rmse'], scores['no weather']['rmse']), '% slower than the average race, actual',
          'predicted from the other race weekends')

    #temperature during the race, after new snow and thaws
    ax = fig.add_subplot(grid[1, 1])
    resid = data['slower'] - (design(data, MAIN)[0] @ fit.values)
    ax.axhline(0, color=INK_2, linewidth=0.8)
    ax.axvline(0, color=GRID, linewidth=1.2)
    plot_series(ax, data, data['t_race'], resid)
    for _, r in data.loc[resid.abs().sort_values().index[-4:]].iterrows():
        ax.annotate('{} {}'.format(r['label'], r['tech']), (r['t_race'], resid[_]), xytext=(6, 2),
                    textcoords='offset points', fontsize=7, color=INK_2)
    t = scores['+ race temperature, below and above freezing']
    lo_y, hi_y = ax.get_ylim()
    ax.set_ylim(lo_y, hi_y + 0.25 * (hi_y - lo_y))
    ax.text(0.03, 0.97, 'adding race temperature, split at freezing: unseen races missed by {:.1f}% on average,\n'
            'against {:.1f}% without it'.format(t['rmse'], s['rmse']), transform=ax.transAxes, fontsize=8,
            color=INK_2, va='top')
    style(ax, 'Race-day temperature adds nothing reliable', 'what new snow and thaws leave unexplained, %',
          'average temperature 8am to 2pm, C (Hayward airport)')

    titles = [RACE_TITLES[r] for r in RACE_MARKERS if (data['series'].str.rsplit(n=1).str[0] == r).any()]
    races = ', '.join(titles[:-1]) + ' and ' + titles[-1] if len(titles) > 1 else titles[0]
    fig.suptitle('Weather and {} speed: each race day, the same skiers compared from one year to the next'.format(
        races), x=0.06, ha='left', fontsize=13, color=INK)
    handles, labels = fig.axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper left', bbox_to_anchor=(0.06, 0.955), ncol=len(labels), fontsize=9,
               frameon=False)
    os.makedirs('graphs', exist_ok=True)
    fig.savefig('graphs/{}.png'.format(name), dpi=130, bbox_inches='tight', facecolor=SURFACE)
    plt.close(fig)


if __name__ == '__main__':
    main()
