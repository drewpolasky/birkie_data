#year to year changes in individual performance, built on the athlete links from athlete_linking.py
#
#raw finish times swing 20-30% between years with snow and weather, so each race is modeled as
#   log(finish time) = skier's ability + that race's conditions + age effect + experience effect + noise
#with the skier's ability as a fixed effect, so conditions, aging and learning are all measured from the same
#skiers changing from one year to the next, never by comparing different people.
#
#two assumptions make that possible. age goes up a year every year, so a steady drift in conditions and a steady
#aging trend look identical from inside the data. the age effect is assumed flat from 25 to 35, so 25-35 year olds'
#year to year changes pin down the conditions. likewise learning is assumed to be done after the 5th race.
#2024 is left out (shortened course), and so are the open track and 2024 elite races.
#
#example usage:
#python performance_changes.py --race birkie --tech skate
#python performance_changes.py --race birkie --tech skate --name "drew polasky"
import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from athlete_linking import link_athletes, first_name_relation
from results_loader import load_all_results, compact

EXCLUDE_YEARS = [2024]
#a different course. its races keep their own conditions, but aren't part of the average year they're measured from
DIFFERENT_COURSE = [2021]
EXCLUDE_VARIANTS = ['openTrack', 'elite']
#age bands with their own slope. 25-35 is the reference band, held flat
AGE_BANDS = [('<25', None, 25), ('35-45', 35, 45), ('45-55', 45, 55), ('55-65', 55, 65), ('65-75', 65, 75), ('75+', 75, None)]
NEWCOMER_FROM = 2012            #no results at all before this, so probably new to the birkie
LEARNING_RACES = 4              #separate effects for a newcomer's 1st-4th race, 5th+ is the reference
OUTLIER_SIGMAS = 4
N_BOOTSTRAP = 200

#chart colors (reference palette from the dataviz guidance), hairline gray grid
COLORS = {'M': '#2a78d6', 'F': '#eb6834', 'third': '#1baf7a'}
INK, INK_2, GRID, SURFACE = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--race", type=str, default='birkie')
    parser.add_argument("--tech", type=str, default='skate')
    parser.add_argument("--name", type=str, default='', help='also plot this skier\'s condition adjusted history')
    parser.add_argument("--linked", type=str, default='linked_data/linked_results.csv')
    parser.add_argument("--keep_shared_names", action='store_true',
                        help='keep athletes whose exact name belongs to more than one athlete')
    args = parser.parse_args()

    linked = load_linked(args.linked)
    panel = build_panel(linked, args.race, args.tech, drop_shared_names=not args.keep_shared_names)
    fit = fit_model(panel)
    boot = bootstrap(fit)
    changes = consecutive_changes(fit)

    print_summary(fit, boot, changes)
    label = args.race + '_' + args.tech
    plot_overview(fit, boot, changes, linked, label)
    if args.name:
        plot_skier(fit, args.name, label)
    fit['panel'].to_csv(os.path.join(os.path.dirname(args.linked) or '.', 'performance_' + label + '.csv'), index=False)


#---------------------------------------------------------------- data

def load_linked(path):
    if os.path.exists(path):
        return pd.read_csv(path)
    print('no {}, linking from scratch (run athlete_linking.py to cache it)'.format(path))
    return link_athletes(load_all_results())


def athlete_birth_years(linked):
    #exact birth year from ages (2021+). failing that, the middle of whatever range the age groups (2016-2020) allow
    exact = (linked['year'] - linked['age']).groupby(linked['athlete_id']).median()
    lo = (linked['year'] - linked['age_max'] - 1).groupby(linked['athlete_id']).max()
    hi = (linked['year'] - linked['age_min']).groupby(linked['athlete_id']).min()
    from_groups = ((lo + hi) / 2).where(lo <= hi)
    return exact.fillna(from_groups)


def athlete_genders(linked):
    g = linked[linked['gender'].isin(['M', 'F'])]
    return g.groupby('athlete_id')['gender'].agg(lambda s: s.value_counts().index[0])


def build_panel(linked, race, tech, drop_shared_names=True):
    birth = athlete_birth_years(linked)
    gender = athlete_genders(linked)
    first_year = linked.groupby('athlete_id')['year'].min()

    p = linked[(linked['race'] == race) & (linked['tech'] == tech) & (linked['variant'] != 'openTrack')].copy()
    #experience counts every start in this race, including DNFs and the shortened 2024 race
    p = p.sort_values(['athlete_id', 'year'])
    p['race_number'] = p.groupby('athlete_id').cumcount() + 1
    p['newcomer'] = p['athlete_id'].map(first_year) >= NEWCOMER_FROM
    p = p[(p['status'] == 'finished') & ~p['year'].isin(EXCLUDE_YEARS) & ~p['variant'].isin(EXCLUDE_VARIANTS)]
    if drop_shared_names:
        #anyone who shares a name with another athlete might have some of the other's results mixed in
        p = p[p.groupby('athlete_id')['name_shared'].transform('max') == 1]
    p['birth_year'] = p['athlete_id'].map(birth)
    p['sex'] = p['athlete_id'].map(gender)
    p = p.dropna(subset=['birth_year', 'sex', 'time_s'])
    p['age_at_race'] = p['year'] - p['birth_year']
    #2021 was raced in waves on different days, each day gets its own conditions
    p['condition'] = p['year'].astype(str).where(p['variant'] == 'main', p['year'].astype(str) + ' ' + p['variant'])
    p['log_time'] = np.log(p['time_s'] / 3600)
    #a skier only helps measure change if they raced this more than once
    p = p[p.groupby('athlete_id')['year'].transform('size') > 1]
    return p.reset_index(drop=True)


#---------------------------------------------------------------- model

def design(panel):
    #everything except the athlete's own ability: race conditions, age slopes by gender, newcomer race number
    cols = {}
    conditions = sorted(panel['condition'].unique())
    for c in conditions[1:]:
        cols['cond ' + c] = (panel['condition'] == c).astype(float)
    age = panel['age_at_race']
    for sex in ['M', 'F']:
        is_sex = (panel['sex'] == sex).astype(float)
        for band, lo, hi in AGE_BANDS:
            cols['age {} {}'.format(sex, band)] = age_basis(age, lo, hi) * is_sex
    for n in range(1, LEARNING_RACES + 1):
        cols['race {}'.format(n)] = (panel['newcomer'] & (panel['race_number'] == n)).astype(float)
    return pd.DataFrame(cols, index=panel.index), conditions


def age_basis(age, lo, hi):
    #years of age spent inside this band, so each coefficient is the slope within its band
    if lo is None:
        return np.minimum(age - hi, 0)
    if hi is None:
        return np.maximum(age - lo, 0)
    return np.clip(age - lo, 0, hi - lo)


def fit_model(panel, extra=None):
    #extra: more columns for the model, on panel's index (snow_effect.py adds snow at home)
    X, conditions = design(panel)
    if extra is not None:
        X = X.join(extra)
    beta, keep = solve_within(panel, X, np.ones(len(panel), dtype=bool))
    #one refit without wild outliers (injuries, broken equipment, timing errors)
    resid = within(panel['log_time'], panel['athlete_id'], keep) - within(X, panel['athlete_id'], keep) @ beta
    sigma = 1.4826 * np.median(np.abs(resid[keep]))
    keep = keep & (np.abs(resid) < OUTLIER_SIGMAS * sigma)
    keep &= panel['athlete_id'].map(pd.Series(keep).groupby(panel['athlete_id']).sum()).values > 1
    beta, keep = solve_within(panel, X, keep)

    panel = panel[keep].copy()
    X = X[keep]
    effects = X @ beta
    panel['ability'] = (panel['log_time'] - effects).groupby(panel['athlete_id']).transform('mean')
    panel['resid'] = panel['log_time'] - effects - panel['ability']
    #performance with conditions, aging and learning all taken out: the skier's ability plus that day's luck
    panel['form'] = panel['log_time'] - effects
    #performance with conditions taken out, as a finish time on an average day
    cond = condition_effects(beta, conditions)
    panel['condition_effect'] = panel['condition'].map(cond['effect'])
    panel['adjusted'] = panel['log_time'] - panel['condition_effect']
    panel['adjusted_time_s'] = np.exp(panel['adjusted']) * 3600

    n_athletes = panel['athlete_id'].nunique()
    dof = len(panel) - n_athletes - len(beta)
    sigma_e = np.sqrt((panel['resid'] ** 2).sum() / dof)
    races = panel.groupby('athlete_id').size()
    ability = panel.groupby('athlete_id')['ability'].first()
    #the spread of fitted abilities includes some noise from skiers with only a few races, take that back out
    sigma_a = np.sqrt(max(ability.var() - (sigma_e ** 2 / races).mean(), 0))
    return {'panel': panel, 'X': X, 'beta': beta, 'conditions': cond, 'sigma_e': sigma_e, 'sigma_a': sigma_a,
            'n_dropped': int((~keep).sum())}


def within(values, groups, keep):
    #subtract each athlete's mean, over the kept rows only
    values = pd.DataFrame(values) if isinstance(values, pd.DataFrame) else pd.Series(values)
    kept = values[keep]
    return (values - kept.groupby(groups[keep]).transform('mean').reindex(values.index)).values


def solve_within(panel, X, keep):
    y = within(panel['log_time'], panel['athlete_id'], keep)
    Xw = within(X, panel['athlete_id'], keep)
    beta = np.linalg.lstsq(Xw[keep], y[keep], rcond=None)[0]
    return pd.Series(beta, index=X.columns), keep


def condition_effects(beta, conditions):
    #log effect of each race's conditions, centered on the average race on the usual course
    effect = pd.Series(0.0, index=conditions)
    for c in conditions[1:]:
        effect[c] = beta['cond ' + c]
    usual = [c for c in conditions if int(c.split()[0]) not in DIFFERENT_COURSE]
    effect -= effect[usual].mean()
    return pd.DataFrame({'effect': effect, 'pct': 100 * (np.exp(effect) - 1)})


def age_curve(beta, sex, ages):
    #% slower than at 30
    f = sum(beta['age {} {}'.format(sex, band)] * age_basis(ages, lo, hi) for band, lo, hi in AGE_BANDS)
    return 100 * (np.exp(f) - 1)


def bootstrap(fit, n=N_BOOTSTRAP, seed=0, clusters=None):
    #resample skiers, for uncertainty on the conditions, age curves and learning effects. clusters (one label per
    #panel row, the same for all of a skier's rows) resamples whole groups of skiers instead
    panel, X = fit['panel'], fit['X']
    keep = np.ones(len(panel), dtype=bool)
    y = within(panel['log_time'], panel['athlete_id'], keep)
    Xw = within(X, panel['athlete_id'], keep)
    groups = panel['athlete_id'] if clusters is None else clusters
    rows = pd.Series(np.arange(len(panel))).groupby(np.asarray(groups)).apply(np.array)
    rng = np.random.default_rng(seed)
    betas = []
    for _ in range(n):
        idx = np.concatenate(rows.values[rng.integers(0, len(rows), len(rows))])
        betas.append(np.linalg.lstsq(Xw[idx], y[idx], rcond=None)[0])
    return pd.DataFrame(betas, columns=X.columns)


#---------------------------------------------------------------- year to year changes

def consecutive_changes(fit):
    #each pair of back to back races by the same skier: consecutive years, or skipping over 2017 (cancelled)
    #or 2024 (left out)
    p = fit['panel'].sort_values(['athlete_id', 'year'])
    nxt = p.groupby('athlete_id').shift(-1)
    pairs = p.assign(next_year=nxt['year'], next_adjusted=nxt['adjusted'], next_form=nxt['form'],
                     next_age=nxt['age_at_race']).dropna(subset=['next_year'])
    gap = pairs['next_year'] - pairs['year']
    pairs = pairs[(gap == 1) | ((gap == 2) & (pairs['year'] + 1).isin([2017] + EXCLUDE_YEARS))].copy()
    pairs['change_pct'] = 100 * (np.exp(pairs['next_adjusted'] - pairs['adjusted']) - 1)

    #how much of a good or bad day carries over: deviation from the skier's usual, with aging and learning taken
    #out, where usual comes from their other races (not this pair) so a lucky year can't define its own baseline
    totals = p.groupby('athlete_id')['form'].agg(['sum', 'count'])
    n_other = pairs['athlete_id'].map(totals['count']) - 2
    usual = (pairs['athlete_id'].map(totals['sum']) - pairs['form'] - pairs['next_form']) / n_other
    pairs['usual_ok'] = n_other >= 2
    pairs['dev'] = 100 * (np.exp(pairs['form'] - usual) - 1)
    pairs['next_dev'] = 100 * (np.exp(pairs['next_form'] - usual) - 1)
    return pairs


#---------------------------------------------------------------- output

def print_summary(fit, boot, changes):
    p = fit['panel']
    beta = fit['beta']
    print('{} results from {} skiers with 2+ races ({} outliers dropped)'.format(
        len(p), p['athlete_id'].nunique(), fit['n_dropped']))
    print('\nspread of ability between skiers: {:.1f}%   year to year noise for one skier: {:.1f}%'.format(
        100 * fit['sigma_a'], 100 * fit['sigma_e']))
    print('share of the variation in (condition adjusted) times that is the skier, not the year: {:.0%}'.format(
        fit['sigma_a'] ** 2 / (fit['sigma_a'] ** 2 + fit['sigma_e'] ** 2)))

    c = changes['change_pct']
    print('\nback to back races: {}. condition adjusted change, median {:+.1f}%, half within {:.1f}%, 90% within {:.1f}%'.format(
        len(c), c.median(), c.abs().quantile(0.5), c.abs().quantile(0.9)))

    print('\nconditions (% slower than an average year):')
    print(fit['conditions']['pct'].round(1).to_string())

    print('\naging, % slower per year of age within each band (25-35 held flat):')
    for sex in ['M', 'F']:
        row = []
        for band, lo, hi in AGE_BANDS:
            k = 'age {} {}'.format(sex, band)
            est, lo_ci, hi_ci = 100 * beta[k], 100 * boot[k].quantile(0.025), 100 * boot[k].quantile(0.975)
            if band == '<25':
                est, lo_ci, hi_ci = -est, -hi_ci, -lo_ci        #report as change when getting older
            row.append('{} {:+.2f} [{:+.2f}, {:+.2f}]'.format(band, est, lo_ci, hi_ci))
        print(' ', sex, '   '.join(row))

    print('\nnewcomers (no results before {}), % slower than in their 5th+ race:'.format(NEWCOMER_FROM))
    for n in range(1, LEARNING_RACES + 1):
        k = 'race {}'.format(n)
        print('  race {}: {:+.1f}% [{:+.1f}, {:+.1f}]  ({} results)'.format(
            n, 100 * (np.exp(beta[k]) - 1), 100 * (np.exp(boot[k].quantile(0.025)) - 1),
            100 * (np.exp(boot[k].quantile(0.975)) - 1), int(fit['X'][k].sum())))

    d = changes[changes['usual_ok']]
    slope = np.polyfit(d['dev'], d['next_dev'], 1)[0]
    print('\nafter a race X% off your usual, the next year averages {:.0%} of X off your usual ({} pairs)'.format(
        slope, len(d)))


def style(ax, title, ylabel, xlabel=''):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc='left', fontsize=11, color=INK)
    ax.set_ylabel(ylabel, color=INK_2, fontsize=9)
    ax.set_xlabel(xlabel, color=INK_2, fontsize=9)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ['top', 'right']:
        ax.spines[side].set_visible(False)
    for side in ['left', 'bottom']:
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=8)


def plot_overview(fit, boot, changes, linked, label):
    beta = fit['beta']
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), facecolor=SURFACE)

    #conditions, next to the raw field median so the adjustment is visible
    ax = axes[0, 0]
    cond = fit['conditions']
    race, tech = label.split('_')
    field = linked[(linked['race'] == race) & (linked['tech'] == tech) & (linked['status'] == 'finished')]
    field = field.assign(condition=field['year'].astype(str).where(field['variant'] == 'main',
                                                                   field['year'].astype(str) + ' ' + field['variant']))
    field_median = np.log(field.groupby('condition')['time_s'].median()).reindex(cond.index)
    #both lines measured from the average race on the usual course
    usual = np.array([int(c.split()[0]) not in DIFFERENT_COURSE for c in cond.index])
    field_median = 100 * (np.exp(field_median - field_median[usual].mean()) - 1)
    #an all-elite wave's median says nothing about the snow
    field_median[[c for c in cond.index if 'elite' in c]] = np.nan
    keys = ['cond ' + c for c in cond.index[1:]]
    draws = np.column_stack([np.zeros(len(boot)), boot[keys].values])
    draws = 100 * (np.exp(draws - draws[:, usual].mean(axis=1, keepdims=True)) - 1)
    lo = pd.Series(np.percentile(draws, 2.5, axis=0), index=cond.index)
    hi = pd.Series(np.percentile(draws, 97.5, axis=0), index=cond.index)

    order = sorted(cond.index, key=condition_x)
    x = np.array([condition_x(c) for c in order])
    #break the lines over years with no comparable race, and on either side of a different course
    missing = np.diff(x) > 1.5
    other_course = np.isin([int(c.split()[0]) for c in order], DIFFERENT_COURSE).astype(int)
    breaks = np.where(missing | (np.diff(other_course) != 0))[0] + 1
    break_x = (x[breaks - 1] + x[breaks]) / 2
    line = lambda values: (np.insert(x, breaks, break_x), np.insert(values.reindex(order).values, breaks, np.nan))
    gap_x = break_x[missing[breaks - 1]]
    ax.axhline(0, color=INK_2, linewidth=0.8)
    ax.plot(*line(field_median), color='#b4b2ab', marker='o', markersize=4, linewidth=1.5, label='median finisher (raw)')
    ax.plot(*line(cond['pct']), color=COLORS['M'], marker='o', markersize=5, linewidth=2,
            label='same skiers, year to year (model)')
    ax.vlines(x, lo.reindex(order), hi.reindex(order), color=COLORS['M'], linewidth=1)
    for gx in gap_x:
        missing = 'cancelled' if round(gx) == 2017 else 'short course'
        ax.text(gx, 0, missing, rotation=90, ha='center', va='bottom', fontsize=7, color=INK_2)
    days = [c for c in order if ' ' in c]
    if days:
        low = min(days, key=lambda c: cond.loc[c, 'pct'])
        ax.annotate('2021: different course,\none point per race day', (condition_x(low), cond.loc[low, 'pct']),
                    xytext=(0, -24),
                    textcoords='offset points', ha='center', fontsize=7, color=INK_2)
    ax.set_xticks(range(int(x.min()), int(x.max()) + 1, 2))
    ax.legend(frameon=False, fontsize=8, loc='upper right')
    style(ax, 'How fast each race was', '% slower than an average year')

    #aging
    ax = axes[0, 1]
    p = fit['panel']
    for sex, name in [('M', 'men'), ('F', 'women')]:
        ages_seen = p.loc[p['sex'] == sex, 'age_at_race']
        ages = np.arange(max(16, np.floor(ages_seen.quantile(0.005))), min(80, np.ceil(ages_seen.quantile(0.995))) + 1)
        curves = np.array([age_curve(boot.iloc[i], sex, ages) for i in range(len(boot))])
        est = age_curve(beta, sex, ages)
        ax.fill_between(ages, np.percentile(curves, 2.5, axis=0), np.percentile(curves, 97.5, axis=0),
                        color=COLORS[sex], alpha=0.15, linewidth=0)
        ax.plot(ages, est, color=COLORS[sex], linewidth=2, label=name)
        ax.annotate(name, (ages[-1], est[-1]), xytext=(4, 0), textcoords='offset points', color=INK_2, fontsize=8,
                    va='center')
    ax.axvspan(25, 35, color=GRID, alpha=0.5, linewidth=0)
    ax.text(30, ax.get_ylim()[1], 'held flat', ha='center', va='top', fontsize=7, color=INK_2)
    ax.legend(frameon=False, fontsize=8, loc='upper left')
    style(ax, 'Aging, within the same skiers', '% slower than at 30', 'age')

    #learning
    ax = axes[1, 0]
    n = np.arange(1, LEARNING_RACES + 1)
    keys = ['race {}'.format(i) for i in n]
    est = 100 * (np.exp(beta[keys].values) - 1)
    draws = 100 * (np.exp(boot[keys].values) - 1)
    upper = np.percentile(draws, 97.5, axis=0)
    ax.bar(n, est, width=0.5, color=COLORS['third'])
    ax.errorbar(n, est, yerr=[est - np.percentile(draws, 2.5, axis=0), upper - est], fmt='none', ecolor=INK_2,
                linewidth=1)
    for xi, v, top in zip(n, est, upper):
        ax.annotate('{:+.1f}%'.format(v), (xi, max(top, 0)), xytext=(0, 4), textcoords='offset points',
                    ha='center', fontsize=8, color=INK)
    ax.axhline(0, color=INK_2, linewidth=0.8)
    ax.set_xticks(n)
    ax.set_xticklabels(['1st', '2nd', '3rd', '4th'])
    style(ax, 'New skiers: how much slower than by their 5th race', '% slower than 5th+ race',
          'race number (skiers with no results before {})'.format(NEWCOMER_FROM))

    #regression to the mean
    ax = axes[1, 1]
    d = changes[changes['usual_ok']]
    bins = np.arange(-20, 22.5, 2.5)
    d = d.assign(bin=pd.cut(d['dev'], bins))
    g = d.groupby('bin', observed=True).agg(dev=('dev', 'mean'), next_dev=('next_dev', 'mean'), n=('dev', 'size'))
    g = g[g['n'] >= 30]
    slope = np.polyfit(d['dev'], d['next_dev'], 1)[0]
    ax.plot([-20, 20], [-20, 20], color=GRID, linewidth=1)
    ax.annotate('no regression', (15, 15), xytext=(-4, 4), textcoords='offset points', ha='right', fontsize=7,
                color=INK_2)
    ax.axhline(0, color=INK_2, linewidth=0.8)
    ax.plot(g['dev'], g['next_dev'], color=COLORS['M'], marker='o', markersize=5, linewidth=2)
    ax.annotate('next year keeps {:.0%}'.format(slope), (g['dev'].iloc[-1], g['next_dev'].iloc[-1]),
                xytext=(0, 10), textcoords='offset points', ha='right', fontsize=8, color=INK)
    ax.set_xlim(-20, 20)
    ax.set_ylim(-20, 20)
    style(ax, 'About half of a good or bad year carries over', 'next year, % slower than usual',
          'this year, % slower than usual (aging and conditions taken out)')

    fig.suptitle('{} {}: year to year performance ({} skiers, {} races)'.format(
        race.capitalize(), tech, p['athlete_id'].nunique(), len(p)), x=0.01, ha='left', fontsize=13, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    path = 'graphs/{}_year_to_year.png'.format(label)
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    print('\nsaved', path)
    plt.close(fig)


def condition_x(condition):
    #where a race sits on a time axis. 2021's race days are spread out a little around 2021
    year, _, day = condition.partition(' ')
    offsets = {'wednesday': -0.3, 'thursday': -0.15, 'friday': -0.15, 'saturday': 0.05, 'sunday': 0.05,
               'saturday elite': 0.25, 'sunday elite': 0.25}
    return int(year) + offsets.get(day, 0)


def plot_skier(fit, name, label):
    p = fit['panel']
    key = compact(name)
    last = compact(name.split()[-1])
    first = compact(' '.join(name.split()[:-1]))
    #find the skier by name or nickname, then take all their races whatever name they used
    match = (p['last'].map(compact) == last) & p['first'].map(compact).map(lambda f: first_name_relation(f, first) is not None)
    ids = p.loc[match, 'athlete_id'].unique()
    if len(ids) != 1:
        print('\n{} matches {} skiers in this race, not plotting'.format(name, len(ids)))
        return
    rows = p[p['athlete_id'] == ids[0]].sort_values('year')
    #what the model expects from this skier on an average day: their ability, age and experience, without that day's luck
    rows = rows.assign(expected=rows['adjusted'] - rows['resid'])
    to_hours = lambda log_t: np.exp(log_t)

    fig, ax = plt.subplots(figsize=(9, 5), facecolor=SURFACE)
    ax.plot(rows['year'], to_hours(rows['log_time']), color='#b4b2ab', marker='o', markersize=5, linewidth=1.5,
            label='actual finish time')
    ax.plot(rows['year'], to_hours(rows['adjusted']), color=COLORS['M'], marker='o', markersize=6, linewidth=2,
            label='adjusted to an average year')
    ax.plot(rows['year'], to_hours(rows['expected']), color=COLORS['F'], linewidth=1.5,
            label='expected from ability, age and experience')
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda h, _: '{}:{:02d}'.format(*divmod(int(round(h * 60)), 60))))
    ax.invert_yaxis()
    ax.legend(frameon=False, fontsize=8)
    style(ax, '{}, {} {} (faster is up)'.format(rows['name'].iloc[-1], *label.split('_')), 'finish time', 'year')
    fig.tight_layout()
    path = 'graphs/{}_{}.png'.format(label, key)
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    print('saved', path)
    plt.close(fig)

    clock = lambda seconds: pd.to_datetime(seconds, unit='s').dt.strftime('%H:%M:%S')
    print(rows.assign(actual=clock(rows['time_s']), adjusted=clock(rows['adjusted_time_s']),
                      expected=clock(np.exp(rows['expected']) * 3600),
                      conditions=(100 * (np.exp(rows['condition_effect']) - 1)).round(1))[
        ['year', 'age_at_race', 'race_number', 'actual', 'conditions', 'adjusted', 'expected']].to_string(index=False))


if __name__ == '__main__':
    main()
