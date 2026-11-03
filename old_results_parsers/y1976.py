#1976's results booklet: typewritten pages, each class under a heading in two columns (its first half down the left,
#the rest down the right), read by class_lists.py: place, name (surname first, "HARJU, Dave"), town ("Minneapolis,
#MN"), time (h:mm.ss.hh, or with tenths only, or h:mm:ss.hh), and many a skier's club on a line of its own below. pages
#1-6 are the birkebeiner (55 km by its page 1, 53 by the champions list), its touring classes then its elite ones;
#pages 7-9 the 27.5 km citizens race
import sys

from old_results_parsers import class_lists

YEAR = 1976
PAGES = [1, 2, 3, 4, 5, 6]
TURN = {}
#the small turn (degrees counterclockwise) that makes each page's lines level
ANGLE = {1: 0.02, 2: -0.1, 3: 0.04, 4: 0.04, 5: 0.07, 6: 0.05}
#the columns' left and right edges, in pixels on the level page, and each field's in pixels from a column's left
COLUMNS = ((0, 1270), (1270, 2552))
FIELDS = [{'place': (0, 85), 'name': (85, 560), 'town': (560, 940), 'time': (940, 1270)},
          {'place': (0, 110), 'name': (110, 520), 'town': (520, 980), 'time': (980, 1282)}]
#page 6's right column ends at a dotted rule
PAGE_FIELDS = {6: [FIELDS[0], {**FIELDS[1], 'time': (980, 1222)}]}
#a line's ink in pixels high, least and most, the pixels from one line to the next, and a character's width
LINE_HEIGHT = (12, 34)
LINE_PITCH = 38.6
PITCH = 19.4
TIME_DIGITS = (6, 7)
NAME_ORDER = 'last'
#the typist put a point after every initial
POINTS = True
SCALES = (1.5, 2)
#each class's heading: (page, its top, class), repeated atop a page the class runs on to
HEADINGS = [(1, 575, 'TM 19-34'), (2, 115, 'TM 19-34'), (3, 2440, 'TM 35-42'), (4, 15, 'TM 35-42'),
            (4, 2268, 'TM 43-49'), (5, 15, 'TM 50-56'), (5, 870, 'TM 57+'), (5, 1150, 'TW 20-34'), (5, 1916, 'TW 35+'),
            (5, 2340, 'EM 19-20'), (5, 2589, 'EM 20+'), (6, 30, 'EM 20+'), (6, 461, 'EV 25-34'),
            (6, 1398, 'EV 35-44'), (6, 2160, 'EV 45-54'), (6, 2546, 'EV 55+'), (6, 2808, 'EW')]
#(gender, age class, race). the touring classes' youngest are 18 years 9 months, as are the elite women and the elite
#juniors
CLASSES = {'TM 19-34': ('M', 'M 19-34', 'birkie'), 'TM 35-42': ('M', 'M 35-42', 'birkie'),
           'TM 43-49': ('M', 'M 43-49', 'birkie'), 'TM 50-56': ('M', 'M 50-56', 'birkie'),
           'TM 57+': ('M', 'M 57+', 'birkie'), 'TW 20-34': ('F', 'F 20-34', 'birkie'),
           'TW 35+': ('F', 'F 35+', 'birkie'),
           'EM 19-20': ('M', 'M elite 19-20', 'birkie'), 'EM 20+': ('M', 'M elite 20+', 'birkie'),
           'EV 25-34': ('M', 'M elite 25-34', 'birkie'), 'EV 35-44': ('M', 'M elite 35-44', 'birkie'),
           'EV 45-54': ('M', 'M elite 45-54', 'birkie'), 'EV 55+': ('M', 'M elite 55+', 'birkie'),
           'EW': ('F', 'F elite', 'birkie')}
#by (page, column, the line's top): lines typed askew, their towns and times half a line off their names, so that a
#line's town and time sit on the line above's or below's (as typed), and a line with no place
HAND = {
    (4, 0, 1068): {'town': 'Minneapolis, MN', 'time': '4:58:30.77'},
    (4, 0, 1107): {'town': 'Ontonagon, MI', 'time': '4:59:45.57'},
    (6, 1, 118): {'town': 'Bloomington, MN', 'time': '3:45:26.27'},
    (6, 1, 196): {'town': 'Houghton, Mich.', 'time': '3:57:20.87'},
    (6, 1, 225): {'town': 'Winnipeg, Man.', 'time': '3:58:07.32'},
    (6, 1, 265): {'town': 'Duluth, MN', 'time': '3:58:59.89'},
    (6, 1, 343): {'town': 'Chicago, IL', 'time': '4:04:34.76'},
    (6, 0, 2636): {'result': True},
}


def parse(year=YEAR):
    return class_lists.parse(year)


def ocr(year=YEAR):
    class_lists.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
