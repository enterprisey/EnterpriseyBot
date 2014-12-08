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

# Parse our args. Arrrrrrrghs.
parser = argparse.ArgumentParser(prog="DYKNotifier",
                                 description=\
                                 "Notify editors of their DYK noms.")
verbosity_group = parser.add_mutually_exclusive_group()
verbosity_group.add_argument("-v", "--verbosity", action="count",
                             help="Increases verbosity.")
verbosity_group.add_argument("-o", "--dump-only", action="store_true",
                             help="Only print JSON dump.")
args = parser.parse_args()

# Die, STDOUT! (If the user wants)
if args.dump_only or args.verbosity == 0:
    black_market_stdout = sys.stdout
    memory_hole = open(os.devnull, "w")
    sys.stdout = memory_hole
else:
    black_market_stdout = None

class DYKNotifier(object):
    """
    A class implementing the bot.
    """

    def __init__(self):
        self._wiki = Site()
        self._ttdyk = Page(self._wiki, "Template talk:Did you know")
        self._people_to_notify = dict()
        self._dyk_noms = []

        # CONFIGURATION
        self._summary = "[[Wikipedia:Bots/Requests for approval/APersonBot " +\
                        "2|Robot]] notification about the DYK nomination of" +\
                        " %(nom_name)s."

    #################
    ##
    ## MAIN FUNCTIONS
    ##
    #################

    def read_dyk_noms(self):
        """
        Sets self._dyk_noms to a list of subpages of T:DYKN nominated for DYK.
        """
        self._dyk_noms = []
        all_templates = self._ttdyk.templates()
        logging.info("Got " + str(len(all_templates)) +\
                     " templates from T:DYKN.")
        for template in [x.title(withNamespace=False) for x in all_templates]:
            if template.startswith("Did you know nominations/"):
                self._dyk_noms.append("Template:" + template)
        logging.info("Out of those, " + str(len(self._dyk_noms)) +\
              " were nominations.")

    def run(self):
        """
        Runs the task.
        """
        self.read_dyk_noms()
        self.remove_noms_with_wikitext(["Category:Passed DYK nominations",\
                                        "Category:Failed DYK nominations"])
        self.remove_noms_with_wikitext(["Self nominated"])
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
        dyk_noms_strings = list_to_pipe_separated_query(self._dyk_noms)
        self.run_query(dyk_noms_strings,
                       {"prop":"revisions", "rvprop":"content"},
                       resolved_handler)
        logging.info("Done removing noms with " +\
              str(texts) + " - " + str(len(self._dyk_noms)) + " noms left.")

    def get_people_to_notify(self):
        """
        Returns a dict of user talkpages to notify about their creations and
        the noms about which they should be notified.
        """
        logging.info("Getting whom to notify for " + str(len(self._dyk_noms)) +\
              " noms...")
        dyk_noms_strings = list_to_pipe_separated_query(self._dyk_noms)
        eventual_count = (len(self._dyk_noms) // 50) +\
                         (cmp(len(self._dyk_noms), 0))
        count = 1
        for dyk_noms_string in dyk_noms_strings:
            params = {"titles":dyk_noms_string,\
                      "prop":"revisions", "rvprop":"content"}
            api_request = api.Request(site=self._wiki, action="query")
            for key in params.keys():
                api_request[key] = params[key]
            api_result = api_request.submit()
            logging.info("Processing results from query number " + str(count) +\
                  " out of " + str(eventual_count) + "...")
            for wikitext, title in [(page["revisions"][0]["*"], page["title"])\
                                    for page in\
                                    api_result["query"]["pages"].values()]:
                success, talkpages = get_who_to_nominate(wikitext, title)
                if success:
                    self._people_to_notify.update(talkpages)
                else:
                    if "#REDIRECT" in wikitext:
                        logging.error(title + " is a redirect.")
                    else:
                        logging.error("Unable to find anyone to notify for " +\
                          title + " in wikitext.")
                        try:
                            logging.debug("Wikitext for " + title + ": " +\
                                          wikitext)
                        except UnicodeEncodeError:
                            logging.error("Couldn't print " + title +\
                                          " due to error.")
            count += 1
        logging.info("There are " + str(len(self._people_to_notify)) +\
              " people to notify before pruning.")

    def prune_list_of_people(self):
        """
        Removes four types of people who shouldn't be notified from the list:
         - people with blank usernames or nomination names
         - people with {{bots}} indicating that they shouldn't be notified by
           this bot
         - people who have already been notified about the specific nomination
           by the bot (i.e. not people who've already been notified about a
           different nomination)
         - people who have been told about the nomination by other means
           (e.g. through {{DYKProblem}})
        """
        initial_count = len(self._people_to_notify)

        # Remove entries with empty keys
        self._people_to_notify = dict([(x, y) for x, y in\
                                       self._people_to_notify.iteritems() if x])
        def handler(page):
            """
            Remove people using {{bots}} to exclude this bot AND
            already-notified people in one go, since both use wikitext.
            """
            wikitext, title = "", ""
            try:
                wikitext, title = page["revisions"][0]["*"], page["title"]
            except KeyError:
                return
            name_of_person = title[len("User talk:"):]

            # Sanity check
            if not name_of_person in self._people_to_notify.keys():
                logging.error(name_of_person + " not found in the " +\
                      "list of people to notify.")
                return
            name_of_nom = self._people_to_notify[name_of_person]

            if is_excluded_given_wikitext(wikitext) or\
               is_already_notified(wikitext,\
                                   name_from_title(name_of_nom),\
                                   name_of_person):
                del self._people_to_notify[name_of_person]

        # Actually run the query
        titles_string = list_to_pipe_separated_query([\
            "User talk:" + x for x in self._people_to_notify.keys()])
        logging.info("Running query to remove people...")
        self.run_query(titles_string, {"prop":"revisions", "rvprop":"content"},\
                       handler)
        logging.info("Removed " +\
              str(initial_count - len(self._people_to_notify)) +\
              " people. " + str(len(self._people_to_notify)) + " people left.")

    #################
    ##
    ## IMPORTANT HELPER FUNCTIONS
    ##
    #################

    def run_query(self, list_of_queries, params, function):
        """
    	Runs a query on the given lists of queries with the given params and
    	the given handler.
    	"""
        count = 1
        for titles_string in list_of_queries:
            api_request = api.Request(site=self._wiki, action="query")
            api_request["titles"] = titles_string
            for key in params.keys():
                api_request[key] = params[key]
            api_result = api_request.submit()
            logging.info("Processing results from query number " +\
                  str(count) + " out of " + str(len(list_of_queries)) + "...")
            for page in api_result["query"]["pages"].values():
                function(page)
            count += 1

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
        logging.info("Parsed " + str(len(result)) + " templates from " +\
                     page + ".")
        return result

    def dump_list_of_people(self):
        "Dumps the list of people to notify to stdout."
        dump_text = json.dumps(self._people_to_notify)
        if black_market_stdout:
            black_market_stdout.write(dump_text)
            black_market_stdout.write("\n")
        else:
            print "JSON DUMP OF PEOPLE TO NOTIFY"
            print "-----------------------------"
            print dump_text
            print "-----------------------------"
            print "END JSON DUMP"

###################
# END CLASS
###################

def get_who_to_nominate(wikitext, title):
    """
    Given the wikitext of a DYK nom and its title, return a tuple of (
    success, a dict of user talkpages of who to notify and the titles
    of the noms for which they should be notified).
    """
    if "<small>" not in wikitext:
        return (False, [])

    whodunit = re.search("<small>(.*)</small>", wikitext).group(1)

    # Every user whose talk page is linked to within the <small> tags
    # is assumed to have contributed. Looking for piped links to user
    # talk pages.
    usernames = usernames_from_text_with_sigs(whodunit)

    # If there aren't any usernames, WTF and exit
    if len(usernames) == 0:
        logging.error("WTF, no usernames for " + title)
        return (False, [])

    # The last one is the nominator.
    nominator = usernames[-1]

    # Removing all instances of nominator from usernames, since he or she
    # already knows about the nomination
    while nominator in usernames:
        usernames.remove(nominator)

    result = dict()
    for username in usernames:
        result[username] = title

    return (True, result)

def is_already_notified(wikitext, nom, user, recursion_level=0):
    """"
    Return true if there is already a notification or a {{DYKProblem}} in
    the given user talk page wikitext for the given nomination.
    """
    if not "<!-- Template:DYKNom -->" in wikitext:
        return False

    if not " has been nominated for Did You Know" in wikitext:
        logging.error("Found the comment for T:DYKNom but no section header!")
        return False

    # Check for too much recursion
    if recursion_level > 10:
        return False

    # Parse the section header to find the nom it's talking about
    header_regex = r"==(.*)has been nominated for Did You Know"
    wikitext_nom = re.search(header_regex, wikitext).group(1)

    # In an early version of Template:DYKNom, the article name was in a link
    wikitext_nom = wikitext_nom.replace("[", "").replace("]", "")
    if wikitext_nom == nom:
        logging.warning("Already notified " + str(user) +\
              " for " + str(nom))
        return True

    if wikitext.count("<!-- Template:DYKNom -->") +\
       wikitext.count("<!--Template:DYKProblem-->") > 1:

        # If we didn't find it, there might be another notification template
        # in the rest of the wikitext, so let's check with a recursive call.
        the_rest = wikitext[wikitext.find("<!-- Template:DYKNom -->"):]
        return is_already_notified(the_rest, nom, recursion_level + 1)
    else:
        return False

def usernames_from_text_with_sigs(wikitext):
    "Returns the users whose talk pages are linked to in the wikitext."
    return [wikitext[m.end():m.end()+wikitext[m.end():].find("|")]\
            for m in re.finditer(r"User talk:", wikitext)]

def is_excluded_given_wikitext(wikitext):
    """
    Return whether {{bots}} is used in the wikitext to exclude
    this bot.
    """
    if not "bots" in wikitext:
        return False
    strings_that_mean_excluded = ["{{nobots}}", "{{bots|allow=none}}",\
                                  "{{bots|deny=all}}",\
                                  "{{bots|optout=all}}"]
    if any(x in wikitext for x in strings_that_mean_excluded):
        return True
    return False

def list_to_pipe_separated_query(the_list):
    "Breaks a list up into pipe-separated queries of 50."
    result = []
    for index in xrange(0, len(the_list) - 1, 50):
        sub_result = ""
        for item in the_list[index : index + 50]:
            sub_result += str(item.encode("utf-8")) + "|"
        result.append(sub_result[:-1])
    return result

def name_from_title(title):
    "Get the name of the nomination from the title of the nom subpage."
    return title[34:]

def main():
    "The main function."
    notifier = DYKNotifier()
    logging.debug("Calling run() from main().")
    notifier.run()

if __name__ == "__main__":
    main()
