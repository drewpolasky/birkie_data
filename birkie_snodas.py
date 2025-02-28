import math
import argparse
import matplotlib.pyplot as plt
from scipy import stats
import numpy as np
import sys
import datetime
from bisect import bisect
import pandas as pd
import re
import pickle
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from matplotlib.ticker import FuncFormatter

from birkie_data_plotting import readIn
sys.path.append('/home/adp29/snowdas/')
from snowdas_data import load_data

#https://simplemaps.com/data/us-cities

def main():
	length = 'birkie'
	technique = 'skate'
	#data = readIn(length, technique)
	city_data = pd.read_csv('uscities.csv')
	city_data['compare_name'] = city_data['city'].str.lower().str.replace(" ", "")+','+city_data['state_id'].str.lower()
	#skiable_days_by_city(data)

	skiable_city_days = pickle.load(open('skiable_days_by_city.pickle', 'rb'))
	#region = [-100, -80, 40, 50]
	#region = [-125, -65, 26, 50]
	region = [-115, -100, 35, 44]
	plot_birkie_cities_skiable_days(skiable_city_days, city_data, region = region)

def plot_birkie_cities_skiable_days(skiable_city_days, city_data, region = [-125, -65, 26, 50]):
	fig = plt.figure(figsize=(10, 6))
	ax = plt.axes(projection=ccrs.PlateCarree())

	# Add country boundaries
	ax.add_feature(cfeature.BORDERS, linestyle='-')
	ax.add_feature(cfeature.COASTLINE)
	states = cfeature.NaturalEarthFeature(category='cultural', name='admin_1_states_provinces_lines',
                             scale='10m', facecolor='none', edgecolor='black')
	ax.add_feature(states, linestyle='-', linewidth=1, edgecolor='black')
	ax.coastlines(resolution='10m')
	# Add rivers and lakes
	#ax.add_feature(cfeature.RIVERS, edgecolor='blue')
	ax.add_feature(cfeature.LAKES)
	lats = []
	lons = []
	ski_days = []
	for city in skiable_city_days:
		city_info = city_data[city_data['compare_name']==city]
		if len(city_info) > 0:
			lats.append(city_info['lat'].values[0])
			lons.append(city_info['lng'].values[0])
			average_ski_days=0
			for i in range(len(skiable_city_days[city])):
				average_ski_days += skiable_city_days[city][i][1]
			average_ski_days = (average_ski_days/(i+1)).flatten()[0]
			ski_days.append(average_ski_days)

	max_ski_days = np.max(ski_days)
	norm = plt.Normalize(np.min(ski_days), np.max(ski_days))
	colors = plt.cm.viridis(norm(ski_days))
	scatter=ax.scatter(lons, lats, c=colors, cmap='viridis', marker='o', transform=ccrs.PlateCarree())
	ax.set_extent(region, crs=ccrs.PlateCarree())
	cbar = plt.colorbar(scatter, ax=ax, shrink=0.5)
	cbar.set_label('skiable days per year')
	cbar.ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: format_ticks(x, pos, max_ski_days)))
	plt.savefig('Skiable_days_cities.png')
	plt.show()

def format_ticks(x, pos, max_value):
    # Multiply the tick value by the fixed value
    new_value = x * max_value
    # Return the formatted tick label as a string
    return f'{new_value:.2f}'

def skiable_days_by_city(data):
	start_year = 2009
	domain = [-100, -86, 40, 50]
	snodas_data = load_data(start_year, lons = domain[0:2], lats = domain[2:], file_loc = '/home/adp29/snowdas/nc_files/')

	year_cities = {}
	for year in data:
		#print(year)
		if year in [2022, 2023]:
			cities, skiers = order_cities_2022_on(data, year)
		elif year in [i for i in range(2009,2016)]:
			cities, skiers = order_cities_pre_2009_2015(data, year)
		else:
			cities, skiers = order_cities_pre_2016_2020(data, year)
		cities = [city.replace(" ", "") for city in cities]
		year_cities[year] = [list(cities), list(skiers)]

	all_cities = []
	for year in year_cities:
		for city in year_cities[year][0]:
			if city not in all_cities:
				all_cities.append(city)
	skiable_days = cities_skiable_days(all_cities, snodas_data)
	with open('skiable_days_by_city.pickle', 'wb') as f:
		pickle.dump(skiable_days, f)
	#plot_cities(year_cities, ['minneapolis,mn','duluth,mn','madison,wi'])

def cities_skiable_days(cities, snodas_data):
	city_data = pd.read_csv('uscities.csv')
	city_data['compare_name'] = city_data['city'].str.lower().str.replace(" ", "")+','+city_data['state_id'].str.lower()
	city_ski_days = {}
	for city in cities:
		city_info = city_data[city_data['compare_name']==city]
		if len(city_info) > 0:
			print(city)
			#print(city_info)
			loc = [city_info['lat'].values, city_info['lng'].values]
			#print(loc)
			city_snow = snodas_data.sel(lat=loc[0],lon=loc[1],method='nearest')
			#print(city_snow)

			ski_threshold = 4	#in inches
			ski_threshold = ski_threshold * 25.4
			ski_days = city_snow['Band1'] > ski_threshold
			city_ski_days[city] = []
			for year in range(2009, 2023):
				year_ski_days = ski_days.sel(time=((ski_days['time.month'] >= 9) & (ski_days['time.year'] == year-1)) | ((ski_days['time.month'] < 3) & (ski_days['time.year'] == year))) 
				year_ski_days = year_ski_days.sum(dim='time')
				print(year, year_ski_days.values) 
				city_ski_days[city].append([year, year_ski_days.values])
			#input()
	return city_ski_days

def plot_cities(year_cities, cities):
	line_styles = ['solid', 'dotted', 'dashed']
	i = 0
	fig, ax1 = plt.subplots()
	ax2 = ax1.twinx()
	for city in cities:
		num_skiers = []
		average_place = []
		for year in year_cities:
			city_index = year_cities[year][0].index(city)
			city_skiers = year_cities[year][1][city_index]
			num_skiers.append([year, len(city_skiers)])
			#print(city_skiers)
			city_skiers = np.array(city_skiers)
			city_skiers = city_skiers[city_skiers!='DNF']
			city_skiers = city_skiers[city_skiers!='DSQ']
			city_skiers = np.array(city_skiers, dtype=float)
			average_place.append([year, np.nanmean(city_skiers)])
		num_skiers = np.array(num_skiers)
		average_place = np.array(average_place)
		#print(num_skiers)
		line1 = ax1.plot(num_skiers[:,0], num_skiers[:,1], label=city, color='b', linestyle=line_styles[i])
		line2 = ax2.plot(average_place[:,0], average_place[:,1], label=city, color='r',  linestyle=line_styles[i])
		i += 1

	plt.legend()
	ax1.set_yticklabels(ax1.get_yticks(), color=line1[0].get_color())
	ax2.set_yticklabels(ax2.get_yticks(), color=line2[0].get_color())
	ax1.set_ylabel('Number of Skiers', color='b')
	ax2.set_ylabel('Average Finish Place', color='r')
	plt.tight_layout()
	plt.savefig('citiesFinishersByYear.png')
	plt.show()

def order_cities_pre_2016_2020(data, year, verbose=0):
	cities = {}
	for index, row in data[year].iterrows():
		#print(row)
		place = str(row[' City'])
		#print(place)
		place = re.sub(' +', ' ', place)
		place = place.strip().split(' ')
		if year == 2020:
			place = place[:-1]+[place[-1][0:2]]+[place[-1][2:]]
		if len(place) > 3:
			place = [' '.join(place[:-2]), place[-2], place[-1]]
		place = [i.lower() for i in place]
		#print(place, row[' Overall Place'])
		#input()
		try:
			if place[2] in [' us', ' usa', 'us','usa']:
				citystate = ','.join(place[0:2])
				if citystate not in cities:
					cities[citystate] = []
				cities[citystate].append(row[' Overall Place'])
			else:
				if verbose > 1:
					print('excluding:', place)
		except IndexError:
			if verbose > 1:
				print('excluding:', place)

	#print('len cities: ', len(cities))
	cities, skiers = cities.keys(), cities.values()
	'''num_skiers = [len(skis) for skis in skiers]
	#average_place = [np.mean(skis) for skis in skiers]
	most_skiers, ordered_cities = zip(*sorted(zip(num_skiers, cities)))
	for i in range(len(most_skiers)):
		if most_skiers[i] > 20:
			print(ordered_cities[i], most_skiers[i])'''
	return cities, skiers
				
def order_cities_pre_2009_2015(data, year, verbose=0):
	cities = {}
	for index, row in data[year].iterrows():
		place = str(row[' City']) + str(row[' State '])
		place = place.strip().split(' ')
		place = [i.lower() for i in place]
		#print(place, row[' Overall Place'])
		try:
			if place[2] in [' us', ' usa', 'us','usa']:
				citystate = ','.join(place[0:2])
				if citystate not in cities:
					cities[citystate] = []
				cities[citystate].append(row[' Overall Place'])
		except IndexError:
			if verbose > 1:
				print('excluding:', place)

	#print('len cities: ', len(cities))
	cities, skiers = cities.keys(), cities.values()
	'''num_skiers = [len(skis) for skis in skiers]
	#average_place = [np.mean(skis) for skis in skiers]
	most_skiers, ordered_cities = zip(*sorted(zip(num_skiers, cities)))
	for i in range(len(most_skiers)):
		if most_skiers[i] > 20:
			print(ordered_cities[i], most_skiers[i])'''
	return cities, skiers

def order_cities_2022_on(data, year, verbose=0):
	cities = {}
	for index, row in data[year].iterrows():
		place = row['City, State, Nation']
		place = place.split(',')
		place = [i.lower() for i in place]
		#print(place)
		try:
			if place[2] in [' us', ' usa']:
				citystate = ','.join(place[0:2])
				if citystate not in cities:
					cities[citystate] = []
				cities[citystate].append(row['Ovr'])
		except IndexError:
			if verbose > 1:
				print('excluding:', place)

	#print(len(cities))
	cities, skiers = cities.keys(), cities.values()
	'''num_skiers = [len(skis) for skis in skiers]
	#average_place = [np.mean(skis) for skis in skiers]
	most_skiers, ordered_cities = zip(*sorted(zip(num_skiers, cities)))
	for i in range(len(most_skiers)):
		if most_skiers[i] > 20:
			print(ordered_cities[i], most_skiers[i])'''

	return cities, skiers


if __name__ == '__main__':
	main()