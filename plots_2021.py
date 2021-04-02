#because 2021 was so weird because of covid, I'm figuring these plots won't be as useful for other years
import math
import sys
import datetime
import argparse
import os
import re

import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
import numpy as np


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--tech", type=str, default='skate')
	parser.add_argument("--length", type=str, default='birkie')
	parser.add_argument("--wave", type=int, default=1)
	parser.add_argument("--day", type=str, default='thursday')
	args = parser.parse_args()

	results_by_day(args.tech, args.length)


def results_by_day(tech, length, wave='all',dataloc='yearly_data/2021/'):
	#plot the finishing time for each day for a technique, for a single wave or for all waves
	days = {}
	for filename in os.listdir(dataloc):
		if re.search(length+' '+tech, filename):
			day_data = pd.read_csv(dataloc+filename)
			day_data['Chip Time'] = day_data['Chip Time'].replace('DNF', np.nan)
			day_data['Chip Time'] = pd.to_timedelta(day_data['Chip Time']).dt.total_seconds()

			if re.search('elite', filename):
				day = filename.split(' ')[-2]+filename.split(' ')[-1][:-4]
			else:
				day = filename.split(' ')[-1][:-4]

			day_data['day'] = day
			days[day] = day_data

	for day in days:
		#print(days[day]['Chip Time'])
		days[day]['Chip Time'].plot.kde(label=day)

	if length == 'birkie':
		if tech == 'skate':
			maxT = 23400    
			minT = 5000
		if tech == 'classic':
			maxT = 32000        
			minT = 7000
	elif length == 'kortie':
		if tech == 'skate':
			maxT = 14400
			minT = 3200
		if tech == 'classic':
			maxT = 21600
			minT = 4800
	plotTimes = {}

	x = np.linspace(minT, maxT, 200)
	plt.legend(prop = {'size':10})

	times = ["2:00", "2:30", "3:00", "3:30", "4:00", "4:30", "5:00", "5:30", "6:00", "6:30", "7:00","8:00","9:00"]
	xticksValues = [7200, 9000, 10800, 12600, 14400, 16200, 18000, 19800, 21600, 23400, 25200, 28800, 32400]
	plt.xticks(xticksValues, times)
	#plt.ylim([0,.0006])
	plt.ylabel("Frequency")
	plt.xlabel("Finishing times")
	plt.xlim([minT -200,maxT + 200])
	plt.grid(True)
	plt.title(length + " " + tech + " Finish Times by day")
	plt.savefig('graphs/'+length + "_" + tech + "_FinishTimesbyDay_2021.png")
	plt.show()






if __name__ == '__main__':
	main()