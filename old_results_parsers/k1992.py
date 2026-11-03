#1992 birch scroll: the kortelopet results are pages 46-51 (men, places 1-1046, ending with the first run of rows at the
#top of page 51) and 51-54 (women, 1-752, under their own title on page 51; page 54's second column stops at a photo),
#printed in the birkebeiner's fixed-pitch font and read the same way, by y1992.py. its table has no 25% column and its
#bib column is a character wider (up to five digits): the name, hometown and state sit a character right of the
#birkebeiner's, the class and class rank two, and the pace a character left, with room for a pace of ten minutes or
#more. its classes are the birkebeiner's with the juniors' (13-14, 15-16, 17-18), 19-24 in place of 18-24. the PACE
#column is the time over 26 km, every row of it (the champions list gives the race as 29 km)
import sys

from old_results_parsers import y1992
from old_results_parsers.y1992 import YEAR

PAGES = range(46, 55)
#the lists' sizes, from the last places printed (1046 on page 51, 752 on page 54)
LIST_SIZES = {'M': 1046, 'F': 752}
#the women's list starts with the second run of rows on page 51
WOMEN_FROM = (51, 1)
COURSE_KM = 26
#each field's characters, counted from the time's first (k = 0)
FIELDS = {'rank': (-12, -9), 'cls': (-7, -3), 'time': (0, 8), 'bib': (11, 15), 'name': (17, 42), 'city': (43, 59),
          'state': (60, 62), 'country': (63, 67), 'class': (69, 74), 'class_rank': (76, 79), 'pace': (82, 86)}
#the PACE column's digits: the tens of minutes' (for a pace of ten minutes or more), the minutes' and the seconds' two
PACE = (82, 83, 85, 86)
AGES = ('13-14', '15-16', '17-18', '19-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64',
        '65-69', '70+')
#none of the kortelopet's pages was turned upside down
UPSIDE_DOWN = []


def parse(year=YEAR):
    return y1992.parse(year, 'kortie')


def ocr(year=YEAR):
    y1992.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
