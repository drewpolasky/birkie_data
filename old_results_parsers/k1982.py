#1982 kortelopet: pages 36-40, after the birkebeiner's (y1982.py), headed "Telemark Kortelopet": a dot matrix
#printer's list in mixed case, three blocks a page, men and women in one list by overall place: the place, bib, name
#(surname first), town, state (or province or country: ONT, CAN, NOR), the class (as a number) and the time
#(h.mm.ss.t), with a dotted rule under every fifth line. page 40's lower half, set sideways, is past years' statistics,
#which give 1,239 finishers, as read: every place from 1 to 1239 is there, so a line's number down the list is its
#printed place. the printer's digits print broken, and tesseract reads its narrow class digits, its bibs and its
#states' letters badly, so the times, bibs and classes are read again digit by digit (see kortie_lists.py), and a
#state is guessed from its town where it doesn't read as one. a few times are printed out of order (a typist's slip:
#3.58.10.5 between 3.37 and 3.38, 4.05.05.0 among the 5.05s), kept as printed
import sys

from old_results_parsers import kortie_lists

YEAR = 1982
SCAN = 1982
TURN = {}
ANGLE = {36: 1.15, 37: -0.15, 38: 0, 39: 0.45, 40: 0}
FIELDS = ('place', 'bib', 'name', 'town', 'state', 'class', 'time')
#the shares of a column's lines, and of the lines either side of one, a field's tab stop is found in (higher than the
#other years': its bibs' numbers start the names' column on the lines tesseract runs a bib into the name)
TAB_SHARES = (0.7, 0.75)
#its bibs, 7000 to 8999 (tesseract reads them badly, and they're read again digit by digit, matched to the time's)
BIB_DIGITS = 4
BIB_FIRST = '78'
#(page, the section's box on the level page, where its columns part (the rules between the blocks), its class: None,
#each line's own), in the list's order
SECTIONS = [(36, (200, 570, 3420, 2380), [1222, 2243], None),
            (37, (230, 90, 3420, 2380), [1254, 2241], None),
            (38, (230, 90, 3420, 2380), [1254, 2241], None),
            (39, (230, 90, 3420, 2380), [1254, 2241], None),
            (40, (230, 170, 3420, 1510), [1254, 2241], None)]
#h.mm.ss.t, its digits printed broken now and then, so cut out on the printer's grid
TIME_GROUPS = (1, 2, 2, 1)
GLYPHS = 'grid'
#one list by overall place: no class ranks. its times are in order but for a few printed out of order (a typist's
#slip: 3.58.10.5 between 3.37 and 3.38), so a time read surely (both readings and the digits agreeing) is kept as
#printed where the order would change it
ORDER_BY = None
KEEP_SURE = 0.7
CLASS_RANKS = False
#the class code's cell, in pixels from the left of the time
CODE_CELL = (-50, -22)
#the class codes, which the list doesn't give: by the skiers in them who raced the kortelopet's classes in 1979 and
#1980 (the boys 13-14 of 1980 in 2, its boys 15-16 in 3, the girls 15-16 of 1979 in 7, the novices in 4 and 8)
CLASS_CODES = {'1': 'M 13-14', '2': 'M 15-16', '3': 'M 17-18', '4': 'M 19+', '5': 'F 13-14', '6': 'F 15-16',
               '7': 'F 17-18', '8': 'F 19+'}


def age_group(row):
    return CLASS_CODES.get(row['class'], '')


#its state column's letters read badly (WE, IK, TH): each is the state its town is seen in with most of the letters
GUESS_STATES = True


def town_text(row):
    return '{}, {}'.format(row['town'], row['state'])


#all the lines printed
LINES = 1239


def hand_key(row):
    #(the line's number down the list, which is its printed place)
    return row['line']


#as printed, by printed place: bibs the digits read wrong, times the readings get wrong (or leave unread), the order
#changes (one printed out of order) or that print too broken to read surely, and classes and a state not read
BIBS = {75: '8648', 110: '7898', 165: '7833', 236: '8854', 307: '7498', 371: '8441', 493: '8186', 575: '8521',
        610: '8791', 708: '7066', 710: '7296', 761: '7199', 847: '7882', 885: '8162', 990: '7434', 1013: '7183',
        1033: '7865', 1041: '8032', 1047: '8313', 1073: '8653', 1110: '8693', 1141: '8449', 1176: '7262'}
TIMES = {18: '1:55:58.0', 52: '2:13:10.3', 113: '2:48:53.7', 257: '3:17:31.2', 296: '3:24:23.2', 387: '3:58:10.5',
         490: '3:53:09.4', 493: '3:53:35.2', 496: '3:53:55.3', 532: '4:02:18.2', 640: '4:14:27.7', 951: '5:01:35.5',
         982: '4:05:05.0', 1013: '5:10:18.1', 1022: '5:11:34.7', 1025: '5:11:42.6', 1033: '5:13:14.2',
         1047: '5:16:17.6', 1078: '5:20:15.8', 1132: '5:36:23.2', 1140: '5:38:13.0', 1141: '5:38:21.9',
         1196: '6:02:02.1', 1199: '6:06:33.3', 1215: '6:22:21.0'}
OTHER = {483: {'class': '8'}, 532: {'class': '2'}, 990: {'class': '5', 'state': 'WI'}, 1033: {'class': '6'},
         1041: {'class': '4'}, 1206: {'class': '8'}}
HAND = {p: {**({'bib': BIBS[p]} if p in BIBS else {}), **({'time': TIMES[p]} if p in TIMES else {}),
            **OTHER.get(p, {})} for p in set(BIBS) | set(TIMES) | set(OTHER)}


def parse(year=YEAR):
    return kortie_lists.parse(year)


def ocr(year=YEAR):
    kortie_lists.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
