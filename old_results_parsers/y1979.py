#1979 birch scroll: the birkebeiner results are pages 3-12 (printed 11-20), set sideways, two blocks a page of a line
#printer's table, men and women in one list by overall place, read by line_printer.py: PLACE, NAME (surname first),
#BIB, CLS (the class, as a number), STD (the class rank), CITY (8 characters), STE, CNTRY (written out), YRS FIN, TIME
#(h:mm:ss.hh) and 25% ("*"). the printer now and then leaves out a W (NOR AY, WI printed I), and tesseract learns its
#comma, which the glyphs' network otherwise takes for a T (and still now and then for &, T or Y)
import sys

import numpy as np
from PIL import Image

from old_results_parsers import line_printer
from old_results_parsers.line_printer import Printer, DIGITS, LETTERS, OCR_CHARACTERS

YEAR = 1979
#'X': men and women in one list
PAGES = {p: 'X' for p in range(3, 12)}
TURN = {p: Image.ROTATE_90 for p in PAGES}
ANGLE = {3: -0.06, 4: -0.06, 5: 0.32, 6: -0.55, 7: 0.93, 8: 0.19, 9: -0.72, 10: 0.39, 11: -0.43}
#each page's blocks' left edges, level (the first block's first column is at the scan's edge)
FIRST_BLOCK = 0
BLOCK_EDGES = {3: (0, 1572), 4: (0, 1554), 5: (8, 1561), 6: (9, 1572), 7: (42, 1593), 8: (7, 1554), 9: (34, 1571),
               10: (18, 1539), 11: (27, 1553)}
#18.73 pixels a character and 31 a line, two blocks a page. the place right aligned in columns 0-3, the name from 5,
#the bib in 25-28, the class code in 31-32 and its rank in 34-36, the city from 38, the state in 47-48, the country
#from 50, the years finished in 58, the time in 66-75 and the 25% club's star in 77. every result line has its time's
#hour and first minutes digit, where parts of the table are blanked out on the scan and where the scan's edge cuts it
#off (and now and then the printer leaves out a digit or a colon after it)
PRINTER = Printer(pitch=18.73, pitches=np.arange(18.4, 19.1, 0.002), blocks=2, block_width=1480, block_chars=79,
                  block_step=(1480, 1620), title_rows=250, line_pitch=31, line_gap=8, line_height=(12, 28),
                  joined_height=90, strips=((0, 300), (300, 650), (650, 1000), (1000, 1225), (1225, 1480)),
                  line_strip=4, band=22, glyph_widths=(3, 18), glyph_w=16, glyph_h=26, glyph_top=3, middle=11,
                  middle_slack=8, label_marks='.,', drift_most=4, drift_reach=4, ocr_characters=OCR_CHARACTERS + ' ,',
                  dropped_letters='W', comma_letters='&TY',
                  nation_names={'USA': 'USA', 'CANADA': 'CAN', 'NORWAY': 'NOR', 'FINLAND': 'FIN', 'SWEDEN': 'SWE',
                                'ITALY': 'ITA', 'GERMANY': 'GER', 'AUSTRIA': 'AUT', 'SWITZ': 'SUI', 'FRANCE': 'FRA',
                                'JAPAN': 'JPN', 'ICELAND': 'ISL', 'AUSTRAL': 'AUS', 'CZECH': 'TCH'},
                  fields={'rank': (0, 4), 'name': (5, 25), 'bib': (25, 30), 'cls': (30, 33), 'crank': (33, 37),
                          'town': (37, 46), 'st': (46, 49), 'nat': (49, 57), 'club': (57, 61), 'time': (65, 76)},
                  anchor_inked=(66, 67, 68), anchor_blank=(4, 62, 65), anchor_least=3,
                  place_columns=range(0, 4), sex_columns=(), punctuation={67: ':', 70: ':', 73: '.'},
                  time_columns=(66, 68, 69, 71, 72, 74, 75), pace_columns=(), age_columns=(),
                  column_characters=[DIGITS] * 5 + [LETTERS + "-.,'&"] * 20 + [DIGITS] * 12 + [LETTERS + "-.'&"] * 9
                  + [LETTERS] * 11 + [DIGITS] * 8 + [DIGITS + ':.'] * 11 + [DIGITS] * 3)
#the class codes, as the results' first page gives them
CLASS_CODES = {1: 'M 19-24', 2: 'M 25-29', 3: 'M 30-34', 4: 'M 35-39', 5: 'M 40-44', 6: 'M 45-49', 7: 'M 50-54',
               8: 'M 55-59', 9: 'M 60+', 10: 'F 19-24', 11: 'F 25-29', 12: 'F 30-34', 13: 'F 35-39', 14: 'F 40-44',
               15: 'F 45-49', 16: 'F 50-54', 17: 'F 55-59', 18: 'F 60+'}
SURNAME_FIRST = True
#the article and class legend above page 3's left block
TABLE_TOP = {3: 1060}
BLOCK_TOP = {(3, 2): 470}
#the scan's edge cuts off the right blocks' times on pages 4 and 6 (after the seconds) and 8 (after the tens of seconds)
CUT_TIMES = {(4, 2): 5, (6, 2): 5, (8, 2): 4}
#three lines printed slanted on page 4, whose times can't be read, as printed (the third's hundredths are faint)
HAND = {(4, 2, 1998): {'time': '4:13:49.28'}, (4, 2, 2028): {'time': '4:13:50.00'}, (4, 2, 2057): {'time': '4:13:52'}}


def parse(year=YEAR):
    return line_printer.parse(year)


def ocr(year=YEAR):
    line_printer.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
