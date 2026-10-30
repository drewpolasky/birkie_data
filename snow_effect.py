#does a snowy winter at home make for a faster birkie? each skier's skiable days at home from november 1 to the day
#before the race, split into their town's normal (its average over 2009-2026) and how far this winter was above or
#below it, added to the year to year model from performance_changes.py:
#   log(finish time) = skier's ability + that race's conditions + age + experience
#                      + winter effect x (days - town's normal) + town effect x town's normal + noise
#the race's conditions take out everything the whole field shared that year, including the snow around the course,
#and the skier's ability takes out everything about them that doesn't change. so the winter effect only comes from
#skiers whose winter at home was snowier or leaner than normal there, compared with skiers from other places in the
#same race. that's the weather, which nobody picks. the town effect only comes from skiers who moved, and carries
#whatever else came with the move (moving up north to ski more, say), so it isn't just snow.
#
#skate and classic are fit together, with a separate ability for each skier and separate conditions for each race
#in each technique. a skiable day has at least 4 inches of snow on average within 10 km of the hometown listed in
#that year's results (snow_data/ from snow_depth.py). everyone from one town shares its winter, so the uncertainty
#comes from resampling whole hometowns.
#
#example usage:
#python snow_effect.py
import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from performance_changes import load_linked, build_panel, fit_model, bootstrap, style, COLORS, INK, INK_2, GRID, SURFACE
from snow_depth import km_between

#race day each year. 2017 was cancelled, but its winter still counts toward town normals and 2016's placebo
RACE_DAYS = {2009: '2009-02-21', 2010: '2010-02-27', 2011: '2011-02-26', 2012: '2012-02-25', 2013: '2013-02-23',
             2014: '2014-02-22', 2015: '2015-02-21', 2016: '2016-02-20', 2017: '2017-02-25', 2018: '2018-02-24',
             2019: '2019-02-23', 2020: '2020-02-22', 2021: '2021-02-27', 2022: '2022-02-26', 2023: '2023-02-25',
             2024: '2024-02-24', 2025: '2025-02-22', 2026: '2026-02-21'}
#2021 was raced in waves from wednesday to sunday
WAVE_DAYS_2021 = {'wednesday': -3, 'thursday': -2, 'friday': -1, 'saturday': 0, 'sunday': 1, 'saturday elite': 0,
                  'sunday elite': 1}
INCH = 25.4
SKIABLE_MM = 4 * INCH
MIN_COVERAGE = 0.9              #a hometown's winter needs data on this share of its days
PER = 30                        #effects are quoted per this many more skiable days
#winters by how far they were from the town's normal, in days. the middle bin is the baseline
WINTER_BINS = [-30, -10, 10, 30]
WINTER_LABELS = ['30+ fewer', '10-30 fewer', 'within 10', '10-30 more', '30+ more']
NORMAL_GROUPS = [0, 30, 60]     #towns that usually get under 30, 30 to 60 and 60+ skiable days
COURSE = (46.11, -91.39)        #halfway between cable and hayward
LOCAL_KM = 50
MIDWEST = ['MN', 'WI', 'MI', 'IL', 'IA']
TREND_MIN_RESULTS = 300         #states with this many results get their own time trend in that check
N_BOOTSTRAP = 200
N_CHECK_BOOTSTRAP = 100
#towns shown for context, in the categorical color order from the dataviz guidance
TOWNS = {('cable', 'WI'): ('Cable', '#2a78d6'), ('duluth', 'MN'): ('Duluth', '#eb6834'),
         ('minneapolis', 'MN'): ('Minneapolis', '#1baf7a'), ('madison', 'WI'): ('Madison', '#eda100'),
         ('chicago', 'IL'): ('Chicago', '#e87ba4')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--linked", type=str, default='linked_data/linked_results.csv')
    parser.add_argument("--snow", type=str, default='snow_data', help='folder with snow_depth.py\'s output')
    args = parser.parse_args()

    towns = pd.read_csv(os.path.join(args.snow, 'hometowns.csv'))
    depth = pd.read_parquet(os.path.join(args.snow, 'hometown_snow_depth.parquet'))
    panel = snow_panel(load_linked(args.linked), towns, depth)

    fit, boot = fit_snow(panel, snow_columns(panel))
    bins_fit, bins_boot = fit_snow(panel, binned(panel))
    checks = robustness(panel, fit, boot)

    print_summary(fit, bins_fit, bins_boot, checks)
    plot_snow(bins_fit, bins_boot, checks, towns, depth)
    out = fit['panel'][['skier', 'name', 'year', 'tech', 'city', 'state', 'hometown_id', 'race_day', 'days',
                        'days_normal', 'days_novdec', 'days_janrace', 'time_s', 'resid']]
    out.to_csv(os.path.join(os.path.dirname(args.linked) or '.', 'snow_performance.csv'), index=False)


#---------------------------------------------------------------- snow at home

def race_dates(p):
    day = pd.to_datetime(p['year'].map(RACE_DAYS))
    shift = p['variant'].map(WAVE_DAYS_2021).where(p['year'] == 2021).fillna(0)
    return day + pd.to_timedelta(shift, unit='D')


def skiable_days(depth, race_days, column='depth_10km_mm', threshold=SKIABLE_MM, window='season'):
    #days with at least threshold mm on the ground from november 1 to the day before each race (or only november and
    #december, or only january to the race), per hometown and race day. NaN when too much of the winter has no data
    out = {}
    for day in sorted(set(race_days)):
        start = pd.Timestamp(day.year, 1, 1) if window == 'late' else pd.Timestamp(day.year - 1, 11, 1)
        end = pd.Timestamp(day.year - 1, 12, 31) if window == 'early' else day - pd.Timedelta(days=1)
        d = depth[depth['date'].between(start, end)]
        ski = (d[column] >= threshold).groupby(d['hometown_id']).sum()
        seen = d[column].notna().groupby(d['hometown_id']).sum()
        out[day] = ski.where(seen >= MIN_COVERAGE * ((end - start).days + 1))
    return pd.concat(out, names=['race_day', 'hometown_id']).swaplevel()


def lookup(days, hometown_id, race_day):
    return days.reindex(pd.MultiIndex.from_arrays([hometown_id, race_day])).values


def snow_panel(linked, towns, depth):
    #birkie skate and classic finishes by skiers with 2+ of them, with the snow at the hometown they listed that year
    p = pd.concat([build_panel(linked, 'birkie', tech) for tech in ['skate', 'classic']], ignore_index=True)
    #the race days in RACE_DAYS only: the hometown snow starts in 2004, and so its winters are complete from 2009 on
    p = p[p['year'].isin(RACE_DAYS)]
    p['skier'] = p['athlete_id']
    p['athlete_id'] = p['athlete_id'].astype(str) + ' ' + p['tech']
    p['condition'] = p['tech'] + ' ' + p['condition']
    p = p.merge(towns[['hometown_id', 'city', 'state', 'lat', 'lng']], on=['city', 'state'], how='left')
    p['hometown_id'] = p['hometown_id'].fillna(-1).astype(int)
    p['course_km'] = km_between(p['lat'], p['lng'], *COURSE)
    p['race_day'] = race_dates(p)

    saturdays = pd.to_datetime(list(RACE_DAYS.values()))
    definitions = {'days': ('depth_10km_mm', SKIABLE_MM, 'season'), 'days_nearest': ('depth_mm', SKIABLE_MM, 'season'),
                   'days_2in': ('depth_10km_mm', 2 * INCH, 'season'), 'days_8in': ('depth_10km_mm', 8 * INCH, 'season'),
                   'days_novdec': ('depth_10km_mm', SKIABLE_MM, 'early'),
                   'days_janrace': ('depth_10km_mm', SKIABLE_MM, 'late')}
    for name, (column, threshold, window) in definitions.items():
        days = skiable_days(depth, set(p['race_day']) | set(saturdays), column, threshold, window)
        #the town's normal: its average winter, over every winter to the saturday race day
        normal = days[days.index.get_level_values('race_day').isin(saturdays)].groupby(level='hometown_id').mean()
        p[name] = lookup(days, p['hometown_id'], p['race_day'])
        p[name + '_normal'] = p['hometown_id'].map(normal)
        if name == 'days':
            #placebo: the same hometown's following winter, which can't have helped this race
            p['days_next'] = lookup(days, p['hometown_id'], pd.to_datetime(p['year'].add(1).map(RACE_DAYS)))

    p = p.dropna(subset=['days'])
    p = p[p.groupby('athlete_id')['year'].transform('size') > 1].reset_index(drop=True)
    #the hometown a skier listed most, which the bootstrap resamples
    most = p.groupby(['skier', 'hometown_id']).size().sort_values().reset_index().drop_duplicates('skier', keep='last')
    p['home_id'] = p['skier'].map(most.set_index('skier')['hometown_id'])
    return p


#---------------------------------------------------------------- model

def snow_columns(panel, name='days'):
    #this winter's departure from the town's normal, and the town's normal, both per PER skiable days
    return pd.DataFrame({'winter': (panel[name] - panel[name + '_normal']) / PER,
                         'town': panel[name + '_normal'] / PER}, index=panel.index)


def binned(panel):
    #one column per bin of this winter's departure from normal, against a winter within 10 days of normal
    bins = pd.cut(panel['days'] - panel['days_normal'], [-np.inf] + WINTER_BINS + [np.inf], labels=WINTER_LABELS)
    columns = pd.get_dummies(bins, dtype=float).drop(columns=WINTER_LABELS[2]).add_prefix('winter ')
    return columns.join(snow_columns(panel)[['town']])


def fit_snow(panel, extra, n_boot=N_BOOTSTRAP):
    #fit on the rows that have every extra column, by skiers with 2+ of those rows, and resample hometowns
    p = panel[extra.notna().all(axis=1).values]
    p = p[p.groupby('athlete_id')['year'].transform('size') > 1]
    extra = extra.loc[p.index].reset_index(drop=True)
    fit = fit_model(p.reset_index(drop=True), extra)
    return fit, bootstrap(fit, n_boot, clusters=fit['panel']['home_id'])


def pct_faster(log_effect):
    return 100 * (1 - np.exp(log_effect))


def estimate(fit, boot, column):
    #% faster for one model column, with a 95% range from resampling hometowns
    draws = pct_faster(boot[column])
    return pct_faster(fit['beta'][column]), draws.quantile(0.025), draws.quantile(0.975)


def robustness(panel, fit, boot):
    #the winter effect from the main fit, then from other samples, other definitions of a skiable day and a placebo,
    #and last the town effect
    rows = []

    def add(group, label, f, b, column='winter'):
        est, lo, hi = estimate(f, b, column)
        rows.append({'group': group, 'check': label, 'pct_faster': est, 'lo': lo, 'hi': hi, 'results': len(f['panel'])})

    def run(group, label, mask=None, extra=None):
        p = panel if mask is None else panel[mask]
        f, b = fit_snow(p, snow_columns(p) if extra is None else extra.loc[p.index], N_CHECK_BOOTSTRAP)
        add(group, label, f, b, column='winter' if extra is None else extra.columns[0])

    def split(group, labels, codes):
        #a separate winter effect for each group of results (codes 0, 1, 2.., NaN to leave out), one town effect
        extra = snow_columns(panel)
        for i, label in enumerate(labels):
            extra[label] = extra['winter'].where(codes == i, 0).where(codes.notna())
        f, b = fit_snow(panel, extra.drop(columns='winter'), N_CHECK_BOOTSTRAP)
        for label in labels:
            add(group, label, f, b, label)

    add('main', 'All skiers, skate and classic', fit, boot)
    run('who', 'Skate', panel['tech'] == 'skate')
    run('who', 'Classic', panel['tech'] == 'classic')
    run('who', 'Only MN, WI, MI, IL and IA', panel['state'].isin(MIDWEST))
    run('who', 'Not counting skiers within {} km of the course'.format(LOCAL_KM), panel['course_km'] > LOCAL_KM)
    run('who', 'Only skiers who never changed hometown', panel.groupby('skier')['hometown_id'].transform('nunique') == 1)
    usual = pd.cut(panel['days_normal'], NORMAL_GROUPS + [np.inf], right=False, labels=False)
    split('who', ['Towns that normally get under 30 skiable days', 'Towns that normally get 30-60',
                  'Towns that normally get 60+'], usual)
    #fastest, middle and slowest third of skiers in each technique, by their ability in the main fit
    ability = fit['panel'].groupby('athlete_id').agg(ability=('ability', 'first'), tech=('tech', 'first'))
    third = ability.groupby('tech')['ability'].transform(lambda s: pd.qcut(s, 3, labels=False))
    split('who', ['The fastest third of skiers', 'The middle third', 'The slowest third'],
          panel['athlete_id'].map(third))

    run('definition', 'Snow in the nearest 1 km cell, not within 10 km', extra=snow_columns(panel, 'days_nearest'))
    run('definition', 'Counting days with 2+ inches', extra=snow_columns(panel, 'days_2in'))
    run('definition', 'Counting days with 8+ inches', extra=snow_columns(panel, 'days_8in'))
    early, late = snow_columns(panel, 'days_novdec'), snow_columns(panel, 'days_janrace')
    f, b = fit_snow(panel, pd.DataFrame({'novdec': early['winter'], 'janrace': late['winter'],
                                         'town': snow_columns(panel)['town']}), N_CHECK_BOOTSTRAP)
    add('definition', 'Only November-December (January to race day also in)', f, b, 'novdec')
    add('definition', 'Only January to race day (November-December also in)', f, b, 'janrace')

    #a state whose skiers got faster over the years for some other reason while its winters got snowier would look
    #like a snow effect, so give every big state its own time trend (wisconsin and the small states are the baseline)
    counts = panel['state'].value_counts()
    trend = pd.DataFrame({'trend ' + s: (panel['year'] - 2017) / 10 * (panel['state'] == s)
                          for s in counts[counts >= TREND_MIN_RESULTS].index if s != 'WI'})
    run('confounding', 'With a time trend for each state', extra=snow_columns(panel).join(trend))
    placebo = pd.DataFrame({'next': (panel['days_next'] - panel['days_normal']) / PER}).join(snow_columns(panel))
    run('confounding', 'Placebo: the following winter (should be 0)', extra=placebo)

    add('town', 'Moving to a town with 30 more skiable days in a normal winter', fit, boot, 'town')
    return pd.DataFrame(rows)


#---------------------------------------------------------------- output

def print_summary(fit, bins_fit, bins_boot, checks):
    p = fit['panel']
    print('{} birkie finishes by {} skiers from {} hometowns, {} to {} (no 2024)'.format(
        len(p), p['skier'].nunique(), p['hometown_id'].nunique(), p['year'].min(), p['year'].max()))
    winter = p['days'] - p['days_normal']
    print('skiable days at home, Nov 1 to race day: median {:.0f}. a winter is typically {:.0f} days off its town\'s '
          'normal (sd), and {:.0f} days once the whole field\'s winter is taken out'.format(
              p['days'].median(), winter.std(), (winter - winter.groupby(p['condition']).transform('mean')).std()))
    moved = p.groupby('skier')['hometown_id'].transform('nunique') > 1
    print('{:.0%} of skiers listed more than one hometown'.format(p.loc[moved, 'skier'].nunique() / p['skier'].nunique()))

    main = checks.iloc[0]
    town = checks[checks['group'] == 'town'].iloc[0]
    print('\na winter with {} more skiable days than normal at home: {:.2f}% faster [95% range {:.2f} to {:.2f}], '
          'about {:.1f} minutes for a 3 hour skier'.format(PER, main['pct_faster'], main['lo'], main['hi'],
                                                           main['pct_faster'] / 100 * 180))
    print('moving to a town with {} more skiable days in a normal winter: {:.2f}% faster [{:.2f} to {:.2f}] '
          '(snow plus whatever else came with the move)'.format(PER, town['pct_faster'], town['lo'], town['hi']))

    print('\n% faster than in a winter within 10 days of normal at home:')
    counts = pd.cut(bins_fit['panel']['days'] - bins_fit['panel']['days_normal'], [-np.inf] + WINTER_BINS + [np.inf],
                    labels=WINTER_LABELS).value_counts()
    for label in WINTER_LABELS:
        if label == WINTER_LABELS[2]:
            print('  {:>11}: baseline  ({} results)'.format(label, counts[label]))
            continue
        est, lo, hi = estimate(bins_fit, bins_boot, 'winter ' + label)
        print('  {:>11}: {:+.2f}% [{:+.2f}, {:+.2f}]  ({} results)'.format(label, est, lo, hi, counts[label]))

    print('\nchecks, % faster per {} more skiable days:'.format(PER))
    print(checks.round(2).to_string(index=False))


def plot_snow(bins_fit, bins_boot, checks, towns, depth):
    fig = plt.figure(figsize=(14, 9.5), facecolor=SURFACE)
    grid = fig.add_gridspec(2, 2, width_ratios=[1, 1.2])

    #how much faster, by how far the winter at home was from normal
    ax = fig.add_subplot(grid[0, 0])
    x = np.arange(len(WINTER_LABELS))
    values = [estimate(bins_fit, bins_boot, 'winter ' + l) if l != WINTER_LABELS[2] else (0.0, 0.0, 0.0)
              for l in WINTER_LABELS]
    est, lo, hi = map(np.array, zip(*values))
    ax.axhline(0, color=INK_2, linewidth=0.8)
    ax.vlines(x, lo, hi, color=COLORS['M'], linewidth=1.2)
    ax.plot(x, est, color=COLORS['M'], marker='o', markersize=7, linewidth=2, markeredgecolor=SURFACE,
            markeredgewidth=1.5)
    for xi, e, l, h in zip(x, est, lo, hi):
        if xi == 2:
            ax.annotate('baseline', (xi, 0), xytext=(0, 8), textcoords='offset points', ha='center', fontsize=7,
                        color=INK_2)
        elif e > 0:
            ax.annotate('{:+.1f}%'.format(e), (xi, h), xytext=(0, 4), textcoords='offset points', ha='center',
                        fontsize=8, color=INK)
        else:
            ax.annotate('{:+.1f}%'.format(e), (xi, l), xytext=(0, -12), textcoords='offset points', ha='center',
                        fontsize=8, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels(WINTER_LABELS)
    style(ax, 'A snowier winter than normal at home, a faster Birkie', '% faster than a normal winter',
          'skiable days (4+ inches, Nov 1 to race day) compared with the town\'s normal')

    ax.set_ylim(lo.min() - 0.15, hi.max() + 0.15)

    #the winters behind it: big swings from year to year, and not the same swings everywhere
    ax = fig.add_subplot(grid[1, 0])
    ends = {}
    for (city, state), (name, color) in TOWNS.items():
        hid = towns.loc[(towns['city'] == city) & (towns['state'] == state), 'hometown_id'].iloc[0]
        days = skiable_days(depth[depth['hometown_id'] == hid], pd.to_datetime(list(RACE_DAYS.values())))
        days = days.xs(hid).rename(lambda d: d.year)
        ax.plot(days.index, days.values, color=color, marker='o', markersize=4, linewidth=1.8, label=name)
        ends[name] = (days.index[-1], days.values[-1])
    #end labels, nudged apart where towns finished at about the same number of days
    placed = []
    for name, (year, value) in sorted(ends.items(), key=lambda e: e[1][1]):
        label_y = max([value] + [p + 6 for p in placed])
        placed.append(label_y)
        ax.annotate(name, (year, value), xytext=(year + 0.3, label_y), textcoords='data', va='center', fontsize=8,
                    color=INK_2)
    ax.set_xlim(2008.5, 2028.2)
    ax.set_xticks(range(2009, 2027, 2))
    ax.legend(frameon=False, fontsize=7, ncol=5, loc='upper left')
    style(ax, 'Skiable days, Nov 1 to race day, in a few skier towns', 'days with 4+ inches', 'winter ending in')

    #every check, per 30 more skiable days
    ax = fig.add_subplot(grid[:, 1])
    gap = {'main': 0, 'who': 1, 'definition': 2, 'confounding': 3, 'town': 4}
    y = -(np.arange(len(checks)) + checks['group'].map(gap).values * 0.8)
    main = checks.iloc[0]
    weather = checks[checks['group'] != 'town']
    x_min, x_max = min(-0.4, weather['lo'].min() - 0.1), weather['hi'].max() + 0.3
    ax.axvspan(main['lo'], main['hi'], color=COLORS['M'], alpha=0.12, linewidth=0)
    ax.axvline(0, color=INK_2, linewidth=0.8)
    for yi, (_, r) in zip(y, checks.iterrows()):
        if r['hi'] > x_max:
            #the town effect is far bigger than any winter's, so it's drawn off the scale with its numbers
            ax.plot(x_max - 0.02, yi, '>', color=INK_2, markersize=8)
            ax.annotate('{:+.2f}% [{:.2f} to {:.2f}], off the scale'.format(r['pct_faster'], r['lo'], r['hi']),
                        (x_max - 0.02, yi), xytext=(-10, 0), textcoords='offset points', ha='right', va='center',
                        fontsize=7, color=INK_2)
            ax.annotate('not just the weather: it carries whatever else came with the move', (x_max - 0.02, yi),
                        xytext=(-10, -11), textcoords='offset points', ha='right', fontsize=7, color=INK_2)
            continue
        ax.plot([r['lo'], r['hi']], [yi, yi], color=COLORS['M'], linewidth=1.5)
        ax.plot(r['pct_faster'], yi, 'D' if r['group'] == 'main' else 'o', color=COLORS['M'],
                markersize=9 if r['group'] == 'main' else 7, markeredgecolor=SURFACE, markeredgewidth=1.5)
        ax.annotate('{:+.2f}%'.format(r['pct_faster']), (r['hi'], yi), xytext=(5, 0), textcoords='offset points',
                    va='center', fontsize=7, color=INK_2)
    ax.set_yticks(y)
    ax.set_yticklabels(checks['check'], fontsize=8)
    ax.set_ylim(y.min() - 1, 0.8)
    ax.set_xlim(x_min, x_max)
    style(ax, '30 more skiable days than normal at home, checked every way', '',
          '% faster per {} more skiable days at home (95% range, resampling hometowns)'.format(PER))
    ax.grid(False, axis='y')

    fig.suptitle('Snow at home and Birkie times: the same skiers compared from one winter to the next',
                 x=0.01, ha='left', fontsize=13, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    path = 'graphs/snow_at_home.png'
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    print('\nsaved', path)
    plt.close(fig)


if __name__ == '__main__':
    main()
