import json
import time
import os
from datetime import datetime
from config import RESPONSE_OUT

import pytz

try:
    from rich import print
except:
    pass
from generator import Generator
from stravalib.client import Client
from stravalib.exc import RateLimitExceeded


def adjust_time(time, tz_name):
    tc_offset = datetime.now(pytz.timezone(tz_name)).utcoffset()
    return time + tc_offset


def adjust_time_to_utc(time, tz_name):
    tc_offset = datetime.now(pytz.timezone(tz_name)).utcoffset()
    return time - tc_offset


def adjust_timestamp_to_utc(timestamp, tz_name):
    tc_offset = datetime.now(pytz.timezone(tz_name)).utcoffset()
    delta = int(tc_offset.total_seconds())
    return int(timestamp) - delta


def to_date(ts):
    # TODO use https://docs.python.org/3/library/datetime.html#datetime.datetime.fromisoformat
    # once we decide to move on to python v3.7+
    ts_fmts = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]

    for ts_fmt in ts_fmts:
        try:
            # performance with using exceptions
            # shouldn't be an issue since it's an offline cmdline tool
            return datetime.strptime(ts, ts_fmt)
        except ValueError:
            print(
                f"Warning: Can not execute strptime {ts} with ts_fmt {ts_fmt}, try next one..."
            )
            pass

    raise ValueError(f"cannot parse timestamp {ts} into date with fmts: {ts_fmts}")


def make_activities_file(sql_file, data_dir, json_file, file_suffix="gpx"):
    generator = Generator(sql_file)
    generator.sync_from_data_dir(data_dir, file_suffix=file_suffix)
    activities_list = generator.load()
    with open(json_file, "w") as f:
        json.dump(activities_list, f)


def make_strava_client(client_id, client_secret, refresh_token):
    client = Client()

    refresh_response = client.refresh_access_token(
        client_id=client_id, client_secret=client_secret, refresh_token=refresh_token
    )
    client.access_token = refresh_response["access_token"]
    return client


def get_strava_last_time(client, is_milliseconds=True):
    """
    if there is no activities cause exception return 0
    """
    try:
        activity = None
        activities = client.get_activities(limit=10)
        activities = list(activities)
        activities.sort(key=lambda x: x.start_date, reverse=True)
        # for else in python if you don't know please google it.
        for a in activities:
            if a.type == "Run":
                activity = a
                break
        else:
            return 0
        end_date = activity.start_date + activity.elapsed_time
        last_time = int(datetime.timestamp(end_date))
        if is_milliseconds:
            last_time = last_time * 1000
        return last_time
    except Exception as e:
        print(f"Something wrong to get last time err: {str(e)}")
        return 0


def upload_file_to_strava(client, file_name, data_type, force_to_run=True):
    with open(file_name, "rb") as f:
        try:
            if force_to_run:
                r = client.upload_activity(
                    activity_file=f, data_type=data_type, activity_type="run"
                )
            else:
                r = client.upload_activity(activity_file=f, data_type=data_type)

        except RateLimitExceeded as e:
            timeout = e.timeout
            print()
            print(f"Strava API Rate Limit Exceeded. Retry after {timeout} seconds")
            print()
            time.sleep(timeout)
            if force_to_run:
                r = client.upload_activity(
                    activity_file=f, data_type=data_type, activity_type="run"
                )
            else:
                r = client.upload_activity(activity_file=f, data_type=data_type)
        print(
            f"Uploading {data_type} file: {file_name} to strava, upload_id: {r.upload_id}."
        )

# 根据单条纪录的响应寄过生成对应的文件名
def keep_handler(response):
    s_type = response['data']['type']
    s_subtype = response['data']['subtype']
    s_time = response['data']['startTime']
    return f'{s_type}_{s_subtype}_{s_time}.json'

def codoon_handler(response):
    s_type = response['data']['activity_type']
    s_subtype = response['data']['sports_type']
    s_time = response['data']['StartDateTime']
    return f'{s_type}_{s_subtype}_{s_time}.json'

def joyrun_handler(response):
    s_type = response['runrecord']['type']
    s_time = response['runrecord']['starttime']
    return f'{s_type}_{s_time}.json'

def write_response(file_type):
    file_name_handler = None
    if file_type == "keep":
        file_name_handler = keep_handler
    elif file_type == "codoon":
        file_name_handler = codoon_handler
    elif file_type == "joyrun":
        file_name_handler = joyrun_handler
        
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                response = func(*args, **kwargs)
                if file_name_handler is None:
                    return response
                
                file_path = os.path.join(RESPONSE_OUT, file_type)
                file_name = file_name_handler(response)
                full_file_path = os.path.join(file_path, file_name)
                if not os.path.exists(file_path):
                    os.makedirs(file_path)
                response_json = json.dumps(response, indent=4)
                with open(full_file_path, "w") as fb:
                    fb.write(response_json)
                return response
            except Exception as e:
                print(f"Error: {str(e)}")
                return None
        return wrapper
    return decorator