import cgi
import json
import os

def main():
    print("Content-Type: text/html")
    print()
    print("""<!DOCTYPE HTML>
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8"/>
<title>CatTrack - Results</title>
<link rel="stylesheet" type="text/css" href="style.css">
</head>
<body>""")

    form = cgi.FieldStorage()
    category = form["category"]

    print("""
<h1>CatTrack info for <a href='https://en.wikipedia.org/wiki/Category:{0}'>Category:{0}</a></h1>
<table><tr><th>Date</th><th>Category size</th></tr>""")

    bad_dates = []

    for each_filename in os.listdir("."):
        each_date = each_filename[:-5]
        if ".json" not in each_filename:
            continue

        with open(each_filename) as each_file:
            date_data = json.load(each_file)
            if category in date_data:
                cat_size = date_data[category]
                print("<tr><td>{}</td><td>{}</td></tr>".format(each_date,
                                                               cat_size))
            else:
                bad_dates += [each_date]

    print("</table>")

    if bad_dates:
        print("<p>Unable to read category data for: " +
              ", ".join(bad_dates) + "</p>")

    print("<footer><a href='https://en.wikipedia.org/wiki/User:APerson' title='APerson's user page on the English Wikipedia'>APerson</a> (<a href='https://en.wikipedia.org/wiki/User_talk:APerson' title='APerson's talk page on the English Wikipedia'>talk!</a>)</footer></body></html>")

main()
