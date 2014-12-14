"A Python script to notify a bunch of people about their DYK nominations."

import getpass
import json
import sys
import argparse
from string import Template

###################
# LOGGING
###################
import logging
logging.basicConfig(filename='dyknotifier.log',
                    level=logging.DEBUG,
                    datefmt="%d %b. %Y %I:%M:%S",
                    format="[%(asctime)s] [%(levelname)s] %(message)s")
streamHandler = logging.StreamHandler()
streamHandler.setLevel(logging.INFO)
logging.getLogger().addHandler(streamHandler)

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
parser.add_argument("-f", "--file", help="Read JSON from a file instead.")
parser.add_argument("-c", "--count", type=int, help="Notify at most n people.")
args = parser.parse_args()

# CONFIGURATION
SUMMARY = Template("[[Wikipedia:Bots/Requests for approval/APersonBot " +\
		"2|Bot]] notification about the DYK nomination of" +\
		" %{nomination}s.")
MESSAGE = Template("\n\n{{subst:DYKNom|${nomination}|passive=yes}}")

###################
# LOGIN
###################
while True:
    username = raw_input("Username: ")
    password = getpass.getpass("Password for " + username + " on enwiki: ")
    logging.info("Logging in to enwiki as " + username + "...")
    wiki.login(username, password)
    if wiki.isLoggedIn():
        break
    logging.error("Error logging in. Try again.")
logging.info("Successfully logged in as " + wiki.username + ".")

###################
# GET PEOPLE TO NOTIFY
###################
if args.file:
    args.file = args.file.strip()
    logging.info("Attempting to read JSON from file \"" + args.file + "\"...")
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
            logging.error("ValueError while parsing JSON: " + str(ex))
        except AttributeError as ex:
            logging.error("AttributeError while parsing JSON: " + str(ex))

logging.info("Loaded " + str(len(people_to_notify.keys())) + " people. Cool!")

###################
# NOTIFY PEOPLE
###################
num_notified = 0
for person in people_to_notify.keys():
    nom_name = people_to_notify[person][34:]
    logging.info("Notifying " + str(person) + " because of " +\
          nom_name + "...")
    if args.count:
        if num_notified >= args.count:
            logging.info(str(num_notified) + " notified; exiting.")
            sys.exit(0)
    if args.interactive:
        choice = raw_input("What (s[kip], c[ontinue], q[uit])? ")
        if choice[0] == "s":
            print "Skipping " + str(person) + "."
            continue
        elif choice[0] == "q":
            print "Stop requested; exiting."
            sys.exit(0)
    talkpage = Page(wiki, title="User talk:" + person)
    text_to_add = MESSAGE.substitute(nomination=nom_name)
    edit_summary = SUMMARY.substitute(nomination=nom_name.encode("ascii",
                                                                 "ignore"))
    result = talkpage.edit(appendtext=text_to_add,
                           bot=True,
                           summary=edit_summary)
    num_notified += 1
    logging.info("Result: " + str(result))
    logging.info("Notified " + person + " because of " + nom_name + ".")

###################
# FINISH UP
###################
logging.info("Done; exiting.")
