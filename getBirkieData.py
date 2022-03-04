#to scrape birkie results data from the searchable results
#event ids:
#2015 birkie skate: 114
#2015 birkie classic: 115
#2015 kortie skate: 112
#2015 kortie classic: 113
#2015 prince haakon: 110

from lxml import html
from lxml import etree
import requests
from bs4 import BeautifulSoup
from urllib.request import urlopen
from selenium import webdriver
import time
import re
import pandas as pd

def main():
    #get_searchable_results()
    get_2022_data()

def get_searchable_results():
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
        print(event)
        eventID = eventIDs[event]
        print(eventID)
        page = BeautifulSoup.BeautifulSoup(urllib2.urlopen('http://results.birkie.com/index.php?event_id=' + str(eventID)).read())
        tables = page.findAll("tbody")
        print(tables)
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
        print(results[0])       

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

def get_2022_data():
    #and once again, they compeletely changed the formatting of the results, meaning new code is needed
    #link: skate: https://my.raceresult.com/189471/results#10_3C2D41
    eventIDs = eventIds_2022()

    for event in eventIDs:
        results = []
        print(event)
        eventID = eventIDs[event]
        #print(eventID)
        driver = webdriver.Firefox()
        driver.get('https://my.raceresult.com/189471/'+str(eventID))
        time.sleep(2)       #seems to take a couple seconds sometimes for the showall button to come up
        ids = driver.find_elements_by_xpath('//*[@id]')
        
        #for ii in ids:
        #    print(ii.get_attribute('id'))    # id name as string
        driver.find_element_by_id("cookieChoiceDismiss").click()
        elements = driver.find_elements_by_css_selector(".aShowAll")
        elements[-1].click()  #click the show all results button to get everyone on one page

        table = driver.find_element_by_id("tb_1Data")
        time.sleep(2)
        #driver.find_element_by_class_name("aShowAll").click()
        table_html = table.get_attribute('innerHTML')
        tree = etree.HTML(table_html)
        header = [ 'Ovr', 'Sex', 'Div', 'Bib', 'Name', 'City, State, Nation', 'Age', 'Gender', 'Time', 'Pace']
        results = []
        for page in iter(tree):
            for skier in page:
                result = []
                for element in skier:
                    result.append(element.text)
                result = result[1:-1]
                results.append(result)

        day_frame = pd.DataFrame(results, columns=header)
        day_frame.to_csv('yearly_data/2022/'+event+'.csv')
        driver.quit()


def get_2021_data():
    #the 2021 data is (at least currently) in a different format from the previous year, so will need new code for scraping.
    #there's also the added complication of the different days results, due to COVID
    #https://runsignup.com/Race/Results/107357#resultSetId-239900;perpage:5000
    #https://runsignup.com/Race/Results/107357#resultSetId-239915;perpage:5000
    eventIDs = eventIds_2021()

    for event in eventIDs:
        results = []
        print(event)
        eventID = eventIDs[event]
        #print(eventID)
        driver = webdriver.Firefox()
        driver.get('https://runsignup.com/Race/Results/107357#resultSetId-' + str(eventID)+';perpage:5000')
        table = driver.find_element_by_id('resultsTable')
        time.sleep(5)
        table_html = table.get_attribute('innerHTML')

        tree = etree.HTML(table_html)
        header = [element.text for element in tree[0][0][0]]
        #print(header)
        day_results = []

        for row in iter(tree[0][1]):
            entry = [element.text for element in row]

            #I think because of the name formatting in the table, the names aren't coming through, so working around with regex
            firstName = re.findall(r'firstName(.*?)<', etree.tostring(row).decode('utf-8'))[0][2:]
            lastName = re.findall(r'lastName(.*?)<', etree.tostring(row).decode('utf-8'))[0][2:]

            entry[2] = firstName+' '+lastName
            day_results.append(entry)

        day_frame = pd.DataFrame(day_results, columns=header)
        day_frame.to_csv('yearly_data/2021/'+event+'.csv')
        driver.quit()

def eventIds_2021():
    eventIDs = {}
    eventIDs['birkie classic 2021 sunday elite'] = 239915
    eventIDs['birkie classic 2021 sunday'] = 239914
    eventIDs['kortie classic 2021 sunday elite'] = 239917
    eventIDs['kortie classic 2021 sunday'] = 239916
    eventIDs['haakon classic 2021 sunday'] = 239918

    eventIDs['birkie skate 2021 saturday elite'] = 239901
    eventIDs['birkie skate 2021 saturday'] = 239911
    eventIDs['kortie skate 2021 saturday elite'] = 239903
    eventIDs['kortie skate 2021 saturday'] = 239912
    eventIDs['haakon skate 2021 saturday'] = 239913

    eventIDs['birkie classic 2021 friday'] = 239908
    eventIDs['kortie classic 2021 friday'] = 239909
    eventIDs['haakon classic 2021 friday'] = 239910

    eventIDs['birkie skate 2021 thursday'] = 239905
    eventIDs['kortie skate 2021 thursday'] = 239906
    eventIDs['haakon skate 2021 thursday'] = 239907

    eventIDs['birkie skate 2021 wednesday'] = 239900
    eventIDs['kortie skate 2021 wednesday'] = 239902
    eventIDs['haakon skate 2021 wednesday'] = 239904

    return eventIDs

def eventIds_2022():
    eventIDs = {}
    eventIDs['birkie classic 2022'] = "#11_C0D558"
    eventIDs['kortie classic 2022'] = "#8_1706C5"

    eventIDs['birkie skate 2022'] = "#10_3C2D41"
    eventIDs['kortie skate 2022'] = "#7_9C7CB5"
    eventIDs['haakon skate 2022'] = "#9_5D9B23"

    return eventIDs

main()