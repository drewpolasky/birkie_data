#1993 birch scroll: the kortelopet results are pages 50-54 (men, places 1-979; page 54's right half is photos) and 55-58
#(women, 1-677; page 58's left half stops after 17 rows, at photos), under titles that say KORTELOPET, set in the
#birkebeiner's typeface and read the same way, by y1993.py. its table has no 25% column and its bibs have five digits
#(flush right where the birkebeiner's end): its columns from the name on sit 4 to 25 pixels right of the birkebeiner's,
#the pace where the birkebeiner's is, with room for a pace of ten minutes or more. its classes are the birkebeiner's
#with the juniors' (13-14, 15-16, 17-18), 19-24 in place of 18-24. the PACE column is the time over 26 km (the champions
#list gives the race as 29 km)
import sys

from old_results_parsers import y1993
from old_results_parsers.y1993 import YEAR

TITLE = ('KORTE', 'BIRKEBEINER')
#below its 17 rows (to row 790 of the scan) page 58 is photos
TABLE_ENDS = {58: 860}
#where each column starts, in page pixels from the left edge of the FINAL TIME column, as measured on the levelled
#OCR: the name's heading at 172, the hometowns from 479, the states from 704, the nations from 751, the classes from
#821, the class ranks ending by 949 and the paces from 971
COLUMNS = [('rank', -1e9), ('time', -12), ('bib', 85), ('name', 159), ('city', 470), ('state', 699), ('country', 749),
           ('class', 813), ('class_rank', 897), ('pace', 958), ('beyond', 1045)]
TEXT_FROM, TEXT_TO = 159, 699
BIB_RIGHT = 133
#the states from 704 (a hometown ends by 691) to 746, the nations ending by 802 (a class starts at 821)
STATE_COLUMN, NATION_COLUMN = (697, 752), (745, 815)
#min.sec, or for the slowest (from about 4:20) mm.ss
PACE_DIGITS = (3, 4)
GROUPS = ['13-14', '15-16', '17-18', '19-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64',
          '65-69', '70+']
KM = 26.0


def parse(year=YEAR):
    return y1993.parse(year, 'kortie')


def ocr(year=YEAR):
    y1993.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
