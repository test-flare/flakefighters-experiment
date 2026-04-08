# flakefighters-experiment
Replication package for our FlakeFighters tool paper.

## Setup
1. Clone this repo.
2. Create a new virtual environment.
```
virtualenv -p python3.11 --download venv
source venv/bin/activate
```
3. Build the docker images.
```
bash build_docker.sh
```
4. Run the flakiness replication.
```
python src/reproduce_flakiness_docker.py
```
