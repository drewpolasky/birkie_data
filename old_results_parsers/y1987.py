#1987 birch scroll: the birkebeiner results are pages 20-35 (men, places 1-2938; page 35's first block ends the
#list) and 35-37 (women, places 1-397, from page 35's second block; page 37's top third, the men's kortelopet below
#it). each results page is printed across the page, with three blocks of a printer's fixed pitch table side by side,
#64 lines a block, read by line_printer.py: RANK, SEX, FINAL TIME, BIB, NAME, HOMETOWN, ST, NAT, CLASS ("M40-44"), CL
#RANK, 25% ("Y"). no pace column. the copy of page 37's third block (women 372-397) is stretched unevenly, and its
#names and towns read poorly
import sys

import numpy as np

from old_results_parsers import line_printer
from old_results_parsers.line_printer import Printer, DIGITS, LETTERS

YEAR = 1987
PAGES = {**{p: 'M' for p in range(20, 35)}, 35: 'MFF', 36: 'F', 37: 'F'}
#the pages are stored upright. the small turn (degrees counterclockwise) that makes each one's lines level, found by
#the sharpest profile of ink by row (line_printer.level_angle)
TURN = {}
ANGLE = {20: -0.5, 21: -0.27, 22: 0.66, 23: -0.02, 24: 0.28, 25: 0.73, 26: 0.06, 27: 0.05, 28: 0.88, 29: 0.24, 30: 1.0,
         31: 0.52, 32: 0.85, 33: -0.01, 34: 1.02, 35: 0.93, 36: -0.4, 37: 0.65}
#the left edge of the first page's first block, level
FIRST_BLOCK = 177
#a larger print than 1988-1991's, about 9.46 pixels a character (9.38 to 9.53 from page to page) and 32 a line. the
#place in columns 0-3, the sex in 7, the time in 12-20, the bib in 23-26, the name from 29, the town from 55, the
#state in 71-72, the nation in 76-78, the class in 81-86, its rank in 90-92 and the 25% club's Y in 99. a cell
#is 9 pixels wide, narrower than the pitch, so the edge of a wide glyph doesn't spill into the blank beside it. the
#printer shifted the right part of some lines (from the town on) by most of a column, which the class shows. the
#last strip stops short of the rule between blocks
PRINTER = Printer(pitch=9.46, pitches=np.arange(9.25, 9.7, 0.002), block_width=990, block_chars=104,
                  block_step=(970, 1030), title_rows=480, line_pitch=32, line_gap=10, line_height=(16, 28),
                  joined_height=100, strips=((15, 225), (225, 420), (420, 620), (620, 800), (800, 950)), band=24,
                  drift_most=4.5, glyph_widths=(3, 12), glyph_w=9, glyph_h=33, glyph_top=6, middle=11, middle_slack=8,
                  fields={'rank': (0, 5), 'sex': (6, 9), 'time': (11, 22), 'bib': (22, 28), 'name': (28, 55),
                          'town': (55, 71), 'st': (71, 74), 'nat': (74, 80), 'cls': (80, 87), 'crank': (88, 95),
                          'club': (95, 101)},
                  anchor_inked=(7, *range(12, 21)), anchor_blank=(4, 5, 6, 8, 9, 10, 11, 21), anchor_least=8,
                  right_anchor=(55, (81, 82, 83, 84, 85, 86), (79, 80, 87, 88)),
                  place_columns=range(0, 4), sex_columns=(7, 81), punctuation={13: ':', 16: ':', 19: '.'},
                  time_columns=(12, 14, 15, 17, 18, 20), pace_columns=(), age_columns=(82, 83, 85, 86),
                  column_characters=[DIGITS] * 6 + ['MF'] * 3 + [DIGITS + ':.'] * 13 + [DIGITS] * 6
                  + [LETTERS + "-.'&"] * 43 + [LETTERS] * 3 + [LETTERS] * 6 + [LETTERS] + ['MF'] + [DIGITS] * 2
                  + ['-+'] + [DIGITS] * 2 + [DIGITS] * 8 + [LETTERS] * 4 + [LETTERS] * 5)

#places 38 and 52 are left blank on page 20, and 64 is never printed (its first block stops at 63, the second starts
#at 65)
MISSING_LINES = {(20, 1): 1}
#the last line of page 36's first block (place 191) is printed over shading, which fills the blanks around its time
EXTRA_LINES = {(36, 1): 1}


def parse(year=YEAR):
    return line_printer.parse(year)


def ocr(year=YEAR):
    line_printer.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
