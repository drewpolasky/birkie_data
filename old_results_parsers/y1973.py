#1973's results: typewritten finishing sheets, a class to a page, read by class_lists.py: place (1st, 2nd...), name,
#time (h:mm:ss). pages 1 and 2 are the birkebeiner from hayward to telemark (48 km), men 32 and over and men 20 to 31,
#with three 17-year-olds unnumbered below; pages 3-5 the 22 km race from seeley, for men under 20 and for women. a
#skier with no time (Charles Woydt, Terry Marshall: "No Time") has no place either, and is left out
import sys

from old_results_parsers import class_lists

YEAR = 1973
PAGES = [1, 2]
TURN = {}
#the small turn (degrees counterclockwise) that makes each page's lines level
ANGLE = {1: 0.4, 2: -0.05}
#each page's column's left and right edges, in pixels on the level page, and each field's in pixels from its left
PAGE_COLUMNS = {1: ((250, 1550),), 2: ((330, 1700),)}
PAGE_FIELDS = {1: {'place': (0, 230), 'name': (230, 900), 'time': (900, 1250)},
               2: {'place': (0, 230), 'name': (230, 920), 'time': (920, 1300)}}
#a line's ink in pixels high, least and most, the pixels from one line to the next (typed double spaced), and a
#character's width (pica)
LINE_HEIGHT = (14, 60)
LINE_PITCH = 100
PITCH = 30
TIME_DIGITS = 5
NAME_ORDER = 'first'
#the type is big enough that tesseract reads it best as it is
SCALES = (1, 1.5)
#each class's heading: (page, its top, class), page 2's below its title
HEADINGS = [(1, 870, 'M 32+'), (2, 810, 'M 20-31'), (2, 2560, 'M 17')]
TABLE_TOP = {2: 810}
#(gender, age class, race)
CLASSES = {'M 32+': ('M', 'M 32+', 'birkie'), 'M 20-31': ('M', 'M 20-31', 'birkie'), 'M 17': ('M', 'M 17', 'birkie')}
#classes printed without places
UNNUMBERED = {'M 17'}
#by (page, column, the line's top): the last man's time, written in by hand
HAND = {(1, 0, 2811): {'time': '6:34:07'}}


def parse(year=YEAR):
    return class_lists.parse(year)


def ocr(year=YEAR):
    class_lists.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
