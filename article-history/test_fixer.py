import unittest

from fixer import History, process, encode_wikilinks, decode_wikilinks

class TestEncodeDecode(unittest.TestCase):
    def roundtrip(self, some_text):
        wikitext, wikilinks = encode_wikilinks(some_text)
        self.assertEqual(some_text, decode_wikilinks(wikitext, wikilinks))

    def test_roundtrip_empty(self):
        self.roundtrip("")

    def test_roundtrip_random_text(self):
        self.roundtrip("asdf")

    def test_roundtrip_non_piped_link(self):
        self.roundtrip("[[asdf]]")

    def test_roundtrip_piped_link(self):
        self.roundtrip("[[asdf|hjkl]]")

class TestAH(unittest.TestCase):
    def setUp(self):
        self.history_normal = History("""
{{article history
|action1=GAN
|action1date=12:52, 7 December 2005
|action1result=listed
|action1oldid=30462537
|currentstatus=GA
|topic=math
}}""")

    def test_actions(self):
        self.assertEqual(self.history_normal.actions[0],
                         ("GAN", "12:52, 7 December 2005", "", "listed", "30462537"))

    def test_other(self):
        self.assertEqual(self.history_normal.other_parameters,
                         {"currentstatus":"GA", "topic":"math"})

class TestFixer(unittest.TestCase):

    def test_itn(self):
        self.assertEqual(process("""
{{article history
|action1=GAN
|action1date=12:52, 7 December 2005
|action1result=listed
|action1oldid=30462537
|currentstatus=GA
|topic=math
}}
{{ITN talk|date1=12 September 2009|date2=24 December 2013}}"""), """
{{article history
|action1=GAN
|action1date=12:52, 7 December 2005
|action1link=
|action1result=listed
|action1oldid=30462537

|currentstatus=GA
|itndate=12 September 2009
|itn2date=24 December 2013
|topic=math
}}""")

    def test_otd(self):
        self.assertEqual(process("""
{{article history
|action1=GAN
|action1date=12:52, 7 December 2005
|action1result=listed
|action1oldid=30462537
|currentstatus=GA
|topic=math
}}
{{On this day|date1=2004-05-28|oldid1=6717950|date2=2005-05-28|oldid2=16335227}}"""), """
{{article history
|action1=GAN
|action1date=12:52, 7 December 2005
|action1link=
|action1result=listed
|action1oldid=30462537

|currentstatus=GA
|otddate=2004-05-28
|otdoldid=6717950
|otd2date=2005-05-28
|otd2oldid=16335227
|topic=math
}}""")

    def test_dyk(self):
        self.assertEqual(process("""
{{Article history
| action1       =  GAN
| action1date   = 14:45, 22 March 2015 (UTC)
| action1link   = Talk:Dyslexia/GA1
| action1result = Passed
| action1oldid  = 653061069
}}
{{dyktalk|6 April|2015|entry= ... that '''[[dyslexia]]''' is the most common learning disability, affecting about 3% to 7% of people?}}"""), """
{{article history
|action1=GAN
|action1date=14:45, 22 March 2015 (UTC)
|action1link=Talk:Dyslexia/GA1
|action1result=Passed
|action1oldid=653061069

|dykdate=6 April 2015
|dykentry= ... that '''[[dyslexia]]''' is the most common learning disability, affecting about 3% to 7% of people?
}}""")

    def test_empty(self):
        self.assertEqual(process(""), "")

    def test_blank_ah(self):
        self.assertEqual(process("""
{{Article history}}
{{ITN talk|date1=1 June 2009}}"""), """
{{article history
|itndate=1 June 2009
}}""")

    def test_already(self):
        self.assertEqual(process("""
{{Article history|itndate=1 June 2009}}
{{ITN talk|date1=1 June 2010}}"""), """
{{article history
|itndate=1 June 2009
|itn2date=1 June 2010
}}""")

    def test_multiple(self):
        self.assertEqual(process("""
{{Article history}}
{{ITN talk|date1=1 June 2010}}
{{ITN talk|date1=1 June 2009}}"""), """
{{article history
|itndate=1 June 2009
|itn2date=1 June 2010
}}""")

if __name__ == '__main__':
    unittest.main()
