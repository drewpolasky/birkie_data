#1980 kortelopet: the 1980 scan's pages 12 (below the birkebeiner's end, under "Telemark Kortelopet Results") and 13,
#the results section's pages 11 and 12, set sideways, typewritten class by class in mixed case, each class under a
#heading ("CLASS 1 - Boys 13 & 14") and numbered from 1: POS., NAME (surname first), BIB, HOMETOWN (town, state and
#country) and TIME (h:mm:ss.hh). the scan has no more of the list: its next page is the spring 1979 birch scroll's,
#so it holds classes 1 to 4 (boys 13-14, 15-16 and 17-18 and men 19 and over, as age_group M 13-14 ... M 19+) and the
#men 19+ only to the 69th, at the foot of page 13, and none of the women's classes (the statistics in the 1982 birch
#scroll give 996 finishers). the scan shades parts of the pages with a dither, which is cleaned off
import sys

from PIL import Image

from old_results_parsers import kortie_lists

YEAR = 1980
SCAN = 1980
TURN = {12: Image.ROTATE_90, 13: Image.ROTATE_90}
ANGLE = {12: -2.45, 13: -1.85}
#a blur's radius and the gray under which it's ink, to clean the dither off
CLEAN = (1.5, 150)
FIELDS = ('place', 'name', 'bib', 'town', 'time')
#(page, the section's box on the level page, where its columns part, its class), in the list's order
SECTIONS = [(12, (200, 3690, 3420, 4260), [1740], 'M 13-14'),
            (13, (300, 330, 1820, 1030), [], 'M 13-14'),
            (13, (300, 1100, 1820, 3445), [], 'M 15-16'),
            (13, (300, 3530, 1820, 4320), [], 'M 17-18'),
            (13, (1830, 320, 3420, 2150), [], 'M 17-18'),
            (13, (1830, 2238, 3420, 4320), [], 'M 19+')]
#h:mm:ss.hh
TIME_GROUPS = (1, 2, 2, 2)
#each class's times are in order, and its lines numbered
ORDER_BY = 'age_group'
CLASS_RANKS = True
#the men 19 and over stop at the 69th, so a boy slower than him has no place
CUT_CLASSES = ('M 19+',)


def age_group(row):
    return row['section_class']


def hand_key(row):
    return row['age_group'], row['class_rank']


#bibs as printed, where tesseract reads a digit wrong or runs a speck into one
HAND = {('M 13-14', 27): {'bib': '7031'}, ('M 13-14', 44): {'bib': '6930'}, ('M 15-16', 44): {'bib': '6502'},
        ('M 17-18', 30): {'bib': '6661'}, ('M 17-18', 49): {'bib': '6521'}, ('M 17-18', 84): {'bib': '7111'},
        ('M 19+', 40): {'bib': '6891'}}


def parse(year=YEAR):
    return kortie_lists.parse(year)


def ocr(year=YEAR):
    kortie_lists.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
