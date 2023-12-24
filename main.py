import csv
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, Response, BackgroundTasks
from fastapi.responses import JSONResponse
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import httpx
from typing import Dict
import uvicorn
import logging

logger = logging.getLogger("uvicorn")

# Load environment variables
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

app = FastAPI()
client = WebClient(token=os.environ['SLACK_TOKEN'])
BOT_ID = client.api_call("auth.test")['user_id']

message_counts: Dict[str, int] = {}

@app.post('/message-count')
async def message_count(channel_id: str = Form(...), user_id: str = Form(...)):
    count = message_counts.get(user_id, 0)
    try:
        client.chat_postMessage(channel=channel_id, text=f"Messages: {count}")
    except SlackApiError as e:
        error_message = e.response['error']
        return Response(content=f"Error uploading file: {error_message}", status_code=200)

    return Response(content='', status_code=200)

async def fetch_data_and_save_as_csv(table_name: str, filename: str):
    supabase_url = os.environ['SUPABASE_URL']
    supabase_key = os.environ['SUPABASE_KEY']
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}"
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{supabase_url}/rest/v1/{table_name}", headers=headers)
        data = response.json()
    csv_file = filename
    with open(csv_file, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    return csv_file

@app.post('/trips')
async def trips(background_tasks: BackgroundTasks, channel_id: str = Form(...)):
    logger.info(f"Received /trips command for channel {channel_id}")
    background_tasks.add_task(handle_trips, channel_id)
    return Response(content='', status_code=200)

async def handle_trips(channel_id: str):
    csv_file = await fetch_data_and_save_as_csv("trips", "trips.csv")
    try:
        result = client.files_upload(channels=channel_id, file=csv_file, filename='trips.csv')
        file_link = result['file']['permalink']
        client.chat_postMessage(channel=channel_id, text=f"Trips data: <{file_link}|Download CSV>")
    finally:
        if os.path.exists(csv_file):
            os.remove(csv_file)

@app.post('/users')
async def users(background_tasks: BackgroundTasks, channel_id: str = Form(...)):
    background_tasks.add_task(handle_users, channel_id)
    return Response(content='', status_code=200)

async def handle_users(channel_id: str):
    csv_file = await fetch_data_and_save_as_csv("users", "users.csv")
    try:
        result = client.files_upload(channels=channel_id, file=csv_file, filename='users.csv')
        file_link = result['file']['permalink']
        client.chat_postMessage(channel=channel_id, text=f"Users data: <{file_link}|Download CSV>")
    finally:
        if os.path.exists(csv_file):
            os.remove(csv_file)

@app.post('/commands')
async def commands():
    # List of all commands and their short descriptions
    commands_list = {
        "/trips": "provides a downloadable csv for all trips",
        "/users": "provides a downloadable csv for all users",
    }

    # Formatting the response message
    response_message = "\n".join([f"{cmd}: {desc}" for cmd, desc in commands_list.items()])

    # Preparing the payload for Slack
    payload = {
        "response_type": "ephemeral",  # Only the user who issued the command will see the response
        "text": "Here are the available commands:\n" + response_message
    }

    return JSONResponse(content=payload)

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
