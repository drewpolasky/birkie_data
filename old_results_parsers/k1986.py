#1986 birch scroll: the kortelopet results are pages 35-38 (men; page 38's second block ends the list) and 38-41
#(women, from below the men's in page 38's second block; page 41's second block stops at a photo), printed on the
#birkebeiner's printer (y1986.py) and read the same way
import sys

from old_results_parsers import line_printer
from old_results_parsers.line_printer import Printer, DIGITS, LETTERS
from old_results_parsers.y1986 import YEAR, TURN, PRINTER

PAGES = {**{p: 'M' for p in range(35, 38)}, 38: ('M', 'MF'), **{p: 'F' for p in range(39, 42)}}
ANGLE = {35: 0.31, 36: -0.21, 37: 0.07, 38: -0.02, 39: -0.09, 40: -0.49, 41: 0.39}
#the left edge of the first page's first block, level: the table sits about four columns further right in its block
#than the birkebeiner's
FIRST_BLOCK = 200
#the birkebeiner's printer, but its table has no 25% column: the class is a column right of the birkebeiner's (in
#90-95) and its rank two (ending in 102). its classes are the juniors' (13-14, 15-16, 17-18) and one for everyone
#older, 19+
PRINTER = Printer(**{**vars(PRINTER), 'ages': ('13-14', '15-16', '17-18', '19+'),
                     'fields': {**{k: v for k, v in PRINTER.fields.items() if k != 'club'}, 'cls': (89, 97),
                                'crank': (97, 104)},
                     'sex_columns': (7, 90), 'age_columns': (91, 92, 94, 95),
                     'column_characters': PRINTER.column_characters[:88] + [LETTERS] * 2 + ['MF'] + [DIGITS] * 2
                     + ['-+'] + [DIGITS] * 2 + [DIGITS] * 8 + [LETTERS] * 6})


def parse(year=YEAR):
    return line_printer.parse(year, 'kortie')


def ocr(year=YEAR):
    line_printer.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
