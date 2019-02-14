#random code for palying with birkie results data
import math
import matplotlib.pyplot as plt
from scipy import stats
import numpy
import sys



def main():
    #tech = sys.argv[1]
    #length = sys.argv[2]
    tech = "skate"      #skate or classic
    length = 'birkie'       #kortie or birkie 
    allResults = readIn(length, tech)
    resultsByYear(tech, length, allResults)
    #allResults = readIn(length, 'skate')
    #resultsByYear('skate', length, allResults)
    resultsByWave(tech, length, allResults)

def resultsByWave(tech, length, allResults):
    waveTimes = {}
    threeGap = []
    for year in allResults:
        waves = {}
        for racer in allResults[year]:
            time = racer[4]
            time = time.split(':')
            hours = float(time[0])
            minutes = float(time[1])
            seconds = float(time[2][0:2])
            seconds += 3600 * hours + 60 * minutes  
            
            bib = int(racer[5])
            wave = bib / 1000
            
            if wave in waves:
                waves[wave].append(seconds)
            else:
                waves[wave] = [seconds]
        waveGaps = []
        prevWaveAvg = 0
        for wave in waves:    
            if len(waves[wave]) > 10:
                print wave 
                waveAvg = sum(waves[wave]) / float(len(waves[wave]))
                waveGap = math.floor(waveAvg - prevWaveAvg)
                if prevWaveAvg != 0:
                    waveGaps.append(waveGap)
                prevWaveAvg = waveAvg
                waveHist = stats.kde.gaussian_kde(waves[wave])
                if tech == 'skate':
                    maxT = 28000    
                    minT = 5000
                if tech == 'classic':
                    maxT = 32000        
                    minT = 7000
                x = numpy.linspace(minT, maxT, 200)
                plt.plot(x, waveHist(x), label = "Wave" + str(wave), linewidth = 1.5)
        print year, waveGaps
        if year != 2008 and year != 2016:
            threeGap.append(waveGaps[0])
        plt.legend(prop = {'size':10})
        plt.xlim([minT -200,maxT + 200])
        plt.ylim([0,.00065])
        plt.ylabel("Frequency")
        plt.xlabel("Finishing times")
        times = ["2:00", "2:30", "3:00", "3:30", "4:00", "4:30", "5:00", "5:30", "6:00", "6:30", "7:00"]
        xticksValues = [7200, 9000, 10800, 12600, 14400, 16200, 18000, 19800, 21600, 23400, 25200]
        plt.xticks(xticksValues, times)
        plt.title(length + " " + tech + " Finish Times by wave for " + str(year))
        if year == 2018:
            plt.savefig(length + " " + tech + " Finish Times by wave for " + str(year) + '.png')
            plt.show()
        else:
            plt.clf()
    print sum(threeGap) / float(len(threeGap))

def resultsByYear(tech, length, allResults):    #graphs histogram of results by year
    yearTimes = {}
    for year in allResults:
        times = []
        for racer in allResults[year]:
            time = racer[4]
            time = time.split(':')
            hours = float(time[0])
            minutes = float(time[1])
            seconds = float(time[2][0:2])
            seconds += 3600 * hours + 60 * minutes
            times.append(float(seconds))
        yearTimes[year] = times
    times2009 = stats.kde.gaussian_kde(yearTimes[2009])
    times2010 = stats.kde.gaussian_kde(yearTimes[2010])
    times2011 = stats.kde.gaussian_kde(yearTimes[2011])
    times2012 = stats.kde.gaussian_kde(yearTimes[2012])
    if tech == 'skate':
        maxT = 28000    
        minT = 5000
    if tech == 'classic':
        maxT = 32000        
        minT = 7000
    times2013 = stats.kde.gaussian_kde(yearTimes[2013])
    times2014 = stats.kde.gaussian_kde(yearTimes[2014])
    times2015 = stats.kde.gaussian_kde(yearTimes[2015])
    times2016 = stats.kde.gaussian_kde(yearTimes[2016])
    times2018 = stats.kde.gaussian_kde(yearTimes[2018])
    print maxT
    x = numpy.linspace(minT, maxT, 200)
    plt.plot(x,times2009(x), 'm-', label = '2009 results', linewidth = 1.5 )
    plt.plot(x,times2010(x), 'b-', label = '2010 results', linewidth = 1.5)
    plt.plot(x,times2011(x), 'r-', label = '2011 results', linewidth = 1.5 )
    plt.plot(x,times2012(x), 'g-', label = '2012 results', linewidth = 1.5 )
    plt.plot(x,times2013(x), 'y-', label = '2013 results', linewidth = 1.5 )
    plt.plot(x,times2014(x), 'c-', label = '2014 results', linewidth = 1.5 )
    plt.plot(x,times2015(x), 'k-', label = '2015 results', linewidth = 1.5 )
    plt.plot(x,times2016(x), 'v-', label = '2016 results', linewidth = 1.5 )
    plt.plot(x,times2018(x), 'r+', label = '2018 results', linewidth = 1.5 )
    plt.legend(prop = {'size':10})
    plt.xlim([minT -200,maxT + 200])
    times = ["2:00", "2:30", "3:00", "3:30", "4:00", "4:30", "5:00", "5:30", "6:00", "6:30", "7:00"]
    xticksValues = [7200, 9000, 10800, 12600, 14400, 16200, 18000, 19800, 21600, 23400, 25200]
    plt.xticks(xticksValues, times)
    plt.ylim([0,.00015])
    plt.ylabel("Frequency")
    plt.xlabel("Finishing times")
    plt.title(length + " " + tech + " Finish Times by year")
    plt.savefig(length + " " + tech + " Finish Times by year " + str(year) + '.png')
    plt.show()


def readIn(distance, technique):
    years = [2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2018]
    allResults = {}                 #data will be a dictonary with entries for each year. within each year there will be a list of lists, with each lowest level list containing all the elements scraped from the results website
    for year in years:
        yearResults = []
        event = distance + " " + technique + " " + str(year) + ".csv"
        try:    
            dataIn = open(event, 'r')
            for line in dataIn:
                l = line.split(',')
                if l[0] != "Name":
                    yearResults.append(l)
            allResults[year] = yearResults            
        except IOError:
            pass
    return allResults



main()