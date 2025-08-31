mysqldump -uroot -h mb-3.local ct \
  --single-transaction \
  --quick \
  --default-character-set=utf8mb4 | gzip > ct.`date +"%Y-%m-%d-%H-%M-%S"`.sql.gz
