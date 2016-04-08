"""
A bot to help WP:ALBUM with some lists.
"""
import argparse
from datetime import date
from itertools import groupby
import json
import logging
from operator import itemgetter
import os
import os.path
import re
import string

from clint.textui import progress
import pywikibot
import pywikibot.pagegenerators as pagegenerator

ALBUM_PAGE_CACHE = "s.json"
INFOBOX_PAGE_CACHE = "m.json"

def main():
    "The main function."
    init_logging()
    global wiki
    wiki = pywikibot.Site("en", "wikipedia")
    wiki.login()

    # Use list_regex to make a few lists
    list4 = lambda: list_regex(r".*\(.*Album.*\)")
    list5 = lambda: list_regex(r".*(\s(are|is|it|my|our|that|their|this)\s)|[\w ]+" +
                              r"(\s(A|An|And|At|For|From|In|Into|Of|On|Or|The|To|With)\s).*")
    list6 = lambda: list_category("All disputed non-free Wikipedia files")
    list7 = lambda: list_category("All Wikipedia files with no non-free use rationale")
    list4.__name__, list5.__name__, list6.__name__, list7.__name__ = "list4", "list5", "list6", "list7"

    # Parse args to find out which lists
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--lists", nargs="+", type=int, required=True,
                        help="The numbers of the lists to make.")
    args = parser.parse_args()
    logging.info("Going to make " +
                 list_to_description(["list " + str(x) for x in args.lists]))
    list_functions = {3: list3, 4: list4, 5: list5, 6: list6, 7: list7}

    for list_number in args.lists:
        list_function = list_functions[list_number]
        function_name = list_function.__name__
        print
        logging.info("Starting work on %s" % function_name)
        article_list = list_function()
        wikitext_list = build_wikitext_list(article_list)
        with open(function_name + ".txt", "w") as text_file:
            text_file.write(wikitext_list.encode("utf-8"))
        target_page = pywikibot.Page(wiki, title="User:APersonBot/sandbox/" +
                                     function_name)
        target_page.save(text=wikitext_list,
                         comment="Bot updating maintenance list for WP:ALBUMS")

def list3():
    "This is a list of album articles without infoboxes."
    global wiki

    FORCE_CACHE_RELOAD = False

    if (not os.path.exists(INFOBOX_PAGE_CACHE)) or FORCE_CACHE_RELOAD:
        keyed_pages = {}
        for template_name in ["Template:WikiProject Albums",
                              "Template:Infobox album"]:
            template = pywikibot.Page(wiki, template_name)
            logging.info("Initialized an object for %s" % template_name)
            template_pages = template.getReferences(onlyTemplateInclusion=True)
            logging.info("Got a generator of pages transcluding %s" % template_name)
            template_page_titles = []
            for page in progress.mill(template_pages, expected_size=200000,
                                      label="Converting "):
                template_page_titles.append(page.title(withNamespace=False))
            logging.info("Turned that list into a list of %d titles." % len(template_page_titles))
            template_page_titles = key_on_first_letter(template_page_titles)
            logging.info("Keyed that list on title, forming a %d-key dict."
                         % len(template_page_titles))
            keyed_pages[template_name] = template_page_titles
            with open(template_name[-1], "w") as cache:
                json.dump(template_page_titles, cache)
            print

        album_pages = keyed_pages["Template:WikiProject Albums"]
        infoboxed_pages = keyed_pages["Template:Infobox album"]
    else:
        with open(ALBUM_PAGE_CACHE, "r") as cache:
            album_pages = json.load(cache)
        with open(INFOBOX_PAGE_CACHE, "r") as cache:
            infoboxed_pages = json.load(cache)

    logging.info("Removing album pages that already have infoboxes...")
    for letter in progress.bar(album_pages):
        if letter not in infoboxed_pages:
            continue

        for album in album_pages[letter]:
            if album in infoboxed_pages[letter]:
                album_pages[letter].remove(album)
                infoboxed_pages[letter].remove(album)

    logging.info("Done removing album pages with infoboxes!")

    return album_pages

def list_regex(expression):
    'Gets a list of album pages with whose names match the regex in their name'
    global wiki
    wikiproject_template = pywikibot.Page(wiki, "Template:WikiProject Albums")
    album_pages = wikiproject_template.getReferences(onlyTemplateInclusion=True)
    logging.info("Got a generator of album pages.")
    album_titles = []
    for page in progress.mill(album_pages, expected_size=200000,
                              label="Converting "):
        album_titles.append(page.title(withNamespace=True))
    logging.info("Turned that into a list of %d titles." % len(album_titles))

    INCORRECT = re.compile(expression)
    incorrect_pages = []
    for page_title in progress.bar(album_titles, label="Filtering "):
        if INCORRECT.match(page_title):
            incorrect_pages.append(page_title)

    to_be_removed = []
    for page_title in progress.bar(incorrect_pages, label="-Internal "):
        page = pywikibot.Page(wiki, page_title)
        category_titles = [x.title() for x in page.categories()]
        if "Category:Project-Class Album articles" in category_titles:
            to_be_removed.append(page_title)
    for page_title in to_be_removed:
        incorrect_pages.remove(page_title)

    to_be_removed = []
    for page_title in progress.bar(incorrect_pages, label="Unicode "):
        try:
            page_title.decode("ascii")
        except UnicodeEncodeError:
            to_be_removed.append(page_title)
    for page_title in to_be_removed:
        incorrect_pages.remove(page_title)

    return incorrect_pages

def list_category(category_name):
    'Gets a list of album covers that intersect with the specified category'
    album_covers_cat = pywikibot.Category(wiki, title="Category:Album covers")
    category_name = (category_name if category_name.startswith("Category:")
                     else "Category:" + category_name)
    other_cat = pywikibot.Category(wiki, title=category_name)

    # Get a list of album covers
    album_covers = []
    num_album_covers = album_covers_cat.categoryinfo["files"]
    for album_cover in progress.bar(album_covers_cat.articles(),
                                    label="Getting titles ",
                                    expected_size=num_album_covers):
        album_covers.append(album_cover.title(withNamespace=False))
    album_covers = key_on_first_letter(album_covers)

    # Get a list of other images
    num_other = other_cat.categoryinfo["files"]
    other_list = []
    for other in progress.bar(other_cat.articles(),
                              label="Getting other titles ",
                              expected_size=num_other):
        other_list.append(other.title(withNamespace=False))
    other_dict = key_on_first_letter(other_list)

    # Get that intersection
    result_list = {}
    for letter in progress.bar(album_covers,
                               label="Intersecting "):
        if letter not in other_dict:
            continue

        for album_cover in album_covers[letter]:
            if album_cover in other_dict[letter]:
                result_list[letter] = result_list.get(letter, []) +\
                                      [album_cover]
                other_dict[letter].remove(album_cover)

    return result_list

def build_wikitext_list(pages, force_no_key=False):

    # Flat lists more than 15 pages long get keyed on first letter
    if isinstance(pages, list) and len(pages) > 15:
        pages = key_on_first_letter(pages)

    if hasattr(pages, "items"):
        return build_wikitext_list_from_dict(pages)
    else:
        return "".join(["\n* [[%s]]" % page for page in pages])

def build_wikitext_list_from_dict(pages):
    wikitext_list = "Last updated: " + date.strftime(date.today(), "%-d %B %Y")

    if not pages:
        return wikitext_list + "\n\n(no items)"

    bar_label = "Building a list "
    for letter, pages in progress.bar(sorted(pages.items()), label=bar_label):
        wikitext_list += "\n\n=== %s ===" % letter
        for page in pages:
            wikitext_list += "\n* [[%s]]" % page
    return wikitext_list

def init_logging():
    "Initialize logging."
    logging_filename = os.path.basename(__file__)[:-3] + ".log"
    logging.basicConfig(filename=logging_filename,
                        level=logging.DEBUG,
                        datefmt="%d %b. %Y %I:%M:%S",
                        format="[%(asctime)s] [%(levelname)s] %(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(stream_handler)

def key_on_first_letter(the_list):
    """
    Splits a list based on the first letter of each item.
    http://stackoverflow.com/a/17366841/1757964
    """
    groupby_object = groupby(sorted(the_list), key=itemgetter(0))
    return {key: list(value) for key, value in groupby_object}

def list_to_description(the_list):
    return ", ".join(map(str, the_list[:-1])) +\
        (" and " if len(the_list) > 1 else "") +\
        str(the_list[-1])

if __name__ == "__main__":
    main()
