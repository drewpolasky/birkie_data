#does a slow year hit the front of the field and the back the same? performance_changes.py gives each race one
#conditions effect, the same % for every skier. here each race gets its own effect for each tenth of the field:
#   log(finish time) = skier's ability + that race's conditions for skiers of their speed + age + experience + noise
#a skier's tenth comes from their typical finish time on an average day (conditions taken out, age left in), so the
#fastest tenth is the front of the race. the effects are still measured within the same skiers from year to year:
#how much slower than their own usual the fastest tenth skied in 2014, next to how much slower the middle did.
#
#everyone slower by the same % already spreads the field out in minutes, so the question here is only whether some
#parts of the field lost a bigger share of their time than others.
#
#a skier's typical time averages all their races, the one being measured included, so a bad day in 2014 also nudges
#them toward the back. with normal noise that doesn't bias anything (an average and the deviations from it are
#independent), and a check with each skier's tenth set from their other races only agrees. 2021 is left out: it was
#raced over several days, with the elite wave on its own, so no day had the whole field.
#
#the waves are seeded by speed, so the fastest skiers also start first, on a course nobody has skied yet. the bib
#gives the wave (one wave per thousand), and from that each skier's start position: the share of the field that
#started ahead of them. seeding lags a year and first-timers start at the back, so skiers of the same speed start in
#different places, which lets a second model hold start position fixed:
#   ... + that race's conditions for skiers of their speed + that race's cost of starting later x start position
#a start position that is late for the skier also goes with them being off form (they were seeded from a slow year),
#but that is the same in every race, so only each race's difference from the average race is read off it.
#results whose wave isn't known (bibs outside the numbered waves) are left out of both models. a plain check does
#the same without the start position model: each result against the skier's own usual from their other races,
#skiers of the same speed split by where they started, each race read against the average race.
#
#example usage:
#python front_back.py
import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from performance_changes import load_linked, build_panel, fit_model, bootstrap, style, N_BOOTSTRAP, INK, INK_2, GRID, \
    SURFACE

TECHS = ['skate', 'classic']
GROUPS = 10
FRONT, MIDDLE, BACK = [0], [4, 5], [9]          #fastest tenth, the middle fifth, slowest tenth
LEAVE_OUT_YEARS = [2021]
FIRST_YEAR = 2009                               #the bib waves are known from here on, older results numbered bibs otherwise
MIN_RACES_LOO = 3                               #the leave one out check needs 2+ other races to place a skier
MIDDLE_START = 0.5                              #start position of the skier in the middle of the start order
CHECK_FROM = 2013                               #the late start costs of 2009-2012 carry the start checks, so refit without
#the plain check: starting this share of the field behind the usual for a skier's speed that year is late, within
#ON_TIME of it is on time. and for one race, the fastest and middle fifths by where they started
LATE, ON_TIME, MIN_CELL = 0.15, 0.1, 5
FASTEST_FIFTH, MIDDLE_FIFTH = [0, 1], [4, 5]
UP_FRONT, MID_PACK = 0.25, (0.3, 0.7)
PLAIN_YEAR = 2014
MIN_TABLE = 10                                  #skiers a group needs in that race to be compared
PER = 10                                        #gaps are quoted per this many % slower race
#years picked out in the plots, in the categorical color order from the dataviz guidance. the rest are gray
HIGHLIGHT = {2014: '#2a78d6', 2019: '#eb6834', 2026: '#1baf7a'}
OTHER = '#bdbcb7'
#the end of the field whose gap holds up in every check, plotted against how slow the race was
GAP_SHOWN = {'skate': 'front', 'classic': 'back'}
GAP_NAMES = {'front': 'fastest tenth', 'back': 'slowest tenth'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--linked", type=str, default='linked_data/linked_results.csv')
    args = parser.parse_args()

    linked = load_linked(args.linked)
    results = {}
    for tech in TECHS:
        panel = race_panel(linked, tech)
        fit = fit_groups(panel)
        results[tech] = summarize(fit, bootstrap(fit))
        start_fit = fit_groups(panel, start=True)
        results[tech]['start'] = summarize(start_fit, bootstrap(start_fit))
        results[tech]['checks'] = checks(panel, fit, results[tech])
        results[tech]['plain'] = plain_check(panel)
        results[tech]['raw'] = raw_spread(linked, tech)

    print_summary(results)
    plot_front_back(results)
    plot_start(results)
    out_dir = os.path.dirname(args.linked) or '.'
    rows, races = [], []
    for tech, r in results.items():
        for g in range(GROUPS):
            rows.append(pd.DataFrame({'tech': tech, 'year': r['pct'].index, 'tenth': g + 1,
                                      'typical_time_h': r['typical'][g], 'pct_slower': r['pct'][g].values,
                                      'lo': r['lo'][g].values, 'hi': r['hi'][g].values,
                                      'pct_slower_same_start': r['start']['pct'][g].values}))
        s, plain = r['start']['gaps'], r['plain']['races']
        races.append(pd.DataFrame({'tech': tech, 'year': s.index, 'race_pct_slower': r['gaps']['level'],
                                   'start_cost': s['start'], 'start_cost_lo': s['start_lo'],
                                   'start_cost_hi': s['start_hi'], 'front_gap': r['gaps']['front'],
                                   'front_gap_same_start': s['front'], 'back_gap': r['gaps']['back'],
                                   'back_gap_same_start': s['back'], 'plain_late_minus_on_time': plain['plain'],
                                   'plain_lo': plain['lo'], 'plain_hi': plain['hi'],
                                   'plain_start_gap': plain['start_gap']}))
    pd.concat(rows).round(3).to_csv(os.path.join(out_dir, 'front_back.csv'), index=False)
    pd.concat(races).round(3).to_csv(os.path.join(out_dir, 'front_back_start.csv'), index=False)


#---------------------------------------------------------------- model

def race_panel(linked, tech):
    panel = build_panel(linked, 'birkie', tech)
    panel = panel[(panel['year'] >= FIRST_YEAR) & ~panel['year'].isin(LEAVE_OUT_YEARS)]
    panel = panel.merge(start_positions(linked, tech), on=['year', 'variant', 'athlete_id'], how='left')
    panel = panel.dropna(subset=['start_pos'])
    return panel[panel.groupby('athlete_id')['year'].transform('size') > 1].reset_index(drop=True)


def wave_of(bib, tech):
    #skate: elite wave under 1000, then wave n in the n000s. classic: elite under 1000, then wave n in the 1n000s
    #(9n000s in 2012). other bibs (35000s, 70000s, 80000s...) are separate starts with no known place in the order
    thousand = bib // 1000
    wave = pd.Series(np.nan, index=bib.index)
    wave[bib < 1000] = 0
    if tech == 'skate':
        return wave.mask(thousand.between(1, 10), thousand)
    wave = wave.mask(thousand.between(11, 19), thousand - 10)
    return wave.mask(thousand.between(90, 99), thousand - 90)


def start_positions(linked, tech):
    #share of the field that started in an earlier wave, plus half of the skier's own wave. every starter with a
    #known wave counts, DNFs too where the results have them
    d = linked[(linked['race'] == 'birkie') & (linked['tech'] == tech) & (linked['variant'] != 'openTrack')].copy()
    d['wave'] = wave_of(pd.to_numeric(d['bib'], errors='coerce'), tech)
    d = d.dropna(subset=['wave'])
    share = d.groupby(['year', 'variant', 'wave']).size()
    share = share / share.groupby(level=['year', 'variant']).transform('sum')
    position = share.groupby(level=['year', 'variant']).cumsum() - share / 2
    d = d.join(position.rename('start_pos'), on=['year', 'variant', 'wave'])
    return d[['year', 'variant', 'athlete_id', 'wave', 'start_pos']].drop_duplicates(['year', 'variant', 'athlete_id'])


def start_columns(panel):
    #how much starting later costs, overall and in each race on top of that
    cols = {'start': panel['start_pos']}
    for c in sorted(panel['condition'].unique())[1:]:
        cols['start x ' + c] = panel['start_pos'] * (panel['condition'] == c)
    return pd.DataFrame(cols, index=panel.index)


def start_effects(beta, conditions):
    #each race's extra log cost of being the last starter rather than the first, centered on the average race
    cost = pd.Series([0.0] + [beta['start x ' + c] for c in conditions[1:]], index=conditions)
    return cost - cost.mean()


def tenth_cuts(fit):
    #where the tenths split, by typical finish time on an average day, so each tenth has a tenth of the results
    p = fit['panel']
    typical = p.groupby('athlete_id')['adjusted'].mean()
    cuts = p['athlete_id'].map(typical).quantile(np.arange(1, GROUPS) / GROUPS).values
    return typical, cuts


def interactions(panel, group):
    #each race's conditions for each tenth, on top of the fastest tenth's (the conditions in design())
    cols = {}
    conditions = sorted(panel['condition'].unique())
    for g in range(1, GROUPS):
        in_group = group == g
        for c in conditions[1:]:
            cols['cond {} x {}'.format(c, g)] = ((panel['condition'] == c) & in_group).astype(float)
    return pd.DataFrame(cols, index=panel.index)


def fit_groups(panel, cuts=None, group=None, start=False):
    #start: also give each race its own cost of starting later, so the tenths are compared at the same start
    base = fit_model(panel)
    typical, base_cuts = tenth_cuts(base)
    cuts = base_cuts if cuts is None else cuts
    if group is None:
        panel = panel[panel['athlete_id'].isin(typical.index)].reset_index(drop=True)
        group = pd.Series(np.searchsorted(cuts, panel['athlete_id'].map(typical)), index=panel.index)
    extra = interactions(panel, group)
    if start:
        extra = extra.join(start_columns(panel))
    fit = fit_model(panel, extra)
    fit['panel']['tenth'] = group[fit['panel'].index]
    fit['cuts'] = cuts
    return fit


def tenth_effects(beta, conditions):
    #log effect of each race for each tenth, each tenth centered on its own average race. in the model with start
    #position, for skiers starting in the middle of the order, so how slow the race was means the same in both
    eff = pd.DataFrame(0.0, index=conditions, columns=range(GROUPS))
    for c in conditions[1:]:
        for g in range(GROUPS):
            eff.loc[c, g] = beta['cond ' + c] + (beta['cond {} x {}'.format(c, g)] if g else 0)
    if 'start' in beta.index:
        eff = eff.add(MIDDLE_START * start_effects(beta, conditions), axis=0)
    return eff - eff.mean()


def gaps(eff, beta=None):
    #how much more of their time the front and back lost than the middle, in % points, and how slow the race was.
    #with beta from a model with start position, also each race's extra % for the last starter over the first
    pct = 100 * (np.exp(eff) - 1)
    middle = pct[MIDDLE].mean(axis=1)
    g = pd.DataFrame({'level': 100 * (np.exp(eff.mean(axis=1)) - 1), 'front': pct[FRONT].mean(axis=1) - middle,
                      'back': pct[BACK].mean(axis=1) - middle})
    if beta is not None and 'start' in beta.index:
        g['start'] = 100 * (np.exp(start_effects(beta, list(eff.index))) - 1)
    return g


def slope(g, column, trend=False):
    #change in the gap per PER % slower race, across races, optionally with a straight line trend over the years
    X = np.column_stack([np.ones(len(g)), g['level'] / PER] + ([g.index.astype(int)] if trend else []))
    return np.linalg.lstsq(X, g[column].values, rcond=None)[0][1]


def summarize(fit, boot):
    conditions = list(fit['conditions'].index)
    eff = tenth_effects(fit['beta'], conditions)
    draws = [tenth_effects(row, conditions) for _, row in boot.iterrows()]
    pct = 100 * (np.exp(eff) - 1)
    stack = 100 * (np.exp(np.stack([d.values for d in draws])) - 1)
    lo = pd.DataFrame(np.quantile(stack, 0.025, axis=0), index=eff.index, columns=eff.columns)
    hi = pd.DataFrame(np.quantile(stack, 0.975, axis=0), index=eff.index, columns=eff.columns)
    g = gaps(eff, fit['beta'])
    g_draws = [gaps(d, row) for d, (_, row) in zip(draws, boot.iterrows())]
    columns = [c for c in ['front', 'back', 'start'] if c in g]
    for col in columns:
        g[col + '_lo'] = np.quantile([d[col] for d in g_draws], 0.025, axis=0)
        g[col + '_hi'] = np.quantile([d[col] for d in g_draws], 0.975, axis=0)
    slopes = {}
    for col in columns:
        for trend in [False, True]:
            s = [slope(d, col, trend) for d in g_draws]
            slopes[(col, trend)] = (slope(g, col, trend), np.quantile(s, 0.025), np.quantile(s, 0.975))
    p = fit['panel']
    typical = np.exp(p['adjusted']).groupby(p['tenth']).median()
    for d in [pct, lo, hi, g]:
        d.index = d.index.astype(int)
    return {'pct': pct, 'lo': lo, 'hi': hi, 'gaps': g, 'slopes': slopes, 'typical': typical, 'fit': fit,
            'n': len(p), 'skiers': p['athlete_id'].nunique()}


def checks(panel, fit, main):
    #the front and back gaps' slopes refit other ways, without the bootstrap
    out = {'main': main['slopes'][('front', False)][0], 'main back': main['slopes'][('back', False)][0]}
    #the slowest race on its own carries a lot of the line
    out['without 2014'] = slope(main['gaps'].drop(2014), 'front')
    out['without 2014 back'] = slope(main['gaps'].drop(2014), 'back')

    #each result's tenth set from the skier's other races only, so their luck that day can't move them
    p = fit_model(panel)['panel']
    p = p[p.groupby('athlete_id')['year'].transform('size') >= MIN_RACES_LOO].reset_index(drop=True)
    totals = p.groupby('athlete_id')['adjusted'].agg(['sum', 'count'])
    others = (p['athlete_id'].map(totals['sum']) - p['adjusted']) / (p['athlete_id'].map(totals['count']) - 1)
    loo = fit_groups(p, fit['cuts'], pd.Series(np.searchsorted(fit['cuts'], others), index=p.index))
    g = gaps(tenth_effects(loo['beta'], list(loo['conditions'].index)))
    out['tenth from other races'] = slope(g, 'front')
    out['tenth from other races back'] = slope(g, 'back')

    #men only, since the front of the field is mostly men. same tenths as the whole field
    men = panel[panel['sex'] == 'M'].reset_index(drop=True)
    men_fit = fit_model(men)
    typical = men_fit['panel'].groupby('athlete_id')['adjusted'].mean()
    men = men[men['athlete_id'].isin(typical.index)].reset_index(drop=True)
    m = fit_groups(men, fit['cuts'], pd.Series(np.searchsorted(fit['cuts'], men['athlete_id'].map(typical)),
                                               index=men.index))
    g = gaps(tenth_effects(m['beta'], list(m['conditions'].index)))
    out['men only'] = slope(g, 'front')
    out['men only back'] = slope(g, 'back')

    #the start position model without first-timers' first race, since they start at the back whatever their speed
    #and might struggle with hard conditions for being new, not for starting late. and from CHECK_FROM on, since a late
    #start cost a lot in 2009-2012, mostly fast years, and not since
    since = '{} on'.format(CHECK_FROM)
    for label, keep in [('no first-timer first race', ~(panel['newcomer'] & (panel['race_number'] == 1))),
                        (since, panel['year'] >= CHECK_FROM)]:
        p = panel[keep]
        p = p[p.groupby('athlete_id')['year'].transform('size') > 1].reset_index(drop=True)
        s = fit_groups(p, start=True)
        conditions = list(s['conditions'].index)
        g = gaps(tenth_effects(s['beta'], conditions), s['beta'])
        for col in ['front', 'back', 'start']:
            out['same start, {}, {}'.format(label, col)] = slope(g, col)
    #and the gaps as measured over the same years, to set the same start ones against
    p = panel[panel['year'] >= CHECK_FROM]
    a = fit_groups(p[p.groupby('athlete_id')['year'].transform('size') > 1].reset_index(drop=True))
    g = gaps(tenth_effects(a['beta'], list(a['conditions'].index)))
    for col in ['front', 'back']:
        out['as measured, {}, {}'.format(since, col)] = slope(g, col)
    return out


def plain_check(panel, n=N_BOOTSTRAP, seed=0):
    #the start position model's answers without it. each result against the skier's own usual from their other races,
    #through the simple year to year model only (one conditions effect per race, nothing about tenths or starts), then
    #skiers of the same speed split by where they started. a late start goes with being off form in every race, so
    #each race is read against the average race
    base = fit_model(panel)
    typical, cuts = tenth_cuts(base)
    p = base['panel']
    tenth = np.searchsorted(cuts, p['athlete_id'].map(typical))
    totals = p.groupby('athlete_id')['form'].agg(['sum', 'count'])
    usual = (p['athlete_id'].map(totals['sum']) - p['form']) / (p['athlete_id'].map(totals['count']) - 1)
    dev = (p['form'] - usual).values
    behind = (p['start_pos'] - p['start_pos'].groupby([p['year'], tenth]).transform('median')).values
    years = np.array(sorted(p['year'].unique()))
    yi = np.searchsorted(years, p['year'].values)
    level = base['conditions']['effect'].rename(lambda c: int(c))[PLAIN_YEAR]
    late, on_time = behind > LATE, np.abs(behind) <= ON_TIME
    cell = yi * GROUPS + tenth
    speed = np.select([np.isin(tenth, FASTEST_FIFTH), np.isin(tenth, MIDDLE_FIFTH)], [0, 1], -1)
    start = np.select([p['start_pos'] < UP_FRONT, p['start_pos'].between(*MID_PACK)], [0, 1], -1)

    def means(keys, mask, w, size):
        count = np.bincount(keys[mask], w[mask], size)
        return np.bincount(keys[mask], (w * dev)[mask], size) / np.maximum(count, 1e-12), count

    def compute(w):
        #each race: late minus on time starters of the same tenth, averaged over the tenths, against the average race
        late_mean, n_late = means(cell, late, w, len(years) * GROUPS)
        on_mean, n_on = means(cell, on_time, w, len(years) * GROUPS)
        ok = (n_late >= MIN_CELL) & (n_on >= MIN_CELL)
        weight = np.where(ok, n_late, 0).reshape(len(years), GROUPS)
        diff = np.where(ok, late_mean - on_mean, 0).reshape(len(years), GROUPS)
        by_race = (diff * weight).sum(axis=1) / weight.sum(axis=1)
        #one race, the fastest and middle fifths by where they started: % slower than their own usual, against what
        #that same group does in the average race
        table = np.empty((2, 2))
        for a in range(2):
            for b in range(2):
                m, count = means(yi, (speed == a) & (start == b), w, len(years))
                m = np.where(count > 0, m, np.nan)
                table[a, b] = 100 * (np.exp(level + m[years == PLAIN_YEAR][0] - np.nanmean(m)) - 1)
        return 100 * (by_race - by_race.mean()), table

    by_race, table = compute(np.ones(len(p)))
    athletes = pd.factorize(p['athlete_id'])[0]
    rng = np.random.default_rng(seed)
    draws = [compute(np.bincount(rng.integers(0, athletes.max() + 1, athletes.max() + 1),
                                 minlength=athletes.max() + 1)[athletes].astype(float)) for _ in range(n)]
    race_draws, table_draws = np.array([d[0] for d in draws]), np.array([d[1] for d in draws])
    gap = (pd.Series(p['start_pos'].values[late]).groupby(p['year'].values[late]).mean() -
           pd.Series(p['start_pos'].values[on_time]).groupby(p['year'].values[on_time]).mean()).reindex(years)
    races = pd.DataFrame({'plain': by_race, 'lo': np.quantile(race_draws, 0.025, axis=0),
                          'hi': np.quantile(race_draws, 0.975, axis=0), 'start_gap': gap.values}, index=years)
    counts = [[int(((speed == a) & (start == b) & (p['year'].values == PLAIN_YEAR)).sum()) for b in range(2)]
              for a in range(2)]
    #the comparisons the table is for: same start different speed, same speed different start
    pairs = {'mid-pack starters, fastest minus middle fifth': ((0, 1), (1, 1)),
             'up front starters, fastest minus middle fifth': ((0, 0), (1, 0)),
             'fastest fifth, mid-pack minus up front starters': ((0, 1), (0, 0)),
             'middle fifth, mid-pack minus up front starters': ((1, 1), (1, 0))}
    #a draw can leave a small cell empty, those draws don't count toward its range
    contrasts = {k: (table[a] - table[b], *np.nanquantile(table_draws[:, a[0], a[1]] - table_draws[:, b[0], b[1]],
                                                           [0.025, 0.975]), min(counts[a[0]][a[1]], counts[b[0]][b[1]]))
                 for k, (a, b) in pairs.items()}
    return {'races': races, 'table': table, 'table_lo': np.nanquantile(table_draws, 0.025, axis=0),
            'table_hi': np.nanquantile(table_draws, 0.975, axis=0), 'counts': counts, 'contrasts': contrasts,
            'draws': race_draws}


def raw_spread(linked, tech):
    #minutes from the 10th to the 90th percentile finisher each year, and the ratio between them
    r = linked[(linked['race'] == 'birkie') & (linked['tech'] == tech) & (linked['status'] == 'finished') &
               (linked['variant'] == 'main') & (linked['year'] >= FIRST_YEAR) & ~linked['year'].isin(LEAVE_OUT_YEARS + [2024])]
    q = r.groupby('year')['time_s'].quantile([0.1, 0.9]).unstack() / 60
    return pd.DataFrame({'p10': q[0.1], 'p90': q[0.9], 'minutes': q[0.9] - q[0.1], 'ratio': q[0.9] / q[0.1]})


#---------------------------------------------------------------- output

def print_summary(results):
    for tech, r in results.items():
        print('\n==== birkie {}: {} results from {} skiers'.format(tech, r['n'], r['skiers']))
        raw = r['raw']
        print('raw spread, 10th to 90th percentile finisher: {:.0f} min in 2014, {:.0f} min in the average other '
              'year; as a ratio {:.2f} in 2014, {:.2f} on average'.format(
                  raw.loc[2014, 'minutes'], raw.drop(2014)['minutes'].mean(), raw.loc[2014, 'ratio'],
                  raw.drop(2014)['ratio'].mean()))
        print('typical finish time on an average day, by tenth (h): ' +
              ' '.join('{:.2f}'.format(t) for t in r['typical']))
        print('% slower than that tenth\'s average race, fastest tenth to slowest:')
        print(r['pct'].round(1).to_string())
        g = r['gaps']
        print('\nfront (fastest tenth) and back (slowest tenth) minus the middle fifth, % points [95% CI]:')
        for year, row in g.iterrows():
            print('  {}  race {:+5.1f}%   front {:+5.1f} [{:+5.1f}, {:+5.1f}]   back {:+5.1f} [{:+5.1f}, {:+5.1f}]'.format(
                year, row['level'], row['front'], row['front_lo'], row['front_hi'], row['back'], row['back_lo'],
                row['back_hi']))
        for col in ['front', 'back']:
            for trend in [False, True]:
                est, lo, hi = r['slopes'][(col, trend)]
                print('{} gap per {}% slower race{}: {:+.2f} points [{:+.2f}, {:+.2f}]'.format(
                    col, PER, ' (with a trend over the years)' if trend else '', est, lo, hi))

        s = r['start']['gaps']
        print('\nholding start position fixed. start cost: extra % for the last starter over the first, compared with '
              'the average race')
        for year, row in s.iterrows():
            print('  {}  start cost {:+5.1f} [{:+5.1f}, {:+5.1f}]   front {:+5.1f} (was {:+5.1f})   back {:+5.1f} '
                  '(was {:+5.1f})'.format(year, row['start'], row['start_lo'], row['start_hi'], row['front'],
                                         r['gaps'].loc[year, 'front'], row['back'], r['gaps'].loc[year, 'back']))
        for col in ['front', 'back', 'start']:
            est, lo, hi = r['start']['slopes'][(col, False)]
            print('{} per {}% slower race, same start: {:+.2f} points [{:+.2f}, {:+.2f}]'.format(
                col, PER, est, lo, hi))
        print('checks, per {}% slower race:'.format(PER))
        for k, v in r['checks'].items():
            print('  {:45s} {:+.2f}'.format(k, v))

        pl = r['plain']
        races = pl['races'].join(r['gaps']['level'])
        races['model'] = s['start'] * races['start_gap']
        print('\nplain check: late starters (more than {:.0%} of the field behind the usual for their speed) minus '
              'on-time starters of the same tenth, % points against the average race, and the start position '
              'model\'s cost for the same start gap'.format(LATE))
        for year, row in races.iterrows():
            print('  {}  plain {:+5.1f} [{:+5.1f}, {:+5.1f}]   model {:+5.1f}   start gap {:.2f}'.format(
                year, row['plain'], row['lo'], row['hi'], row['model'], row['start_gap']))
        print('  plain vs model, correlation over races: {:.2f}'.format(np.corrcoef(races['plain'], races['model'])[0, 1]))
        for label, keep in [('all races', races.index), ('{} on'.format(CHECK_FROM), races.index[races.index >= CHECK_FROM])]:
            pick = np.isin(races.index, keep)
            draws = [np.polyfit(races.loc[keep, 'level'] / PER, d[pick], 1)[0] for d in pl['draws']]
            print('  plain per {}% slower race, {}: {:+.2f} [{:+.2f}, {:+.2f}]'.format(
                PER, label, np.polyfit(races.loc[keep, 'level'] / PER, races.loc[keep, 'plain'], 1)[0],
                *np.quantile(draws, [0.025, 0.975])))
        print('{}, % slower than their own usual, against what the same group does in the average race:'.format(
            PLAIN_YEAR))
        for a, name in enumerate(['fastest fifth', 'middle fifth']):
            print('  {:14s}'.format(name) + '   '.join(
                '{} {:5.1f} [{:5.1f}, {:5.1f}] n={}'.format(where, pl['table'][a, b], pl['table_lo'][a, b],
                                                            pl['table_hi'][a, b], pl['counts'][a][b])
                for b, where in enumerate(['started up front', 'started mid-pack'])))
        for k, (est, lo, hi, n) in pl['contrasts'].items():
            print('  {:50s} {:+5.1f} [{:+5.1f}, {:+5.1f}]{}'.format(
                k, est, lo, hi, '' if n >= MIN_TABLE else '   (only {} skiers, too few)'.format(n)))


def hours(h):
    return '{:d}:{:02d}'.format(int(h), int(round(60 * (h - int(h))))) if round(60 * (h - int(h))) < 60 else \
        '{:d}:00'.format(int(h) + 1)


def place_labels(ax, points, size=(20, 8)):
    #year labels next to their points, each on the first side where it doesn't cover a label already placed.
    #offsets and the label size are in points, positions on screen in pixels
    placed = []
    ax.get_xlim(), ax.get_ylim()            #settles the autoscaled limits, so the transform below is final
    to_px = ax.transData.transform
    k = ax.figure.dpi / 72
    for (x, y), text, kwargs in sorted(points, key=lambda p: -p[0][1]):
        px, py = to_px((x, y))
        for dx, dy in [(6, 3), (6, -10), (-6 - size[0], 3), (-6 - size[0], -10), (6, 11), (6, -19)]:
            box = (px + k * dx, py + k * dy, px + k * (dx + size[0]), py + k * (dy + size[1]))
            if all(box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3] for b in placed):
                break
        placed.append(box)
        ax.annotate(text, (x, y), xytext=(dx, dy), textcoords='offset points', **kwargs)


def plot_front_back(results):
    fig = plt.figure(figsize=(14, 10), facecolor=SURFACE)
    grid = fig.add_gridspec(2, 2, width_ratios=[1.35, 1], hspace=0.38, wspace=0.22, top=0.9)
    titles = {'skate': ('Skate: in 2014 the front of the field lost the least',
                        'Skate: slow years cost the front less than the middle'),
              'classic': ('Classic: the back of the field swings the least',
                          'Classic: slow years cost the back less, fast years help it less')}
    for row, tech in enumerate(TECHS):
        r = results[tech]
        x = r['typical'].values

        #every race's effect along the field, the picked out years in color
        ax = fig.add_subplot(grid[row, 0])
        ax.axhline(0, color=INK_2, linewidth=0.8)
        for year, values in r['pct'].iterrows():
            if year not in HIGHLIGHT:
                ax.plot(x, values.values, color=OTHER, linewidth=1, zorder=1)
        for year, color in HIGHLIGHT.items():
            ax.fill_between(x, r['lo'].loc[year].values, r['hi'].loc[year].values, color=color, alpha=0.15,
                            linewidth=0, zorder=2)
            ax.plot(x, r['pct'].loc[year].values, color=color, linewidth=2, marker='o', markersize=6,
                    markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=3, label=str(year))
            ax.annotate(str(year), (x[-1], r['pct'].loc[year].values[-1]), xytext=(8, 0), textcoords='offset points',
                        va='center', fontsize=9, color=INK)
        ax.plot([], [], color=OTHER, linewidth=1, label='other years')
        ax.set_xscale('log')
        ax.set_xticks(x)
        ax.set_xticklabels([hours(h) for h in x])
        ax.minorticks_off()
        ax.set_xlim(x[0] * 0.97, x[-1] * 1.06)
        style(ax, titles[tech][0], '% slower than that tenth\'s average Birkie',
              'typical finish time on an average day: each tenth of the field, fastest to slowest')
        ax.legend(loc='upper left', fontsize=8, frameon=False, ncol=4)
        lo, hi = ax.get_ylim()
        ax.set_ylim(lo, hi + 0.08 * (hi - lo))

        #one end's gap from the middle against how slow the race was, every race
        ax = fig.add_subplot(grid[row, 1])
        g, end = r['gaps'], GAP_SHOWN[tech]
        ax.axhline(0, color=INK_2, linewidth=0.8)
        labels = []
        for year, gr in g.iterrows():
            color = HIGHLIGHT.get(year, OTHER)
            ax.vlines(gr['level'], gr[end + '_lo'], gr[end + '_hi'], color=color, linewidth=1.2, zorder=2)
            ax.plot(gr['level'], gr[end], 'o', color=color, markersize=8 if year in HIGHLIGHT else 6,
                    markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=3)
            labels.append(((gr['level'], gr[end]), str(year),
                           {'fontsize': 8 if year in HIGHLIGHT else 7, 'color': INK if year in HIGHLIGHT else INK_2}))
        est, lo, hi = r['slopes'][(end, False)]
        xs = np.array([g['level'].min(), g['level'].max()])
        fit_line = np.polyfit(g['level'], g[end], 1)
        ax.plot(xs, np.polyval(fit_line, xs), color=INK_2, linewidth=1.2, linestyle='--', zorder=1)
        ax.text(0.03, 0.04, '{:+.1f} points per {}% slower race [{:+.1f} to {:+.1f}]'.format(est, PER, lo, hi),
                transform=ax.transAxes, fontsize=8, color=INK_2)
        style(ax, titles[tech][1], '{}\'s % slower minus the middle\'s, % points'.format(GAP_NAMES[end]),
              'how slow the race was, % slower than the average Birkie')
        place_labels(ax, labels)
    fig.suptitle('Does a slow Birkie hit the front of the field and the back the same? The same skiers compared '
                 'from one year to the next', x=0.06, ha='left', fontsize=13, color=INK)
    os.makedirs('graphs', exist_ok=True)
    fig.savefig('graphs/front_back.png', dpi=130, bbox_inches='tight', facecolor=SURFACE)
    plt.close(fig)


def plot_start(results):
    fig = plt.figure(figsize=(14, 10), facecolor=SURFACE)
    grid = fig.add_gridspec(2, 2, hspace=0.38, wspace=0.22, top=0.9)
    titles = {'skate': ('Skate: a late start costs more some years, less others',
                        'Skate: the front\'s edge isn\'t from starting first'),
              'classic': ('Classic: a late start cost much more in 2009-2012',
                          'Classic: the start is part of the back\'s gap, mostly before 2013')}
    since = '{} on'.format(CHECK_FROM)
    for row, tech in enumerate(TECHS):
        r = results[tech]
        s = r['start']['gaps']
        level = r['gaps']['level']

        #each race's cost of starting at the back rather than the front, skiers of the same speed
        ax = fig.add_subplot(grid[row, 0])
        ax.axhline(0, color=INK_2, linewidth=0.8)
        labels = []
        for year, gr in s.iterrows():
            color = HIGHLIGHT.get(year, OTHER)
            ax.vlines(level[year], gr['start_lo'], gr['start_hi'], color=color, linewidth=1.2, zorder=2)
            ax.plot(level[year], gr['start'], 'o', color=color, markersize=8 if year in HIGHLIGHT else 6,
                    markeredgecolor=SURFACE, markeredgewidth=1.2, zorder=3)
            labels.append(((level[year], gr['start']), str(year),
                           {'fontsize': 8 if year in HIGHLIGHT else 7, 'color': INK if year in HIGHLIGHT else INK_2}))
        est, lo, hi = r['start']['slopes'][('start', False)]
        xs = np.array([level.min(), level.max()])
        ax.plot(xs, np.polyval(np.polyfit(level, s['start'], 1), xs), color=INK_2, linewidth=1.2, linestyle='--',
                zorder=1)
        ax.text(0.97, 0.94, '{:+.1f} points per {}% slower race [{:+.1f} to {:+.1f}], {:+.1f} from {}'.format(
            est, PER, lo, hi, r['checks']['same start, {}, start'.format(since)], since), transform=ax.transAxes,
            fontsize=8, color=INK_2, ha='right')
        style(ax, titles[tech][0], 'last starter\'s % slower minus the first\'s,\ncompared with the average race',
              'how slow the race was, % slower than the average Birkie')
        place_labels(ax, labels)

        #the end of the field's gap from the middle, as measured and among skiers who started in the same place
        ax = fig.add_subplot(grid[row, 1])
        end = GAP_SHOWN[tech]
        ax.axhline(0, color=INK_2, linewidth=0.8)
        ax.vlines(level, r['gaps'][end], s[end], color=GRID, linewidth=1.5, zorder=1)
        ax.plot(level, r['gaps'][end], 'o', color=SURFACE, markeredgecolor=INK_2, markeredgewidth=1.2, markersize=7,
                zorder=2, label='as measured')
        ax.plot(level, s[end], 'o', color=INK, markeredgecolor=SURFACE, markeredgewidth=1.2, markersize=8, zorder=3,
                label='same start position')
        for values, line, name in [(r['gaps'][end], '--', 'as measured'), (s[end], '-', 'same start position')]:
            ax.plot(xs, np.polyval(np.polyfit(level, values, 1), xs), color=INK_2 if line == '--' else INK,
                    linewidth=1.2, linestyle=line, zorder=1)
        #room under the points for the two lines of slopes
        lo_y, hi_y = ax.get_ylim()
        ax.set_ylim(lo_y - 0.2 * (hi_y - lo_y), hi_y)
        labels = [((level[y], s.loc[y, end]), str(y), {'fontsize': 8, 'color': INK}) for y in HIGHLIGHT]
        place_labels(ax, labels)
        measured, same = r['slopes'][(end, False)], r['start']['slopes'][(end, False)]
        ax.text(0.03, 0.04, 'per {}% slower race: {:+.1f} as measured, {:+.1f} [{:+.1f} to {:+.1f}] at the same '
                'start\nfrom {}: {:+.1f} as measured, {:+.1f} at the same start'.format(
                    PER, measured[0], *same, since, r['checks']['as measured, {}, {}'.format(since, end)],
                    r['checks']['same start, {}, {}'.format(since, end)]),
                transform=ax.transAxes, fontsize=8, color=INK_2)
        style(ax, titles[tech][1], '{}\'s % slower minus the middle\'s, % points'.format(GAP_NAMES[end]),
              'how slow the race was, % slower than the average Birkie')
        ax.legend(loc='upper right', fontsize=8, frameon=False)
    fig.suptitle('Is it the skiers or the start? Holding start position fixed (from the bib\'s wave)', x=0.06,
                 ha='left', fontsize=13, color=INK)
    fig.savefig('graphs/front_back_start.png', dpi=130, bbox_inches='tight', facecolor=SURFACE)
    plt.close(fig)


if __name__ == '__main__':
    main()
