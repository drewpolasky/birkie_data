#1990 birch scroll: the birkebeiner results are pages 27-39 (men; page 39 has one block, beside photos) and 40-41
#(women; page 41's second and third blocks stop at a photo), the kortelopet's 42-49. each results page is printed
#across the page, with three blocks of the same line printer's table as 1991 side by side, 81 lines a block, read by
#line_printer.py. the PACE column is the time over 53.5 km
import sys

from old_results_parsers import line_printer

YEAR = 1990
PAGES = {**{p: 'M' for p in range(27, 40)}, **{p: 'F' for p in range(40, 42)}}
#the pages are stored upright. the small turn (degrees counterclockwise) that makes each one's lines level, found by
#the sharpest profile of ink by row (line_printer.level_angle)
TURN = {}
ANGLE = {27: -0.06, 28: -0.06, 29: -0.15, 30: -1.07, 31: -0.77, 32: -0.57, 33: -0.38, 34: -0.55, 35: -0.18,
         36: -1.04, 37: -0.39, 38: -0.61, 39: 0.12, 40: -0.94, 41: -0.75}
#the left edge of the first page's first block, level
FIRST_BLOCK = 150
PACE_KM = 53.5
#1991's line printer, but a line counts from 12 pixels high, as for 1988
PRINTER = line_printer.Printer(line_height=(12, 24))


def parse(year=YEAR):
    return line_printer.parse(year)


def ocr(year=YEAR):
    line_printer.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
