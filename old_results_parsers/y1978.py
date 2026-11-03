#1978 birch scroll: the birkebeiner results are pages 14-19 and 23-27 (printed 9-14 and 18-22), two blocks a page of a
#line printer's table, men and women in one list by overall place, read by line_printer.py: PLACE, NAME (surname
#first), BIB, CLS (the class, as a number), STD (the class rank), CITY (8 characters), STE, CNTRY (written out: NORWAY,
#FINDLAN), CLUB, TIME (h:mm:ss.hh) and 25% ("*"). the table runs across each pair of facing pages: down the left
#page's left block, the right page's left block, then the left page's right block and the right page's
import sys

import numpy as np

from old_results_parsers import line_printer
from old_results_parsers.line_printer import Printer, DIGITS, LETTERS, OCR_CHARACTERS

YEAR = 1978
#'X': men and women in one list
PAGES = {p: 'X' for p in (14, 15, 16, 17, 18, 19, 23, 24, 25, 26, 27)}
#(page, block) in the order the list runs: across each pair of facing pages, then page 27's two
BLOCK_ORDER = [(page, k) for pair in ((14, 15), (16, 17), (18, 19), (23, 24), (25, 26)) for k in (1, 2)
               for page in pair] + [(27, 1), (27, 2)]
TURN = {}
ANGLE = {14: -0.05, 15: 0.74, 16: -0.32, 17: 1.09, 18: 0.05, 19: 0.84, 23: -0.03, 24: 0.41, 25: 0.92, 26: 0.28,
         27: 0.91}
#the scans' edges are black, and shaded with a dither of single pixels over the lines there
SPECKS = 4
BLOTS = 3000
#the left edge of the first page's first block, level
FIRST_BLOCK = 105
#16.3 pixels a character and 27.2 a line, two blocks a page. the place right aligned in columns 2-5, a star in 7 for a
#few of the fastest (left out), the name from 8, the bib in 28-31, the class code in 33-34 and its rank in 36-38, the
#city from 40, the state in 49-50, the country from 52, the club from 60, the time in 68-77 and the 25% club's star in
#79. the town is read as letters only, since the printer's I and 1 look alike. tesseract runs the words of a line
#together unless a space is among the characters it may read
PRINTER = Printer(pitch=16.3, pitches=np.arange(16.0, 16.6, 0.002), blocks=2, block_width=1320, block_chars=81,
                  block_step=(1380, 1500), title_rows=150, line_pitch=27.2, line_gap=6, line_height=(12, 26),
                  joined_height=80, strips=((20, 330), (330, 640), (640, 960), (960, 1310)), line_strip=0, band=20,
                  glyph_widths=(2, 16), glyph_w=14, glyph_h=24, glyph_top=3, middle=10, middle_slack=7,
                  label_marks='.,', drift_most=4, drift_reach=4, fit_tops=4, ocr_characters=OCR_CHARACTERS + ' ',
                  comma_letters='Y',
                  nation_names={'USA': 'USA', 'CANADA': 'CAN', 'NORWAY': 'NOR', 'FINLAND': 'FIN', 'FINDLAN': 'FIN',
                                'SWEDEN': 'SWE', 'ITALY': 'ITA', 'GERMANY': 'GER', 'AUSTRIA': 'AUT', 'SWITZ': 'SUI',
                                'SWISS': 'SUI', 'FRANCE': 'FRA', 'JAPAN': 'JPN'},
                  fields={'rank': (1, 6), 'name': (8, 28), 'bib': (28, 32), 'cls': (32, 35), 'crank': (35, 39),
                          'town': (39, 48), 'st': (48, 51), 'nat': (51, 59), 'club': (59, 67), 'time': (67, 78)},
                  anchor_inked=(5, 28, 29, 30, 31, 33, 34, 68, 69, 70, 71, 72, 73, 74, 76, 77),
                  anchor_blank=(6, 7, 32, 35, 39, 67, 78), anchor_least=14,
                  place_columns=range(2, 6), sex_columns=(), punctuation={69: ':', 72: ':', 75: '.'},
                  time_columns=(68, 70, 71, 73, 74, 76, 77), pace_columns=(), age_columns=(),
                  column_characters=[DIGITS] * 8 + [LETTERS + "-.,'&"] * 20 + [DIGITS] * 11
                  + [LETTERS + "-.'&"] * 9 + [LETTERS] * 11 + [LETTERS + DIGITS] * 8 + [DIGITS + ':.'] * 11
                  + [DIGITS] * 3)
#the class codes, as the results' first page gives them
CLASS_CODES = {1: 'M 19-24', 2: 'M 25-29', 3: 'M 30-34', 4: 'M 35-39', 5: 'M 40-44', 6: 'M 45-49', 7: 'M 50-54',
               8: 'M 55-59', 9: 'M 60+', 10: 'F 19-34', 11: 'F 35+'}
SURNAME_FIRST = True
#the article and class legend above page 14's left block, and the column headings above its right block
TABLE_TOP = {14: 1290}
BLOCK_TOP = {(14, 2): 560}
#page 27's blocks, set further right above the kortelopet's results
BLOCK_EDGES = {27: (245, 1681)}
#the lines lost where each table is split across two scans, at the foot of a block or the top of the next in the list
#(counted at the foot of the earlier): places 46-48, 204, 370-372, 539-540, 712-713, 879-880, 1048-1049,
#1216-1218, 1385-1387 and 1553-1554
MISSING_LINES = {(14, 1): 3, (14, 2): 1, (16, 1): 3, (16, 2): 2, (18, 1): 2, (18, 2): 2, (23, 1): 2, (23, 2): 3,
                 (25, 1): 3, (25, 2): 2}
#a correction pasted over page 19's table, in another type: place 733, class 10's 36th in 5:41:58.81, is Anna Marie
#Beckel-Krutz, not Nancy Carlson of Minneapolis (bib 2596) as the printer has it. her bib and town aren't given. and the
#lines at the scans' edges that the glyphs can't be read on, half cut off or in the dark edge's dither, as printed
HAND = {(19, 1, 555): {'drop': True},
        (19, 1, 594): {'name': 'ANNA MARIE BECKEL-KRUTZ', 'first': 'ANNA MARIE', 'last': 'BECKEL-KRUTZ', 'bib': '',
                       'city': '', 'state': '', 'country': ''},
        (14, 1, 2402): {'name': 'MARK DIX', 'first': 'MARK', 'last': 'DIX'},
        (15, 1, 71): {'name': 'MARK PEARSON', 'first': 'MARK', 'last': 'PEARSON'},
        (19, 1, 36): {'name': 'JAMES D SCOTT', 'first': 'JAMES D', 'last': 'SCOTT'},
        (23, 1, 2489): {'time': '6:19:14.94'},
        (24, 1, 31): {'name': 'DAN PETERSON', 'first': 'DAN', 'last': 'PETERSON', 'bib': '0227', 'age_group': 'M 19-24',
                      'class_rank': '194', 'city': 'APPLETON', 'state': 'WI', 'country': 'USA', 'time': '6:19:21.99'},
        (26, 2, 32): {'name': 'DAWN NEVE', 'first': 'DAWN', 'last': 'NEVE', 'city': 'BRAINERD'}}


def parse(year=YEAR):
    return line_printer.parse(year)


def ocr(year=YEAR):
    line_printer.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
