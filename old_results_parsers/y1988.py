#1988 birch scroll: the birkebeiner results are pages 24-35 (men) and 36-37 (women), the kortelopet's 38-44. the second
#and third blocks of pages 35 and 37 stop at a photo. each results page is printed across the page, with three blocks of
#the same line printer's table as 1990 and 1991 side by side, 80 or 81 lines a block, read by line_printer.py. the PACE
#column is the time over 52.5 km
import sys

from old_results_parsers import line_printer

YEAR = 1988
PAGES = {**{p: 'M' for p in range(24, 36)}, **{p: 'F' for p in range(36, 38)}}
#the pages are stored upright. the small turn (degrees counterclockwise) that makes each one's lines level, found by
#the sharpest profile of ink by row (line_printer.level_angle)
TURN = {}
ANGLE = {24: 0.06, 25: -1.97, 26: -0.13, 27: -1.11, 28: -0.71, 29: -1.83, 30: -0.54, 31: -1.94, 32: -0.08, 33: -1.38,
         34: -0.17, 35: -1.63, 36: -0.62, 37: -1.17}
#the left edge of the first page's first block, level
FIRST_BLOCK = 140
PACE_KM = 52.5
#1991's line printer, but a line counts from 12 pixels high, since one on page 37 prints that faintly
PRINTER = line_printer.Printer(line_height=(12, 24))


def parse(year=YEAR):
    return line_printer.parse(year)


def ocr(year=YEAR):
    line_printer.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
