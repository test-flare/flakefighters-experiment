for i in '3.10' '3.11' '3.12' '3.13' '3.14'; do
  # docker build --build-arg PY_VERSION=3.$i -t flakehunter:3.$i .
  docker build --build-arg PY_VERSION=$i -t flakehunter:$i -f flakefighters-experiment/Dockerfile .
done
