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

    def prune_resolved_dyk_noms(self, dyk_noms):
        print "About to prune a list of " + str(len(dyk_noms)) + " DYK noms."
        dyk_noms_strings = list_to_pipe_separated_query(dyk_noms)
        eventual_count = (len(dyk_noms) // 50) + (cmp(len(dyk_noms), 0))
        count = 1
        removed_count = 0
        for dyk_noms_string in dyk_noms_strings:
            params = {"action":"query", "titles":dyk_noms_string, "prop":\
                      "categories"}
            api_request = api.APIRequest(self._wiki, params)
            api_result = api_request.query()
            print "Processing results from query number " + str(count) +\
                  " out of " + str(eventual_count) + "..."
            for page in api_result["query"]["pages"].values():
                if not "categories" in page:
                    continue
                for category in page["categories"]:
                    if "Category:Passed DYK nominations" in category["title"]\
                       or "Category:Failed DYK nominations" in\
                       category["title"]:
                        # Since it's already been passed or failed,
                        # let's not notify the creator
                        dyk_noms.remove(page["title"])
                        removed_count += 1
            count += 1
        print "Removed " + str(removed_count) + " noms because they passed" +\
              " or failed. " + str(len(dyk_noms)) + " left in the list."
        return dyk_noms

    def remove_self_noms(self, dyk_noms):
        print "Removing self-nominations from the list of DYK noms."
        removed_count = 0
        for dyk_nom_title in dyk_noms[:]:
            print "Checking " + dyk_nom_title + "..."
            dyk_nom = Page(self._wiki, title=dyk_nom_title)
            nom_wikitext = dyk_nom.getWikiText()
            self_nom = re.search("Self nominated at ", nom_wikitext)
            if self_nom:
                dyk_noms.remove(dyk_nom_title)
                removed_count += 1
        print "Removed " + str(removed_count) + " noms because self-nom. " +\
              str(len(dyk_noms)) + " left in the list."
        return dyk_noms
            
                
    def get_people_to_notify(self, dyk_noms):
        people_to_notify = []
        for dyk_nom_title in dyk_noms:
            print "Getting who to notify for " + dyk_nom_title + "..."
            dyk_nom = Page(self._wiki, title=dyk_nom_title)
            nom_wikitext = dyk_nom.getWikiText()
            line_matchobj = re.search(r"<small>\S*", wikitext)
            line_begin = nom_wikitext.find("<small>Created by ")
            line_end = nom_wikitext[line_begin:].find(\
                "</small>.")
            line_begin += len("<small>")
            line_end += line_begin - 7 # To take out "</small>."
            print nom_wikitext[line_begin:line_end]
        return people_to_notify

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
    dyk_noms = notifier.get_list_of_dyk_noms_from_ttdyk()
    print "[main()] Got a list of DYK noms from T:TDYK."
    dyk_noms = notifier.prune_resolved_dyk_noms(dyk_noms)
    print "[main()] Pruned resolved noms from the list of DYK noms."
    dyk_noms = notifier.remove_self_noms(dyk_noms)
    print "[main()] Removed self-noms from the list of DYK noms."
    #people_to_notify = notifier.get_people_to_notify(dyk_noms)
    #print "[main()] Got a list of people to notify."
    #print people_to_notify
    print "[main()] Exiting main()"

if __name__ == "__main__":
    main()
