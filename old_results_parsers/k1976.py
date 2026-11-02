#1976's results booklet, pages 7-9: the 27.5 km "telemark citizens race" (the kortelopet by the champions list), for
#juniors and women, typed like the birkebeiner's pages 1-6 (y1976.py) and read the same way by class_lists.py: place,
#name (surname first), town, time (h:mm.ss.hh, most often), a skier's club on a line of its own below. its classes
#are boys 13 and under, 14-15 and 16 to 18 years 9 months, girls 13 and under, 14-15 and 16-20, elite women, and
#women 20-34 and 35 and over: age_group 'M -13', 'M 14-15', 'M 16-18', 'F -13', 'F 14-15', 'F 16-20', 'F elite',
#'F 20-34' and 'F 35+'. no man older than a junior raced it. each class was typed on its own, so the fields sit a
#little differently from class to class; each page's are set to fit all of its classes. a skier listed with a time
#but no place among the boys 14-15 (Mitch Larson) is listed again below as disqualified, as are five boys 16-18 with
#no time; none of them is kept. page 9 ends with a note on the 25 per cent club, which is no result. the 6th of women
#35 and over, Matilee Christman, is typed 3:10:01.94, between 3:16:56.53 and 3:19:18.46: the order of her class makes
#it 3:19:01.94. the 7th of women 20-34, Mary Oelrich, is typed 2:53:46.07, slower than the 8th's 2:50:08.99, and is
#kept as typed (so her class rank is out of order by time). three times' last digits, at the scan's right edge or
#misread, are set in HAND
import sys

from old_results_parsers import class_lists
from old_results_parsers.y1976 import YEAR, LINE_HEIGHT, LINE_PITCH, PITCH, NAME_ORDER, POINTS, SCALES

PAGES = [7, 8, 9]
TURN = {}
#the small turn (degrees counterclockwise) that makes each page's lines level
ANGLE = {7: 0.0, 8: -0.76, 9: 0.1}
#the columns' left and right edges, in pixels on the level page, and each field's in pixels from a column's left
COLUMNS = ((0, 1270), (1270, 2552))
PAGE_FIELDS = {
    7: [{'place': (0, 80), 'name': (80, 514), 'town': (514, 975), 'time': (975, 1270)},
        {'place': (0, 115), 'name': (115, 530), 'town': (530, 990), 'time': (990, 1282)}],
    8: [{'place': (0, 75), 'name': (75, 485), 'town': (485, 960), 'time': (960, 1270)},
        {'place': (0, 62), 'name': (62, 497), 'town': (497, 970), 'time': (970, 1282)}],
    9: [{'place': (0, 100), 'name': (100, 580), 'town': (580, 966), 'time': (966, 1270)},
        {'place': (0, 130), 'name': (130, 560), 'town': (560, 1015), 'time': (1015, 1282)}]}
FIELDS = PAGE_FIELDS[7]
#every time typed with hundredths
TIME_DIGITS = 7
#each class's heading: (page, its top, class), repeated atop the page the women 20-34 run on to
HEADINGS = [(7, 215, 'JB 13'), (7, 750, 'JB 14-15'), (7, 1366, 'JB 16-18'), (8, 106, 'JG 13'), (8, 515, 'JG 14-15'),
            (8, 1023, 'JG 16-20'), (8, 1736, 'EW'), (8, 2095, 'W 20-34'), (9, 132, 'W 20-34'), (9, 993, 'W 35+')]
#(gender, age class, race)
CLASSES = {'JB 13': ('M', 'M -13', 'kortie'), 'JB 14-15': ('M', 'M 14-15', 'kortie'),
           'JB 16-18': ('M', 'M 16-18', 'kortie'), 'JG 13': ('F', 'F -13', 'kortie'),
           'JG 14-15': ('F', 'F 14-15', 'kortie'), 'JG 16-20': ('F', 'F 16-20', 'kortie'),
           'EW': ('F', 'F elite', 'kortie'), 'W 20-34': ('F', 'F 20-34', 'kortie'), 'W 35+': ('F', 'F 35+', 'kortie')}
#by (page, column, the line's top): the note under the last class, last digits the scan's right edge cuts or that are
#misread, and names and towns tesseract misreads (a name and town typed run together)
HAND = {
    (9, 0, 1840): {'drop': True},
    (7, 1, 2055): {'time': '2:45:49.53'},
    (9, 1, 1263): {'time': '3:47:09.42'},
    (9, 1, 1417): {'name': 'DIEFSCHE, Ilse', 'time': '4:07:50.72'},
    (7, 0, 1482): {'town': 'Ah-gwah-ching, MN'},
    (8, 0, 229): {'name': 'KLUS, Kathy'},
    (8, 0, 1502): {'name': 'HARTMANN, Jeni'},
    (8, 0, 1587): {'name': 'BANOVETZ, Terry Ann', 'town': 'Minneapolis, MN'},
    (8, 0, 3100): {'name': 'WELDNER, Carol'},
    (8, 1, 2364): {'name': 'RIEMER, Boni'},
}


def parse(year=YEAR):
    return class_lists.parse(year, 'kortie')


def ocr(year=YEAR):
    class_lists.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
