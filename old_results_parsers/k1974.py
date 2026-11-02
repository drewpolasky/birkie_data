#1974's results, pages 5-7: the 24 km race for women and juniors (the kortelopet by the champions list), typed on
#finishing sheets like the birkebeiner's pages 1-4 (y1974.py) and read the same way by class_lists.py: place (1st,
#2nd...), name, time (h:mm:ss). each class has a sheet of its own, under the race's title and "FINISHING SHEET", page 5
#holding three: women 43-49 ('F 43-49'), 20-34 ('F 20-34') and 35-42 ('F 35-42'), then junior women ('F -19') and
#junior men 19 and under ('M -19'). no town is printed. the men's winner's time is typed 1:6:50, a digit short
#(1:06:50 by the champions list). the scan has specks either side of some lines, and a mark just before a time on
#pages 5 and 6
import sys

from old_results_parsers import class_lists
from old_results_parsers.y1974 import YEAR, LINE_HEIGHT, LINE_PITCH, PITCH, TIME_DIGITS, NAME_ORDER, SCALES

PAGES = [5, 6, 7]
TURN = {}
#the small turn (degrees counterclockwise) that makes each page's lines level
ANGLE = {5: 0.08, 6: 0.02, 7: 0.08}
#the column's left and right edges, in pixels on the level page, and each field's in pixels from its left
COLUMNS = ((250, 2000),)
FIELDS = {'place': (0, 300), 'name': (300, 1280), 'time': (1280, 1700)}
#each class's sheet: (page, the top of the race's title, class), three lines high with "FINISHING SHEET" and the
#class's name
HEADING_LINES = 3
HEADINGS = [(5, 221, 'F 43-49'), (5, 992, 'F 20-34'), (5, 2410, 'F 35-42'), (6, 236, 'F -19'), (7, 199, 'M -19')]
#(gender, age class, race)
CLASSES = {'F 43-49': ('F', 'F 43-49', 'kortie'), 'F 20-34': ('F', 'F 20-34', 'kortie'),
           'F 35-42': ('F', 'F 35-42', 'kortie'), 'F -19': ('F', 'F -19', 'kortie'), 'M -19': ('M', 'M -19', 'kortie')}
#by (page, column, the line's top): the time typed a digit short, and a 4 read as a 3 (the typewriter's 4 reads as
#almost anything)
HAND = {(7, 0, 500): {'time': '1:06:50'},
        (6, 0, 592): {'time': '1:47:40'}}


def parse(year=YEAR):
    return class_lists.parse(year, 'kortie')


def ocr(year=YEAR):
    class_lists.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
