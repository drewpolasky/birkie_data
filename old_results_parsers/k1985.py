#1985 birch scroll: the kortelopet results are pages 30-34 (men, from below the women's birkebeiner in page 30's second
#block to partway down page 34's first) and 34-36 (women, from below the men's; page 36's second block stops at a
#mailing form), printed on the birkebeiner's printer (y1985.py) and read the same way
import sys

from old_results_parsers import line_printer
from old_results_parsers.line_printer import Printer, DIGITS, LETTERS
from old_results_parsers.y1985 import YEAR, TURN, PRINTER, SURNAME_FIRST

PAGES = {30: ('M', 'M'), **{p: 'M' for p in range(31, 34)}, 34: ('MF', 'F'), 35: 'F', 36: 'F'}
ANGLE = {30: -0.87, 31: 0.2, 32: -0.64, 33: 0.17, 34: -0.15, 35: 0.98, 36: -0.79}
#the left edge of the first page's first block, level: the table sits about three columns right of the
#birkebeiner's in its frame
FIRST_BLOCK = 160
#the birkebeiner's printer, but its table has no CTZ or 25% columns: the time is three columns right of the
#birkebeiner's (in 88-96), the class code in 101-102 and its rank ending in 109. its dots are fainter still, so a line
#anchors with two fewer of the sex and time columns as they should be
PRINTER = Printer(**{**vars(PRINTER),
                     'fields': {'rank': (0, 5), 'sex': (5, 8), 'bib': (8, 14), 'name': (14, 45), 'town': (45, 66),
                                'st': (66, 69), 'nat': (69, 74), 'time': (87, 98), 'cls': (100, 105),
                                'crank': (105, 110)},
                     'anchor_inked': (6, *range(88, 97)), 'anchor_blank': (4, 5, 7, 8, 86, 87, 97, 98), 'anchor_least': 8,
                     'punctuation': {89: ':', 92: ':', 95: '.'}, 'time_columns': (88, 90, 91, 93, 94, 96),
                     'column_characters': PRINTER.column_characters[:74] + [LETTERS + DIGITS] * 13
                     + [DIGITS + ':.'] * 11 + [DIGITS] * 12})
#the class codes. no page gives them, so they're inferred: men's 1-4 and women's 5-8, the last of each by far the
#largest (everyone 19 and over, as 1986's kortelopet prints it) and the other three the juniors' by age, the older the
#faster and the 15-16s the most
CLASS_CODES = {1: 'M 13-14', 2: 'M 15-16', 3: 'M 17-18', 4: 'M 19+', 5: 'F 13-14', 6: 'F 15-16', 7: 'F 17-18',
               8: 'F 19+'}
#page 30's kortelopet starts below the women's birkebeiner and its heading, in the second block (the first holds none)
BLOCK_TOP = {(30, 1): 9999, (30, 2): 1380}
#page 30's blocks, where the birkebeiner's table above the kortelopet's throws off finding them. its kortelopet lines
#set the rank to the country three columns further right of the time than the pages after do, so those columns are
#moved back
BLOCK_EDGES = {30: (160, 1685)}
COLUMN_MAPS = {30: [(3, 77, 0), (77, 110, 77)]}
#the last two lines of page 32's first block and the last of the men's and women's on page 34's first are printed too
#faintly to anchor
EXTRA_LINES = {(32, 1): 2, (34, 1): 1}


def parse(year=YEAR):
    return line_printer.parse(year, 'kortie')


def ocr(year=YEAR):
    line_printer.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
