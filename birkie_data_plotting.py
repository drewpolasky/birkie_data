#random scritps for playing with birkie results data
#python 2 - if using python 3, will have to change in int divides for bib -> wave number
import math
import matplotlib.pyplot as plt
from scipy import stats
import numpy
import sys
import datetime
from bisect import bisect


def main():
    #tech = sys.argv[1]
    #length = sys.argv[2]
    tech = "classic"      #skate or classic
    length = 'birkie'       #kortie or birkie 
    allResults = readIn(length, tech)
    #print(allResults)
    #resultsByYear(tech, length, allResults)
    #allResults = readIn(length, 'skate')
    #resultsByYear('skate', length, allResults)
    #resultsByWave(tech, length, allResults)
    getWavePlacement(allResults, 2019, tech,length,2, 'Andrew Polasky')

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
                print(wave)
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
        print(year, waveGaps)
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
    print(sum(threeGap) / float(len(threeGap)))

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
    if tech == 'skate':
        maxT = 28000    
        minT = 5000
    if tech == 'classic':
        maxT = 32000        
        minT = 7000
    plotTimes = {}
    for year in yearTimes:
        plotTimes[year] = stats.kde.gaussian_kde(yearTimes[year])
    print(maxT)

    x = numpy.linspace(minT, maxT, 200)
    for year in plotTimes:
        plt.plot(x,plotTimes[year](x), label = str(year)+ ' results', linewidth = 1.5 )
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

def getWavePlacement(allResults, year, tech, length, wave, skier):
    #get the placement of an indididual skier in a given wave. The skier does not have to have been in the specified wave
    if tech == 'classic' and wave <10:
        wave+=10
    waveTimes = []
    for racer in allResults[year]:
        bib = int(racer[5])
        racer_wave = bib / 1000
        if racer[0] == skier:
            targetTime = racer[4].strip(' ')
            targetTime = datetime.datetime.strptime(targetTime, '%H:%M:%S.%f').time()
            #print(targetTime)
        elif racer_wave == wave:
            waveTime = racer[4].strip(' ')
            waveTime = datetime.datetime.strptime(waveTime, '%H:%M:%S.%f')
            #print(waveTime.time().isoformat())
            waveTimes.append(waveTime.time())
    waveTimes = sorted(waveTimes) 
    place = bisect(waveTimes, targetTime)
    print('place in wave '+str(wave)+' for '+str(skier)+':') 
    print(place+1) 
    print('out of: ')
    print(len(waveTimes))       #if the wave is the wave the skier is in, this will be off by one

def parseTime(time):
    #deprecated in favor of datetime
    time = racer[4]
    time = time.split(':')
    hours = float(time[0])
    minutes = float(time[1])
    seconds = float(time[2][0:2])
    seconds += 3600 * hours + 60 * minutes
    return seconds


def readIn(distance, technique, path='yearly_data/', start_year = 2008, end_year=2019):
    years = list(range(start_year, end_year+1))
    years.remove(2017)      
    allResults = {}                 #data will be a dictonary with entries for each year. within each year there will be a list of lists, with each lowest level list containing all the elements scraped from the results website
    for year in years:
        yearResults = []
        event = distance + " " + technique + " " + str(year) + ".csv"
        try:    
            dataIn = open(path+event, 'r')
            for line in dataIn:
                l = line.split(',')
                if l[0] != "Name":
                    yearResults.append(l)
            allResults[year] = yearResults            
        except IOError:
            pass
    return allResults



main()