import json
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
        Returns a list of subpages of T:DYK nominated for DYK.
        """
        dyk_noms = []
        wikitext = self._ttdyk.getWikiText()
        print "Got wikitext from TT:DYK."
        params = {"action":"parse", "page":"Template talk:Did you know",\
                  "prop":"templates"}
        api_request = api.APIRequest(self._wiki, params)
        print "Sending an APIRequest for the templates on TT:DYK..."
        api_result = api_request.query()
        print "APIRequest completed."
        templates = json.loads(json.dumps(api_result))
        for template in templates["parse"]["templates"]:
            if template["*"].startswith("Template:Did you know nominations/"):
                dyk_noms.append(template["*"])
        return dyk_noms

    def prune_dyk_nom_list(self, dyk_noms):
        print "About to prune " + str(len(dyk_noms)) + " queries."
        dyk_noms_strings = list_to_pipe_separated_query(dyk_noms)
        for dyk_noms_string in dyk_noms_strings:
            params = {"action":"query", "titles":dyk_noms_string, "prop":"categories"}
            api_request = api.APIRequest(self._wiki, params)
            print api_request.query()
        return dyk_noms
                
    def get_people_to_notify(self, dyk_noms):
        people_to_notify = []
        for dyk_nom_title in dyk_noms:
            print "Checking " + dyk_nom_title + "..."
            dyk_nom = Page(self._wiki, title=dyk_nom_title)
            nom_wikitext = dyk_nom.getWikiText()
            line_begin = nom_wikitext.find("<small>Created by ")
            line_end = nom_wikitext[line_begin:].find(\
                "</small>.")
            line_begin += len("<small>")
            line_end += line_begin - 7 # To take out "</small>."
            print nom_wikitext[line_begin:line_end]
        return people_to_notify

def query(request):
    """
    Queries the MediaWiki API in a humane way.
    """
    request['action'] = 'query'
    request['format'] = 'json'
    lastContinue = dict()
    while True:
        # Clone original request
        req = request.copy()
        # Modify it with the values returned in the 'continue' section of the last result.
        req.update(lastContinue)
        # Call API
        result = requests.get('http://en.wikipedia.org/w/api.php', params=req).json()
        if 'error' in result: raise Error(result['error'])
        if 'warnings' in result: print(result['warnings'])
        if 'query' in result: yield result['query']
        if 'continue' not in result: break
        lastContinue = result['continue']

def list_to_pipe_separated_query(the_list):
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
    print "[main()] Got a list of DYK noms from TT:DYK."
    dyk_noms = notifier.prune_dyk_nom_list(dyk_noms)
    print "[main()] Pruned list of DYK noms."
    people_to_notify = notifier.get_people_to_notify(dyk_noms)
    print "[main()] Got a list of people to notify."
    print people_to_notify
    print "[main()] Exiting main()"

if __name__ == "__main__":
    main()
