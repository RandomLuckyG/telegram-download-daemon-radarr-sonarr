# Telegram Download Daemon for Radarr and Sonarr

A Telegram Daemon (not a bot) for file downloading automation for channels of which you have admin privileges Into Radarr and Sonarr Media Files.

Telegram bots are limited to 20Mb file size downloads. So this agent or daemon allow bigger downloads (limited to 2GB by Telegram APIs).

Download Movies And TV Shows From Telegram Straight into Radarr/ Sonnar Media Folders

# Docker Setup:

| Environment Variable     | Command Line argument | Description                                                  | Default Value       |
|--------------------------|:-----------------------:|--------------------------------------------------------------|---------------------|
| `TELEGRAM_DAEMON_API_ID`   | `--api-id`              | api_id from https://core.telegram.org/api/obtaining_api_id   |                  |
| `TELEGRAM_DAEMON_API_HASH` | `--api-hash`            | api_hash from https://core.telegram.org/api/obtaining_api_id |                  |
| `TELEGRAM_DAEMON_MOVIES_DEST`     | `--moviesdest`   | Radarr Destination path for downloaded Movies                | `/movies` |
| `TELEGRAM_DAEMON_TVSHOWS_DEST` | `--tvshowsdest`     | Sonarr Destination path for downloaded Episodes                | `/tvshows` |
| `TELEGRAM_DAEMON_TEMP`     | `--temp`                | Destination path for temporary (download in progress) files  | `/downloads` |
| `TELEGRAM_DAEMON_CHANNEL`  | `--channel`             | Channel id to download from it           |                 |
| `TELEGRAM_DAEMON_DUPLICATES`  | `--duplicates`       | What to do with current downloading duplicated files: ignore, overwrite or rename them | rename     |
| `TELEGRAM_DAEMON_WORKERS`  | `--workers`             | Number of simultaneous downloads | Equals to processor cores  |

You can define them as Environment Variables, or put them as a command line arguments, for example:

```
python telegram-download-daemon.py --api-id <your-id> --api-hash <your-hash> --channel <channel-number>
```

# docker-compose
```bash
version: "4"
services:
  telegram-download-daemon-radarr-sonarr:
    image: docker.io/randomg1/telegram-download-daemon-radarr-sonarr:latest
    container_name: telegram-download-daemon-radarr-sonarr
    read_only: true
    environment:
      TELEGRAM_DAEMON_API_ID: "api_id"
      TELEGRAM_DAEMON_API_HASH: "api_hash"
      TELEGRAM_DAEMON_CHANNEL: "channel_id"
      TELEGRAM_DAEMON_TEMP: "/downloads"
      TELEGRAM_DAEMON_MOVIES_DEST: "/movies"
      TELEGRAM_DAEMON_TVSHOWS_DEST: "/tvshows"
      TELEGRAM_DAEMON_SESSION_PATH: "/session"
      TELEGRAM_DAEMON_DUPLICATES: "ignore"
      TELEGRAM_DAEMON_WORKERS: 7
    volumes:
      - ${MEDIA_DIRECTORY}/downloads:/downloads
      - ${MEDIA_DIRECTORY}/movies:/movies
      - ${MEDIA_DIRECTORY}/tvshows:/tvshows
      - ${MEDIA_DIRECTORY}/sessions:/session
    restart: unless-stopped
```

# How to login
- after docker-compose setup
- You need to **interactively** run the container for the first time.
- When you use `docker-compose`, the `.session` file, where the login is stored is kept in *Volume* outside the container. Therefore, when using docker-compose you are required to:

```bash
$ docker compose run --rm telegram-download-daemon-radarr
# Interact with the console to authenticate yourself.
# See the message "Signed in successfully"
# Close the container
$ docker compose up -d
```

# How to use with Radarr/ Sonarr:
- Sonarr Standard Episode Format MUST be `{Series Title} - S{season:00}E{episode:00}`.
- Sonarr TV show seasons need to be configured to be separated by folders
- Radarr Movie Folder Format MUST be `{Movie Title} ({Release Year})`.
- Temp Could be Sonarr "/downloads" or whatever you want.
- You Must Conigure Your Files Destination Acording to Radarr, Sonarr
- After Telegram Login, restart the server.
- You should be prompted with a message that the bot is on, on the channel you chose.
- Currently You Need To Manually Add The Movie, TV Show To Radarr, Sonarr Catalogs.
- Forward A File To The Channel, You will be prompted by the bot to provide data about the file until its achieved, else use /cancel to cancel the operation of downloading the file.
- File Data Provided from the user is now more Dynamic:
- - Movie: `{Movie Title} {Year}`, like "Hot Seat (2022)", Hot Seat 2022"
- - TV Show: `{Series Title} {Year} - S{season:00}E{episode:00}`, like "The Witcher (2019) - S03E02", "The Witcher 2019 - S03E02", "The Witcher 2019 - s3e2", "The Witcher 2019 - s20e120".
- Without providing data the daemon doesn't proceed to the download part.


# Bot Functions:
* Say "/status" to the daemon to check the current status of downloads.
* Say "/clean" to remove stale (*.tdd) files from temporary directory.
* Say "/queue" to list the pending files waiting to start.
