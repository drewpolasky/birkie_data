#1975's results booklet: the 27.5 km race from seeley (the kortelopet by the champions list) ends the birkebeiner's
#pages 2 and 3, typed the same way, so it's read with them by class_lists.py from y1975.py's layout and readings (no
#ocr of its own), which mark its classes as the kortelopet's: women 20-34 ('F 20-34'), women 35 and over ('F 35+'),
#junior women 19 and under ('F -19') and junior men 19 and under ('M -19'), each under a heading in two columns:
#place, name, town, time (h:mm:ss). the scan's right edge fades the last digit of the times down page 2's right
#column (29 lines): y1975.py's HAND gives them as read by eye where enough of the digit shows (15), and with 5, the
#middle of its ten seconds, where it doesn't (14: women 35 and over 10th, 11th, 12th, 15th to 18th, junior women 7th to
#13th)
from old_results_parsers import class_lists
from old_results_parsers.y1975 import YEAR


def parse(year=YEAR):
    return class_lists.parse(year, 'kortie', pages='birkie')
