#1984 birch scroll: the birkebeiner results are pages 8-29 (men; page 29's second block ends the list) and 29-33
#(women, from the foot of page 29's second block; page 33's second block ends the list, the kortelopet below it). each
#results page is printed across the page, with two blocks of cooper sports timing's fixed pitch table side by side,
#read by line_printer.py: RANK, SEX, BIB, NAME (surname first), CITY, ST, CTRY, CTZ ("Y"), YRS, 25% (a figure), TIME,
#CL (the class, as a number) and CLASS RANK
import sys

import numpy as np

from old_results_parsers import line_printer
from old_results_parsers.line_printer import Printer, DIGITS, LETTERS

YEAR = 1984
PAGES = {**{p: 'M' for p in range(8, 29)}, 29: ('M', 'MF'), 30: 'F', 31: 'F', 32: 'F', 33: 'F'}
#the pages are stored upright. the small turn (degrees counterclockwise) that makes each one's lines level, found by
#the sharpest profile of ink by row (line_printer.level_angle)
TURN = {}
ANGLE = {8: 0.46, 9: -0.17, 10: 0.05, 11: -1.16, 12: -0.01, 13: -1.83, 14: 0.24, 15: -0.63, 16: 0.26, 17: -0.77,
         18: -0.25, 19: -0.16, 20: 0.81, 21: -1.01, 22: 0.82, 23: 0.09, 24: 0.37, 25: 0.1, 26: 0.46, 27: -0.59,
         28: 0.46, 29: -0.71, 30: -0.25, 31: -0.05, 32: 0.94, 33: -1.2}
#the left edge of the first page's first block, level
FIRST_BLOCK = 95
#14.16 pixels a character and 24 a line, two blocks a page. the place in columns 0-3, the sex in 6, the bib in 9-12,
#the name from 14, the city from 45, the state in 66-67, the country in 70-72, the CTZ Y in 76, YRS in 79, the 25%
#figure in 82, the time in 85-93, the class code in 99-100 and its rank in 104-106, as 1985's
PRINTER = Printer(pitch=14.157, pitches=np.arange(13.85, 14.45, 0.002), blocks=2, block_width=1560, block_chars=110,
                  block_step=(1550, 1750), title_rows=280, line_pitch=24, line_gap=9, line_height=(8, 22),
                  joined_height=70, strips=((15, 300), (300, 600), (600, 900), (900, 1250), (1250, 1540)), line_strip=3,
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
#the class codes, as the class results page gives them (its 14 for men 18-24 is a 1 misread)
CLASS_CODES = {1: 'M 18-24', 2: 'M 25-29', 3: 'M 30-34', 4: 'M 35-39', 5: 'M 40-44', 6: 'M 45-49', 7: 'M 50-54',
               8: 'M 55-59', 9: 'M 60+', 10: 'F 18-24', 11: 'F 25-29', 12: 'F 30-34', 13: 'F 35-39', 14: 'F 40-44',
               15: 'F 45-49', 16: 'F 50-54', 17: 'F 55+'}
SURNAME_FIRST = True
#page 8 (men's places 1-100, under the class results, printed upright) sets the table's fields closer together, the
#name cut to 21 characters and the city to 17, and is scanned a little smaller: RANK in columns 0-3, SEX 6, BIB 9-12,
#NAME 14-34, CITY 35-51, ST 52-53, CTRY 56-58, CTZ 62, YRS 65, 25% 68, TIME 71-79, CL 81-82 and CLASS RANK 84-85.
#CL is printed two or three pixels left of the time's grid and CLASS RANK four right, so each column's offset is taken
#from the glyphs nearest it, even a lone one
PAGE_PRINTERS = {8: Printer(**{**vars(PRINTER), 'pitch': 13.99, 'pitches': np.arange(13.7, 14.3, 0.002),
                               'block_width': 1200, 'block_chars': 88, 'drift_reach': 2, 'drift_least': 1,
                               'strips': ((15, 300), (300, 600), (600, 900), (900, 1208)),
                               'anchor_inked': (6, *range(71, 80)), 'anchor_blank': (4, 5, 7, 8, 69, 70, 80)})}
BLOCK_EDGES = {8: (68, 1273)}
TABLE_TOP = {8: 1990}
COLUMN_MAPS = {8: [(0, 4, 0), (6, 7, 6), (9, 13, 9), (14, 35, 14), (35, 52, 45), (52, 55, 66), (56, 59, 70),
                   (62, 63, 76), (65, 66, 79), (68, 69, 82), (71, 80, 85), (81, 83, 99), (84, 86, 105)]}
#page 27's second block is turned against the rest of the page
BLOCK_ANGLE = {(27, 2): -0.83}
#the first line of these blocks touches the rule under the headings
LEADING_LINES = {(20, 1): 1, (20, 2): 1, (22, 2): 1, (24, 1): 1, (25, 2): 1, (32, 1): 1, (32, 2): 1}
#the odd pages were scanned with their foot cut off, so up to six lines at the foot of each block (99 lines to a full
#block) are missing, a half cut line among them, and the RANK column on the next block gives how many
MISSING_LINES = {(9, 1): 2, (9, 2): 1, (11, 1): 6, (11, 2): 5, (13, 1): 5, (13, 2): 3, (15, 1): 6, (15, 2): 2,
                 (17, 1): 4, (17, 2): 3, (19, 1): 3, (19, 2): 2, (21, 1): 4, (21, 2): 2, (23, 1): 3, (23, 2): 3,
                 (25, 1): 5, (25, 2): 3, (27, 1): 6, (27, 2): 5, (29, 1): 3, (29, 2): 2, (31, 2): 1, (33, 1): 4}


def parse(year=YEAR):
    return line_printer.parse(year)


def ocr(year=YEAR):
    line_printer.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
