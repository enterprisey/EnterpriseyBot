"""
A module implementing a bot to notify editors when articles they create or
expand are nominated for DYK by someone else.
"""

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
    print("Unable to find pywikibot. Exiting...")
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
editing_group = parser.add_mutually_exclusive_group()
editing_group.add_argument("-s", "--skip-editing", action="store_true",
                           help="Skip the user notification part.")
editing_group.add_argument("-d", "--dry-run", action="store_true",
                           help="Only say which edits would be made.")
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

        # Initialize list of users to trace.
        self._trace = []
        if cfgparser.has_option("configuration", "trace"):
            if cfgparser.get("configuration", "trace"):
                trace_option = cfgparser.get("configuration", "trace")
                self._trace = trace_option.split("\n")
                print("[__init__] Tracing users: " + ", ".join(self._trace))

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
        print "[read_dyk_noms()] Got " + str(len(all_templates)) +\
              " templates from T:DYKN."
        for template in [x.title(withNamespace=False) for x in all_templates]:
            if template.startswith("Did you know nominations/"):
                self._dyk_noms.append("Template:" + template)
        print "[read_dyk_noms()] Out of those, " + str(len(self._dyk_noms)) +\
              " were nominations."

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
            print("[run()] Nobody to notify.")
            return
        self.dump_list_of_people()
        if not args.skip_editing:
            self.notify_people()
        print "[run()] Notified people."

    def remove_noms_with_wikitext(self, texts):
        """
        Removes all noms whose wikitext contains any of the given texts
        from the list.
        """
        print "[remove_noms_with_wikitext()] Removing noms containing " +\
              ("any of " if len(texts) != 1 else "") + str(texts)
        def is_wikitext_in_page(page):
            "Checks if text occurs in the given JSON doc representing a page."
            try:
                wikitext = page["revisions"][0]["*"]
                return any(text in wikitext for text in texts)
            except KeyError:
                print "ERROR: Couldn't find wikitext in " + str(page["title"])
                return False
        def resolved_handler(page):
            "Removes a page if one of the given texts matches."
            if is_wikitext_in_page(page):
                self._dyk_noms.remove(page["title"])
        dyk_noms_strings = list_to_pipe_separated_query(self._dyk_noms)
        self.run_query(dyk_noms_strings,
                       {"prop":"revisions", "rvprop":"content"},
                       resolved_handler)
        print "[remove_noms_with_wikitext()] Done removing noms with " +\
              str(texts) + " - " + str(len(self._dyk_noms)) + " noms left."

    def get_people_to_notify(self):
        """
        Returns a dict of user talkpages to notify about their creations and
        the noms about which they should be notified.
        """
        print "Getting whom to notify for " + str(len(self._dyk_noms)) +\
              " noms..."
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
            print "Processing results from query number " + str(count) +\
                  " out of " + str(eventual_count) + "..."
            for wikitext, title in [(page["revisions"][0]["*"], page["title"])\
                                    for page in\
                                    api_result["query"]["pages"].values()]:
                success, talkpages = self.get_who_to_nominate(wikitext, title)
                if success:
                    if len(self._trace) > 0:
                        for user in talkpages.keys():
                            if user in self._trace:
                                print("[get_people_to_notify] ENCOUNTERED " +\
                                        user)
                    self._people_to_notify.update(talkpages)
                else:
                    if "#REDIRECT" in wikitext:
                        print "ERROR: " + title + " is a redirect."
                    else:
                        print "ERROR: Unable to find anyone to notify for " +\
                          title + " in wikitext:"
                        try:
                            print wikitext
                        except UnicodeEncodeError:
                            print "Couldn't print " + title + " due to error."
                        print "(end wikitext for " + title + ".)"
            count += 1
        print "[get_people_to_notify()] There are " +\
              str(len(self._people_to_notify)) +\
              " people to notify."

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
                print "ERROR: " + name_of_person + " not found in the " +\
                      "list of people to notify."
                return
            name_of_nom = self._people_to_notify[name_of_person]

            if is_excluded_given_wikitext(wikitext) or\
               self._is_already_notified(wikitext,\
                                         name_from_title(name_of_nom),\
                                         name_of_person):
                if name_of_person in self._trace:
                    print("[prune_list_of_people()] Removed ", name_of_person)
                del self._people_to_notify[name_of_person]

        # Actually run the query
        titles_string = list_to_pipe_separated_query([\
            "User talk:" + x for x in self._people_to_notify.keys()])
        print "[prune_list_of_people()] Running query..."
        self.run_query(titles_string, {"prop":"revisions", "rvprop":"content"},\
                       handler)
        print "[prune_list_of_people()] Removed " +\
              str(initial_count - len(self._people_to_notify)) +\
              " people. " + str(len(self._people_to_notify)) + " people left."

    def notify_people(self):
        """
        Substitutes User:APersonBot/DYKNotice at the end of each page in a list
        of user talkpages, given a list of usernames.
        """
        people_notified_count = 0
        for person in self._people_to_notify:
            nom_name = self._people_to_notify[person]
            template = "\n\n{{subst:DYKNom|" +\
                       name_from_title(nom_name) + "|passive=yes}}"
            print "ABOUT TO NOTIFY " + str(person) + " BECAUSE OF " +\
                  nom_name + "..."
            if robust_input("Continue (y/n)? ") == "n":
                print "Breaking..."
                return
            talkpage = Page(self._wiki, title="User talk:" + person, ns=3)
            if args.dry_run:
                talkpage.text = talkpage.text + template
                print "[notify_people()] Saving User talk:" + person + "..."
                summary = "Robot notifying user about DYK nomination."
                print "[notify_people()] Summary is \"" + summary + "\""
                talkpage.save(comment=summary)
                print "Saved."
                people_notified_count += 1
                print str(people_notified_count) + " have been notified so far."
            print "Notified " + person + " because of " + nom_name + "."

    #################
    ##
    ## IMPORTANT HELPER FUNCTIONS
    ##
    #################

    def get_who_to_nominate(self, wikitext, title):
        """
        Given the wikitext of a DYK nom and its title, return a tuple of (
        success, a dict of user talkpages of who to notify and the titles
        of the noms for which they should be notified).
        """
        if "<small>" not in wikitext:
            return (False, [])
        index = wikitext.find("<small>")
        index_end = wikitext[index:].find("</small>")
        whodunit = wikitext[index:index_end + index]

        # Every user whose talk page is linked to within the <small> tags
        # is assumed to have contributed. Looking for piped links to user
        # talk pages.
        usernames = [whodunit[m.end():m.end()+whodunit[m.end():].find("|")]\
                     for m in re.finditer(r"User talk:", whodunit)]

        # If any username getting traced is in here, print the entire list.
        if len(self._trace) > 0:
            for user in usernames:
                if(user in self._trace):
                    print("[get_who_to_nominate] ENCOUNTERED " + user +\
                            " in list for " + title)
                    if args.verbosity < 1:
                        print("[get_who_to_nominate] User list: " +\
                              str(usernames))
                    break

        # If there aren't any usernames, WTF and exit
        if len(usernames) == 0:
            print("[get_who_to_nominate] WTF, no usernames for " + title)
            return (False, [])

        # The last one is the nominator.
        nominator = usernames[-1]

        # Removing all instances of nominator from usernames, since he or she
        # already knows about the nomination
        dupe = False
        printing_dupe_messages = False # args.verbosity >= 2
        if printing_dupe_messages and usernames.count(nominator) != 1:
            print("[get_who_to_nominate] Found a dupe: " +\
            	  str(nominator))
            dupe = True
            print("[get_who_to_nominate] Before the dupe, " +\
            	    "dict was " + str(usernames))
        while nominator in usernames:
            usernames.remove(nominator)
        if printing_dupe_messages and dupe:
            print("[get_who_to_nominate] After the dupe, " +\
            	    "dict was " + str(usernames))
        result = dict()
        for username in usernames:
            result[username] = title

        if args.verbosity >= 2:
            print "[get_who_to_nominate] For " + title + ": " + str(result)
        return (True, result)

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
            print "[run_query()] Processing results from query number " +\
                  str(count) + " out of " + str(len(list_of_queries)) + "..."
            for page in api_result["query"]["pages"].values():
                function(page)
            count += 1

    def get_template_names_from_page(self, page):
        """
        Returns a list of template names in the given page using an API query.
        """
        print "Parsing out all templates from " + page + "..."
        api_request = api.Request(site=self._wiki, action="parse")
        api_request["page"] = page
        api_request["prop"] = "templates"
        api_result = api_request.submit()
        print "APIRequest for templates on " + page + " completed."
        result = api_result["parse"]["templates"]
        print "Parsed " + str(len(result)) + " templates from " + page + "."
        return result

    def _is_already_notified(self, wikitext, nom, user, recursion_level=0):
        """"
        Return true if there is already a notification or a {{DYKProblem}} in
        the given wikitext for the given nomination.
        """
        if not "<!-- Template:DYKNom -->" in wikitext:
            return False
        if not " has been nominated for Did You Know" in wikitext:
            print "Found the comment for T:DYKNom but no section header!"
            return False

        # Check for too much recursion
        if recursion_level > 10:
            return False

        # Parse the section header to find the nom it's talking about
        index_end = wikitext.find(" has been nominated for Did You Know")
        index_begin = wikitext[:index_end].rfind("==")
        index_begin += 2 # to get past the == part
        wikitext_nom = wikitext[index_begin:index_end]

        # In an early version of Template:DYKNom, the article name was in a link
        wikitext_nom = wikitext_nom.replace("[", "").replace("]", "")
        if wikitext_nom == nom:
            print("[_is_already_notified] Already notified " + user + " for " +\
                  nom)
            return True
        if wikitext.count("<!-- Template:DYKNom -->") +\
           wikitext.count("<!--Template:DYKProblem-->") > 1:

            # If we didn't find it, there might be another notification template
            # in the rest of the wikitext, so let's check with a recursive call.
            return self._is_already_notified(wikitext[wikitext.find(\
                "<!-- Template:DYKNom -->"):], nom, recursion_level + 1)
        else:
            return False

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
    """
    Breaks a list up into pipe-separated queries of 50.
    """
    result = []
    for index in xrange(0, len(the_list) - 1, 50):
        sub_result = ""
        for item in the_list[index : index + 50]:
            sub_result += str(item.encode("utf-8")) + "|"
        result.append(sub_result[:-1])
    return result

def robust_input(query, acceptable_values=None):
    "Query the user in a robust fashion."
    if not acceptable_values:
        acceptable_values = ("y", "n")
    error_message = "Please enter one of " +\
            ", ".join([str("\"" + x + "\"") for x in acceptable_values]) + "."
    while True:
        user_input = raw_input(query)
        if (not user_input) or user_input not in acceptable_values:
            print(error_message)
        else:
            return user_input

def name_from_title(title):
    "Get the name of the nomination from the title of the nom subpage."
    return title[34:]

def main():
    "The main function."
    print "[main()] Constructing DYKNotifier..."
    notifier = DYKNotifier()
    print "[main()] Constructed a DYKNotifier."
    notifier.run()
    print "[main()] Exiting main()"

if __name__ == "__main__":
    main()
