"""
A module implementing a bot to notify editors when articles they create or
expand are nominated for DYK by someone else.
"""

import logging
logging.basicConfig(filename='dyknotifier.log',
                    level=logging.DEBUG,
                    datefmt="%d %b. %Y %I:%M:%S",
                    format="[%(asctime)s] [%(levelname)s] %(message)s")
streamHandler = logging.StreamHandler()
streamHandler.setLevel(logging.INFO)
logging.getLogger().addHandler(streamHandler)

import ConfigParser

# Import pywikibot from wherever the configuration files says
import sys
cfgparser = ConfigParser.RawConfigParser()
cfgparser.read("config.txt")
pwb_location = cfgparser.get("configuration", "pwb_location")
sys.path.append(pwb_location)
try:
    # pylint: disable=import-error
    import pywikibot
    from pywikibot.pagegenerators import CategorizedPageGenerator
    import pywikibot.pagegenerators as pagegenerators
except ImportError:
    logging.critical("Unable to find pywikibot. Exiting...")
    exit()

# Now, import everything else
import argparse
import datetime
import functools
import getpass
import json
import operator
import os
import re
from fuzzywuzzy import fuzz
from bs4 import BeautifulSoup
from clint.textui import progress
from clint.textui import prompt

# These last two are so I can actually edit stuff. TODO: make PWB edit stuff.
# pylint: disable=import-error
from wikitools.wiki import Wiki as WikitoolsWiki
# pylint: disable=import-error
from wikitools.page import Page as WikitoolsPage

# Parse our args. Arrrrrrrghs.
parser = argparse.ArgumentParser(prog="DYKNotifier",
                                 description=\
                                 "Notify editors of their DYK noms.")
parser.add_argument("-i", "--interactive", action="store_true",
                    help="Confirm before each edit.")
parser.add_argument("-c", "--count", type=int, help="Notify at most n people.")
args = parser.parse_args()

# Globals. (Best practices FTW)
g_wiki = pywikibot.Site("en", "wikipedia")
g_people_to_notify = dict()

# Configuration for the user-page-editing part.
SUMMARY = u"[[Wikipedia:Bots/Requests for approval/APersonBot " +\
                "2|Bot]] notification about the DYK nomination of" +\
                " {0}."
MESSAGE = u"\n\n{{{{subst:DYKNom|{0}|passive=yes}}}}"

# And other configuration.
ALREADY_NOTIFIED_FILE = "notified.json"
NOMINATION_TEMPLATE = "Template:Did you know nominations/"

def main():
    global g_wiki, g_people_to_notify
    g_wiki.login()
    get_people_to_notify()
    prune_list_of_people()
    notify_people()

def get_people_to_notify():
    """
    Gets a dict of user talkpages to notify about their creations and
    the noms about which they should be notified.
    """
    global g_people_to_notify, g_wiki
    cat_dykn = pywikibot.Category(g_wiki, "Category:Pending DYK nominations")
    logging.info("Getting nominations from " + cat_dykn.title() + "...")
    BAD_TEXT = ur'(Self(-|\s)nominated|Category:((f|F)ailed|(p|P)assed) DYK)'
    for nomination in CategorizedPageGenerator(cat_dykn, content=True):
        wikitext = nomination.get()
        if not re.search(re.compile(BAD_TEXT, re.I), wikitext):
            who_to_nominate = get_who_to_nominate(wikitext,
                                                  nomination.title())
            for k, v in who_to_nominate.items():
                g_people_to_notify[k] = g_people_to_notify.get(k, []) + [v]

    logging.info("Found " + str(len(g_people_to_notify)) + " people to notify.")

def prune_list_of_people():
    "Removes people who shouldn't be notified from the list."
    global g_people_to_notify
    initial_count = len(g_people_to_notify)

    # Purely for logging purposes.
    def print_people_left(what_was_removed):
        logging.info(str(len(g_people_to_notify)) + " people for " +\
                     str(len(functools.reduce(operator.add,
                                              g_people_to_notify.values()))) +\
                     " nominations left after removing " + what_was_removed +\
                     ".")

    # Prune empty entries
    g_people_to_notify = {k: v for k, v in g_people_to_notify.items() if k}
    print_people_left("empty entries")

    # Prune people I've already notified
    with open(ALREADY_NOTIFIED_FILE) as already_notified_file:

        # Since the outer dict in the file is keyed on month string,
        # smush all the values together to get a dict keyed on username
        already_notified = functools.reduce(merge_dicts,
                                            json.load(
                                                already_notified_file).values(),
                                            {})
        for username, nominations in already_notified.items():
            if username not in g_people_to_notify: continue
            nominations = map(lambda x:NOMINATION_TEMPLATE+x, nominations)
            proposed = set(g_people_to_notify[username])
            g_people_to_notify[username] = list(proposed - set(nominations))
    print_people_left("already-notified people")

    # Prune user talk pages that link to this nom.
    titles = ["User talk:" + username for username in g_people_to_notify.keys()]
    titles_generator = pagegenerators.PagesFromTitlesGenerator(titles)
    nom_iterable = zip(titles_generator, g_people_to_notify.values())
    for user_talk_page, nom_subpage_titles in nom_iterable:
        username = user_talk_page.title(withNamespace=False)
        for outgoing_link in user_talk_page.linkedPages(namespaces=10):
            outgoing_link_name = outgoing_link.title(withNamespace=True)
            if outgoing_link_name in nom_subpage_titles:
                g_people_to_notify[username].remove(outgoing_link_name)
                break # break out of the inner loop
    print_people_left("linked people")

def notify_people():
    global g_people_to_notify

    # First, check if there's even someone to notify
    if len(g_people_to_notify) == 0:
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

    def write_notified_to_file():
        now = datetime.datetime.now()
        now = now.strftime("%B") + " " + str(now.year)
        with open(ALREADY_NOTIFIED_FILE) as already_notified_file:
            already_notified = json.load(already_notified_file)
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
        logging.info("Wrote {} people for {} nominations.".format(
            len(already_notified_this_month),
            len(functools.reduce(operator.add,
                                 already_notified_this_month.values()))))

    for person, nom_names in g_people_to_notify.items():
        for nom_name in map(lambda x:x[34:], nom_names):
            person_ascii = person.encode("ascii", "replace")
            nom_name_ascii = nom_name.encode("ascii", "replace")
            if args.count:
                if len(people_notified) >= args.count:
                    logging.info(str(num_notified) + " notified; exiting.")
                    write_notified_to_file()
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
                    write_notified_to_file()
                    sys.exit(0)
            talkpage = WikitoolsPage(my_wiki, title="User talk:" + person)
            text_to_add = MESSAGE.format(nom_name)
            edit_summary = SUMMARY.format(nom_name)
            try:
                result = talkpage.edit(appendtext=text_to_add,
                                       bot=True,
                                       summary=edit_summary)
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
                write_notified_to_file()
                raise
            except:
                logging.error(u"Error notifying " + unicode(person) + u": " +\
                              unicode(sys.exc_info()[1]))
    write_notified_to_file()

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
    def is_nom_string(x):
        "Is x the line in a DYK nom reading 'Created by... Nominated by...'?"
        return u"Nominated by" in x
    nom_lines = filter(is_nom_string, small_tags)
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
