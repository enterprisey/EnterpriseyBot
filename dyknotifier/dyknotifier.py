import json
import sys
from wikitools.wiki import Wiki
from wikitools.page import Page
from wikitools.user import User
from wikitools import api
import mwparserfromhell as Parser

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
        Returns a list of subpages of T:DYK nominated for DYK.
        """
        dyk_noms = []
        wikitext = self._ttdyk.getWikiText()
        print "Got wikitext from TT:DYK."
        params = {"action":"parse", "page":"Template talk:Did you know", "prop":"templates"}
        api_request = api.APIRequest(self._wiki, params)
        print "Sending an APIRequest for the templates on TT:DYK..."
        api_result = api_request.query()
        print "APIRequest completed."
        templates = json.loads(json.dumps(api_result))
        for template in templates["parse"]["templates"]:
            if template["*"].startswith("Template:Did you know nominations/"):
                dyk_noms.append(template["*"][34:])
        return dyk_noms

    def get_people_to_notify(self, dyk_noms):
        people_to_notify = []
        return people_to_notify

def main():
    print "Before DYKNotifier constructor"
    notifier = DYKNotifier()
    print "Constructed a DYKNotifier."
    dyk_noms = notifier.get_list_of_dyk_noms_from_ttdyk()
    print "Got a list of DYK noms from TT:DYK."
    print dyk_noms
    people_to_notify = notifier.get_people_to_notify(dyk_noms)
    print "Got a list of people to notify."
    print people_to_notify
    print "Exiting main()"

if __name__ == "__main__":
    main()
