#1973's results, pages 3-5: the 22 km race from seeley to telemark (the kortelopet by the champions list), typed on
#finishing sheets like the birkebeiner's pages 1 and 2 (y1973.py) and read the same way by class_lists.py: place (1st,
#2nd...), name, time (h:mm:ss), a class to a page: men under 20 ('M -19'), women 32 and older ('F 32+') and women 20 to
#31 ('F 20-31'). no town is printed. the scan is speckled about the women's first lines, and a pen line runs through
#Kevin Sande's surname and on past it (his name is set in HAND; he's kept, his time as clear as the rest)
import sys

from old_results_parsers import class_lists
from old_results_parsers.y1973 import YEAR, LINE_HEIGHT, LINE_PITCH, PITCH, TIME_DIGITS, NAME_ORDER, SCALES

PAGES = [3, 4, 5]
TURN = {}
#the small turn (degrees counterclockwise) that makes each page's lines level
ANGLE = {3: 0.06, 4: -0.16, 5: 0.34}
#each page's column's left and right edges, in pixels on the level page, and each field's in pixels from its left
PAGE_COLUMNS = {3: ((250, 1650),), 4: ((350, 1750),), 5: ((350, 1750),)}
FIELDS = {'place': (0, 290), 'name': (290, 900), 'time': (900, 1400)}
#each class's heading ("Finishing Sheet - Men under 20 - Seeley-Telemark - 22 km."): (page, its top, class), below the
#page's title
HEADINGS = [(3, 943, 'M -19'), (4, 793, 'F 32+'), (5, 826, 'F 20-31')]
TABLE_TOP = {3: 943, 4: 793, 5: 826}
#(gender, age class, race)
CLASSES = {'M -19': ('M', 'M -19', 'kortie'), 'F 32+': ('F', 'F 32+', 'kortie'), 'F 20-31': ('F', 'F 20-31', 'kortie')}
#by (page, column, the line's top): the name the pen's line runs through
HAND = {(3, 0, 1446): {'name': 'Kevin Sande'}}


def parse(year=YEAR):
    return class_lists.parse(year, 'kortie')


def ocr(year=YEAR):
    class_lists.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
