import getpass
import json
import re
from wikitools.wiki import Wiki
from wikitools.page import Page
from wikitools import api

class PruneMode():
    RESOLVED = 1,
    SELF_NOM = 2

class DYKNotifier():
    """
    A Wikipedia bot to notify an editor if an article they had created/expanded
    was nominated for DYK by someone else.
    """

    def __init__(self):
        self._wiki = Wiki("http://en.wikipedia.org/w/api.php")
        def attempt_login():
            username = raw_input("Username: ")
            password = getpass.getpass()
            self._wiki.login(username, password)
        attempt_login()
        while not self._wiki.isLoggedIn():
            print "Error logging in. Try again."
            attempt_login()
        print "Successfully logged in as " + self._wiki.username + "."
        self._ttdyk = Page(self._wiki, title="Template talk:Did you know")
        self._dyk_noms = self.get_list_of_dyk_noms_from_ttdyk()

    def get_list_of_dyk_noms_from_ttdyk(self):
        """
        Returns a list of subpages of T:DYKN nominated for DYK.
        """
        dyk_noms = []
        wikitext = self._ttdyk.getWikiText()
        print "Got wikitext from T:TDYK."
        params = {"action":"parse", "page":"Template talk:Did you know",\
                  "prop":"templates"}
        api_request = api.APIRequest(self._wiki, params)
        print "Sending an APIRequest for the templates on T:TDYK..."
        api_result = api_request.query()
        print "APIRequest completed."
        templates = json.loads(json.dumps(api_result))
        for template in templates["parse"]["templates"]:
            if template["*"].startswith("Template:Did you know nominations/"):
                dyk_noms.append(template["*"])
        return dyk_noms

    def run(self):
        """
        Runs the task.
        """
        self.prune_dyk_noms(PruneMode.RESOLVED)
        print "[run()] Pruned resolved noms from the list of DYK noms."
        self.prune_dyk_noms(PruneMode.SELF_NOM)
        print "[run()] Removed self-noms from the list of DYK noms."
        people_to_notify = self.get_people_to_notify()
        print "[run()] Got a list of people to notify."
        self.notify_people(people_to_notify)
        print "[run()] Notified people."

    def prune_dyk_noms(self, prune_mode):
        """
        Prune the list of DYK noms given a function which determines whether
        a given page should be removed.
        """
        print "About to prune a list of " + str(len(self._dyk_noms)) +\
              " DYK noms."
        dyk_noms_strings = list_to_pipe_separated_query(self._dyk_noms)
        eventual_count = (len(self._dyk_noms) // 50) +\
                         (cmp(len(self._dyk_noms), 0))
        count = 1
        removed_count = 0
        should_prune = lambda x:False
        if prune_mode == PruneMode.RESOLVED:
            should_prune = self.should_prune_as_resolved
        elif prune_mode == PruneMode.SELF_NOM:
            should_prune = self.should_prune_as_self_nom
        for dyk_noms_string in dyk_noms_strings:
            params = {"action":"query", "titles":dyk_noms_string}
            # Based on the function, complete the rest of the params
            if prune_mode == PruneMode.RESOLVED:
                # This function uses categories, so querying for categories
                params["prop"] = "categories"
            elif prune_mode == PruneMode.SELF_NOM:
                # This function uses wikitext, so querying for wikitext
                params["prop"] = "revisions"
                params["rvprop"] = "content"
            api_request = api.APIRequest(self._wiki, params)
            api_result = api_request.query()
            print "Processing results from query number " + str(count) +\
                  " out of " + str(eventual_count) + "..."
            for page in api_result["query"]["pages"].values():
                if should_prune(page):
                    self._dyk_noms.remove(page["title"])
                    removed_count += 1
            count += 1
        print "Removed " + str(removed_count) + " noms. " +\
              str(len(self._dyk_noms)) + " left in the list."

    def should_prune_as_resolved(self, page):
        """
        Given a page, should it be pruned from the list of DYK noms
        since it's already been passed or failed?
        """
        if not "categories" in page:
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
        dyk_noms_strings = list_to_pipe_separated_query(self._dyk_noms)
        eventual_count = (len(self._dyk_noms) // 50) +\
                         (cmp(len(self._dyk_noms), 0))
        count = 1
        people_to_notify = dict()
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
                    people_to_notify.update(talkpages)
            count += 1
        print "The dict of user talkpages has " + str(len(people_to_notify))\
              + " members."
        return people_to_notify

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
        # For people who use standard signatures
        usernames = [whodunit[m.end():m.end()+whodunit[m.end():].find("|talk")]\
                     for m in re.finditer(r"User talk:", whodunit)]
        remove_multi_duplicates(usernames)
        #print "For " + title + ", " + str(usernames)
        result = dict()
        for username in usernames:
            result[username] = title
        return (True, result)

    def notify_people(self, people_to_notify):
        for person in people_to_notify:
            nom_name = people_to_notify[person]
            template = "{{subst:User:APersonBot/DYKNotice|" +\
                       nom_name + "}}"
            talkpage = Page(self._wiki, title="User talk:" + person)
            #result = talkpage.edit(appendtext=template)
            print "Notified " + person + " because of " + nom_name + "."

def remove_multi_duplicates(the_list):
    """
    If there's a duplicate item in the_list, remove BOTH occurrences.
    """
    for item in the_list[:]:
        if the_list.count(item) > 1:
            while item in the_list:
                the_list.remove(item)
    return the_list

def pretty_print(query_result):
    """
    What **is** beauty?
    """
    print json.dumps(query_result, indent=4, separators=(",", ": "))

def list_to_pipe_separated_query(the_list):
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
