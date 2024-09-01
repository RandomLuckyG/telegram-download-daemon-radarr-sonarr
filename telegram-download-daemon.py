#!/usr/bin/env python3
# Telegram Download Daemon
# Author: Alfonso E.M. <alfonso@el-magnifico.org>
# You need to install telethon (and cryptg to speed up downloads)

import asyncio
import argparse
import multiprocessing
from os import getenv, path
from shutil import move
import time
import random
import string
import os.path
import re


from sessionManager import getSession, saveSession

from telethon import TelegramClient, events, __version__
from telethon.tl.types import PeerChannel, DocumentAttributeFilename, DocumentAttributeVideo
import logging

logging.basicConfig(format='[%(levelname) 5s/%(asctime)s]%(name)s:%(message)s',
                    level=logging.WARNING)


TDD_VERSION = "1.14"

TELEGRAM_DAEMON_API_ID = getenv("TELEGRAM_DAEMON_API_ID")
TELEGRAM_DAEMON_API_HASH = getenv("TELEGRAM_DAEMON_API_HASH")
TELEGRAM_DAEMON_CHANNEL = getenv("TELEGRAM_DAEMON_CHANNEL")

TELEGRAM_DAEMON_SESSION_PATH = getenv("TELEGRAM_DAEMON_SESSION_PATH")

TELEGRAM_DAEMON_MOVIES_DEST = getenv("TELEGRAM_DAEMON_MOVIES_DEST", "/movies")
TELEGRAM_DAEMON_TVSHOWS_DEST = getenv(
    "TELEGRAM_DAEMON_TVSHOWS_DEST", "/tvshows")
TELEGRAM_DAEMON_TEMP = getenv("TELEGRAM_DAEMON_TEMP", "/downloads")
TELEGRAM_DAEMON_DUPLICATES = getenv("TELEGRAM_DAEMON_DUPLICATES", "rename")

TELEGRAM_DAEMON_TEMP_SUFFIX = "tdd"

TELEGRAM_DAEMON_WORKERS = getenv(
    "TELEGRAM_DAEMON_WORKERS", multiprocessing.cpu_count())

parser = argparse.ArgumentParser(
    description="Script to download files from a Telegram Channel to Sonarr/Radarr.")
parser.add_argument(
    "--api-id",
    required=TELEGRAM_DAEMON_API_ID == None,
    type=int,
    default=TELEGRAM_DAEMON_API_ID,
    help='api_id from https://core.telegram.org/api/obtaining_api_id (default is TELEGRAM_DAEMON_API_ID env var)'
)
parser.add_argument(
    "--api-hash",
    required=TELEGRAM_DAEMON_API_HASH == None,
    type=str,
    default=TELEGRAM_DAEMON_API_HASH,
    help='api_hash from https://core.telegram.org/api/obtaining_api_id (default is TELEGRAM_DAEMON_API_HASH env var)'
)

parser.add_argument(
    "--moviesdest",
    type=str,
    default=TELEGRAM_DAEMON_MOVIES_DEST,
    help='Destination path for Radarr media files (default is /movies).')

parser.add_argument(
    "--tvshowsdest",
    type=str,
    default=TELEGRAM_DAEMON_TVSHOWS_DEST,
    help='Destination path for Sonarr media files (default is /tvshows).')
parser.add_argument(
    "--temp",
    type=str,
    default=TELEGRAM_DAEMON_TEMP,
    help='Destination path for temporary files (default is /downloads).')
parser.add_argument(
    "--channel",
    required=TELEGRAM_DAEMON_CHANNEL == None,
    type=int,
    default=TELEGRAM_DAEMON_CHANNEL,
    help='Channel id to download from it (default is TELEGRAM_DAEMON_CHANNEL env var)'
)
parser.add_argument(
    "--duplicates",
    choices=["ignore", "rename", "overwrite"],
    type=str,
    default=TELEGRAM_DAEMON_DUPLICATES,
    help='"ignore"=do not download duplicated files, "rename"=add a random suffix, "overwrite"=redownload and overwrite.'
)
parser.add_argument(
    "--workers",
    type=int,
    default=TELEGRAM_DAEMON_WORKERS,
    help='number of simultaneous downloads'
)
args = parser.parse_args()

api_id = args.api_id
api_hash = args.api_hash
channel_id = args.channel
moviesDest = args.moviesdest
tvshowsDest = args.tvshowsdest
tempFolder = args.temp
duplicates = args.duplicates
worker_count = args.workers
updateFrequency = 10
lastUpdate = 0


# Edit these lines:
proxy = None

# End of interesting parameters


async def sendHelloMessage(client, peerChannel):
    entity = await client.get_entity(peerChannel)
    print("Telegram Download Daemon "+TDD_VERSION+" using Telethon "+__version__)
    print("  Simultaneous downloads:"+str(worker_count))
    await client.send_message(entity, "Telegram Download Daemon "+TDD_VERSION+" using Telethon "+__version__+"\nMod By RandomLuckyGuy")


async def log_reply(message, reply):
    await message.edit(reply)


def getRandomId(len):
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for x in range(len))


def fix_year_format(input_str):
    tvshow_check = re.search(
        r'-\s*S(\d{1,5})E(\d{1,5})$', input_str, re.IGNORECASE)
    if not tvshow_check:
        input_str += " "
    match_with_parentheses = re.search(r' \((\d{4})\) ', input_str)
    if match_with_parentheses:
        output = input_str
    match_without_parentheses = re.search(r' (\d{4}) ', input_str)
    if match_without_parentheses:
        year = match_without_parentheses.group(1)
        output = re.sub(r'(\d{4})', f'({year})', input_str)
    match_parentheses_left = re.search(r' \((\d{4}) ', input_str)
    if match_parentheses_left:
        year = match_parentheses_left.group(1)
        output = re.sub(r'(\d{4})', f'{year})', input_str)
    match_parentheses_right = re.search(r' (\d{4})\) ', input_str)
    if match_parentheses_right:
        year = match_parentheses_right.group(1)
        output = re.sub(r'(\d{4})', f'({year}', input_str)
    if output:
        return output.strip(" ")
    else:
        raise ValueError("Couldn't Process String")


def getFilename(event: events.NewMessage.Event):
    mediaFileName = "unknown"

    if hasattr(event.media, 'photo'):
        mediaFileName = str(event.media.photo.id)+".jpeg"
    elif hasattr(event.media, 'document'):
        for attribute in event.media.document.attributes:
            if isinstance(attribute, DocumentAttributeFilename):
                mediaFileName = attribute.file_name
                break
    mediaFileName = "".join(
        c for c in mediaFileName if c.isalnum() or c in "()._- ")
    return mediaFileName


in_progress = {}


async def set_progress(filename, message, received, total, current_tv_show):
    global lastUpdate
    global updateFrequency

    if received >= total:
        try:
            in_progress.pop(filename)
        except:
            pass
        return

    percentage = (received / total) * 100
    progress_length = 10
    filled_length = int((percentage / 100) * progress_length)
    progress_message = 'Downloading..\n' + current_tv_show + '\n' + filename + '\n' + \
        '[' + '█' * filled_length + '░' * \
        (progress_length - filled_length) + \
        ']' + str(round(percentage, 2)) + '%'

    in_progress[filename] = progress_message

    currentTime = time.time()
    if (currentTime - lastUpdate) > updateFrequency:
        await log_reply(message, progress_message)
        lastUpdate = currentTime

temp = {}

with TelegramClient(getSession(), api_id, api_hash,
                    proxy=proxy).start() as client:

    saveSession(client.session)

    queue = asyncio.Queue()
    peerChannel = PeerChannel(channel_id)

    @client.on(events.NewMessage())
    async def handler(event):
        global temp

        if event.to_id != peerChannel:
            return

        try:
            if event.media and (hasattr(event.media, 'document') or hasattr(event.media, 'photo')):
                filename = getFilename(event)
                print(filename)
                if path.exists(f"{tempFolder}/{filename}.{TELEGRAM_DAEMON_TEMP_SUFFIX}") and duplicates == "ignore":
                    message = await event.reply(f"{filename} is already downloading. Ignoring it.")
                else:
                    temp.clear()
                    temp['filename'] = filename
                    temp['event'] = event
                    message = await event.reply("Please, Provide The File Data.")
            else:
                command = event.message.message
                output = "Unknown command"
                if re.search(r'(\d{4})', command) and len(temp.keys()) == 2 and len(command) > 4:
                    try:
                        tvshow_match = re.match(
                            r'^([^\{\}\(\)]*)\s*\((\d{4})\)\s*-\s*S(\d{1,5})E(\d{1,5})$', fix_year_format(command), re.IGNORECASE)
                        movie_match = re.match(
                            r'^(.+) \((\d{4})\)$', fix_year_format(command), re.IGNORECASE)
                    except:
                        output = "Error, Send File Data Again"

                    if tvshow_match and not movie_match:
                        try:
                            temp['data'] = {"title": tvshow_match.group(1).strip(" "), "year": int(tvshow_match.group(
                                2)), "season": tvshow_match.group(3).zfill(2), "episode": tvshow_match.group(4).zfill(2), "type": "tvshow"}
                            output = f"The Tv Show Will Be Renamed to {command}"
                        except:
                            output = "Error, Send File Data Again"
                    elif movie_match and not tvshow_match:
                        try:
                            temp['data'] = {"title": movie_match.group(1).strip(
                                " "), "year": int(movie_match.group(2)), "type": "movie"}
                            output = f"The Movie Will Be Renamed to {command}"
                        except:
                            output = "Error, Send File Data Again"
                    else:
                        output = "Error, Send File Data Again"

                    if temp.get('event', -1) != -1 and temp.get('data', -1) != -1:
                        message = await event.reply(f"{temp['filename']} Added To Queue")
                        await queue.put([temp['event'], message, temp['data']])
                        temp.clear()
                    else:
                        output = "Error, Send File Data Again"

                elif len(temp.keys()) == 2 and temp.get('data', -1) == -1 and command != '/cancel':
                    output = "Error, Send File Data Again"

                elif command == "/cancel":
                    try:
                        temp.clear()
                        if len(temp.keys()) == 0:
                            output = "Current Operation Canceled."
                    except:
                        output = "Some error occurred while canceling current operation. Retry."
                elif command == "/status":
                    try:
                        output = "".join([f"{value}\n\n" for (
                            key, value) in in_progress.items()])
                        if output:
                            output = "Active downloads:\n\n" + output
                        else:
                            output = "No active downloads"
                    except:
                        output = "Some error occurred while checking the status. Retry."
                elif command == "/clean":
                    try:
                        [os.remove(temp_folder_path) for temp_folder_path in [os.path.join(root, file) for root, dirs, files in os.walk(
                            tempFolder) for file in files] if temp_folder_path.endswith('.tdd')]
                        output = "Successfully Cleaned Temp Folder"
                    except:
                        output = f"Error Cleaning Temp Folder"
                elif command == "/queue":
                    try:
                        files_in_queue = []
                        for q in queue.__dict__['_queue']:
                            files_in_queue.append(q[2])
                        output = "".join(
                            [f"{filename}\n" for (filename) in files_in_queue])
                        if output:
                            output = "Files in queue:\n\n" + output
                        else:
                            output = "Queue is empty"
                    except:
                        output = "Some error occurred while checking the queue. Retry."
                else:
                    output = "First Send A File.\nAvailable commands: /cancel, /status, /clean, /queue"

                await log_reply(event, output)

        except Exception as e:
            output = "Error, Send File Data Again"
            await log_reply(event, output)
            print('Events handler error: ', e)

    async def worker():
        while True:
            try:
                element = await queue.get()
                event = element[0]
                message = element[1]
                file_data = element[2]
                if file_data['type'] == "tvshow":
                    tvshow_data = f"{file_data['title']} ({file_data['year']}) - S{file_data['season']}E{file_data['episode']}"
                    tvshow_folder_name = f"{file_data['title']} ({file_data['year']})"
                    tvshow_season_folder = f"Season {int(file_data['season'])}"
                    new_tvshow_filename = f"{file_data['title']} - S{file_data['season']}E{file_data['episode']}"

                if file_data['type'] == "movie":
                    movie_data = f"{file_data['title']} ({file_data['year']})"

                filename = getFilename(event)
                fileName, fileExtension = os.path.splitext(filename)
                tempfilename = fileName+"-"+getRandomId(8)+fileExtension

                if path.exists(f"{tempFolder}/{filename}.{TELEGRAM_DAEMON_TEMP_SUFFIX}") and duplicates == "rename":
                    filename = tempfilename

                if hasattr(event.media, 'photo'):
                    size = 0
                else:
                    size = event.media.document.size

                await log_reply(
                    message,
                    f"Downloading file\n{filename} - {size} bytes"
                )
                if file_data['type'] == "tvshow":
                    def download_callback(received, total): return set_progress(
                        filename, message, received, total, tvshow_data)

                    await client.download_media(event.message, f"{tempFolder}/{filename}.{TELEGRAM_DAEMON_TEMP_SUFFIX}", progress_callback=download_callback)
                    set_progress(filename, message, 100, 100, tvshow_data)
                    #  check if tvshow folder exists, else creates folder
                    tvshow_folder_path = os.path.join(
                        tvshowsDest, tvshow_folder_name)
                    if not os.path.exists(tvshow_folder_path):
                        os.makedirs(tvshow_folder_path)
                    # check if tvshow sesson folder exists, else creates sesson folder
                    tvshow_season_folder_path = os.path.join(
                        tvshowsDest, tvshow_folder_name, tvshow_season_folder)
                    if not os.path.exists(tvshow_season_folder_path):
                        os.makedirs(tvshow_season_folder_path)
                    # Move the file into the specific folder with the new filename
                    await log_reply(message, f"Moving..\n {tvshow_data} > {tvshowsDest} ")
                    move(f"{tempFolder}/{filename}.{TELEGRAM_DAEMON_TEMP_SUFFIX}",
                         f"{tvshowsDest}/{tvshow_folder_name}/{tvshow_season_folder}/{new_tvshow_filename+fileExtension.lower()}")
                    while not os.path.exists(f"{tvshowsDest}/{tvshow_folder_name}/{tvshow_season_folder}/{new_tvshow_filename+fileExtension}"):
                        pass
                    # give permissions to files
                    os.chmod(f"{tvshowsDest}/{tvshow_folder_name}", 0o777)
                    os.chmod(
                        f"{tvshowsDest}/{tvshow_folder_name}/{tvshow_season_folder}", 0o777)
                    os.chmod(
                        f"{tvshowsDest}/{tvshow_folder_name}/{tvshow_season_folder}/{new_tvshow_filename+fileExtension}", 0o777)
                    await log_reply(message, f"{tvshow_data}\nDownloaded Successfully")
                    queue.task_done()

                if file_data['type'] == "movie":
                    def download_callback(received, total): return set_progress(
                        filename, message, received, total, movie_data)

                    await client.download_media(event.message, f"{tempFolder}/{filename}.{TELEGRAM_DAEMON_TEMP_SUFFIX}", progress_callback=download_callback)
                    set_progress(filename, message, 100, 100, movie_data)
                    #  check if tvshow folder exists, else creates folder
                    folder_path = os.path.join(moviesDest, movie_data)
                    if not os.path.exists(folder_path):
                        os.makedirs(folder_path)
                    # Move the file into the specific folder with the new filename
                    await log_reply(message, f"Moving..\n {movie_data} > {moviesDest} ")
                    move(f"{tempFolder}/{filename}.{TELEGRAM_DAEMON_TEMP_SUFFIX}",
                         f"{moviesDest}/{movie_data}/{movie_data+fileExtension.lower()}")
                    while not os.path.exists(f"{moviesDest}/{movie_data}/{movie_data+fileExtension}"):
                        pass
                    # give permissions to files
                    os.chmod(f"{moviesDest}/{movie_data}", 0o777)
                    os.chmod(
                        f"{moviesDest}/{movie_data}/{movie_data+fileExtension}", 0o777)
                    await log_reply(message, f"{movie_data}\nDownloaded Successfully")
                    queue.task_done()

            except Exception as e:
                try:
                    # If it failed, inform the user about it.
                    await log_reply(message, f"Error: {str(e)}")
                except:
                    pass
                print('Queue worker error: ', e)

    async def start():

        tasks = []
        loop = asyncio.get_event_loop()
        for i in range(worker_count):
            task = loop.create_task(worker())
            tasks.append(task)
        await sendHelloMessage(client, peerChannel)
        await client.run_until_disconnected()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    client.loop.run_until_complete(start())
