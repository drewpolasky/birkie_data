#1988 birch scroll: the kortelopet results are pages 38-41 (men; page 41's second and third blocks stop at a photo) and
#42-44 (women; each block of page 44 stops at a photo), printed on the birkebeiner's line printer (y1988.py) and read
#the same way. its table has no 25% column: the state, zip and country sit a column right of the birkebeiner's, the
#class and class rank three, and the pace where it was. its classes are the birkebeiner's with the juniors' (13-14,
#15-16, 17-18), 19-24 in place of 18-24. the PACE column is the time over 29 km
import sys

from old_results_parsers import line_printer
from old_results_parsers.line_printer import DIGITS, LETTERS
from old_results_parsers.y1988 import YEAR, TURN, FIRST_BLOCK

PAGES = {**{p: 'M' for p in range(38, 42)}, **{p: 'F' for p in range(42, 45)}}
ANGLE = {38: -0.01, 39: -0.52, 40: 0.05, 41: -1.21, 42: 0.21, 43: -1.27, 44: 0.19}
PACE_KM = 29
AGES = ('13-14', '15-16', '17-18', '19-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64',
        '65-69', '70+')
#the kortelopet's table on 1988-1991's line printer, which is 1991's birkebeiner table left of the state
TABLE = dict(
    ages=AGES,
    fields={'rank': (2, 7), 'sex': (9, 12), 'time': (13, 25), 'bib': (25, 31), 'name': (31, 57), 'town': (57, 74),
            'st': (74, 78), 'zip': (78, 85), 'nat': (85, 90), 'cls': (90, 97), 'crank': (97, 103),
            'pace': (103, 111)},
    sex_columns=(10, 91), age_columns=(92, 93, 95, 96), pace_columns=(104, 105, 107, 108),
    column_characters=([DIGITS] * 9 + ['MF'] * 3 + [DIGITS + ':.'] * 13 + [DIGITS] * 6 + [LETTERS + "-.'&"] * 43
                       + [LETTERS] * 4 + [LETTERS + DIGITS] * 7 + [LETTERS] * 5
                       + [LETTERS] + ['MF'] + [DIGITS] * 2 + ['-+'] + [DIGITS] * 2
                       + [DIGITS] * 6 + [DIGITS + ':'] * 9))
#a line counting from 12 pixels high, as for the birkebeiner
PRINTER = line_printer.Printer(line_height=(12, 24), **TABLE)


def parse(year=YEAR):
    return line_printer.parse(year, 'kortie')


def ocr(year=YEAR):
    line_printer.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
