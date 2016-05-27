import argparse
import logging
import pywikibot
import pywikibot.pagegenerators as generators
import re
import sys
import time

from clint.textui import prompt

from fixer import Processor

REDUNDANT_TEMPLATES = ("on this day", "dyk talk", "itn talk")
SUMMARY = "[[Wikipedia:Bots/Requests for approval/APersonBot 7|Bot]] merging redundant talk page banners into the article history template."

# LOGIN
# ----
site = pywikibot.Site("en", "wikipedia")
site.login()

# PARSE ARGUMENTS
# ----
parser = argparse.ArgumentParser()
parser.add_argument("-i", "--interactive", action="store_true",
                    help="Confirm before each edit.")
parser.add_argument("-c", "--count", type=int,
                    help="Start counting edits at this number.")
parser.add_argument("-l", "--limit", type=int,
                    help="Stop making edits at this number.")
args = parser.parse_args()

# INITIALIZE LOGGING
# ----
# Trick from http://stackoverflow.com/a/6321221/1757964
logging.Formatter.converter = time.gmtime

logging.basicConfig(filename='task.log',
                    level=logging.DEBUG,
                    datefmt="%Y-%m-%dT%H:%M:%SZ",
                    format="[%(asctime)s] [%(levelname)s] %(message)s")
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(stream_handler)

# SET UP PAGE STREAM
# ----
article_history = pywikibot.Page(site, "Template:Article history")
references_args = {"onlyTemplateInclusion": True, "namespaces": (1), "content": True}
references_gen = article_history.getReferences(**references_args)

lower = unicode.lower
def has_redundant_templates(page):
    """Checks if the page should be fixed by this bot."""
    text = lower(page.text)
    text = text[:text.find("==")]
    return any("{{" + template in text for template in REDUNDANT_TEMPLATES)

if args.count:
    num_edits = args.count
    logging.info("Starting off with %d edits made." % num_edits)
else:
    num_edits = 0
for page in references_gen:
    if has_redundant_templates(page):
        logging.debug("About to process %s." % page.title(withNamespace=True).encode("utf-8"))
        page.text = Processor(page.text).get_processed_text()
        if not args.interactive or prompt.yn("Save %s?" % page.title(withNamespace=True).encode("utf-8")):
            page.save(summary=SUMMARY)
            num_edits += 1
            logging.info("%d edits made so far." % num_edits)
            if args.limit and num_edits >= args.limit:
                logging.info("%d edits (limit) reached; done." % num_edits)
                sys.exit(0)
        elif prompt.yn("Exit?"):
            sys.exit(0)
