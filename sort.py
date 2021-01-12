"""Sorts through screenshots of news sites and stitches together screenshots
detected to belong to a "group" of one screenshot from each paper within a few
minutes of each other.

Chuan-Zheng Lee
© January 2021
"""

from collections import Counter
from itertools import islice
from pathlib import Path
import argparse
import datetime
import png
import shutil

IMAGES_DIR = Path('images')
SORTED_DIR = Path('sorted')
OUTPUT_DIR = Path('output')

# These specify rows (of pixels) in images that are used as "examples". That is,
# if another image has the same row of pixels at the same vertical location, it
# is assumed to be from the same newspaper. Both newspapers and my screenshots
# weren't always consistent, so there are multiple "signature rows" for each
# paper, and an image matches if any one signature row matches. The Washington
# Post needs more signatures because it doesn't have any unique colours (unlike
# Fox's blue and CNN's red), so we have to take a row that crosses its logo,
# which is too complicated to be consistent. (Also, its design changed more
# often.)
SIGNATURES_IN_FILES = {
    "fox": [
        ('images/Screenshot_2018-09-05-08-59-19.png', 329),
        ('images/Screenshot_2018-11-22-12-11-31.png', 353),
        ('images/Screenshot_2020-05-29-14-19-45.png', 397),
        ('images/Screenshot_2020-06-04-22-33-11.png', 117),
    ],
    "cnn": [
        ('images/Screenshot_2018-08-23-18-56-27.png', 655),
        ('images/Screenshot_2018-09-05-18-27-31.png', 328),
        ('images/Screenshot_2018-11-07-18-15-31.png', 352),
        ('images/Screenshot_2019-04-21-09-48-16.png', 388),
        ('images/Screenshot_2020-05-29-14-20-14.png', 396),
        ('images/Screenshot_2020-12-11-19-49-31.png', 108),
    ],
    "wap": [
        ('images/Screenshot_2018-09-05-18-27-49.png', 169),
        ('images/Screenshot_2018-11-08-09-27-13.png', 170),
        ('images/Screenshot_2019-05-14-19-16-47.png', 165),
        ('images/Screenshot_2019-07-28-20-29-21.png', 171),
        ('images/Screenshot_2019-11-05-18-51-15.png', 174),
        ('images/Screenshot_2019-12-20-09-58-03.png', 166),
        ('images/Screenshot_2020-02-11-13-19-33.png', 172),
        ('images/Screenshot_2020-02-18-14-23-00.png', 173),
        ('images/Screenshot_2020-04-18-03-37-26.png', 168),
        ('images/Screenshot_2020-09-28-12-55-09.png', 200),
        ('images/Screenshot_2020-10-01-08-09-57.png', 181),
        ('images/Screenshot_2020-11-08-21-19-42.png', 167),
        ('images/Screenshot_2020-12-24-16-19-17.png', 197),
        ('images/Screenshot_2021-01-04-08-30-50.png', 196),
    ]
}

ROWS = {row for sigs in SIGNATURES_IN_FILES.values() for _, row in sigs}
FIRST_ROW = min(ROWS)
LAST_ROW = max(ROWS)
PAPERS = set(SIGNATURES_IN_FILES.keys())
INSIDE_BORDER_COLOUR = bytearray(b'\xff\xff\xff')
INSIDE_BORDER_WIDTH = 10
INSIDE_BORDER = INSIDE_BORDER_COLOUR * INSIDE_BORDER_WIDTH
SCREENSHOT_WIDTH = 1440
STITCHED_WIDTH = SCREENSHOT_WIDTH * len(PAPERS) + INSIDE_BORDER_WIDTH * (len(PAPERS) - 1)
STITCHED_HEIGHT = 2004


def build_signature_library():
    """Converts the data in SIGNATURES_IN_FILES to {rowno: {paper: (entryno, row)}}"""
    signature_library = {}
    for paper, sigs in SIGNATURES_IN_FILES.items():
        for entryno, (filename, rowno) in enumerate(sigs):
            reader = png.Reader(filename)
            _, _, values, _ = reader.read()
            row = next(islice(values, rowno, rowno+1))
            signature_library.setdefault(rowno, {}).update({paper: (entryno, row)})
    return signature_library


def match_image(values, signature_library):
    """Determines which paper an image came from, returning the name of the paper,
    the row number of the matched pixels, and the entry number in the signature library."""
    for rowno, row in enumerate(islice(values, FIRST_ROW, LAST_ROW+1), start=FIRST_ROW):
        if rowno not in ROWS:
            continue
        for name, (entryno, signature) in signature_library[rowno].items():
            if row == signature:
                return (name, rowno, entryno)
    return None, None, None


def handle_group(group):
        if {paper for paper, _, _ in group} == PAPERS:
            if len(group) == 3:
                print("\033[1;32m ✓ This is a complete group!\033[0m")
                stitch_images(group)
            else:
                print("\033[0;33m ⦿ Too many images, maybe drop some?\033[0m")
        else:
            print("\033[0;31m × This is not a complete group.\033[0m")


def stitch_images(group):
    """Crops and concatenates the images and saves it as a new image."""

    paper_order = ["cnn", "fox", "wap"]
    images = [None, None, None]
    times = []

    for paper, filepath, time in group:
        index = paper_order.index(paper)
        reader = png.Reader(open(filepath, 'rb'))
        _, _, values, _ = reader.read()
        images[index] = values
        times.append(time)

    # extract median time of image
    median_time = sorted(times)[1]
    filename = median_time.strftime("stitched-%Y-%m-%d-%H-%M.png")
    print("\033[1;34m → writing to: " + filename + "\033[0m")

    outarray = []
    first_stitched_row = bytearray(b'')

    # find first row of each image
    # status bar is 96 pixels so start at row 97
    # detection method is different for each paper

    # cnn and fox: first row in each the 100th pixel is red
    for paper, image in zip(paper_order[:2], images[:2]):
        for row in image:
            if row[300] > row[301] and row[300] > row[302]:
                first_stitched_row += row + INSIDE_BORDER
                break
        else:
            print(f"\033[1;31m !! No first row found in {paper} image\033[0m")
            return

    # wapo: just burn the first 96 rows
    for i in range(96):
        next(images[2])

    # stitch subsequent rows together
    writer = png.Writer(width=STITCHED_WIDTH, height=STITCHED_HEIGHT, greyscale=False)
    for i, (cnn_row, fox_row, wap_row) in enumerate(zip(*images)):
        outarray.append(cnn_row + INSIDE_BORDER + fox_row + INSIDE_BORDER + wap_row)
        if i == STITCHED_HEIGHT - 1:
            break

    # write to file
    outfile = open(OUTPUT_DIR / filename, 'wb')
    writer.write_packed(outfile, outarray)
    outfile.close()


# Make directories to copy images to
for key in {'none'} | PAPERS:
    (SORTED_DIR / key).mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Gather signatures
signature_library = build_signature_library()

# Match images

current_group = []
earliest_in_group = None
total_matched = {key: Counter() for key in PAPERS}

for child in sorted(IMAGES_DIR.iterdir()):
    reader = png.Reader(str(child))
    width, height, values, properties = reader.read()
    if width != 1440:
        print(f"{child}: wrong dimension ({height} x {width})")

    paper, rowno, entryno = match_image(values, signature_library)

    if paper is None:
        print(f"matched {child}: -")
        shutil.copy(child, SORTED_DIR / 'none' / child.name)
        continue

    total_matched[paper][(entryno, rowno)] += 1
    shutil.copy(child, SORTED_DIR / paper / child.name)  # copy to a folder for easy review

    # log in matched images
    time = datetime.datetime.strptime(child.name, "Screenshot_%Y-%m-%d-%H-%M-%S.png")

    if not current_group:
        current_group.append((paper, child, time))
        earliest_in_group = time

    elif time - earliest_in_group < datetime.timedelta(minutes=10):
        current_group.append((paper, child, time))

    else:
        handle_group(current_group)
        current_group = [(paper, child, time)]
        earliest_in_group = time

    print(f"{child}: {paper} ({entryno}) at {rowno}")


handle_group(current_group)


for paper, counts in sorted(total_matched.items()):
    total = sum(count for _, count in counts.items())
    print(f"{paper}, total {total} - " + ", ".join(
        f"{entryno}-{rowno}: {count}" for (entryno, rowno), count in sorted(counts.items())))
