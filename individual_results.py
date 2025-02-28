import math
import argparse
import matplotlib.pyplot as plt
from scipy import stats
import numpy as np
import sys
import datetime
from bisect import bisect
import pandas as pd

dists = ['birkie','kortie']
techs = ['skate','classic']

#Give the results for every year that someone has raced
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", type=str, default='')
    args = parser.parse_args()

    all_results = get_results()

    all_years_results = {}
    for dist in all_results:
        for tech in all_results[dist]:
            for year in all_results[dist][tech]:
                df = all_results[dist][tech][year]
                indiv_results = df[df['Name'].str.lower().str.replace(' ', '') == args.name.lower().replace(' ', '')]
                if  args.name.lower().replace(' ', '') =='drewpolasky':
                    indiv_results = pd.concat([indiv_results, df[df['Name'].str.lower().str.replace(' ', '') == 'andrewpolasky']])
                if len(indiv_results) > 0:
                    all_years_results['_'.join([dist,tech,str(year)])] = indiv_results
                    print(year, dist.capitalize(), tech.capitalize(), 'place:', indiv_results[' Overall Place'].values[0], 'out of', len(df), indiv_results[' Finish Time'].dt.strftime('%H:%M:%S').values[0])

    print_results(all_years_results, args.name)

def print_results(indiv, name):
    print("All Birkie/Kortie finishes for {}".format(name))
    print('Total Finishes: {}'.format(len(indiv)))
    nums = {}
    for finish in indiv:
        dist, tech, year = finish.split('_')    
        if dist+'_'+tech not in nums:
            nums[dist+'_'+tech] = 0
        nums[dist+'_'+tech] += 1
        #print(indiv[finish].columns)
        #print(year, dist.capitalize(), tech.capitalize(), indiv[finish][' Overall Place'].values[0], indiv[finish][' Finish Time'].dt.strftime('%H:%M:%S').values[0])
    for disttech in nums:
        dist, tech = disttech.split('_')
        num = nums[disttech]
        print("{} {} finishes: {}".format(dist.capitalize(), tech.capitalize(), num))


def get_results(path='yearly_data/', start_year = 2009, end_year=2025):
    years = list(range(start_year, end_year+1))
    years.remove(2017) 
    years.remove(2021)          
    allResults = {dist:{tech:{} for tech in techs} for dist in dists}                 #data will be a dictonary with entries for each year. within each year there will be a list of lists, with each lowest level list containing all the elements scraped from the results website
    for distance in dists:
        for technique in techs:
            for year in years:
                #print(year, distance, technique)
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
                if 'Ovr' in year_results.columns:
                    year_results[' Overall Place'] = year_results['Ovr']

                allResults[distance][technique][year] = year_results
    return allResults

if __name__ == '__main__':
    main()
