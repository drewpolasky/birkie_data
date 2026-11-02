#1975's results booklet: three typewritten pages, each class under a heading in two columns (its first half down the
#left, the rest down the right), read by class_lists.py: place, name, town ("Wausau, Wi."), time (h:mm:ss). the 55 km
#classes are the birkebeiner; pages 2 and 3 end with the 27.5 km race from seeley, for women and boys (the
#kortelopet, read with the rest, its classes marked as its race: k1975.py). someone has marked up the scan with a pen:
#lines struck out (two marked OK again), a time written in, a note in the margin
import sys

from old_results_parsers import class_lists

YEAR = 1975
PAGES = [1, 2, 3]
TURN = {}
#the small turn (degrees counterclockwise) that makes each page's lines level
ANGLE = {1: 0.07, 2: 0.02, 3: 0.32}
#the columns' left and right edges, in pixels on the level page, and each field's in pixels from a column's left
COLUMNS = ((0, 1300), (1300, 2552))
FIELDS = [{'place': (0, 75), 'name': (75, 555), 'town': (555, 1040), 'time': (1040, 1248)},
          {'place': (0, 115), 'name': (115, 555), 'town': (555, 1025), 'time': (1025, 1252)}]
#a line's ink in pixels high, least and most, the pixels from one line to the next, and a character's width
LINE_HEIGHT = (14, 40)
LINE_PITCH = 38.5
PITCH = 23.1
TIME_DIGITS = 5
NAME_ORDER = 'first'
#the type is big enough that tesseract reads it best as it is
SCALES = (1, 1.5)
#the pages' titles, above the lists
TABLE_TOP = {2: 280, 3: 300}
#each class's heading: (page, its top, class), and page 2's title for the race from seeley
HEADINGS = [(1, 234, 'M elite'), (1, 542, 'M 20-34'), (1, 2160, 'M 35-42'), (2, 283, 'M 43-49'), (2, 634, 'M 50+'),
            (2, 1062, 'M junior'), (2, 1257, 'F'), (2, 1494, 'F 20-34 seeley'), (2, 1570, 'F 20-34 seeley'),
            (2, 2192, 'F 35+ seeley'), (2, 2657, 'F junior seeley'), (3, 308, 'M junior seeley')]
#(gender, age class, race). the elite class is for 18 years 9 months to 24, the women's 55 km class for all ages
CLASSES = {'M elite': ('M', 'M 19-24', 'birkie'), 'M 20-34': ('M', 'M 20-34', 'birkie'),
           'M 35-42': ('M', 'M 35-42', 'birkie'), 'M 43-49': ('M', 'M 43-49', 'birkie'),
           'M 50+': ('M', 'M 50+', 'birkie'), 'M junior': ('M', 'M -19', 'birkie'), 'F': ('F', '', 'birkie'),
           'F 20-34 seeley': ('F', 'F 20-34', 'kortie'), 'F 35+ seeley': ('F', 'F 35+', 'kortie'),
           'F junior seeley': ('F', 'F -19', 'kortie'), 'M junior seeley': ('M', 'M -19', 'kortie')}
#the pen's marks on page 1, by (page, column, the line's top): lines struck out, that line's time written in, and the
#lines its marks leave unreadable, as printed
HAND = {
    #23rd of men 20-34, struck out and ringed: he's the 9th of men 35-42, ringed there too
    (1, 0, 1453): {'drop': True},
    #8th of men 35-42, struck out (unlike the 74th of men 20-34 and 37th of men 35-42, marked OK)
    (1, 0, 2506): {'drop': True},
    #9th of men 35-42, ringed, and the 21st, 6:08:37, struck out and written in below as 5:28:32, which puts him after
    #the 9th
    (1, 0, 2543): {'time': '5:28:07'},
    (1, 0, 3008): {'name': 'Bill Stai', 'town': 'Earl, Wis.', 'time': '5:28:32'},
    #under the ring round the line above, and with a note written across its time
    (1, 0, 1495): {'name': 'Tim Swanson', 'time': '5:29:56'},
    (1, 0, 1654): {'time': '5:43:37'},
    #a line drawn across, two struck out but marked OK, and a time underlined
    (1, 1, 1721): {'name': 'Jim Duffy', 'town': 'Hayward, Wis.'},
    (1, 1, 1919): {'name': 'Stephen Paladie', 'town': 'Oakdale, Minn.', 'time': '7:08:50'},
    (1, 1, 2815): {'name': 'Malcolm C. Scott', 'town': 'Superior, Wis.'},
    (1, 1, 2932): {'time': '7:34:35'},
    #the kortelopet's (k1975.py): the scan's right edge fades page 2's right column's last digits, read by eye where
    #enough of the digit shows (women 20-34, and two of women 35 and over), and taken as 5, the middle of its ten
    #seconds, where it doesn't
    (2, 1, 1646): {'time': '3:46:21'},
    (2, 1, 1685): {'time': '3:51:09'},
    (2, 1, 1723): {'time': '3:53:17'},
    (2, 1, 1762): {'time': '3:58:28'},
    (2, 1, 1802): {'time': '4:04:49'},
    (2, 1, 1841): {'time': '4:12:44'},
    (2, 1, 1880): {'time': '4:17:32'},
    (2, 1, 1919): {'time': '4:17:57'},
    (2, 1, 1957): {'time': '4:24:06'},
    (2, 1, 1998): {'time': '4:31:59'},
    (2, 1, 2036): {'time': '4:35:46'},
    (2, 1, 2074): {'time': '4:46:03'},
    (2, 1, 2111): {'name': 'Eileen Stombaugh', 'time': '4:46:19'},
    (2, 1, 2268): {'time': '3:48:55'},
    (2, 1, 2307): {'time': '3:56:45'},
    (2, 1, 2346): {'time': '4:11:05'},
    (2, 1, 2384): {'time': '4:13:19'},
    (2, 1, 2423): {'time': '4:26:53'},
    (2, 1, 2463): {'time': '4:43:55'},
    (2, 1, 2502): {'time': '5:26:45'},
    (2, 1, 2540): {'time': '5:39:05'},
    (2, 1, 2580): {'time': '5:46:55'},
    (2, 1, 2733): {'time': '3:43:05'},
    (2, 1, 2773): {'time': '4:12:35'},
    (2, 1, 2812): {'time': '4:15:15'},
    (2, 1, 2852): {'time': '4:21:15'},
    (2, 1, 2891): {'time': '4:21:25'},
    (2, 1, 2929): {'time': '4:46:25'},
    (2, 1, 2968): {'time': '5:36:05'},
    #and its names and towns tesseract misreads
    (2, 0, 2463): {'name': 'Helen Dungan'},
    (3, 1, 1078): {'town': 'La Crosse, Wis.'},
}


def parse(year=YEAR):
    return class_lists.parse(year)


def ocr(year=YEAR):
    class_lists.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
