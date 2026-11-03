#1986 birch scroll: the birkebeiner results are pages 14-32 (men; page 32's first block ends the list) and 32-34
#(women, from the foot of page 32's first block), the kortelopet's 35-41. each results page is printed across the
#page, with two blocks of cooper sports timing's fixed pitch table side by side, read by line_printer.py: RANK, SEX,
#FINAL TIME, BIB, NAME, HOMETOWN, ST, ZIP, NAT, CLASS ("M40-44"), CL RANK, 25% ("Y"). no pace column. page 14 (men's
#places 1-100, under the class results) sets the same table's fields closer together to fit a page printed upright
import sys

import numpy as np

from old_results_parsers import line_printer
from old_results_parsers.line_printer import Printer, DIGITS, LETTERS

YEAR = 1986
PAGES = {**{p: 'M' for p in range(14, 32)}, 32: ('MF', 'F'), 33: 'F', 34: 'F'}
#the pages are stored upright. the small turn (degrees counterclockwise) that makes each one's lines level, found by
#the sharpest profile of ink by row (line_printer.level_angle)
TURN = {}
ANGLE = {14: -0.64, 15: 1.0, 16: -0.13, 17: 1.19, 18: 0.18, 19: 0.22, 20: 0.36, 21: 1.28, 22: 0.05, 23: 0.41,
         24: -1.11, 25: -0.01, 26: -0.03, 27: 0.04, 28: -0.01, 29: 0.25, 30: -1.05, 31: -0.28, 32: -0.49, 33: -0.09,
         34: 0.2}
#the left edge of the first page's first block, level
FIRST_BLOCK = 150
#12.52 pixels a character and 25 a line, two blocks a page. the place in columns 0-3, the sex in 7, the time in
#12-20, the bib in 23-26, the name from 29, the town from 55, the state in 71-72, the zip in 76-81, the nation in
#84-86, the class in 89-94, its rank in 98-100 and the 25% club's Y in 104
PRINTER = Printer(pitch=12.52, pitches=np.arange(12.2, 12.85, 0.002), blocks=2, block_width=1400, block_chars=110,
                  block_step=(1500, 1700), title_rows=250, line_pitch=25, line_gap=7, line_height=(12, 24),
                  joined_height=80, strips=((15, 300), (300, 600), (600, 900), (900, 1150), (1150, 1380)), band=19,
                  glyph_widths=(3, 13), glyph_w=11, glyph_h=26, middle=9, middle_slack=7,
                  fields={'rank': (0, 5), 'sex': (6, 9), 'time': (11, 22), 'bib': (22, 28), 'name': (28, 55),
                          'town': (55, 71), 'st': (71, 74), 'zip': (75, 82), 'nat': (82, 88), 'cls': (88, 95),
                          'crank': (95, 102), 'club': (102, 108)},
                  anchor_inked=(7, *range(12, 21)), anchor_blank=(4, 5, 6, 8, 9, 10, 11, 21), anchor_least=8,
                  place_columns=range(0, 4), sex_columns=(7, 89), punctuation={13: ':', 16: ':', 19: '.'},
                  time_columns=(12, 14, 15, 17, 18, 20), pace_columns=(), age_columns=(90, 91, 93, 94),
                  column_characters=[DIGITS] * 6 + ['MF'] * 3 + [DIGITS + ':.'] * 13 + [DIGITS] * 6
                  + [LETTERS + "-.'&"] * 43 + [LETTERS] * 3 + [LETTERS] + [LETTERS + DIGITS] * 7 + [LETTERS] * 6
                  + [LETTERS] + ['MF'] + [DIGITS] * 2 + ['-+'] + [DIGITS] * 2 + [DIGITS] * 7 + [LETTERS] * 8)

#page 14 prints the table under the class results, upright, two blocks to the width of the page: the same printer,
#its fields closer together (the name 20 characters, not 26). its rank is left aligned from column 4, the sex is in 9,
#the time in 12-20, the bib 23-26, the name from 29, the town from 50, the state 66-67, the zip 71-76, the nation
#79-81, the class 84-89, its rank ending in 93 and the 25% club's Y in 95, moved to this printer's columns
TABLE_TOP = {14: 1880}
PAGE_PRINTERS = {14: Printer(pitch=12.52, pitches=np.arange(12.2, 12.85, 0.002), blocks=2, block_width=1200,
                             block_chars=97, line_pitch=25, line_gap=7, line_height=(12, 24), joined_height=80,
                             strips=((15, 300), (300, 600), (600, 900), (900, 1150)), band=19, glyph_widths=(3, 13),
                             glyph_w=11, glyph_h=26, anchor_inked=(9, *range(12, 21)),
                             anchor_blank=(6, 7, 8, 10, 11, 21))}
BLOCK_EDGES = {14: (152, 1350)}
COLUMN_MAPS = {14: [(4, 8, 0, 'right'), (9, 10, 7), (12, 21, 12), (23, 27, 23), (29, 49, 29), (50, 66, 55),
                    (66, 68, 71), (71, 77, 76), (79, 82, 84), (84, 90, 89), (90, 94, 97), (95, 96, 104)]}


def parse(year=YEAR):
    return line_printer.parse(year)


def ocr(year=YEAR):
    line_printer.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
