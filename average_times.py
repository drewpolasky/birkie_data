#the average birkie finish time each year, from the scanned results (old_results/, 1973 on) to now (yearly_data/)
#every finisher counts, for skate and classic on their own and for the whole field. until 2006 classic skiers raced the
#skate course with the skaters, and most years before 2002 don't say who skied classic, so those years only have the
#whole field. the open track is left out
#
#example usage:
#python average_times.py      prints each year's averages and writes graphs/average_finish_time.png
import glob
import os
import re

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd

from performance_changes import style, INK, INK_2, SURFACE
from results_loader import load_all_results, parse_time

OLD_DIR = 'old_results'
GRAPH = 'graphs/average_finish_time.png'
#races on another course, shown but not joined to the years around them: the first races, of 48, 50 and 53 km by the
#champions list (1975's and 1977's were 55)
OTHER_COURSE = {1973: '48 km', 1974: '50 km', 1976: '53 km', 1991: 'alternate start, 46 km', 2002: 'cut to 46.7 km',
                2021: 'other course'}
#races too short to share the axis, years with no results, 1985 and 1989, whose fastest 100 and 240 men aren't read (a
#page set too irregularly to read, and one missing from the scan), and 1979, whose slowest 260 or so aren't (blank on
#the scan)
NOT_SHOWN = {1979: 'slowest missing', 1985: 'fastest men missing', 1989: 'fastest men missing', 1998: 'cut to 23 km',
             2000: 'cancelled', 2007: 'cut to 25 km', 2017: 'cancelled', 2024: 'short course'}
#the year the race turned for good to run from cable to hayward
REVERSED = 1993
SERIES = [('all', 'skate and classic together', INK_2), ('skate', 'skate', '#2a78d6'), ('classic', 'classic', '#eb6834')]


def main():
    times = load_times()
    means = average_times(times)
    with pd.option_context('display.width', 200):
        print(means.map(h_mm).assign(finishers=times.groupby('year').size()).to_string())
    plot(means)


def load_times():
    #one row per finisher: year, tech (skate, classic, or '' where the results don't say) and time in seconds
    old = []
    for path in sorted(glob.glob(os.path.join(OLD_DIR, '*', 'birkie *.csv'))):
        raw = pd.read_csv(path, dtype=str, keep_default_na=False)
        old.append(pd.DataFrame({'year': int(re.search(r'(\d{4})\.csv$', path).group(1)), 'tech': raw['tech'],
                                 'time_s': raw['time'].map(parse_time), 'status': raw['status']}))
    new = load_all_results()
    new = new[(new['race'] == 'birkie') & (new['variant'] != 'openTrack')]
    times = pd.concat(old + [new[['year', 'tech', 'time_s', 'status']]], ignore_index=True)
    return times[(times['status'] == 'finished') & times['time_s'].notna()].drop(columns='status')


def average_times(times):
    #mean finish time in seconds, a column for each series and a row for each year
    means = pd.DataFrame({'all': times.groupby('year')['time_s'].mean()})
    for tech in ['skate', 'classic']:
        means[tech] = times[times['tech'] == tech].groupby('year')['time_s'].mean()
    return means.drop(index=[y for y in NOT_SHOWN if y in means.index])


def h_mm(seconds):
    if np.isnan(seconds):
        return ''
    minutes = int(round(seconds / 60))
    return '{}:{:02d}'.format(minutes // 60, minutes % 60)


def runs(years):
    #consecutive years, so a line breaks over a missing year
    out = []
    for y in years:
        if out and y == out[-1][-1] + 1:
            out[-1].append(y)
        else:
            out.append([y])
    return out


def plot(means):
    fig, ax = plt.subplots(figsize=(11, 5.5), facecolor=SURFACE)
    for key, label, color in SERIES:
        s = means[key].dropna() / 3600
        usual = s[~s.index.isin(list(OTHER_COURSE))]
        for run in runs(list(usual.index)):
            ax.plot(run, usual[run], color=color, linewidth=2, marker='o', markersize=5, markeredgecolor=SURFACE,
                    markeredgewidth=1, label=label if run[0] == usual.index[0] else None)
        other = s[s.index.isin(list(OTHER_COURSE))]
        ax.plot(other.index, other, linestyle='none', marker='o', markersize=6, markerfacecolor=SURFACE,
                markeredgecolor=color, markeredgewidth=1.5)
        ax.annotate(label, (s.index[-1], s.iloc[-1]), xytext=(8, 0), textcoords='offset points', va='center',
                    fontsize=8, color=INK)
    ax.plot([], [], linestyle='none', marker='o', markersize=6, markerfacecolor=SURFACE, markeredgecolor=INK_2,
            markeredgewidth=1.5, label='course cut short or changed')

    bottom, top = 2.75, 6.1
    for year, note in sorted({**OTHER_COURSE, **NOT_SHOWN}.items()):
        ax.text(year, bottom + 0.05, note, rotation=90, ha='center', va='bottom', fontsize=7, color=INK_2)
    ax.axvline(REVERSED - 0.5, color=INK_2, linewidth=1, linestyle='--', zorder=1)
    ax.text(REVERSED - 0.3, top - 0.04, 'Cable to Hayward from {}'.format(REVERSED), ha='left', va='top', fontsize=7,
            color=INK_2)
    ax.set_ylim(bottom, top)
    ax.set_xlim(means.index.min() - 1.5, 2029.5)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(5))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(0.5))
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda hours, _: h_mm(hours * 3600)))
    style(ax, 'Average Birkie finish time, {}-{}'.format(means.index.min(), means.index.max()),
          'mean finish time (h:mm)')
    ax.set_title(ax.get_title('left'), loc='left', fontsize=11, color=INK, pad=24)
    ax.legend(loc='lower left', bbox_to_anchor=(0, 1.0), ncol=4, fontsize=8, frameon=False, labelcolor=INK)
    fig.text(0.01, 0.015, 'Every finisher, open track left out. Until 2006 classic skiers raced the skate course with '
             'the skaters; most years before 2002 (from scanned results) don\'t say who skied classic. Years cut much '
             'shorter aren\'t shown,\nnor are 1985 and 1989, whose fastest 100 and 240 men aren\'t read, or 1979, '
             'whose slowest 260 or so aren\'t, and 2007 (cut to 25 km) isn\'t in the data.\nClassic has had its own '
             'course since 2008. The old results\' pace columns put the course at 52.5 to 55 km in 1988-1990 and 52 km '
             'in 1992-1997.\nThe first races ran from Hayward to Telemark; in 1973 and 1974 the women raced the shorter '
             'race (1974\'s champion raced with the men).', fontsize=7, color=INK_2, va='bottom')
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    fig.savefig(GRAPH, dpi=130, facecolor=SURFACE)
    print('\nsaved', GRAPH)
    plt.close(fig)


if __name__ == '__main__':
    main()
