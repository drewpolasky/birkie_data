#1977's results: the timing company's printout ("official teletime standings"), a class to a run of pages, read by
#class_lists.py: place, name (surname first: ARVNES,BJORN), BIB, CITY (cut to 12 or so letters), STE, CNTRY, CLUB,
#TIME (h:mm:ss.hh) and 25% ("*"). classes 1-5 are men 19-34, 35-42, 43-49, 50-56 and 57 and over, 6 and 7 women 19-34
#and 35 and over, as written in by hand on the scan. pages 13, 17 and 24 hold the end of one sheet above the start of
#the next, each under its class's heading; page 22 is printed larger than the rest. page 1 is the cover
import sys

from old_results_parsers import class_lists

YEAR = 1977
PAGES = list(range(2, 26))
TURN = {}
#the small turn (degrees counterclockwise) that makes each page's lines level
ANGLE = {2: -0.45, 3: 0.07, 4: 0.02, 5: -0.75, 6: 0.07, 7: 0.03, 8: 0.6, 9: 0.09, 10: 0.6, 11: 0.47, 12: 0.45, 13: 0.53,
         14: -0.06, 15: 0.53, 16: 0.1, 17: 0.12, 18: 0.12, 19: -0.35, 20: 0.43, 21: 0.07, 22: 0.1, 23: 0.07, 24: 0.07,
         25: 0.09}
#page 22, shrunk to the others' size
SCALE = {22: 0.836}
#one column a page, its fields' left and right edges in pixels on the level page
COLUMNS = ((0, 2552),)
FIELDS = {'place': (120, 285), 'name': (285, 820), 'bib': (820, 925), 'town': (925, 1360), 'st': (1360, 1430),
          'nat': (1430, 1620), 'club': (1620, 1830), 'time': (1830, 2160)}
#where each page's NAME heading starts across: the printout sits up to 40 pixels further right on some pages, and its
#fields with it
NAME_AT = {2: 424, 3: 438, 4: 439, 5: 430, 6: 445, 7: 460, 8: 466, 9: 453, 10: 453, 11: 460, 12: 461, 13: 445, 14: 424,
           15: 453, 16: 447, 17: 435, 18: 445, 19: 434, 20: 439, 21: 450, 22: 420, 23: 429, 24: 437, 25: 435}
PAGE_FIELDS = {p: {f: (a + x - 424, b + x - 424) for f, (a, b) in FIELDS.items()} for p, x in NAME_AT.items()}
#a line's ink in pixels high, least and most, the pixels from one line to the next, and a character's width
LINE_HEIGHT = (12, 34)
LINE_PITCH = 42
PITCH = 25.3
TIME_DIGITS = 7
NAME_ORDER = 'last'
#tesseract reads the printer's capitals badly: a name word not seen in the clean results is taken as the one it's
#clearly nearest
NEAR_NAMES = True
SCALES = (1.5, 2)
#each sheet's heading ("CLASS 1 OFFICIAL TELETIME STANDINGS"): (page, its top, class), four lines high with the column
#headings, and the pages' tops above it, but where the sheet before it ends above it
HEADING_LINES = 4
HEADINGS = [(2, 204, 'C1'), (3, 180, 'C1'), (4, 160, 'C1'), (5, 171, 'C1'), (6, 275, 'C1'), (7, 164, 'C1'), (8, 198,
            'C1'), (9, 193, 'C1'), (10, 184, 'C1'), (11, 219, 'C1'), (12, 272, 'C1'), (13, 848, 'C1'), (14, 210,
            'C2'), (15, 201, 'C2'), (16, 543, 'C2'), (17, 1416, 'C2'), (18, 201, 'C3'), (19, 218, 'C3'), (20, 191,
            'C4'), (21, 557, 'C4'), (22, 142, 'C5'), (23, 615, 'C6'), (24, 1898, 'C6'), (25, 442, 'C7')]
TABLE_TOP = {2: 204, 3: 180, 4: 160, 5: 171, 6: 275, 7: 164, 8: 198, 9: 193, 10: 184, 11: 219, 12: 272, 14: 210, 15:
             201, 16: 543, 18: 201, 19: 218, 20: 191, 21: 557, 22: 142, 23: 615, 25: 442}
#(gender, age class, race)
CLASSES = {'C1': ('M', 'M 19-34', 'birkie'), 'C2': ('M', 'M 35-42', 'birkie'), 'C3': ('M', 'M 43-49', 'birkie'),
           'C4': ('M', 'M 50-56', 'birkie'), 'C5': ('M', 'M 57+', 'birkie'), 'C6': ('F', 'F 19-34', 'birkie'),
           'C7': ('F', 'F 35+', 'birkie')}
#(page, column, the line's top): what's printed, where the reading is moved to a known name or town that isn't it (L
#CROSSE, written out, would lose its L as a speck)
HAND = {(6, 0, 1784): {'name': 'BERG, SVEIN PETTER'}, (6, 0, 2558): {'name': 'FEHLANDT, WILLIAM'},
        (15, 0, 2137): {'town': 'La Crosse, WI'}, (20, 0, 1444): {'name': 'BRUUN, RAGNAR'}}


def parse(year=YEAR):
    return class_lists.parse(year)


def ocr(year=YEAR):
    class_lists.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
