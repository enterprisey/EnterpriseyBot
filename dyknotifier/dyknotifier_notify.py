"A Python script to notify a bunch of people about their DYK nominations."

import getpass
import json
import sys
import argparse

# pylint: disable=import-error
from wikitools.wiki import Wiki
# pylint: disable=import-error
from wikitools.page import Page

wiki = Wiki("http://en.wikipedia.org/w/api.php")
people_to_notify = dict()

###################
# ARGS
###################
parser = argparse.ArgumentParser(prog="DYKNotifier",
                                 description=\
                                 "Edit talkpages of editors to be nominated.")
parser.add_argument("-i", "--interactive", action="store_true",
                    help="Confirm before each edit.")
parser.add_argument("-p", "--previous-edits", type=int,
                    help="People already notified (for running total)")
parser.add_argument("--file", help="Read JSON from a file instead")
args = parser.parse_args()

people_notified_count = args.previous_edits if args.previous_edits else 0

# CONFIGURATION
SUMMARY = "[[Wikipedia:Bots/Requests for approval/APersonBot " +\
		"2|Bot]] notification about the DYK nomination of" +\
		" %(nom_name)s."

###################
# LOGIN
###################
while True:
    username = raw_input("Username: ")
    password = getpass.getpass("Password for " + username + " on enwiki: ")
    print "Logging in to enwiki as " + username + "..."
    wiki.login(username, password)
    if wiki.isLoggedIn():
        break
    print "Error logging in. Try again."
print "Successfully logged in as " + wiki.username + "."

###################
# GET PEOPLE TO NOTIFY
###################
if args.file:
    args.file = args.file.strip()
    print "Attempting to read JSON from file \"" + args.file + "\"..."
    with open(args.file) as jsonfile:
        people_to_notify = json.load(jsonfile)
        assert hasattr(people_to_notify, "keys")
        jsonfile.close()
else:
    while True:
        user_input = raw_input("JSON: ")
        try:
            people_to_notify = json.loads(user_input)
            assert hasattr(people_to_notify, "keys")
            break
        except ValueError as ex:
            print "ValueError: " + str(ex)
            print "ERROR parsing JSON. Try again."
        except AttributeError as ex:
            print "AttributeError: " + str(ex)
            print "ERROR parsing JSON. Try again."

print "Loaded " + str(len(people_to_notify.keys())) + " people. Cool!"

###################
# NOTIFY PEOPLE
###################
for person in people_to_notify.keys():
    nom_name = people_to_notify[person]
    template = "\n\n{{subst:DYKNom|" +\
               nom_name[34:] + "|passive=yes}}"
    print
    print "Notifying " + str(person) + " because of " +\
          nom_name + "..."
    if args.interactive:
        choice = raw_input("What (s[kip], c[ontinue], q[uit])? ")
        if choice[0] == "s":
            print "Skipping " + str(person) + "."
            continue
        elif choice[0] == "q":
            print "Exiting loop..."
            sys.exit(0)
    talkpage = Page(wiki, title="User talk:" + person)
    # cross fingers here
    result = talkpage.edit(appendtext=template, bot=True,\
                            summary=SUMMARY %\
                            {"nom_name":nom_name[34:].encode(\
                                "ascii", "ignore")})
    print "Result: " + str(result)
    people_notified_count += 1
    print str(people_notified_count) + " have been notified so far."
    print "Notified " + person + " because of " + nom_name + "."

###################
# FINISH UP
###################
print()
print("TOTAL # of people notified so far: " +\
      str(people_notified_count))
print "Done! Exiting."
