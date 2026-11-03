#1987 birch scroll: the kortelopet results are pages 37-41 (men, from below the women's birkebeiner on page 37 to the
#top third of page 41) and 41-44 (women, from below the men's on page 41; page 44's blocks stop at a photo), printed
#on the birkebeiner's printer (y1987.py) and read the same way
import sys

from old_results_parsers import line_printer
from old_results_parsers.k1988 import AGES
from old_results_parsers.line_printer import Printer
from old_results_parsers.y1987 import YEAR, TURN, PRINTER

PAGES = {**{p: 'M' for p in range(37, 41)}, 41: ('MF', 'MF', 'MF'), **{p: 'F' for p in range(42, 45)}}
ANGLE = {37: 0.65, 38: 0.21, 39: -0.08, 40: -0.41, 41: 0.43, 42: -0.09, 43: 0.7, 44: -0.91}
#the left edge of the first page's first block, level: the table sits about four columns further right in its block
#than the birkebeiner's
FIRST_BLOCK = 215
#the birkebeiner's printer, but the town to the class rank sit a column or so right of the rest of the line, more on
#some lines than others, and set wider, so that part of each line gets its own pitch and shift, found where its class
#(always printed) is inked. the classes are the kortelopet's, with its juniors'
PRINTER = Printer(**{**vars(PRINTER), 'ages': AGES, 'right_anchor': None, 'part_pitches': True,
                     'moved_parts': ((55, 96, (81, 82, 83, 84, 85, 86), (79, 80, 87, 88)),)})
#page 37's kortelopet starts below the women's birkebeiner and its heading
BLOCK_TOP = {(37, 1): 1440, (37, 2): 1440, (37, 3): 1440}


def parse(year=YEAR):
    return line_printer.parse(year, 'kortie')


def ocr(year=YEAR):
    line_printer.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
