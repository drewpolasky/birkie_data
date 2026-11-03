#did skiers get faster once a snowmaking venue opened near home? snow_effect.py's panel (birkie skate and classic,
#2009-2026, the same skiers from one year to the next, with the snow at home in the model), and only skiers who never
#changed hometown, so a move can't stand in for the venue. each of their races is placed against the first birkie
#after a venue first opened within 25 km of their town, and the model gets a column for each race before and after
#it, measured against the last race before. the whole field's year is taken out by the race's conditions, so this is
#how much those skiers changed against everyone else. the twin cities and the other towns that had a venue all along,
#and the towns that never got one, only help measure the race conditions.
#
#then each venue that opened since 2009 on its own: its first birkie after opening and the ones after that, against
#the ones before, for the skiers within 25 km of it (in the twin cities most of them already had another venue)
#
#example usage:
#python snowmaking_openings.py      writes graphs/snowmaking_openings.png and linked_data/snowmaking_openings.csv
import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from performance_changes import load_linked, style, COLORS, INK, INK_2, GRID, SURFACE
from snow_depth import km_between
from snow_effect import snow_panel, snow_columns, fit_snow, estimate, snowmaking_venues, SNOWMAKING_KM

#races counted from the first birkie after a venue opened (0), the last one before is -1 and the reference. the
#first and last bins take in every race further out
EVENT_BINS = [(-99, -3, '3+ before'), (-2, -2, '2nd before'), (0, 0, 'first after'), (1, 1, '2nd after'),
              (2, 2, '3rd after'), (3, 99, '4th+ after')]
REFERENCE = 'last before'
MIN_SKIERS = 10                 #venues with fewer skiers nearby racing both before and after it opened are left out
#each venue's chart is cut here: the ranges for a venue whose skiers come from one or two towns (duluth, rochester)
#come from resampling just those towns, so they swing wildly and say little
VENUE_X = (-4, 4)
N_BOOTSTRAP = 200
N_VENUE_BOOTSTRAP = 100


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--linked", type=str, default='linked_data/linked_results.csv')
    parser.add_argument("--snow", type=str, default='snow_data', help='folder with snow_depth.py\'s output')
    args = parser.parse_args()

    towns = pd.read_csv(os.path.join(args.snow, 'hometowns.csv'))
    depth = pd.read_parquet(os.path.join(args.snow, 'hometown_snow_depth.parquet'))
    panel = snow_panel(load_linked(args.linked), towns, depth)
    venues = snowmaking_venues()
    held = np.array(sorted(panel['year'].unique()))
    stayed = panel.groupby('skier')['hometown_id'].transform('nunique') == 1

    pooled = event_study(panel, venues, held, stayed)
    each = venue_effects(panel, venues, held, stayed)
    print_summary(pooled, each)
    plot_openings(pooled, each)
    pd.concat([pooled.assign(venue='every town that gained one'), each]).to_csv(
        os.path.join(os.path.dirname(args.linked) or '.', 'snowmaking_openings.csv'), index=False)


def town_opened(panel, venues):
    #the first race year a venue was open within SNOWMAKING_KM of each result's hometown (inf if never)
    opened = np.full(len(panel), np.inf)
    for _, v in venues.iterrows():
        near = km_between(panel['lat'], panel['lng'], v['lat'], v['lng']).values <= SNOWMAKING_KM
        opened = np.where(near, np.minimum(opened, v['from_year']), opened)
    return opened


def races_since(years, opened, held):
    #how many birkies after the first one at or after the opening year: 0 for that one, -1 for the last before it.
    #counted in races held, since 2017 was cancelled and 2024 isn't in the model
    return np.searchsorted(held, years) - np.searchsorted(held, opened)


def skiers_both_sides(panel, rel):
    #skiers with a race before and after the opening, the ones the effect is measured from
    side = pd.DataFrame({'skier': panel['skier'], 'after': rel >= 0})[rel.notna()]
    return int((side.groupby('skier')['after'].nunique() == 2).sum())


def fit_columns(panel, columns, n_boot):
    #the year to year model with the snow at home and these columns, % faster for each with a 95% range from
    #resampling hometowns
    extra = snow_columns(panel, access=None)
    for name, column in columns.items():
        extra[name] = column.astype(float)
    fit, boot = fit_snow(panel, extra, n_boot)
    return {name: estimate(fit, boot, name) for name in columns}


def event_study(panel, venues, held, stayed):
    #every town where a venue first came within reach during the years raced here
    opened = town_opened(panel, venues)
    gained = stayed & (opened > held[0]) & (opened <= held[-1])
    rel = pd.Series(races_since(panel['year'].values, opened, held), index=panel.index).where(gained)
    effects = fit_columns(panel, {label: rel.between(lo, hi) for lo, hi, label in EVENT_BINS}, N_BOOTSTRAP)
    rows = [{'race': label, 'position': lo if lo > -99 else -3, 'pct_faster': est, 'lo': lo_ci, 'hi': hi_ci,
             'results': int(rel.between(lo, hi).sum())}
            for (lo, hi, label), (est, lo_ci, hi_ci) in zip(EVENT_BINS, effects.values())]
    rows.append({'race': REFERENCE, 'position': -1, 'pct_faster': 0.0, 'lo': 0.0, 'hi': 0.0,
                 'results': int((rel == -1).sum())})
    out = pd.DataFrame(rows).sort_values('position').reset_index(drop=True)
    out['skiers'] = skiers_both_sides(panel, rel)
    out['towns'] = panel.loc[gained, 'hometown_id'].nunique()
    return out


def venue_effects(panel, venues, held, stayed):
    #each venue that opened within the years raced here, for the skiers within reach of it who never moved
    rows = []
    others = town_opened(panel, venues)
    for i, v in venues[(venues['from_year'] > held[0]) & (venues['from_year'] <= held[-1])].iterrows():
        near = stayed & (km_between(panel['lat'], panel['lng'], v['lat'], v['lng']) <= SNOWMAKING_KM)
        rel = pd.Series(races_since(panel['year'].values, np.full(len(panel), v['from_year']), held),
                        index=panel.index).where(near)
        skiers = skiers_both_sides(panel, rel)
        if skiers < MIN_SKIERS:
            continue
        #how many of them already had a venue within reach: another one open before this one was
        before = town_opened(panel, venues.drop(index=i))
        already = (before[near.values] < v['from_year']).mean()
        effects = fit_columns(panel, {'first after': rel == 0, 'later': rel >= 1}, N_VENUE_BOOTSTRAP)
        first = held[np.searchsorted(held, v['from_year'])]
        for race, (est, lo, hi) in effects.items():
            rows.append({'venue': v['venue'], 'town': v['town'], 'first_race': first, 'race': race,
                         'pct_faster': est, 'lo': lo, 'hi': hi, 'skiers': skiers, 'already_had_one': already})
    return pd.DataFrame(rows)


#---------------------------------------------------------------- output

def print_summary(pooled, each):
    print('skiers who never moved, in the {} towns where a snowmaking venue first came within {} km since 2009: {} '
          'raced both before and after it opened'.format(pooled['towns'].iloc[0], SNOWMAKING_KM,
                                                          pooled['skiers'].iloc[0]))
    print('% faster than in the last birkie before it opened (95% range, resampling hometowns):')
    for _, r in pooled.iterrows():
        if r['race'] == REFERENCE:
            print('  {:12s} reference  ({} results)'.format(r['race'], r['results']))
            continue
        print('  {:12s} {:+.2f}% [{:+.2f}, {:+.2f}]  ({} results)'.format(r['race'], r['pct_faster'], r['lo'], r['hi'],
                                                                          r['results']))
    print('\neach venue that opened since 2009, % faster than in the birkies before it, for skiers within {} km who '
          'never moved:'.format(SNOWMAKING_KM))
    for (venue, town, first, skiers, already), g in each.groupby(
            ['venue', 'town', 'first_race', 'skiers', 'already_had_one'], sort=False):
        r = g.set_index('race')
        print('  {} ({}, first birkie after {}), {} skiers, {:.0%} already had one nearby: first after {:+.2f}% '
              '[{:+.2f}, {:+.2f}], later {:+.2f}% [{:+.2f}, {:+.2f}]'.format(
                  venue, town, first, skiers, already, *r.loc['first after', ['pct_faster', 'lo', 'hi']],
                  *r.loc['later', ['pct_faster', 'lo', 'hi']]))


def plot_openings(pooled, each):
    fig = plt.figure(figsize=(14, 6.5), facecolor=SURFACE)
    grid = fig.add_gridspec(1, 2, width_ratios=[1, 1.1], left=0.06, right=0.98, top=0.86, bottom=0.12, wspace=0.6)

    #every town that gained a venue, race by race
    ax = fig.add_subplot(grid[0, 0])
    ax.axhline(0, color=INK_2, linewidth=0.8)
    ax.axvline(-0.5, color=GRID, linewidth=1.2, linestyle='--')
    ax.vlines(pooled['position'], pooled['lo'], pooled['hi'], color=COLORS['M'], linewidth=1.5)
    ax.plot(pooled['position'], pooled['pct_faster'], 'o', color=COLORS['M'], markersize=8, markeredgecolor=SURFACE,
            markeredgewidth=1.5)
    for _, r in pooled.iterrows():
        if r['race'] != REFERENCE:
            ax.annotate('{:+.1f}%'.format(r['pct_faster']), (r['position'], r['hi']), xytext=(0, 4),
                        textcoords='offset points', ha='center', fontsize=8, color=INK)
    ax.annotate('venue opens', (-0.5, ax.get_ylim()[1]), xytext=(4, -12), textcoords='offset points', fontsize=8,
                color=INK_2)
    ax.set_xticks(pooled['position'])
    ax.set_xticklabels(pooled['race'].str.replace(' ', '\n', n=1), fontsize=8)
    style(ax, 'Towns that gained a snowmaking venue, race by race',
          '% faster than the last Birkie before it opened',
          '{} skiers who never moved, in {} towns, with Birkies before and after'.format(
              pooled['skiers'].iloc[0], pooled['towns'].iloc[0]))

    #each venue on its own
    ax = fig.add_subplot(grid[0, 1])
    venues = each.drop_duplicates('venue').reset_index(drop=True)
    y = -np.arange(len(venues))
    ax.axvline(0, color=INK_2, linewidth=0.8)
    for (race, label), color, shift in zip([('first after', 'first Birkie after it opened'),
                                            ('later', 'the Birkies after that')], [COLORS['M'], COLORS['F']],
                                           [0.12, -0.12]):
        r = each[each['race'] == race].set_index('venue').loc[venues['venue']]
        ax.hlines(y + shift, r['lo'].clip(*VENUE_X), r['hi'].clip(*VENUE_X), color=color, linewidth=1.5)
        ax.plot(r['pct_faster'], y + shift, 'o', color=color, markersize=7, markeredgecolor=SURFACE,
                markeredgewidth=1.5, label=label)
        #ranges running off the chart, with their numbers
        for yi, (_, v) in zip(y + shift, r.iterrows()):
            if v['lo'] < VENUE_X[0] or v['hi'] > VENUE_X[1]:
                for edge, off, marker in [(VENUE_X[0], v['lo'] < VENUE_X[0], '<'),
                                          (VENUE_X[1], v['hi'] > VENUE_X[1], '>')]:
                    if off:
                        ax.plot(edge, yi, marker, color=color, markersize=5)
                ax.annotate('{:.1f} to {:.1f}'.format(v['lo'], v['hi']), (VENUE_X[1], yi), xytext=(-8, 3),
                            textcoords='offset points', ha='right', va='bottom', fontsize=7, color=INK_2)
    ax.set_xlim(VENUE_X[0] - 0.2, VENUE_X[1] + 0.2)
    ax.set_yticks(y)
    ax.set_yticklabels(['{} ({})\n{}, {} skiers{}'.format(
        v['venue'].split(' (')[0], v['first_race'], v['town'], v['skiers'],
        ', {:.0%} had one already'.format(v['already_had_one']) if v['already_had_one'] >= 0.5 else '')
        for _, v in venues.iterrows()], fontsize=8)
    ax.legend(frameon=False, fontsize=8, loc='upper right')
    ax.grid(False, axis='y')
    style(ax, 'Each venue that opened since 2009, by its first Birkie after', '',
          '% faster than in the Birkies before it opened (95% range)')

    fig.suptitle('Snowmaking near home and Birkie times: skiers who never moved, against the rest of the field',
                 x=0.01, ha='left', fontsize=13, color=INK)
    path = 'graphs/snowmaking_openings.png'
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    print('\nsaved', path)
    plt.close(fig)


if __name__ == '__main__':
    main()
