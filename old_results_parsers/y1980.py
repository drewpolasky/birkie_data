#1980 birch scroll: the birkebeiner results are pages 3-12 (printed 2-11), set sideways, two blocks a page of a
#typewritten table, men and women in one list by overall place, read by line_printer.py: RANK/CLASS (the class rank
#and the class, as a number), NAME (surname first), BIB, CITY, ST, CTRY, YRS FIN, TIME (h:mm.ss.hh), 25% ("*") and
#OVERALL. the list is set in sections under headings (TOP 20, 21-50, 51-100, ... 3001-), whose gaps in the blocks are
#no places
import sys

import numpy as np
from PIL import Image

from old_results_parsers import line_printer
from old_results_parsers.line_printer import Printer, DIGITS, LETTERS, OCR_CHARACTERS

YEAR = 1980
#'X': men and women in one list
PAGES = {p: 'X' for p in range(3, 13)}
TURN = {p: Image.ROTATE_90 for p in PAGES}
ANGLE = {3: -1.57, 4: -2.15, 5: -2.57, 6: -0.59, 7: -1.18, 8: -0.73, 9: -1.61, 10: -1.72, 11: -2.39, 12: -2.93}
#the scans' edges are black, and shaded with a dither of single pixels
SPECKS = 4
BLOTS = 3000
#each page's blocks (column 0's middle, level): the odd pages' set further right, so that the scan cuts off the right
#block's places, and on page 7 its times
BLOCK_EDGES = {3: (250, 1825), 4: (29, 1553), 5: (361, 1878), 6: (37, 1588), 7: (456, 1994), 8: (129, 1670),
               9: (286, 1806), 10: (14, 1566), 11: (323, 1865), 12: (125, 1650)}
#the scan's edge cuts across the times at the foot of these blocks, and all down page 7's right block
CUT_TIMES = {(5, 2): 'edge', (7, 2): 'edge', (11, 2): 'edge'}
#14.74 pixels a character and 24.7 a line, two blocks a page. the class rank right aligned in columns 4-6, the class
#code in 9-10, the name from 13, the bib in 44-47, the city from 50, the state in 68-70, the country in 73-75, the
#years finished in 79, the time in 82-91, the 25% club's star in 93 and the overall place right aligned in 97-100. the
#printer sets the class to the country (the left part, columns 0-76) off the rest by up to a column and a half, in
#steps of no set size: each line's grid is its time's (its pitch from the left part's glyphs, which are the more), and
#its left part is fitted to its own glyphs. the lines are found in the time's strip, so the headings aren't lines
PRINTER = Printer(pitch=14.74, pitches=np.arange(14.5, 15.0, 0.002), blocks=2, block_width=1530, block_chars=103,
                  block_step=(1480, 1580), title_rows=250, line_pitch=24.7, line_gap=5, line_height=(12, 22),
                  joined_height=80, strips=((-10, 175), (175, 640), (640, 995), (995, 1190), (1190, 1500)),
                  line_strip=4, section_gaps=True, table_gap=5, band=18, glyph_widths=(2, 15), glyph_w=14, glyph_h=26,
                  glyph_top=3, middle=9, middle_slack=7, label_marks='.,', digit_labels=True,
                  ocr_characters=OCR_CHARACTERS + ' ,',
                  fields={'crank': (3, 7), 'cls': (9, 11), 'name': (12, 44), 'bib': (44, 49), 'town': (49, 68),
                          'st': (68, 72), 'nat': (72, 77), 'club': (77, 81), 'time': (81, 93), 'rank': (96, 101)},
                  anchor_inked=(79, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91), anchor_blank=(80, 81, 92), anchor_least=5,
                  pitch_from=1135, pitch_before=1135, reanchor=False,
                  moved_parts=((0, 77, (9, 10, 44, 45, 46, 47), (7, 8, 11, 12, 42, 43, 48, 49)),),
                  place_columns=range(97, 101), sex_columns=(), punctuation={83: ':', 86: '.', 89: '.'},
                  time_columns=(82, 84, 85, 87, 88, 90, 91), pace_columns=(), age_columns=(),
                  column_characters=[DIGITS] * 12 + [LETTERS + "-.,'&"] * 32 + [DIGITS] * 6 + [LETTERS + "-.'&"] * 18
                  + [LETTERS] * 10 + [DIGITS] * 3 + [DIGITS + ':.'] * 12 + [DIGITS] * 10)
#the class codes, as the results' first page gives them
CLASS_CODES = {1: 'M 19-24', 2: 'M 25-29', 3: 'M 30-34', 4: 'M 35-39', 5: 'M 40-44', 6: 'M 45-49', 7: 'M 50-54',
               8: 'M 55-59', 9: 'M 60+', 10: 'F 19-24', 11: 'F 25-29', 12: 'F 30-34', 13: 'F 35-39', 14: 'F 40-44',
               15: 'F 45-49', 16: 'F 50-54', 17: 'F 55-59', 18: 'F 60+'}
SURNAME_FIRST = True
#the column headings above each page's table (and the article and class legend above page 3's)
TABLE_TOP = {3: 1300, 4: 274, 5: 352, 6: 248, 7: 211, 8: 248, 9: 280, 10: 181, 11: 359, 12: 201}
#the two finishers typed into the table after the printout (in a smaller face the glyphs can't be read in), each tied
#with the line above on time, place and class rank, as printed, and a line typed over page 5's in that face, tied with
#the line above on time and class rank. and as printed, three times the glyphs misplace or misread (one printed a
#column left of the rest, one after a speck, one with a broken 0), and the note under the table's end on page 12 and
#the rule under it, which are no results
HAND = {(7, 1, 822): {'name': 'DAVID C SUND', 'first': 'DAVID C', 'last': 'SUND', 'bib': '1187', 'age_group': 'M 25-29',
                      'class_rank': '311', 'city': 'MADISON', 'state': 'WI', 'country': 'USA', 'time': '4:54:33.10'},
        (9, 2, 1976): {'name': 'MARY BETH FRASCH', 'first': 'MARY BETH', 'last': 'FRASCH', 'bib': '2879',
                       'age_group': 'F 25-29', 'class_rank': '62', 'city': 'CUSTER', 'state': 'WI', 'country': 'USA',
                       'time': '5:58:39.70'},
        (5, 2, 4133): {'name': 'RICHARD W BESSER', 'first': 'RICHARD W', 'last': 'BESSER', 'bib': '1353',
                       'age_group': 'M 30-34', 'class_rank': '195', 'city': 'PORTAGE', 'state': 'WI', 'country': 'USA',
                       'time': '4:27:27.20'},
        (7, 2, 3244): {'time': '5:14:25'}, (10, 1, 3184): {'time': '6:17:22.60'}, (11, 2, 1703): {'time': '7:05:25.80'},
        (4, 1, 522): {'name': 'MED H BENNETT', 'first': 'MED H', 'last': 'BENNETT', 'age_group': 'M 50-54',
                      'class_rank': '4'},
        (7, 2, 221): {'name': 'JOE G MULHERAN', 'first': 'JOE G', 'last': 'MULHERAN', 'age_group': 'M 35-39',
                      'class_rank': '160'},
        (7, 2, 246): {'age_group': 'M 30-34', 'class_rank': '301'},
        (11, 1, 443): {'age_group': 'M 19-24', 'class_rank': '462'},
        (11, 1, 468): {'age_group': 'F 19-24', 'class_rank': '51'},
        (11, 1, 493): {'age_group': 'M 50-54', 'class_rank': '52'},
        (11, 1, 518): {'age_group': 'M 35-39', 'class_rank': '266'},
        (11, 1, 542): {'age_group': 'F 25-29', 'class_rank': '96'},
        (12, 1, 1665): {'age_group': 'M 19-24', 'class_rank': '502'},
        (12, 2, 2709): {'drop': True}, (12, 2, 2773): {'drop': True}}


def parse(year=YEAR):
    return line_printer.parse(year)


def ocr(year=YEAR):
    line_printer.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
