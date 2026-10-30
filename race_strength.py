#how strong is the field in each race? birkie vs kortie vs haakon, skate vs classic, open track, by year
#
#the races are different lengths on different days in different snow, so finish times can't be compared directly.
#skiers who have done more than one event tie them together: every result is modeled as
#   log(finish time) = skier's ability + that race (course, distance, snow) + age effect + experience effect + noise
#with one ability per skier across every event they've done. each race's effect then says how long that course took
#a reference skier, and a finisher's time minus their race's effect is the ability that time implies. comparing
#those implied abilities puts every race's winner, median and spread on one scale, quoted below as % slower
#than the typical birkie skate median finisher.
#
#the same assumptions as performance_changes.py: age is held flat from 25 to 35, learning is done after the 5th
#start. it also assumes a skier who is 10% off someone over 50k is about 10% off them over 29k (checked below).
#
#example usage:
#python race_strength.py
#python race_strength.py --name "drew polasky"      one skier's results across every event
#python race_strength.py --name "dan polasky" "drew polasky"     two skiers on one scale, and their head to head
import argparse
import itertools
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from athlete_linking import first_name_relation
from performance_changes import (load_linked, athlete_birth_years, athlete_genders, age_basis, within, style,
                                 AGE_BANDS, OUTLIER_SIGMAS, NEWCOMER_FROM, LEARNING_RACES, INK, INK_2, GRID, SURFACE)
from results_loader import compact

#race effects are measured on adults only. teenagers race the short races and then move up as they grow, so their
#development and the change in distance would get mixed up. they're still in every race's field summary
MIN_AGE = 20
MIN_FINISHERS = 20              #races smaller than this don't get a field estimate
REFERENCE = 'birkie skate'
N_BOOTSTRAP = 100
#main events in the categorical color order from the dataviz guidance
EVENT_COLORS = {'birkie skate': '#2a78d6', 'birkie classic': '#eb6834', 'kortie skate': '#1baf7a',
                'kortie classic': '#eda100', 'haakon skate': '#e87ba4'}
QUANTILES = {'p10': 0.1, 'p25': 0.25, 'median': 0.5, 'p75': 0.75, 'p90': 0.9}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--linked", type=str, default='linked_data/linked_results.csv')
    parser.add_argument("--name", type=str, nargs='+', default=[],
                        help='just plot this skier\'s results across every event, or compare two skiers')
    args = parser.parse_args()
    out_dir = os.path.dirname(args.linked) or '.'

    linked = load_linked(args.linked)
    results = normalized_results(linked)
    fit = fit_model(results)
    if len(args.name) == 1:
        plot_skier(fit, results, args.name[0])
        return
    if len(args.name) == 2:
        plot_pair(fit, results, *args.name)
        return
    boot = bootstrap(fit)
    races, events, yearly = field_levels(fit, results, boot)

    crossover = crossover_results(results)
    same_year = same_year_check(fit)
    slope = distance_check(fit)

    crossover.to_csv(os.path.join(out_dir, 'crossover_results.csv'), index=False)
    races.to_csv(os.path.join(out_dir, 'race_strength.csv'), index=False)
    print_summary(fit, crossover, events, same_year, slope)
    plot_strength(events, yearly)


#---------------------------------------------------------------- data

def normalized_results(linked):
    #every finish at the birkie weekend from 2009 on (before that the data only has the birkie itself), with its race's
    #reference times and the normalized versions of it
    f = linked[(linked['status'] == 'finished') & ~linked['race'].str.startswith('prebirkie') & (linked['year'] >= 2009)]
    f = f.dropna(subset=['time_s']).copy()
    f['race_id'] = f['year'].astype(str) + ' ' + f['race'] + ' ' + f['tech'] + ' ' + f['variant']
    f['event'] = f['race'] + ' ' + f['tech'] + f['variant'].map(variant_group).radd(' ').replace(' ', '')
    g = f.groupby('race_id')['time_s']
    f['race_finishers'] = g.transform('size')
    f['winner_s'] = g.transform('min')
    f['top10_s'] = g.transform(lambda s: s.nsmallest(10).mean())
    f['median_s'] = g.transform('median')
    f['pct_of_median'] = 100 * f['time_s'] / f['median_s']
    f['pct_back_winner'] = 100 * (f['time_s'] / f['winner_s'] - 1)
    f['pct_back_top10'] = 100 * (f['time_s'] / f['top10_s'] - 1)
    f['percentile'] = 100 * g.rank(pct=True)
    return f


def variant_group(variant):
    #2021's race days were the main race spread over the week
    if 'elite' in variant:
        return 'elite'
    if variant == 'openTrack':
        return 'open track'
    return ''


def crossover_results(results):
    #every finish by a skier who has finished more than one event (birkie/kortie/haakon x skate/classic x
    #open track/elite), with how many and which events they've done
    events = results.groupby('athlete_id')['event'].agg(lambda s: ', '.join(sorted(set(s))))
    n_events = results.groupby('athlete_id')['event'].nunique()
    cross = results[results['athlete_id'].map(n_events) > 1].copy()
    cross['n_events'] = cross['athlete_id'].map(n_events)
    cross['events_done'] = cross['athlete_id'].map(events)
    cols = ['athlete_id', 'name', 'gender', 'age', 'city', 'state', 'year', 'race', 'tech', 'variant', 'event',
            'race_id', 'time_s', 'overall_place', 'race_finishers', 'winner_s', 'top10_s', 'median_s',
            'pct_of_median', 'pct_back_winner', 'pct_back_top10', 'percentile', 'n_events', 'events_done',
            'link_score', 'name_shared']
    return cross[cols].sort_values(['athlete_id', 'year', 'event'])


#---------------------------------------------------------------- model

def build_panel(results):
    birth = athlete_birth_years(results)
    sex = athlete_genders(results)
    first_year = results.groupby('athlete_id')['year'].min()
    #experience counts every year with a birkie weekend finish, including races left out of the fit below
    #(junior years, tiny races), for skiers with nothing before NEWCOMER_FROM
    start_number = results.groupby('athlete_id')['year'].rank(method='dense').astype(int)

    p = results[results['race_finishers'] >= MIN_FINISHERS].copy()
    p['start_number'] = start_number
    #anyone sharing a name with another athlete might have the other's results mixed in
    p = p[p.groupby('athlete_id')['name_shared'].transform('max') == 1]
    p['birth_year'] = p['athlete_id'].map(birth)
    p['sex'] = p['athlete_id'].map(sex)
    p['age_at_race'] = p['year'] - p['birth_year']
    p = p.dropna(subset=['birth_year', 'sex'])
    p = p[p['age_at_race'].between(MIN_AGE, 90)]
    p['log_time'] = np.log(p['time_s'] / 3600)
    p['newcomer'] = p['athlete_id'].map(first_year) >= NEWCOMER_FROM
    p = p[p.groupby('athlete_id')['year'].transform('size') > 1]
    return p.reset_index(drop=True)


def design(panel):
    cols = {}
    race_ids = sorted(panel['race_id'].unique())
    for r in race_ids[1:]:
        cols['race ' + r] = (panel['race_id'] == r).astype(float)
    for sex in ['M', 'F']:
        is_sex = (panel['sex'] == sex).astype(float)
        for band, lo, hi in AGE_BANDS:
            cols['age {} {}'.format(sex, band)] = age_basis(panel['age_at_race'], lo, hi) * is_sex
    for n in range(1, LEARNING_RACES + 1):
        cols['start {}'.format(n)] = (panel['newcomer'] & (panel['start_number'] == n)).astype(float)
    return pd.DataFrame(cols, index=panel.index), race_ids


def fit_model(results):
    panel = build_panel(results)
    X, race_ids = design(panel)
    keep = np.ones(len(panel), dtype=bool)
    beta = solve(panel, X, keep)
    resid = within(panel['log_time'], panel['athlete_id'], keep) - within(X, panel['athlete_id'], keep) @ beta
    sigma = 1.4826 * np.median(np.abs(resid))
    keep = np.abs(resid) < OUTLIER_SIGMAS * sigma
    keep &= panel['athlete_id'].map(pd.Series(keep).groupby(panel['athlete_id']).sum()).values > 1
    panel, X = panel[keep].reset_index(drop=True), X[keep].reset_index(drop=True)
    beta = solve(panel, X, np.ones(len(panel), dtype=bool))
    effects = X @ beta
    panel['ability'] = (panel['log_time'] - effects).groupby(panel['athlete_id']).transform('mean')
    panel['resid'] = panel['log_time'] - effects - panel['ability']
    return {'panel': panel, 'X': X, 'beta': beta, 'race_ids': race_ids, 'race_effects': race_effects(beta, race_ids),
            'n_dropped': int((~keep).sum())}


def solve(panel, X, keep):
    y = within(panel['log_time'], panel['athlete_id'], keep)
    Xw = within(X, panel['athlete_id'], keep)
    return pd.Series(np.linalg.lstsq(Xw[keep], y[keep], rcond=None)[0], index=X.columns)


def race_effects(beta, race_ids):
    #log time of the same reference skier in each race (only differences between races mean anything)
    effect = pd.Series(0.0, index=race_ids)
    for r in race_ids[1:]:
        effect[r] = beta['race ' + r]
    return effect


def bootstrap(fit, n=N_BOOTSTRAP, seed=0):
    #resample skiers and refit, for uncertainty in the race effects
    panel, X = fit['panel'], fit['X']
    keep = np.ones(len(panel), dtype=bool)
    y = within(panel['log_time'], panel['athlete_id'], keep)
    Xw = within(X, panel['athlete_id'], keep)
    rows = pd.Series(np.arange(len(panel))).groupby(panel['athlete_id'].values).apply(np.array)
    rng = np.random.default_rng(seed)
    effects = []
    for _ in range(n):
        idx = np.concatenate(rows.values[rng.integers(0, len(rows), len(rows))])
        beta = pd.Series(np.linalg.lstsq(Xw[idx], y[idx], rcond=None)[0], index=X.columns)
        effects.append(race_effects(beta, fit['race_ids']))
    return pd.DataFrame(effects)


#---------------------------------------------------------------- field levels

def implied_abilities(fit, results):
    #every finisher's implied ability: their log time minus their race's effect
    effects = fit['race_effects']
    f = results[results['race_id'].isin(effects.index)].copy()
    f['implied'] = np.log(f['time_s'] / 3600) - f['race_id'].map(effects)
    return f


def reference_level(f):
    #the typical birkie skate median finisher, the zero point for every comparison
    ref = f[f['event'] == REFERENCE]
    return ref.groupby('year')['implied'].median().mean()


def to_pct(log_diff):
    return 100 * (np.exp(log_diff) - 1)


def field_levels(fit, results, boot):
    #every finisher's implied ability = their log time minus their race's effect. the field's winner, median and
    #spread are then just summaries of those, on the same scale for every race
    f = implied_abilities(fit, results)

    def summarize(groups):
        out = groups['implied'].quantile(list(QUANTILES.values())).unstack()
        out.columns = list(QUANTILES)
        out['winner'] = groups['implied'].min()
        out['top10'] = groups['implied'].apply(lambda s: s.nsmallest(10).mean())
        out['finishers'] = groups.size()
        return out

    races = summarize(f.groupby('race_id'))
    races = races.join(f.groupby('race_id')[['year', 'race', 'tech', 'variant', 'event']].first())
    yearly = summarize(f.groupby(['event', 'year']))

    #everything relative to the typical birkie skate median finisher
    ref = reference_level(f)
    levels = list(QUANTILES) + ['winner', 'top10']
    races[levels] = to_pct(races[levels] - ref)
    yearly[levels] = to_pct(yearly[levels] - ref)
    #an event's typical field: the average year
    events = yearly.groupby('event')[levels].mean()
    events['years'] = yearly.groupby('event').size()
    events['finishers'] = yearly.groupby('event')['finishers'].sum()

    #uncertainty in each event's median from refitting the race effects
    draws = []
    for _, eff in boot.iterrows():
        implied = np.log(f['time_s'] / 3600) - f['race_id'].map(eff)
        med = implied.groupby([f['event'], f['year']]).median()
        med = med - med.loc[REFERENCE].mean()
        draws.append(to_pct(med.groupby(level='event').mean()))
    draws = pd.DataFrame(draws)
    events['median_lo'] = draws.quantile(0.025)
    events['median_hi'] = draws.quantile(0.975)
    races = races.reset_index().sort_values(['event', 'year'])
    return races, events.sort_values('median'), yearly.reset_index()


#---------------------------------------------------------------- checks

def same_year_check(fit):
    #skiers who did two events in the same year: same fitness, same age, so their implied abilities in the two races
    #should match if the race effects are right. a gap here is model error, or fatigue from racing the day before
    p = fit['panel'].assign(implied=lambda d: d['log_time'] - d['race_id'].map(fit['race_effects']))
    p = p[p.groupby(['athlete_id', 'year'])['event'].transform('nunique') > 1]
    rows = []
    for (aid, year), g in p.groupby(['athlete_id', 'year']):
        for a, b in itertools.combinations(g.sort_values('event').itertuples(), 2):
            if a.event != b.event:
                rows.append((a.event, b.event, year, a.implied - b.implied,
                             np.log(a.pct_of_median / 100) - np.log(b.pct_of_median / 100)))
    d = pd.DataFrame(rows, columns=['event_a', 'event_b', 'year', 'implied_gap', 'median_gap'])
    pct = lambda s: 100 * (np.exp(s.mean()) - 1)
    return d.groupby(['event_a', 'event_b']).agg(pairs=('year', 'size'), model_gap_pct=('implied_gap', pct),
                                                 median_gap_pct=('median_gap', pct)).query('pairs >= 15')


def distance_check(fit):
    #does a skier who is X% off the pace over 50k stay X% off over 29k, or do slower skiers lose more over the longer
    #race? compare each crossover skier's average implied ability in the birkie and the kortie of the same technique
    p = fit['panel'].assign(implied=lambda d: d['log_time'] - d['race_id'].map(fit['race_effects']))
    out = {}
    for tech in ['skate', 'classic']:
        m = p[p['event'].isin(['birkie ' + tech, 'kortie ' + tech])]
        a = m.groupby(['athlete_id', 'event'])['implied'].mean().unstack().dropna()
        level = a.mean(axis=1)
        gap = a['birkie ' + tech] - a['kortie ' + tech]
        out[tech] = (np.polyfit(level, gap, 1)[0], len(a))
    return out


#---------------------------------------------------------------- output

def print_summary(fit, crossover, events, same_year, slope):
    p = fit['panel']
    print('{} finishes by {} skiers who finished more than one event ({} events)'.format(
        len(crossover), crossover['athlete_id'].nunique(), crossover['event'].nunique()))
    print('model: {} finishes by {} skiers with 2+ races and known ages, {} races ({} outliers dropped)'.format(
        len(p), p['athlete_id'].nunique(), p['race_id'].nunique(), fit['n_dropped']))

    print('\nfield level, % slower than the typical {} median finisher (average year):'.format(REFERENCE))
    cols = ['winner', 'top10', 'p10', 'p25', 'median', 'p75', 'p90']
    t = events[cols].round(1)
    t['median 95% range'] = events.apply(lambda r: '{:+.1f} to {:+.1f}'.format(r['median_lo'], r['median_hi']), axis=1)
    t['years'] = events['years']
    t['finishers'] = events['finishers']
    print(t.to_string())

    print('\nsame-year check: skiers who did both events in one year (gap = event a minus event b, %):')
    print('  model_gap: should be ~0 if the race effects are right.  median_gap: their % of median in a minus in b')
    print(same_year.round(1).to_string())

    print('\ndistance check, slope of (birkie - kortie implied ability) on skier level (0 = same % gap at any level):')
    for tech, (s, n) in slope.items():
        print('  {}: {:+.3f} per unit of log ability ({} skiers)'.format(tech, s, n))


def plot_strength(events, yearly):
    fig = plt.figure(figsize=(14, 9), facecolor=SURFACE)
    grid = fig.add_gridspec(2, 2, width_ratios=[1.1, 1])

    #each event's field, from the 10th to the 90th percentile finisher
    ax = fig.add_subplot(grid[:, 0])
    ev = events[events['years'] >= 2].sort_values('median', ascending=False)
    y = np.arange(len(ev))
    color = lambda e: EVENT_COLORS.get(e, '#8f8d86')
    for yi, (name, r) in zip(y, ev.iterrows()):
        c = color(name)
        ax.plot([r['p10'], r['p90']], [yi, yi], color=c, linewidth=1.5, solid_capstyle='round')
        ax.plot([r['p25'], r['p75']], [yi, yi], color=c, linewidth=7, solid_capstyle='butt', alpha=0.45)
        ax.plot(r['median'], yi, 'o', color=c, markersize=8, markeredgecolor=SURFACE, markeredgewidth=1.5)
        ax.plot(r['winner'], yi, 'D', color=c, markersize=5)
        ax.annotate('{:+.0f}%'.format(r['median']), (r['median'], yi), xytext=(0, 9), textcoords='offset points',
                    ha='center', fontsize=8, color=INK)
    ax.axvline(0, color=INK_2, linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(['{}\n{} yrs, {:,} finishers'.format(n, int(r['years']), int(r['finishers']))
                        for n, r in ev.iterrows()], fontsize=8)
    ax.set_ylim(-0.7, len(ev) - 0.3)
    ax.plot([], [], 'D', color=INK_2, markersize=5, label='winner')
    ax.plot([], [], 'o', color=INK_2, markersize=8, label='median finisher')
    ax.plot([], [], color=INK_2, linewidth=7, alpha=0.45, label='middle half (25th-75th)')
    ax.plot([], [], color=INK_2, linewidth=1.5, label='10th-90th percentile')
    ax.legend(frameon=False, fontsize=8, loc='upper right')
    style(ax, 'Each race\'s field on one scale', '', '% slower than the typical {} median finisher'.format(REFERENCE))

    #median and front of the field by year, for the main events
    for row, (level, title) in enumerate([('median', 'Median finisher by year'), ('top10', 'Top 10 finishers by year')]):
        ax = fig.add_subplot(grid[row, 1])
        for name, c in EVENT_COLORS.items():
            d = yearly[yearly['event'] == name].sort_values('year')
            if d.empty:
                continue
            years = d['year'].values
            values = d[level].values.astype(float)
            #break the line where years are missing (2017 cancelled)
            gaps = np.where(np.diff(years) > 1)[0] + 1
            ax.plot(np.insert(years.astype(float), gaps, np.nan), np.insert(values, gaps, np.nan), color=c,
                    linewidth=2, marker='o', markersize=4, label=name)
            if row == 0:
                ax.annotate(name, (years[-1], values[-1]), xytext=(5, 0), textcoords='offset points', fontsize=7,
                            color=INK_2, va='center')
        ax.axhline(0, color=INK_2, linewidth=0.8)
        ax.set_xlim(2008.5, 2029)
        ax.set_xticks(range(2010, 2027, 2))
        if row == 0:
            ax.legend(frameon=False, fontsize=7, loc='upper left', ncol=2)
        style(ax, title, '% slower than typical {} median'.format(REFERENCE), 'year' if row == 1 else '')

    fig.suptitle('How strong is each race? Skiers who did several events put them on one scale',
                 x=0.01, ha='left', fontsize=13, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    path = 'graphs/race_strength.png'
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    print('\nsaved', path)
    plt.close(fig)


def skier_rows(fit, f, ref, name):
    #one skier's finishes on the common scale, and what the model expects of them each year (their ability with
    #age and experience, without the day's luck), or None when the name isn't exactly one skier
    last = compact(name.split()[-1])
    first = compact(' '.join(name.split()[:-1]))
    match = (f['last'].map(compact) == last) & f['first'].map(compact).map(lambda x: first_name_relation(x, first) is not None)
    ids = f.loc[match, 'athlete_id'].unique()
    if len(ids) != 1:
        print('{} matches {} skiers, not plotting'.format(name, len(ids)))
        return None, None
    rows = f[f['athlete_id'] == ids[0]].sort_values(['year', 'event']).copy()
    rows['level'] = to_pct(rows['implied'] - ref)
    rows['beat'] = 100 - rows['percentile']
    mine = fit['panel'][fit['panel']['athlete_id'] == ids[0]]
    expected = (mine['log_time'] - mine['resid'] - mine['race_id'].map(fit['race_effects'])).groupby(mine['year']).mean()
    rows['expected'] = rows['year'].map(to_pct(expected - ref))
    return rows, expected


def plot_skier(fit, results, name):
    #one skier's races across every event: on the common scale, and how much of each field they beat
    f = implied_abilities(fit, results)
    ref = reference_level(f)
    rows, expected = skier_rows(fit, f, ref, name)
    if rows is None:
        return

    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True, facecolor=SURFACE,
                                  gridspec_kw={'height_ratios': [2, 1]})
    ax.plot(expected.index, to_pct(expected - ref), color=INK_2, linewidth=1.2,
            label='expected from ability, age and experience')
    for event in sorted(rows['event'].unique(), key=lambda e: list(EVENT_COLORS).index(e) if e in EVENT_COLORS else 99):
        d = rows[rows['event'] == event]
        c = EVENT_COLORS.get(event, '#8f8d86')
        ax.plot(d['year'], d['level'], 'o', color=c, markersize=8, markeredgecolor=SURFACE, markeredgewidth=1.5,
                label=event)
        ax2.plot(d['year'], d['beat'], 'o', color=c, markersize=7, markeredgecolor=SURFACE, markeredgewidth=1.5)
    for _, r in rows[rows['year'].isin(COURSE_NOTES)].iterrows():
        ax.annotate(COURSE_NOTES[r['year']], (r['year'], r['level']), xytext=(0, -14), textcoords='offset points',
                    ha='center', fontsize=7, color=INK_2)
    ax.axhline(0, color=INK_2, linewidth=0.8)
    ax.invert_yaxis()
    ax.legend(frameon=False, fontsize=8)
    style(ax, '{}: every race on one scale (faster is up)'.format(rows['name'].iloc[-1]),
          '% slower than the typical {} median finisher'.format(REFERENCE))
    ax2.set_ylim(0, 100)
    ax2.set_xticks(range(int(rows['year'].min()), int(rows['year'].max()) + 1, 2))
    style(ax2, 'Share of that race\'s field they finished ahead of (raw, no model)', '% of finishers behind', 'year')
    fig.tight_layout()
    path = 'graphs/all_events_{}.png'.format(compact(name))
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    print('saved', path)
    plt.close(fig)

    clock = lambda s: pd.to_datetime(s, unit='s').dt.strftime('%H:%M:%S')
    print(rows.assign(time=clock(rows['time_s']), place=rows['overall_place'].astype('Int64').astype(str) + '/' +
                      rows['race_finishers'].astype(str))[
        ['year', 'event', 'time', 'place', 'pct_of_median', 'pct_back_winner', 'level', 'expected']].round(1).to_string(index=False))


def plot_pair(fit, results, name_a, name_b):
    #two skiers on the common scale (color is the skier, shape is the event), and below that the raw head to head
    #in every race they both finished
    f = implied_abilities(fit, results)
    ref = reference_level(f)
    (a, exp_a), (b, exp_b) = skier_rows(fit, f, ref, name_a), skier_rows(fit, f, ref, name_b)
    if a is None or b is None:
        return
    label_a, label_b = a['name'].iloc[-1], b['name'].iloc[-1]
    events = sorted(set(a['event']) | set(b['event']),
                    key=lambda e: list(EVENT_COLORS).index(e) if e in EVENT_COLORS else 99)
    shape = dict(zip(events, 'osD^vPX*'))

    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(10, 8.5), sharex=True, facecolor=SURFACE,
                                  gridspec_kw={'height_ratios': [2, 1]})
    for rows, expected, color, label in [(a, exp_a, PAIR_COLORS[0], label_a), (b, exp_b, PAIR_COLORS[1], label_b)]:
        ax.plot(expected.index, to_pct(expected - ref), color=color, linewidth=2, alpha=0.5)
        for event in events:
            d = rows[rows['event'] == event]
            ax.plot(d['year'], d['level'], shape[event], color=color, markersize=8, markeredgecolor=SURFACE,
                    markeredgewidth=1.5)
        ax.annotate(label, (expected.index[-1], to_pct(expected.iloc[-1] - ref)), xytext=(8, 0),
                    textcoords='offset points', va='center', fontsize=9, color=INK)
    #legend: who is which color, which event is which shape, and the lines
    handles = [plt.Line2D([], [], color=c, marker='o', linestyle='', markersize=8, label=l)
               for c, l in zip(PAIR_COLORS, [label_a, label_b])]
    handles += [plt.Line2D([], [], color=INK_2, marker=shape[e], linestyle='', markersize=7, label=e) for e in events]
    handles.append(plt.Line2D([], [], color=INK_2, linewidth=2, alpha=0.5, label='expected from ability, age and experience'))
    ax.legend(handles=handles, frameon=False, fontsize=8, ncol=2)
    ax.axhline(0, color=INK_2, linewidth=0.8)
    ax.invert_yaxis()
    style(ax, '{} and {}: every race on one scale (faster is up)'.format(label_a, label_b),
          '% slower than the typical {} median finisher'.format(REFERENCE))

    both = a.merge(b, on=['race_id', 'year', 'event'], suffixes=('_a', '_b'))
    both['gap'] = 100 * (both['time_s_a'] / both['time_s_b'] - 1)
    gap = to_pct(exp_a - exp_b).dropna()
    ax2.plot(gap.index, gap, color=INK_2, linewidth=2, alpha=0.5)
    for event in events:
        d = both[both['event'] == event]
        ax2.plot(d['year'], d['gap'], shape[event], color=INK, markersize=8, markeredgecolor=SURFACE,
                 markeredgewidth=1.5)
    for _, r in both[both['year'].isin(COURSE_NOTES)].iterrows():
        ax2.annotate(COURSE_NOTES[r['year']], (r['year'], r['gap']), xytext=(0, -14), textcoords='offset points',
                     ha='center', fontsize=7, color=INK_2)
    ax2.axhline(0, color=INK_2, linewidth=0.8)
    ax2.invert_yaxis()
    ax2.set_xticks(range(int(min(a['year'].min(), b['year'].min())), int(max(a['year'].max(), b['year'].max())) + 1, 2))
    style(ax2, 'Same race, raw times: {} vs {} (above the line, {} was faster)'.format(
        label_a.split()[0], label_b.split()[0], label_a.split()[0]),
        '% slower than {}'.format(label_b.split()[0]), 'year')
    fig.tight_layout()
    path = 'graphs/all_events_{}_vs_{}.png'.format(compact(name_a), compact(name_b))
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    print('saved', path)
    plt.close(fig)
    clock = lambda s: pd.to_datetime(s, unit='s').dt.strftime('%H:%M:%S')
    print(both.assign(time_a=clock(both['time_s_a']), time_b=clock(both['time_s_b']))[
        ['year', 'event', 'time_a', 'time_b', 'gap', 'level_a', 'level_b']].round(1).to_string(index=False))


#the two skiers in a comparison, first two categorical colors
PAIR_COLORS = ['#2a78d6', '#eb6834']
#notes for races that weren't the usual course
COURSE_NOTES = {2024: 'short course'}


if __name__ == '__main__':
    main()
