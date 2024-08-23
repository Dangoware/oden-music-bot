import uuid, os

async def delete_after_delay(ctx, delay):
    await sleep(delay)
    await ctx.message.delete()


async def get_ids(ctx):
    server_id = ctx.message.guild.id
    voice_channel = ctx.message.guild.voice_client
    user_voice_channel = ctx.author.voice
    return server_id, voice_channel, user_voice_channel


async def getFileNames(server_id):
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
