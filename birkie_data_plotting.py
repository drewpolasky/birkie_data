#random scritps for playing with birkie results data
import math
import argparse
import matplotlib.pyplot as plt
from scipy import stats
import numpy as np
import sys
import datetime
from bisect import bisect
import pandas as pd
from itertools import cycle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tech", type=str, default='skate')
    parser.add_argument("--length", type=str, default='birkie')
    parser.add_argument("--wave", type=int, default=1)
    parser.add_argument("--year", type=str, default='2025')
    parser.add_argument("--plot", type=str, default='byWave')
    parser.add_argument("--name", type=str, default='')
    args = parser.parse_args()

    allResults = readIn(args.length, args.tech)
    #print(allResults.keys())
    #resultsByYear(args.tech, args.length, allResults)
    #allResults = readIn(args.length, 'skate')
    if args.plot == 'byYear':
        resultsByYear(args.tech, args.length, allResults)
    elif args.plot == 'byWave':
        resultsByWave(args.tech, args.length, allResults, int(args.year))
    elif args.plot == 'wavePlacement': 
        getWavePlacement(allResults, int(args.year), args.tech,args.length,args.wave, args.name)
    elif args.plot == 'wave_gaps':
        wave_gaps(args.tech, args.length, allResults, int(args.year))

def resultsByWave(tech, length, allResults, plot_year):
    waveTimes = {}
    threeGap = []
    cutoffs = {'skate':{2023:[180,193,207,221,238,260,289,339],2020: [161,174,187,205,224,262], 2019:[191,210,227,244,268,304], 2018:[177,194,210,226,248,281], 2016:[181,199,215,231,254,288]}, 'classic':{2020:[227, 262, 302, 350], 2019:[257, 294, 328, 372], 2018:[251, 287, 326, 374]}}       #wave placement cutoff times, to the nearest minute
    for year in [plot_year]:
        waves = {}
        allResults[year]['times'] = allResults[year][' Finish Time'].dt.hour*3600 + allResults[year][' Finish Time'].dt.minute*60 + allResults[year][' Finish Time'].dt.second

        for index, row in allResults[year].iterrows(): #iterate over all skiers
            bib = int(row[' Bib Number'])
            wave = math.floor(bib / 1000)
            seconds = row['times']
            if not np.isnan(seconds):
                if wave in waves:
                    waves[wave].append(seconds)
                else:
                    waves[wave] = [seconds]
        waveGaps = []
        prevWaveAvg = 0
        order_waves = {wave:waves[wave] for wave in sorted(list(waves.keys()))}
        waves = order_waves
        for wave in waves:
            print(wave)
            if wave != 35:    
                if len(waves[wave]) > 10:
                    #print(wave)
                    waveAvg = sum(waves[wave]) / float(len(waves[wave]))
                    waveGap = math.floor(waveAvg - prevWaveAvg)
                    if prevWaveAvg != 0:
                        waveGaps.append(waveGap)
                    prevWaveAvg = waveAvg
                    waveHist = stats.kde.gaussian_kde(waves[wave])
                    if tech == 'skate':
                        maxT = 28000    
                        minT = 5000
                        if year == 2024:
                            maxT = 4*3600
                            minT = 3600
                    if tech == 'classic':
                        maxT = 32000        
                        minT = 7000
                    if year == 2024:
                        maxT = 4*3600
                        minT = 3600
                    x = np.linspace(minT, maxT, 200)
                    plt.plot(x, waveHist(x), label = "Wave" + str(wave), linewidth = 1.5)

        if year in cutoffs[tech]:
            for i in range(len(cutoffs[tech][year])):
                plt.axvline(cutoffs[tech][year][i]*60, linestyle = 'dashed')
        print(year, waveGaps)
        #if year != 2008 and year != 2016:
        #    threeGap.append(waveGaps[0])
        plt.legend(prop = {'size':10})
        plt.xlim([minT -200,maxT + 200])
        plt.ylim([0,.0006])
        plt.ylabel("Frequency")
        plt.xlabel("Finishing times")
        times = ["2:00", "2:30", "3:00", "3:30", "4:00", "4:30", "5:00", "5:30", "6:00", "6:30", "7:00", "7:30","8:00"]
        #times = ["1:00","1:30", "2:00", "2:30", "3:00", "3:30", "4:00"]
        xticksValues = [7200, 9000, 10800, 12600, 14400, 16200, 18000, 19800, 21600, 23400, 25200, 26000, 27800]
        #xticksValues = [3600, 5400, 7200, 9000, 10800, 12600, 14400]
        plt.xticks(xticksValues, times)
        plt.title(length + " " + tech + " Finish Times by wave for " + str(year))
        if year == plot_year:
            plt.grid(True)
            plt.savefig('graphs/' + length + "_" + tech + "FinishTimesbyWave_" + str(year) + '.png')
            plt.show()
        else:
            plt.clf()
    #print(sum(threeGap) / float(len(threeGap)))

def wave_gaps(tech, length, allResults, plot_year):
    #calculate the percent back between the waves over the years
    years = sorted(list(allResults.keys()))
    years.pop(3)
    waveGaps = {}
    for year in years:
        #print(year)
        waves = {}
        allResults[year]['times'] = allResults[year][' Finish Time'].dt.hour*3600 + allResults[year][' Finish Time'].dt.minute*60 + allResults[year][' Finish Time'].dt.second

        for index, row in allResults[year].iterrows(): #iterate over all skiers
            bib = int(row[' Bib Number'])
            wave = math.floor(bib / 1000)
            seconds = row['times']
            if not np.isnan(seconds):
                if wave in waves:
                    waves[wave].append(seconds)
                else:
                    waves[wave] = [seconds]

        prevWaveAvg = 0
        order_waves = {wave:waves[wave] for wave in sorted(list(waves.keys()))}
        waves = order_waves
        print(year, waves.keys())
        #for wave in [0,11,12,13,14,15]:
        for wave in [0,1,2,3,4,5,6]: 
            if wave not in [35, 70] and wave < 90:
                if len(waves[wave]) > 10:
                    waveAvg = sum(waves[wave]) / float(len(waves[wave]))
                    if prevWaveAvg != 0:
                        waveGap = math.floor(waveAvg - prevWaveAvg)/prevWaveAvg*100
                        wavePair = str(prevWave)+'-'+str(wave) 
                        if wavePair not in waveGaps:
                            waveGaps[wavePair] = [[],[]]
                        waveGaps[wavePair][0].append(year)
                        waveGaps[wavePair][1].append(waveGap)
                    prevWaveAvg = waveAvg
                    prevWave = wave
                    #print(year, wave, waveAvg)
    #print(waveGaps['11-12'][1])
    for wavePair in waveGaps: 
        plt.plot(waveGaps[wavePair][0], waveGaps[wavePair][1],label=wavePair)

    plt.title('Wave gaps by year '+' '.join([length, tech]))
    plt.ylabel('Percent difference between mean wave times')
    plt.legend(loc='center left', bbox_to_anchor=(1, 0.5))
    plt.grid(True)
    plt.tight_layout()
    plt.savefig('./graphs/wave_gaps_by_year_'+'_'.join([length, tech]))
    plt.show()
            
def resultsByYear(tech, length, allResults):    #graphs histogram of results by year
    for year in allResults:
        allResults[year]['times'] = allResults[year][' Finish Time'].dt.hour*3600 + allResults[year][' Finish Time'].dt.minute*60 + allResults[year][' Finish Time'].dt.second
    if tech == 'skate':
        maxT = 28000    
        minT = 5000
    if tech == 'classic':
        maxT = 32000        
        minT = 7000
    plotTimes = {}
    for year in allResults:
        results_array = allResults[year]['times'].dropna()
        plotTimes[year] = stats.kde.gaussian_kde(results_array)
    print(maxT)

    x = np.linspace(minT, maxT, 200)
    colors = plt.cm.jet(np.linspace(0, 1, len(allResults.keys())))
    line_styles = ['-', '--', '-.', ':']
    styles = []
    for i in range(len(allResults.keys())):
        styles.append((colors[i], line_styles[i%4]))
    combined_cycle = cycle(styles)

    for year in plotTimes:
        color, style = next(combined_cycle)
        plt.plot(x, plotTimes[year](x), label=str(year) + ' results', linewidth=1.5, color=color, linestyle=style)

    #for year in plotTimes:
    #    plt.plot(x,plotTimes[year](x), label = str(year)+ ' results', linewidth = 1.5 )
    plt.legend(prop = {'size':10})
    plt.xlim([minT -200,maxT + 200])
    times = ["2:00", "2:30", "3:00", "3:30", "4:00", "4:30", "5:00", "5:30", "6:00", "6:30", "7:00"]
    xticksValues = [7200, 9000, 10800, 12600, 14400, 16200, 18000, 19800, 21600, 23400, 25200]
    plt.xticks(xticksValues, times)
    plt.ylim([0,.00015])
    plt.ylabel("Frequency")
    plt.xlabel("Finishing times")
    plt.grid(True)
    plt.title(length + " " + tech + " Finish Times by year")
    plt.savefig('graphs/'+length + "_" + tech + "FinishTimesbyYear_" + str(year) + '.png')
    plt.show()

def getWavePlacement(allResults, year, tech, length, target_wave, skier):
    #get the placement of an indididual skier in a given wave. The skier does not have to have been in the specified wave, but does have to have skied that race in that year and in that technique
    if tech == 'classic' and target_wave <10:
        target_wave+=10
    waveTimes = []

    allResults[year]['times'] = allResults[year][' Finish Time'].dt.hour*3600 + allResults[year][' Finish Time'].dt.minute*60 + allResults[year][' Finish Time'].dt.second

    for index, row in allResults[year].iterrows(): #iterate over all skiers
        bib = int(row[' Bib Number'])
        wave = math.floor(bib / 1000)
        #print(skier.lower().strip(), row['Name'].lower().strip())
        if row['Name'].lower().strip() == skier.lower().strip():
            targetTime = row['times']
        elif target_wave == wave:
            waveTime = row['times']
            waveTimes.append(waveTime)
    waveTimes = sorted(waveTimes) 
    place = bisect(waveTimes, targetTime)
    print('place in wave '+str(target_wave)+' for '+str(skier)+':') 
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

def readIn(distance, technique, path='yearly_data/', start_year = 2009, end_year=2025):
    years = list(range(start_year, end_year+1))
    years.remove(2017) 
    years.remove(2021)
    years.remove(2024)          
    allResults = {}                 #data will be a dictonary with entries for each year. within each year there will be a list of lists, with each lowest level list containing all the elements scraped from the results website
    for year in years:
        #print(year)
        yearResults = []
        event = distance + " " + technique + " " + str(year) + ".csv"
        year_results = pd.read_csv(path+str(year)+'/'+event)
        if 'Time' in year_results.columns:
            year_results[' Finish Time'] = year_results['Time']
            year_results[' Bib Number'] = year_results['Bib']
            year_results['Name'] = year_results['Name'].str.split(',', expand=True)[1] + ' ' + year_results['Name'].str.split(',', expand=True)[0]
        try:
            year_results[' Finish Time'] = pd.to_datetime(year_results[' Finish Time'].str.strip(), format='%H:%M:%S.%f')
        except ValueError:
            year_results[' Finish Time'] = pd.to_datetime(year_results[' Finish Time'].str.strip().str.split(".").str[0], format='%H:%M:%S', errors='coerce')

        allResults[year] = year_results
    return allResults

def readIn_old(distance, technique, path='yearly_data/', start_year = 2010, end_year=2022):
    years = list(range(start_year, end_year+1))
    years.remove(2017) 
    years.remove(2021)          
    allResults = {}                 #data will be a dictonary with entries for each year. within each year there will be a list of lists, with each lowest level list containing all the elements scraped from the results website
    for year in years:
        yearResults = []
        event = distance + " " + technique + " " + str(year) + ".csv"
        try:    
            dataIn = open(path+str(year)+'/'+event, 'r')
            for line in dataIn:
                l = line.split(',')
                if l[0] != "Name":
                    yearResults.append(l)
            allResults[year] = yearResults            
        except IOError:
            pass
    return allResults

if __name__ == '__main__':
    main()
