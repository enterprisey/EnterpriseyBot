import argparse
import datetime
import itertools
import re
import sys
from time import mktime

from parsedatetime import Calendar

# Pywikibot imported in main() so we can test w/o importing

ACTION_ORDER = ("", "date", "link", "result", "oldid")
EXTRA_SUFFIXES = {
    "itn": ["link"],
    "otd": ["oldid", "link"],
    "dyk": ["entry"]
    }
DELETE_COMMENT = "<!-- Delete this line. -->"
ARTICLE_HISTORY = re.compile(r"\{\{(article history[\s\S]*?)\}\}",
                                   flags=re.IGNORECASE)
ITN = re.compile(r"\{\{(itn talk[\s\S]+?)\}\}", flags=re.IGNORECASE)
OTD = re.compile(r"\{\{(on this day[\s\S]+?)\}\}", flags=re.IGNORECASE)
DYK = re.compile(r"\{\{(dyktalk[\s\S]+?)\}\}", flags=re.IGNORECASE)

class History:
    def __init__(self, wikitext):
        """Builds fields from text containing a transclusion."""
        search = ARTICLE_HISTORY.search(wikitext)
        params = search.group(1).split("|")[1:]
        params = {x.strip(): y.strip() for x, y in [t.split("=") for t in params]}

        # Actions
        self.actions = []
        next_action = lambda: "action%d" % (len(self.actions) + 1)
        while next_action() in params:
            prefix = next_action()
            self.actions.append(tuple(params.get(prefix + suffix, "") for suffix in ACTION_ORDER))

        # Other parameters
        self.other_parameters = {x: y for x, y in params.items() if "action" not in x}

    def as_wikitext(self):
        """Converts template to wikitext."""
        result = "{{article history"

        def test_and_build(*parameters):
            test_results = []
            for parameter in parameters:
                if parameter in self.other_parameters:
                    test_results.append("\n|%s=%s" % (parameter, self.other_parameters[parameter]))
            return "".join(test_results)

        for index, action in enumerate(self.actions, start=1):
            for suffix, value in zip(ACTION_ORDER, action):
                result += "\n|action%i%s=%s" % (index, suffix, value)
            result += "\n"

        result += test_and_build("currentstatus", "maindate")
        for code in ("itn", "otd", "dyk"):
            suffixes = ["date"] + EXTRA_SUFFIXES[code]
            for suffix in suffixes:
                result += test_and_build(code + suffix)
            if code + "2date" in self.other_parameters:
                last_num = next(i for i in itertools.count(1) if "%s%ddate" % (code, i) in self.other_parameters)
                for i, suffix in itertools.product(range(2, last_num + 1), suffixes):
                    result += test_and_build("%s%d%s" % (code, i, suffix))
        result += test_and_build("four", "aciddate", "ftname", "ftmain", "ft2name", "ft2main", "ft3name", "ft3main", "topic", "small")
        result += "\n}}"
        return result

class Processor:
    def __init__(self, wikitext):
        self.text = wikitext

    def get_processed_text(self):
        old_ah_wikitext_search = ARTICLE_HISTORY.search(self.text)

        if not old_ah_wikitext_search:
            return self.text

        old_ah_wikitext = old_ah_wikitext_search.group(0)
        history = History(self.text)

        # For use in sorting parameters
        by_time = lambda x: datetime.datetime.fromtimestamp(mktime(Calendar().parse(x[0])[0]))

        if ITN.search(self.text):
            itn_list = self.get_relevant_params("itn", history)
            for itn_result in ITN.finditer(self.text):
                itn = itn_result.group(1)
                itn_list += [(x[x.find("=")+1:], "") for x in itn.split("|")[1:] if "date" in x]
                self.text = self.text.replace(itn_result.group(0), DELETE_COMMENT)

            itn_list.sort(key=by_time)

            # Update the article history template
            history.other_parameters["itndate"] = itn_list[0][0]
            if itn_list[0][1]:
                history.other_parameters["itnlink"] = itn_list[0][1]
            for i, item in enumerate(itn_list[1:], start=2):
                history.other_parameters["itn%ddate" % i] = item[0]
                if item[1]:
                    history.other_parameters["itn%ditem" % i] = item[1]

        if OTD.search(self.text):
            otd_list = self.get_relevant_params("otd", history)
            for otd_result in OTD.finditer(self.text):
                otd = otd_result.group(1)
                otd_params = {x: y for x, y in [t.strip().split("=") for t in otd.split("|")[1:]]}
                for i in itertools.count(1):
                    date_key = "date%d" % i
                    if date_key in otd_params:
                        otd_list.append((otd_params[date_key],
                                         otd_params.get("oldid%d" % i, ""),
                                         ""))
                    else:
                        break
                self.text = self.text.replace(otd_result.group(0), DELETE_COMMENT)

            otd_list.sort(key=by_time)

            # Update the article history template
            history.other_parameters["otddate"], history.other_parameters["otdoldid"], _ = otd_list[0]
            if otd_list[0][2]:
                history.other_parameters["otdlink"] = otd_list[0][2]
            for i, item in enumerate(otd_list[1:], start=2):
                history.other_parameters["otd%ddate" % i], history.other_parameters["otd%doldid" % i], _ = item
                if item[2]:
                    history.other_parameters["otd%dlink" % i] = item[2]

        dyk_search = DYK.search(self.text)
        if dyk_search:
            dyk = dyk_search.group(1)
            dyk_params = dyk.split("|")[1:]
            history.other_parameters["dykentry"] = next(x for x in dyk_params if x.startswith("entry")).split("=")[1]
            positional_dyk_params = [x for x in dyk_params if "=" not in x]
            if len(positional_dyk_params) == 1:
                history.other_parameters["dykdate"] = positional_dyk_params[0]
            elif len(positional_dyk_params) == 2:
                for param in positional_dyk_params:
                    if len(param) == 4:
                        year = param
                    else:
                        month_day = param
                history.other_parameters["dykdate"] = month_day + " " + year

            # Delete the DYK template
            self.text = self.text.replace(dyk_search.group(0), DELETE_COMMENT)

        # Delete the lines with only the delete comment on them
        self.text = "\n".join(x for x in self.text.splitlines() if x != DELETE_COMMENT)
        self.text = self.text.replace(old_ah_wikitext, history.as_wikitext())
        return self.text

    def get_relevant_params(self, code, history):
        current_params = {x: y for x, y in history.other_parameters.items() if code in x}
        result = []
        extra_suffixes = EXTRA_SUFFIXES[code]
        for date_param_name in [x for x in current_params if "date" in x]:
            new_item = [current_params[date_param_name]]
            for extra_suffix in extra_suffixes:
                new_item.append(current_params.get(date_param_name.replace("date", extra_suffix), ""))
            result.append(tuple(new_item))
        return result

def main():
    import pywikibot

    site = pywikibot.Site("en", "wikipedia")
    site.login()

    parser = argparse.ArgumentParser()
    parser.add_argument("page", help="The title (no namespace) of the talk page to fix.")
    args = parser.parse_args()

    page_title = args.page if args.page.startswith("Talk:") else "Talk:" + args.page
    page = pywikibot.Page(site, page_title)
    if not page.exists():
        print("%s doesn't exist! Exiting." % page_title)
        sys.exit(1)

    processor = Processor(page.text)
    page.text = processor.get_processed_text()
    print(page.text[:page.text.find("==")])
    #page.save(summary="Bot testing for a BOTREQ request")

    dump_page = pywikibot.Page(site, "User:APersonBot/sandbox")
    dump_page.text += "\n\n==Testing article-history (%s)==\n\n" % page_title
    dump_page.text += page.text[:page.text.find("==")]
    dump_page.save(summary="Bot testing for a BOTREQ request")

if __name__ == "__main__":
    main()
