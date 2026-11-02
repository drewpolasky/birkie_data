#1981 birch scroll, pages 21-24: the "telemark kortelopet" (24.5 km by the champions list), typeset class by class
#under headings in two columns a page, read by class_lists.py like 1973-1977's lists: place in the class, NAME (surname
#first), BIB, HOMETOWN (town, state and country: "River Falls, WI USA"), TIME (h:mm:ss.t) and CLASS (1-8, as the
#heading). its classes: boys 13-14, 15-16 and 17-18 and novice men 19 and over, girls 13-14, 15-16 and 17-18 and
#novice women 19 and over ('M 13-14', 'M 15-16', 'M 17-18', 'M 19+', 'F 13-14' ... 'F 19+'). the novice men's places
#are printed on from the boys 17-18's, 60 to 272 (their 60th is 2 seconds behind the boys' winner, the race's), so
#their class rank is counted from 1. the novice women's 200th has a bib and time but no name (page 24), and is kept
#without one. some towns are printed misspelt or with the wrong state (Brookfeild, Vriginia, "West Bend, IN",
#"Cambridge, QI"), and kept so
import sys

from old_results_parsers import class_lists

YEAR = 1981
PAGES = [21, 22, 23, 24]
TURN = {}
#the small turn (degrees counterclockwise) that makes each column's lines level, left column then right
ANGLE = {21: (0.7, 0.58), 22: (-0.58, -0.7), 23: (0.24, 0.0), 24: (0.0, 0.0)}
#the columns' left and right edges, in pixels on the level page
PAGE_COLUMNS = {21: ((150, 1320), (1320, 2552)), 22: ((150, 1290), (1290, 2552)), 23: ((150, 1290), (1290, 2552)),
                24: ((150, 1290), (1290, 2552))}


def fields(name, bib, town, time, cls, end):
    #a column's fields from where its name, bib, town, time and class start, in pixels from its left
    return {'place': (0, name - 10), 'name': (name - 10, bib - 10), 'bib': (bib - 10, town - 10),
            'town': (town - 10, time - 10), 'time': (time - 10, cls - 15), 'cls': (cls - 15, end)}


#where each column's NAME, BIB, HOMETOWN, TIME and CLASS headings start
PAGE_FIELDS = {21: [fields(111, 432, 523, 924, 1095, 1170), fields(92, 429, 520, 921, 1090, 1232)],
               22: [fields(104, 426, 517, 918, 1088, 1140), fields(129, 453, 543, 945, 1113, 1262)],
               23: [fields(110, 419, 510, 912, 1081, 1140), fields(127, 436, 527, 929, 1098, 1262)],
               24: [fields(113, 434, 525, 925, 1094, 1140), fields(143, 457, 548, 948, 1116, 1262)]}
FIELDS = PAGE_FIELDS[21][0]
#a line's ink in pixels high, least and most, the pixels from one line to the next, and a character's width
LINE_HEIGHT = (12, 34)
LINE_PITCH = 31
PITCH = 14.7
TIME_DIGITS = 6
NAME_ORDER = 'last'
SCALES = (1.5, 2)
#a hometown is followed by its country
TOWN_COUNTRY = True
COLUMN_ORDER = [(21, 0), (21, 1), (22, 0), (22, 1), (23, 0), (23, 1), (24, 0), (24, 1)]
#each class's heading: (page, column, its top, class), the column headings below it no result. None ends a column's
#class above the next heading's big type
HEADING_LINES = 0.2
HEADINGS = [(21, 0, 370, 'B 13'), (21, 0, 2180, None), (21, 0, 2250, 'B 15'), (21, 1, 1200, None),
            (21, 1, 1270, 'B 17'), (22, 0, 240, None), (22, 0, 360, 'NM'), (23, 0, 1120, None), (23, 0, 1185, 'G 13'),
            (23, 0, 1750, None), (23, 0, 1815, 'G 15'), (23, 0, 2355, None), (23, 0, 2420, 'G 17'), (23, 1, 190, None),
            (23, 1, 310, 'NW')]
#(page, column): the pixel row the lists start below, under the page's title and column headings
TABLE_TOP = {(21, 1): 310, (22, 0): 360, (22, 1): 140, (23, 0): 140, (23, 1): 310, (24, 0): 150, (24, 1): 145}
#(gender, age class, race)
CLASSES = {'B 13': ('M', 'M 13-14', 'kortie'), 'B 15': ('M', 'M 15-16', 'kortie'), 'B 17': ('M', 'M 17-18', 'kortie'),
           'NM': ('M', 'M 19+', 'kortie'), 'G 13': ('F', 'F 13-14', 'kortie'), 'G 15': ('F', 'F 15-16', 'kortie'),
           'G 17': ('F', 'F 17-18', 'kortie'), 'NW': ('F', 'F 19+', 'kortie')}
#the line with no name: too little ink where the place and name are to be found
EXTRA_LINES = {(24, 1): [(591, 609)]}
#by (page, column, the line's top): a line whose place is too faint to find, and names and towns tesseract misreads
HAND = {
    (23, 0, 1377): {'result': True},
    (22, 1, 2787): {'name': 'Marineau, Stephen C.'},
    (22, 1, 1501): {'name': 'Weyland, Chris M.'},
    (23, 1, 506): {'name': 'Fjelstad, Diane M.'},
    (22, 1, 1624): {'town': 'Long Prairie, MN'},
    (23, 0, 774): {'town': 'Glenwood City, WI'},
}


def parse(year=YEAR):
    return class_lists.parse(year, 'kortie')


def ocr(year=YEAR):
    class_lists.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
