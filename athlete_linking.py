#link results from year to year, so each skier gets one athlete_id across every race they've done
#
#the results have no athlete ids, so this is record linkage on name, birth year, gender and hometown:
#   - results are only compared when the last names match and the first names are the same or a nickname
#     ("Drew"/"Andrew", "Bob"/"Robert", "Chris"/"Christopher")
#   - each pair of results gets a score, the log odds that they're the same person. it starts from how common the
#     name is (counted by people, not results), then adds evidence from birth year (exact age 2021+, age group
#     2016-2020), middle initial (mostly 2009-2014) and hometown, where a move counts for less the younger the skier
#     and the more years in between
#   - pairs are merged best first, never merging two groups of results that contradict each other
#     (two results in the same race or on the same day, different genders, incompatible birth years, Jr/Sr, different
#     middle initials)
#finish times are deliberately not used, so the links can't bias a year to year performance analysis
#
#example usage:
#python athlete_linking.py                      link everything, write linked_data/
#python athlete_linking.py --name "drew polasky"  print one skier's history
import argparse
import bisect
import functools
import itertools
import math
import os
import re
from collections import Counter, defaultdict, namedtuple

import numpy as np
import pandas as pd

from results_loader import load_all_results, compact

MERGE_THRESHOLD = 2.0           #minimum log odds to link two results. 2.0 is ~88% sure
BIRTH_YEAR_SPREAD = 45          #roughly how many birth years the field is spread over, for how often strangers share one
FIRST_MULTI_RACE_YEAR = 2018    #before this the birkie and kortie were the same day, so one race per person per year.
                                #the pre-birkie's races are always on one day
FIRST_NAME_PENALTY = {0: 0.0, 1: -1.0, 2: -2.0}     #same first name, known nickname, looser variant
PARTIAL_LAST_NAME_PENALTY = -1.5                    #"Noble-Stuen" vs "Stuen"

#each line is one set of interchangeable first names. a name can be in several sets (chris)
NICKNAMES = '''
abigail abby abbie
abraham abram abe
alan allan allen al
albert al bert
alexander alex xander
alexandra alex alexa lexi
alfred al alf fred
amanda mandy
andrew andy drew
angela angie
anthony tony
augustus august augustin gus
barbara barb
benjamin ben benji benny
bennett ben
bradley brad
brian bryan
cameron cam
catherine katherine kathryn katharine kathleen kate katie katy kati kathy cathy kat kay
charles charlie chuck chas
christian chris
christina christine kristina kristine chris christy kris tina
christopher chris kristopher kris topher
cynthia cindy
daniel dan danny
danielle dani danni
david dave davey
deborah debra deb debbie
dennis denny
dominic dominick dom
donald don donnie
douglas doug
edward ed eddie ted ned
eleanor ellie nora
elizabeth liz lizzie beth betsy libby eliza betty
eric erik
ernest ernie
frederick fredrick frederic fred freddie fritz
gabriel gabe
gabrielle gabby gabi
geoffrey jeffrey jeffery geoff jeff
gerald gerry jerry
gregory greg
harold hal harry
henry hank harry
howard howie
jacob jakob jake
jacqueline jackie
james jim jimmy jamie jamey
jennifer jen jenn jenny jennie
jerome jerry
jessica jess jessie
john jack johnny jon
jonathan jon jonny
joseph joe joey jojo
joshua josh
judith judy
kenneth ken kenny
kimberly kim
kristen kristin kirsten
lawrence laurence larry
leonard len lenny
louis lou
madeleine madeline madelyn madison maddie maddy madi
margaret maggie meg peggy marge margie
matthew matt matty
maxwell maximilian max
melissa missy mel
michael mike mikey mick mickey
mitchell mitch
nathan nathaniel nate nat
nicholas nicolas nickolas nick nicky nic nik
nicole nikki nicki
oliver ollie
pamela pam
patricia pat patty trish tricia
patrick pat paddy
peter pete
philip phillip phil
randall randolph randy
raymond ray
rebecca becca becky
richard rich rick ricky richie dick
robert rob bob bobby robbie robby bert
ronald ron ronnie
russell russ
samantha sam sammi sammie
samuel sam sammy
sandra sandy
sara sarah
stanley stan
stephanie steph
stephen steven steve stevie
susan suzanne sue susie suzy
teresa theresa terri terry tess
theodore ted teddy theo
thomas tom tommy
timothy tim timmy
tobias toby
valerie val
victoria vicki vicky tori
vincent vince vinny
walter walt
wesley wes
william will bill billy willy willie liam
zachary zachariah zackary zach zack zac
'''

Rec = namedtuple('Rec', 'i year event day first last last_keys initial suffix gender gender_inferred birth city region')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", type=str, default='', help='print the linked history for this skier')
    parser.add_argument("--threshold", type=float, default=MERGE_THRESHOLD)
    parser.add_argument("--out", type=str, default='linked_data/')
    args = parser.parse_args()

    results = load_all_results()
    linked = link_athletes(results, threshold=args.threshold)
    athletes = summarize_athletes(linked)

    if args.name:
        print_history(linked, args.name)
        return

    os.makedirs(args.out, exist_ok=True)
    linked.to_csv(os.path.join(args.out, 'linked_results.csv'), index=False)
    athletes.to_csv(os.path.join(args.out, 'athletes.csv'), index=False)
    print_summary(linked, athletes)


#---------------------------------------------------------------- linking

def link_athletes(results, threshold=MERGE_THRESHOLD):
    #returns a copy of results with
    #   athlete_id:  the same for every result linked to one skier (ids are only stable for a given set of data)
    #   link_score:  log odds of the strongest pair tying this result to another of the athlete's results,
    #                NaN for an athlete with only one result
    #   name_shared: how many athletes have this exact name. above 1, some results may sit with the wrong one
    results = results.reset_index(drop=True)
    records = prepare_records(results)
    model = NameModel(records)

    #only results sharing a last name key get compared. a result can have a few keys, so "Andrea J Noble Stuen",
    #"Andrea Noble-Stuen" and "Andrea Stuen" all end up compared with each other
    blocks = defaultdict(list)
    for rec in records:
        if rec.first:
            for key in rec.last_keys:
                blocks[key].append(rec)

    scores = {}
    for key, block in blocks.items():
        for group in first_name_groups(block):
            for a, b in itertools.combinations(group, 2):
                score = pair_score(a, b, key, model)
                if score is not None and score >= threshold and score > scores.get((a.i, b.i), -math.inf):
                    scores[(a.i, b.i)] = score

    #merge the most certain pairs first, skipping any merge that would contradict something already linked
    parent = list(range(len(records)))
    clusters = {i: Cluster(rec) for i, rec in enumerate(records)}
    link_score = np.full(len(records), np.nan)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for (i, j), score in sorted(scores.items(), key=lambda item: -item[1]):
        ri, rj = find(i), find(j)
        if ri != rj:
            if not clusters[ri].compatible(clusters[rj]):
                continue
            parent[rj] = ri
            clusters[ri].absorb(clusters.pop(rj))
        link_score[i] = np.fmax(link_score[i], score)
        link_score[j] = np.fmax(link_score[j], score)

    roots = [find(i) for i in range(len(records))]
    #number athletes in order of their first appearance
    order = {}
    for root in roots:
        order.setdefault(root, len(order))
    linked = results.copy()
    linked['athlete_id'] = [order[root] for root in roots]
    linked['link_score'] = link_score.round(2)
    name_key = linked['first'].map(compact) + ' ' + linked['last'].map(compact)
    linked['name_shared'] = linked.groupby(name_key)['athlete_id'].transform('nunique')
    return linked


def prepare_records(results):
    #pull out just what linking needs, as plain tuples (much faster than pandas rows)
    first = results['first'].fillna('').map(compact)
    last = results['last'].fillna('').map(compact)
    middle = results['middle'].fillna('')
    #only a lone letter counts as a middle initial. longer middle names are often a maiden or second last name
    #("Colleen Flanagan Pritz"), which can be there one year and gone the next
    initial = middle.str.split().str[0].where(middle.str.split().str[0].str.len() == 1, '').fillna('')
    last_keys = [last_name_keys(l, m) for l, m in zip(results['last'].fillna(''), middle)]
    event = results['year'].astype(str) + ' ' + results['race'] + ' ' + results['tech'] + ' ' + results['variant']
    #races on one day, where a skier can only have one result: each pre-birkie, and the birkie weekend before
    #FIRST_MULTI_RACE_YEAR. empty when a skier could have more than one
    pre = results['race'].str.startswith('prebirkie')
    day = np.where(pre, results['year'].astype(str) + ' prebirkie',
                   np.where(results['year'] < FIRST_MULTI_RACE_YEAR, results['year'].astype(str) + ' birkie', ''))
    region = results['state'].where(results['state'] != '', results['country']).fillna('')
    gender = results['gender'].where(results['gender'].isin(['M', 'F']), '')
    #2008-2015 birkie weekend genders are inferred from places
    inferred = results['year'].between(2008, 2015) & ~pre

    #birth year range: exact from age (2021+), or from the age group (2016-2020)
    birth_lo = (results['year'] - results['age']).fillna(results['year'] - results['age_max'] - 1)
    birth_hi = (results['year'] - results['age']).fillna(results['year'] - results['age_min'])

    records = []
    for i in range(len(results)):
        birth = None if np.isnan(birth_lo[i]) else (int(birth_lo[i]), int(birth_hi[i]))
        records.append(Rec(i=i, year=int(results.at[i, 'year']), event=event[i], day=day[i], first=first[i],
                           last=last[i], last_keys=last_keys[i], initial=initial[i],
                           suffix=results.at[i, 'suffix'] or '', gender=gender[i], gender_inferred=inferred[i],
                           birth=birth, city=results.at[i, 'city'] or '', region=region[i]))
    return records


PARTICLES = {'van', 'von', 'vande', 'vanden', 'vander', 'der', 'den', 'de', 'la', 'le', 'du', 'st', 'mc', 'mac', 'di', 'da', 'del'}

def last_name_keys(last, middle):
    #the full last name, each part of a double or hyphenated one, and a middle name that might really be a
    #second last name: "Colleen Flanagan Pritz" -> pritz, flanaganpritz, flanagan
    keys = {compact(last)}
    parts = [p for p in re.split(r'[\s\-]+', last) if p]
    if len(parts) > 1:
        keys |= {compact(p) for p in parts if p not in PARTICLES}
    middle_words = middle.split()
    if middle_words and len(middle_words[-1]) > 1 and middle_words[-1] not in PARTICLES:
        keys.add(compact(middle_words[-1] + last))
        keys.add(compact(middle_words[-1]))
    return frozenset(k for k in keys if len(k) > 1)


class NameModel:
    #frequencies of names and places, for how surprising it is that two results share them
    def __init__(self, records):
        #names are counted by people (distinct names), not results, so a family of regulars racing every year
        #doesn't make their last name look common
        names = {(r.first, r.last) for r in records}
        self.n_people = len(names)
        self.first = Counter(first for first, last in names)
        self.last = Counter(key for key, first in {(key, r.first) for r in records for key in r.last_keys})
        #same for places: the share of people from each state and city
        self.region = Counter(region for name, region in {((r.first, r.last), r.region) for r in records if r.region})
        self.city = Counter(place for name, place in {((r.first, r.last), (r.city, r.region))
                                                      for r in records if r.city and r.region})
        #a name that shows up more than once on one race day belongs to at least that many people
        per_day = Counter((r.first, r.last, r.day) for r in records if r.day)
        self.min_people = defaultdict(lambda: 1)
        for (first, last, day), count in per_day.items():
            self.min_people[(first, last)] = max(self.min_people[(first, last)], count)

    def prior(self, a, b, last_key):
        #log odds that two results with this name are the same person, before any other evidence:
        #about -log(number of other people expected to share the name)
        n_first = max(self.first[a.first], self.first[b.first])
        others = n_first * self.last[last_key] / self.n_people
        others = max(others, self.min_people[(a.first, a.last)] - 1, self.min_people[(b.first, b.last)] - 1)
        return min(6.0, -math.log(max(others, 1e-6)))


def pair_score(a, b, last_key, model):
    #log odds that results a and b are the same skier, or None when they can't be
    if a.event == b.event:
        return None
    if a.day and a.day == b.day:
        return None
    if a.suffix and b.suffix and a.suffix != b.suffix:
        return None
    if a.initial and b.initial and a.initial != b.initial:
        return None
    relation = first_name_relation(a.first, b.first)
    if relation is None:
        return None
    score = model.prior(a, b, last_key) + FIRST_NAME_PENALTY[relation]
    if a.last != b.last:
        score += PARTIAL_LAST_NAME_PENALTY

    if a.gender and b.gender and a.gender != b.gender:
        if not (a.gender_inferred or b.gender_inferred):
            return None
        score -= 3.0            #2008-2015 gender is inferred from places, so allow for a mistake

    birth = birth_year_score(a.birth, b.birth)
    if birth is None:
        return None
    score += birth

    if a.initial and b.initial:
        score += 2.4            #same middle initial, which strangers share ~8% of the time

    score += location_score(a, b, model)
    return score


def birth_year_score(a, b):
    if a is None or b is None:
        return 0.0
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    exact = a[0] == a[1] and b[0] == b[1]
    if lo <= hi:
        width = (a[1] - a[0] + 1) + (b[1] - b[0] + 1) - 1
        return math.log(0.99 * BIRTH_YEAR_SPREAD / width)
    if lo - hi == 1:
        #off by one: ~1% of exact age pairs for the same person (birthday around race day), much rarer for age groups
        return -1.4 if exact else -3.0
    return None


def location_score(a, b, model):
    if not a.region or not b.region:
        return 0.0
    moved_state, moved_city = move_rates(a, b)
    f_region = model.region[a.region] / model.n_people
    if a.region != b.region:
        if len(a.city) >= 5 and a.city == b.city:
            return 0.0          #"maple grove MN" / "maple grove WI" is far more likely a typo than a move
        return math.log(moved_state / max(1 - f_region, 0.05))
    if not a.city or not b.city:
        return min(math.log((1 - moved_state) / f_region), 3.0)
    f_city = max(model.city[(a.city, a.region)], 1) / model.n_people
    if same_city(a.city, b.city):
        return min(math.log((1 - moved_city) / f_city), 4.5)
    return max(-3.0, min(3.0, math.log((moved_city - moved_state) / max(f_region - f_city, 0.002))))


#how often the same skier lists a different state (or country) / a different city when they race again, by their age
#at the earlier race and the years in between. measured on rare names with consistent ages, so the links aren't
#in doubt. young skiers move a lot more: 12% of 22-25 year olds are in a different state a year later, 2% of 40-55s
MOVE_GAP_BANDS = [1, 2, 4, 7, 11]       #upper ends of the gap bands, longer gaps use the last band
MOVE_RATES = {                          #age band start -> (different state, different city) for each gap band
    None: [(0.035, 0.10), (0.050, 0.15), (0.071, 0.21), (0.094, 0.28), (0.126, 0.36), (0.147, 0.42)],
    0:  [(0.030, 0.11), (0.051, 0.16), (0.103, 0.27), (0.200, 0.45), (0.326, 0.66), (0.389, 0.79)],
    22: [(0.123, 0.25), (0.184, 0.40), (0.266, 0.55), (0.340, 0.71), (0.412, 0.80), (0.413, 0.83)],
    26: [(0.086, 0.23), (0.134, 0.35), (0.182, 0.46), (0.239, 0.56), (0.266, 0.65), (0.266, 0.65)],
    30: [(0.045, 0.12), (0.061, 0.19), (0.077, 0.25), (0.093, 0.33), (0.111, 0.38), (0.111, 0.42)],
    40: [(0.018, 0.06), (0.022, 0.09), (0.032, 0.13), (0.039, 0.18), (0.055, 0.24), (0.072, 0.29)],
    55: [(0.021, 0.06), (0.028, 0.09), (0.041, 0.13), (0.056, 0.18), (0.074, 0.23), (0.102, 0.27)],
}

def move_rates(a, b):
    gap_band = bisect.bisect_left(MOVE_GAP_BANDS, abs(a.year - b.year))
    birth = a.birth or b.birth
    age_band = None
    if birth:
        age = min(a.year, b.year) - (birth[0] + birth[1]) / 2
        age_band = max([k for k in MOVE_RATES if k is not None and k <= age], default=0)
    return MOVE_RATES[age_band][gap_band]


class Cluster:
    #everything about a group of linked results that a new result has to be consistent with
    __slots__ = ('events', 'days', 'genders', 'birth_lo', 'birth_hi', 'firsts', 'initials', 'suffixes')

    def __init__(self, rec):
        self.events = {rec.event}
        self.days = {rec.day} if rec.day else set()
        self.genders = {rec.gender} if rec.gender and not rec.gender_inferred else set()
        self.birth_lo, self.birth_hi = rec.birth if rec.birth else (-math.inf, math.inf)
        self.firsts = {rec.first}
        self.initials = {rec.initial} if rec.initial else set()
        self.suffixes = {rec.suffix} if rec.suffix else set()

    def compatible(self, other):
        if self.events & other.events or self.days & other.days:
            return False
        if len(self.genders | other.genders) > 1:
            return False
        if len(self.initials | other.initials) > 1 or len(self.suffixes | other.suffixes) > 1:
            return False
        if max(self.birth_lo, other.birth_lo) - min(self.birth_hi, other.birth_hi) > 1:
            return False
        return all(first_name_relation(a, b) is not None for a in self.firsts for b in other.firsts)

    def absorb(self, other):
        self.events |= other.events
        self.days |= other.days
        self.genders |= other.genders
        self.birth_lo = max(self.birth_lo, other.birth_lo)
        self.birth_hi = min(self.birth_hi, other.birth_hi)
        self.firsts |= other.firsts
        self.initials |= other.initials
        self.suffixes |= other.suffixes


def first_name_groups(block):
    #split a last name block into groups whose first names could possibly match, so only those pairs get scored
    firsts = sorted({r.first for r in block})
    group_of = {f: f for f in firsts}

    def find(f):
        while group_of[f] != f:
            f = group_of[f]
        return f

    for a, b in itertools.combinations(firsts, 2):
        if first_name_relation(a, b) is not None:
            group_of[find(b)] = find(a)
    groups = defaultdict(list)
    for r in block:
        groups[find(r.first)].append(r)
    return [g for g in groups.values() if len(g) > 1]


def build_nickname_index():
    index = defaultdict(set)
    for i, line in enumerate(NICKNAMES.strip().splitlines()):
        for name in line.split():
            index[name].add(i)
    return index

NICKNAME_INDEX = build_nickname_index()


@functools.lru_cache(maxsize=None)
def first_name_relation(a, b):
    #0 same name, 1 known nickname, 2 looser variant (prefix like "max"/"maxwell", or a one letter spelling
    #difference like "kristin"/"kristen"), None for different names
    if a == b:
        return 0
    if NICKNAME_INDEX.get(a, set()) & NICKNAME_INDEX.get(b, set()):
        return 1
    short, long = sorted((a, b), key=len)
    if len(short) >= 3 and long.startswith(short):
        return 2
    if len(short) >= 4 and a[0] == b[0] and within_one_edit(a, b):
        return 2
    return None


def same_city(a, b):
    if a == b:
        return True
    short, long = sorted((a, b), key=len)
    #truncated names ("steamboat spr"), but not a different town that starts the same ("st paul" / "st paul park")
    if len(short) >= 5 and long.startswith(short) and long[len(short)] != ' ':
        return True
    return len(short) >= 6 and within_one_edit(a, b)


def within_one_edit(a, b):
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    short, long = sorted((a, b), key=len)
    for k in range(len(long)):
        if long[:k] + long[k+1:] == short:
            return True
    return False


#---------------------------------------------------------------- summaries

def summarize_athletes(linked):
    linked = linked.sort_values('year').assign(birth_year=linked['year'] - linked['age'],
                                               event=linked['race'] + ' ' + linked['tech'])
    g = linked.groupby('athlete_id')
    athletes = pd.DataFrame({
        'name': g['name'].last(),
        'gender': g['gender'].last(),
        'birth_year': g['birth_year'].median(),
        'city': g['city'].last(),
        'state': g['state'].last(),
        'n_results': g.size(),
        'n_years': g['year'].nunique(),
        'first_year': g['year'].min(),
        'last_year': g['year'].max(),
        'events': linked.drop_duplicates(['athlete_id', 'event']).groupby('athlete_id')['event'].agg(', '.join),
        'weakest_link': g['link_score'].min(),
        'name_shared': g['name_shared'].max(),
    })
    return athletes.reset_index()


def print_summary(linked, athletes):
    print('{} results linked into {} athletes'.format(len(linked), len(athletes)))
    years = athletes['n_years']
    print('athletes with results in 1 year: {}, 2-4 years: {}, 5-9 years: {}, 10+ years: {}'.format(
        (years == 1).sum(), years.between(2, 4).sum(), years.between(5, 9).sum(), (years >= 10).sum()))
    repeat = linked['athlete_id'].map(linked.groupby('athlete_id')['year'].nunique()) > 1
    print('results belonging to someone who raced in more than one year: {:.1%}'.format(repeat.mean()))
    print('athletes whose exact name is shared with another athlete: {}'.format((athletes['name_shared'] > 1).sum()))
    print('most years raced:')
    print(athletes.sort_values(['n_years', 'n_results'], ascending=False).head(10)[
        ['name', 'city', 'state', 'n_results', 'n_years', 'first_year', 'last_year']].to_string(index=False))


def print_history(linked, name):
    key = compact(name)
    full_key = (linked['first'].map(compact) + linked['last'].map(compact))
    ids = linked.loc[full_key == key, 'athlete_id'].unique()
    if len(ids) == 0:
        #try nickname variants of the first name, e.g. drew -> andrew
        last = name.split()[-1]
        first = compact(' '.join(name.split()[:-1]))
        same_last = linked[linked['last'].map(compact) == compact(last)]
        ids = same_last.loc[same_last['first'].map(compact).map(lambda f: first_name_relation(f, first) is not None),
                            'athlete_id'].unique()
    if len(ids) == 0:
        print('no results found for', name)
    for athlete_id in ids:
        rows = linked[linked['athlete_id'] == athlete_id].sort_values('year')
        print('\nathlete {}: {} results'.format(athlete_id, len(rows)))
        times = pd.to_datetime(rows['time_s'], unit='s').dt.strftime('%H:%M:%S').fillna(rows['status'])
        out = rows.assign(time=times)[['year', 'race', 'tech', 'variant', 'name', 'gender', 'age', 'city', 'state',
                                       'overall_place', 'time', 'link_score']]
        print(out.to_string(index=False))


if __name__ == '__main__':
    main()
