"""
A bot to help WP:ALBUM with some lists.
"""
import argparse
from itertools import groupby
import logging
from operator import itemgetter
import os
import re
import string

from clint.textui import progress
import pywikibot
import pywikibot.pagegenerators as pagegenerator

def main():
    "The main function."
    init_logging()
    global wiki
    wiki = pywikibot.Site("en", "wikipedia")
    wiki.login()
    for list_function in [list4]:
        function_name = list_function.__name__
        print
        logging.info("Starting work on %s" % function_name)
        article_list = list_function()
        wikitext_list = build_wikitext_list(article_list)
        with open(function_name + ".txt", "w") as text_file:
            text_file.write(wikitext_list)

def list3():
    "This is a list of album articles without infoboxes."
    global wiki

    keyed_pages = {}
    for template_name in ["Template:WikiProject Albums",
                          "Template:Infobox album"]:
        template = pywikibot.Page(wiki, template_name)
        logging.info("Initialized an object for %s" % template_name)
        template_pages = template.getReferences(onlyTemplateInclusion=True)
        logging.info("Got a generator of pages transcluding %s" % template_name)
        template_page_titles = [page.title(withNamespace=False)
                                for page in template_pages]
        logging.info("Turned that list into a list of %d titles." % len(template_page_titles))
        template_page_titles = key_on_first_letter(template_page_titles)
        logging.info("Keyed that list on title, forming a %d-key dict."
                     % len(template_page_titles))
        keyed_pages[template_name] = template_page_titles
        print

    album_pages = keyed_pages["Template:WikiProject Albums"]
    infoboxed_pages = keyed_pages["Template:Infobox album"]

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

def list4():
    'Gets a list of album pages with "Album" in their name'
    global wiki
    wikiproject_template = pywikibot.Page(wiki, "Template:WikiProject Albums")
    album_pages = wikiproject_template.getReferences(onlyTemplateInclusion=True)
    logging.info("Got a generator of album pages.")
    album_pages = [page.title(withNamespace=True) for page in album_pages]
    logging.info("Turned that into a list of %d titles." % len(album_pages))

    INCORRECT = re.compile("\(.*Album.*\)")
    incorrect_pages = []
    for page_title in progress.bar(album_pages, label="list4 "):
        if INCORRECT.match(page_title):
            incorrect_pages.append(page_title)

    to_be_removed = []
    for page_title in progress.bar(incorrect_pages, label="Internal "):
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

def build_wikitext_list(pages):

    # Flat lists more than 15 pages long get keyed on first letter
    if isinstance(pages, list) and len(pages) > 15:
        pages = key_on_first_letter(pages)

    if hasattr(pages, "items"):
        return build_wikitext_list_from_dict(pages)
    else:
        return "".join(["\n* [[%s]]" % page for page in pages])

def build_wikitext_list_from_dict(pages):
    wikitext_list = ""
    bar_label = "Building a list "
    for letter, pages in progress.bar(pages.items(), label=bar_label):
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

if __name__ == "__main__":
    main()
