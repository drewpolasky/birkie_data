#can the weather say how fast a birkie will be? each race's speed comes from the year to year model in
#performance_changes.py (the same skiers compared from one race to the next, so it isn't about who showed up), and
#is set against the weather around the course:
#   hourly: hayward municipal airport (HYR, at the finish end) from the iowa environmental mesonet, for temperature
#           and when it was snowing. its heated gauge reports most snow as a trace, so it can't say how much fell
#   daily:  the hayward ranger station co-op (GHCN USC00473511) for snowfall amounts. its daily totals end around
#           midday, so the race day's report covers the night before and the race morning
#   SNODAS: snow depth on the course, the average of cable and hayward (snow_depth.py's output)
#each race is one data point per technique, so there are only 15 of each. every model is judged by leaving out one
#race day at a time and predicting it from the others, skate and classic together. 2021 is left out: it was a
#different course, so its speed isn't comparable.
#
#example usage:
#python weather_speed.py              downloads the weather into weather_data/ the first time
import argparse
import glob
import os
import urllib.request

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from performance_changes import load_linked, build_panel, fit_model, style, INK, INK_2, GRID, SURFACE
from snow_effect import RACE_DAYS

WEATHER_DIR = 'weather_data'
ASOS_STATION = 'HYR'
COOP_STATION = 'USC00473511'
ASOS_URL = ('https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station={station}&data=tmpf&data=wxcodes'
            '&year1={y0}&month1=11&day1=1&year2={y1}&month2=3&day2=15&tz=America%2FChicago&format=onlycomma'
            '&latlon=no&elev=no&missing=M&trace=T&direct=no&report_type=3&report_type=4')
COOP_URL = ('https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries&stations={station}'
            '&startDate=2008-10-01&endDate=2026-04-01&dataTypes=SNOW,SNWD,PRCP,TMAX,TMIN&format=csv&units=standard')
COURSE_TOWNS = [('cable', 'WI'), ('hayward', 'WI')]
LEAVE_OUT_YEARS = [2017, 2021, 2024]    #cancelled, a different course, and the shortened course
RACE_HOURS = (8, 14)                    #the field is mostly on course from 8am to 2pm
NEW_SNOW_DAYS = 3                       #race day's co-op report and the two before it
SNOWFALL_IN = 1.0                       #a snowfall, for counting thaw days since the last one
LOOKBACK_DAYS = 30
TECHS = ['skate', 'classic']
COLORS = {'skate': '#2a78d6', 'classic': '#eb6834'}
#candidate models, each on top of a separate level for each technique. the first is the simple one plotted
MAIN = ['new_snow', 'thaws']
MODELS = {'technique only': [], 'new snow': ['new_snow'], 'new snow + thaw days': MAIN,
          '+ race temperature, below and above freezing': MAIN + ['below_freezing', 'above_freezing'],
          '+ race temperature, mean': MAIN + ['t_race'], '+ overnight low': MAIN + ['overnight_low'],
          '+ warming during the race': MAIN + ['warming'], '+ froze overnight, thawed in the race': MAIN + ['thaw_in_race'],
          '+ hours snowing in the race': MAIN + ['snowing_in_race'], '+ course snow depth': MAIN + ['depth_10cm'],
          'every one of the above': ['new_snow', 'thaws', 'below_freezing', 'above_freezing', 'overnight_low',
                                     'thaw_in_race', 'snowing_in_race', 'depth_10cm']}
N_BOOTSTRAP = 1000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--linked", type=str, default='linked_data/linked_results.csv')
    parser.add_argument("--snow", type=str, default='snow_data', help='folder with snow_depth.py\'s output')
    parser.add_argument("--refresh", action='store_true', help='download the weather again')
    args = parser.parse_args()

    download(args.refresh)
    weather = race_weather(hourly_weather(), daily_weather(), course_depth(args.snow))
    data = race_speeds(load_linked(args.linked)).join(weather, on='condition', how='inner')
    data = data.reset_index(drop=True)

    scores = {name: cross_validate(data, terms) for name, terms in MODELS.items()}
    fit = fit_terms(data, MAIN)
    boot = bootstrap_days(data, MAIN)
    data['predicted'] = scores['new snow + thaw days']['predicted']
    print_summary(data, scores, fit, boot)
    plot_weather(data, fit, scores)
    data.round(3).to_csv(os.path.join(os.path.dirname(args.linked) or '.', 'weather_speed.csv'), index=False)


#---------------------------------------------------------------- weather

def download(refresh=False):
    os.makedirs(WEATHER_DIR, exist_ok=True)
    for year in range(min(RACE_DAYS), max(RACE_DAYS) + 1):
        path = os.path.join(WEATHER_DIR, '{}_{}.csv'.format(ASOS_STATION.lower(), year))
        if refresh or not os.path.exists(path):
            print('downloading', path)
            urllib.request.urlretrieve(ASOS_URL.format(station=ASOS_STATION, y0=year - 1, y1=year), path)
    path = os.path.join(WEATHER_DIR, 'ghcn_{}.csv'.format(COOP_STATION))
    if refresh or not os.path.exists(path):
        print('downloading', path)
        urllib.request.urlretrieve(COOP_URL.format(station=COOP_STATION), path)


def hourly_weather():
    #one row per hour: temperature (C) and whether snow was falling, from the routine reports just before each hour
    paths = sorted(glob.glob(os.path.join(WEATHER_DIR, '{}_*.csv'.format(ASOS_STATION.lower()))))
    h = pd.concat([pd.read_csv(p, na_values=['M']) for p in paths])
    h['valid'] = pd.to_datetime(h['valid'])
    h['snowing'] = h['wxcodes'].fillna('').str.contains(r'(?:^|\s)[-+]?(?:SH|BL|DR)?SN')
    h = h[h['valid'].dt.minute.between(50, 59)].copy()
    h['hour'] = h['valid'].dt.floor('h') + pd.Timedelta(hours=1)
    h['t'] = (h['tmpf'] - 32) / 1.8
    h = h.groupby('hour').agg(t=('t', 'mean'), snowing=('snowing', 'max'))
    h = h.reindex(pd.date_range(h.index.min(), h.index.max(), freq='h'))
    h['t'] = h['t'].interpolate(limit=3)
    h['snowing'] = h['snowing'].astype(float).fillna(0) > 0
    return h


def daily_weather():
    d = pd.read_csv(os.path.join(WEATHER_DIR, 'ghcn_{}.csv'.format(COOP_STATION)), parse_dates=['DATE'])
    #a missing day is usually folded into the next day's report, so it counts as no snow
    return d.set_index('DATE')['SNOW'].fillna(0)


def course_depth(snow_dir):
    towns = pd.read_csv(os.path.join(snow_dir, 'hometowns.csv'))
    ids = [towns.loc[(towns['city'] == c) & (towns['state'] == s), 'hometown_id'].iloc[0] for c, s in COURSE_TOWNS]
    depth = pd.read_parquet(os.path.join(snow_dir, 'hometown_snow_depth.parquet'), columns=['hometown_id', 'date',
                                                                                             'depth_10km_mm'])
    return depth[depth['hometown_id'].isin(ids)].groupby('date')['depth_10km_mm'].mean() / 10


def race_days():
    #every race day by its conditions label in performance_changes.py
    return {str(y): pd.Timestamp(d) for y, d in RACE_DAYS.items() if y not in LEAVE_OUT_YEARS}


def race_weather(hourly, snowfall, depth):
    rows = {}
    for condition, day in race_days().items():
        start, end = day + pd.Timedelta(hours=RACE_HOURS[0]), day + pd.Timedelta(hours=RACE_HOURS[1] - 1)
        race = hourly.loc[start:end]
        night = hourly.loc[day - pd.Timedelta(hours=6):start - pd.Timedelta(hours=1), 't']
        #snowfall reports back from the race day, and the days since the last real snowfall
        back = snowfall.reindex(pd.date_range(day - pd.Timedelta(days=LOOKBACK_DAYS - 1), day))[::-1].fillna(0).values
        snowed = np.where(back >= SNOWFALL_IN)[0]
        since = int(snowed[0]) if len(snowed) else LOOKBACK_DAYS
        daily_max = hourly['t'].resample('D').max()
        thaws = int((daily_max.loc[day - pd.Timedelta(days=since):day - pd.Timedelta(days=1)] > 0).sum()) if since else 0
        rows[condition] = {
            'date': day, 'new_snow': back[:NEW_SNOW_DAYS].sum(), 'days_since_snowfall': since, 'thaws': thaws,
            't_race': race['t'].mean(), 'below_freezing': np.maximum(-race['t'], 0).mean(),
            'above_freezing': np.maximum(race['t'], 0).mean(), 'overnight_low': night.min(),
            'warming': hourly.loc[end, 't'] - hourly.loc[start, 't'],
            'thaw_in_race': float(night.min() < 0 and (race['t'] > 0).any()),
            'snowing_in_race': race['snowing'].sum(), 'depth_10cm': depth.get(day, np.nan) / 10}
    return pd.DataFrame(rows).T.astype({k: float for k in rows[next(iter(rows))] if k != 'date'})


#---------------------------------------------------------------- model

def race_speeds(linked):
    #% slower than the average race for the same skiers, every race day of each technique
    rows = []
    for tech in TECHS:
        fit = fit_model(build_panel(linked, 'birkie', tech))
        for condition, pct in fit['conditions']['pct'].items():
            rows.append({'tech': tech, 'condition': condition, 'slower': pct})
    return pd.DataFrame(rows)


def design(data, terms):
    X = np.column_stack([(data['tech'] == t).astype(float) for t in TECHS] + [data[k] for k in terms])
    return X, TECHS + terms


def fit_terms(data, terms):
    X, names = design(data, terms)
    beta = np.linalg.lstsq(X, data['slower'].values, rcond=None)[0]
    return pd.Series(beta, index=names)


def explained(data, predicted):
    #share of the spread between races (within each technique) the model accounts for
    y = data['slower']
    return 1 - ((y - predicted) ** 2).sum() / ((y - y.groupby(data['tech']).transform('mean')) ** 2).sum()


def cross_validate(data, terms):
    #predict each race day from a fit to all the other race days
    X, _ = design(data, terms)
    y = data['slower'].values
    predicted = np.empty(len(y))
    for day in data['date'].unique():
        out = (data['date'] == day).values
        predicted[out] = X[out] @ np.linalg.lstsq(X[~out], y[~out], rcond=None)[0]
    in_sample = X @ np.linalg.lstsq(X, y, rcond=None)[0]
    return {'predicted': predicted, 'cv': explained(data, predicted), 'in_sample': explained(data, in_sample),
            'rmse': np.sqrt(np.mean((y - predicted) ** 2))}


def bootstrap_days(data, terms, n=N_BOOTSTRAP, seed=0):
    #resample whole race days
    days = data['date'].unique()
    rows = data.groupby('date').indices
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n):
        pick = np.concatenate([rows[d] for d in rng.choice(days, len(days))])
        draws.append(fit_terms(data.iloc[pick], terms))
    return pd.DataFrame(draws)


#---------------------------------------------------------------- output

def print_summary(data, scores, fit, boot):
    print('{} race days, {} skate and {} classic. spread between races: skate {:.1f}%, classic {:.1f}% (sd)'.format(
        data['date'].nunique(), (data['tech'] == 'skate').sum(), (data['tech'] == 'classic').sum(),
        *[data.loc[data['tech'] == t, 'slower'].std() for t in TECHS]))
    print('\nshare of the spread between races explained, fit to every race / predicting each race day from the rest:')
    for name, s in scores.items():
        print('  {:48s} {:5.2f}  {:5.2f}   (miss by {:.1f}% on average)'.format(name, s['in_sample'], s['cv'], s['rmse']))
    print('\nnew snow + thaw days, % slower [95% CI over race days]:')
    for k in MAIN:
        print('  {:10s} {:+.2f} [{:+.2f}, {:+.2f}]'.format(k, fit[k], *boot[k].quantile([0.025, 0.975])))
    #a few races carry each term: 2014 the new snow, 2010 and 2026 (7 and 10 thaw days) the thaws
    without = {'without {}'.format(y): data['condition'] != str(y) for y in [2014, 2010, 2026]}
    for label, keep in [('skate only', data['tech'] == 'skate'), ('classic only', data['tech'] == 'classic'),
                        *without.items()]:
        sub = data[keep].reset_index(drop=True)
        f = fit_terms(sub, MAIN)
        print('  {:22s} new snow {:+.2f}  thaws {:+.2f}  (explained {:.2f}, predicting {:.2f})'.format(
            label, f['new_snow'], f['thaws'], cross_validate(sub, MAIN)['in_sample'], cross_validate(sub, MAIN)['cv']))
    cols = ['tech', 'condition', 'slower', 'predicted', 'new_snow', 'thaws', 't_race', 'overnight_low', 'snowing_in_race']
    print('\nevery race, % slower than average and the prediction from the other race days:')
    print(data[cols].sort_values(['tech', 'condition']).round(1).to_string(index=False))


def plot_weather(data, fit, scores):
    fig = plt.figure(figsize=(14, 10), facecolor=SURFACE)
    grid = fig.add_gridspec(2, 2, hspace=0.38, wspace=0.22, top=0.9)

    #each term's share, with the other one taken out: partial residuals. and how much it leans on its extreme years
    level = data['tech'].map(fit[TECHS])
    leans = {}
    for term, years in [('new_snow', ['2014']), ('thaws', ['2010', '2026'])]:
        parts = []
        for y in years:
            sub = data[data['condition'] != y].reset_index(drop=True)
            parts.append('without {}: {:+.1f}, misses unseen races by {:.1f}% (no weather: {:.1f}%)'.format(
                y, fit_terms(sub, MAIN)[term], cross_validate(sub, MAIN)['rmse'], cross_validate(sub, [])['rmse']))
        leans[term] = '\n'.join(parts)
    for i, (term, title, xlabel) in enumerate([
            ('new_snow', 'New snow slows the race: about {:.1f}% per inch', 'new snow in the 3 days to race morning, '
                                                                               'inches (Hayward co-op)'),
            ('thaws', 'Thaws since the last snowfall speed it up: {:.1f}% a day',
             'days above freezing since the last 1"+ snowfall (Hayward airport)')]):
        ax = fig.add_subplot(grid[0, i])
        other = [k for k in MAIN if k != term]
        partial = data['slower'] - level - sum(fit[k] * data[k] for k in other)
        ax.axhline(0, color=INK_2, linewidth=0.8)
        xs = np.array([data[term].min(), data[term].max()])
        ax.plot(xs, fit[term] * xs - (fit[term] * data[term]).mean() + partial.mean(), color=INK_2, linewidth=1.2,
                linestyle='--')
        for tech in TECHS:
            d = data[data['tech'] == tech]
            ax.plot(d[term], partial[d.index], 'o', color=COLORS[tech], markersize=7, markeredgecolor=SURFACE,
                    markeredgewidth=1.2, label=tech)
        for _, r in data.loc[partial.abs().sort_values().index[-4:]].iterrows():
            ax.annotate(r['condition'], (r[term], partial[_]), xytext=(6, 2), textcoords='offset points', fontsize=7,
                        color=INK_2)
        lo_y, hi_y = ax.get_ylim()
        ax.set_ylim(lo_y - 0.2 * (hi_y - lo_y), hi_y)
        ax.text(0.97, 0.03, leans[term], transform=ax.transAxes, fontsize=8, color=INK_2, ha='right')
        style(ax, title.format(abs(fit[term])), '% slower than the average race, other term taken out', xlabel)
        ax.legend(loc='upper left' if term == 'new_snow' else 'upper right', fontsize=8, frameon=False)

    #how well it predicts a race it hasn't seen
    ax = fig.add_subplot(grid[1, 0])
    lim = [min(data['slower'].min(), data['predicted'].min()) - 2, max(data['slower'].max(), data['predicted'].max()) + 2]
    ax.plot(lim, lim, color=GRID, linewidth=1.2)
    for tech in TECHS:
        d = data[data['tech'] == tech]
        ax.plot(d['predicted'], d['slower'], 'o', color=COLORS[tech], markersize=7, markeredgecolor=SURFACE,
                markeredgewidth=1.2, label=tech)
    for _, r in data.loc[(data['slower'] - data['predicted']).abs().sort_values().index[-5:]].iterrows():
        ax.annotate('{} {}'.format(r['condition'], r['tech']), (r['predicted'], r['slower']), xytext=(6, 2),
                    textcoords='offset points', fontsize=7, color=INK_2)
    s = scores['new snow + thaw days']
    ax.set_ylim(lim[0], lim[1] + 0.3 * (lim[1] - lim[0]))
    ax.text(0.03, 0.97, 'predicting each race day from the others misses by {:.1f}% on average ({:.1f}% with no\n'
            'weather), {:.0%} of the spread between races explained ({:.0%} fit to every race)'.format(
                s['rmse'], scores['technique only']['rmse'], s['cv'], s['in_sample']),
            transform=ax.transAxes, fontsize=8, color=INK_2, va='top')
    style(ax, 'New snow and thaw days predict about a quarter of it', '% slower than the average race, actual',
          'predicted from the other race days')
    ax.legend(loc='lower right', fontsize=8, frameon=False)

    #temperature during the race, after new snow and thaws
    ax = fig.add_subplot(grid[1, 1])
    resid = data['slower'] - (design(data, MAIN)[0] @ fit.values)
    ax.axhline(0, color=INK_2, linewidth=0.8)
    ax.axvline(0, color=GRID, linewidth=1.2)
    for tech in TECHS:
        d = data[data['tech'] == tech]
        ax.plot(d['t_race'], resid[d.index], 'o', color=COLORS[tech], markersize=7, markeredgecolor=SURFACE,
                markeredgewidth=1.2, label=tech)
    for _, r in data.loc[resid.abs().sort_values().index[-4:]].iterrows():
        ax.annotate('{} {}'.format(r['condition'], r['tech']), (r['t_race'], resid[_]), xytext=(6, 2),
                    textcoords='offset points', fontsize=7, color=INK_2)
    t = scores['+ race temperature, below and above freezing']
    lo_y, hi_y = ax.get_ylim()
    ax.set_ylim(lo_y, hi_y + 0.25 * (hi_y - lo_y))
    ax.text(0.03, 0.97, 'adding race temperature, split at freezing, makes predicting unseen races worse:\nmisses by '
            '{:.1f}% on average, from {:.1f}%'.format(t['rmse'], s['rmse']), transform=ax.transAxes, fontsize=8,
            color=INK_2, va='top')
    style(ax, 'Race-day temperature adds nothing reliable', 'what new snow and thaws leave unexplained, %',
          'average temperature 8am to 2pm, C (Hayward airport)')
    ax.legend(loc='lower left', fontsize=8, frameon=False)

    fig.suptitle('Weather and Birkie speed: each race day, the same skiers compared from one year to the next', x=0.06,
                 ha='left', fontsize=13, color=INK)
    os.makedirs('graphs', exist_ok=True)
    fig.savefig('graphs/weather_speed.png', dpi=130, bbox_inches='tight', facecolor=SURFACE)
    plt.close(fig)


if __name__ == '__main__':
    main()
