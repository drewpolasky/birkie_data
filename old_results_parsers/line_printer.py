#the fixed pitch printouts of 1978 to 1991, read character by character. each results page has two or three blocks of
#a printer's table side by side, a result a line. 1988-1991's line printer prints RANK, SEX ("M"/"F"), FINAL TIME, BIB,
#NAME, HOMETOWN (15 characters, so often shortened: STVNS POINT), ST, ZIP, NAT, CLASS ("M25-29"), CL RANK, 25% ("Y"),
#PACE (the minutes a kilometre over a set distance); the earlier printers much the same fields in other columns and
#sizes (a Printer each), 1978's to 1982's men and women in one list by overall place, the class as a number giving
#the gender. no technique column: classic and skate skiers share one list per gender, and the places count up by one
#down it. each year's module (y1978.py to y1991.py) says which pages hold which list, how each page turns upright and
#level, where the first block starts, the printer and what's odd about its copy
#
#tesseract reads the printers' dotted letters badly (M as H or W, 3, 8 and 9 for each other), so the pages are read
#character by character instead: each page is turned upright and straightened, each block's lines found, and each
#character cell on the printer's grid (8.74 to 18.73 pixels a character at 300 dpi, set line by line and nudged where
#the copy is stretched) read by a small neural network learned from the cells themselves: the places, the sex, the
#time's punctuation, the digits the tables pin down, tesseract's letters (in both cases, for 1982's mixed case names,
#read as capitals; and its digits, for 1980's typewriter face) where its reading of the block
#(old_results/ocr/<year>/<page>_b<n>.tsv) lines up with the grid, and
#the names and towns read as words seen in the clean results. the reading, with each character's runner-up, third
#choice and how sure it is, is kept as old_results/ocr/<year>/<page>_grid.tsv; "python -m old_results_parsers.y<year>
#ocr" makes them (about four minutes)
#
#parse() then repairs what the tables pin down: a time out of order gets the digit swap that puts it in order, a class
#that can't be read the one its class ranks leave a gap for, a class rank the count within its class, a state its zip
#code's state (or, with no zip, the runner-up letter that makes a state the town is known in), a repeated bib the
#runner-up digit that makes an unused one, a name or town word not seen in the clean results the runner-up letter that
#makes a common one, and a shortened town the one town in that state it shortens. a list of men and women together is
#then split by the classes' genders, the places within each counted with those in the list's gaps
#
#'top' is the line's y pixel in the page turned upright and level. on a page stored upside down it's the line's y
#pixel in the stored image, counted from the top
import bisect
import collections
import concurrent.futures
import copy
import difflib
import functools
import importlib
import itertools
import os
import re
import subprocess

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage

from birkie_archive import PAGE_DIR, OCR_DIR, TESSERACT, parse_seconds
from results_loader import load_all_results, US_STATES, CA_PROVINCES

DIGITS = '0123456789'
LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
OCR_CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:.-/%'&"
OCR_WORKERS = 4
#the list being read: the birkebeiner's, laid out by each year's y<year>.py, or the kortelopet's, printed after it in
#the same printer's table, by its k<year>.py. parse() and ocr() set it
RACE_MODULES = {'birkie': 'y', 'kortie': 'k'}
race = 'birkie'


class Printer:
    #a printer's table: where things are in pixels (at 300 dpi) and in character columns from the left of a block's
    #grid. the defaults are 1991's line printer, and a year printed otherwise sets its module's PRINTER to a Printer
    #made with the settings that differ
    #pixels a character, and the range a line's own pitch is looked for in
    pitch = 8.742
    pitches = np.arange(8.62, 8.92, 0.002)
    #blocks side by side, each this wide in pixels and in characters, and the pixels from one block's left edge to the
    #next's, least and most
    blocks = 3
    block_width = 985
    block_chars = 112
    block_step = (960, 1020)
    #pixel rows above the table, left out when finding the blocks
    title_rows = 330
    #pixels from one line to the next, and between one line's ink and the next's; a line's ink in pixels high, least
    #and most, and most for a few lines joined by specks
    line_pitch = 25.2
    line_gap = 7
    line_height = (13, 24)
    joined_height = 80
    #rows with next to no ink that a line's ink can be broken by (between a dot matrix's rows of dots)
    row_gaps = 0
    #blank lines printed between groups of lines (1981's, every five), which are no place
    separator_lines = 0
    #where the list is set in sections under headings (1980's "251-500"), so that a gap between a block's lines is a
    #heading, no places
    section_gaps = False
    #the most lines a block's table can skip (a gap of a few missing lines, or a section's heading) and run on
    table_gap = 3.5
    #the strips of a block in which each line's height is measured, since a line can bend by up to 9 pixels across a
    #block near the foot of a page, and the one whose lines are the block's lines: the first, which holds the rank, sex
    #and time, which every result has
    strips = ((15, 225), (225, 420), (420, 620), (620, 800), (800, 975))
    line_strip = 0
    #the most pixels a line's top in a strip can be off its top in the line strip, or where the strips are tracked
    #(1983's, whose typed part drifts off the printer's lines down a block, by up to most of a line), off where the line
    #above's offset puts it
    strip_reach = 10
    track_strips = False
    #the most pixels a stretch of a line's glyphs is moved to fit them, short of half a character, the columns either
    #side of a column whose glyphs give its offset, and the fewest glyphs that do
    drift_most = 3.5
    drift_reach = 6
    drift_least = 3
    #where the copy's dark edge, or the dither shading it, puts a line's top a few pixels off (1978's): the most pixels
    #its cells are moved up or down to fit their ink, row by row, to the block's
    fit_tops = 0
    #the pixel rows of a line in which its glyphs are found, and a glyph's width in pixels, least and most
    band = 19
    glyph_widths = (4, 9)
    #a character's cell in pixels, its top row glyph_top pixels above the line's top
    glyph_w, glyph_h = 9, 26
    glyph_top = 3
    #pixels from a line's top to its middle, and how far a word's middle can be off it
    middle = 9
    middle_slack = 7
    #each field's character columns
    fields = {'rank': (2, 7), 'sex': (9, 12), 'time': (13, 25), 'bib': (25, 31), 'name': (31, 57), 'town': (57, 74),
              'st': (74, 77), 'zip': (77, 84), 'nat': (84, 88), 'cls': (88, 95), 'crank': (95, 101), 'club': (101, 104),
              'pace': (104, 111)}
    #the columns every result line inks (the sex and the time) and leaves blank (around them): a line is a result line
    #when at least anchor_least more of them are as they should be than not
    anchor_inked = (10, *range(15, 24))
    anchor_blank = (8, 9, 11, 12, 13, 14, 24)
    anchor_least = 8
    #where the anchor spans most of a line, and its glyphs are too broken up to give its pitch (1985's dot matrix): a
    #line that doesn't anchor at the pitch its glyphs give tries the others, every 0.01 pixels
    anchor_pitch = False
    #where the printer can shift a line's right part by a column: (the first column of the part, the columns every
    #result line inks there, the columns it leaves blank there), as right_shift uses it
    right_anchor = None
    #where the copy stretches a block's left part against its right (1981's): the pixels from the block's edge from
    #which a line's glyphs give its pitch and phase, and (the column the stretch is from, the columns every result line
    #inks left of it, the columns it leaves blank there), as left_stretch uses it
    pitch_from = 0
    left_anchor = None
    #the pixels from the block's edge before which a line's glyphs give its pitch, where pitch_from's give only its
    #phase (1980's, whose left part has the more glyphs but sits off the grid of its right)
    pitch_before = 0
    #where parts of a line are set off its grid by a column and some, varying from line to line (1980's: the class to
    #the country, against the years finished, time and place, which with pitch_from give the line's grid; 1983's: the
    #bib to the state, against the country to the time): each part's (first column, column after its last, the columns
    #every result line inks in it, the columns it leaves blank there), as part_shifts uses them
    moved_parts = ()
    #whether each moved part's pitch is its own (where the copy is stretched unevenly across a page, 1983's)
    part_pitches = False
    #where a part's anchor columns are judged by the ink within this many pixels of each cell's middle, not the whole
    #cell (1983's, whose glyphs nearly fill their cells, so that one a few pixels off inks the blank beside it)
    part_core = None
    #where a part is typed onto the printout left of its columns, off them by up to several columns (1983's rank, class
    #and class rank): (the column its first character is in, the column after its last, and the column of the grid as
    #the parts are moved that it lies left of), its first glyph being its first character
    typed_part = None
    #the fewest pixels of ink in a glyph, a speck having fewer, and the fewest pixel rows high a typed place's first
    #digit is
    glyph_ink = 25
    place_height = 20
    #the most columns a line's anchor, or a part, is moved from where its glyphs' phase puts it (more where a block's
    #columns lean, 1983's)
    anchor_reach = 2
    #whether each line's grid is moved by up to two columns to fit the block's other lines, where a smudge can put a
    #line's anchor a column off (not where the lines' parts sit differently from line to line, 1980's)
    reanchor = True
    #the place's columns (right aligned, or left aligned where place_left), the columns the list's sex is printed in,
    #and the time's punctuation
    place_columns = range(3, 7)
    place_left = False
    #where the place, class and class rank are printed one after another, a blank or more between them (1983's, typed
    #onto the printout): the column after the last they reach. the class and class rank are then the first two numbers
    #after the place's digits and the blank after them, not the cls and crank fields
    ranks_after_place = 0
    #whether the class ranks count a class whose code is printed with a leading 0 apart from the same class printed
    #without (1983's)
    ranks_by_code = False
    sex_columns = (10, 89)
    punctuation = {16: ':', 19: ':', 22: '.'}
    #the columns of the time's six digits, the pace's minutes and seconds (the colon in column 107) and the class's age
    time_columns = (15, 17, 18, 20, 21, 23)
    pace_columns = (105, 106, 108, 109)
    age_columns = (90, 91, 93, 94)
    #the age classes the table prints (the kortelopet's start with its juniors')
    ages = ('18-24', '25-29', '30-34', '35-39', '40-44', '45-49', '50-54', '55-59', '60-64', '65-69', '70+')
    #the characters tesseract may read (lower case letters are learned as such, and read as their capitals), and the
    #marks learned from its reading too, where the printer puts them in names (1981's and 1982's commas and points)
    ocr_characters = OCR_CHARACTERS
    label_marks = ''
    #where tesseract reads the printer's digits about as well as its letters (1980's typewriter face): its digits are
    #learned too, each of its labels kept where it's the nearest mean cell of the characters its column holds
    digit_labels = False
    #the letters (or marks) the comma between a surname and a first name is sometimes read as (1978's, Y)
    comma_letters = ''
    #the letters the printer now and then leaves out (1979's, W: WI printed I), restored in a state that isn't one
    dropped_letters = ''
    #the letters printed after some names as a mark (1983's small m), dropped where one ends the name on its own
    name_marks = ''
    #where names are printed in mixed case but the network doesn't learn the small l, reading it as I (1983's): an I
    #among small letters is an l, and a name or town word not seen in the clean results is the one some of its I's as L
    #make, where there's one
    small_l = False
    #where the network reads every one of a capital as another (1989's kortelopet, Y as T): {letter read: letter
    #meant}, a name or town word not seen in the clean results being the one some of them as the letter meant make,
    #as for small_l
    swapped = {}
    #{country as printed: its code}, where the printer writes the country out
    nation_names = {}
    #the characters each column can hold, so a 0 isn't read as a D in a time, or an M as an N in the sex column
    column_characters = ([DIGITS] * 9 + ['MF'] * 3 + [DIGITS + ':.'] * 13 + [DIGITS] * 6 + [LETTERS + "-.'&"] * 43
                         + [LETTERS] * 3 + [LETTERS + DIGITS] * 7 + [LETTERS] * 4
                         + [LETTERS] + ['MF'] + [DIGITS] * 2 + ['-+'] + [DIGITS] * 2
                         + [DIGITS] * 6 + [LETTERS] * 3 + [DIGITS + ':'] * 8)

    def __init__(self, **settings):
        for name, value in settings.items():
            if not hasattr(Printer, name):
                raise AttributeError(name)
            setattr(self, name, value)


LINE_PRINTER = Printer()


def layout(year):
    #the year's module for the race being read (k<year>.py for the kortelopet, laid out the same way):
    #   PAGES          {page: gender (X for men and women in one list), or a gender for each block where a list ends
    #                  partway, or a tuple with the genders of each block's lists, top down, where a block holds the
    #                  end of one and the start of the next ('MF')}
    #   TURN           {page: transpose to upright}
    #   ANGLE          {page: degrees counterclockwise that make its lines level}
    #   FIRST_BLOCK    the left edge of the first block on the first page (without BLOCK_EDGES), upright and level
    #   PACE_KM        the distance the PACE column is the final time over, where there is one
    #   PRINTER        where it isn't printed as 1991 was
    #and where needed, with blocks counted from 1:
    #   MISSING_LINES  {(page, block): places at the foot of the block with no line to read (cut off, never printed)}
    #   EXTRA_LINES    {(page, block): lines after the block's last one found (shading over their blanks)}
    #   LEADING_LINES  {(page, block): lines before the block's first one found (the rule under the headings touching
    #                  them)}
    #   BLOCK_ANGLE    {(page, block): degrees counterclockwise that make the block's lines level, where it's turned
    #                  against the rest of its page}
    #   FIRST_PLACE    {gender: the place on the list's first line, where its first page is missing}
    #   RANK_SKIPS     {(page, block, line): numbers the RANK column skips before the line, every place there after it
    #                  printed that much higher, where no skier is missing (the class ranks run on)}
    #   SCALE          {page: how much larger the page is made, where it's printed smaller than the rest}
    #   SPECKS         the most pixels of a speck of ink, which is cleared, where the scan's edges are shaded with a
    #                  dither (1978's)
    #   BLOTS          the fewest pixels of a blot of ink, which is cleared, where the scan's edges are black
    #   TABLE_TOP      {page: the pixel row the table starts below, upright, level and scaled, where something else
    #                  is printed above it}
    #   BLOCK_TOP      {(page, block): the same for one block, where the page's blocks start at different heights}
    #   BLOCK_ORDER    [(page, block)] in the order the list runs, where it isn't page by page (1978's runs across
    #                  each pair of facing pages)
    #   CLASS_CODES    {code: class}, where the class is printed as a number
    #   CUT_TIMES      {(page, block): the time's digits the scan shows, where its edge cuts the rest off, or 'edge'
    #                  where it cuts them aslant, each line keeping those wholly on the scan}
    #   HAND           {(page, block, the line's top): what the scan can't give}: 'drop' for a line that's no result (a
    #                  correction pasted over the table), or the fields as they should be
    #   UNFOUND        {(gender, place): the result's fields}, for a line printed in another face or set off the
    #                  rest that isn't found as a line, its place kept by the gap it leaves
    #   SURNAME_FIRST  True where the name is printed surname first
    #and for a page that sets the same table's fields otherwise (a first page printed upright):
    #   PAGE_PRINTERS  {page: its Printer}
    #   BLOCK_EDGES    {page: each block's left edge}
    #   COLUMN_MAPS    {page: [(first column, column after the last, the year's column the first goes to, and
    #                  'right' for a field printed left aligned that the year prints right aligned)]}
    return importlib.import_module('old_results_parsers.{}{}'.format(RACE_MODULES[race], year))


def use_race(name):
    #read the other race's list: what's kept of the pages' geometry is its layout's, so it's cleared
    global race
    if name != race:
        race = name
        for kept in (upright, on_scan, block_ink, blocks, block_lines, block_glyphs):
            kept.cache_clear()


def page_file(year, page, name):
    #a file kept for one of the year's pages, in old_results/ocr/<year>/: <page>_<name>, or <page>_kortie_<name> for
    #the kortelopet's reading (a page can hold the end of one list and the start of the other)
    return os.path.join(ocr_dir(year), '{:03d}{}_{}'.format(page, '' if race == 'birkie' else '_' + race, name))


def page_printer(year, page):
    #the printer whose geometry the page is read with
    return getattr(layout(year), 'PAGE_PRINTERS', {}).get(page) or printer(year)


def to_year_columns(year, page, glyphs):
    #the cells of a page in another layout moved to the year's columns, by its column map; the rest left blank. a field
    #marked 'right' is printed left aligned there, and is moved so its last inked cell ends the year's columns for it
    columns = getattr(layout(year), 'COLUMN_MAPS', {}).get(page)
    if columns is None:
        return glyphs
    p = printer(year)
    out = np.zeros((len(glyphs), p.block_chars) + glyphs.shape[2:], bool)
    ink = inked(glyphs)
    for a, b, to, *align in columns:
        if align == ['right']:
            for i in range(len(glyphs)):
                cols = np.nonzero(ink[i, a:b])[0]
                last = a + cols[-1] if len(cols) else b - 1
                out[i, to + b - 1 - last:to + b - a] = glyphs[i, a:last + 1]
        else:
            out[:, to:to + b - a] = glyphs[:, a:b]
    return out


def block_order(year):
    #(page, block from 0) in the order the list runs
    order = getattr(layout(year), 'BLOCK_ORDER', None)
    if order:
        return [(page, k - 1) for page, k in order]
    return [(page, k) for page in layout(year).PAGES for k in range(page_printer(year, page).blocks)]


def hand(year, page, block, top):
    #what the year's HAND says of a line (keyed by page, block from 1 and the line's top, give or take half a line)
    for (pg, b, t), what in getattr(layout(year), 'HAND', {}).items():
        if pg == page and b == block and abs(t - top) <= printer(year).line_pitch / 2:
            return what
    return {}


def block_genders(year, page, k):
    #the gender of each of the block's lists, top down
    genders = layout(year).PAGES[page]
    return genders[k] if isinstance(genders, tuple) else genders[k] if len(genders) > 1 else genders


def table_top(year, page):
    return getattr(layout(year), 'TABLE_TOP', {}).get(page)


def pace_km(year):
    return getattr(layout(year), 'PACE_KM', None)


def printer(year):
    return getattr(layout(year), 'PRINTER', LINE_PRINTER)


def first_places(year):
    return {g: getattr(layout(year), 'FIRST_PLACE', {}).get(g, 1) for g in 'MFX'}


def ocr_dir(year):
    return os.path.join(OCR_DIR, str(year))


#---------------------------------------------------------------- geometry

@functools.lru_cache(maxsize=None)
def upright(year, page):
    #the page as ink (True) and paper, upright and level
    im = Image.open(os.path.join(PAGE_DIR, str(year), '{:03d}.png'.format(page)))
    turn = layout(year).TURN.get(page)
    if turn is not None:
        im = im.transpose(turn)
    im = im.rotate(layout(year).ANGLE[page], resample=Image.NEAREST, fillcolor=255)
    scale = getattr(layout(year), 'SCALE', {}).get(page)
    if scale:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    ink = np.array(im) < 128
    specks, blots = getattr(layout(year), 'SPECKS', 0), getattr(layout(year), 'BLOTS', 0)
    if specks or blots:
        labels, _ = ndimage.label(ink)
        sizes = np.bincount(labels.ravel())[labels]
        ink &= (sizes > specks) & ((sizes < blots) if blots else True)
    return ink


@functools.lru_cache(maxsize=None)
def on_scan(year, page):
    #the pixels of the page, upright and level, that lie on the scan (not in a corner the turn brings in from off it)
    im = Image.open(os.path.join(PAGE_DIR, str(year), '{:03d}.png'.format(page)))
    im = Image.new('L', im.size, 255)
    turn = layout(year).TURN.get(page)
    if turn is not None:
        im = im.transpose(turn)
    im = im.rotate(layout(year).ANGLE[page], resample=Image.NEAREST, fillcolor=0)
    scale = getattr(layout(year), 'SCALE', {}).get(page)
    if scale:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.NEAREST)
    return np.array(im) > 128


@functools.lru_cache(maxsize=None)
def block_ink(year, page, k):
    #the page as ink, upright and level, turned about the middle of block k where the year's BLOCK_ANGLE turns it
    ink = upright(year, page)
    angle = getattr(layout(year), 'BLOCK_ANGLE', {}).get((page, k + 1))
    if not angle:
        return ink
    middle = (blocks(year, page)[k] + page_printer(year, page).block_width / 2, ink.shape[0] / 2)
    im = Image.fromarray(np.where(ink, 0, 255).astype(np.uint8))
    return np.array(im.rotate(angle, resample=Image.NEAREST, fillcolor=255, center=middle)) < 128


def level_angle(year, page):
    #the turn (degrees counterclockwise, to a hundredth) that makes the page's lines level: the sharpest profile of ink
    #by row, searched every 0.05 degrees and then every 0.01 around the best. how 1990's ANGLE was found. the lines bend
    #a little across a page, so a tenth of a degree either way reads just as well, and block_lines follows each line's
    #height across the block anyway
    im = Image.open(os.path.join(PAGE_DIR, str(year), '{:03d}.png'.format(page)))
    turn = layout(year).TURN.get(page)
    if turn is not None:
        im = im.transpose(turn)

    def sharpness(angle):
        rows = (np.array(im.rotate(angle, resample=Image.NEAREST, fillcolor=255)) < 128)[:, 100:-100].sum(1)
        return (np.diff(rows.astype(float)) ** 2).sum()

    coarse = np.arange(-4, 4.01, 0.05)
    best = coarse[np.argmax([sharpness(a) for a in coarse])]
    fine = np.arange(best - 0.05, best + 0.051, 0.01)
    return round(float(fine[np.argmax([sharpness(a) for a in fine])]), 2)


def column_profile(ink, top):
    #ink in each pixel column, below the titles
    return ink[top:ink.shape[0] - 40].sum(0).astype(float)


@functools.lru_cache(maxsize=None)
def blocks(year, page):
    #the left edge of each block: where the page's column profile best matches the first block of the first page, one
    #block width apart give or take (or as the year's BLOCK_EDGES give them)
    if page in getattr(layout(year), 'BLOCK_EDGES', {}):
        return tuple(layout(year).BLOCK_EDGES[page])
    p = printer(year)
    first = layout(year).FIRST_BLOCK
    reference = min(page for page in layout(year).PAGES if page not in getattr(layout(year), 'BLOCK_EDGES', {}))
    ref = column_profile(upright(year, reference), table_top(year, reference) or p.title_rows)
    ref = ref[first:first + p.block_width] - ref[first:first + p.block_width].mean()
    prof = column_profile(upright(year, page), table_top(year, page) or p.title_rows)
    n = len(ref)
    windows = np.lib.stride_tricks.sliding_window_view(prof, n)
    corr = (windows - windows.mean(1, keepdims=True)) @ ref
    out = []
    for k in range(p.blocks):
        if not out:
            lo, hi = max(0, first - 110), first + 90
        else:
            lo, hi = out[-1] + p.block_step[0], out[-1] + p.block_step[1]
        hi = min(hi, len(corr))
        out.append(lo + int(np.argmax(corr[lo:hi])))
    return tuple(out)


def block_image(year, page, k, scale=2):
    x0 = blocks(year, page)[k]
    ink = block_ink(year, page, k)
    crop = ink[:, max(0, x0 - 20):x0 + printer(year).block_width + 15]
    im = Image.fromarray(np.where(crop, 0, 255).astype(np.uint8))
    return im.resize((im.width * scale, im.height * scale), Image.LANCZOS), max(0, x0 - 20)


def joined_rows(on, gaps):
    #the rows with ink, and those in a break of up to gaps rows between them
    on = np.array(on)
    if gaps:
        for s, e in runs(~on):
            if e - s <= gaps and s > 0 and e < len(on):
                on[s:e] = True
    return on


def runs(on):
    out, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(on)))
    return out


def line_runs(profile, p):
    #rows of print: runs of rows with ink (across breaks of up to the printer's row_gaps rows), a line high, and runs a
    #few lines high (lines joined by specks) cut at their thinnest rows
    out = []
    least, most = p.line_height
    for s, e in runs(joined_rows(profile > 3, p.row_gaps)):
        h = e - s
        if least <= h <= most:
            out.append((s, e))
        elif most < h <= p.joined_height:
            n = int(round((h + p.line_gap) / p.line_pitch))
            if n < 2:
                out.append((s, e))
                continue
            cuts = [s]
            for i in range(1, n):
                guess = s + int(round(i * (h + p.line_gap) / n)) - (p.line_gap + 1) // 2
                lo, hi = max(s + 1, guess - 5), min(e - 1, guess + 6)
                cuts.append(lo + int(np.argmin(profile[lo:hi])) if hi > lo else guess)
            cuts.append(e)
            for a, b in zip(cuts[:-1], cuts[1:]):
                part = np.nonzero(profile[a:b] > 3)[0]
                if len(part) and least <= part[-1] - part[0] + 1 <= most:
                    out.append((a + part[0], a + part[-1] + 1))
    return out


def smooth_offsets(tops, offsets, window=4):
    #each strip's height against the first strip's, as the median over the nearby lines, so a strip a line has
    #nothing in (or a speck in) takes its neighbours'
    out = np.zeros_like(offsets)
    for j in range(offsets.shape[1]):
        col = offsets[:, j]
        for i in range(len(tops)):
            near = col[max(0, i - window):i + window + 1]
            near = near[~np.isnan(near)]
            out[i, j] = np.median(near) if len(near) else 0
    return out


@functools.lru_cache(maxsize=None)
def block_lines(year, page, k):
    #each line of a block: its top in each strip, and where its character grid starts (x of column 0's centre)
    p = page_printer(year, page)
    ink = block_ink(year, page, k)
    x0 = blocks(year, page)[k]
    tops = []
    per_strip = []
    for a, b in p.strips:
        prof = ink[:, x0 + a:x0 + b].sum(1)
        per_strip.append(np.array([s for s, e in line_runs(prof, p)]))
    tops = per_strip[p.line_strip]
    offsets = np.full((len(tops), len(p.strips)), np.nan)
    offsets[:, p.line_strip] = 0
    for j, other in enumerate(per_strip):
        if j == p.line_strip or not len(other):
            continue
        #(where the strips are tracked, each line's top in the strip is looked for where the line above's offset puts
        #it, the first line's where the first ten lines' nearest tops in the strip put it)
        guess = 0
        if p.track_strips:
            near = [d for d in (other[np.argmin(abs(other - t))] - t for t in tops[:10]) if abs(d) < p.line_pitch / 2]
            guess = np.median(near) if near else 0
        for i, t in enumerate(tops):
            m = np.argmin(abs(other - t - guess))
            if abs(other[m] - t - guess) <= p.strip_reach:
                offsets[i, j] = other[m] - t
                guess = offsets[i, j] if p.track_strips else 0
    offsets = smooth_offsets(tops, offsets)
    centres = np.array([x0 + (a + b) / 2 for a, b in p.strips])
    bounds = np.array([x0 + b for a, b in p.strips[:-1]])
    #each line's character pitch and grid phase, from the centres of its glyphs. the pitch changes a little from line to
    #line (the copy was stretched unevenly), so it's taken as the median over the nearby lines
    lines, centres_x, pitch_x = [], [], []
    for i, t in enumerate(tops):
        line_tops = t + offsets[i]
        xs = []
        for j, (a, b) in enumerate(p.strips):
            y0 = int(round(line_tops[j]))
            band = ink[y0:y0 + p.band, x0 + a:x0 + b].any(0)
            xs += [a + (u + v - 1) / 2 for u, v in runs(band) if p.glyph_widths[0] <= v - u <= p.glyph_widths[1]]
        if len(xs) < 3:
            continue
        lines.append({'top': int(t), 'tops': line_tops, 'centres': centres, 'bounds': bounds,
                      'glyph_x': x0 + np.array(xs)})
        centres_x.append(np.array([x for x in xs if x >= p.pitch_from] or xs))
        pitch_x.append(np.array([x for x in xs if x < p.pitch_before]) if p.pitch_before else centres_x[-1])
    if not lines:
        return []
    fitted = np.full(len(lines), np.nan)
    for i, xs in enumerate(pitch_x):
        if len(xs) >= (10 if p.pitch_from and not p.pitch_before else 20):
            z = np.abs(np.exp(2j * np.pi * xs[None, :] / p.pitches[:, None]).mean(1))
            if z.max() > 0.8:
                fitted[i] = p.pitches[np.argmax(z)]
    if np.isnan(fitted).all():
        fitted[:] = p.pitch
    pitches = []
    for i in range(len(lines)):
        near = fitted[max(0, i - 4):i + 5]
        near = near[~np.isnan(near)]
        pitches.append(np.median(near) if len(near) else np.nanmedian(fitted))
    #which column is which: the sex and the time are always printed, with blanks around them. a line without them (a
    #heading) keeps to the line above's grid
    previous = None
    width = max(p.anchor_inked + p.anchor_blank) + 2
    for line, xs, pitch in zip(lines, centres_x, pitches):
        best = anchor(ink, line, xs, x0, pitch, p, width)
        if best[0] < p.anchor_least and p.anchor_pitch:
            tried = max((anchor(ink, line, xs, x0, other, p, width) for other in p.pitches[::5]),
                        key=lambda b: (b[0], -abs(b[2] - pitch)))
            if tried[0] >= p.anchor_least:
                best, pitch = tried, tried[2]
        phase = best[3]
        if best[0] < p.anchor_least and previous is not None:
            start = previous + np.round((x0 + phase - previous) / pitch) * pitch
        else:
            start = best[1]
        line.update({'x0': start, 'pitch': pitch, 'anchored': bool(best[0] >= p.anchor_least)})
        previous = start
    return drift(reanchor(ink, lines, p) if p.reanchor else lines, p)


def anchor(ink, line, xs, x0, pitch, p, width):
    #(score, x of column 0, pitch, phase): the line's grid at the pitch, its phase from the glyphs' centres, moved by up
    #to two columns to where the sex and time are inked, and the blanks around them aren't, most
    phase = np.angle(np.exp(2j * np.pi * xs / pitch).mean()) / (2 * np.pi) * pitch
    best = None
    for s in range(-p.anchor_reach, p.anchor_reach + 1):
        cells = inked(line_glyphs(ink, {**line, 'x0': x0 + phase + s * pitch, 'pitch': pitch}, p, width))
        score = cells[list(p.anchor_inked)].sum() - cells[list(p.anchor_blank)].sum()
        if best is None or score > best[0]:
            best = (score, x0 + phase + s * pitch, pitch, phase)
    return best


def reanchor(ink, lines, p, rounds=2):
    #a line whose sex and time are smudged can be placed a column off. so each line's grid is moved by up to two
    #columns to where its inked cells best fit the share of the block's lines with ink in each column
    chars = p.block_chars
    occ = np.array([inked(line_glyphs(ink, {**l, 'x0': l['x0'] - 2 * l['pitch']}, p, chars + 4)) for l in lines])
    rows = [i for i, l in enumerate(lines) if l['anchored']]
    if len(rows) < 10:
        return lines
    shift = np.zeros(len(lines), int)
    for _ in range(rounds):
        share = np.mean([occ[i, 2 + shift[i]:2 + shift[i] + chars] for i in rows], 0).clip(0.01, 0.99)
        hit, miss = np.log(share), np.log(1 - share)
        for i in range(len(lines)):
            scores = [(occ[i, 2 + s:2 + s + chars] * hit + ~occ[i, 2 + s:2 + s + chars] * miss).sum()
                      for s in range(-2, 3)]
            shift[i] = int(np.argmax(scores)) - 2
    for line, s in zip(lines, shift):
        line['x0'] += s * line['pitch']
        line['shift'] = int(s)
    return lines


def drift(lines, p):
    #the copy is stretched unevenly along a line too, so a stretch of glyphs can sit a pixel or two off the line's grid:
    #each column's offset is the median of the glyphs' offsets from the grid within a few columns of it. a line can
    #also be warped more than that, which the offsets carry too: its right part printed a column over (split: the
    #first column and the shift, from right_shift) or its block stretched from a column on (stretch: the column and
    #the pixels added a column, from block_pitch), its left part's columns stretched (lean, from left_stretch) or parts
    #of it moved (moved: each part's first column, the column after its last, the pixels its first column is moved and
    #the pixels added a column across it, from part_shifts), and each glyph is then the column whose warped place it's
    #nearest
    for line in lines:
        gx = line['glyph_x']
        split, s = line.get('split', (p.block_chars, 0))
        pivot, extra = line.get('stretch', (p.block_chars, 0))
        left_pivot, lean = line.get('lean', (0, 0))
        moved = line.get('moved', ())
        columns = np.arange(p.block_chars)
        warp = s * line['pitch'] * (columns >= split) + extra * np.maximum(columns - pivot, 0) \
            - lean * np.maximum(left_pivot - columns, 0) \
            + sum(((columns >= a) & (columns < b)) * (m + added * (columns - a)) for a, b, m, added in moved)
        if s or extra or lean or any(m or added for _, _, m, added in moved):
            places = line['x0'] + columns * line['pitch'] + warp
            c = np.abs(gx[:, None] - places[None, :]).argmin(1)
            r = gx - places[c]
        else:
            c = np.round((gx - line['x0']) / line['pitch'])
            r = gx - (line['x0'] + c * line['pitch'])
        offset = np.full(p.block_chars, np.nan)
        for col in range(p.block_chars):
            near = r[np.abs(c - col) <= p.drift_reach]
            if len(near) >= p.drift_least:
                offset[col] = np.clip(np.median(near), -p.drift_most, p.drift_most)
        known = ~np.isnan(offset)
        #a column with too few glyphs near it takes its neighbours' offset
        line['offset'] = np.interp(np.arange(p.block_chars), np.nonzero(known)[0], offset[known]) if known.any() \
            else np.zeros(p.block_chars)
        line['offset'] += warp
    return lines


def part_shifts(ink, lines, p):
    #where parts of a line are set off its grid (1980's, 1983's): the pixels each part is moved, the fraction of a
    #column its glyphs' centres sit off the line's grid and the whole columns that put the part's anchor columns where
    #they belong, most (the fewest columns where several do). where the copy is stretched unevenly across a page
    #(1983's), each part has a pitch of its own too, from its glyphs: the median over the nearby lines of theirs. a part
    #from column 0 has the glyphs left of the grid too
    owns = [[line['glyph_x'][((line['glyph_x'] >= line['x0'] + (a - 0.5) * line['pitch']) | (a == 0))
                             & (line['glyph_x'] < line['x0'] + (b - 0.5) * line['pitch'])] for line in lines]
            for a, b, *_ in p.moved_parts]
    pitches = []
    for part in owns:
        fitted = np.full(len(lines), np.nan)
        for i, own in enumerate(part):
            if p.part_pitches and len(own) >= 10:
                z = np.abs(np.exp(2j * np.pi * own[None, :] / p.pitches[:, None]).mean(1))
                fitted[i] = p.pitches[np.argmax(z)] if z.max() > 0.8 else np.nan
        near = [fitted[max(0, i - 4):i + 5] for i in range(len(lines))]
        pitches.append([np.nanmedian(v) if np.isfinite(v).any() else line['pitch'] for v, line in zip(near, lines)])
    for i, line in enumerate(lines):
        moved = []
        for (a, b, inked_columns, blank_columns), part, q in zip(p.moved_parts, owns, pitches):
            own, q = part[i], q[i]
            if len(own) < 3:
                continue
            start = line['x0'] + a * line['pitch']
            fraction = np.angle(np.exp(2j * np.pi * (own - start) / q).mean()) / (2 * np.pi) * q
            columns = np.arange(b)

            def score(s):
                warp = fraction + s * q + (columns - a) * (q - line['pitch'])
                glyphs = line_glyphs(ink, {**line, 'offset': warp}, p, b)
                core = p.glyph_w // 2
                cells = inked(glyphs) if p.part_core is None \
                    else glyphs[:, :, core - p.part_core:core + p.part_core + 1].sum((1, 2)) > 3
                return cells[list(inked_columns)].sum() - cells[list(blank_columns)].sum()

            best = max(range(-p.anchor_reach, p.anchor_reach + 1), key=lambda s: (score(s), -abs(s)))
            moved.append((a, b, fraction + best * q, q - line['pitch']))
        if p.typed_part:
            #the typed part: its glyphs' phase, and its first glyph in its first column, at the pitch of the part it's
            #left of. its glyphs are the runs of pixel columns in the line's cells with a glyph's ink (specks having
            #less) no higher than a line (a rule down the page being higher), from up to three columns left of the
            #line's grid, a run a few glyphs wide being that many touching glyphs
            first, end, bound = p.typed_part
            right = [(a, b, m, added) for a, b, m, added in moved if a <= bound < b]
            edge = int(line['x0'] + bound * line['pitch'] + sum(m + added * (bound - a) for a, b, m, added in right))
            q = line['pitch'] + sum(added for *_, added in right)
            x_lo = max(0, int(line['x0'] - 3 * line['pitch']))
            top = int(round(line_top(line, line['x0'] + first * line['pitch'], p)))
            band = ink[max(0, top - p.glyph_top):top + p.glyph_h - p.glyph_top, x_lo:edge]
            glyphs = [(u, v) for u, v in runs(band.any(0)) if band[:, u:v].sum() >= p.glyph_ink
                      and np.ptp(np.nonzero(band[:, u:v].any(1))[0]) < p.line_height[1]]
            own = np.array([x_lo + u + (j + 0.5) * (v - u) / n for u, v in glyphs
                            for n in [max(1, int(round((v - u) / q)))] for j in range(n)])
            if len(own):
                fraction = np.angle(np.exp(2j * np.pi * (own - line['x0']) / q).mean()) / (2 * np.pi) * q
                whole = np.round((own[0] - line['x0'] - fraction) / q) - first
                moved.append((0, end, fraction + whole * q, q - line['pitch']))
                u, v = glyphs[0]
                rows = np.nonzero(band[:, u:v].any(1))[0]
                line['typed_first'], line['typed_height'] = own[0], int(rows[-1] - rows[0] + 1)
        line['moved'] = moved
    return lines


def typed_in(lines, glyphs, p, near=6):
    #where lines were typed in after the list was printed (1983's), in another face and with no place: those whose
    #typed part doesn't start with a place's digit (place_height high) where the places start on the lines around it
    #in its section (a class typed on its own being smaller, or further right), and whose time isn't the printer's: not
    #a glyph in each of its columns (the typed time being shorter, at another pitch), or not where the line anchors
    span = sorted(p.time_columns + tuple(p.punctuation))
    full = [l.get('typed_first', np.nan) if l.get('typed_height', 0) >= p.place_height else np.nan for l in lines]
    section = np.cumsum([0] + [b['top'] - a['top'] > 1.5 * p.line_pitch for a, b in zip(lines, lines[1:])])
    for i, (line, cells) in enumerate(zip(lines, inked(glyphs))):
        around = [full[j] for j in range(max(0, i - near), min(len(lines), i + near + 1))
                  if j != i and section[j] == section[i] and np.isfinite(full[j])]
        placed = np.isfinite(full[i]) and around and abs(full[i] - np.median(around)) < 1.5 * line['pitch']
        line['added'] = bool(not placed and (not cells[span].all() or not line['anchored']))
    return lines


def right_anchored(ink, line, p):
    #whether the right anchor's columns are inked and blank as they should be
    split, inked_columns, blank_columns = p.right_anchor
    cells = inked(line_glyphs(ink, line, p))
    return cells[list(inked_columns)].all() and not cells[list(blank_columns)].any()


def block_pitch(ink, lines, p, least=0.5):
    #where the copy is stretched across a block so that its glyphs can't give each line's pitch (1987's page 37), and
    #so fewer than half its result lines have the right anchor where it belongs: the stretch from the middle of the
    #left anchor (the time) on, in pixels added a column, that puts it there on the most lines
    if not lines or np.mean([right_anchored(ink, l, p) for l in lines]) >= least:
        return lines
    pivot = int(round(np.mean(p.anchor_inked)))

    def stretched(line, extra):
        return drift([{**line, 'stretch': (pivot, extra)}], p)[0]

    best = max(np.arange(-0.4, 0.41, 0.02), key=lambda e: sum(right_anchored(ink, stretched(l, e), p) for l in lines))
    return [stretched(l, best) for l in lines]


def left_stretch(ink, lines, p, most=0.9, step=0.02, near=0.06, window=10):
    #where the copy stretches a block's left part against its right, the stretch of each line (pixels added a column,
    #from the left anchor's column leftwards: lean, for drift). the stretch changes down a block (1981's copy is turned
    #a little), so each line takes the one that puts the left anchor where it belongs on it nearest the median over the
    #nearby lines of theirs, starting from the one that does on the most lines of the block
    pivot, inked_columns, blank_columns = p.left_anchor
    chars = max(inked_columns + blank_columns) + 1
    left = np.maximum(pivot - np.arange(chars), 0)

    def fits(line, lean):
        cells = inked(line_glyphs(ink, {**line, 'offset': -lean * left}, p, chars))
        return cells[list(inked_columns)].all() and not cells[list(blank_columns)].any()

    leans = np.round(np.arange(-most, most + step / 2, step), 2)
    hits = np.array([[fits(line, lean) for lean in leans] for line in lines])
    if not len(lines) or not hits.any():
        return lines
    guides = np.full(len(lines), leans[hits.sum(0).argmax()])
    for _ in range(2):
        #each line's run of fitting stretches nearest its guide, by its middle, and the guide the nearby lines' median
        middles = np.full(len(lines), np.nan)
        for i, row in enumerate(hits):
            spans = [(leans[a], leans[b - 1]) for a, b in runs(row)]
            if spans:
                lo, hi = min(spans, key=lambda span: max(span[0] - guides[i], guides[i] - span[1], 0))
                middles[i] = (lo + hi) / 2
        for i in range(len(lines)):
            nearby = middles[max(0, i - window):i + window + 1]
            nearby = nearby[~np.isnan(nearby)]
            guides[i] = np.median(nearby) if len(nearby) else guides[i]
    for line, row, guide in zip(lines, hits, guides):
        own = [lean for lean, hit in zip(leans, row) if hit and abs(lean - guide) <= near + 1e-9]
        line['lean'] = (pivot, min(own, key=lambda lean: abs(lean - guide)) if own else guide)
    return lines


def right_shift(ink, lines, p):
    #where a printer shifts the right part of some lines by a column (1987's, after the name), the shift that puts the
    #printer's right_anchor (the first column it shifts from, the columns every result line inks there and those it
    #leaves blank) where it belongs, when one does better than none
    split, inked_columns, blank_columns = p.right_anchor
    for line in lines:
        cells = inked(line_glyphs(ink, line, p))

        def score(s):
            return cells[[c + s for c in inked_columns]].sum() - cells[[c + s for c in blank_columns]].sum()

        best = max((-1, 0, 1), key=score)
        if score(best) > score(0):
            line['split'] = (split, best)
    return lines


def fitted_tops(ink, lines, p):
    #each line's cells moved up or down (by up to the printer's fit_tops pixels) to where their ink, row by row, best
    #fits the block's: the median over its lines. the line's top as found stays its key
    most = p.fit_tops
    tall = copy.copy(p)
    tall.glyph_h, tall.glyph_top = p.glyph_h + 2 * most, p.glyph_top + most
    profiles = np.array([line_glyphs(ink, l, tall).sum((0, 2)) for l in lines], float)
    template = np.median(profiles[:, most:most + p.glyph_h], 0)
    for line, profile in zip(lines, profiles):
        fits = [np.corrcoef(profile[most + dy:most + dy + p.glyph_h], template)[0, 1] for dy in range(-most, most + 1)]
        fits = np.nan_to_num(fits, nan=-1)
        line['tops'] = line['tops'] + int(np.argmax(fits)) - most
    return lines


def line_top(line, x, p):
    #the line's top at pixel x: between the tops in its strips' middles, or where the strips are tracked (1983's, whose
    #typed part is a strip of its own) the top in its strip
    if p.track_strips:
        return line['tops'][np.searchsorted(line['bounds'], x)]
    return np.interp(x, line['centres'], line['tops'])


def inked(cells):
    #the cells that hold a character: ink inside the cell's edge columns, which pick up the edges of the glyphs on
    #either side, wide ones like M and W especially
    return cells[..., 1:cells.shape[-1] - 1].sum((-2, -1)) > 3


def line_glyphs(ink, line, p, chars=None):
    #the ink of each of the line's character cells, the printer's glyph_h by glyph_w, the top row glyph_top pixels above
    #the line's top
    chars = p.block_chars if chars is None else chars
    out = np.zeros((chars, p.glyph_h, p.glyph_w), bool)
    offset = line.get('offset')
    for c in range(chars):
        cx = line['x0'] + c * line.get('pitch', p.pitch) + (offset[c] if offset is not None and c < len(offset) else 0)
        top = line_top(line, cx, p)
        x, y = int(round(cx)) - p.glyph_w // 2, int(round(top)) - p.glyph_top
        if y < 0 or x < 0:
            continue
        cell = ink[y:y + p.glyph_h, x:x + p.glyph_w]
        out[c, :cell.shape[0], :cell.shape[1]] = cell
    return out


def table_lines(lines, top, gap):
    #the lines that run down from the top of the table with no gap of more than two lines missing: a block can stop
    #short at a photo, and a photo can look like a line or a few
    out = []
    for line in lines:
        if line['top'] > (out[-1]['top'] if out else top) + gap:
            break
        out.append(line)
    return out


@functools.lru_cache(maxsize=None)
def block_glyphs(year, page, k):
    #the block's result lines (those with a sex and a time where they belong, down from the top of the table, where the
    #first block's first one is, and any line between them, whose sex and time an underline or a smudge hides, and
    #the year's EXTRA_LINES after them) and their cells' ink, each line with the list it's in (run: 0 for the first
    #in the block, 1 for a list that starts below the end of another), and the year's LEADING_LINES before them. where
    #the printer has a right anchor, the block's pitch and each line's right part are then fitted to it
    p = page_printer(year, page)
    ink = block_ink(year, page, k)
    own = getattr(layout(year), 'BLOCK_TOP', {}).get((page, k + 1))
    top = own if own is not None else table_top(year, page) or 0
    lines = block_lines(year, page, k)
    first = [l['top'] for l in (lines if own is not None else block_lines(year, page, 0))
             if l['anchored'] and l['top'] >= top]
    anchored = [l for l in lines if l['anchored'] and l['top'] >= top]
    start = first[0] if first else 0
    found = []
    for r in range(len(block_genders(year, page, k))):
        run = table_lines(anchored, start, p.table_gap * p.line_pitch)
        if not run:
            break
        found += [{**l, 'run': r} for l in lines if run[0]['top'] <= l['top'] <= run[-1]['top']]
        anchored = [l for l in anchored if l['top'] > run[-1]['top']]
        start = anchored[0]['top'] if anchored else 0
    extra = getattr(layout(year), 'EXTRA_LINES', {}).get((page, k + 1), 0)
    leading = getattr(layout(year), 'LEADING_LINES', {}).get((page, k + 1), 0)
    before = [{**l, 'run': 0} for l in lines if found and l['top'] < found[0]['top']]
    after = [{**l, 'run': found[-1]['run']} for l in lines if found and l['top'] > found[-1]['top']]
    lines = (before[len(before) - leading:] if leading else []) + found + after[:extra]
    if p.right_anchor:
        lines = drift(right_shift(ink, block_pitch(ink, [dict(l) for l in lines], p), p), p)
    if p.left_anchor:
        lines = drift(left_stretch(ink, [dict(l) for l in lines], p), p)
    if p.moved_parts or p.typed_part:
        lines = drift(part_shifts(ink, [dict(l) for l in lines], p), p)
    if p.fit_tops and lines:
        lines = fitted_tops(ink, [dict(l) for l in lines], p)
    glyphs = np.array([line_glyphs(ink, l, p) for l in lines]) if lines \
        else np.zeros((0, p.block_chars, p.glyph_h, p.glyph_w), bool)
    if p.typed_part:
        #(a typed glyph wider than the printer's spills into the cells beside it, so a typed cell with no ink near its
        #middle is blank)
        core = p.glyph_w // 2
        end = p.typed_part[1]
        empty = ~glyphs[:, :end, :, core - p.part_core:core + p.part_core + 1].any((2, 3))
        glyphs[:, :end][empty] = False
        lines = typed_in(lines, glyphs, p)
    return lines, to_year_columns(year, page, glyphs)


def tesseract_words(year, page, k, scale=2):
    #tesseract's words in the block, boxes in the upright page's pixels
    path = page_file(year, page, 'b{}.tsv'.format(k + 1))
    if not os.path.exists(path):
        return pd.DataFrame(columns=['text', 'left', 'top', 'width', 'height', 'conf'])
    words = pd.read_csv(path, sep='\t', quoting=3, dtype={'text': str}, keep_default_na=False)
    words = words[(words['level'] == 5) & (words['text'].str.strip() != '')].copy()
    xoff = max(0, blocks(year, page)[k] - 20)
    words[['left', 'top', 'width', 'height']] = words[['left', 'top', 'width', 'height']] / scale
    words['left'] += xoff
    return words


def tesseract_labels(year, page, k, lines, glyphs):
    #{(line, column): character} where one of tesseract's words covers as many inked cells as it has characters. none
    #on a page in another layout, whose columns aren't the year's
    p = printer(year)
    ink = inked(glyphs)
    out = {}
    if page in getattr(layout(year), 'COLUMN_MAPS', {}):
        return out
    for _, w in tesseract_words(year, page, k).iterrows():
        yc = w['top'] + w['height'] / 2
        xl, xr = w['left'], w['left'] + w['width']
        for i, line in enumerate(lines):
            top = line_top(line, (xl + xr) / 2, p)
            if abs(yc - (top + p.middle)) <= p.middle_slack:
                #where the copy stretches the line's left part or moves parts of it, its columns are where that puts
                #them
                pivot, lean = line.get('lean', (0, 0))
                moved = line.get('moved', ())
                cols = [c for c in range(p.block_chars) if ink[i, c]
                        and xl - 3 <= line['x0'] + c * line['pitch'] - lean * max(pivot - c, 0)
                        + sum(m + added * (c - a) for a, b, m, added in moved if a <= c < b) <= xr + 3]
                if len(cols) == len(w['text']):
                    out.update({(i, c): ch for c, ch in zip(cols, w['text'])})
                break
    return out


#---------------------------------------------------------------- reading the glyphs

def result_lines(year):
    #every result line, in order: (page, block, line, gender, line geometry) and the ink of its cells. a place with no
    #line to read, a line left blank inside a block (line -1) or one of the year's MISSING_LINES at its foot, is kept as
    #a line with no geometry and no ink, so the places after it still count up. a line the year's HAND drops is left out
    p = printer(year)
    keys, glyphs = [], []
    missing = getattr(layout(year), 'MISSING_LINES', {})
    blank = np.zeros((1, p.block_chars, p.glyph_h, p.glyph_w), bool)
    for page, k in block_order(year):
        genders = block_genders(year, page, k)
        lines, g = block_glyphs(year, page, k)
        for i, line in enumerate(lines):
            gender = genders[line['run']]
            same = i and lines[i - 1]['run'] == line['run']
            gap = int(round((line['top'] - lines[i - 1]['top']) / p.line_pitch)) - 1 if same else 0
            gap = 0 if p.section_gaps else max(0, gap - p.separator_lines)
            keys += [(page, k, -1, gender, None)] * gap
            glyphs += [blank] * gap
            #a line HAND drops is no place, though it spaces the lines around it
            if not hand(year, page, k + 1, line['top']).get('drop'):
                keys.append((page, k, i, gender, line))
                glyphs.append(g[i:i + 1])
        n = missing.get((page, k + 1), 0)
        keys += [(page, k, len(lines) + i, genders[-1], None) for i in range(n)]
        glyphs += [blank] * n
    return keys, np.concatenate(glyphs)


def shifted(cells):
    #each cell moved by up to a pixel each way: 9 arrays of flattened cells
    h, w = cells.shape[1:]
    padded = np.pad(cells, ((0, 0), (1, 1), (1, 1)))
    return [padded[:, dy:dy + h, dx:dx + w].reshape(len(cells), -1).astype(np.float32)
            for dy in range(3) for dx in range(3)]


def aligned(cells, template):
    #each cell at the shift that best matches the template
    moved = np.stack(shifted(cells))
    d = ((moved - template.reshape(-1)) ** 2).sum(2)
    return moved[d.argmin(0), np.arange(len(cells))].reshape(cells.shape)


def nearest_template(cells, templates, chunk=20000, allowed=None):
    #each cell's nearest template, of those allowed it where given
    flat = templates.reshape(len(templates), -1).astype(np.float32)
    out = []
    for a in range(0, len(cells), chunk):
        d = np.stack([(s ** 2).sum(1)[:, None] - 2 * s @ flat.T + (flat ** 2).sum(1)
                      for s in shifted(cells[a:a + chunk])]).min(0)
        if allowed is not None:
            d = np.where(allowed[a:a + chunk], d, np.inf)
        out.append(d.argmin(1))
    return np.concatenate(out)


def training_cells(year, keys):
    #(line, column, character) known for sure: the places (which count up by one in each gender's list, so the n-th
    #line holds place n), the sex and the class's first letter, and the time's colons and point. and the letters
    #tesseract read, where its words line up with the grid
    p = printer(year)
    sure, read = [], []
    place = {g: first - 1 for g, first in first_places(year).items()}
    skips = getattr(layout(year), 'RANK_SKIPS', {})
    labels = {}
    for n, (page, k, i, gender, line) in enumerate(keys):
        if (page, k) not in labels:
            labels[(page, k)] = {}
            for (i2, c), ch in tesseract_labels(year, page, k, *block_glyphs(year, page, k)).items():
                labels[(page, k)].setdefault(i2, []).append((c, ch))
        #a line typed in after the list was printed has no place printed, and is in another face
        if line and line.get('added'):
            continue
        place[gender] += 1 + skips.get((page, k + 1, i + 1), 0)
        digits = str(place[gender])
        for c, ch in zip(p.place_columns, digits.ljust(len(p.place_columns)) if p.place_left
                         else digits.rjust(len(p.place_columns))):
            if ch != ' ':
                sure.append((n, c, ch))
        sure += [(n, c, gender) for c in p.sex_columns] + [(n, c, ch) for c, ch in p.punctuation.items()]
        read += [(n, c, ch) for c, ch in labels[(page, k)].get(i, [])
                 if (ch.upper() in LETTERS + '-&' or ch in p.label_marks or p.digit_labels and ch in DIGITS)
                 and not (ch in 'MF' and p.sex_columns)]
    return sure, read


def by_char(cells):
    out = {}
    for n, c, ch in cells:
        out.setdefault(ch, []).append((n, c))
    return {ch: np.array(v) for ch, v in out.items() if len(v) >= 15}


def learn(year, keys, glyphs, rounds=2):
    #first a linear discriminant over the cells' pixels (each character's mean cell and the cells' shared spread about
    #their means), learned from the cells known for sure and tesseract's letters where the nearest mean cell agrees
    #with it. tesseract mixes up M, H, N and W, and D and O, so the letters are then learned again from the names and
    #towns read as a word seen in the clean results, or one letter off one, the letter off being the reading's
    #runner-up. the discriminant mixes up the printer's 5 and 6, 6 and 8, 1 and 7, so last a small neural network is
    #learned from those cells and the digits the tables pin down whatever the reading (pinned_cells)
    p = printer(year)
    sure, read = training_cells(year, keys)
    ink = inked(glyphs)
    sure = [s for s in sure if ink[s[0], s[1]]]
    read = [r for r in read if ink[r[0], r[1]]]
    if p.digit_labels:
        #(tesseract's letters and digits only where the column holds them: it reads a 0 in the class column as Q now
        #and then. its points, commas and hyphens anywhere, specks and the dashes of a rule among them)
        read = [r for r in read if r[2] in p.label_marks + '-' or r[2].upper() in p.column_characters[r[1]]]
    first = by_char(sure + read)
    chars = sorted(first)
    templates = np.array([glyphs[first[ch][:, 0], first[ch][:, 1]].mean(0) for ch in chars])
    idx = np.array([(n, c) for n, c, _ in read])
    #(with tesseract's digits, only among the characters the cell's column holds, so a letter O isn't taken for the
    #0 the times teach)
    allowed = np.array([[ch.upper() in p.column_characters[c] for ch in chars] for c in idx[:, 1]]) \
        if p.digit_labels else None
    nearest = np.array(chars)[nearest_template(glyphs[idx[:, 0], idx[:, 1]], templates, allowed=allowed)]
    letters = [r for r, ch in zip(read, nearest) if r[2] == ch]
    model = discriminant(glyphs, by_char(sure + letters))
    for _ in range(rounds):
        words = lexicon_cells(glyphs, model, p)
        #the rare letters keep tesseract's too
        counts = by_char(words)
        rare = [r for r in letters if r[2] not in counts or len(counts[r[2]]) < 200]
        model = discriminant(glyphs, by_char(sure + words + rare))
    #the network learns twice, the second time from the names, towns and pinned digits as the first network reads them
    for _ in range(2):
        pinned = [c for c in pinned_cells(keys, read_text(glyphs, model, p)[0], p, pace_km(year))
                  if ink[c[0], c[1]]]
        model = network(glyphs, by_char(sure + pinned + words + rare))
        words = lexicon_cells(glyphs, model, p)
        counts = by_char(words)
        rare = [r for r in letters if r[2] not in counts or len(counts[r[2]]) < 200]
    return model


def read_text(glyphs, model, p):
    #every line's characters, their runners-up, the margins between them and the third choices
    ink = inked(glyphs)
    n, c = np.nonzero(ink)
    #(and where the network learned small letters but not l, 1983's, whose l it reads as I)
    cased = 'I' in model[1] and ('l' in model[1] or p.small_l)
    best, second, margin, third, *case = read_cells(glyphs[n, c], c, model, p, third=True, cased=cased)
    text = np.full(ink.shape, ' ', dtype='<U1')
    alt = np.full(ink.shape, ' ', dtype='<U1')
    alt2 = np.full(ink.shape, ' ', dtype='<U1')
    sure = np.full(ink.shape, np.inf)
    text[n, c], alt[n, c], sure[n, c], alt2[n, c] = best, second, margin, third
    if cased:
        lettered = np.full(ink.shape, ' ', dtype='<U1')
        lettered[n, c] = case[0]
        capital_i(text, alt, lettered)
    return text, alt, sure, alt2


def capital_i(text, alt, lettered):
    #where a printer's capital I and small l look the same (1982's), or the network never learned l (1983's), each is
    #the one the case of the other letters of its word calls for: I among capitals or on its own, L among small
    #letters. the other becomes the runner-up
    for i in range(len(text)):
        line = lettered[i]
        for a, b in runs(line != ' '):
            word = line[a:b]
            others = [ch for ch in word if ch.isalpha() and ch not in 'lI']
            small = sum(ch.islower() for ch in others) > len(others) / 2
            for j in range(a, b):
                if line[j] in 'lI' and text[i, j] in 'LI':
                    want = 'L' if small else 'I'
                    if text[i, j] != want:
                        alt[i, j], text[i, j] = text[i, j], want


def pinned_cells(keys, text, p, pace_km):
    #(line, column, digit) that the tables pin down whatever the reading: the leading digits of a time that the times
    #placed just before and after it share, the PACE column's digits that every time within a second or so of the
    #line's gives, and the class's age digits where the reading is one digit off one class only
    out = []
    lines = [''.join(t) for t in text]
    genders = [k[3] for k in keys]
    for gender in sorted(set(genders)):
        rows = [n for n, g in enumerate(genders) if g == gender]
        d = [''.join(lines[n][c] for c in p.time_columns) for n in rows]
        secs = np.array([seconds(time_text(x)) if x.isdigit() and time_text(x) else np.nan for x in d])
        keep = longest_rising(secs)
        for i, n in enumerate(rows):
            if 0 < i < len(rows) - 1 and i - 1 in keep and i + 1 in keep:
                a, b = d[i - 1], d[i + 1]
                for k in range(len(p.time_columns)):
                    if a[:k + 1] != b[:k + 1]:
                        break
                    out.append((n, p.time_columns[k], a[k]))
            if p.pace_columns and i in keep and i - 1 in keep and i + 1 in keep:
                paces = {'{:>2}:{:02d}'.format(*divmod(int(round(q)), 60))
                         for q in np.arange(secs[i] / pace_km - 1.6, secs[i] / pace_km + 1.65, 0.1)}
                for j, col in enumerate(p.pace_columns):
                    chars = {pace[j + (j >= 2)] for pace in paces}
                    if len(chars) == 1 and chars != {' '}:
                        out.append((n, col, chars.pop()))
    ages = [a.replace('-', '') for a in p.ages if '-' in a]
    for n, line in enumerate(lines):
        age = ''.join(line[c] for c in p.age_columns)
        close = [a for a in ages if sum(x == y for x, y in zip(a, age)) >= 3]
        if len(close) == 1:
            out += [(n, c, ch) for c, ch in zip(p.age_columns, close[0])]
    return out


@functools.lru_cache(maxsize=None)
def lexicon():
    #every word of the names and towns in the clean results, upper case: {word}, and {(length, position, word with that
    #letter blanked): [words]}
    clean = load_all_results()
    words = set()
    for col in ('first', 'middle', 'last', 'city'):
        for text in clean[col].dropna().unique():
            words.update(w.upper() for w in re.findall(r'[a-z]+', str(text).lower()) if len(w) >= 3)
    near = {}
    for w in words:
        for i in range(len(w)):
            near.setdefault(w[:i] + '?' + w[i + 1:], []).append(w)
    return frozenset(words), near


def lexicon_cells(glyphs, model, p):
    #(line, column, letter) for the name and town words read as a known word, or as one letter off exactly one known
    #word where that letter's runner-up makes it
    words, near = lexicon()
    cols = np.arange(p.fields['name'][0], p.fields['town'][1])
    cells = glyphs[:, cols]
    ink = inked(cells)
    n, c = np.nonzero(ink)
    best, second, _, case = read_cells(cells[n, c], cols[c], model, p, cased=True)
    text = np.full(ink.shape, ' ', dtype='<U1')
    alt = np.full(ink.shape, ' ', dtype='<U1')
    lettered = np.full(ink.shape, ' ', dtype='<U1')
    text[n, c], alt[n, c], lettered[n, c] = best, second, case
    out = []
    for i in range(len(cells)):
        line = ''.join(text[i])
        for m in re.finditer(r'[A-Z]{3,}', line):
            word, start = m.group(), m.start()
            if word in words:
                fixed = word
            else:
                fits = {w for j in range(len(word)) for w in near.get(word[:j] + '?' + word[j + 1:], [])
                        if w[j] == alt[i, start + j]}
                if len(fits) != 1:
                    continue
                fixed = fits.pop()
            #in the case most of its letters are read in (I and l aside, which some printers print alike), a word in
            #small letters keeping its first letter's capital ("Daniel")
            read = lettered[i, start:start + len(word)]
            others = [ch for ch in read if ch not in 'lI']
            small = sum(ch.islower() for ch in others) > len(others) / 2
            out += [(i, cols[start + j], ch.lower() if small and not (j == 0 and read[0].isupper()) else ch)
                    for j, ch in enumerate(fixed)]
    return out


def discriminant(glyphs, final):
    chars = sorted(final)
    rng = np.random.RandomState(0)
    mus, spread = [], []
    for ch in chars:
        cells = final[ch]
        if len(cells) > 3000:
            cells = cells[rng.choice(len(cells), 3000, replace=False)]
        x = glyphs[cells[:, 0], cells[:, 1]]
        x = aligned(x, aligned(x, x.mean(0)).mean(0)).reshape(len(x), -1)
        mus.append(x.mean(0))
        spread.append(x - x.mean(0))
    spread = np.concatenate(spread)
    inv = np.linalg.inv(spread.T @ spread / len(spread) + 0.02 * np.eye(spread.shape[1]))
    mus = np.array(mus)
    weights = mus @ inv
    return 'lda', chars, weights.astype(np.float32), (-0.5 * (weights * mus).sum(1)).astype(np.float32)


def network(glyphs, final, hidden=128, epochs=20, per_char=4000, batch=256, seed=0):
    #a network with one hidden layer, learned from each character's cells (up to per_char of them), each moved by up to
    #a pixel each way at random
    chars = sorted(final)
    rng = np.random.RandomState(seed)
    idx, target = [], []
    for k, ch in enumerate(chars):
        cells = final[ch]
        if len(cells) > per_char:
            cells = cells[rng.choice(len(cells), per_char, replace=False)]
        idx.append(cells)
        target.append(np.full(len(cells), k))
    idx, target = np.concatenate(idx), np.concatenate(target)
    padded = np.pad(glyphs[idx[:, 0], idx[:, 1]], ((0, 0), (1, 1), (1, 1)))
    glyph_h, glyph_w = glyphs.shape[2:]
    n, size, classes = len(idx), glyph_h * glyph_w, len(chars)
    params = [rng.randn(size, hidden).astype(np.float32) * np.sqrt(2 / size), np.zeros(hidden, np.float32),
              rng.randn(hidden, classes).astype(np.float32) * np.sqrt(1 / hidden), np.zeros(classes, np.float32)]
    moments = [(np.zeros_like(p), np.zeros_like(p)) for p in params]
    step = 0
    for epoch in range(epochs):
        rate = 1e-3 * 0.85 ** epoch
        order, moves = rng.permutation(n), rng.randint(0, 9, n)
        for a in range(0, n, batch):
            b = order[a:a + batch]
            x = np.empty((len(b), size), np.float32)
            for m in range(9):
                sel = moves[b] == m
                x[sel] = padded[b[sel], m // 3:m // 3 + glyph_h, m % 3:m % 3 + glyph_w].reshape(-1, size)
            h = np.maximum(x @ params[0] + params[1], 0)
            p = softmax(h @ params[2] + params[3])
            p[np.arange(len(b)), target[b]] -= 1
            p /= len(b)
            dh = (p @ params[2].T) * (h > 0)
            grads = [x.T @ dh, dh.sum(0), h.T @ p, p.sum(0)]
            step += 1
            for param, grad, (m1, m2) in zip(params, grads, moments):
                m1 *= 0.9
                m1 += 0.1 * grad
                m2 *= 0.999
                m2 += 0.001 * grad ** 2
                param -= rate * (m1 / (1 - 0.9 ** step)) / (np.sqrt(m2 / (1 - 0.999 ** step)) + 1e-8)
    return ('net', chars, *params)


def softmax(z):
    z = np.exp(z - z.max(1, keepdims=True))
    return z / z.sum(1, keepdims=True)


def scores(flat, model):
    #each cell's score for each character: the discriminant's, or the network's log probability
    if model[0] == 'lda':
        _, _, weights, bias = model
        return flat @ weights.T + bias
    if model[0] == 'nets':
        return np.mean([scores(flat, m) for m in model[2]], 0)
    _, _, w1, b1, w2, b2 = model
    z = np.maximum(flat @ w1 + b1, 0) @ w2 + b2
    z = z - z.max(1, keepdims=True)
    return z - np.log(np.exp(z).sum(1, keepdims=True))


def read_cells(cells, columns, model, p, chunk=20000, third=False, cased=False):
    #each cell's character, the runner-up and the margin between their scores, among the characters its column holds,
    #at the best of the cell's moves by up to a pixel each way. a letter learned in both cases scores as the better of
    #the two, and is read as its capital. and the third choice, when asked, and the best character in its own case
    chars = model[1]
    capitals = list(dict.fromkeys(ch.upper() for ch in chars))
    folded = [[j for j, ch in enumerate(chars) if ch.upper() == u] for u in capitals]
    capital_of = np.array([capitals.index(ch.upper()) for ch in chars])
    allowed = np.array([[u in p.column_characters[c] for u in capitals] for c in range(p.block_chars)])
    best, second, margin, thirds, cases = [], [], [], [], []
    for a in range(0, len(cells), chunk):
        raw = np.stack([scores(s, model) for s in shifted(cells[a:a + chunk])]).max(0)
        score = raw if capitals == list(chars) else np.stack([raw[:, js].max(1) for js in folded], 1)
        score = np.where(allowed[columns[a:a + chunk]], score, -np.inf)
        order = np.argsort(-score, 1)[:, :3]
        top = np.take_along_axis(score, order, 1)
        best.append(order[:, 0])
        second.append(np.where(np.isfinite(top[:, 1]), order[:, 1], order[:, 0]))
        thirds.append(np.where(np.isfinite(top[:, 2]), order[:, 2], order[:, 0]))
        margin.append(np.where(np.isfinite(top[:, 1]), top[:, 0] - top[:, 1], np.inf))
        if cased:
            cases.append(np.where(capital_of[None, :] == order[:, :1], raw, -np.inf).argmax(1))
    out = (np.array(capitals)[np.concatenate(best)], np.array(capitals)[np.concatenate(second)],
           np.concatenate(margin))
    out += (np.array(capitals)[np.concatenate(thirds)],) if third else ()
    return out + (np.array(chars)[np.concatenate(cases)],) if cased else out


def read_year(year):
    #every result line's characters as <page>_grid.tsv: the line's top, its characters, each one's runner-up and how
    #sure the reading is (0-9: the network's log probability over the runner-up's, capped)
    keys, glyphs = result_lines(year)
    model = learn(year, keys, glyphs)
    text, alt, margin, alt2 = read_text(glyphs, model, printer(year))
    sure = np.clip(np.nan_to_num(margin, posinf=99), 0, 9).astype(int).astype(str)
    rows = [{'page': page, 'block': k + 1, 'line': i + 1, 'gender': gender, 'top': line['top'] if line else '',
             'text': '|' + ''.join(text[m]) + '|', 'alt': '|' + ''.join(alt[m]) + '|',
             'sure': '|' + ''.join(sure[m]) + '|', 'alt2': '|' + ''.join(alt2[m]) + '|',
             **({'added': int(bool(line and line.get('added')))} if printer(year).typed_part else {})}
            for m, (page, k, i, gender, line) in enumerate(keys)]
    df = pd.DataFrame(rows)
    for page, lines in df.groupby('page'):
        lines.to_csv(grid_path(year, page), sep='\t', index=False)
    return df.astype(str)


def grid_path(year, page):
    return page_file(year, page, 'grid.tsv')


def grid(year):
    #the glyph reading, made once (about two minutes) and kept in old_results/ocr/<year>/
    pages = layout(year).PAGES
    if not all(os.path.exists(grid_path(year, page)) for page in pages):
        df = read_year(year)
    else:
        df = pd.concat([pd.read_csv(grid_path(year, page), sep='\t', dtype=str, keep_default_na=False, quoting=3)
                        for page in pages], ignore_index=True)
    #the lines in the order the list runs, which the pages' files keep page by page
    order = {key: n for n, key in enumerate(block_order(year))}
    df = df.iloc[sorted(range(len(df)), key=lambda i: order[(int(df['page'].iat[i]), int(df['block'].iat[i]) - 1)])]
    df = df.reset_index(drop=True)
    for col in ('text', 'alt', 'sure', 'alt2'):
        df[col] = df[col].str[1:-1]
    return df


#---------------------------------------------------------------- the results

PROVINCES = {'ONT': 'ON', 'MAN': 'MB', 'QUE': 'QC', 'QU': 'QC', 'SAS': 'SK', 'SA': 'SK', 'SASK': 'SK', 'ALT': 'AB',
             'ALB': 'AB', 'BC': 'BC', 'NB': 'NB', 'NS': 'NS', 'PEI': 'PE', 'NFL': 'NL'}
#the first three digits of each state's zip codes
ZIP3 = [(10, 27, 'MA'), (28, 29, 'RI'), (30, 38, 'NH'), (39, 49, 'ME'), (50, 59, 'VT'), (60, 69, 'CT'), (70, 89, 'NJ'),
        (100, 149, 'NY'), (150, 196, 'PA'), (197, 199, 'DE'), (200, 205, 'DC'), (206, 219, 'MD'), (220, 246, 'VA'),
        (247, 268, 'WV'), (270, 289, 'NC'), (290, 299, 'SC'), (300, 319, 'GA'), (320, 349, 'FL'), (350, 369, 'AL'),
        (370, 385, 'TN'), (386, 397, 'MS'), (400, 427, 'KY'), (430, 458, 'OH'), (460, 479, 'IN'), (480, 499, 'MI'),
        (500, 528, 'IA'), (530, 549, 'WI'), (550, 567, 'MN'), (570, 577, 'SD'), (580, 588, 'ND'), (590, 599, 'MT'),
        (600, 629, 'IL'), (630, 658, 'MO'), (660, 679, 'KS'), (680, 693, 'NE'), (700, 714, 'LA'), (716, 729, 'AR'),
        (730, 749, 'OK'), (750, 799, 'TX'), (800, 816, 'CO'), (820, 831, 'WY'), (832, 838, 'ID'), (840, 847, 'UT'),
        (850, 865, 'AZ'), (870, 884, 'NM'), (889, 898, 'NV'), (900, 961, 'CA'), (967, 968, 'HI'), (970, 979, 'OR'),
        (980, 994, 'WA'), (995, 999, 'AK')]
#a province's postal codes start with its letter
POSTAL = {'A': 'NL', 'B': 'NS', 'C': 'PE', 'E': 'NB', 'G': 'QC', 'H': 'QC', 'J': 'QC', 'K': 'ON', 'L': 'ON', 'M': 'ON',
          'N': 'ON', 'P': 'ON', 'R': 'MB', 'S': 'SK', 'T': 'AB', 'V': 'BC'}


def zip_state(z):
    z = z.replace('D', '0').replace('O', '0')
    if re.fullmatch(r'\d{5}', z):
        return next((s for a, b, s in ZIP3 if a <= int(z[:3]) <= b), '')
    if re.fullmatch(r'[A-Z]\d[A-Z]\d[A-Z]\d', z):
        return POSTAL.get(z[0], '')
    return ''


def cells(row, field, p, third=False):
    a, b = p.fields[field]
    out = row['text'][a:b], row['alt'][a:b], row['sure'][a:b]
    return out + (row['alt2'][a:b],) if third else out


def clean_words(text):
    #a field's words (a comma between them, as in "FLOOD, ROBERT"), without specks read as stray points at their ends
    return ' '.join(w.strip(".'-") for w in text.replace(',', ' ').split() if w.strip(".'-"))


def seconds(t):
    return parse_seconds(t) if t else np.nan


def kept_digits(year, page, block, top, text=''):
    #the time's digits the scan shows on a line: as the year's CUT_TIMES gives them for its block, or where it gives
    #'edge' (the scan's edge cutting across a block's times aslant, 1980's), those whose glyphs (the middle of the cell,
    #a line high) lie wholly on the scan, less any last ones read as blank (a digit the edge cuts through)
    cut = getattr(layout(year), 'CUT_TIMES', {}).get((page, block))
    if cut != 'edge' or top == '':
        return cut
    p = page_printer(year, page)
    lines, _ = block_glyphs(year, page, block - 1)
    line = min(lines, key=lambda l: abs(l['top'] - int(top)))
    scan = on_scan(year, page)
    half = p.glyph_w // 2 - 2
    kept = 0
    for c in p.time_columns:
        cx = line['x0'] + c * line['pitch'] + line['offset'][c]
        x = int(round(cx)) - half
        y = int(round(line_top(line, cx, p)))
        if x < 0 or x + 2 * half > scan.shape[1] or not scan[y:y + p.line_height[1], x:x + 2 * half].all():
            break
        kept += 1
    while text and kept > 3 and text[p.time_columns[kept - 1]] == ' ':
        kept -= 1
    return kept


#a time the scan cuts off after its minutes or tens of seconds (CUT_TIMES) is taken as the middle of what's cut
TIME_FORMATS = {3: '{}:{}{}:30', 4: '{}:{}{}:{}5', 5: '{}:{}{}:{}{}', 6: '{}:{}{}:{}{}.{}', 7: '{}:{}{}:{}{}.{}{}'}


def time_text(d):
    #the time's digits (to the minute, ten seconds, second, tenth or hundredth) as a time, or nothing when they can't
    #be one
    ok = len(d) in TIME_FORMATS and all(ch.isdigit() for ch in d) and int(d[1]) < 6 and (len(d) < 4 or int(d[3]) < 6)
    return TIME_FORMATS[len(d)].format(*d) if ok else ''


def pace_seconds(text):
    m = re.fullmatch(r'(\d{1,2}):(\d\d)', text.strip())
    return int(m.group(1)) * 60 + int(m.group(2)) if m and int(m.group(2)) < 60 else np.nan


def time_readings(row, p, kept=None):
    #the time as read, and every reading with one or two of its digits swapped for their runner-up, the least sure
    #first: its first `kept` digits, where the scan cuts the rest off. a digit the printer left out (a blank among
    #them) is each digit in turn, for the times around it to choose
    text, alt, sure = row['text'], row['alt'], row['sure']
    columns = p.time_columns[:kept]
    best = [text[c] for c in columns]
    blank = [j for j, ch in enumerate(best) if ch == ' ']
    if len(blank) == 1 and len(best) > 1:
        j = blank[0]
        return [t for t in dict.fromkeys(time_text(best[:j] + [d] + best[j + 1:]) for d in DIGITS) if t]
    out = []
    if all(ch.isdigit() for ch in best):
        out.append(''.join(best))
    order = sorted(range(len(columns)), key=lambda j: sure[columns[j]])
    swaps = [[j] for j in order] + [[i, j] for n, i in enumerate(order[:3]) for j in order[n + 1:4]]
    for js in swaps:
        d = list(best)
        for j in js:
            d[j] = alt[columns[j]]
        if all(ch.isdigit() for ch in d):
            out.append(''.join(d))
    return [t for t in dict.fromkeys(time_text(d) for d in out) if t]


def swaps_from(t, row, p):
    #how many of the time's digits differ from the reading
    return sum(a != row['text'][c] for a, c in zip(re.sub(r'\D', '', t), p.time_columns))


def fits_pace(t, pace, pace_km):
    return np.isnan(pace) or abs(seconds(t) / pace_km - pace) <= 1.5


#where the scan cuts a time short, the seconds the true time may be off its reading, least and most, by the digits kept
#(6:20:2 is 6:20:20 to 6:20:29.99, read as 6:20:25)
CUT_RANGES = {3: (-30, 29.99), 4: (-5, 4.99), 5: (0, 0.99), 6: (0, 0.09)}


def longest_rising(secs, ranges=None):
    #indexes of the longest run (not necessarily adjacent) of times that never go down. where some times are cut short
    #(ranges: each one's least and most seconds off its reading), of times that can be put in an order that never goes
    #down within their ranges
    if ranges is not None and any(ranges):
        return longest_rising_ranges(secs, ranges)
    idx = [i for i, s in enumerate(secs) if np.isfinite(s)]
    tails, prev, at = [], {}, []
    for i in idx:
        k = bisect.bisect_right(tails, secs[i])
        if k == len(tails):
            tails.append(secs[i])
            at.append(i)
        else:
            tails[k] = secs[i]
            at[k] = i
        prev[i] = at[k - 1] if k else None
    out, i = [], at[-1] if at else None
    while i is not None:
        out.append(i)
        i = prev[i]
    return set(out)


def longest_rising_ranges(secs, ranges):
    #longest_rising with each time a range: a run can go on to a time whose most is no less than the least the run's
    #times so far can be (the floor), and of runs as long, the one with the lowest floor is kept
    idx = [i for i, s in enumerate(secs) if np.isfinite(s)]
    if not idx:
        return set()
    lo = np.array([secs[i] + (ranges[i] or (0, 0))[0] for i in idx])
    hi = np.array([secs[i] + (ranges[i] or (0, 0))[1] for i in idx])
    best, prev, floor = np.ones(len(idx), int), np.full(len(idx), -1), lo.copy()
    for j in range(1, len(idx)):
        ok = np.nonzero(floor[:j] <= hi[j])[0]
        if len(ok):
            top = best[ok].max()
            tied = ok[best[ok] == top]
            m = tied[np.argmin(floor[tied])]
            best[j], prev[j], floor[j] = top + 1, m, max(lo[j], floor[m])
    tied = np.nonzero(best == best.max())[0]
    j = tied[np.argmin(floor[tied])]
    out = []
    while j >= 0:
        out.append(idx[j])
        j = prev[j]
    return set(out)


def repair_list_times(lst, p, pace_km, kept=None):
    #a list's times: the reading, where it lies between the times placed around it; otherwise the one reading with a
    #digit or two swapped for its runner-up that does, and, of several that do, the one that fits the PACE column. a
    #time no reading fits is left blank. kept: each line's digits the scan shows (all of them when not given)
    kept = kept or [None] * len(lst)
    readings = [time_readings(r, p, k) for k, (_, r) in zip(kept, lst.iterrows())]
    paces = [pace_seconds(cells(r, 'pace', p)[0]) if 'pace' in p.fields else np.nan for _, r in lst.iterrows()]
    first = [rs[0] if rs and rs[0] == time_text([r['text'][c] for c in p.time_columns[:k]]) else ''
             for rs, k, (_, r) in zip(readings, kept, lst.iterrows())]
    ranges = [CUT_RANGES.get(k) for k in kept]
    least = np.array([(r or (0, 0))[0] for r in ranges])
    most = np.array([(r or (0, 0))[1] for r in ranges])
    secs = np.array([seconds(t) for t in first])
    keep = longest_rising(secs, ranges)
    times = [t if i in keep else '' for i, t in enumerate(first)]
    secs = np.array([seconds(t) for t in times])
    for i in range(len(times)):
        if times[i]:
            continue
        before = (secs + least)[:i][np.isfinite(secs[:i])]
        after = (secs + most)[i + 1:][np.isfinite(secs[i + 1:])]
        lo = before.max() if len(before) else 0
        hi = after.min() if len(after) else np.inf
        fits = [t for t in readings[i] if lo <= seconds(t) + most[i] and seconds(t) + least[i] <= hi]
        if len(fits) > 1:
            #the fewest digits changed
            fewest = min(swaps_from(t, lst.iloc[i], p) for t in fits)
            fits = [t for t in fits if swaps_from(t, lst.iloc[i], p) == fewest]
        if len(fits) > 1:
            fits = [t for t in fits if not np.isnan(paces[i]) and fits_pace(t, paces[i], pace_km)]
        if len(fits) == 1:
            times[i] = fits[0]
            secs[i] = seconds(fits[0])
    return times


def class_and_rank(row, place, p):
    #the class and class rank as read, and the class's runner-up digits: their fields, or where they're printed after
    #the place (1983's), the first two numbers after the place's digits (the place as printed) and the blank after them
    if not p.ranks_after_place:
        return cells(row, 'cls', p)[0], cells(row, 'crank', p)[0], None
    start = p.place_columns[0] + len(str(place)) + 1
    text = row['text'][start:p.ranks_after_place]
    code = text.split(' ')[0]
    rest = text[len(code):].split()
    return code, rest[0] if rest else '', row['alt'][start:start + len(code)]


def class_label(row, gender, p, codes=None, code=None, alt=None):
    #"M 30-34" from the CLASS column, its letter being the list's: the reading, or the class that the fewest of its
    #least sure characters swapped for their runner-up make, when only one does. the class starts in the field's second
    #column (a speck can fill the first), and a faint hyphen reads as a space. where the class is printed as a number,
    #the class it codes for (code: the number as read, where it isn't the cls field's, and alt its runner-up digits,
    #one of which makes the one class a code that's none does), when that's the list's gender
    if codes:
        code = digits_only(cells(row, 'cls', p)[0] if code is None else code)
        if alt and code and int(code) not in codes:
            fits = {code[:j] + alt[j] + code[j + 1:] for j in range(len(code)) if alt[j].isdigit()}
            fits = [c for c in fits if int(c) in codes]
            code = fits[0] if len(fits) == 1 else code
        label = codes.get(int(code), '') if code else ''
        return label if label.startswith(gender) or gender == 'X' else ''
    text, alt, sure = cells(row, 'cls', p)
    weak = [j for j in range(len(text)) if sure[j] <= '4' and alt[j] != ' ']
    found = {}
    for k in range(len(weak) + 1):
        for js in itertools.combinations(weak, k):
            t = ''.join(alt[j] if j in js else ch for j, ch in enumerate(text))[1:]
            m = re.fullmatch(r'\s*[MF](\d\d)[- ](\d\d)\s*', t)
            #(and an open class, 70+, or the 1986 kortelopet's 19+)
            over = re.fullmatch(r'\s*[MF](\d\d)[-+]\s*', t)
            age = '{}-{}'.format(*m.groups()) if m else over.group(1) + '+' if over else ''
            if age in p.ages:
                found.setdefault(k, set()).add(age)
        if len(found.get(k, ())) == 1:
            return '{} {}'.format(gender, found[k].pop())
        if found.get(k):
            return ''
    return ''


def class_starts(df, first):
    #{(gender, class): the ranks before the class's first one here}: none, unless the list's first page is missing,
    #and then the commonest gap between the ranks read and the count within the class
    out = {}
    for (gender, age), c in df[df['age_group'] != ''].groupby(['gender', 'age_group']):
        gap = pd.to_numeric(c.sort_values('place')['class_rank'], errors='coerce').values - np.arange(1, len(c) + 1)
        gap = gap[~np.isnan(gap)]
        out[(gender, age)] = int(pd.Series(gap).mode().min()) if first[gender] > 1 and len(gap) else 0
    return out


def fill_classes(df, starts):
    #a class that can't be read is the one class whose ranks, placed around the skier's, leave a gap for the skier's
    #class rank
    out = df['age_group'].copy()
    rank = pd.to_numeric(df['class_rank'], errors='coerce')
    for i in df.index[df['age_group'] == '']:
        fits = []
        gender = df.at[i, 'gender']
        for age, c in df[(df['gender'] == gender) & (df['age_group'] != '')].groupby('age_group'):
            before = rank[c.index[c['place'] < df.at[i, 'place']]]
            after = rank[c.index[c['place'] > df.at[i, 'place']]]
            if len(before) + starts[(gender, age)] == rank[i] - 1 \
                    and (not len(before) or before.iloc[-1] == rank[i] - 1) \
                    and len(after) and after.iloc[0] == rank[i] + 1:
                fits.append(age)
        if len(fits) == 1:
            out[i] = fits[0]
    return out


def repair_class_ranks(df, starts):
    #the class ranks count up by one within each class, in place order: a rank that doesn't is replaced by the count
    #when the ranks read on either side of it in the class agree with the count, or by the one rank they leave between
    #them. and a run of ranks that don't (cut off by the scan's edge, 1980's) by the ranks the ranks read either side
    #of the run, each one more or less than its own neighbour's, leave for it
    out = df['class_rank'].copy()
    for key, c in df[df['age_group'] != ''].groupby(['gender', 'age_group']):
        c = c.sort_values('place')
        read = pd.to_numeric(c['class_rank'], errors='coerce').values
        n = np.arange(1, len(c) + 1) + starts[key]
        for i in range(len(c)):
            if read[i] == n[i]:
                continue
            ok_before = i == 0 or read[i - 1] == n[i - 1]
            ok_after = i == len(c) - 1 or read[i + 1] == n[i + 1]
            if ok_before and ok_after:
                out[c.index[i]] = str(n[i])
            elif 0 < i < len(c) - 1 and read[i + 1] == read[i - 1] + 2:
                #or, where places are missing (so the count is off), the one rank its neighbours leave between them
                out[c.index[i]] = str(int(read[i - 1]) + 1)
        steady = np.zeros(len(c), bool)
        steady[1:] |= np.diff(read) == 1
        steady[:-1] |= np.diff(read) == 1
        held = np.nonzero(steady)[0]
        for a, b in zip(held[:-1], held[1:]):
            if b - a > 2 and read[b] - read[a] == b - a:
                for i in range(a + 1, b):
                    out[c.index[i]] = str(int(read[a]) + i - a)
        #or, for a run of a few that don't count up among themselves, by the count, where the ranks read either side
        #of the run agree with it (not a stretch after a tie, whose ranks all run one behind the count)
        for a, b in runs(read != n):
            if 0 < a and b < len(c) and 1 < b - a <= 6 and not (np.diff(read[a:b]) == 1).all():
                for i in range(a, b):
                    out[c.index[i]] = str(n[i])
    return out


#the nations' codes, as the list writes them
NATIONS = {'USA', 'CAN', 'FIN', 'SUI', 'FRA', 'BRD', 'SWE', 'URS', 'AUS', 'POL', 'AUT', 'NOR', 'ITA', 'GER', 'JPN',
           'NET', 'NED', 'SLO', 'TCH', 'GBR', 'DEN', 'ISL', 'ESP', 'YUG', 'DDR', 'EST', 'HUN', 'BEL', 'NZL'}


def nation(row, p):
    #NAT: three letters, or the code the runner-up of its least sure letter makes. a speck is no nation
    text, alt, sure = cells(row, 'nat', p)
    nat = text.strip()
    if p.nation_names:
        #a printer that writes the country out (NORWAY, and FINDLAN for Finland): the code of the name it's nearest
        near = difflib.get_close_matches(nat, p.nation_names, n=1, cutoff=0.6)
        return p.nation_names[near[0]] if near else ''
    if not re.fullmatch(r'[A-Z]{3}', nat):
        return ''
    if nat not in NATIONS:
        a = text.index(nat)
        fits = {nat[:j] + alt[a + j] + nat[j + 1:] for j in range(3) if sure[a + j] <= '2'} & NATIONS
        if len(fits) == 1:
            return fits.pop()
    return nat


def state_and_country(row, p):
    #ST, with the provinces' codes as Canada Post writes them, and NAT: USA for a state, and CAN for a province, when
    #it's blank or reads as no nation's code
    st = clean_words(cells(row, 'st', p)[0]).replace(' ', '')
    nat = nation(row, p)
    z = cells(row, 'zip', p)[0].strip() if 'zip' in p.fields else ''
    st = PROVINCES.get(st, st)
    if p.dropped_letters and st and st not in US_STATES | CA_PROVINCES:
        fits = {st[:j] + ch + st[j:] for ch in p.dropped_letters for j in range(len(st) + 1)} \
            & (US_STATES | CA_PROVINCES)
        st = fits.pop() if len(fits) == 1 else st
    from_zip = zip_state(z) if not nat or nat == 'CAN' else ''
    if from_zip and st != from_zip:
        #the zip pins the state when the state as read is one letter off it (MM, NI, II), or has a speck after it
        if (len(st) == len(from_zip) and sum(a != b for a, b in zip(st, from_zip)) == 1) or st[:2] == from_zip \
                or st not in US_STATES | CA_PROVINCES:
            st = from_zip
    if st in US_STATES and nat not in NATIONS:
        nat = 'USA'
    if st in CA_PROVINCES and nat not in NATIONS - {'CAN'}:
        nat = 'CAN'
    return st, nat


@functools.lru_cache(maxsize=None)
def word_counts():
    #how often each word turns up in the clean results as a first name, a last name and in a town, upper case
    clean = load_all_results()
    count = lambda col: collections.Counter(w.upper() for text in clean[col].dropna()
                                            for w in re.findall(r'[a-z]+', str(text).lower().replace("'", '')))
    first, last, town = count('first'), count('last'), count('city')
    return first, last, first + last, town


SUFFIXES = {'JR', 'SR', 'II', 'III', 'IV'}
#the words a surname can start with
PARTICLES = {'VAN', 'VON', 'DE', 'DER', 'DEN', 'DU', 'DI', 'DA', 'DEL', 'LA', 'LE', 'ST', 'TEN', 'TER', 'MC'}


def field_text(row, field, p, unsure=2, common=3, surname_first=False):
    #a name or town as printed. a point with a letter right after it is a speck in the space between two words. a word
    #not seen in the clean results (as a first name, for a name's first word, as a last name for its last, or the other
    #way round for a name printed surname first) becomes the
    #one word seen there at least `common` times that the second choice for one of its letters read least surely makes
    #(or failing any, the third choice). the network never learned the apostrophe, which it reads as I or T: O'HARA
    #comes out OIHARA
    text, alt, sure, alt2 = cells(row, field, p, third=True)
    chars = list(text)
    for j in range(len(chars) - 1):
        if chars[j] == '.' and chars[j + 1].isalpha():
            chars[j] = ' '
    if field == 'name' and p.name_marks:
        #a mark printed after some names (1983's small m) is a last word of its letter alone, with no point after it
        mark = re.search(r'(?<=\s)[{}]\s*$'.format(p.name_marks), ''.join(chars))
        if mark:
            chars[mark.start()] = ' '
    first, last, either, town = word_counts()
    if field == 'name' and p.comma_letters:
        #a mark the comma is read as is a space
        chars = [' ' if ch in p.comma_letters and not ch.isalpha() else ch for ch in chars]
        #a word not seen in the clean results with one of those letters where the comma would be (WIESEYJOHN) is the
        #surname and first name either side of it: where both are seen there, or failing that one of them is (the
        #first name, or the surname with three letters or more after it), the last such letter
        for m in re.finditer(r'[A-Z]+', ''.join(chars)):
            word = m.group()
            if either[word]:
                continue
            fits = {j: 2 * (last[word[:j]] > 0 and first[word[j + 1:]] > 0)
                    or int(first[word[j + 1:]] >= common or (last[word[:j]] >= common and len(word) - j > 3))
                    for j in range(2, len(word) - 2) if word[j] in p.comma_letters}
            if fits and max(fits.values()):
                chars[m.start() + max(fits, key=lambda j: (fits[j], j))] = ' '
            elif m.start() == len(text) - len(text.lstrip()) and word[-1] in p.comma_letters and last[word[:-1]] \
                    and text[m.end():].strip():
                #or the surname's, the comma at its end (EVANSY ROBERT)
                chars[m.end() - 1] = ' '
    words = list(re.finditer(r"[A-Z][A-Z'-]*", ''.join(chars)))
    named = [m for m in words if m.group() not in SUFFIXES]
    for m in words:
        word, start = m.group(), m.start()
        if len(word) < 3 or not word.isalpha():
            continue
        if field == 'town':
            counts = town
        else:
            if surname_first:
                counts = last if named and m is named[0] else first if len(named) > 1 and m is named[1] else either
            else:
                counts = first if named and m is named[0] else last if named and m is named[-1] else either
        if counts[word]:
            continue
        #(a word whose small l's are read as I, BIII: the word seen most often of those some of them as L make. and the
        #same for a capital read as another, from the word's first letter)
        swaps = [(1, 'I', 'L')] if p.small_l and 'I' in word[1:] else []
        swaps += [(0, read, meant) for read, meant in p.swapped.items() if read in word]
        fits = {}
        for first_j, read, meant in swaps:
            js = [j for j in range(first_j, len(word)) if word[j] == read]
            fits = {w: counts[w] for k in range(1, len(js) + 1) for chosen in itertools.combinations(js, k)
                    for w in [''.join(meant if j in chosen else ch for j, ch in enumerate(word))] if counts[w] >= common}
            if fits:
                break
        if fits:
            chars[start:start + len(word)] = max(fits, key=fits.get)
            continue
        if field == 'name' and re.match(r'O[IT{}]'.format(p.comma_letters), word) and sure[start + 1] <= '4' \
                and counts['O' + word[2:]] >= common:
            chars[start + 1] = "'"
            continue
        weak = [j for j in range(len(word)) if sure[start + j] <= str(unsure)]
        for choice in (alt, alt2):
            fits = {word[:j] + choice[start + j] + word[j + 1:] for j in weak
                    if choice[start + j].isalpha() and choice[start + j] != word[j]}
            fits = {w for w in fits if counts[w] >= common}
            if fits:
                break
        if not fits:
            #the printer's X looks like its K, and a year whose network barely learned X reads every one as K
            fits = {word[:j] + 'X' + word[j + 1:] for j in range(len(word)) if word[j] == 'K'}
            fits = {w for w in fits if counts[w] >= common}
        if len(fits) == 1:
            chars[start:start + len(word)] = fits.pop()
    return clean_words(''.join(chars))


@functools.lru_cache(maxsize=None)
def town_counts():
    #{state: {town: how often it turns up in the clean results}}, upper case, for US states and Canadian provinces.
    #a few towns there are written twice over (MILWAUKEEMILWAUKEE)
    clean = load_all_results()
    out = {}
    for (city, state), n in clean.groupby(['city', 'state']).size().items():
        town = re.sub(r'[^A-Z ]', '', str(city).upper()).strip()
        if town and state in US_STATES | CA_PROVINCES and not re.fullmatch(r'(.+)\1', town.replace(' ', '')):
            out.setdefault(state, collections.Counter())[town] += n
    return out


def shortened(short, full):
    #the printer's 15 characters shorten a town's words: STVNS for STEVENS, PK for PARK, SHORE for SHORES
    return short == full or (short[0] == full[0] and len(short) < len(full)
                             and re.fullmatch('.*'.join(short) + '.*', full) is not None)


#(state, town): towns printed whole that a town in the clean results fits as if shortened (DOWNS: their DOWNERS is
#Downers Grove cut short)
WHOLE_TOWNS = {('IL', 'DOWNS')}


def expand_town(city, state, common=2, ahead=10):
    #a town not seen in that state, written out as the town seen there (at least `common` times) that it shortens,
    #when there's one, or one seen `ahead` times as often as the others (the clean results misspell a few). a letter
    #after a town seen there is a speck or a rule's dash read as one (1980's EDINA L), and is dropped
    towns = town_counts().get(state)
    key = city.upper().replace('ST. ', 'ST ')
    if not towns or not city or towns[key] or (state, key) in WHOLE_TOWNS:
        return city
    words = key.split()
    if len(words) > 1 and len(words[-1]) == 1 and towns[' '.join(words[:-1])]:
        return ' '.join(city.split()[:-1])
    fits = sorted(((n, t) for t, n in towns.items() if n >= common and len(t.split()) == len(words)
                   and all(shortened(a, b) for a, b in zip(words, t.split()))), reverse=True)
    if len(fits) == 1 or (len(fits) > 1 and fits[0][0] >= ahead * fits[1][0]):
        return fits[0][1]
    return city


def mended_state(row, st, nat, city, p):
    #a North American state that's no state's code, as the one a letter's second or third choice makes where the town
    #is known (WL: WI, where 1982's printer's I looks like its l), the first state in it with a letter more where the
    #town is known (MNR: MN), the state the town is seen in nine times in ten in the clean results (at least ten times;
    #ONT read DNT: ON), or the state its first two letters make whatever the town (CAL: CA). a state left blank, or a
    #nation's code printed in its place, stays
    if not st or st in US_STATES | CA_PROVINCES | NATIONS or nat not in ('', 'USA', 'CAN'):
        return st
    towns = town_counts()
    town = re.sub(r'[^A-Z ]', '', city)
    text, alt, _, alt2 = cells(row, 'st', p, third=True)
    letters = [j for j, ch in enumerate(text) if ch.isalpha()]
    if len(st) == 2 and len(letters) == 2:
        a, b = letters
        fits = {c + text[b] for c in (alt[a], alt2[a])} | {text[a] + c for c in (alt[b], alt2[b])}
        known = {f for f in fits if f in towns and towns[f][town]}
        if len(known) == 1:
            return known.pop()
    inside = [st[j:j + 2] for j in range(len(st) - 1) if st[j:j + 2] in US_STATES | CA_PROVINCES] \
        if len(st) > 2 else []
    known = [f for f in inside if f in towns and towns[f][town]]
    if known:
        return known[0]
    seen = {state: counts[town] for state, counts in towns.items()}
    total = sum(seen.values())
    best = max(seen, key=seen.get) if total else ''
    if total >= 10 and seen[best] >= 0.9 * total:
        return best
    return st[:2] if len(st) > 2 and st[:2] in US_STATES | CA_PROVINCES else st


def without_postcode(row, city, nat, p):
    #a European town is printed after its postal code (15870 HOLLOLA) and sometimes before a district (0861 OSLO 1),
    #which the town's columns read as letters, none of them surely: those are dropped
    if nat in ('USA', 'CAN', ''):
        return city
    text, _, sure = cells(row, 'town', p)
    raw = [(m.group(), np.mean([int(c) for c in sure[m.start():m.end()]])) for m in re.finditer(r'\S+', text)]
    words = city.split()
    if len(raw) != len(words) or len(words) < 2:
        return city
    if 4 <= len(raw[0][0]) <= 5 and raw[0][1] <= 2:
        words[0] = ''
    if len(raw[-1][0]) == 1 and raw[-1][1] <= 2.5:
        words[-1] = ''
    return ' '.join(w for w in words if w)


def repair_bibs(res, bibs):
    #no two skiers share a bib: of two that read the same, the one read less surely gets its least sure digit's runner-
    #up when that makes a bib nobody has, and loses its bib when nothing does
    out = res['bib'].copy()
    used = set(out[out != ''])
    for bib, group in res[res['bib'] != ''].groupby('bib'):
        if len(group) < 2:
            continue
        weakest = {i: min(bibs[i][2]) for i in group.index}
        order = sorted(group.index, key=lambda i: weakest[i])
        for i in order[:-1]:
            if weakest[i] >= weakest[order[-1]]:
                continue
            text, alt, sure = bibs[i]
            fits = set()
            for j in sorted(range(len(text)), key=lambda j: sure[j]):
                if text[j].isdigit() and alt[j].isdigit() and sure[j] < '9':
                    b = digits_only(text[:j] + alt[j] + text[j + 1:])
                    if b and b not in used:
                        fits.add(b)
                    break
            out[i] = fits.pop() if len(fits) == 1 else ''
            used.add(out[i])
    return out


def parse(year, race='birkie'):
    use_race(race)
    p = printer(year)
    df = grid(year)
    df['page'] = df['page'].astype(int)
    first = first_places(year)
    codes = getattr(layout(year), 'CLASS_CODES', None)
    surname_first = getattr(layout(year), 'SURNAME_FIRST', False)
    out, bibs = [], []
    skips = getattr(layout(year), 'RANK_SKIPS', {})
    for gender, lst in df.groupby('gender', sort=False):
        lst = lst.reset_index(drop=True)
        #(a line typed in after the list was printed, in a face the glyphs can't be read in, has no time to read: the
        #year's HAND gives it)
        added = lst['added'] == '1' if 'added' in lst else pd.Series(False, index=lst.index)
        times = repair_list_times(lst, p, pace_km(year), [0 if typed else kept_digits(year, int(page), int(block), top,
                                                                                       text)
                                                          for page, block, top, text, typed
                                                          in zip(lst['page'], lst['block'], lst['top'], lst['text'],
                                                                 added)])
        #the place the list prints (where lines typed in after it was printed have none, 1983's)
        printed = first[gender] - 1
        for i, row in lst.iterrows():
            printed += 0 if added[i] else 1 + skips.get((int(row['page']), int(row['block']), int(row['line'])), 0)
            #a line cut off the scan keeps its place, but has nothing to read, unless the year's UNFOUND gives it
            if row['top'] == '':
                given = getattr(layout(year), 'UNFOUND', {}).get((gender, i + first[gender]))
                if given:
                    out.append({'place': i + first[gender], 'gender': gender, 'code': '', 'status': 'finished',
                                'tech': '', 'page': row['page'], 'top': '', **given})
                    width = p.fields['bib'][1] - p.fields['bib'][0]
                    bibs.append(tuple(given['bib'].rjust(width) for _ in range(2)) + ('9' * width,))
                continue
            st, nat = state_and_country(row, p)
            city = without_postcode(row, field_text(row, 'town', p), nat, p)
            st = mended_state(row, st, nat, city, p)
            nat = 'USA' if st in US_STATES and not nat else 'CAN' if st in CA_PROVINCES and not nat else nat
            top = int(row['top'])
            if layout(year).TURN.get(row['page']) == Image.ROTATE_180:
                top = Image.open(os.path.join(PAGE_DIR, str(year), '{:03d}.png'.format(row['page']))).height - top - 18
            name = field_text(row, 'name', p, surname_first=surname_first)
            code, rank, alt = class_and_rank(row, printed, p)
            out.append({'place': i + first[gender], 'bib': digits_only(cells(row, 'bib', p)[0]),
                        'name': name, 'gender': gender,
                        'age_group': class_label(row, gender, p, codes, code, alt),
                        'class_rank': digits_only(rank), 'code': code,
                        'city': city, 'state': st, 'country': nat,
                        'time': times[i], 'status': 'finished', 'tech': '', 'page': row['page'], 'top': top,
                        **(first_name_first(name) if surname_first else {}),
                        **hand(year, row['page'], int(row['block']), int(row['top']))})
            #(a class set by hand is no code as read, and a bib set by hand is sure)
            given = hand(year, row['page'], int(row['block']), int(row['top']))
            if 'age_group' in given:
                out[-1]['code'] = ''
            bib = cells(row, 'bib', p)
            bibs.append(tuple(given['bib'].rjust(len(bib[0])) for _ in range(2)) + ('9' * len(bib[0]),)
                        if 'bib' in given else bib)
    res = pd.DataFrame(out)
    if p.ranks_by_code:
        #(a man's class code whose leading 0 is read as a 1 is a woman's class: where the skier's first name is clearly
        #a man's, it's the class a 0 makes, ten less. not for a class set by hand)
        names = first_name_genders()
        number = {label: n for n, label in codes.items()}
        for i in res.index[res['age_group'].str.startswith('F') & (res['code'] != '')]:
            n = number[res.at[i, 'age_group']] - 10
            if names.get(res.at[i, 'first'].split()[0] if res.at[i, 'first'] else '') == 'M' and n in codes:
                res.at[i, 'age_group'], res.at[i, 'code'] = codes[n], '0{}'.format(n)
        #(and a man's class for a first name clearly a woman's is left for the class ranks to give, a few men's names
        #being women's in the later results)
        for i in res.index[res['age_group'].str.startswith('M') & (res['code'] != '')]:
            if names.get(res.at[i, 'first'].split()[0] if res.at[i, 'first'] else '') == 'F':
                res.at[i, 'age_group'] = ''
    #where the printout ranks a class whose code is printed with a leading 0 apart from the same class printed without
    #(1983's, whose men's classes are each ranked as two), each is a class of its own while the ranks are repaired
    apart = p.ranks_by_code and (res['code'].str.len() > 1) & res['code'].str.startswith('0')
    res['age_group'] = res['age_group'] + np.where(apart & (res['age_group'] != ''), '|0', '')
    starts = class_starts(res, first)
    res['age_group'] = fill_classes(res, starts)
    res['class_rank'] = repair_class_ranks(res, starts)
    res['age_group'] = res['age_group'].str.replace('|0', '', regex=False)
    if p.ranks_by_code:
        #and a class printed both ways (each a twentieth of it or more) has no rank in the class printed, so its ranks
        #are left out, as are those of the skiers whose class can't be read
        forms = pd.crosstab(res['age_group'], apart)
        split = [age for age in forms.index
                 if age and forms.shape[1] == 2 and forms.loc[age].min() >= forms.loc[age].sum() / 20]
        res.loc[res['age_group'].isin(split) | (res['age_group'] == ''), 'class_rank'] = ''
    res = res.drop(columns='code')
    if (res['gender'] == 'X').any():
        res = split_mixed(res)
    res['bib'] = repair_bibs(res, bibs)
    res['city'] = [expand_town(c, st) for c, st in zip(res['city'], res['state'])]
    return res


def split_mixed(res):
    #a list of men and women together (gender X, places overall) as the men's and women's: each skier is their class's
    #gender, or for a class of both (X) or none read, their first name's (failing that, the list's commonest), and
    #their place among it counts those of that gender before them, with those in the list's gaps (places with no line,
    #before the first line read included) counted from each class's ranks either side of the gap, a class of both's
    #going to the gender most of it is. a line with neither a class nor a name (blanked out on 1979's scan but for its
    #place and time) counts as a gap too, and is kept with no gender or place
    res = res.copy()
    mixed = res[res['gender'] == 'X'].sort_values('place')
    gender = mixed['age_group'].str[:1].where(mixed['age_group'] != '', 'X')
    names = first_name_genders()
    gender = gender.where(gender != 'X', mixed['first'].str.split().str[0].map(names).fillna('X'))
    both = gender[mixed['age_group'] == 'X']
    most = both[both != 'X'].mode().iloc[0] if (both != 'X').any() else 'M'
    unknown = (gender == 'X') & (mixed['name'] == '')
    #a skier with neither (a class misread, a rare name) is taken to be the gender most of the list is
    gender = gender.replace('X', gender[gender != 'X'].mode().iloc[0])
    rank = pd.to_numeric(mixed['class_rank'], errors='coerce')
    count = {'M': 0, 'F': 0, 'X': 0}
    last = {}
    places = {}
    previous = 0
    for n, i in enumerate(mixed.index):
        if unknown[i]:
            continue
        gap = mixed.at[i, 'place'] - previous - 1
        if gap:
            #each class's skiers in the gap: its first rank after it less its last before, less one
            ahead = {}
            for j in mixed.index[n:]:
                age = mixed.at[j, 'age_group']
                if age and age not in ahead and np.isfinite(rank[j]):
                    ahead[age] = rank[j]
            inside = {'M': 0, 'F': 0}
            for age, r in ahead.items():
                inside[most if age == 'X' else age[0]] += max(0, int(r - last.get(age, 0) - 1))
            if inside['M'] + inside['F'] != gap:
                print('places {}-{}: the class ranks put {} men and {} women in a gap of {}'.format(
                    previous + 1, previous + gap, inside['M'], inside['F'], gap))
                #(1979's blanked stretches, where a class's next rank can lie past the next stretch): the gap shared
                #between them in that proportion
                women = int(round(gap * inside['F'] / max(1, inside['M'] + inside['F'])))
                inside = {'M': gap - women, 'F': women}
            count['M'] += inside['M']
            count['F'] += inside['F']
        g = gender[i]
        count[g] += 1
        places[i] = count[g] if g != 'X' else np.nan
        if mixed.at[i, 'age_group'] and np.isfinite(rank[i]):
            last[mixed.at[i, 'age_group']] = rank[i]
        previous = mixed.at[i, 'place']
    res.loc[mixed.index, 'overall'] = mixed['place']
    res.loc[mixed.index, 'place'] = pd.Series(places)
    res.loc[mixed.index, 'gender'] = gender.where(~unknown, '')
    res.loc[mixed.index, 'age_group'] = mixed['age_group'].where(mixed['age_group'] != 'X', '')
    return res


@functools.lru_cache(maxsize=None)
def first_name_genders(least=5, share=0.9):
    #{first name, upper case: M or F} for the names in the clean results at least `least` times, `share` of them one
    #gender's
    clean = load_all_results()
    first = clean['first'].dropna().str.split().str[0].str.upper()
    counts = pd.crosstab(first, clean.loc[first.index, 'gender'])
    total = counts.sum(1)
    out = {}
    for g in ('M', 'F'):
        if g in counts:
            out.update({name: g for name in counts.index[(total >= least) & (counts[g] >= share * total)]})
    return out


def first_name_first(name):
    #a name printed surname first ("KELLER HARRY S") as the other years print it, and its parts: the surname is taken to
    #be the first word, with the word after a particle ("VAN STRATTEN THERESA J") where a first name is left, and a
    #suffix ends the name, whether printed at the end or after the surname ("SKEMP,JR FRED C")
    words = name.split()
    if not words:
        return {}
    n = 1
    while n < len(words) - 1 and words[n - 1] in PARTICLES:
        n += 1
    last, rest = ' '.join(words[:n]), words[n:]
    suffix = [rest.pop(0)] if len(rest) > 1 and rest[0] in SUFFIXES else []
    suffix += [rest.pop()] if rest and rest[-1] in SUFFIXES and not suffix else []
    return {'name': ' '.join(rest + [last] + suffix), 'first': ' '.join(rest), 'last': ' '.join([last] + suffix)}


def digits_only(text):
    text = text.strip()
    return text if text.isdigit() else ''


#---------------------------------------------------------------- tesseract, for learning the glyphs

def ocr_block(year, page, k, scale=2):
    #tesseract's reading of one block, at twice the size, as <page>_b<k>.tsv (boxes in the doubled crop's pixels)
    out = page_file(year, page, 'b{}'.format(k + 1))
    if os.path.exists(out + '.tsv'):
        return out
    im, _ = block_image(year, page, k, scale)
    im.save(out + '.png')
    subprocess.run([TESSERACT, out + '.png', out, '--psm', '6', '-c',
                    'tessedit_char_whitelist=' + printer(year).ocr_characters,
                    'tsv'], capture_output=True)
    os.remove(out + '.png')
    return out


def ocr(year, race='birkie'):
    #tesseract on each block, then the glyph reading of every line
    use_race(race)
    jobs = block_order(year)
    with concurrent.futures.ThreadPoolExecutor(OCR_WORKERS) as pool:
        for out in pool.map(lambda job: ocr_block(year, *job), jobs):
            print(out)
    read_year(year)
