sudo docker run -d \
--name ct-log-worker \
-e DEBUG=1 \
-e MANAGER_URL=http://192.168.0.185:1173 \
-e WORKER_NAME=chikuwa \
docker.io/kujiy/ct-worker:20250922-220351
