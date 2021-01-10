import argparse
import png
from pathlib import Path
from itertools import islice
from collections import Counter
import shutil
import datetime

IMAGES_DIR = Path('images')

# These specify rows (of pixels) in images that are used as "examples". That is,
# if another image has the same row of pixels at the same vertical location, it
# is assumed to be from the same newspaper. Both newspapers and my screenshots
# weren't always consistent, so there are multiple "signature rows" for each
# paper, and an image matches if any one signature row matches. The Washington
# Post needs more signatures because it doesn't have any unique colours (unlike
# Fox's blue and CNN's red), so we have to take a row that crosses its logo,
# which is too complicated to be consistent. (Also, its design changed more
# often.)
signatures_in_files = {
    "fox": [
        ('images/Screenshot_2018-09-05-08-59-19.png', 329),
        ('images/Screenshot_2018-11-22-12-11-31.png', 353),
        ('images/Screenshot_2020-06-04-22-33-11.png', 117),
        ('images/Screenshot_2020-05-29-14-19-45.png', 397),
    ],
    "cnn": [
        ('images/Screenshot_2018-06-22-10-01-24.png', 339),
        ('images/Screenshot_2018-08-23-18-56-27.png', 655),
        ('images/Screenshot_2018-09-05-18-27-31.png', 328),
        ('images/Screenshot_2018-11-07-18-15-31.png', 352),
        ('images/Screenshot_2019-04-21-09-48-16.png', 388),
        ('images/Screenshot_2020-12-11-19-49-31.png', 108),
        ('images/Screenshot_2020-05-29-14-20-14.png', 396),
    ],
    "wap": [
        ('images/Screenshot_2018-09-05-18-27-49.png', 169),
        ('images/Screenshot_2018-11-08-09-27-13.png', 170),
        ('images/Screenshot_2019-07-28-20-29-21.png', 171),
        ('images/Screenshot_2019-11-05-18-51-15.png', 174),
        ('images/Screenshot_2020-02-11-13-19-33.png', 172),
        ('images/Screenshot_2020-02-18-14-23-00.png', 173),
        ('images/Screenshot_2020-04-18-03-37-26.png', 168),
        ('images/Screenshot_2020-09-28-12-55-09.png', 200),
        ('images/Screenshot_2019-12-20-09-58-03.png', 166),
        ('images/Screenshot_2020-11-08-21-19-42.png', 167),
        ('images/Screenshot_2020-10-01-08-09-57.png', 181),
        ('images/Screenshot_2020-12-24-16-19-17.png', 197),
        ('images/Screenshot_2021-01-04-08-30-50.png', 196),
    ]
}

Path('none').mkdir(exist_ok=True)
for key in signatures_in_files:
    Path(key).mkdir(exist_ok=True)

signatures_by_row = {}
for paper, sigs in signatures_in_files.items():
    for i, (filename, rowno) in enumerate(sigs):
        reader = png.Reader(filename)
        _, _, values, _ = reader.read()
        row = next(islice(values, rowno, rowno+1))
        signatures_by_row.setdefault(rowno, {}).update({paper: row})

matched_images = [] # (path, paper, time)
total_captured = Counter()
total_captured_by_paper = Counter()

for child in sorted(IMAGES_DIR.iterdir()):
    reader = png.Reader(str(child))
    width, height, values, properties = reader.read()
    if width != 1440:
        print(f"{child}: wrong dimension ({height} x {width})")

    for i, row in enumerate(islice(values, 108, 656), start=108):
        for name, signature in signatures_by_row.get(i, {}).items():
            if row == signature:
                print(f"{child}: {name} at {i}")
                total_captured[(name, i)] += 1
                total_captured_by_paper[name] += 1

                # copy to a folder for easy review
                shutil.copy(child, Path(name) / child.name)

                # log in matched images
                time = datetime.datetime.strptime(child.name, "Screenshot_%Y-%m-%d-%H-%M-%S.png")
                matched_images.append((child, name, time))
                break
        else:
            continue
        break
    else:
        print(f"{child}: -")
        shutil.copy(child, Path('none') / child.name)

print("\nFrom each signature:")
for (name, rowno), count in sorted(total_captured.items()):
    print(f"{name} at {rowno}: {count}")

print("\nFrom each paper:")
for name, count in sorted(total_captured_by_paper.items()):
    print(f"{name}: {count}")

print("\nAttempt to group:")
current_group = []
earliest_in_group = None
for path, paper, time in matched_images:

    if not current_group:
        current_group.append((path, paper, time))
        earliest_in_group = time
        continue

    if time - earliest_in_group < datetime.timedelta(minutes=5):
        current_group.append((path, paper, time))
    else:
        # end group
        print("Group:")
        for thispath, thispaper, _ in current_group:
            print(f" - {thispaper} {thispath}")

        current_group = [(path, paper, time)]
        earliest_in_group = time