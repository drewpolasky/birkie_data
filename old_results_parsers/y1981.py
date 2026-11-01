#1981 birch scroll: the birkebeiner results are pages 9-20 (printed 7-18), two blocks a page of minnesota micro systems'
#fixed pitch table, men and women in one list by overall place, in groups of five lines, read by line_printer.py: BIB,
#NAME (surname first), CITY, ST, CTRY, CTZ ("$"), YRS, 25% ("*"), TIME (h:mm.ss.hh), RANK, CL (the class, as a number)
#and CLASS RANK
import sys

import numpy as np

from old_results_parsers import line_printer
from old_results_parsers.line_printer import Printer, DIGITS, LETTERS

YEAR = 1981
#'X': men and women in one list
PAGES = {p: 'X' for p in range(9, 21)}
TURN = {}
ANGLE = {9: 0.06, 10: 0.17, 11: 0.38, 12: -0.08, 13: 0.75, 14: -0.08, 15: 0.76, 16: 0.04, 17: 0.7, 18: 0.02,
         19: 1.15, 20: -0.09}
#the left edge of the first page's first block, level
FIRST_BLOCK = 135
#13.62 pixels a character and 22.6 a line, two blocks a page, a blank line after every fifth (now and then a little
#more). the bib in columns 6-9, the name from 11, the city from 33, the state in 51-52, the country in 54-56, YRS in
#60, the time in 64-73, the rank in 75-78, the class code in 80-81 and its rank in 84-86. the time's colon and points
#can print too faintly to anchor on. the copy stretches each block's left part (to the city) against its right, by an
#amount that changes down the block, so the grid is set by the right part (the time, rank and class), and the left
#part stretched to put the bib's last digit in column 9 and the name's first letter in 11. the stretch isn't even along
#a line either, so the glyphs nearer a column, and further off it, set its offset
PRINTER = Printer(pitch=13.62, pitches=np.arange(13.3, 13.9, 0.002), blocks=2, block_width=1190, block_chars=88,
                  block_step=(1120, 1220), title_rows=140, line_pitch=22.6, line_gap=8, line_height=(10, 20),
                  joined_height=60, separator_lines=2, strips=((45, 300), (300, 600), (600, 900), (900, 1150)),
                  line_strip=3, band=15, glyph_widths=(2, 14), glyph_w=12, glyph_h=20, glyph_top=3, middle=7,
                  middle_slack=6, label_marks='.,', drift_most=6, drift_reach=3,
                  fields={'bib': (5, 10), 'name': (10, 32), 'town': (32, 50), 'st': (50, 53), 'nat': (53, 57),
                          'club': (57, 63), 'time': (63, 74), 'rank': (74, 79), 'cls': (79, 83), 'crank': (83, 88)},
                  anchor_inked=(64, 66, 67, 69, 70, 72, 73, 78, 80), anchor_blank=(63, 74, 79, 82, 83),
                  anchor_least=9, pitch_from=680, left_anchor=(64, (9, 11), (10,)),
                  anchor_pitch=True,
                  place_columns=range(75, 79), sex_columns=(), punctuation={65: ':', 68: '.', 71: '.'},
                  time_columns=(64, 66, 67, 69, 70, 72, 73), pace_columns=(), age_columns=(),
                  column_characters=[DIGITS] * 10 + [LETTERS + "-.,'&"] * 40 + [LETTERS] * 7 + [LETTERS + DIGITS] * 7
                  + [DIGITS + ':.'] * 10 + [DIGITS] * 14)
#the class codes, as the class results page gives them
CLASS_CODES = {1: 'M 19-24', 2: 'M 25-29', 3: 'M 30-34', 4: 'M 35-39', 5: 'M 40-44', 6: 'M 45-49', 7: 'M 50-54',
               8: 'M 55-59', 9: 'M 60+', 10: 'F 19-24', 11: 'F 25-29', 12: 'F 30-34', 13: 'F 35-39', 14: 'F 40-44',
               15: 'F 45-49', 16: 'F 50-54', 17: 'F 55-59', 18: 'F 60+'}
SURNAME_FIRST = True
#the class legend above page 9's table
TABLE_TOP = {9: 570}


def parse(year=YEAR):
    return line_printer.parse(year)


def ocr(year=YEAR):
    line_printer.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
