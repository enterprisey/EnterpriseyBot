import argparse
import datetime
import pywikibot
import re
import sys
import time

from clint.textui import prompt

BATTLE_TITLE = re.compile(r"Battle of (.+)")
CATEGORY = re.compile(r"\[\[Category:(.+?)(?:\|(.+?))?\]\]")
SUMMARY = "[[Wikipedia:Bots/Requests for approval/APersonBot 8|Bot]] {} for an article about a battle"
BATTLE_CATEGORY_KEYWORDS = ("battle", "conflict", "military history", "war", "offensive")

def print_log(what_to_print):
    print(datetime.datetime.utcnow().strftime("[%Y-%m-%dT%H:%M:%SZ] ") + what_to_print)

def get_parsed_args():
    """Parse and return args."""
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Confirm before each edit.")
    parser.add_argument("-c", "--count", type=int,
                        help="Start counting edits at this number.")
    parser.add_argument("-l", "--limit", type=int,
                        help="Stop making edits at this number.")
    parser.add_argument("-p", "--page", type=str,
                        help="Process ONLY this page.")
    return parser.parse_args()

def is_battle_category(category_name):
    """Determines whether a category is a battle category based on its name."""
    category_name = category_name.lower()
    return any(x in category_name for x in BATTLE_CATEGORY_KEYWORDS)

def is_actual_battle(page):
    """Checks if a page is in any battle categories."""
    return any(is_battle_category(each_category.title()) for each_category in page.categories())

def add_defaultsort(wikitext, defaultsort):
    """Removes all cat keys and adds the provided defaultsort to the wikitext."""
    description_of_changes = ""

    # First, remove cat keys
    if re.search(r"\[\[Category:.+\|.+\]\]", wikitext):
        description_of_changes = "removing existing category keys and "
    wikitext = re.sub(r"\[\[Category:(.+)\|.+\]\]", r"[[Category:\1]]", wikitext)

    # Then, add the defaultsort
    description_of_changes += "adding a defaultsort"
    category_start = wikitext.find("[[Category:")
    wikitext = wikitext[:category_start] + "{{DEFAULTSORT:%s}}\n" % defaultsort + wikitext[category_start:]
    return wikitext, description_of_changes

# From http://stackoverflow.com/a/3844832/1757964
def checkEqual(iterator):
    try:
        iterator = iter(iterator)
        first = next(iterator)
        return all(first == rest for rest in iterator)
    except StopIteration:
        return True

def makeKey(page_title):
    """Makes a battle cat key or a defaultsort key."""
    rest_of_title = BATTLE_TITLE.search(page_title).group(1)
    if re.search(r"^[\w\- ]+$", rest_of_title):
        return rest_of_title
    if re.search(r"^[\w\- ]+\((?:\w+ )?\d+\)$", rest_of_title):
        return rest_of_title.replace("(", "").replace(")", "")
    else:
        print_log("WARNING: Can't process title: {}".format(page_title.encode("utf-8")))
        return rest_of_title

def process(page_object):
    """Adds appropriate defaultsorts, based on cats."""
    page_title = page_object.title(withNamespace=False)
    wikitext = page_object.get()
    global_key = makeKey(page_title) # The thing that goes in a defaultsort or a cat key
    description_of_changes = ""

    if "DEFAULTSORT" in wikitext:
        print_log("{} already has a defaultsort.".format(page_title.encode("utf-8")))
        return

    categories = [x.groups() for x in CATEGORY.finditer(wikitext)]
    battle_categories = [x for x in categories if is_battle_category(x[0])]
    if len(battle_categories) != len(categories):

        # Some categories aren't battle categories, so a defaultsort won't work.
        # So, we add a category key to every battle category.
        categories_changed = 0
        for cat_name, cat_key in battle_categories:
            if not cat_key:
                cat_name = unicode(cat_name)
                wikitext = wikitext.replace(u"[[Category:{}]]".format(cat_name),
                                            u"[[Category:{}|{}]]".format(cat_name, unicode(global_key)))
                categories_changed += 1
        description_of_changes = "updating {} categor{} with sort keys".format(categories_changed,
                                                                               "y" if categories_changed == 1 else "ies")
    else:

        # Add a defaultsort
        wikitext, description_of_changes = add_defaultsort(wikitext, global_key)

    # If every single category has a key, that's pretty much equal to having a defaultsort
    categories = [x.groups() for x in CATEGORY.finditer(wikitext)]
    if "DEFAULTSORT" not in wikitext and categories[0][1] and checkEqual(x[1] for x in categories):
        wikitext, description_of_changes = add_defaultsort(wikitext, global_key)

    page_object.text = wikitext
    return description_of_changes

def main():
    print_log("Starting battle-catsort at " + datetime.datetime.utcnow().isoformat())

    site = pywikibot.Site("en", "wikipedia")
    site.login()

    args = get_parsed_args()
    if args.count:
        num_edits = args.count
        print_log("Starting off with %d edits made." % num_edits)
    else:
        num_edits = 0

    for each_page in [pywikibot.Page(site, args.page)] if args.page else site.allpages("Battle of", filterredir=False):
        each_title = each_page.title(withNamespace=False).encode("utf-8")
        title_match = BATTLE_TITLE.search(each_title)

        if not title_match:
            print_log("Somehow {} didn't match.".format(each_title))
            continue

        if not is_actual_battle(each_page):
            print_log("{} isn't an actual battle.".format(each_title))
            continue

        print_log("About to process {}.".format(each_title))
        old_text = each_page.text
        changes_made = process(each_page)
        if old_text == each_page.text:
            print_log("No changes made to {}.".format(each_title))
            continue

        if not args.interactive or prompt.yn("({}) Save {}?".format(changes_made, each_title)):
            each_page.save(summary=SUMMARY.format(changes_made))
            num_edits += 1
            print_log("%d edits made so far." % num_edits)
            if args.limit and num_edits >= args.limit:
                print_log("%d edits (limit) reached; done." % num_edits)
                sys.exit(0)
        elif prompt.yn("Exit?"):
            sys.exit(0)

if __name__ == "__main__":
    main()
