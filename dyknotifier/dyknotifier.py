"""
A module implementing a bot to notify editors when articles they create or
expand are nominated for DYK by someone else.
"""
import argparse
import datetime
import functools
import getpass
import json
import logging
import operator
import os.path
# pylint: disable=import-error
import pywikibot
import pywikibot.pagegenerators as pagegenerators
import re
import sys
from bs4 import BeautifulSoup
from clint.textui import prompt

# These last two are so I can actually edit stuff. TODO: make PWB edit stuff.
# pylint: disable=import-error
from wikitools.wiki import Wiki as WikitoolsWiki
# pylint: disable=import-error
from wikitools.page import Page as WikitoolsPage

# Configuration for the user-page-editing part.
SUMMARY = u"[[Wikipedia:Bots/Requests for approval/APersonBot " +\
                "2|Bot]] notification about the DYK nomination of" +\
                " {0}."
MESSAGE = u"\n\n{{{{subst:DYKNom|{0}|passive=yes}}}}"

# And other configuration.
ALREADY_NOTIFIED_FILE = "notified.json"
NOMINATION_TEMPLATE = "Template:Did you know nominations/"
BAD_TEXT = ur'(Self(-|\s)nominated|Category:((f|F)ailed|(p|P)assed) DYK)'

def main():
    "The main function."
    init_logging()
    args = parse_args()
    people_to_notify = get_people_to_notify()
    people_to_notify = prune_list_of_people(people_to_notify)
    notify_people(people_to_notify, args)

def init_logging():
    "Initialize logging."
    logging.basicConfig(filename='dyknotifier.log',
                        level=logging.DEBUG,
                        datefmt="%d %b. %Y %I:%M:%S",
                        format="[%(asctime)s] [%(levelname)s] %(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(stream_handler)

def parse_args():
    "Parse the arguments."
    parser = argparse.ArgumentParser(prog="DYKNotifier",
                                     description=\
                                     "Notify editors of their DYK noms.")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Confirm before each edit.")
    parser.add_argument("-c", "--count", type=int,
                        help="Notify at most n people.")
    return parser.parse_args()

def get_people_to_notify():
    """
    Returns a dict of user talkpages to notify about their creations and
    the noms about which they should be notified.
    """
    people_to_notify = dict()
    wiki = pywikibot.Site("en", "wikipedia")
    wiki.login()
    cat_dykn = pywikibot.Category(wiki, "Category:Pending DYK nominations")
    logging.info("Getting nominations from " + cat_dykn.title() + "...")
    for nomination in pagegenerators.CategorizedPageGenerator(
            cat_dykn, content=True):
        wikitext = nomination.get()
        if not re.search(re.compile(BAD_TEXT, re.I), wikitext):
            who_to_nominate = get_who_to_nominate(wikitext,
                                                  nomination.title())
            for username, nomination in who_to_nominate.items():
                people_to_notify[username] = people_to_notify.get(
                    username, []) + [nomination]

    logging.info("Found %d people to notify.", len(people_to_notify))
    return people_to_notify

def prune_list_of_people(people_to_notify):
    "Removes people who shouldn't be notified from the list."

    # Define a couple of helper functions...

    # ... one purely for logging purposes,
    def print_people_left(what_was_removed):
        "Print the number of people left after removing something."
        nominations = functools.reduce(operator.add, people_to_notify.values())
        logging.info("%d people for %d noms left after removing %s.",
                     len(people_to_notify), len(nominations), what_was_removed)

    # ... and another simply to save keystrokes.
    def user_talk_pages():
        titles = ["User talk:" + username for username in people_to_notify.keys()]
        for user_talk_page in pagegenerators.PagesFromTitlesGenerator(titles):

            # First, some sanity checks
            if not user_talk_page.exists() or user_talk_page.isRedirectPage():
                continue

            username = user_talk_page.title(withNamespace=False)
            if not username in people_to_notify:
                continue

            # Then yield the page and username
            yield (user_talk_page, username)

    # Prune empty entries
    people_to_notify = {k: v for k, v in people_to_notify.items() if k}
    print_people_left("empty entries")

    # Prune people I've already notified
    if os.path.isfile(ALREADY_NOTIFIED_FILE):
        with open(ALREADY_NOTIFIED_FILE) as already_notified_file:
            try:
                already_notified_data = json.load(already_notified_file)
            except ValueError as error:
                if error.message != "No JSON object could be decoded":
                    raise
                else:
                    already_notified_data = {}

            # Since the outer dict in the file is keyed on month string,
            # smush all the values together to get a dict keyed on username
            already_notified = functools.reduce(merge_dicts,
                                                already_notified_data.values(),
                                                {})
            for username, nominations in already_notified.items():
                if username not in people_to_notify:
                    continue

                nominations = [NOMINATION_TEMPLATE + x for x in nominations]
                proposed = set(people_to_notify[username])
                people_to_notify[username] = list(proposed - set(nominations))
            print_people_left("already-notified people")

    # Prune user talk pages that link to this nom.
    for user_talk_page, username in user_talk_pages():
        people_to_notify[username] = [nom for nom in people_to_notify[username]
                                      if nom not in user_talk_page.get()]
    people_to_notify = dict([(k, v) for k, v in people_to_notify.items() if v])
    print_people_left("linked people")

    # Prune based on exclusion compliance
    for user_talk_page, username in user_talk_pages():
        if not user_talk_page.botMayEdit():
            del people_to_notify[username]
    print_people_left("people who are excluding this bot")

    return people_to_notify

# Disabling pylint because breaking stuff out into
# methods would spill too much into global scope

# pylint: disable=too-many-branches
def notify_people(people_to_notify, args):
    "Adds a message to people who ought to be notified about their DYK noms."

    # First, check if there's anybody to notify
    if len(people_to_notify) == 0:
        logging.info("Nobody to notify.")
        return

    my_wiki = WikitoolsWiki("http://en.wikipedia.org/w/api.php")

    # Then, login
    while True:
        username = raw_input("Username: ")
        password = getpass.getpass("Password for " + username + " on enwiki: ")
        logging.info("Logging in to enwiki as " + username + "...")
        my_wiki.login(username, password)
        if my_wiki.isLoggedIn():
            break
        logging.error("Error logging in. Try again.")
    logging.info("Successfully logged in as " + my_wiki.username + ".")

    # Finally, do the notification
    people_notified = dict()

    def write_notified_people_to_file():
        """Update the file of notified people with people_notified."""
        now = datetime.datetime.now().strftime("%B") + " " +\
              str(datetime.datetime.now().year)
        with open(ALREADY_NOTIFIED_FILE) as already_notified_file:
            try:
                already_notified = json.load(already_notified_file)
            except ValueError as error:
                if error.message != "No JSON object could be decoded":
                    raise
                else:
                    already_notified = {} # eh, we'll be writing to it anyway

            already_notified_this_month = already_notified.get(now, {})
            with open(ALREADY_NOTIFIED_FILE, "w") as already_notified_file:
                usernames = set(already_notified_this_month.keys() +
                                people_notified.keys())
                for username in usernames:
                    already_notified_this_month[username] = list(set(
                        already_notified_this_month.get(username, []) +\
                        people_notified.get(username, [])))

                already_notified[now] = already_notified_this_month
                json.dump(already_notified, already_notified_file)

        logging.info("Wrote %d people for %d nominations this month.",
                     len(already_notified_this_month),
                     len(functools.reduce(operator.add,
                                          already_notified_this_month.values(),
                                          [])))

    for person, nom_names in people_to_notify.items():
        for nom_name in [x[34:] for x in nom_names]:
            if args.count:
                edits_made = len(functools.reduce(operator.add,
                                                  people_notified.values(), []))
                if edits_made >= args.count:
                    logging.info("%d notified; exiting.", edits_made)
                    write_notified_people_to_file()
                    sys.exit(0)

            if args.interactive:
                logging.info("About to notify " + person + " for " +\
                             nom_name + ".")
                choice = raw_input("What (s[kip], c[ontinue], q[uit])? ")
                if choice[0] == "s":
                    if prompt.yn("Because I've already notified them?"):
                        people_notified[person] = people_notified.get(
                            person, []) + [nom_name]
                    logging.info("Skipping " + person + ".")
                    continue
                elif choice[0] == "q":
                    logging.info("Stop requested; exiting.")
                    write_notified_people_to_file()
                    sys.exit(0)
            talkpage = WikitoolsPage(my_wiki, title="User talk:" + person)
            try:
                result = talkpage.edit(appendtext=MESSAGE.format(nom_name),
                                       bot=True,
                                       summary=SUMMARY.format(nom_name))
                if result[u"edit"][u"result"] == u"Success":
                    logging.info("Success! Notified " + person +\
                                 " because of " + nom_name + ".")
                    people_notified[person] = people_notified.get(person, []) +\
                                              [nom_name]
                else:
                    logging.error("Couldn't notify " + person +\
                                  " because of " + nom_name + " - result: " +\
                                  str(result))
            except (KeyboardInterrupt, SystemExit):
                write_notified_people_to_file()
                raise
            except UnicodeEncodeError:
                logging.error(u"Unicode encoding error notifying " +\
                              unicode(person) +\
                              u" about " + unicode(nom_name) + u": " +\
                              unicode(sys.exc_info()[1]))
    write_notified_people_to_file()

def get_who_to_nominate(wikitext, title):
    """
    Given the wikitext of a DYK nom and its title, return a dict of user
    talkpages of who to notify and the titles of the noms for which they
    should be notified).
    """
    if "#REDIRECT" in wikitext:
        logging.error(title + " is a redirect.")
        return {}

    if "<small>" not in wikitext:
        logging.error("<small> not found in " + title)
        return {}

    soup = BeautifulSoup(wikitext)
    small_tags = [unicode(x.string) for x in soup.find_all("small")]
    def is_nom_string(text):
        "Is text the line in a DYK nom reading 'Created by... Nominated by...'?"
        return u"Nominated by" in text
    nom_lines = [tag for tag in small_tags if is_nom_string(tag)]
    if not len(nom_lines) == 1:
        logging.error(u"Small tags for " + title + u": " + unicode(small_tags))
        return {}

    # Every user whose talk page is linked to within the <small> tags
    # is assumed to have contributed. Looking for piped links to user
    # talk pages.
    usernames = usernames_from_text_with_sigs(nom_lines[0])

    # If there aren't any usernames, WTF and exit
    if len(usernames) == 0:
        logging.error("WTF, no usernames for " + title)
        return {}

    # The last one is the nominator.
    nominator = usernames[-1]

    # Removing all instances of nominator from usernames, since he or she
    # already knows about the nomination
    while nominator in usernames:
        usernames.remove(nominator)

    # Removing people who have contributed to the discussion
    discussion_text = wikitext[wikitext.find("</small>") + len("</small>"):]
    discussion = usernames_from_text_with_sigs(discussion_text)
    usernames = [user for user in usernames if user not in discussion]

    result = dict()
    for username in usernames:
        result[username] = title

    return result

def usernames_from_text_with_sigs(wikitext):
    "Returns the users whose talk pages are linked to in the wikitext."
    return [wikitext[m.end():m.end()+wikitext[m.end():].find("|")]\
            for m in re.finditer(r"User talk:", wikitext)]

# From http://stackoverflow.com/a/26853961/1757964
def merge_dicts(*dict_args):
    '''
    Given any number of dicts, shallow copy and merge into a new dict,
    precedence goes to key value pairs in latter dicts.
    '''
    result = {}
    for dictionary in dict_args:
        result.update(dictionary)
    return result

if __name__ == "__main__":
    main()
