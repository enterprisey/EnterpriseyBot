import unittest

from fixer import Processor

class TestFixer(unittest.TestCase):
    def test_itn(self):
        processor = Processor("""
{{article history
|action1=GAN
|action1date=12:52, 7 December 2005
|action1result=listed
|action1oldid=30462537
|currentstatus=GA
|topic=math
}}
{{ITN talk|date1=12 September 2009|date2=24 December 2013}}""")
        self.assertEqual(processor.get_processed_text(), """
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
        processor = Processor("""
{{article history
|action1=GAN
|action1date=12:52, 7 December 2005
|action1result=listed
|action1oldid=30462537
|currentstatus=GA
|topic=math
}}
{{On this day|date1=2004-05-28|oldid1=6717950|date2=2005-05-28|oldid2=16335227}}""")
        self.assertEqual(processor.get_processed_text(), """
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
        processor = Processor("""
{{Article history
| action1       =  GAN
| action1date   = 14:45, 22 March 2015 (UTC)
| action1link   = Talk:Dyslexia/GA1
| action1result = Passed
| action1oldid  = 653061069
}}
{{dyktalk|6 April|2015|entry= ... that '''[[dyslexia]]''' is the most common learning disability, affecting about 3% to 7% of people?}}""")
        self.assertEqual(processor.get_processed_text(), """
{{article history
|action1=GAN
|action1date=14:45, 22 March 2015 (UTC)
|action1link=Talk:Dyslexia/GA1
|action1result=Passed
|action1oldid=653061069

|dykdate=6 April 2015
|dykentry= ... that '''[[dyslexia]]''' is the most common learning disability, affecting about 3% to 7% of people?
}}""")

if __name__ == '__main__':
    unittest.main()
