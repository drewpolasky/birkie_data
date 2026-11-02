#1998: "MEN'S JOHNSON BANK KORTELOPET RESULTS" on pages 44-46 and the top table of page 47, "WOMEN'S ..." in the bottom
#table of page 47 (its columns some 25 pixels right of the men's above) and on pages 48-50 (page 50's table stops at an
#ad), by Burns Computer Services in the birkebeiner's halftone-shaded table (y1998.py) and read by the same code: RK,
#CL ("Y" for a classic skier), BIB, NAME, HOMETOWN, CO, AGE, DIV. ("M19-24"), DIV PL, DIV. TOTAL, FINISH TIME (m:ss
#under an hour, from the winners' 55:15) and PACE. the kortelopet was cut short to the birkebeiner's 23 km that year:
#its pace is the time over 23 km too, rounded up, and runs to mm:ss from 10 minutes a km. its classes are the
#birkebeiner's with the juniors' (13-14, 15-16, 17-18) and 19-24 in place of 18-24
#
#example usage:
#python -m old_results_parsers.k1998 ocr          clean, straighten and OCR the pages (kept in old_results/ocr/1998/)
#python birkie_archive.py parse --years 1998      the results into old_results/1998/kortie 1998.csv
import sys

from old_results_parsers import y1998
from old_results_parsers.y1998 import YEAR

MEN_PAGES = [44, 45, 46, (47, 1)]
WOMEN_PAGES = [(47, 2), 48, 49, 50]
#page 47's two tables: the men's headings near the top, the women's some two thirds of the way down
TABLES = {47: [y1998.HEADINGS_ROWS, (2200, 2500)]}
YOUNG_CLASSES = [(13, 14), (15, 16), (17, 18), (19, 24)]
FIVE_YEAR_FROM = 25
LONG_PACES = True


def parse(year=YEAR):
    return y1998.parse(year, 'kortie')


def ocr(year=YEAR):
    y1998.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
