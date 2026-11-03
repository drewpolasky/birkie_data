#1979 kortelopet: the spring 1979 birch scroll's results pages 21-24, set sideways, typewritten class by class, each
#class under a heading ("Novice Women Ages 19 & Over") in three columns and numbered from 1: the number, NAME (surname
#first), town and state (or country) and time (h:mm:ss.hh). the 1979 scan's copy of them (its pages 13-16) blanks out
#parts of its pages (the first column of page 13 but for its towns and times, the first column of the junior boys
#17-18 and the names of their second), so the list is read from the second copy of them in the 1980 scan (its pages
#23-26; 'page' and 'top' are on those), and the 1979 scan's copy only for a second reading of each line's time (and of
#the names and towns where it shows them). both scans shade parts of the pages with a dither, which is cleaned off
#
#the classes, as age_group: novice women and novice men 19 and over (F 19+, M 19+), junior girls and boys 17-18, 15-16
#and 13-14 (F 17-18 ... M 13-14). the scans' right edges cut off the times at the foot of some columns (see CUT):
#those of the junior boys 13-14 from 33 to 49 aren't on either scan and are left blank (so they have no place), the
#girls 15-16 from 23 and 13-14 from 10 show only their minutes (taken as the middle of the minute, :30), and the men
#19+ from 145 on only their tens of seconds (the middle of those, :x5). two lines are printed with no name (the
#women's 77th and 144th) and two with a bib in place of a name ("BIB # 7164"), and the men 19+'s 202nd and 203rd are
#printed out of order (4:18:34.91, 4:18:34.22). the statistics in the 1982 birch scroll give 949 finishers
import sys

from PIL import Image

from old_results_parsers import kortie_lists

YEAR = 1979
SCAN = 1980
TURN = {p: Image.ROTATE_90 for p in (23, 24, 25, 26)}
ANGLE = {23: -1.75, 24: -2.5, 25: -1.95, 26: -0.35}
#a blur's radius and the gray under which it's ink, to clean the dither off
CLEAN = (1.5, 150)
FIELDS = ('place', 'name', 'town', 'time')
#(page, the section's box on the level page, where its columns part, its class), in the list's order
SECTIONS = [(23, (60, 2040, 3420, 4330), [1102, 2105], 'F 19+'),
            (24, (300, 330, 3420, 2010), [1311, 2358], 'F 19+'),
            (24, (330, 2270, 3420, 4430), [1350, 2391], 'M 19+'),
            (25, (60, 250, 3420, 1200), [1030, 2093], 'M 19+'),
            (25, (60, 1520, 3420, 1930), [1090, 2092], 'F 17-18'),
            (25, (60, 2210, 3420, 3110), [1095, 2105], 'M 17-18'),
            (25, (60, 3440, 3420, 4360), [1080, 2098], 'M 15-16'),
            (26, (450, 500, 3420, 880), [1480, 2485], 'F 15-16'),
            (26, (450, 1205, 3420, 1390), [1480, 2485], 'F 13-14'),
            (26, (450, 1715, 3420, 2290), [1480, 2485], 'M 13-14')]
#the 1979 scan's copy, by the index of the section each box copies
TWIN_SCAN = 1979
TWIN_TURN = {p: Image.ROTATE_90 for p in (13, 14, 15, 16)}
TWIN_ANGLE = {13: -0.15, 14: -0.15, 15: -0.45, 16: -0.15}
TWINS = {0: (13, (0, 1925, 3016, 4224), [1000, 2025]),
         1: (14, (0, 50, 2948, 1745), [995, 2020]),
         2: (14, (0, 2030, 2948, 4176), [1020, 2034]),
         3: (15, (0, 250, 3240, 1195), [1021, 2015]),
         4: (15, (0, 1535, 3240, 1905), [1034, 2023]),
         5: (15, (0, 2220, 3240, 3120), [1034, 2028]),
         6: (15, (0, 3440, 3240, 4392), [1034, 2028]),
         7: (16, (0, 355, 2892, 720), [994, 2006]),
         8: (16, (0, 1068, 2892, 1245), [994, 2006]),
         9: (16, (0, 1583, 2892, 2130), [994, 2006])}
#the times the scans' right edges cut off, by section and column: the digits each leaves, or 'edge' for as many as a
#line shows. the women 19+ from 319 (the 1980 scan to the last hundredth or so, the 1979 scan to the seconds, aslant),
#the men 19+ from 134 (both aslant, the 1980 scan to the seconds at the top, both to the tens of seconds or the
#minutes further down), the girls 15-16 from 23 and 13-14 from 10 (the 1980 scan cuts off their times, the 1979 scan
#leaves the minutes) and the boys 13-14 from 33 (neither scan shows their times)
CUT = {(1, 2): 'edge', (2, 2): 'edge'}
TWIN_CUT = {(1, 2): 'edge', (2, 2): 'edge', (7, 2): 3, (8, 2): 3}
#tesseract reads the typewriter's 0 as 9 now and then, in both scans alike
DOUBTFUL_NINES = True
#h:mm:ss.hh
TIME_GROUPS = (1, 2, 2, 2)
#each class's times are in order, and its lines numbered
ORDER_BY = 'age_group'
CLASS_RANKS = True


def age_group(row):
    return row['section_class']


def hand_key(row):
    return row['age_group'], row['class_rank']


#as the scans show them: hundredths printed faintly or cut by the scan's edge (as far as they show), and times the
#readings get wrong. the men 19+ from 134 as far as the scans show them (from 145 the 1979 scan's tens of seconds;
#the 184th's and 185th's only to the minute, between 4:11:2x and 4:11:5x), and the girls' the 1979 scan leaves
HAND = {('F 19+', 108): {'time': '3:55:57.10'}, ('F 19+', 366): {'time': '5:56:08.7'},
        ('F 19+', 367): {'time': '5:56:17.1'}, ('F 19+', 368): {'time': '6:01:02.8'},
        ('F 19+', 369): {'time': '6:01:06.4'}, ('F 19+', 370): {'time': '6:04:01.4'},
        ('M 19+', 201): {'time': '4:17:37.62'}, ('M 19+', 203): {'time': '4:18:34.22'},
        ('M 19+', 204): {'time': '4:18:52.31'}, ('M 19+', 205): {'time': '4:19:10.19'},
        ('M 19+', 206): {'time': '4:19:53'}, ('M 19+', 211): {'time': '4:22:24.93'},
        ('M 19+', 218): {'time': '4:26:44.91'}, ('M 17-18', 11): {'time': '1:45:09.69'},
        ('M 17-18', 18): {'time': '1:54:37.43'}, ('M 17-18', 25): {'time': '2:02:35.01'},
        ('F 15-16', 20): {'time': '3:47:22.93'},
        **{('M 19+', 134 + i): {'time': t} for i, t in enumerate(
            ['3:50:56', '3:51:26', '3:52:22', '3:52:53', '3:53:05', '3:54:06', '3:54:16', '3:54:23', '3:54:37',
             '3:55:04', '3:55:1', '3:55:3', '3:56:0', '3:56:1', '3:56:2', '3:56:4', '3:56:5', '3:57:1', '3:57:2',
             '3:57:4', '3:58:4', '3:58:4', '3:58:4', '3:58:5', '4:00:2', '4:00:4', '4:01:5', '4:02:1', '4:02:2',
             '4:02:5', '4:03:0', '4:04:1', '4:04:3', '4:04:3', '4:05:2', '4:05:3', '4:06:2', '4:06:4', '4:06:5',
             '4:06:5', '4:07:5', '4:08:0', '4:08:5', '4:09:1', '4:09:1', '4:09:2', '4:10:0', '4:10:1', '4:11:1',
             '4:11:2', '4:11', '4:11', '4:11:5', '4:12:0', '4:12:1', '4:13:1', '4:13:1', '4:13:1', '4:13:1',
             '4:13:4', '4:13:5', '4:14:0', '4:14:1', '4:14:4', '4:15:0', '4:15:2'])},
        **{('F 15-16', 23 + i): {'time': t} for i, t in enumerate(
            ['3:57', '3:57', '3:59', '4:10', '4:24', '4:26', '4:33', '4:36', '4:42', '5:04', '5:30'])},
        **{('F 13-14', 10 + i): {'time': t} for i, t in enumerate(['4:50', '4:57', '4:57', '5:06', '5:20'])}}
#and a state the readings get wrong (Stillwater, MN)
HAND[('M 19+', 134)]['state'] = 'MN'


def parse(year=YEAR):
    return kortie_lists.parse(year)


def ocr(year=YEAR):
    kortie_lists.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
