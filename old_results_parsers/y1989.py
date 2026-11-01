#1989 birch scroll: the birkebeiner results are pages 25-36 (men; page 36's second block stops at a photo) and 37-38
#(women; page 38's second and third blocks stop at a photo), the kortelopet's 39-46. each results page is printed across
#the page, with three blocks of the same line printer's table as 1990 and 1991 side by side, 80 to 82 lines a block,
#read by line_printer.py. the PACE column is the time over 55 km. the scanned issue has no page with men's places 1-240
#(page 25, printed page 26, starts at 241, and the pages before it are the class results, facts and ads). page 27 was
#scanned turned three and a half degrees, and the scan cuts off the foot of its first block, so places 802 and 803
#(only the top of the one and the end of the other show) are left out
import sys

from old_results_parsers import line_printer

YEAR = 1989
PAGES = {**{p: 'M' for p in range(25, 37)}, **{p: 'F' for p in range(37, 39)}}
#the pages are stored upright. the small turn (degrees counterclockwise) that makes each one's lines level, found by
#the sharpest profile of ink by row (line_printer.level_angle)
TURN = {}
ANGLE = {25: -2.33, 26: -0.74, 27: -3.49, 28: -1.38, 29: -0.92, 30: 0.55, 31: -1.52, 32: -0.82, 33: -0.03, 34: -0.17,
         35: -0.66, 36: -0.24, 37: -0.74, 38: -0.54}
#the left edge of the first page's first block, level
FIRST_BLOCK = 95
PACE_KM = 55
#1991's line printer, but a line counts from 12 pixels high, as for 1988
PRINTER = line_printer.Printer(line_height=(12, 24))
#the men's list here starts at place 241, and two lines are cut off the foot of page 27's first block
FIRST_PLACE = {'M': 241}
MISSING_LINES = {(27, 1): 2}


def parse(year=YEAR):
    return line_printer.parse(year)


def ocr(year=YEAR):
    line_printer.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
