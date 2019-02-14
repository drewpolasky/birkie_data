#this will scrape the data from the individual results pages, to get information about split times, etc



def main():
	eventIDs = {}
	year = 2016 
	eventIDs['birkie classic '+str(year)] = 2
	eventIDs['birkie skate '+str(year)] = 1
	eventIDs['kortie skate '+str(year)] = 3
	eventIDs['kortie classic '+str(year)] = 4
	eventIDs['prince haakon freestyle '+str(year)] = 5

	for event in eventIDs:
		resultsFile = open(event, 'r')
		header = resultsFile.readline().strip().split(',')
		for line in resultsFile:
			line = line.strip().split(',')
























if __name__ == '__main__':
	main()