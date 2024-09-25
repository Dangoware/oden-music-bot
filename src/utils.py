import uuid, os, ffmpeg

async def getIds(ctx):
    """Get server id, voice channel id, and user voice channel id"""

    server_id = ctx.message.guild.id
    voice_channel = ctx.message.guild.voice_client
    user_voice_channel = ctx.author.voice
    return server_id, voice_channel, user_voice_channel


async def notSameChannel(ctx) -> bool:
    """If the user is not in a voice channel, or is in a different voice channel than the bot, return false"""

    server_id, voice_channel, user_voice_channel = await getIds(ctx)

    if user_voice_channel is None or user_voice_channel.channel != voice_channel.channel:
        return True
    else:
        return False


def getFileNames(server_id):
    """Get the UUID-based filenames for temp files"""

    downloading = 1
    # Get the current unix timestamp to the nearest millisecond for the filename
    uuid_stamp = uuid.uuid1()
    audioname = str(uuid_stamp) + "audio"
    thumbname = str(uuid_stamp) + "image"

    # Create the id and thumbnail of the attachment as "tmp<timestamp>.flac" and "tmp<timestamp>.png" respectively
    # And add the server ID as the path, making it unique
    audioname = os.path.join(str(server_id), audioname)
    thumbname = os.path.join(str(server_id), thumbname)
    return audioname, thumbname


def parseMediaFile(discord_file, tmp_filename: str, tmp_thumbname: str):
    """Parse information about uploaded media files using ffmpeg"""

    # Grab thumbnail from the file
    (ffmpeg
        .input(tmp_filename, t=1)
        .output(tmp_thumbname, f="image2")
        .overwrite_output()
        .run(quiet=True))

    # Grab metadata from file
    try:
        metadata = ffmpeg.probe(tmp_filename)
    except:
        metadata = {}

    file_title = discord_file.filename
    if "TITLE" in metadata["format"]["tags"]:
        file_title = metadata["format"]["tags"]["TITLE"]

    file_artist = ""
    if "ARTIST" in metadata["format"]["tags"]:
        file_artist = metadata["format"]["tags"]["ARTIST"]

    file_album = ""
    if "ALBUM" in metadata["format"]["tags"]:
        file_album = metadata["format"]["tags"]["ALBUM"]


    if os.path.exists(tmp_thumbname):
        thumbnail = tmp_thumbname
    else:
        thumbnail = "assets/unknown.png"

    try:
        duration = metadata['format']['duration']
    except:
        duration = None

    # Create the item dictionary
    item = {
        "name": file_title.rstrip(),
        "artist": file_artist.rstrip(),
        "album": file_album.rstrip(),
        "url": discord_file.url,
        "id": tmp_filename,
        "thumbnail": thumbnail,
        "thumbnail_url": None,
        "duration": int(float(duration))
    }

    return item

