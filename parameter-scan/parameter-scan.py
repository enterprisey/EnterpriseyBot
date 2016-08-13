import codecs
from numbers import Number
import pywikibot
import re
import sys

from clint.textui import progress

TEMPLATE_NAME = "Template:Infobox Fraternity"
TEMPLATE_REGEX = r"\{\{Infobox(\s|_)Fraternity(\{\{.+\}\}|[\s\S])+?\}\}"
TEMPLATE_PATTERN = re.compile(TEMPLATE_REGEX, flags=re.IGNORECASE)
TEMPLATE_SUB = re.compile(r"\{\{.+?\}\}")
LINK_SUB = re.compile(r"\[\[(?P<target>.+?)\|(?P<text>.+?)\]\]")
REF_SUB = re.compile(r"<ref[\s\S]+?</ref>")
#EQUALS_SIGN_STRIP = re.compile(r"\s*=\s*")
PARAM_SPLIT = re.compile(r"\s*([\s\S]*?)\s*=\s*([\s\S]*)\s*")
DUNNO = "{{dunno|(none)}}"
TEMPLATE_TRANSCLUSIONS = 570

#COUNT_AND_LIST = ("origin_coordinates", "location", "length_km", "length_mi", "elevation_m", "elevation_ft", "mouth_elevation_m", "mouth_elevation_ft", "discharge_m3/s", "discharge_cuft/s", "watershed_km2", "watershed_sqmi", "etymology", "river_system", "native_name_lang")

site = pywikibot.Site("en", "wikipedia")
site.login()

template = pywikibot.Page(site, TEMPLATE_NAME)

#param_usage = {}
#param_empty_usage = {}
#types = []
#pages = {}
pages_by_type = {}

references = template.getReferences(onlyTemplateInclusion=True,
                                    namespaces=(0))
progress = progress.bar(references, expected_size=TEMPLATE_TRANSCLUSIONS)

#i = 0

for each_page in progress:
    #if i > 10: break
    each_title = each_page.title(withNamespace=True)
    each_text = each_page.get()
    match = TEMPLATE_PATTERN.search(each_text)
    if not match:
        print(each_title)
        print("^ NO MATCH FOUND!")
    transclusion = match.group(0)[2:-2]
    transclusion = TEMPLATE_SUB.sub("!t!", transclusion)
    transclusion = LINK_SUB.sub(r"[[\1!\2]]", transclusion)
    transclusion = REF_SUB.sub("!r!", transclusion)
    for param in transclusion.split("|")[1:]:
        try:
            _, param_name, param_value, _ = PARAM_SPLIT.split(param)
        except:
            pass

        if param_name.lower() != "type":
            continue

        pages_by_type[param_value] = pages_by_type.get(param_value, []) + [each_title]
        #pages[each_title] = param_value
        #dictionary = param_usage if param_value else param_empty_usage
        #dictionary[param_name] = dictionary.get(param_name, []) + [each_title]

    #i += 1

#print("\n".join([x + ": " + y for x, y in pages.items()]))
#sys.exit(0)
for param_value, page_titles in pages_by_type.items():
    print("* " + re.sub(r"!(.)", r"|\1", param_value.strip()).encode("utf-8") + " (" + " ".join("[[{}|{}]]".format(item.encode("utf-8"), index + 1) for index, item in enumerate(page_titles)) + ")")
sys.exit(0)

types = [x.strip().encode("utf-8", "replace") for x in types]
frequencies = {}
for each_type in set(types):
    frequencies[each_type] = types.count(each_type)
print("\n".join([x + ("" if (i == 1) else (" (" + str(i) + "x)")) for x, i in frequencies.items()]))
sys.exit(0)

for dictionary in (param_usage, param_empty_usage):
    for param, titles in dictionary.items():
        if param not in COUNT_AND_LIST:
            dictionary[param] = len(titles)

def cell(dictionary, param):
    if param in dictionary:
        s = dictionary[param]
        if isinstance(s, Number):
            return "{} usage{}".format(s, "" if s == 1 else "s")
        else:
            if len(s) == 1:
                return "[[" + s[0] + "]]"
            else:
                usages = "{} usages: ".format(len(s))
                return usages + ", ".join(["[[" + x + "]]" for x in s])
    else:
        return DUNNO

result = '{| class=\"wikitable\"\n'
for param in (param_usage.keys() + param_empty_usage.keys()):
    result += '!rowspan="2"|' + param + "\n"
    result += "|" + cell(param_usage, param) + "\n"
    result += "|-\n|" + cell(param_empty_usage, param) + "\n|-\n"
result += "|}"

print(result)

with open("result.txt", "w") as result_file:
    result = str(result.encode("utf-8", "replace"))
    result_file.write(result)
