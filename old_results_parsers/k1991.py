#1991 birch scroll: the kortelopet results are pages 42-46 (men, ending partway down page 46) and 46-49 (women, below
#them on page 46), printed sideways as the birkebeiner's (y1991.py) and read as 1988's (k1988.py). the PACE column is
#the time over 21 km (the race started from an alternate start, as the birkebeiner did)
import sys

from PIL import Image

from old_results_parsers import line_printer
from old_results_parsers.k1988 import TABLE
from old_results_parsers.y1991 import YEAR

PAGES = {**{p: 'M' for p in range(42, 46)}, 46: ('MF', 'MF', 'MF'), **{p: 'F' for p in range(47, 50)}}
TURN = {p: Image.ROTATE_270 for p in PAGES}
ANGLE = {42: -1.36, 43: -0.01, 44: -0.9, 45: 0.11, 46: -0.3, 47: -0.07, 48: -0.85, 49: 0.05}
#the left edge of the first page's first block, upright and level: the table sits two columns further left in its
#frame than the birkebeiner's
FIRST_BLOCK = 145
PACE_KM = 21
PRINTER = line_printer.Printer(**TABLE)


def parse(year=YEAR):
    return line_printer.parse(year, 'kortie')


def ocr(year=YEAR):
    line_printer.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
