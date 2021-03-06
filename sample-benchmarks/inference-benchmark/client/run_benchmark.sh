#!/bin/bash
set -ex

model=${MODEL_NAME:?"Model name must be speficied"}

for i in $(seq 1 1000); do 
	curl -f -o /dev/null -s --write-out 'response_time:%{time_total}\n' -X POST http://${INFERENCE_SERVER_HOST}:${INFERENCE_SERVER_PORT}/predictions/${model} -T /data/kitten.jpg 
done
