#the number of birkie finishers each year, from the scanned results (old_results/, 1973 on) to now (yearly_data/)
#every finisher in the results counts, split by technique where the results say it, with the open track on its own.
#finishers the scans lose are counted from the places either side and drawn as an outline on top
#
#example usage:
#python finishers.py      prints each year's counts and writes graphs/finishers_per_year.png
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


def main():
    counts = count_finishers(load_finishers())
    with pd.option_context('display.width', 200):
        print(counts.assign(total=counts.sum(axis=1)).to_string())
    plot(counts)


def load_finishers():
    #one row per finisher: year and tech (skate, classic, '' where the results don't say, or openTrack)
    old = []
    for path in sorted(glob.glob(os.path.join(OLD_DIR, '*', 'birkie *.csv'))):
        raw = pd.read_csv(path, dtype=str, keep_default_na=False)
        old.append(pd.DataFrame({'year': int(re.search(r'(\d{4})\.csv$', path).group(1)), 'tech': raw['tech'],
                                 'status': raw['status']}))
    new = load_all_results()
    new = new[new['race'] == 'birkie'].copy()
    new.loc[new['variant'] == 'openTrack', 'tech'] = 'openTrack'
    finishers = pd.concat(old + [new[['year', 'tech', 'status']]], ignore_index=True)
    return finishers[finishers['status'] == 'finished'].drop(columns='status')


def count_finishers(finishers):
    #a column for each series and a row for each year, with the finishers the scans lose as 'missing'
    counts = finishers.groupby(['year', 'tech']).size().unstack('tech', fill_value=0)
    counts = counts.reindex(columns=[key for key, _, _ in SERIES], fill_value=0)
    counts['missing'] = pd.Series(MISSING).reindex(counts.index, fill_value=0)
    return counts


def plot(counts):
    fig, ax = plt.subplots(figsize=(11, 5.5), facecolor=SURFACE)
    years = counts.index
    base = pd.Series(0, index=years)
    for key, label, color in SERIES:
        ax.bar(years, counts[key], bottom=base, width=0.8, color=color, edgecolor=SURFACE, linewidth=1, label=label)
        base = base + counts[key]
    lost = counts['missing'] > 0
    ax.bar(years[lost], counts.loc[lost, 'missing'], bottom=base[lost], width=0.8, facecolor='none',
           edgecolor=INK_2, linewidth=1, linestyle='--', label='lost from the scan (counted from the places)')

    #the first year, the most before 2000, the most in the race itself (2024's open track was most of a short race's
    #field), and the latest
    total = counts.drop(columns='missing').sum(axis=1)
    raced = total - counts['openTrack']
    for year in sorted({years.min(), total[years < 2000].idxmax(), raced.idxmax(), years.max()}):
        ax.annotate('{:,}'.format(total[year]), (year, total[year] + counts.loc[year, 'missing']), xytext=(0, 3),
                    textcoords='offset points', ha='center', va='bottom', fontsize=8, color=INK)
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


if __name__ == '__main__':
    main()
