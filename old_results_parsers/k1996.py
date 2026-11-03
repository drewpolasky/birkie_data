#1996 birch scroll: the kortelopet's full results are pages 54-64, "HERITAGE BANK OF HAYWARD KORTELOPET RESULTS",
#printed like the birkebeiner's (y1996.py) and read by the same code: alphabetical by last name, men and women together,
#two results to a line (page 64's right half is a photo), RANK (within the gender, or DNF, or DNS for a skier who didn't
#start), FINAL TIME, BIB, NAME, HOMETOWN, ST, NAT, CLASS ("M 45-49", a space after the letter), class rank and pace.
#its table has no 25% column, and its wider class runs to where the birkebeiner's class rank starts. the pace is the
#time over 25 km (min.sec per km, rounded down), up to 15 minutes a km. its classes are the birkebeiner's with the
#juniors' (13-14, 15-16, 17-18) and 19-24 in place of 18-24. pages 52 and 53 are the top 50 women and men, again in
#the full list
#
#example usage:
#python -m old_results_parsers.k1996 ocr          the pages' own OCR, kept in old_results/ocr/1996/
#python birkie_archive.py parse --years 1996      the results into old_results/1996/kortie 1996.csv
import sys

from old_results_parsers import y1996
from old_results_parsers.y1996 import YEAR

PAGES = range(54, 65)
NO_RESULTS = {64: (1,)}
#each field's left edge in pixels from the left of its line's nation code: the class's range ends at 122, where the
#birkebeiner's class rank starts, and the pace starts at 212 ('10.12'). there's no 25% column between them ('y' takes
#none of the line)
EDGES = {'time': -767, 'bib': -673, 'name': -603, 'town': -300, 'st': -80, 'nat': -22, 'cls': 45, 'crank': 128,
         'y': 190, 'pace': 190, 'end': 290}
AGES = ['13-14', '15-16', '17-18', '19-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64',
        '65-69', '70-74', '75-79', '80-84', '85-89']
KM = 25
PACE_MINUTES = (2, 19)
STRIPS = {**y1996.BIRKIE['STRIPS'],
          'rank': (-850, -767, '0123456789DNFS', (2, 3)),
          'cls': (45, 128, 'MF0123456789-', (2, 3)),
          'pace': (128, 275, '0123456789.', (2, 3))}
GLYPH_FIELDS = [('rank', -880, -768), ('time', -768, -676), ('bib', -676, -598), ('cls', 40, 128), ('crank', 128, 180),
                ('pace', 190, 300)]


def parse(year=YEAR):
    return y1996.parse(year, 'kortie')


def ocr(year=YEAR):
    y1996.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
