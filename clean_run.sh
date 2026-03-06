sudo killall python
sudo rm -rf outputs/*
bash ./build_docker.sh
python src/reproduce_flakiness_docker.py $@
