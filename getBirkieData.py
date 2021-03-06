#to scrape birkie results data from the searchable results
#event ids:
#2015 birkie skate: 114
#2015 birkie classic: 115
#2015 kortie skate: 112
#2015 kortie classic: 113
#2015 prince haakon: 110

from lxml import html
import requests
import BeautifulSoup
import urllib2
import time

def main():
    results = []
    eventIDs = {'birkie skate 2015': 114, 'birkie classic 2015': 115,'kortie skate 2015': 112,'kortie classic 2015': 113,'prince haakon 2015': 110}
    eventIDs['birkie classic 2014'] = 103
    eventIDs['birkie skate 2014'] = 102
    eventIDs['kortie skate 2014'] = 100
    eventIDs['kortie classic 2014'] = 101
    eventIDs['prince haakon freestyle 2014'] = 98

    eventIDs['birkie classic 2013'] = 91
    eventIDs['birkie skate 2013'] = 90
    eventIDs['kortie skate 2013'] = 88
    eventIDs['kortie classic 2013'] = 89
    eventIDs['prince haakon 2013'] = 86

    eventIDs['birkie classic 2012'] = 84
    eventIDs['birkie skate 2012'] = 83
    eventIDs['kortie skate 2012'] = 81
    eventIDs['kortie classic 2012'] = 82
    eventIDs['prince haakon 2012'] = 79

    eventIDs['birkie classic 2011'] = 53
    eventIDs['birkie skate 2011'] = 52
    eventIDs['kortie skate 2011'] = 50
    eventIDs['kortie classic 2011'] = 51
    eventIDs['prince haakon 2011'] = 54

    eventIDs['birkie classic 2010'] = 44
    eventIDs['birkie skate 2010'] = 45
    eventIDs['kortie skate 2010'] = 46
    eventIDs['kortie classic 2010'] = 47
    eventIDs['prince haakon 2010'] = 48

    eventIDs['birkie classic 2009'] = 37
    eventIDs['birkie skate 2009'] = 38
    eventIDs['kortie skate 2009'] = 39
    eventIDs['kortie classic 2009'] = 40


    #event = raw_input("enter event name, i.e. birkie skate 2015 \n")
    #eventID = eventIDs[event]
    for event in eventIDs:
        results = []
        print event
        eventID = eventIDs[event]
        print eventID
        page = BeautifulSoup.BeautifulSoup(urllib2.urlopen('http://results.birkie.com/index.php?event_id=' + str(eventID)).read())
        tables = page.findAll("tbody")
        print tables
        racers = tables[2].findAll("tr")
        for e in range(len(racers) - 3):
            data = racers[e+2].findAll("td")
            result = []
            result.append(data[4].a.contents[0].encode('ascii', 'ignore'))    #name
            result.append(data[3].a.contents[0].encode('ascii', 'ignore'))    #bib
            result.append(data[1].contents[0].encode('ascii', 'ignore'))    #gender place
            result.append(data[2].contents[0].encode('ascii', 'ignore'))    #div place
            result.append(data[5].contents[0].encode('ascii', 'ignore'))    #city
            result.append(data[0].contents[0].encode('ascii', 'ignore'))      #overall place
            result.append(data[6].contents[0].encode('ascii', 'ignore'))      #finish time
            results.append(result)       
        print results[0]        

        numPages = 50               #doesn't matter if page number is larger than number of pages of results
        for i in range(numPages):
            j = i + 2
            time.sleep(2)
            page = BeautifulSoup.BeautifulSoup(urllib2.urlopen('http://results.birkie.com/index.php?page_number=' + str(j) +'&event_id='+ str(eventID) + '&test=1').read())
            tables = page.findAll("tbody")
            racers = tables[2].findAll("tr")
            for e in range(len(racers) - 3):
                data = racers[e+2].findAll("td")
                result = []
                result.append(data[4].a.contents[0].encode('ascii', 'ignore'))    #name
                result.append(data[3].a.contents[0].encode('ascii', 'ignore'))    #bib
                result.append(data[1].contents[0].encode('ascii', 'ignore'))    #gender place
                result.append(data[2].contents[0].encode('ascii', 'ignore'))    #div place
                result.append(data[5].contents[0].encode('ascii', 'ignore'))    #city
                result.append(data[0].contents[0].encode('ascii', 'ignore'))      #overall place
                result.append(data[6].contents[0].encode('ascii', 'ignore'))      #finish time
                results.append(result)       
                   
        

        out = open(event + '.csv', 'w')
        out.write("Name, Overall Place, Gender Place, Division Place, Finish Time, Bib Number, City/State \n")
        for r in results:
            out.write("%s, %s, %s, %s, %s, %s, %s \n" %(r[0],r[5],r[2],r[3],r[6],r[1],r[4]))


main()