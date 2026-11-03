#1982 birch scroll: the birkebeiner results are page 13 (places 1-100, under the class results) and pages 14-34,
#printed across the page, in blocks of another printer's fixed pitch table, men and women in one list by overall
#place, read by line_printer.py: BIB, NAME (surname first, in upper or mixed case), CITY, ST, CTRY, CTZ, YRS,
#25% (a figure), TIME (h:mm:ss), RANK, CL (the class, as a number) and CLASS RANK. the scan has the printed pages out
#of order (its page 44 is printed page 26) and some twice (its pages 30 and 45 are its page 28, its page 31 its page
#29), and is missing the page with places 2945-3181 between its pages 28 and 29. pages 36-40 are the kortelopet
import sys

import numpy as np

from old_results_parsers import line_printer
from old_results_parsers.line_printer import Printer, DIGITS, LETTERS

YEAR = 1982
#'X': men and women in one list
PAGES = {p: 'X' for p in [13, 14, 15, 18, 19, 20, 21, 22, 23, 44, 26, 27, 28, 29, 32, 33, 34]}
TURN = {}
ANGLE = {13: 0.61, 14: -0.06, 15: 0.02, 18: 0.68, 19: 0.28, 20: -0.03, 21: 0.15, 22: 0.23, 23: 0.04, 26: 0.82,
         27: 1.48, 28: 0.43, 29: 1.48, 30: 1.25, 31: 0.05, 32: 1.48, 33: 0.71, 34: 1.51, 44: 1.35, 45: 0.24}
#the left edge of the first block on the first page printed across, level
FIRST_BLOCK = 272
#9.48 pixels a character and 25.7 a line, three blocks a page. the bib in columns 0-3, the name from 5, the city from
#31, the state in 52-53, the country in 55-57, the CTZ in 59, YRS in 62, the 25% figure in 65, the time in 70-76, the
#rank in 81-84, the class code in 86-87 and its rank in 91-93. lower case letters are read as their capitals
PRINTER = Printer(pitch=9.48, pitches=np.arange(9.3, 9.7, 0.002), blocks=3, block_width=905, block_chars=95,
                  block_step=(930, 990), title_rows=320, line_pitch=25.7, line_gap=6, line_height=(14, 24),
                  joined_height=75, strips=((15, 225), (225, 450), (450, 675), (675, 900)), line_strip=3,
                  band=20, glyph_widths=(2, 12), glyph_w=9, glyph_h=24, glyph_top=3, middle=10, middle_slack=7,
                  fields={'bib': (0, 4), 'name': (4, 30), 'town': (30, 51), 'st': (51, 54), 'nat': (54, 58),
                          'club': (58, 69), 'time': (69, 78), 'rank': (79, 85), 'cls': (85, 89), 'crank': (89, 95)},
                  anchor_inked=(3, *range(70, 77), 84, 86), anchor_blank=(4, 68, 69, 77, 78, 79, 80, 85),
                  anchor_least=10, anchor_pitch=True,
                  place_columns=range(81, 85), sex_columns=(), punctuation={71: ':', 74: ':'},
                  time_columns=(70, 72, 73, 75, 76), pace_columns=(), age_columns=(),
                  ocr_characters=line_printer.OCR_CHARACTERS + 'abcdefghijklmnopqrstuvwxyz,', label_marks='.,',
                  column_characters=[DIGITS] * 4 + [LETTERS + "-.,'&"] * 47 + [LETTERS] * 7
                  + [LETTERS + DIGITS] * 11 + [DIGITS + ':'] * 9 + [DIGITS] * 7 + [DIGITS] * 4 + [DIGITS] * 6)
#the class codes, as the class results page gives them, and 0, printed for men and women with no age class (X)
CLASS_CODES = {0: 'X', 1: 'M 19-24', 2: 'M 25-29', 3: 'M 30-34', 4: 'M 35-39', 5: 'M 40-44', 6: 'M 45-49', 7: 'M 50-54',
               8: 'M 55-59', 9: 'M 60+', 10: 'F 19-24', 11: 'F 25-29', 12: 'F 30-34', 13: 'F 35-39', 14: 'F 40-44',
               15: 'F 45-49', 16: 'F 50-54', 17: 'F 55+'}
SURNAME_FIRST = True
#page 13 is printed upright and larger, with two blocks of 50 lines
SCALE = {13: 0.8745}
PAGE_PRINTERS = {13: Printer(**{**vars(PRINTER), 'blocks': 2})}
BLOCK_EDGES = {13: (177, 1139)}
TABLE_TOP = {13: 1280}
#the page missing from the scan, after page 28's last block
MISSING_LINES = {(28, 3): 237}
#the RANK column jumps from 3800 to 3815 on page 33's second block, though the class ranks show no skier missing
RANK_SKIPS = {(33, 2, 67): 14}
#the list's last three lines (places 4093-4095), whose times are printed with two digits too many. the typeset list
#below them, of times corrected after the race, isn't read
EXTRA_LINES = {(34, 3): 3}


def parse(year=YEAR):
    return line_printer.parse(year)


def ocr(year=YEAR):
    line_printer.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
