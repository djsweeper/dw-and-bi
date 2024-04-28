# Creat Virtual Enveronment named its "ENV"
``` bash
python -m venv ENV
```

# Enter into ENV
``` bash
source ENV/bin/activate
```

# install requiement package with requirements.txt
``` bash
pip install -r requirements.txt
```

# Run ETL Script
## replace your credential name file on line 39 of etl_bigquery.py and replace project_id on line 45
``` bash
python etl_bigquery.py
```