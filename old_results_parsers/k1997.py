#1997 birch scroll: "MEN'S HERITAGE BANK OF HAYWARD KORTELOPET RESULTS" on pages 56-60 and the top table of page 61,
#"WOMEN'S ..." in the bottom table of page 61 and on pages 62-65, printed in the birkebeiner's table (y1997.py) and read
#by the same code: two columns of RANK, C for a classic skier (the key at the foot of page 61), FINAL TIME, BIB (five
#digits), NAME, HOMETOWN, ST, NAT, CLASS ("M 19-24"), CL RANK and PACE TIME. there's no 25% column: the class and class
#rank sit about 47 pixels further right than the birkebeiner's, and the pace is the time over 25 km, right aligned, as
#m.ss or, from 10 minutes a km, mm.ss. its classes are the birkebeiner's with the juniors' (13-14, 15-16, 17-18) and
#19-24 in place of 18-24
#
#example usage:
#python -m old_results_parsers.k1997 ocr          the strips' OCR (kept in old_results/ocr/1997/)
#python birkie_archive.py parse --years 1997      the results into old_results/1997/kortie 1997.csv
import sys

from old_results_parsers import y1997
from old_results_parsers.y1997 import YEAR

LISTS = {'M': [56, 57, 58, 59, 60, 61], 'F': [(61, '2'), 62, 63, 64, 65]}
#page 61's two tables: the men's heading rule is near the top, the women's about two thirds of the way down
TABLES = {61: [y1997.HEADING_RULE, (2050, 2400)]}
#page 56's right hand half was pasted up out of line: against its time column's lines (the half turned 2 degrees, a
#degree more than the page), the ST and NAT columns sit about 5 rows high and the class, class rank and pace 13
OUT_OF_LINE = {(56, 'R'): [(636, 5), (780, 8)]}
#in pixels from the left of the FINAL TIME column
STRIPS = {**y1997.BIRKIE['STRIPS'], 'class': (799, 880), 'crank': (878, 940), 'pace': (940, 1004)}
CLASS_LEFT = 807
CRANK = (880, 940)
CLASS_SPAN = (787, 947)
LEFT_ALIGNED = (0, 164, 706, 807)
PACE_RIGHT = 993
DISTANCE_KM = 25
CLASSES = ['13-14', '15-16', '17-18', '19-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64',
           '65-69', '70-74', '75-79', '80-84']


def parse(year=YEAR):
    return y1997.parse(year, 'kortie')


def ocr(year=YEAR):
    y1997.ocr(year, race='kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
