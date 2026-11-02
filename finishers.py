#the number of birkie and kortelopet finishers each year, from the scanned results (old_results/, the birkie's from
#1973 and the kortelopet's from 1976) to now (yearly_data/), and of the prince haakon, whose results start in 2010
#every finisher in the results counts, split by technique where the results say it, with the open track on its own.
#finishers the scans lose are counted from the places either side and drawn as an outline on top
#
#example usage:
#python finishers.py      prints each year's counts and writes graphs/finishers_per_year.png and
#                         graphs/finishers_kortie_haakon.png
import glob
import os
import re

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd

from performance_changes import style, INK, INK_2, SURFACE
from results_loader import load_all_results

OLD_DIR = 'old_results'
GRAPH = 'graphs/finishers_per_year.png'
#finishers the scans lose, by the places and class ranks either side (see the README): lines lost where 1978's table
#crosses pages, 1979's slowest 260 or so (of about 2,545, its last page only a strip of times), 1982's missing page,
#1984's cut off page feet, 1985's unreadable first page and 1989's missing one (and two lines cut off)
MISSING = {1978: 23, 1979: 260, 1982: 233, 1984: 83, 1985: 100, 1989: 242}
#years with no bar, and races whose field was set by something other than the usual race
NO_RESULTS = {2000: 'cancelled', 2007: 'cut to 25 km, not in the data', 2017: 'cancelled'}
NOTES = {2021: 'other course, over five days', 2024: 'short course'}
#bottom to top
SERIES = [('', 'technique not recorded', '#bdbcb7'), ('skate', 'skate', '#2a78d6'), ('classic', 'classic', '#eb6834'),
          ('openTrack', 'open track', '#1baf7a')]
#the shorter races, a panel each. 2000's and 2017's were cancelled with the birkie, and 2007's kortelopet was an untimed
#tour
SHORT_GRAPH = 'graphs/finishers_kortie_haakon.png'
SHORT_RACES = {'kortie': 'Kortelopet', 'haakon': 'Prince Haakon'}
SHORT_NO_RESULTS = {1983: 'not read', 2000: 'cancelled', 2007: 'untimed tour', 2017: 'cancelled'}
SHORT_NOTES = {2021: 'over five days'}
#the kortelopet finishers the scans lose: 1978's four lines under a black band; 1980's all but the first two pages, the
#men's classes to the 69th novice man (996 finishers by the 1982 birch scroll's statistics); and 1984's women's places
#1-135 (a page missing from the scan), 730-773 (a page not read) and 31 lines cut off the pages' feet
KORTIE_MISSING = {1978: 4, 1980: 996 - 294, 1984: 210}


def main():
    results = load_all_results()
    counts = count_finishers(load_finishers(results))
    short = {race: count_finishers(load_finishers(results, race), KORTIE_MISSING if race == 'kortie' else {})
             for race in SHORT_RACES}
    with pd.option_context('display.width', 200):
        for race, c in {'birkie': counts, **short}.items():
            print('\n' + race)
            print(c.loc[:, (c != 0).any()].assign(total=c.sum(axis=1)).to_string())
    plot(counts)
    plot_short_races(short)


def load_finishers(results, race='birkie'):
    #one row per finisher: year and tech (skate, classic, '' where the results don't say, or openTrack)
    old = []
    for path in sorted(glob.glob(os.path.join(OLD_DIR, '*', '{} *.csv'.format(race)))):
        raw = pd.read_csv(path, dtype=str, keep_default_na=False)
        old.append(pd.DataFrame({'year': int(re.search(r'(\d{4})\.csv$', path).group(1)), 'tech': raw['tech'],
                                 'status': raw['status']}))
    new = results[results['race'] == race].copy()
    new.loc[new['variant'] == 'openTrack', 'tech'] = 'openTrack'
    finishers = pd.concat(old + [new[['year', 'tech', 'status']]], ignore_index=True)
    return finishers[finishers['status'] == 'finished'].drop(columns='status')


def count_finishers(finishers, missing=MISSING):
    #a column for each series and a row for each year, with the finishers the scans lose as 'missing'
    counts = finishers.groupby(['year', 'tech']).size().unstack('tech', fill_value=0)
    counts = counts.reindex(columns=[key for key, _, _ in SERIES], fill_value=0)
    counts['missing'] = pd.Series(missing, dtype=float).reindex(counts.index, fill_value=0).astype(int)
    return counts


def stacked_bars(ax, counts):
    #a bar a year, stacked by the series the race has, with the finishers the scans lose outlined on top. returns the
    #finishers in the results each year
    years = counts.index
    base = pd.Series(0, index=years)
    for key, label, color in SERIES:
        if counts[key].any():
            ax.bar(years, counts[key], bottom=base, width=0.8, color=color, edgecolor=SURFACE, linewidth=1,
                   label=label)
            base = base + counts[key]
    lost = counts['missing'] > 0
    if lost.any():
        ax.bar(years[lost], counts.loc[lost, 'missing'], bottom=base[lost], width=0.8, facecolor='none',
               edgecolor=INK_2, linewidth=1, linestyle='--', label='lost from the scan (counted from the places)')
    return base


def label_totals(ax, counts, total, years):
    for year in sorted(years):
        ax.annotate('{:,}'.format(total[year]), (year, total[year] + counts.loc[year, 'missing']), xytext=(0, 3),
                    textcoords='offset points', ha='center', va='bottom', fontsize=8, color=INK)


def plot(counts):
    fig, ax = plt.subplots(figsize=(11, 5.5), facecolor=SURFACE)
    years = counts.index
    total = stacked_bars(ax, counts)

    #the first year, the most before 2000, the most in the race itself (2024's open track was most of a short race's
    #field), and the latest
    raced = total - counts['openTrack']
    label_totals(ax, counts, total, {years.min(), total[years < 2000].idxmax(), raced.idxmax(), years.max()})
    for year, note in NO_RESULTS.items():
        ax.text(year, 80, note, rotation=90, ha='center', va='bottom', fontsize=7, color=INK_2)
    for year, note in NOTES.items():
        ax.text(year, total[year] + 80, note, rotation=90, ha='center', va='bottom', fontsize=7, color=INK_2)

    ax.set_xlim(years.min() - 1.5, years.max() + 1.5)
    ax.set_ylim(0, 7000)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(5))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(1000))
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda n, _: '{:,.0f}'.format(n)))
    style(ax, 'Birkie finishers each year, {}-{}'.format(years.min(), years.max()), 'finishers')
    ax.grid(False, axis='x')
    ax.set_title(ax.get_title('left'), loc='left', fontsize=11, color=INK, pad=24)
    ax.legend(loc='lower left', bbox_to_anchor=(0, 1.0), ncol=5, fontsize=8, frameon=False, labelcolor=INK)
    fig.text(0.01, 0.015, 'Every finisher in the results, the elite waves included; DNF and DSQ left out. Before 2008 '
             'classic skiers raced with the skaters, and most years before 2002 (from scanned results) don\'t say who '
             'skied classic.\nThe dashed outlines are finishers on pages the scans lose or can\'t be read, counted from '
             'the places either side (1979\'s about 260). 1981\'s elite race, the day before, isn\'t counted.',
             fontsize=7, color=INK_2, va='bottom')
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(GRAPH, dpi=130, facecolor=SURFACE)
    print('\nsaved', GRAPH)
    plt.close(fig)


def plot_short_races(short):
    #a panel for each race on the same years, each on its own scale
    first = min(c.index.min() for c in short.values())
    last = max(c.index.max() for c in short.values())
    fig, axes = plt.subplots(len(short), 1, figsize=(11, 7.5), sharex=True, facecolor=SURFACE)
    for ax, (race, counts) in zip(axes, short.items()):
        total = stacked_bars(ax, counts)
        top = total.max() * 1.3
        ax.set_ylim(0, top)
        #the first year, the most, and the latest
        label_totals(ax, counts, total, {counts.index.min(), total.idxmax(), counts.index.max()})
        for year in range(counts.index.min(), last + 1):
            if year not in counts.index:
                ax.text(year, 0.02 * top, SHORT_NO_RESULTS.get(year, 'no results'), rotation=90, ha='center',
                        va='bottom', fontsize=7, color=INK_2)
        if counts.index.min() > first + 5:
            ax.text((first + counts.index.min()) / 2, 0.5 * top, 'no results found before {}'.format(
                counts.index.min()), ha='center', va='center', fontsize=8, color=INK_2)
        for year, note in SHORT_NOTES.items():
            ax.text(year, total[year] + 0.03 * top, note, rotation=90, ha='center', va='bottom', fontsize=7,
                    color=INK_2)
        ax.yaxis.set_major_locator(ticker.MaxNLocator(4, integer=True))
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda n, _: '{:,.0f}'.format(n)))
        style(ax, SHORT_RACES[race], 'finishers')
        ax.grid(False, axis='x')
    axes[-1].set_xlim(first - 1, last + 1)
    axes[-1].xaxis.set_major_locator(ticker.MultipleLocator(5))
    axes[-1].tick_params(axis='x', labelbottom=True)
    fig.suptitle('Kortelopet and Prince Haakon finishers each year, {}-{}'.format(first, last), x=0.01, ha='left',
                 fontsize=13, color=INK)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper left', bbox_to_anchor=(0.01, 0.955), ncol=len(labels), fontsize=8,
               frameon=False, labelcolor=INK)
    fig.text(0.01, 0.015, 'Every finisher in the results, the elite waves included; DNF and DSQ left out. Each panel '
             'has its own scale. Before 2008 classic skiers raced the Kortelopet with the skaters,\nand most years '
             'before 2002 (from scanned results) don\'t say who skied classic. The dashed outlines are finishers the scans '
             'lose (most of 1980\'s list; 1984\'s missing pages and cut-off lines).\nThe Prince Haakon is freestyle (skate) '
             'but for 2021\'s two classic days.', fontsize=7, color=INK_2, va='bottom')
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    fig.savefig(SHORT_GRAPH, dpi=130, facecolor=SURFACE)
    print('saved', SHORT_GRAPH)
    plt.close(fig)


if __name__ == '__main__':
    main()
