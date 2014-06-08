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

    def prune_dyk_noms(self, prune_mode):
        """
        Prune the list of DYK noms given a function which determines whether
        a given page should be removed.
        """
        print "About to prune a list of " + str(len(self._dyk_noms)) + " DYK noms."
        dyk_noms_strings = list_to_pipe_separated_query(self._dyk_noms)
        eventual_count = (len(self._dyk_noms) // 50) + (cmp(len(self._dyk_noms), 0))
        count = 1
        removed_count = 0
        should_prune = lambda x:False
        if prune_mode == PruneMode.RESOLVED:
            should_prune = self.should_prune_as_resolved
        elif prune_mode == PruneMode.SELF_NOM:
            should_prune = self.should_prune_as_self_nom
        for dyk_noms_string in dyk_noms_strings:
            params = {"action":"query", "titles":dyk_noms_string}
            # Based on how the function is pruning, complete the rest of the params
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
        Returns a list of user talkpages to notify about their creations.
        """
        print "Getting whom to notify for" + str(len(self._dyk_noms)) +\
              " noms..."
        people_to_notify = []
        dyk_noms_strings = list_to_pipe_separated_query(self._dyk_noms)
        eventual_count = (len(self._dyk_noms) // 50) + (cmp(len(self._dyk_noms), 0))
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
                success, talkpage = self._get_who_to_nominate_from_wikitext(\
                    wikitext, title)
                if success:
                    people_to_notify.append(talkpage)
            count += 1
        print "The list of user talkpages has " + len(people_to_notify) + " members."
        return people_to_notify

    def _get_who_to_nominate_from_wikitext(self, wikitext, title):
        """
        Given the wikitext of a DYK nom and its title, return a tuple of (
        success, the user talkpage of whom to notify).
        """
        # So, there's always a template called DYKnom, called like
        # {{DYKnom|<title of nom>|<who to notify>}}
        # so let's just scrape it from there.
        length_of_prefix = len("{{DYKnom|" + title + "|")
        index = wikitext.find("{{DYKnom|" + title + "|")
        index += length_of_prefix
        print wikitext[index:index + wikitext[index:].find("}}")]
        return (False, "")

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
    notifier.prune_dyk_noms(PruneMode.RESOLVED)
    print "[main()] Pruned resolved noms from the list of DYK noms."
    notifier.prune_dyk_noms(PruneMode.SELF_NOM)
    print "[main()] Removed self-noms from the list of DYK noms."
    people_to_notify = notifier.get_people_to_notify()
    print "[main()] Got a list of people to notify."
    print people_to_notify
    print "[main()] Exiting main()"

if __name__ == "__main__":
    main()
