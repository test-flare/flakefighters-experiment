# flakefighters-experiment
Replication package for our FlakeFighters tool paper.

## Setup
1. Clone this repo.
```
git clone https://github.com/test-flare/flakefighters-experiment.git --recursive
```
2. Ensure that the `home-assistant/core` repository is in this directory. If not, clone it.
```
git clone https://github.com/home-assistant/core.git 
```
2. Create a new virtual environment and install the dependencies:
```
virtualenv -p python3.11 --download venv
source venv/bin/activate
pip install -e .
```
3. Build the docker images:
```
bash build_docker.sh
```
4. Run the flakiness replication:
```
python src/reproduce_flakiness_docker.py
```
This will produce a folder called `outputs` which will store the run data for each test in a `.db` file and summary information in a `.json` file.
> [!NOTE]
> This will take a long time to run and require a lot of memory.
> Our results are already in the "ouputs" directory.
> Unless you explicitly want to confirm the flaky tests, we recommend you skip this step and process the results directly.

5. Process the results:
```
python src/results_processing.json
```
This will produce a file called `results.csv` which will contain a summary of the results.

# Collecting test runs
The test runs we used for our paper are contained in `home_assistant_flakes_dev.json`.
If you wish to collect more data in a similar format, run `python src/pr_scraper.py`.
This will overwrite the existing `home_assistant_flakes_dev.json` file with new data on the latest failed CI runs.

> [!NOTE]
> To do this, you will need a [GitHub API key](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).
> You will need to put this in a `.env` file in the root of this repo:
> ``` GITHUB_TOKEN=YOUR_TOKEN ```
