sudo docker run -d \
--name ct-log-worker \
-e DEBUG=1 \
-e MANAGER_URL=http://192.168.0.137:1173 \
docker.io/kujiy/ct-worker:20250831-140949
