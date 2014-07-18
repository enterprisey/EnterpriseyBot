import getpass
import json
import re
from wikitools.wiki import Wiki
from wikitools.page import Page

class DYKNotifier():
    """
    A Python script to notify a bunch of people about their DYK nominations.
    """

    def __init__(self):
        self._wiki = Wiki("http://en.wikipedia.org/w/api.php")
        self._people_to_notify = dict()

        # CONFIGURATION
        self._summary = "[[Wikipedia:Bots/Requests for approval/APersonBot " +\
                        "2|Robot]] notification about the DYK nomination of" +\
                        " %(nom_name)s."

        # LOGIN
        while True:
            username = raw_input("Username: ")
            password = getpass.getpass()
            self._wiki.login(username, password)
            if self._wiki.isLoggedIn():
                break
            print "Error logging in. Try again."
        print "Successfully logged in as " + self._wiki.username + "."

    def run(self):
        """
        Runs the task.
        """
        self.get_people()
        self.notify_people()
        print "[run()] Notified people."

    def get_people(self):
        """
        Gets a list of people from stdin and parses the JSON.
        """
        while True:
            user_input = raw_input("JSON: ")
            try:
                data = json.loads(user_input)
                keys = data.keys()
                self._people_to_notify = data
                break
            except Exception as ex:
                print "[get_people()] Error: " + str(ex)
                print "[get_people()] ERROR parsing JSON. Try again."
        print "[get_people()] Loaded " + str(len(data.keys())) + " people. Cool!"
        
    def notify_people(self):
        """
        Substitutes User:APersonBot/DYKNotice at the end of each page in a list
        of user talkpages, given a list of usernames.
        """
        people_notified_count = 0
        for person in self._people_to_notify.keys():
            nom_name = self._people_to_notify[person]
            template = "\n\n{{subst:DYKNom|" +\
                       nom_name[34:] + "|passive=yes}}"
            print "ABOUT TO NOTIFY " + str(person) + " BECAUSE OF " +\
                  nom_name + "..."
            if raw_input("Continue (y/n)? ") == "n":
                print "Exiting loop..."
                return
            talkpage = Page(self._wiki, title="User talk:" + person)
            # cross fingers here
            result = talkpage.edit(appendtext=template, bot=True,\
                                    summary=self._summary %\
                                    {"nom_name":nom_name.encode(\
                                        "ascii", "ignore")})
            print "Result: " + str(result)
            people_notified_count += 1
            print str(people_notified_count) + " have been notified so far."
            print "Notified " + person + " because of " + nom_name + "."

    def pretty_print(self, query_result):
        """
        What **is** beauty?
        """
        print json.dumps(query_result, indent=4, separators=(",", ": "))

def main():
    print "[main()] Before DYKNotifier constructor"
    notifier = DYKNotifier()
    print "[main()] Constructed a DYKNotifier."
    notifier.run()
    print "[main()] Exiting main()"

if __name__ == "__main__":
    main()
