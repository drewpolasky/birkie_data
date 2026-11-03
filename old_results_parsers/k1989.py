#1989 birch scroll: the kortelopet results are pages 39-43 (men; page 43 has one block, beside photos) and 44-46
#(women), printed and read as 1988's (k1988.py). the PACE column is the time over 29 km
import sys

import numpy as np

from old_results_parsers import line_printer
from old_results_parsers.k1988 import TABLE
from old_results_parsers.y1989 import YEAR, TURN, FIRST_BLOCK

PAGES = {**{p: 'M' for p in range(39, 44)}, **{p: 'F' for p in range(44, 47)}}
ANGLE = {39: -0.99, 40: -0.42, 41: -1.2, 42: -0.87, 43: -1.4, 44: -0.66, 45: -1.09, 46: -0.63}
PACE_KM = 29
#1988's, but the foot of pages 40 and 42 is printed wider (up to 8.96 pixels a character), where a line's pitch, taken
#from the lines around it, can leave it short of its anchor: such a line tries the other pitches. the network reads
#the Y as T (POLLT, GART, STURGEON BAT)
PRINTER = line_printer.Printer(line_height=(12, 24), anchor_pitch=True, pitches=np.arange(8.62, 9.02, 0.002),
                               swapped={'T': 'Y'}, **TABLE)
#two women on page 46's second block aren't found as lines, one printed in italics and one with a five-digit bib, so
#they're set from the scan. the women's list prints a zip but no state
UNFOUND = {('F', 569): {'bib': '9062', 'name': 'ROXANNE A ANDERSON', 'age_group': 'F 55-59', 'class_rank': '10',
                        'city': 'QUINNESEC', 'state': 'MI', 'country': 'USA', 'time': '4:39:24.5'},
           ('F', 574): {'bib': '10147', 'name': 'NANCY A MATHEWS', 'age_group': 'F 30-34', 'class_rank': '145',
                        'city': 'CEDARBURG', 'state': 'WI', 'country': 'USA', 'time': '4:41:33.8'}}


def parse(year=YEAR):
    return line_printer.parse(year, 'kortie')


def ocr(year=YEAR):
    line_printer.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
