"""Sorts through screenshots of news sites and stitches together screenshots
detected to belong to a "group" of one screenshot from each paper within a few
minutes of each other.

Chuan-Zheng Lee
© January 2021
"""

from itertools import chain
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from PIL.ImageChops import difference
import datetime
import shutil

IMAGES_DIR = Path('images')
SORTED_DIR = Path('sorted')
OUTPUT_DIR = Path('output')

# These specify regions in images to be used as "examples". That is, if another
# image has exactly the same image in the same location, it is assumed to be
# from the same newspaper. Both newspapers and my screenshots weren't always
# consistent, so there are multiple "signature regions" for each paper, and an
# image matches if any one signature region matches.
SIGNATURES_IN_FILES = {
    "fox": [
        ('images/Screenshot_2018-09-05-08-59-19.png', (10, 340, 330, 500)),
        ('images/Screenshot_2019-04-21-09-48-31.png', (10, 340, 330, 500)),
        ('images/Screenshot_2020-06-04-22-33-11.png', (10, 140, 330, 300)),
    ],
    "cnn": [
        ('images/Screenshot_2018-06-17-23-24-36.png', (10, 360, 230, 520)),
        ('images/Screenshot_2019-04-21-09-48-16.png', (10, 360, 230, 520)),
        ('images/Screenshot_2020-05-29-14-20-14.png', (80, 370, 130, 520)),
        ('images/Screenshot_2020-06-02-11-14-57.png', (80, 120, 130, 270)),
        ('images/Screenshot_2018-08-23-18-56-27.png', (10, 700, 230, 850)),
    ],
    "wap": [
        ('images/Screenshot_2018-06-17-23-25-29.png', (60, 160, 210, 270)),
        ('images/Screenshot_2019-05-14-19-16-47.png', (60, 100, 230, 220)),
        ('images/Screenshot_2019-11-20-13-02-31.png', (60, 120, 200, 300)),  # this is the menu icon
        ('images/Screenshot_2020-09-20-23-19-21.png', (60, 160, 200, 300)),  # this is the menu icon
        ('images/Screenshot_2019-04-21-09-48-47.png', (60, 130, 240, 260)),
    ],
}


PAPERS = set(SIGNATURES_IN_FILES.keys())
DIFF_THRESHOLD = 20
HIST_THRESHOLD = 10000

BACKGROUND_COLOUR = (210, 210, 210)
INSIDE_BORDER_WIDTH = 5
INSIDE_BORDER = BACKGROUND_COLOUR * INSIDE_BORDER_WIDTH
SCREENSHOT_WIDTH = 1440
SCREENSHOT_HEIGHT = 2004
TEXT_HEIGHT = 16
TEXT_MARGIN = 4
HEADER_HEIGHT = TEXT_HEIGHT + 2 * TEXT_MARGIN
RESIZED_WIDTH = SCREENSHOT_WIDTH // 4
RESIZED_HEIGHT = SCREENSHOT_HEIGHT // 4
STITCHED_WIDTH = RESIZED_WIDTH * len(PAPERS) + INSIDE_BORDER_WIDTH * (len(PAPERS) - 1)
STITCHED_HEIGHT = HEADER_HEIGHT + RESIZED_HEIGHT

for key in {'none'} | PAPERS:
    (SORTED_DIR / key).mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


def build_signature_library():
    """Converts the data in SIGNATURES_IN_FILES to [(box, region, paper, entryno)]"""
    signature_library = []
    for paper, sigs in SIGNATURES_IN_FILES.items():
        for entryno, (filename, box) in enumerate(sigs):
            im = Image.open(filename)
            region = im.crop(box)
            hist = region.histogram()
            signature_library.append((box, region, hist, paper, entryno))
    return signature_library


def match_image(im, signature_library):
    """Determines which paper an image came from, returning the name of the
    paper and the entry number in the signature library. Uses a crude metric:
    A region "matches" the signature region if either
     - its pixels all match, or differ by at most `DIFF_THRESHOLD`, or
     - the sum (over colors) of the number of times each color occurs (i.e., its
       histogram) differs by at most `HIST_THRESHOLD` (this should capture
       translations, and is overly permissive in theory but works fine given our
       set of images).
    """
    for box, signature, hist, paper, entryno in signature_library:
        region = im.crop(box)
        diff = difference(signature, region)
        diff_value = max(chain(*diff.getextrema()))
        hist_value = sum([abs(x - y) for x, y in zip(hist, region.histogram())])
        if diff_value <= DIFF_THRESHOLD or hist_value <= HIST_THRESHOLD:
            return (paper, entryno, diff_value, hist_value)

    return None, None, None, None


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
        im = Image.open(filepath)
        images[index] = im
        times.append(time)

    # extract median time of image, adjust for time zones
    median_time = sorted(times)[1]
    if median_time > datetime.datetime(2020, 11, 1):
        median_time -= datetime.timedelta(hours=21)
    elif median_time > datetime.datetime(2020, 9, 27):
        median_time -= datetime.timedelta(hours=20)
    elif median_time > datetime.datetime(2020, 9, 1):
        median_time -= datetime.timedelta(hours=19)

    filename = median_time.strftime("stitched-%Y-%m-%d-%H-%M.png")
    print("\033[1;34m → writing to: " + filename + "\033[0m")

    first_rows = []

    # cnn and fox: first row in each the 100th pixel is red
    def find_first_row(im):
        for i in range(96, 400):
            r, g, b = im.getpixel((100, i))
            if r > g and r > b:
                return i
    first_rows = [find_first_row(im) for im in images[:2]]

    # wapo: just burn the first 96 rows if images is from before 2019, 108 rows if after
    first_rows.append(96 if times[2].year < 2019 else 108)

    if None in first_rows:
        print(f"\033[1;31m !! No first row found in one or more images: {first_rows}\033[0m")
        return

    # stitch chosen regions together
    output = Image.new('RGB', (STITCHED_WIDTH, STITCHED_HEIGHT), color=BACKGROUND_COLOUR)
    for i, (first_row, im) in enumerate(zip(first_rows, images)):
        region = im.crop((0, first_row, SCREENSHOT_WIDTH, first_row + SCREENSHOT_HEIGHT))
        resized = region.resize((RESIZED_WIDTH, RESIZED_HEIGHT))
        left = (RESIZED_WIDTH + INSIDE_BORDER_WIDTH) * i
        output.paste(resized, (left, HEADER_HEIGHT, left + RESIZED_WIDTH, HEADER_HEIGHT + RESIZED_HEIGHT))

    date_text = median_time.strftime("%B %-d, %Y, at %-I:%M%P")
    date_font = ImageFont.truetype("DejaVuSans.ttf", size=TEXT_HEIGHT)
    d = ImageDraw.Draw(output)
    d.text((STITCHED_WIDTH // 2, TEXT_MARGIN), date_text, font=date_font, fill=(0, 0, 0), anchor='mt')

    # write to file
    output.save(OUTPUT_DIR / filename)


# Gather signatures
signature_library = build_signature_library()

# Match images
current_group = []
earliest_in_group = None
total_matched = {paper: [0] * len(sigs) for paper, sigs in SIGNATURES_IN_FILES.items()}

for child in sorted(IMAGES_DIR.iterdir()):
    im = Image.open(child)
    paper, entryno, diff_value, hist_value = match_image(im, signature_library)

    if paper is None:
        print(f"{child}: -")
        shutil.copy(child, SORTED_DIR / 'none' / child.name)
        continue

    total_matched[paper][entryno] += 1
    shutil.copy(child, SORTED_DIR / paper / child.name)  # copy to a folder for easy review

    time = datetime.datetime.strptime(child.name, "Screenshot_%Y-%m-%d-%H-%M-%S.png")

    if not current_group:
        current_group.append((paper, child, time))
        earliest_in_group = time

    elif time - earliest_in_group < datetime.timedelta(minutes=6):
        current_group.append((paper, child, time))

    else:
        handle_group(current_group)
        current_group = [(paper, child, time)]
        earliest_in_group = time

    print(f"{child}: {paper} ({entryno}, {diff_value}, {hist_value})")

handle_group(current_group)

for paper, counts in sorted(total_matched.items()):
    total = sum(counts)
    print(f"{paper}, total {total} - {counts}")
