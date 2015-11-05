import argparse
import json
import re

from clint.textui import progress
import pywikibot
import pywikibot.pagegenerators as pagegenerator

COMMENT = "[[Wikipedia:Bots/Requests for approval/APersonBot 3|Bot]] fixing duplicated Teahouse invitations"
CATEGORY = "Category:Wikipedians who have received a Teahouse invitation through AfC"
CATEGORIES = (CATEGORY, "Category:Wikipedians who have received a Teahouse invitation")
STATE_FILE = "saved_state.json"

WIKI = pywikibot.Site("en", "wikipedia")
WIKI.login()

# Load the template
with open("invite-template.txt", "r") as template_file:
    INVITE_PATTERN = re.compile(template_file.read())

# Parse the arguments
parser = argparse.ArgumentParser(prog="teahouse-invite",
                                 description="Fix duplicated Teahouse invites.")
parser.add_argument("-p", "--page", type=str,
                    help="A specific page to process.")
args = parser.parse_args()

# Load the saved state
with open(STATE_FILE) as state_file:
    saved_state = json.load(state_file)
    edits_made = [saved_state["edits_made"]]
    current_username = saved_state["current_username"]

print("Starting on %s, with %d edits made." % (current_username, edits_made[0]))

pages_scanned = 0
teahouse_img_pages = pywikibot.FilePage(WIKI, "File:WP teahouse logo 2.png").usingPages()
for page in teahouse_img_pages if not args.page else [pywikibot.Page(WIKI, args.page)]:
    try:
        if page.isRedirectPage():
            continue

        page_text = page.get()

        pages_scanned += 1
        if (pages_scanned % 100) == 0:
            print("Scanned %d pages." % pages_scanned)
            if (pages_scanned % 1000) == 0:
                print("Current page: %s; edits made: %d" % (page.title(withNamespace=True), edits_made[0]))
                if (pages_scanned % 10000) == 0:
                    with open(STATE_FILE, "w") as state_file:
                        current_state = {"edits_made": edits_made[0],
                                         "current_username": page.title(withNamespace=False)}
                        json.dump(current_state, state_file)
                        print("Dumped state to %s." % STATE_FILE)

        # Fix page text
        matches = INVITE_PATTERN.findall(page_text)
        if (not matches) or (len(matches) == 1 and any(x in page_text for x in CATEGORIES)):
            continue

        for match in matches[1:]:
            page_text = page_text.replace(match[0], "")

        # Add a maintenance category, if there isn't already one
        if not any(x in page_text for x in CATEGORIES):
            page_text = page_text.replace(matches[0][0], matches[0][0] + "\n\n[[" + CATEGORY + "]]")

        def page_save_callback(_, exception):

            # The "exception" argument is None if the edit was successful
            if not exception:
                edits_made[0] = edits_made[0] + 1
                print("We've made %d edits." % edits_made[0])

        page.save(text=page_text, comment=COMMENT, callback=page_save_callback)
    except:
        current_username = page.title(withNamespace=False)
        print("Leaving off at '%s'" % current_username)
        with open(STATE_FILE, "w") as state_file:
            current_state = {"edits_made": edits_made[0],
                             "current_username": current_username}
            json.dump(current_state, state_file)
            print("Dumped state.")
        raise
