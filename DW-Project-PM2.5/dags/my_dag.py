import json
import glob
import os
import requests
import logging
import pickle
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account
from airflow import DAG
from airflow.utils import timezone
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.operators.empty import EmptyOperator
from airflow.providers.google.cloud.transfers.local_to_gcs import LocalFilesystemToGCSOperator
from airflow.providers.google.cloud.transfers.gcs_to_bigquery import GCSToBigQueryOperator
from bs4 import BeautifulSoup 
from urllib.parse import urlparse
from typing import List

def _get_files():
    exit_file_name = os.listdir('/opt/airflow/dags/data/')
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
        if (name != "data_dictionary.csv") & (name not in exit_file_name):
            req = requests.get(link, verify=False)
            url_content = req.content
            file_p = "/opt/airflow/dags/data/" + name
            csv_file = open(file_p, "wb")
            csv_file.write(url_content)
            csv_file.close()
            

# def _upload_to_gcs(data_folder,gcs_path,**kwargs):
#     data_folder = "/opt/airflow/dags/data/" # local dir
#     bucket_name = "swu-ds-525-525" # bucket name on GCS
#     gcs_conn_id = "my_scp_conn"
#     csv_files = [file for file in os.listdir(data_folder) if file.endswith(".csv")]
#     for csv_file in csv_files:
#         local_file_path = os.path.join(data_folder, csv_file)
#         gcs_file_path = f"{gcs_path}/{csv_file}"

#         upload_task = LocalFilesystemToGCSOperator(
#             task_id = f"upload_to_gcs",
#             src = local_file_path,
#             dst = gcs_file_path,
#             bucket = bucket_name,
#             gcp_conn_id = "my_scp_conn"
#         )
#         upload_task.execute(content=kwargs)
def _clean_df():
    column_names =  ['station_id', 'name_th', 'name_en', 'area_th', 'area_en',
       'station_type', 'lat', 'long', 'date', 'time', 'pm25_color_id',
       'pm25_aqi', 'pm25_value', 'Province', 'datetime']
    df_all = pd.DataFrame(columns = column_names)
    for name in os.listdir('/opt/airflow/dags/data/'):
        if name.endswith(".csv"):
            path = "/opt/airflow/dags/data/" +name
            df = pd.read_csv(path)
            area_en = []
            for area in df['area_en']:
                area = area.strip().split(",")[-1].strip()
                area_en.append(area)
            df['Province'] = area_en
            df['datetime'] = pd.to_datetime(df['date'] + " " + df['time'])
            df_all = pd.concat([df_all, df], axis=0, ignore_index=True)
            df_all.drop_duplicates(inplace=True)
            df_all.dropna(axis=1, inplace=True)
            df_all.to_csv("/opt/airflow/dags/data/all_data.csv", index=False)

# def _feed_to_bigq():
#     keyfile = "/opt/airflow/dags/credentials/admin.json"
#     service_account_info = json.load(open(keyfile))
#     credentials = service_account.Credentials.from_service_account_info(service_account_info)
#     project_id = "upbeat-task-421414"
#     client = bigquery.Client(
#         project=project_id,
#         credentials=credentials,
#     )
#     job_config = bigquery.LoadJobConfig(
#         schema=[
#             bigquery.SchemaField("int64_field_0", "INTEGER"),
#             bigquery.SchemaField("name_th", "STRING"),
#             bigquery.SchemaField("name_en", "STRING"),
#         ],
#         skip_leading_rows=1,
#         # The source format defaults to CSV, so the line below is optional.
#         source_format=bigquery.SourceFormat.CSV,#"PARQUET"
#     )
#     uri = "gs://dw-projec-swu-ds525/pm25_cleaned/all_data.csv"
#     load_job = client.load_table_from_uri(
#     uri, 'pm25.pm25_data', job_config=job_config
#     ) 
#     load_job.result()
#     destination_table = client.get_table('pm25.pm25_data')
# def replace_province_name(x):
#     return province_name.index(x)

def _transform_to_db():
    keyfile = "/opt/airflow/dags/credentials/admin.json"
    service_account_info = json.load(open(keyfile))
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    project_id = "upbeat-task-421414"
    df=pd.read_csv("gs://dw-projec-swu-ds525/pm25_cleaned/all_data.csv", storage_options={"token": keyfile})
    
    unique_province = df['Province'].unique()
    province_id = []
    province_name = []
    for i in range(len(unique_province)):
        province_id.append(i)
        province_name.append(unique_province[i])
    df_province = pd.DataFrame(data = {'Province_id': province_id, 'Province_name': province_name})
    df_station = df[['station_id', 'name_th', 'name_en', 'lat', 'long']]
    df_station.drop_duplicates(inplace=True)
    province_id = []
    for provin in list(df['Province']):
         province_id.append(province_name.index(provin))
    df['province_id'] = province_id
    df_need = df[['station_id', 'date', 'time', 'pm25_aqi', 'pm25_value', 'datetime', 'province_id']]
    client = bigquery.Client(project=project_id, credentials=credentials)
    dataset_ref = client.dataset('pm25')
    table_station = dataset_ref.table('station')
    table_province = dataset_ref.table('province')
    table_all_data = dataset_ref.table('data_transformed')
    job_config_station = bigquery.LoadJobConfig(
        schema = [
            bigquery.SchemaField("station_id", bigquery.enums.SqlTypeNames.STRING),
            bigquery.SchemaField("name_th", bigquery.enums.SqlTypeNames.STRING),
            bigquery.SchemaField("name_en", bigquery.enums.SqlTypeNames.STRING),
            bigquery.SchemaField("lat", bigquery.enums.SqlTypeNames.FLOAT),
            bigquery.SchemaField("long", bigquery.enums.SqlTypeNames.FLOAT),
        ],
        write_disposition="WRITE_TRUNCATE",

    )
    job_config_province =bigquery.LoadJobConfig(
        schema = [
            bigquery.SchemaField("Province_id", bigquery.enums.SqlTypeNames.INTEGER),
            bigquery.SchemaField("Province_name", bigquery.enums.SqlTypeNames.STRING),
        ],
        write_disposition="WRITE_TRUNCATE",
    )
    job_config_all_dat = bigquery.LoadJobConfig(
        schema = [
            bigquery.SchemaField("station_id", bigquery.enums.SqlTypeNames.STRING),
            bigquery.SchemaField("date", bigquery.enums.SqlTypeNames.STRING),
            bigquery.SchemaField("time", bigquery.enums.SqlTypeNames.STRING),
            bigquery.SchemaField("pm25_aqi", bigquery.enums.SqlTypeNames.INTEGER),
            bigquery.SchemaField("pm25_value", bigquery.enums.SqlTypeNames.FLOAT),
            bigquery.SchemaField("datetime", bigquery.enums.SqlTypeNames.STRING),
            bigquery.SchemaField("province_id", bigquery.enums.SqlTypeNames.INTEGER),
        ],
        write_disposition="WRITE_TRUNCATE",
    )
    client.load_table_from_dataframe(df_station, table_station, job_config=job_config_station).result()
    client.load_table_from_dataframe(df_province, table_province, job_config=job_config_province).result()
    client.load_table_from_dataframe(df_need, table_all_data, job_config=job_config_all_dat).result()

with DAG(
    "sample",
    start_date=timezone.datetime(2024, 4, 30),
    schedule="@hourly", #Cron expression
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

    data_folder = "/opt/airflow/dags/data/" # local dir
    gcs_path = "pm25_raw/"
    bucket_name = "dw-projec-swu-ds525" # bucket name on GCS
    path = []
    for csv_file in os.listdir(data_folder):
        if csv_file.endswith(".csv"):
            if csv_file != "all_data.csv":
                path.append(data_folder + csv_file)

    upload_to_gcs = LocalFilesystemToGCSOperator(
        task_id = "upload_to_gcs",
        src = path,
        dst = gcs_path,
        bucket = bucket_name,
        gcp_conn_id = "my_gcp_conn",
        mime_type = 'text/csv',
        ) 

    clean_df = PythonOperator(
        task_id = "clean_df",
        python_callable = _clean_df,
    )         
    
    upload_clean_to_gcs = LocalFilesystemToGCSOperator(
        task_id = "upload_clean_to_gcs",
        src = '/opt/airflow/dags/data/all_data.csv',
        dst = 'pm25_cleaned/',
        bucket = "dw-projec-swu-ds525",
        gcp_conn_id = "my_gcp_conn",
        mime_type = 'text/csv',
        ) 
    gcs_to_bq_station = GCSToBigQueryOperator(
        task_id='gcs_to_bq_station',
        bucket="dw-projec-swu-ds525",
        source_objects=['pm25_raw/*.csv'],
        destination_project_dataset_table='pm25.station',
        schema_fields=[
            {'name': 'station_id'  , 'type': 'STRING'},
            {'name': 'name_th'     , 'type': 'STRING'},
            {'name': 'name_en'     , 'type': 'STRING'},
            {'name': 'area_th'     , 'type': 'STRING'},
            {'name': 'area_en'     , 'type': 'STRING'},
            {'name': 'station_type', 'type': 'STRING'},
            {'name': 'lat'         , 'type': 'FLOAT'},
            {'name': 'long'        , 'type': 'FLOAT'},
            {'name': 'date'        , 'type': 'STRING'},
            {'name': 'time'        , 'type': 'STRING'},
            {'name': 'pm25_value'  , 'type': 'FLOAT'},
        ],
        create_disposition='CREATE_IF_NEEDED',
        write_disposition='WRITE_TRUNCATE',
        gcp_conn_id='my_gcp_conn',
        skip_leading_rows=1,
    )
    
    # feed_to_bigq = PythonOperator(
    #     task_id = "feed_to_bigq",
    #     python_callable = _feed_to_bigq,
    # )
    transform_to_db = PythonOperator(
        task_id = "transform_to_db",
        python_callable = _transform_to_db,
    )   

    end = EmptyOperator(
        task_id="end",
    )

    
    start >> get_files >> [upload_to_gcs, clean_df] >> upload_clean_to_gcs >> gcs_to_bq_station >> transform_to_db >> end