#1983 results booklet (american birkebeiner xi, unofficial results): the birkebeiner results are pages 2-27 (printed
#1-26), each a tabloid page set sideways, two blocks a page of a dot matrix printer's table, men and women in one list
#by overall place, read by line_printer.py: RANK, CLASS (the class, as a number) and the class rank, typed onto the
#printout in another face, then BIB, NAME (surname first, in mixed case), CITY, ST, CTRY, CTZ, YRS, 25% (a figure) and
#TIME (h:mm:ss:hh). the list is set in sections under headings (1-20, 21-50, ...), and ends partway down page 27's
#first block, where the kortelopet's starts. the note above it says the men's class ranks (classes 1-9) are wrong: the
#men's class codes are typed with a leading 0 or without, and each way is ranked on its own, so the men's ranks are
#left out
import sys

import numpy as np
from PIL import Image

from old_results_parsers import line_printer
from old_results_parsers.line_printer import Printer, DIGITS, LETTERS, OCR_CHARACTERS

YEAR = 1983
#'X': men and women in one list
PAGES = {p: 'X' for p in range(2, 28)}
BLOCK_ORDER = [(p, k) for p in range(2, 27) for k in (1, 2)] + [(27, 1)]
TURN = {p: Image.ROTATE_90 for p in PAGES}
ANGLE = {2: -1.61, 3: 0.51, 4: -0.24, 5: 0.61, 6: -2.0, 7: -0.26, 8: -0.63, 9: -0.45, 10: -0.52, 11: 0.58, 12: -0.54,
         13: 1.13, 14: -0.42, 15: 0.65, 16: -1.18, 17: -0.58, 18: -0.8, 19: -0.38, 20: -0.43, 21: 0.15, 22: -0.74,
         23: -0.31, 24: -0.85, 25: -0.31, 26: -0.2, 27: -0.57}
#the scans' edges are black
BLOTS = 3000
SPECKS = 4
#each page's blocks (column 0's middle, level), from where each block's times start
BLOCK_EDGES = {2: (184, 1723), 3: (281, 1850), 4: (135, 1679), 5: (276, 1799), 6: (158, 1708), 7: (160, 1724),
               8: (131, 1656), 9: (248, 1805), 10: (178, 1721), 11: (277, 1834), 12: (196, 1748), 13: (293, 1816),
               14: (198, 1741), 15: (262, 1810), 16: (152, 1698), 17: (209, 1771), 18: (122, 1658), 19: (225, 1753),
               20: (111, 1660), 21: (234, 1778), 22: (133, 1679), 23: (298, 1834), 24: (191, 1727), 25: (292, 1831),
               26: (135, 1681), 27: (277, 1811)}
#14.26 pixels a character and 39.2 a line, two blocks a page. the typed part: the rank left aligned from column 3, the
#class (1 to 17, the men's 1 to 9 typed with a leading 0 or without) a blank after it and the class rank right aligned
#a few columns on, wherever each section was typed. then the printer's: the bib right aligned in 18-21, the name from
#23, the city from 49, the state in 70-71, the country in 74-76, CTZ (Y or N) in 78, the years finished right aligned
#in 81, the 25% club's 1 or 0 in 84 and the time in 89-98. each line's grid is its country to time's, found in the
#time's strip (so the headings aren't lines). the typed part sits off it by up to four columns, varying down a block and
#from section to section, and half a line up or down, so it's placed by its first glyph (the rank's) and its own strip
#is tracked down the block; and the bib to the state is set up to two columns off the country to the time, from line
#to line, and the copy is stretched unevenly across some pages (that part's pitch as much as 0.3 pixels more), so it's
#fitted to its own glyphs and pitch. the typewriter's digits are wider than the printer's, and the dot matrix's bold
#lines on some pages fill their cells, so the cells next to them pick up ink: a typed cell counts only its middle's,
#and the bib is read without the blank column after it. the network learns the printer's digits from tesseract's, and
#never learns its small l, which it reads as I (BIII is BILL by the clean results); a small m after some names is a
#mark, left out
PRINTER = Printer(pitch=14.26, pitches=np.arange(13.8, 14.7, 0.002), blocks=2, block_width=1470, block_chars=101,
                  block_step=(1500, 1580), title_rows=250, line_pitch=39.2, line_gap=10, line_height=(16, 32),
                  joined_height=95, strips=((-80, 245), (245, 690), (690, 985), (985, 1255), (1255, 1420)),
                  line_strip=4, strip_reach=12, track_strips=True, section_gaps=True, table_gap=5, band=24,
                  glyph_widths=(2, 15), glyph_w=14, glyph_h=34, glyph_top=3, middle=12, middle_slack=8,
                  label_marks='.,', digit_labels=True, ocr_characters=OCR_CHARACTERS + 'abcdefghijklmnopqrstuvwxyz,',
                  fields={'rank': (3, 7), 'bib': (17, 22), 'name': (23, 49), 'town': (49, 69), 'st': (69, 73),
                          'nat': (73, 77), 'club': (77, 87), 'time': (88, 100)},
                  anchor_inked=(78, 81, 84, *range(89, 99)), anchor_blank=(79, 82, 83, 85, 86, 87, 88, 99),
                  anchor_least=11, anchor_reach=4, pitch_from=1035, reanchor=False,
                  moved_parts=((17, 73, (21, 23, 24), (22,)),), part_pitches=True, part_core=3,
                  typed_part=(3, 17, 17.5), place_columns=range(3, 7), place_left=True, ranks_after_place=17,
                  ranks_by_code=True, name_marks='M', small_l=True, sex_columns=(),
                  punctuation={90: ':', 93: ':', 96: ':'}, time_columns=(89, 91, 92, 94, 95, 97, 98), pace_columns=(),
                  age_columns=(),
                  column_characters=[DIGITS] * 23 + [LETTERS + "-.,'&"] * 26 + [LETTERS + "-.'&"] * 20 + [LETTERS] * 8
                  + [LETTERS + DIGITS] * 11 + [DIGITS + ':'] * 11 + [DIGITS] * 2)
#the class codes, as the other years of the 1980s give them
CLASS_CODES = {1: 'M 19-24', 2: 'M 25-29', 3: 'M 30-34', 4: 'M 35-39', 5: 'M 40-44', 6: 'M 45-49', 7: 'M 50-54',
               8: 'M 55-59', 9: 'M 60+', 10: 'F 19-24', 11: 'F 25-29', 12: 'F 30-34', 13: 'F 35-39', 14: 'F 40-44',
               15: 'F 45-49', 16: 'F 50-54', 17: 'F 55+'}
SURNAME_FIRST = True
#page 2's first block starts under the article, its second at the page's top
BLOCK_TOP = {(2, 1): 1300, (2, 2): 150}
#the RANK column skips 2621 and 2622, between page 15's blocks
RANK_SKIPS = {(15, 2, 1): 2}
#the skiers typed into the list after it was printed, in their place by time (the note above the list: about 100 left
#off it, found on the backup timing sheets) with no rank or class rank, their class typed small at the left and the
#rest in a typewriter's face the glyphs can't be read in: (page, block, the line's top, class (none where it isn't
#printed or can't be read), bib, surname, first names, city, state, country, time). the class's faint print is all but
#lost on six, and the tens of the seconds on one (4:19:37 or 4:19:47 by the times either side, taken as the middle). a
#lone "m" after some surnames (Galli, m, Walter) is left out
TYPED_IN = [(3, 2, 1876, 10, 5923, 'Drangesholt', 'Unni', 'Kristiansand', '', 'NOR', '3:05:12'),
            (3, 2, 2888, 8, 5727, 'Galli', 'Walter', 'Feuerthalen', '', 'SUI', '3:07:45'),
            (4, 2, 590, 5, 273, 'Babler', 'David A.', 'Monroe', 'WI', 'USA', '3:17:38'),
            (4, 2, 2737, 5, 5932, 'Molstad', 'Svein E.', 'Nordseter', '', 'NOR', '3:21:30'),
            (5, 1, 688, 2, 5930, 'Hanstad', 'Lars', 'Lillehammer', '', 'NOR', '3:24:28'),
            (5, 2, 2228, 2, 1988, 'Helgeson', 'Scott A.', 'St. Cloud', 'MN', 'USA', '3:33:11'),
            (6, 2, 2906, 13, 3804, 'Pommier', 'Shirley A.', 'Sudbury', 'ON', 'CAN', '3:45:24'),
            (7, 1, 3611, 3, 5031, 'Weinke', 'Bruce A.', 'Forest Lake', 'MN', 'USA', '3:51:19'),
            (7, 2, 3332, 2, 4512, 'Staib', 'Robert V.', 'Oak Forest', 'IL', 'USA', '3:57:00'),
            (7, 2, 3398, 7, 5825, 'Schumachker', 'Ingolf', '', '', 'GER', '3:57:10'),
            (7, 2, 3522, 4, 5164, 'Woeste', 'David M.', 'River Falls', 'WI', 'USA', '3:57:19'),
            (7, 2, 3677, 1, 6012, 'Lovaas', 'Steven P.', 'Minnetonka', 'MN', 'USA', '3:57:40'),
            (7, 2, 3900, 15, 5889, 'Poupore', 'Susan', 'Duluth', 'MN', 'USA', '3:58:01'),
            (8, 1, 2461, 1, 5291, 'Anderson', 'David G.', 'Minneapolis', 'MN', 'USA', '4:01:44'),
            (8, 2, 762, 5, 5318, 'Bohmir', 'Tommy', 'Askiv', '', 'NOR', '4:04:36'),
            (8, 2, 2626, 3, 5237, 'Youngren', 'Thomas R.', 'Cumberland', 'WI', 'USA', '4:06:55'),
            (8, 2, 2967, 2, 4158, 'Scherzer', 'David F.', 'Milwaukee', 'WI', 'USA', '4:07:32'),
            (8, 2, 3897, 4, 1956, 'Hedquist', 'J. Patrick', 'Amherst Jct.', 'WI', 'USA', '4:08:29'),
            (9, 1, 2377, 5, 4621, 'Sugden', 'Robert D.', 'Waukesha', 'WI', 'USA', '4:12:12'),
            (9, 1, 3862, 2, 4665, 'Sweinberg', 'Kenneth L.', 'New Berlin', 'WI', 'USA', '4:14:46'),
            (9, 2, 1561, 2, 4944, 'Wagner', 'Timothy L.', 'Fisher', 'MN', 'USA', '4:16:29'),
            (9, 2, 2050, 4, 5352, 'Dooley', 'Barry', 'Weston', 'ON', 'CAN', '4:16:59'),
            (9, 2, 2999, 1, 6029, 'Jewell', 'Kirkpatric K.', 'St. Paul', 'MN', 'USA', '4:18:07'),
            (9, 2, 4020, 5, 4379, 'Simonson', 'Bob M.', 'Hortonville', 'WI', 'USA', '4:19:15'),
            (10, 1, 472, None, 5240, 'Zalatoris', 'Jeffrey E.', 'Antioch', 'IL', 'USA', '4:19:42'),
            (10, 1, 738, 4, 3177, 'Mehne', 'Mike F.', 'Niagara', 'WI', 'USA', '4:19:59'),
            (10, 1, 1839, 4, 4951, 'Waldo', 'David R.', 'St. Paul', 'MN', 'USA', '4:21:45'),
            (10, 2, 1902, 2, 5236, 'Youngquist', 'Craig', 'Juneau', 'AK', 'USA', '4:27:22'),
            (10, 2, 2798, 2, 3098, 'McAninch', 'Gary L.', 'Woods Hole', 'MA', 'USA', '4:29:01'),
            (12, 1, 2732, 8, 4582, 'Stonecipher', 'Ray', 'Whitewater', 'WI', 'USA', '4:45:07'),
            (13, 2, 572, None, 6028, 'Walters', 'Mark A.', 'Osseo', 'MN', 'USA', '4:58:15'),
            (13, 2, 3465, None, 647, 'Brown', 'Gerald', 'Minneapolis', 'MN', 'USA', '5:03:27'),
            (14, 2, 1205, None, 5910, 'Myhra', 'Larry', 'La Crosse', 'WI', 'USA', '5:11:02'),
            (14, 2, 3842, None, 4550, 'Stephens', 'James L.', 'Menomonie Falls', 'WI', 'USA', '5:14:31'),
            (15, 2, 1654, 5, 1436, 'Floren', 'David', 'Plymouth', 'MN', 'USA', '5:23:04'),
            (15, 2, 2235, 6, 5535, 'Bloom', 'Richard', 'Appleton', 'WI', 'USA', '5:23:45'),
            (16, 1, 2601, 3, 1440, 'Flynn', 'Michael', 'Phillips', 'WI', 'USA', '5:29:39'),
            (16, 1, 4083, 11, 5370, 'Ferger', 'Cynthia A.', 'Beaver Dam', 'WI', 'USA', '5:31:43'),
            (17, 1, 2587, 2, 4850, 'Van Hoof', 'Thomas M.', 'Pewaukee', 'WI', 'USA', '5:41:05'),
            (18, 1, 366, 2, 1757, 'Gustafson', 'Dale W.', 'Rockford', 'IL', 'USA', '5:49:11'),
            (18, 1, 1458, 5, 448, 'Berneking', 'William B.', 'Wayzata', 'MN', 'USA', '5:50:44'),
            (18, 1, 3928, None, 1215, 'Duckwitz', 'John', 'Madison', 'WI', 'USA', '5:54:33'),
            (18, 2, 607, 3, 2595, 'Kostroski', 'Larry P.', 'Green Bay', 'WI', 'USA', '5:55:11'),
            (18, 2, 1421, 3, 3969, 'Riedel', 'Thomas M.', 'Wisconsin Rapids', 'WI', 'USA', '5:56:43'),
            (19, 1, 2605, 12, 1583, 'Gentling', 'Linda', 'Ashland', 'WI', 'USA', '6:03:38'),
            (19, 1, 2751, 4, 2749, 'Larsen', 'Richard E.', 'Horicon', 'WI', 'USA', '6:03:45'),
            (19, 1, 2816, 3, 2597, 'Kotovic', 'Michael J.', 'Pewaukee', 'WI', 'USA', '6:03:53'),
            (19, 1, 2894, 10, 2975, 'Macken', 'Julie A.', 'St. Paul', 'MN', 'USA', '6:04:03'),
            (19, 1, 2920, None, 4515, 'Standefer', 'James E.', 'Stillwater', 'MN', 'USA', '6:04:06'),
            (19, 1, 2950, 2, 1354, 'Estherhay', 'Carl A.', 'St. Paul', 'MN', 'USA', '6:04:08'),
            (19, 1, 3058, 3, 3409, 'Nadolney', 'Perry J.', 'Menasha', 'WI', 'USA', '6:04:22'),
            (19, 1, 3130, 1, 4570, 'Stock', 'Joe E.', 'Madison', 'WI', 'USA', '6:04:31'),
            (19, 1, 3279, 3, 4461, 'Soderholm', 'Conrad D.', 'St. Paul', 'MN', 'USA', '6:04:57'),
            (19, 1, 3620, 4, 2154, 'Huibregtge', 'Dennis R.', 'Sussex', 'WI', 'USA', '6:05:47'),
            (20, 1, 2773, 13, 4649, 'Suydam', 'Melinda', 'Brainerd', 'MN', 'USA', '6:18:16'),
            (20, 1, 2802, 3, 6020, 'Wamser', 'John', 'Milwaukee', 'WI', 'USA', '6:18:22'),
            (20, 2, 1218, 10, 5041, 'Weium', 'Karen', 'Minneapolis', 'MN', 'USA', '6:23:06'),
            (20, 2, 1678, 11, 5912, "O'Day", 'Kelly', 'Merrill', 'WI', 'USA', '6:23:43'),
            (21, 1, 2690, 5, 5191, 'Woods', 'Jack H.', 'Bayside', 'WI', 'USA', '6:32:24'),
            (21, 2, 2065, 3, 4536, 'Steffen', 'Jack', 'Plymouth', 'MN', 'USA', '6:38:10'),
            (22, 1, 1050, 2, 1922, 'Haugen', 'Robert S.', 'Portage', 'WI', 'USA', '6:43:48'),
            (22, 1, 1154, 2, 5051, 'Welnak', 'James', 'West Allis', 'WI', 'USA', '6:44:07'),
            (22, 1, 3616, 6, 5601, 'Senfleben', 'Henry G.', 'Oconomowoc', 'WI', 'USA', '6:49:08'),
            (22, 2, 1519, 3, 1463, 'Foster', 'Philip A.', 'St. Paul', 'MN', 'USA', '6:52:19'),
            (22, 2, 1590, 11, 3464, 'Newcomb', 'Deborah A.', 'Chicago', 'IL', 'USA', '6:52:31'),
            (22, 2, 2988, 12, 4377, 'Simon', 'Marilyn S.', 'Madison', 'WI', 'USA', '6:55:14'),
            (23, 1, 2034, 11, 4061, 'Ruhme', 'Annette L.', 'Bloomington', 'MN', 'USA', '7:00:23'),
            (23, 1, 2529, 12, 4763, 'Tingerthal', 'Mary C.', 'Minneapolis', 'MN', 'USA', '7:01:40'),
            (24, 2, 1445, None, 957, 'Cowles', 'Richard L.', 'Appleton', 'WI', 'USA', '7:29:29'),
            (24, 2, 3663, None, 3678, 'Pawlowski', 'Rich', 'Hammond', 'IN', 'USA', '7:35:18'),
            (25, 1, 371, 4, 3957, 'Richards', 'Jeff C.', 'Wayzata', 'MN', 'USA', '7:36:51'),
            (25, 1, 560, 8, 5942, 'Haase', 'Roy T.', 'Middleton', 'WI', 'USA', '7:37:35'),
            (25, 1, 1071, 12, 3410, 'Nagel', 'Judy', 'Minneapolis', 'MN', 'USA', '7:39:12'),
            (25, 1, 2845, None, 5261, 'Ziemer', 'Mark R.', 'Menasha', 'WI', 'USA', '7:44:38'),
            (25, 1, 3550, 2, 1074, 'Dean', 'Robert S.', 'Madison', 'WI', 'USA', '7:46:38'),
            (25, 2, 570, 3, 4974, 'Wandersee', 'Stephen C.', 'St. Paul', 'MN', 'USA', '7:48:22'),
            (25, 2, 2879, 2, 1338, 'Epping', 'Scott T.', 'Milwaukee', 'WI', 'USA', '7:57:28'),
            (26, 1, 2153, 1, 4842, 'Vadnais', 'Timothy W.', 'Mandan', 'ND', 'USA', '8:12:59'),
            (26, 1, 2215, 11, 3018, 'Manering', 'Mary', 'Madison', 'WI', 'USA', '8:13:33'),
            (26, 1, 4032, 3, 4106, 'Sandstrom', 'Stephen', 'River Falls', 'WI', 'USA', '8:22:21')]


def typed_in(page, block, top, cls, bib, last, first, city, state, country, time):
    #a typed in line as HAND gives it
    clean = lambda text: ' '.join(text.upper().replace('.', ' ').split())
    return {(page, block, top): {'name': clean(first + ' ' + last), 'first': clean(first), 'last': clean(last),
                                 'bib': str(bib), 'age_group': CLASS_CODES.get(cls, ''), 'class_rank': '',
                                 'city': clean(city), 'state': state, 'country': country, 'time': time}}


#and the times of three lines a smudge or a speck keeps from their grid, and the two slowest, over ten hours, whose
#hour the time's columns don't hold. three times are misprinted (3:22:82:27, 6:02:65:00 and 7:25:78:00), and are
#left blank. Shirley Pommier is listed twice, at 3:21:39.40 and typed in again at 3:45:24, both kept as printed, so
#the printed line's bib is set too, for the two to keep it
HAND = {**{key: fields for line in TYPED_IN for key, fields in typed_in(*line).items()},
        (2, 2, 3997): {'time': '2:50:39.00'}, (8, 2, 2237): {'time': '4:06:26.00'},
        (8, 2, 2276): {'time': '4:06:26.40'}, (27, 1, 1629): {'time': '10:00:30.00'},
        (27, 1, 1669): {'time': '10:00:41.00'}, (4, 2, 2813): {'bib': '3804'}}


def parse(year=YEAR):
    return line_printer.parse(year)


def ocr(year=YEAR):
    line_printer.ocr(year)


if __name__ == '__main__':
    if sys.argv[1:] == ['ocr']:
        ocr()
