#1990 birch scroll: the kortelopet results are pages 42-46 (men, ending partway down page 46) and 46-49 (women, below
#them on page 46; page 49's blocks stop at a photo), printed and read as 1988's (k1988.py). the PACE column is the time
#over 29 km
import sys

from old_results_parsers import line_printer
from old_results_parsers.k1988 import PRINTER
from old_results_parsers.y1990 import YEAR, TURN, FIRST_BLOCK

PAGES = {**{p: 'M' for p in range(42, 46)}, 46: ('MF', 'MF', 'MF'), **{p: 'F' for p in range(47, 50)}}
ANGLE = {42: -0.23, 43: -0.02, 44: -1.46, 45: -0.47, 46: -1.3, 47: -0.67, 48: -0.54, 49: -0.34}
PACE_KM = 29


def parse(year=YEAR):
    return line_printer.parse(year, 'kortie')


def ocr(year=YEAR):
    line_printer.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
