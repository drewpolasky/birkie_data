#1975's results booklet: three typewritten pages, each class under a heading in two columns (its first half down the
#left, the rest down the right), read by class_lists.py: place, name, town ("Wausau, Wi."), time (h:mm:ss). the 55 km
#classes are the birkebeiner; pages 2 and 3 end with the 27.5 km race from seeley, for women and boys. someone has
#marked up the scan with a pen: lines struck out (two marked OK again), a time written in, a note in the margin
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
           'F 20-34 seeley': ('F', 'F 20-34', 'seeley'), 'F 35+ seeley': ('F', 'F 35+', 'seeley'),
           'F junior seeley': ('F', 'F -19', 'seeley'), 'M junior seeley': ('M', 'M -18', 'seeley')}
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
}


def parse(year=YEAR):
    return class_lists.parse(year)


def ocr(year=YEAR):
    class_lists.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
