Birkie and Kortie results and some plots

Example usage:
python birkie_data_plotting.py  --tech skate --length birkie --plot byWave


Linking skiers from year to year:

python athlete_linking.py                         writes linked_data/linked_results.csv and linked_data/athletes.csv
python athlete_linking.py --name "drew polasky"   prints one skier's linked history

`results_loader.py` reads every file in yearly_data/ (four different formats since 2009) into one table.
`athlete_linking.py` gives each result an `athlete_id`. There are no ids in the results, so it matches on name
(with nicknames like Drew/Andrew), birth year (age group 2016-2020, exact age 2021+), gender, middle initial
(2009-2014) and hometown, and never on finish times. Each result also gets a `link_score` (log odds of its strongest
link) and `name_shared` (how many athletes share that exact name), to filter out shakier links in an analysis.


Year to year performance changes:

python performance_changes.py --race birkie --tech skate                        writes graphs/birkie_skate_year_to_year.png
python performance_changes.py --race birkie --tech skate --name "drew polasky"  also plots one skier, adjusted for conditions

`performance_changes.py` models log(finish time) as the skier's ability + that race's conditions + age + experience,
fit within the same skiers from year to year. Age is held flat from 25 to 35 and learning is assumed done by the 5th
race, which is what lets conditions and aging be told apart. 2024 (short course) and the open track are left out.

![Image](https://github.com/drewpolasky/birkie_data/blob/master/graphs/birkie_skate_year_to_year.png?raw=true)


Birkie Skate finish times by year: 

![Image](https://github.com/drewpolasky/birkie_data/blob/master/graphs/birkie_skateFinishTimesbyYear_2026.png?raw=true)

Birkie Skate Waves 2026: 

![Image](https://github.com/drewpolasky/birkie_data/blob/master/graphs/birkie_skateFinishTimesbyWave_2026.png?raw=true)

Birkie Classic by year: 

![Image](https://github.com/drewpolasky/birkie_data/blob/master/graphs/birkie_classicFinishTimesbyYear_2026.png?raw=true)

Birkie Classic Waves 2026: 

![Image](https://github.com/drewpolasky/birkie_data/blob/master/graphs/birkie_classicFinishTimesbyWave_2026.png?raw=true)














