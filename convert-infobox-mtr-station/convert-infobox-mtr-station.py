import argparse
import datetime
import pywikibot
import re
import sys

import mwparserfromhell

FIRST_PARAGRAPH = re.compile(r"('''.+?'''.+?)\n\n", re.M | re.DOTALL)
LINE_DATA_CODE = re.compile(r"codes = \{(.+?)\},")
PARAMETERS_MAPPING = {"engname": "name", "chiname": "native_name", "image": "image", "caption": "caption", "code": "code", "type": "structure", "coordinatesN": "latitude", "coordinatesE": "longitude", "platformno": "platforms", "connections": "connections", "area": "address"}
PARAMETER_ORDER = ["name", "native_name", "native_name_lang", "symbol_location", "symbol", "type", "image", "caption", "address", "borough", "coordinates_display", "latitude", "longitude", "line", "platforms", "tracks", "structure", "code", "opened", "services", "connections", "map_type"]
DEFAULT_NEW_PARAMETERS = {"native_name_lang": "zh", "symbol_location": "hk", "type": "[[Hong Kong]] [[MTR]] rapid transit station", "coordinates_display": "inline,title", "map_type": "Hong Kong MTR"}

def load_line_codes(site):
    """Loads the line codes from the wiki."""
    data_page = pywikibot.Page(site, "Module:MTR/data")
    line_codes = {}
    for each_match in LINE_DATA_CODE.finditer(data_page.get()):
        each_list = re.findall(r"'([\w ]+?)'", each_match.group(1))
        each_list_sorted = sorted(each_list, key=len)
        try:
            code = next(x for x in each_list if len(x) == 3)
        except StopIteration:
            code = min(each_list, key=len)
        each_list.remove(code)
        code = code.lower()
        for each_key in each_list:
            line_codes[each_key] = code
    return line_codes

def convert_wikitext(wikitext, line_codes):
    """Convert wikitext containing a MTR Station infobox."""
    wikicode = mwparserfromhell.parse(wikitext)
    templates = wikicode.filter_templates()
    infobox = next(x for x in templates if x.name.strip() == "Infobox MTR station")
    old_params = {}
    for parameter_string in infobox.params:
        key, _, value = parameter_string.partition("=")
        key, value = key.strip(), value.strip()
        if bool(key) and bool(value):
            old_params[key] = value

    new_params = DEFAULT_NEW_PARAMETERS.copy()
    for old_name, new_name in PARAMETERS_MAPPING.items():
        new_params[new_name] = old_params.get(old_name, "")
    if old_params.get("services", ""): new_params["services"] = "{{s-rail|title=HK-MTR}}" + old_params["services"]
    new_params["borough"] = (old_params["district"]
                             if "[[" in old_params["district"]
                             else "[[" + old_params["district"] + "]]")
    new_params["tracks"] = raw_input("How many tracks does {} have? ".format(new_params["name"]))
    if old_params.get("open", ""): new_params["opened"] = datetime.datetime.strptime(old_params["open"], "%d %B %Y").strftime("{{Start date|%Y|%m|%d|df=y}}")
    new_params["symbol"] = line_codes[old_params["line"].upper()]
    new_params["line"] = "{{HK-MTR box|%s}}" % old_params["line"]
    if old_params.get("line2", ""):
        new_params["symbol2"] = line_codes[old_params["line2"].upper()]
        new_params["line"] += "\n{{HK-MTR box|%s}}" % old_params["line2"]

    new_infobox = u"{{Infobox station"
    for key in PARAMETER_ORDER:
        if new_params.get(key, ""):
            new_infobox += u"\n|{}={}".format(unicode(key), unicode(new_params[key]))
    new_infobox += u"\n}}"

    # Template in new_params
    old_infobox = unicode(infobox)
    new_infobox = unicode(new_infobox)
    wikitext = wikitext.replace(old_infobox, new_infobox)

    # Also, insert the hours open at the end of the first paragraph
    if old_params.get("hours", ""):
        separator = "-"
        if "-" not in old_params["hours"]:
            separator = "/"
        time_open, time_close = old_params["hours"].split(separator)
        first_paragraph_match = FIRST_PARAGRAPH.search(wikitext)
        if first_paragraph_match:
            first_paragraph = first_paragraph_match.group(1)
            new_sentence = " The station is open between {} and {}.".format(time_open, time_close)
            wikitext = wikitext.replace(first_paragraph, first_paragraph + new_sentence)
        else:
            print("No first paragraph found!")

    return wikitext

def main():
    site = pywikibot.Site("en", "wikipedia")
    site.login()

    line_codes = load_line_codes(site)

    parser = argparse.ArgumentParser()
    parser.add_argument("page", help="The page to edit")
    args = parser.parse_args()

    page = pywikibot.Page(site, args.page)
    page.text = convert_wikitext(page.text, line_codes)
    page.save(summary="Converting Template:Infobox MTR station to just Template:Infobox station", botflag=False)

if __name__ == "__main__":
    main()
