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
    from pywikibot import Site, Page
except ImportError:
    logging.critical("Unable to find pywikibot. Exiting...")
    exit()

# Import the API library from pywikibot
import os
sys.path.append(os.path.join(pwb_location, "pywikibot", "data"))
# pylint: disable=import-error
import api

# Now, import everything else
import argparse
import json
import re
from fuzzywuzzy import fuzz
from bs4 import BeautifulSoup
from clint.textui import progress
from clint.textui import colored

# Parse our args. Arrrrrrrghs.
parser = argparse.ArgumentParser(prog="DYKNotifier",
                                 description=\
                                 "Notify editors of their DYK noms.")
parser.add_argument("-f",
                    "--file",
                    help="Write JSON to a specified file.",
                    default="dyknotifier_list.json")
args = parser.parse_args()

class DYKNotifier(object):
    """
    A class implementing the bot.
    """

    def __init__(self):
        self._wiki = Site()
        self._ttdyk = Page(self._wiki, "Template talk:Did you know")
        self._people_to_notify = dict()
        self._dyk_noms = []

    #################
    ##
    ## MAIN FUNCTIONS
    ##
    #################

    def read_dyk_noms(self):
        """
        Sets self._dyk_noms to a list of subpages of T:DYKN nominated for DYK.
        """
        nom = lambda x:x.startswith("Template:Did you know nominations/")
        titles = [x.title() for x in self._ttdyk.templates()]
        self._dyk_noms = filter(nom, titles)
        logging.info("Got " + str(len(self._dyk_noms)) +\
                     " nominations from TT:DYK.")

    def run(self):
        "Runs the task."
        self.read_dyk_noms()
        self.remove_noms_with_wikitext(["Category:Passed DYK nominations",
                                        "Category:Failed DYK nominations",
                                        "Self nominated"])
        self.get_people_to_notify()
        self.prune_list_of_people()

        if len(self._people_to_notify) == 0:
            logging.info("Nobody to notify.")
            return
        self.dump_list_of_people()

    def remove_noms_with_wikitext(self, texts):
        """
        Removes all noms whose wikitext contains any of the given texts
        from the list.
        """
        logging.info("Removing noms containing " +\
              ("any of " if len(texts) != 1 else "") + str(texts))

        def is_wikitext_in_page(page):
            "Checks if text occurs in the given JSON doc representing a page."
            try:
                wikitext = page["revisions"][0]["*"]
                return any(text in wikitext for text in texts)
            except KeyError:
                logging.error("Couldn't find wikitext in " + str(page["title"]))
                return False
        def resolved_handler(page):
            "Removes a page if one of the given texts matches."
            if is_wikitext_in_page(page):
                self._dyk_noms.remove(page["title"])
        self.run_query(self._dyk_noms,
                       {"prop":"revisions", "rvprop":"content"},
                       resolved_handler)
        logging.info("Done removing noms with " +
                     str(texts) + " - " + str(len(self._dyk_noms)) +
                     " noms left.")

    def get_people_to_notify(self):
        """
        Returns a dict of user talkpages to notify about their creations and
        the noms about which they should be notified.
        """
        logging.info("Getting whom to notify for " + str(len(self._dyk_noms)) +\
              " noms...")
        def handler(page):
            try:
                title = page["title"]
                try:
                    wikitext = page["revisions"][0]["*"]
                except KeyError:
                    logging.error("Couldn't find wikitext in " + str(title))
            except KeyError:
                logging.error("Unable to find a page title.")

            self._people_to_notify.update(get_who_to_nominate(wikitext, title))

        self.run_query(self._dyk_noms,
                       {"prop":"revisions", "rvprop":"content"},
                       handler)
        logging.info("Found " + str(len(self._people_to_notify)) +\
              " people to notify.")

    def prune_list_of_people(self):
        "Removes people who shouldn't be notified from the list."
        initial_count = len(self._people_to_notify)

        people_left = lambda: str(len(self._people_to_notify))

        self.prune_empty_entries()
        logging.info(people_left() + " left after removing empty entries.")

        self.prune_by_exclusion_compliance()
        logging.info(people_left() +\
                     " left after removing based on exclusion compliance.")

        self.prune_by_notification()
        logging.info(people_left() + " left after removing people who have" +\
                     " already been notified.")

    def prune_empty_entries(self):
        "Remove people with no username from the list of people."
        ptn = self._people_to_notify
        self._people_to_notify = {a: ptn[a] for a in ptn if a}

    def prune_by_exclusion_compliance(self):
        "Remove people excluding this bot from their talkpages using {{bot}}."
        exclusion_strings = ["{{nobots}}",
                             "{{bots|allow=none}}",
                             "{{bots|deny=all}}",
                             "{{bots|optout=all}}"]
        is_excluded = lambda text: any(x in text for x in exclusion_strings)
        def handler(page):
            try:
                wikitext = page["revisions"][0]["*"]
                user = page["title"][len("User talk:"):]
            except KeyError:
                return
            if is_excluded(wikitext):
                del self._people_to_notify[user]
        titles = ["User talk:" + x for x in self._people_to_notify.keys()]
        query_params = {"prop": "revisions", "rvprop":"content"}
        self.run_query(titles, query_params, handler)

    def prune_by_notification(self):
        "Remove people whose talk pages link to the nom page."
        def handler(page):
            try:
                links = map(lambda x:x["title"], page["links"])
                user = page["title"][len("User talk:"):]
            except KeyError:
                return

            if self._people_to_notify[user] in links:
                del self._people_to_notify[user]
        titles = map(lambda x:"User talk:" + x, self._people_to_notify.keys())
        query_params = {"prop": "links", "pllimit": "500"}
        self.run_query(titles, query_params, handler)

    #################
    ##
    ## IMPORTANT HELPER FUNCTIONS
    ##
    #################

    def run_query(self, titles, params, function):
        """
        Runs a query on the given lists of queries with the given params and
        the given handler.
        """
        list_of_queries = list_to_pipe_separated_query(titles)
        for titles_string in progress.bar(list_of_queries):
            continue_info = {} # {continue key: continue value}
            while True:
                api_request = api.Request(site=self._wiki, action="query")
                api_request["titles"] = titles_string
                api_request.update(continue_info)
                api_request.update(params)

                api_result = api_request.submit()

                for page in api_result["query"]["pages"].values():
                    function(page)

                if not "query-continue" in api_result:
                    break
                else:
                    query_continue = api_result["query-continue"]
                    module_name = query_continue.keys()[0]
                    continue_key = query_continue[module_name].keys()[0]
                    continue_value = query_continue[module_name][continue_key]
                    continue_info = {continue_key: continue_value}

    def get_template_names_from_page(self, page):
        """
        Returns a list of template names in the given page using an API query.
        """
        logging.debug("Parsing out all templates from " + page + "...")
        api_request = api.Request(site=self._wiki, action="parse")
        api_request["page"] = page
        api_request["prop"] = "templates"
        api_result = api_request.submit()
        logging.debug("APIRequest for templates on " + page + " completed.")
        result = api_result["parse"]["templates"]
        n_templates = str(len(result))
        logging.info("Parsed " + n_templates + " templates from " + page + ".")
        return result

    def dump_list_of_people(self):
        "Dumps the list of people to notify to stdout."
        with open(args.file, "w") as jsonfile:
            jsonfile.write(json.dumps(self._people_to_notify) + "\n")
        logging.info("Wrote to \"" + args.file + "\".")

###################
# END CLASS
###################

def get_who_to_nominate(wikitext, title):
    """
    Given the wikitext of a DYK nom and its title, return a dict of user
    talkpages of who to notify and the titles of the noms for which they
    should be notified).
    """
    if "#REDIRECT" in wikitext:
        logging.error(title + " is a redirect.")
        return []

    if "<small>" not in wikitext:
        logging.error("<small> not found in " + title)
        return []

    soup = BeautifulSoup(wikitext)
    small_tags = [unicode(x.string) for x in soup.find_all("small")]
    def is_nom_string(x):
        "Is x the line in a DYK nom reading 'Created by... Nominated by...'?"
        return u"Nominated by" in x
    nom_lines = filter(is_nom_string, small_tags)
    if not len(nom_lines) == 1:
        logging.error(u"Small tags for " + title + u": " + unicode(small_tags))
        return []

    # Every user whose talk page is linked to within the <small> tags
    # is assumed to have contributed. Looking for piped links to user
    # talk pages.
    usernames = usernames_from_text_with_sigs(nom_lines[0])

    # If there aren't any usernames, WTF and exit
    if len(usernames) == 0:
        logging.error("WTF, no usernames for " + title)
        return []

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

def list_to_pipe_separated_query(the_list):
    "Breaks a list up into pipe-separated queries of 50."
    result = []
    for index in xrange(0, len(the_list) - 1, 50):
        sub_result = ""
        for item in the_list[index : index + 50]:
            sub_result += str(item.encode("utf-8")) + "|"
        result.append(sub_result[:-1])
    return result

def main():
    "The main function."
    notifier = DYKNotifier()
    logging.debug("Calling run() from main().")
    notifier.run()

if __name__ == "__main__":
    main()
