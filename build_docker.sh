for i in 11 12 13 14; do
  docker build --build-arg PY_VERSION=3.$i -t flakehunter:3.$i .
done
