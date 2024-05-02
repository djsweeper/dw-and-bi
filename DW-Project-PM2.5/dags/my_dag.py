import json
import glob
import os
import requests
import logging
from airflow import DAG
from airflow.utils import timezone
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.operators.empty import EmptyOperator
from airflow.providers.google.cloud.transfers.local_to_gcs import LocalFilesystemToGCSOperator
from bs4 import BeautifulSoup 
from urllib.parse import urlparse
from typing import List

def _get_files():
    url = "https://opendata.onde.go.th/dataset/14-pm-25"
    links = []
    req = requests.get(url, verify=False)
    req.encoding = "utf-8"
    soup = BeautifulSoup(req.text, 'html.parser')
    #print(soup.prettify())
    og = soup.find("meta",  property="og:url")
    base = urlparse(url)
    for link in soup.find_all('a'):
        current_link = link.get('href')
        if str(current_link).endswith('csv'):
            links.append(current_link)
    for link in links:
        names = link.split("/")[-1]
        names = names.strip()
        name = names.replace("pm_data_hourly-","")
        req = requests.get(link, verify=False)
        url_content = req.content
        file_p = "/opt/airflow/dags/" + name
        csv_file = open(name, "wb")
        csv_file.write(url_content)
        csv_file.close()
    print(os.listdir("/opt/airflow/dags/"))

with DAG(
    "sample",
    start_date=timezone.datetime(2024, 4, 30),
    schedule="@daily", #Cron expression
    tags=["project"],
    catchup=False,
) as dag:

    start = EmptyOperator(
        task_id="start",
    )

    get_files = PythonOperator(
        task_id = "get_files",
        python_callable = _get_files,
    )
    
    # upload_gcs = LocalFilesystemToGCSOperator(
    #     task_id = "upload_task",
    #     src = "/opt/airflow/dags/",
    #     dst = "gs://swu",
    #     bucket_name = "swu-ds-525-525",
    #     move_object=True,
    #     gcp_conn_id = "my_gcp_conn",
    #     mime_type = "text/csv"
    # )

    end = EmptyOperator(
        task_id="end",
    )

    
    start >> get_files >> end