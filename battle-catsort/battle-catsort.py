import argparse
import datetime
import logging
import pywikibot
import re
import sys
import time

BATTLE_TITLE = re.compile(r"Battle of (.+)(?:\(\w+\))?")
LOGGING_FILENAME = "task.log"
SUMMARY = "[[Wikipedia:Bots/Requests for approval/APersonBot 8|Bot]] adding a sensible defaultsort for an article about a battle"

def is_actual_battle(page):
    """Checks if a page is in any battle categories."""
    for each_category in page.categories():
        each_title = each_category.title(withNamespace=False)
        if "battle" in each_title.lower():
            return True
    return False

def setup_logging():
    """Initialize logging."""
    # Trick from http://stackoverflow.com/a/6321221/1757964
    logging.Formatter.converter = time.gmtime

    logging.basicConfig(filename='task.log',
                        level=logging.DEBUG,
                        datefmt="%Y-%m-%dT%H:%M:%SZ",
                        format="[%(asctime)s] [%(levelname)s] %(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(stream_handler)

def get_parsed_args():
    """Parse and return args."""
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Confirm before each edit.")
    parser.add_argument("-c", "--count", type=int,
                        help="Start counting edits at this number.")
    parser.add_argument("-l", "--limit", type=int,
                        help="Stop making edits at this number.")
    return parser.parse_args()

def main():
    setup_logging()
    logging.info("Starting battle-catsort at " + datetime.datetime.utcnow().isoformat())

    site = pywikibot.Site("en", "wikipedia")
    site.login()

    args = get_parsed_args()
    if args.count:
        num_edits = args.count
        logging.info("Starting off with %d edits made." % num_edits)
    else:
        num_edits = 0

    for each_page in site.allpages("Battle of", filterredir=False):
        each_title = each_page.title(withNamespace=False)
        title_match = BATTLE_TITLE.search(each_title)

        if not title_match:
            print("Somehow {} didn't match.".format(each_title))
            continue
        if not is_actual_battle(each_page):
            print("{} isn't an actual battle.".format(each_title))
            continue

        wikitext = each_page.get()
        battle_name = title_match.group(1)
        if "DEFAULTSORT" not in wikitext:
            logging.debug("About to process %s." % each_title.encode("utf-8"))
            category_start = wikitext.find("[[Category:")
            wikitext = wikitext[:category_start] + "{{DEFAULTSORT:%s}}\n" % battle_name + wikitext[category_start:]
            each_page.text = wikitext
            if not args.interactive or prompt.yn("Save %s?" % each_title.encode("utf-8")):
                each_page.save(summary=SUMMARY)
                num_edits += 1
                logging.info("%d edits made so far." % num_edits)
                if args.limit and num_edits >= args.limit:
                    logging.info("%d edits (limit) reached; done." % num_edits)
                    sys.exit(0)
            elif prompt.yn("Exit?"):
                sys.exit(0)

if __name__ == "__main__":
    main()
