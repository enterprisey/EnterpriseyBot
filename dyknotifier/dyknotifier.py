import getpass
import json
import re
from wikitools.wiki import Wiki
from wikitools.page import Page
from wikitools import api

class DYKNotifier():
    """
    A Wikipedia bot to notify an editor if an article they had created/expanded
    was nominated for DYK by someone else.
    """

    def __init__(self):
        self._wiki = Wiki("http://en.wikipedia.org/w/api.php")
        self._ttdyk = Page(self._wiki, title="Template talk:Did you know")
        self._dyk_noms = self.get_list_of_dyk_noms_from_ttdyk()
        self._people_to_notify = dict()

        # CONFIGURATION
        self.actually_editing = raw_input("Actually edit (y/n)? ") == "y"
        self._summary = "[[Wikipedia:Bots/Requests for approval/APersonBot " +\
                        "2|Robot]] notification about the DYK nomination of" +\
                        " %(nom_name)s."

        # LOGIN
        def attempt_login():
            username = raw_input("Username: ")
            password = getpass.getpass()
            self._wiki.login(username, password)
        if self.actually_editing:
            attempt_login()
            while not self._wiki.isLoggedIn():
                print "Error logging in. Try again."
                attempt_login()
            print "Successfully logged in as " + self._wiki.username + "."
        else:
            print "Won't be editing, so no need to log in."

    #################
    ##
    ## MAIN FUNCTIONS
    ##
    #################

    def get_list_of_dyk_noms_from_ttdyk(self):
        """
        Returns a list of subpages of T:DYKN nominated for DYK.
        """
        dyk_noms = []
        all_templates = self._ttdyk.getTemplates()
        print "Got all " + str(len(all_templates)) + " templates from T:DYKN."
        for template in all_templates:
            if template.startswith("Template:Did you know nominations/"):
                dyk_noms.append(template)
        print "Read " + str(len(dyk_noms)) + " noms from T:DYKN."
        return dyk_noms

    def run(self):
        """
        Runs the task.
        """
        self.remove_resolved_noms()
        self.remove_self_nominated_noms()
        self.get_people_to_notify()
        self.prune_list_of_people()
        self.notify_people()
        print "[run()] Notified people."

    def remove_resolved_noms(self):
        """
        Removes all resolved noms from the list of DYK noms.
        """
        def resolved_handler(page):
            if self.should_prune_as_resolved(page):
                self._dyk_noms.remove(page["title"])
        dyk_noms_strings = self.list_to_pipe_separated_query(self._dyk_noms)
        self.run_query(dyk_noms_strings, {"prop":"categories"},
                       resolved_handler)
        print "[remove_resolved_noms()] Done. " + str(len(self._dyk_noms)) +\
              " noms left."

    def remove_self_nominated_noms(self):
        """
        Removes all resolved noms from the list of DYK noms.
        """
        def resolved_handler(page):
            if self.should_prune_as_self_nom(page):
                self._dyk_noms.remove(page["title"])
        dyk_noms_strings = self.list_to_pipe_separated_query(self._dyk_noms)
        self.run_query(dyk_noms_strings,
                       {"prop":"revisions", "rvprop":"content"},
                       resolved_handler)
        print "[remove_self_nominated_noms()] Done. " +\
              str(len(self._dyk_noms)) + " noms left."

    def should_prune_as_resolved(self, page):
        """
        Given a page, should it be pruned from the list of DYK noms
        since it's already been passed or failed?
        """
        try:
            test = page["categories"]
        except KeyError:
            return False
        for category in page["categories"]:
            if "Category:Passed DYK nominations" in category["title"] or\
               "Category:Failed DYK nominations" in category["title"]:
                return True
        return False

    def should_prune_as_self_nom(self, page):
        wikitext = ""
        try:
            wikitext = page["revisions"][0]["*"]
        except KeyError:
            return False
        return "Self nominated" in wikitext          
                
    def get_people_to_notify(self):
        """
        Returns a dict of user talkpages to notify about their creations and
        the noms about which they should be notified.
        """
        print "Getting whom to notify for " + str(len(self._dyk_noms)) +\
              " noms..."
        dyk_noms_strings = self.list_to_pipe_separated_query(self._dyk_noms)
        eventual_count = (len(self._dyk_noms) // 50) +\
                         (cmp(len(self._dyk_noms), 0))
        count = 1
        for dyk_noms_string in dyk_noms_strings:
            params = {"action":"query", "titles":dyk_noms_string,\
                      "prop":"revisions", "rvprop":"content"}
            api_request = api.APIRequest(self._wiki, params)
            api_result = api_request.query()
            print "Processing results from query number " + str(count) +\
                  " out of " + str(eventual_count) + "..."
            for wikitext, title in [(page["revisions"][0]["*"], page["title"])\
                                    for page in\
                                    api_result["query"]["pages"].values()]:
                success, talkpages = self._get_who_to_nominate_from_wikitext(\
                    wikitext, title)
                if success:
                    self._people_to_notify.update(talkpages)
            count += 1
        print "There are " + str(len(self._people_to_notify)) +\
              " people to notify."

    def prune_list_of_people(self):
        """
        Removes three types of people who shouldn't be notified from the list:
        people with blank usernames or nomination names; people with {{bots}}
        indicating that they shouldn't be notified by this bot; and people
        who have already been notified about the specific nomination (i.e. not
        people who've already been notified about a different nomination)
        """
        initial_count = len(self._people_to_notify)
        # Remove entries with empty keys
        self._people_to_notify = dict([(x, y) for x, y in\
                                       self._people_to_notify.iteritems() if x])
        
        # Remove people using {{bots}} to exclude this bot AND already-notified
        # people in one go, since both use wikitext.
        def handler(page):
            wikitext, title = "", ""
            try:
                wikitext, title = page["revisions"][0]["*"], page["title"]
            except KeyError:
                return
            if self._is_excluded_given_wikitext(wikitext) or\
               self._is_already_notified(wikitext,\
                                         self._people_to_notify[title[len(\
                                             "User talk:"):]][34:]):
                del self._people_to_notify[title[len("User talk:"):]]
        titles_string = self.list_to_pipe_separated_query(\
            ["User talk:" + x for x in self._people_to_notify.keys()])
        self.run_query(titles_string, {"prop":"revisions", "rvprop":"content"},\
                       handler)
        print "Removed " + str(initial_count - len(self._people_to_notify)) +\
              " people. " + str(len(self._people_to_notify)) + " people left."

    def notify_people(self):
        """
        Substitutes User:APersonBot/DYKNotice at the end of each page in a list
        of user talkpages, given a list of usernames.
        """
        for person in self._people_to_notify:
            nom_name = self._people_to_notify[person]
            template = "\n\n{{subst:DYKNom|" +\
                       nom_name[34:] + "|passive=yes}}"
            print "ABOUT TO NOTIFY " + str(person) + " BECAUSE OF " +\
                  nom_name + "..."
            talkpage = Page(self._wiki, title="User talk:" + person)
            if self.actually_editing:
                # cross fingers here
                result = talkpage.edit(appendtext=template, bot=True,\
                                       summary=self._summary %\
                                       {"nom_name":nom_name.encode(\
                                           "ascii", "ignore")})
                print "Result: " + str(result)
            print "Notified " + person + " because of " + nom_name + "."
            if raw_input("Continue (y/n)? ") == "n":
                print "Breaking..."
                return

    #################
    ##
    ## IMPORTANT HELPER FUNCTIONS
    ##
    #################

    def _get_who_to_nominate_from_wikitext(self, wikitext, title):
        """
        Given the wikitext of a DYK nom and its title, return a tuple of (
        success, a dict of user talkpages of who to notify and the titles
        of the noms for which they should be notified).
        """
        if "<small>" not in wikitext: return (False, [])
        index = wikitext.find("<small>")
        index_end = wikitext[index:].find("</small>")
        whodunit = wikitext[index:index_end + index]
        # Every user whose talk page is linked to within the <small> tags
        # is assumed to have contributed, except...
        usernames = [whodunit[m.end():m.end()+whodunit[m.end():].find("|talk")]\
                     for m in re.finditer(r"User talk:", whodunit)]
        result = dict()
        # ...the last one, since that's is the nominator
        nominator = usernames[:-1]
        # Removing all instances of nominator from usernames, since he or she
        # already knows about the nomination
        while nominator in usernames:
            usernames.remove(nominator)
        for username in usernames[:-1]:
            result[username] = title
        return (True, result)

    def run_query(self, list_of_queries, params, function):
        count = 1 # The current query number.
        for titles_string in list_of_queries:
            localized_params = {"action":"query", "titles":titles_string}
            localized_params.update(params)
            api_request = api.APIRequest(self._wiki, localized_params)
            api_result = api_request.query()
            print "Processing results from query number " + str(count) +\
                  " out of " + str(len(list_of_queries)) + "..."
            for page in api_result["query"]["pages"].values():
                function(page)
            count += 1

    def get_template_names_from_page(self, page):
        """
        Returns a list of template names in the given page using an API query.
        """
        print "Parsing out all templates from " + page + "..."
        params = {"action":"parse", "page":page, "prop":"templates"}
        api_request = api.APIRequest(self._wiki, params)
        api_result = api_request.query()
        print "APIRequest for templates on " + page + " completed."
        result = api_result["parse"]["templates"]
        print "Parsed " + str(len(result)) + " templates from " + page + "."
        print self.pretty_print(result)
        return result

    def _is_excluded_given_wikitext(self, wikitext):
        """
        Return whether {{bots}} is used in the wikitext to exclude
        this bot.
        """
        if not "bots" in wikitext:
            return False
        strings_that_mean_excluded = ["{{nobots}}", "{{bots|allow=none}}",\
                                      "{{bots|deny=all}}",\
                                      "{{bots|optout=all}}"]
        if any([x in wikitext for x in strings_that_mean_excluded]):
            return True
        return False

    def _is_already_notified(self, wikitext, nom):
        """"
        Return true if there is already a notification or a {{DYKProblem}} in
        the given wikitext for the given nomination.
        """
        if not "<!-- Template:DYKNom -->" in wikitext:
            return False
        if not " has been nominated for Did You Know" in wikitext:
            print "Found the comment for T:DYKNom but no section header!"
            return False
        index_end = wikitext.find(" has been nominated for Did You Know")
        index_begin = wikitext[:index_end].rfind("==")
        index_begin += 2 # to get past the == part
        wikitext_nom = wikitext[index_begin:index_end]
        # In an early version of Template:DYKNom, the article name was in a link
        wikitext_nom = wikitext_nom.replace("[", "").replace("]", "")
        if wikitext_nom == nom:
            return True
        if wikitext.count("<!-- Template:DYKNom -->") > 1:
            # If we didn't find it, there might be another notification template
            # in the rest of the wikitext, so let's check with a recursive call.
            return self._is_already_notified(wikitext[wikitext.find(\
                "<!-- Template:DYKNom -->"):], nom)
        else:
            return False

    #################
    ##
    ## GENERIC HELPER FUNCTIONS
    ##
    #################

    def remove_multi_duplicates(self, the_list):
        """
        If there's a duplicate item in the_list, remove BOTH occurrences.
        """
        for item in the_list[:]:
            if the_list.count(item) > 1:
                while item in the_list:
                    the_list.remove(item)
        return the_list

    def pretty_print(self, query_result):
        """
        What **is** beauty?
        """
        print json.dumps(query_result, indent=4, separators=(",", ": "))

    def list_to_pipe_separated_query(self, the_list):
        """
        Breaks a list up into pipe-separated queries of 50.
        """
        result = []
        for index in xrange(0, len(the_list) - 1, 50):
            sub_result = ""
            for item in [x.encode("utf-8") for x in the_list[index : index + 50]]:
                sub_result += str(item) + "|"
            result.append(sub_result[:-1])
        return result

def main():
    print "[main()] Before DYKNotifier constructor"
    notifier = DYKNotifier()
    print "[main()] Constructed a DYKNotifier."
    notifier.run()
    print "[main()] Exiting main()"

if __name__ == "__main__":
    main()
