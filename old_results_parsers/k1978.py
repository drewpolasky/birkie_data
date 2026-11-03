#1978 birch scroll, pages 27-32: the "kortelopet results" (26 km by the champions list), typeset class by class
#under big italic headings and read by class_lists.py like 1973-1977's lists: POS. (the place in the class), NAME
#(surname first), ADDRESS (town and state, or a foreign town and its country: "Oslo, NOR", "Norway"), TOTAL TIME
#(h:mm:ss.hh, most of the novice men's typed h:mm:ss:hh). each magazine page is scanned in two halves, its top (27, 29,
#31) and its foot (28, 30, 32), so a column runs on from one scan into the next: the novice women 19 and over ('F
#19+') down the left columns of 27 and 28, the right ones, and page 29's left; the novice men 19 and over ('M 19+')
#down page 30's left column (their heading is at the foot of 29's), then 29's right and 30's right; then the juniors
#on 31 and 32: girls 17 & 18, boys 17 & 18 (on down 32's left), girls 15 & 16, boys 15 & 16, girls 13 & 14 (on down
#32's right) and boys 13 & 14 ('F 17-18', 'M 17-18', 'F 15-16', 'M 15-16', 'F 13-14', 'M 13-14'). each list was typed
#on its own and pasted up, so each column sits at its own slant and tab stops. a black band where the halves meet
#shades a line or two at the foot of 27 and 31 and the head of 28 and 32, and loses four (the novice women's 9th, 10th
#and 92nd, the girls 13 & 14's 7th: counted in the class ranks after them); those it shades are read by eye (HAND), as
#is a line at the head of 30 (the novice men's 119th, John Neal of Stoughton, whose time is lost). the novice men's
#32nd is printed with no name, only a number (3495, a bib?), and kept without one
import sys

from old_results_parsers import class_lists

YEAR = 1978
PAGES = [27, 28, 29, 30, 31, 32]
TURN = {}
#the small turn (degrees counterclockwise) that makes each column's lines level, left column then right
ANGLE = {27: (0.16, 0.82), 28: (0.5, 0.84), 29: (0.46, -0.18), 30: (-0.96, -1.02), 31: (0.85, 0.88), 32: (0.75, 0.6)}
#the columns' left and right edges, in pixels on the level page, and each field's in pixels from a column's left
PAGE_COLUMNS = {27: ((250, 1650), (1650, 3304)), 28: ((250, 1650), (1650, 3304)), 29: ((120, 1600), (1600, 3304)),
                30: ((120, 1600), (1600, 3304)), 31: ((120, 1600), (1600, 3304)), 32: ((120, 1600), (1600, 3304))}
PAGE_FIELDS = {
    27: [{'place': (0, 180), 'name': (180, 595), 'town': (595, 1040), 'time': (1040, 1350)},
         {'place': (0, 202), 'name': (202, 680), 'town': (680, 1095), 'time': (1095, 1400)}],
    28: [{'place': (0, 175), 'name': (175, 580), 'town': (580, 1037), 'time': (1037, 1350)},
         {'place': (0, 175), 'name': (175, 585), 'town': (585, 1046), 'time': (1046, 1350)}],
    29: [{'place': (0, 160), 'name': (160, 583), 'town': (583, 997), 'time': (997, 1380)},
         {'place': (0, 140), 'name': (140, 550), 'town': (550, 1022), 'time': (1022, 1350)}],
    30: [{'place': (0, 144), 'name': (144, 540), 'town': (540, 985), 'time': (985, 1330)},
         {'place': (0, 175), 'name': (175, 580), 'town': (580, 1045), 'time': (1045, 1350)}],
    31: [{'place': (0, 230), 'name': (230, 620), 'town': (620, 1070), 'time': (1070, 1400)},
         {'place': (0, 312), 'name': (312, 715), 'town': (715, 1125), 'time': (1125, 1450)}],
    32: [{'place': (0, 200), 'name': (200, 620), 'town': (620, 1048), 'time': (1048, 1340)},
         {'place': (0, 290), 'name': (290, 700), 'town': (700, 1100), 'time': (1100, 1400)}]}
#and where a column's lists set their fields at other tab stops further down: (the top they start at, fields)
BAND_FIELDS = {
    (29, 1): [(0, PAGE_FIELDS[29][1]),
              (375, {'place': (0, 140), 'name': (140, 550), 'town': (550, 995), 'time': (995, 1300)}),
              (1095, {'place': (0, 140), 'name': (140, 573), 'town': (573, 1048), 'time': (1048, 1350)})],
    (31, 0): [(0, PAGE_FIELDS[31][0]),
              (1010, {'place': (0, 230), 'name': (230, 700), 'town': (700, 1070), 'time': (1070, 1400)}),
              (1600, {'place': (0, 230), 'name': (230, 640), 'town': (640, 1070), 'time': (1070, 1400)})],
    (31, 1): [(0, PAGE_FIELDS[31][1]),
              (1320, {'place': (0, 328), 'name': (328, 750), 'town': (750, 1210), 'time': (1210, 1480)}),
              (2200, {'place': (0, 303), 'name': (303, 680), 'town': (680, 1125), 'time': (1125, 1450)})],
    (32, 1): [(0, PAGE_FIELDS[32][1]),
              (1195, {'place': (0, 290), 'name': (290, 700), 'town': (700, 1190), 'time': (1190, 1450)})]}
FIELDS = PAGE_FIELDS[28][0]
#a line's ink in pixels high, least and most, the pixels from one line to the next, and a character's width
LINE_HEIGHT = (12, 40)
LINE_PITCH = 38
PITCH = 19.2
TIME_DIGITS = 7
NAME_ORDER = 'last'
SCALES = (1.5, 2)
#a foreign town is followed by its country, not a state
TOWN_COUNTRY = True
#the order the columns' lists run in
COLUMN_ORDER = [(27, 0), (28, 0), (27, 1), (28, 1), (29, 0), (30, 0), (29, 1), (30, 1), (31, 0), (32, 0), (31, 1),
                (32, 1)]
#each class's heading: (page, column, its top, class), a heading's lines no result. None ends a column's class where
#the next heading is big type with nothing to read, or a column's lines end; the novice men's heading at the foot of
#page 29's left column is set below the page, so the class starts atop the next column in the order (30's left)
HEADING_LINES = 0.2
HEADINGS = [(27, 0, 2150, 'NW'), (29, 0, 2400, None), (29, 0, 3300, 'NM'), (31, 0, 400, 'JG 17'),
            (31, 0, 1560, None), (31, 0, 1690, 'JB 17'), (32, 0, 1600, None), (32, 0, 1725, 'JG 15'),
            (31, 1, 400, 'JB 15'), (31, 1, 2115, None), (31, 1, 2240, 'JG 13'), (32, 1, 195, None),
            (32, 1, 345, 'JB 13')]
#(page, column): the pixel row the lists start below, under the page's title or a heading
TABLE_TOP = {(27, 0): 2150, (27, 1): 1700, (31, 0): 400, (31, 1): 400}
#(gender, age class, race)
CLASSES = {'NW': ('F', 'F 19+', 'kortie'), 'NM': ('M', 'M 19+', 'kortie'), 'JG 17': ('F', 'F 17-18', 'kortie'),
           'JB 17': ('M', 'M 17-18', 'kortie'), 'JG 15': ('F', 'F 15-16', 'kortie'),
           'JB 15': ('M', 'M 15-16', 'kortie'), 'JG 13': ('F', 'F 13-14', 'kortie'),
           'JB 13': ('M', 'M 13-14', 'kortie')}
#lines the scan has lost at the foot or head of a page, before the line at (page, column, its top)
RANK_SKIPS = {(28, 0, 20): 2, (28, 1, 8): 1, (30, 1, 52): 1, (32, 1, 28): 1}
#by (page, column, the line's top): lines too shaded to read but in part (dropped), lines the band shades read by eye,
#and names and towns tesseract misreads
HAND = {
    (30, 0, 33): {'drop': True},
    (30, 1, 32): {'drop': True},
    (27, 0, 2434): {'name': 'HAMILTON, JoAnn', 'town': 'Laporte, MN', 'time': '2:44:30.74'},
    (28, 0, 20): {'name': 'LINDSTROM, Jan', 'town': 'Dundee, IL', 'time': '2:50:33.65'},
    (27, 1, 2430): {'name': 'HEBERLACH, Rita', 'town': 'Minneapolis, MN', 'time': '3:42:16.37', 'result': True},
    (28, 1, 8): {'name': 'SCHMIDT, Diane', 'town': 'Wauwatosa, WI', 'time': '3:42:23.85'},
    (29, 1, 2513): {'name': 'CERVELLI, Renato', 'town': 'South Bend, IN', 'time': '3:42:20.32'},
    (30, 1, 52): {'time': '3:44:51.67'},
    (31, 0, 2485): {'name': 'SELLNER, Jerry', 'town': 'Hastings, MN', 'time': '2:10:16.85'},
    (32, 0, 40): {'name': 'HESTNES, Torvald', 'town': 'Rochester, MI'},
    (31, 1, 2447): {'name': 'JUNG, Vicki Jo', 'town': 'Hastings, MN', 'time': '3:22:21.57'},
    (30, 0, 77): {'name': 'TORMONDSEN, John', 'town': 'Cable, WI'},
    (30, 0, 115): {'name': 'ROSENBERRY, Donald'},
    (30, 0, 152): {'name': 'CARRABRE, Jim'},
    (30, 0, 1171): {'name': 'RIME, Tom'},
    (30, 0, 1436): {'town': 'Bemidji, MN'},
    (29, 1, 1601): {'name': 'CERVELLI, Robert'},
    (30, 1, 1906): {'name': 'KREIGER, Gary'},
    (31, 1, 454): {'town': 'Marine on St. Croix, MN'},
    (31, 0, 641): {'name': 'MAHER, Bonnie', 'town': 'Marine on St. Croix, MN'},
    (31, 1, 1064): {'town': 'Black River Falls, WI'},
    (31, 0, 679): {'town': 'Barrington, IL'},
    (31, 0, 753): {'town': 'White Bear Lake, MN'},
    (31, 0, 1266): {'town': 'Highbridge, WI'},
    (27, 1, 2407): {'town': 'River Falls, WI'},
    (28, 0, 331): {'name': 'NOSKEY, Jan'},
    (28, 0, 596): {'name': 'HEIKE, Heidi'},
    (28, 0, 1197): {'name': 'SIMS, Deborah'},
    (28, 0, 2067): {'name': 'LAVIK, Drofn'},
    (27, 1, 1837): {'name': 'KUBLEY, Sue'},
    (28, 1, 1100): {'town': 'Willman, MN'},
    (30, 0, 755): {'town': 'Norway'},
    (29, 1, 671): {'town': 'Fayetteville, N.Y.'},
}


def parse(year=YEAR):
    return class_lists.parse(year, 'kortie')


def ocr(year=YEAR):
    class_lists.ocr(year, 'kortie')


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
