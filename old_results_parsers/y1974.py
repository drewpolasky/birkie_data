#1974's results: typewritten finishing sheets, a class to a page or less, read by class_lists.py: place (1st, 2nd...),
#name, time (h:mm:ss). pages 1-4 are the birkebeiner (50 km), men 20-34, 35-42, 43-49 and 50 and over; pages 5-7 the
#24 km race for women and juniors. Jacque Lindskoog, the women's champion, is listed 18th of men 20-34. a skier with
#no time (Aandar Haakon) is left out. John Gannett's time is typed 5:58:68, which the order of his class makes 5:58:08
import sys

from old_results_parsers import class_lists

YEAR = 1974
PAGES = [1, 2, 3, 4]
TURN = {}
#the small turn (degrees counterclockwise) that makes each page's lines level
ANGLE = {1: 0.08, 2: 0.07, 3: 0.06, 4: 0.05}
#the column's left and right edges, in pixels on the level page, and each field's in pixels from its left
COLUMNS = ((250, 2000),)
FIELDS = {'place': (0, 230), 'name': (230, 1250), 'time': (1250, 1650)}
#a line's ink in pixels high, least and most, the pixels from one line to the next (typed a line and a half apart, or
#more), and a character's width (elite)
LINE_HEIGHT = (14, 55)
LINE_PITCH = 75
PITCH = 25.5
TIME_DIGITS = 5
NAME_ORDER = 'first'
SCALES = (1, 1.5)
#each class's heading: (page, its top, class), below the page's title
HEADINGS = [(1, 295, 'M 20-34'), (2, 480, 'M 35-42'), (3, 530, 'M 43-49'), (4, 485, 'M 50+')]
TABLE_TOP = {1: 295, 2: 480, 3: 530, 4: 485}
#(gender, age class, race)
CLASSES = {'M 20-34': ('M', 'M 20-34', 'birkie'), 'M 35-42': ('M', 'M 35-42', 'birkie'),
           'M 43-49': ('M', 'M 43-49', 'birkie'), 'M 50+': ('M', 'M 50+', 'birkie')}
#by (page, column, the line's top): the women's champion, among the men
HAND = {(1, 0, 1692): {'gender': 'F', 'age_group': ''}}


def parse(year=YEAR):
    return class_lists.parse(year)


def ocr(year=YEAR):
    class_lists.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
