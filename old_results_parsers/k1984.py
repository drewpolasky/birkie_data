#1984 birch scroll: the kortelopet results ("TELEMARK KORTELOPET") are page 33 (men from 1, below the women's
#birkebeiner in its second block), 35-37 (men to 672; page 34 is an ad) and 38-40 (women from 136), printed on the
#birkebeiner's printer (y1984.py) and read the same way. the scanned issue has no page with the women's places 1-135
#(nor any men's after 672), and page 41 (women 730-773, printed upright under a column of thanks, its characters
#narrower than the rest) isn't read. the class codes are 1985's kortelopet's (k1985.py), as the codes' sizes and
#times show
import sys

from old_results_parsers import line_printer
from old_results_parsers.k1985 import CLASS_CODES
from old_results_parsers.y1984 import YEAR, TURN, FIRST_BLOCK, PRINTER, SURNAME_FIRST

PAGES = {33: ('M', 'M'), **{p: 'M' for p in range(35, 38)}, **{p: 'F' for p in range(38, 41)}}
ANGLE = {33: -1.2, 35: -0.15, 36: 0.6, 37: 0.26, 38: 0.53, 39: 0.4, 40: 0.48}
#page 33's kortelopet starts below the women's birkebeiner and its heading, in the second block (the first holds none)
BLOCK_TOP = {(33, 1): 9999, (33, 2): 740}
FIRST_PLACE = {'F': 136}
#as in the birkebeiner, the pages were scanned with their foot cut off, losing up to five lines a block (99 lines to a
#full block), and the foot of page 37's first block is shaded with a dither too dark to read its last six lines
MISSING_LINES = {(33, 2): 3, (35, 1): 5, (35, 2): 4, (37, 1): 6, (37, 2): 2, (38, 1): 4, (38, 2): 3, (39, 2): 1,
                 (40, 1): 1, (40, 2): 2}


def parse(year=YEAR):
    return line_printer.parse(year, 'kortie')


def ocr(year=YEAR):
    line_printer.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
