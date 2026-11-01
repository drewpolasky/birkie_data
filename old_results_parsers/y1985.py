#1985 birch scroll: the birkebeiner results are pages 10-28 (men; page 28's first block ends the list) and 28-30
#(women, from the foot of page 28's first block; page 30's second block ends the list, the kortelopet below it). each
#results page is printed across the page, with two blocks of cooper sports timing's fixed pitch table side by side, in
#a fainter dot matrix than 1986's, read by line_printer.py: RANK, SEX, BIB, NAME (surname first), CITY, ST, CTRY, CTZ
#("Y"), 25% (a figure), TIME, CL (the class, as a number) and CLASS RANK
import sys

import numpy as np

from old_results_parsers import line_printer
from old_results_parsers.line_printer import Printer, DIGITS, LETTERS

YEAR = 1985
PAGES = {**{p: 'M' for p in range(11, 28)}, 28: ('MF', 'F'), 29: 'F', 30: 'F'}
#the pages are stored upright. the small turn (degrees counterclockwise) that makes each one's lines level, found by
#the sharpest profile of ink by row (line_printer.level_angle)
TURN = {}
ANGLE = {10: -0.13, 11: -0.38, 12: -1.81, 13: 0.05, 14: -1.69, 15: -0.14, 16: -1.45, 17: -0.16, 18: -1.64, 19: 0.05,
         20: -1.05, 21: -0.18, 22: -1.51, 23: 0.05, 24: -0.01, 25: -0.03, 26: -1.49, 27: -0.83, 28: -0.94, 29: -0.07,
         30: -0.87}
#the left edge of the first page's first block, level
FIRST_BLOCK = 125
#13.6 pixels a character and 25 a line, two blocks a page. the place in columns 0-3, the sex in 6, the bib in 9-12,
#the name from 14, the city from 45, the state in 66-67, the country in 70-72, the CTZ Y in 76, the 25% figure in 82,
#the time in 85-93, the class code in 99-100 and its rank in 104-106. the glyphs are broken into dots, so a line
#that doesn't anchor tries other pitches, and its lines are found in the strip with the state and country, which
#every line prints darkly enough, across the row with next to no ink between two rows of dots
PRINTER = Printer(pitch=13.6, pitches=np.arange(13.25, 13.85, 0.002), blocks=2, block_width=1500, block_chars=110,
                  block_step=(1500, 1650), title_rows=330, line_pitch=25, line_gap=9, line_height=(8, 22),
                  joined_height=70, row_gaps=1, strips=((15, 300), (300, 600), (600, 900), (900, 1200), (1200, 1480)),
                  line_strip=3,
                  band=17, glyph_widths=(2, 13), glyph_w=12, glyph_h=24, middle=8, middle_slack=7,
                  fields={'rank': (0, 5), 'sex': (5, 8), 'bib': (8, 14), 'name': (14, 45), 'town': (45, 66),
                          'st': (66, 69), 'nat': (69, 74), 'club': (74, 84), 'time': (84, 95), 'cls': (97, 102),
                          'crank': (102, 109)},
                  anchor_inked=(6, *range(85, 94)), anchor_blank=(4, 5, 7, 8, 83, 84, 94, 95), anchor_least=10,
                  anchor_pitch=True,
                  place_columns=range(0, 4), sex_columns=(6,), punctuation={86: ':', 89: ':', 92: '.'},
                  time_columns=(85, 87, 88, 90, 91, 93), pace_columns=(), age_columns=(),
                  column_characters=[DIGITS] * 5 + ['MF'] * 3 + [DIGITS] * 6 + [LETTERS + "-.'&"] * 52
                  + [LETTERS] * 3 + [LETTERS] * 5 + [LETTERS + DIGITS] * 10 + [DIGITS + ':.'] * 11
                  + [DIGITS] * 7 + [DIGITS] * 8)
#the class codes, as the class results page gives them
CLASS_CODES = {1: 'M 18-24', 2: 'M 25-29', 3: 'M 30-34', 4: 'M 35-39', 5: 'M 40-44', 6: 'M 45-49', 7: 'M 50-54',
               8: 'M 55-59', 9: 'M 60+', 10: 'F 18-24', 11: 'F 25-29', 12: 'F 30-34', 13: 'F 35-39', 14: 'F 40-44',
               15: 'F 45-49', 16: 'F 50-54', 17: 'F 55+'}
SURNAME_FIRST = True
#page 10 (men's places 1-100, under the class results) sets the table's fields closer together, each block its own
#way and not on one grid with the time, and isn't read yet, so the men's list here starts at place 101
FIRST_PLACE = {'M': 101}
#the last line of page 12's first block and the last two of page 14's are printed too faintly to anchor
EXTRA_LINES = {(12, 1): 1, (14, 1): 2}
#the first line of page 27's first block has its rank and sex smudged where the paper curls
LEADING_LINES = {(27, 1): 1}


def parse(year=YEAR):
    return line_printer.parse(year)


def ocr(year=YEAR):
    line_printer.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
