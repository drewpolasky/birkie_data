#1991 birch scroll: the birkebeiner results are pages 26-39 (men, places 1-3278) and 40-41 (women, places 1-441), the
#kortelopet's 42-49. page 25 says 3720 finished the birkebeiner (3719 are printed). each results page is printed sideways
#(page 34 is also upside down), with three blocks of a line printer's fixed pitch table side by side, 80 lines a block,
#read by line_printer.py. the PACE column is the time over 46 km
#
#'top' is the line's y pixel in the page turned upright (clockwise a quarter turn) and straightened by ANGLE, which is
#the x pixel from the left in the stored page image; each such x holds three results, one in each block. page 34 is
#stored upside down, and its 'top' is the line's y pixel in the stored image, counted from the top
import sys

from PIL import Image

from old_results_parsers import line_printer

YEAR = 1991
PAGES = {**{p: 'M' for p in range(26, 40)}, **{p: 'F' for p in range(40, 42)}}
#each page's turn to upright, and then the small turn (degrees counterclockwise) that makes its lines level, found by
#the sharpest profile of ink by row
TURN = {**{p: Image.ROTATE_270 for p in PAGES}, 34: Image.ROTATE_180}
ANGLE = {26: -0.19, 27: 0.37, 28: -1.32, 29: -0.4, 30: -1.47, 31: -0.68, 32: -1.45, 33: -0.1, 34: -0.09, 35: -0.27,
         36: -0.66, 37: 0.06, 38: -0.62, 39: 0.28, 40: -0.87, 41: -0.01}
#the left edge of the first page's first block, upright and level
FIRST_BLOCK = 170
PACE_KM = 46


def parse(year=YEAR):
    return line_printer.parse(year)


def ocr(year=YEAR):
    line_printer.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
