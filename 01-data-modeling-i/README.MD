# Data Modeling I

## Install Library psycopg2
``` bash
pip install psycopg2
```

## Running Docker that contain Postgres service
``` bash
docker compose up
```

## Creat table by running python script
``` bash
python create_tables.py
```

## ETL the json file by runing python scropt
### make sure you put the json file in data folder
``` bash
python etl.py
```

## Shutdown Postgres service
``` bash
docker compose down
```