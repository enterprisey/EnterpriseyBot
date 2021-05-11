import argparse
import datetime
import pywikibot
import pywikibot.pagegenerators as generators
import re
import sys
import time

from clint.textui import prompt

from fixer import process

REDUNDANT_TEMPLATES = ("on this day", "dyk talk", "itn talk")
SUMMARY = "[[Wikipedia:Bots/Requests for approval/APersonBot 7|Bot]] merging redundant talk page banners into the article history template."

def print_log(info):
    print("[{}] {}".format(datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), info))

print_log("Starting article-history at " + datetime.datetime.utcnow().isoformat())

# Log in
site = pywikibot.Site("en", "wikipedia")
site.login()

# Parse args
parser = argparse.ArgumentParser()
parser.add_argument("-i", "--interactive", action="store_true",
                    help="Confirm before each edit.")
parser.add_argument("-c", "--count", type=int,
                    help="Start counting edits at this number.")
parser.add_argument("-l", "--limit", type=int,
                    help="Stop making edits at this number.")
args = parser.parse_args()

# Set up refs gen
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
    print_log("Starting off with %d edits made." % num_edits)
else:
    num_edits = 0
for page in references_gen:
    if has_redundant_templates(page):
        print("About to process %s." % page.title(withNamespace=True).encode("utf-8"))
        page.text = process(page.text)
        if not args.interactive or prompt.yn("Save %s?" % page.title(withNamespace=True).encode("utf-8")):
            page.save(summary=SUMMARY)
            num_edits += 1
            print_log("%d edits made so far." % num_edits)
            if args.limit and num_edits >= args.limit:
                print_log("%d edits (limit) reached; done." % num_edits)
                sys.exit(0)
        elif prompt.yn("Exit?"):
            sys.exit(0)
