#1994 birch scroll: "MEN'S HERITAGE BANK OF HAYWARD KORTELOPET RESULTS" on pages 55-59 (places 1-988; page 59 has only
#its left column) and "WOMEN'S ..." on pages 60-63 (places 1-714; page 63's two columns stop partway, above photos and
#an advertisement), right after the birkebeiner's and typeset the same way, so y1994.py reads them (its own column OCRs
#included, made when missing). its table has no 25% column and sets its columns further apart from the FINAL TIME
#column; its classes start with the juniors' (13-14, 15-16, 17-18), then 19-24 in place of 18-24; its bibs are five
#figures (11000 to 20388) and its PACE MN/KM is the time over 26 km, with two figures for the minutes from 10 on
#('13.53'). where some OCRs drop a lone initial ('LAURA JOHNSON' for LAURA I JOHNSON), the reading with as many words as
#the page shows comes first (WORDS_FIRST)
from old_results_parsers import y1994

YEAR = 1994
TABLE = dict(
    #each field's left edge, in page pixels, from the left of the FINAL TIME column
    FIELDS=[('rank', -100), ('time', -12), ('bib', 75), ('name', 150), ('town', 460), ('st', 690), ('nat', 740),
            ('cls', 800), ('crank', 880), ('pace', 960), ('end', 1050)],
    CLASSES=['13-14', '15-16', '17-18', '19-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64',
             '65-69', '70+'],
    KM=26,
    BIBS=(11000, 20499),
    PACE_MINUTES=r'1?\d',
    WORDS_FIRST=True)


def parse(year=YEAR):
    return y1994.parse(year, race='kortie', table=TABLE)
