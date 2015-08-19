import argparse
import re

from clint.textui import progress
import pywikibot
import pywikibot.pagegenerators as pagegenerator

COMMENT = "[[Wikipedia:Bots/Requests for approval/APersonBot 3|Bot]] fixing duplicated Teahouse invitations"
CATEGORY = "Category:Wikipedians who have received a Teahouse invitation through AfC"
CATEGORIES = (CATEGORY, "Category:Wikipedians who have received a Teahouse invitation")

WIKI = pywikibot.Site("en", "wikipedia")
WIKI.login()

# Load the template
with open("template", "r") as template_file:
    INVITE_PATTERN = re.compile(template_file.read())

# Parse the arguments
parser = argparse.ArgumentParser(prog="teahouse-invite",
                                 description="Fix duplicated Teahouse invites.")
parser.add_argument("-p", "--page", type=str,
                    help="A specific page to process.")
args = parser.parse_args()

edits_made = [0]
pages_scanned = 0
user_talk_pages = pagegenerator.AllpagesPageGenerator(namespace=3, site=WIKI,
                                                      content=True,
                                                      includeredirects=False)
preloaded_pages = pagegenerator.PreloadingGenerator(user_talk_pages)
for page in preloaded_pages if not args.page else [pywikibot.Page(WIKI, args.page)]:
    page_text = page.get()

    pages_scanned += 1
    if (pages_scanned % 100) == 0:
        print("Scanned %d pages." % pages_scanned)

    # Fix page text
    matches = INVITE_PATTERN.findall(page_text)
    if not matches or len(matches) == 1:
        continue

    print("FOUND ONE: %s" % page.title(withNamespace=True))
    for match in matches[1:]:
        page_text = page_text.replace(match[0], "")

    # Add a maintenance category, if there isn't already one
    if not any(x in page_text for x in CATEGORIES):
        page_text = page_text + "\n\n[[" + CATEGORY + "]]"

    def page_save_callback(the_page, exception):

        # The "exception" argument is None if the edit was successful
        if not exception:
            edits_made[0] = edits_made[0] + 1
            print("We've made %d edits." % edits_made[0])

    page.save(text=page_text, comment=COMMENT, callback=page_save_callback)
