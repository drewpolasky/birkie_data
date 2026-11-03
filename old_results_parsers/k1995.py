#1995 birch scroll: "MEN'S HERITAGE BANK OF HAYWARD KORTELOPET RESULTS" on pages 56-60 (places 1-1020; page 60's right
#column stops at 1020, above a photo) and "WOMEN'S ..." on pages 61-64 (places 1-746; page 64's columns stop at 703 and
#746, above an advertisement), right after the birkebeiner's and typeset the same way, so y1995.py reads them (ocr()
#straightens and reads each page and column as it does the birkebeiner's). its table has no 25% column and sets its
#columns further apart from the FINAL TIME column; the class is printed with a space ('M 25-29'), and its classes start
#with the juniors' (13-14, 15-16, 17-18), then 19-24 in place of 18-24. its bibs are five figures (a few skiers wear
#birkebeiner bibs, '9044'), printed left aligned, where a 1 after a 1 can stand 7 blank pixels off. its PACE MN/KM is
#the time over 25 km (the champions list gives the race as 26 km, but the paces fit 25), with two figures for the
#minutes from 10 on ('10.05')
import sys

from old_results_parsers import y1995
from old_results_parsers.y1995 import YEAR

TABLE = dict(
    LISTS={'M': range(56, 61), 'F': range(61, 65)},
    #each page's tilt, found by the sharpest row profile as for the birkebeiner's
    SKEW={56: -0.1, 57: -1.55, 58: 0.1, 59: 0.25, 60: -0.5, 61: -0.35, 62: -0.35, 63: -1.15, 64: -0.55},
    #as offsets from the left edge of the FINAL TIME column, in the straightened page's pixels: each field's start (by
    #its words' middles), the column crops OCR reads, and where the scan's figures and words are cut from
    COLUMNS=[('rank', -130), ('time', -12), ('bib', 90), ('name', 155), ('town', 474), ('st', 706), ('nat', 748),
             ('cls', 800), ('crank', 900), ('pace', 957), ('end', 1045)],
    CROPS=[('c3', 3, -150, 1045, True), ('n2', 2, 155, 706, False)],
    NUMBER_BANDS={'rank': (-135, -10), 'time': (-20, 75), 'bib': (75, 158), 'crank': (895, 958), 'pace': (958, 1035)},
    WORD_BANDS={'name': (158, 474), 'city': (474, 706), 'state': (706, 745)},
    CLASSES=['13-14', '15-16', '17-18', '19-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64',
             '65-69', '70+'],
    DISTANCE_KM=25,
    PACE_MINUTES=r'1?\d',
    BIB_GAP=8)


def parse(year=YEAR):
    return y1995.parse(year, 'kortie', TABLE)


def ocr(year=YEAR):
    y1995.ocr(year, 'kortie', TABLE)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
