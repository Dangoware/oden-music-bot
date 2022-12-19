import discord
import subprocess
import glob
import os
import os.path
import urllib.request
import ffmpeg
import re
import time
import datetime
import yt_dlp
import typing
import functools
from time import strftime
from time import gmtime
from yt_dlp import YoutubeDL
from asyncio import sleep
from discord.ext import commands
from StringProgressBar import progressBar
intents = discord.Intents.default()
intents.message_content = True

# Dictionary to store queues between servers
queue_list = {}
server_info = {}
downloading = 0
paused = False

# Create a new Discord client
bot = commands.Bot(command_prefix="!",intents=discord.Intents.all(), shard_count=1)

@bot.event
async def on_ready():
    print("Bot is ready!")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="Nanahira"))

async def delete_after_delay(ctx, delay):
    await sleep(delay)
    await ctx.message.delete()

async def get_ids(ctx):
    await ctx.message.delete(delay=3)
    server_id = ctx.message.guild.id
    voice_channel = ctx.message.guild.voice_client
    user_voice_channel = ctx.author.voice
    return server_id, voice_channel, user_voice_channel

async def prepare_filesave(server_id):
    downloading = 1
    # Get the current unix timestamp to the nearest millisecond for the filename
    stamp = str(int(str(time.time()).replace('.', '')))
    id = "tmp" + stamp + ".flac"
    thumbname = "tmp" + stamp + ".png"

    # Create the id and thumbnail of the attachment as "tmp<timestamp>.flac" and "tmp<timestamp>.png" respectively
    # And add the server ID as the path, making it unique
    id = os.path.join(str(server_id),id)
    thumbname = os.path.join(str(server_id),thumbname)
    return id, thumbname

@bot.command()
async def play(ctx, *, query: str = None):
    # Get all the id and channel info
    server_id, voice_channel, user_voice_channel = await get_ids(ctx)

    # Create a queue and info dictionary for the current server
    if server_id not in queue_list:
        queue_list[server_id] = [1]
        server_info[server_id] = {
            "loop": False
        }

    # Create the server ID folder for storing downloads
    if not os.path.exists(str(server_id)):
            os.makedirs(str(server_id))

    global paused

    # If the user is not in a voice channel, return an error message
    if user_voice_channel is None:
        await ctx.send("You must be in a voice channel to use this command.", delete_after=3)
        return

    # Connect to the voice channel if not already connected
    if not voice_channel:
        voice_channel = await user_voice_channel.channel.connect()

    # If the user is not in a voice channel or the voice channel is not the same one as the bot, return an error message
    if user_voice_channel.channel != voice_channel.channel:
        await ctx.send("You must be in the same voice channel as the bot to use this command.", delete_after=3)
        return

    if query == None and not ctx.message.attachments:
        # If the bot is already playing, return an error message
        if voice_channel.is_playing():
            await ctx.send(":no_entry_sign: The bot is already playing", delete_after=3)
            return

        # If the bot is paused, resume playback
        if voice_channel.is_paused():
            voice_channel.resume()
            paused = False
            return

        await ctx.send(":no_entry_sign: Must input a valid query or attachment.", delete_after=3)
        await voice_channel.disconnect()
        return

    if voice_channel.is_playing():
        await ctx.send("The bot is already playing, adding song to queue", delete_after=3)

    if ctx.message.attachments:
        downloading = 1
        notice = await ctx.send(":arrow_double_up: Uploading...", suppress_embeds=True)
        for song in ctx.message.attachments:
            id, thumbname = await prepare_filesave(server_id)

            # Make sure the file is either audio or video
            filetype = song.content_type
            if filetype.split('/')[0] != "audio" and filetype.split('/')[0] != "video":
                await notice.edit(content=":no_entry_sign: Not a valid video or audio file...")
                continue

            await song.save(id)

            # Grab thumbnail from file
            f = open("tmp", "w")
            subprocess.run(["ffmpeg", "-y", "-i", id, "-map", "0:v", "-map", "-0:V", "-c", "copy", thumbname], stderr=subprocess.STDOUT, stdout=f)

            # Grab metadata from file
            f = open("tmp", "w")
            subprocess.run(["ffmpeg", "-y", "-i", id, "-f", "ffmetadata", str(server_id) + "/meta.txt"], stderr=subprocess.STDOUT, stdout=f)

            file_title = song.filename
            file_artist = None
            file_album = None

            with open(str(server_id) + '/meta.txt', 'r') as m:
                lines = m.readlines()
                file_artist = "Unknown"
                file_album = "Unknown"
                for line in lines:
                    if re.search(r'TITLE=', line, re.IGNORECASE):
                        file_title = line.split('=')[1]
                        break
                for line in lines:
                    if re.search(r'ARTIST=', line, re.IGNORECASE):
                        file_artist = line.split('=')[1]
                        break
                for line in lines:
                    if re.search(r'ALBUM=', line, re.IGNORECASE):
                        file_album = line.split('=')[1]
                        break


            if os.path.exists(thumbname):
                thumbnail = thumbname
            else:
                thumbnail = "assets/unknown.png"

            try:
                duration = ffmpeg.probe(id)['format']['duration']
            except:
                duration = None

            # Create the item dictionary
            item = {
                "name": file_title.rstrip(),
                "artist": file_artist.rstrip(),
                "album": file_album.rstrip(),
                "url": song.url,
                "id": id,
                "thumbnail": thumbnail,
                "duration": duration
            }

            await notice.edit(content=":white_check_mark: Successfully uploaded \"" + song.filename + "\"")
            queue_list[server_id].append(item)

            downloading = 0
        await notice.edit(content=":white_check_mark: Successfully uploaded \"" + song.filename + "\"", delete_after=3)
    elif query[0:4] != "http" and query[0:3] != "www":
        id, thumbname = await prepare_filesave(server_id)

        # Let the user know the bot is searching for a video
        notice = await ctx.send(":mag_right: Searching for \"" + query + "\" ...", suppress_embeds=True)

        # Search metadata for youtube video
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download = False)["entries"][0]
            title = info["title"]
            audio_url = info["webpage_url"]
            thumb_url = info["thumbnail"]
            duration = info["duration"]

        # Download thumbnail
        urllib.request.urlretrieve(thumb_url, thumbname)

        # Use yt-dlp to download the audio file from youtube to the "tmp.flac" file
        print(str(server_id) + " | " + audio_url)
        await notice.edit(content=":arrow_double_down: Downloading \"" + title + "\": " + audio_url, suppress=True)

        # Download selected video
        ydl_opts = {
            'format': 'flac/bestaudio/best',
            'outtmpl': id,
            'quiet': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download(audio_url)

        # Create the item dictionary
        item = {
            "name": title,
            "artist": None,
            "album": None,
            "url": audio_url,
            "id": id,
            "thumbnail": thumbname,
            "duration": duration
        }

        await notice.edit(content=":white_check_mark: Downloaded " + title + ": " + audio_url, suppress=True, delete_after=3)
        queue_list[server_id].append(item)
        downloading = 0
    elif query[0:4] == "http" or query[0:3] == "www":
        id, thumbname = await prepare_filesave(server_id)

        # Let the user know the bot is searching for a video
        notice = await ctx.send(":mag_right: Searching for \"" + query + "\" ...", suppress_embeds=True)

        if query[0:17] != "https://www.youtu" and query[0:13] != "https://youtu":
            await notice.edit(content=":no_entry_sign: Must input a valid query or attachment.", delete_after=3)
            await voice_channel.disconnect()
            return

        # Search metadata for youtube video
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(query, download = False)
            title = info["title"]
            thumb_url = info["thumbnail"]
            duration = info["duration"]

        # Download thumbnail
        urllib.request.urlretrieve(thumb_url, thumbname)

        # Use yt-dlp to download the audio file from youtube to the "tmp.flac" file
        print(str(server_id) + " | " + query)
        await notice.edit(content=":arrow_double_down: Downloading \"" + title + "\": " + query, suppress=True)

        # Download selected video
        ydl_opts = {
            'format': 'flac/bestaudio/best',
            'outtmpl': id,
            'quiet': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download(query)

        # Create the item dictionary
        item = {
            "name": title,
            "artist": None,
            "album": None,
            "url": query,
            "id": id,
            "thumbnail": thumbname,
            "duration": duration
        }

        await notice.edit(content=":white_check_mark: Downloaded \"" + title + "\": " + query, suppress=True, delete_after=3)
        queue_list[server_id].append(item)
        downloading = 0
    else:
        print("Error")
        await ctx.send("Something went wrong, please try a different query.", delete_after=3)
        return

    print(str(server_id) + " | " + str(item))

    if voice_channel.is_playing() or downloading == 1:
        return

    embed = discord.Embed(title="▶️ Playing: ", description="Name: " + "\nURL: ", color=0x42f5a7)
    playing = await ctx.send(embed=embed)

    # Loop that repeats as long as the queue position has not reached the length of the queue
    while len(queue_list[server_id]) - 1 >= queue_list[server_id][0]:
        # Get the current queue position
        queue_position = queue_list[server_id][0]

        # Set song variables
        song_id = queue_list[server_id][queue_position]['id']
        song_url = queue_list[server_id][queue_position]['url']
        song_name = queue_list[server_id][queue_position]['name']
        song_thumb = queue_list[server_id][queue_position]['thumbnail']
        song_duration = queue_list[server_id][queue_position]['duration']
        song_thumbname = str(int(time.time())) + ".png"

        # Create the embed
        if queue_list[server_id][queue_position]['artist'] and queue_list[server_id][queue_position]['album']:
            song_desc = "Name: " + song_name + "\nArtist: " + queue_list[server_id][queue_position]['artist'] + "\nAlbum: " + queue_list[server_id][queue_position]['album']
        else:
            song_desc = "Name: " + song_name + "\nURL: " + song_url

        embed=discord.Embed(title="▶️ Playing: " + song_name, url=song_url, description=song_desc, color=0x42f5a7)
        await playing.add_files(discord.File(song_thumb, filename=song_thumbname))
        embed.set_image(url="attachment://" + song_thumbname)
        await playing.edit(embed=embed)

        # Play the converted audio in the voice channel from the temporary file
        player = voice_channel.play(discord.FFmpegPCMAudio(source=song_id))
        time1 = int(time.time())
        total = int(float(song_duration))

        # Wait for audio to finish playing
        while voice_channel.is_playing() or voice_channel.is_paused():
            await sleep(1)
            time2 = int(time.time())
            if paused:
                time1 = time2 - current
            else:
                current = time2 - time1
            bardata = progressBar.splitBar(total, current, size=20)

            # Create embed
            if not paused:
                embed=discord.Embed(title="▶️ Playing: " + song_name, url=song_url, description=song_desc, color=0x42f5a7)
            else:
                embed=discord.Embed(title="⏸ Paused: " + song_name, url=song_url, description=song_desc, color=0x42f5a7)
            embed.set_image(url="attachment://" + song_thumbname)
            embed.add_field(name=str(datetime.timedelta(seconds=current)) + "/" + str(datetime.timedelta(seconds=total)), value=bardata[0], inline=False)
            await playing.edit(embed=embed)

        if server_info[server_id]["loop"]:
            continue

        # Increment the queue position by 1
        try:
            queue_list[server_id][0] += 1
        except:
            print(str(server_id) + " | " + "Queue position out of range.")
            break
        print(str(server_id) + " | " + "Play position: "  + str(queue_position))

        try:
            await q(ctx)
        except:
            pass

    # Display the stop embed
    try:
        await q(ctx, "hide")
    except:
        pass
    embed=discord.Embed(title="⏹️ Finished Queue: " + song_name, url=song_url, description="Name: " + song_name + "\nURL: " + song_url, color=0x42f5a7)
    embed.set_thumbnail(url="attachment://" + song_thumbname)
    await playing.edit(embed=embed)

    await ctx.send("Finished queue, disconnecting.", suppress_embeds=True, delete_after=3)
    print(str(server_id) + " | " + "Queue finished.")
    # Disconnect from the voice channel if the loop finishes
    await voice_channel.disconnect()

    queue_list[server_id].clear()
    queue_list[server_id].insert(0, 1)

    # Remove all queued files and folders
    fileList = glob.glob(os.path.join(str(server_id),'*'))
    for filePath in fileList:
        try:
            os.remove(filePath)
        except OSError:
            print("Error while deleting file")
    os.rmdir(str(server_id))

@bot.command()
async def skip(ctx, direction = None, number = None):
    # Get all the id and channel info
    server_id, voice_channel, user_voice_channel = await get_ids(ctx)

    if voice_channel is None:
        await ctx.send(":no_entry_sign: Bot must be playing to skip!", delete_after=3)
        return

    if user_voice_channel is None or user_voice_channel.channel != voice_channel.channel:
        # If the user is not in a voice channel, return an error message
        await ctx.send(":no_entry_sign: You must be in the same voice channel as the bot to use this command.", delete_after=3)
        return

    try:
        number = int(number)
    except:
        pass

    # Check which direction the user asked to skip
    if direction is None or direction == "forward" or direction.isnumeric():
        try:
            if direction.isnumeric():
                if int(direction) > 0:
                    queue_list[server_id][0] += int(direction) - 1
        except:
            pass
        if number != None and number > 0:
            queue_list[server_id][0] += number - 1

        # Stop the audio playback
        voice_channel.stop()

    elif direction == "back" and not queue_list[server_id][0] == 1:

        # Decrement the queue position
        back = 2

        # Decrement the queue position if the number is set
        if number != None and number > 0:
            back = number + 1

        queue_list[server_id][0] -= back

        # Stop the audio playback of the current track
        voice_channel.stop()

    elif direction == "to" and number is not None:
        queue_list[server_id][0] = number - 1

        voice_channel.stop()

    elif queue_list[server_id][0] == 1:
        await ctx.send(":no_entry_sign: Already at first song in queue.", delete_after=3)

    else:
        await ctx.send(":no_entry_sign: Invalid argument.", delete_after=3)

    await sleep(2)
    try:
        await q(ctx)
    except:
        pass

@bot.command()
async def stop(ctx):
    # Get all the id and channel info
    server_id, voice_channel, user_voice_channel = await get_ids(ctx)

    if voice_channel is None:
        await ctx.send(":no_entry_sign: Bot must be playing to stop!", delete_after=3)
        return
    if user_voice_channel is None or user_voice_channel.channel != voice_channel.channel:
        # If the user is not in a voice channel, return an error message
        await ctx.send(":no_entry_sign: You must be in the same voice channel as the bot to use this command.", delete_after=3)
        return

    queue_list[server_id].clear()
    queue_list[server_id].insert(0, 1)
    await sleep(0.5)
    voice_channel.stop()
    await voice_channel.disconnect()

@bot.command()
async def pause(ctx):
    # Get all the id and channel info
    server_id, voice_channel, user_voice_channel = await get_ids(ctx)

    if voice_channel is None or not voice_channel.is_playing():
        await ctx.send(":no_entry_sign: Bot must be playing to pause!", delete_after=3)
        return
    if user_voice_channel is None or user_voice_channel.channel != voice_channel.channel:
        # If the user is not in a voice channel, return an error message
        await ctx.send(":no_entry_sign: You must be in the same voice channel as the bot to use this command.", delete_after=3)
        return
    voice_channel.pause()
    global paused
    paused = True

@bot.command()
async def queue(ctx, action = None, selection = None):
    await q(ctx, action, selection)

@bot.command()
async def q(ctx, action = None, selection = None):
    # Get all the id and channel info
    server_id, voice_channel, user_voice_channel = await get_ids(ctx)
    global queue_embed
    if action == "hide":
        try:
            queue_embed
        except:
            pass
        else:
            if queue_embed is None:
                pass
            else:
                await queue_embed.delete()
                queue_embed = None
                del queue_embed
        return

    if voice_channel is None:
        await ctx.send(":no_entry_sign: Bot must be in a channel to view the queue!", delete_after=3)
        return
    if user_voice_channel is None or user_voice_channel.channel != voice_channel.channel:
        # If the user is not in a voice channel, return an error message
        await ctx.send(":no_entry_sign: You must be in the same voice channel as the bot to use this command.", delete_after=3)
        return

    if action == "show" or action == "list" or action == None:
        if action == "show":
            try:
                await q(ctx, "hide")
            except:
                pass

        print(str(server_id) + " | " + "Updating queue, position: " + str(queue_list[server_id][0]))
        x = 0
        qu = ""
        d = ""
        p = ""
        now_playing = "⠀"
        for entry in queue_list[server_id]:
            if x != 0:
                if x == queue_list[server_id][0]:
                    now_playing = ":arrow_right:"
                else:
                    now_playing = "⠀"


                if len(entry['name']) >= 30:
                    entry_cut = entry['name'][0:30]
                else:
                    entry_cut = entry['name']

                p += now_playing + "\n"
                qu += "**" + str(x) + ":** " + entry_cut + "\n"
                if str(strftime("%H", gmtime(int(float(entry['duration'])))))[0:1] == "00":
                    d += str(strftime("%M:%S", gmtime(int(float(entry['duration']))))) + "\n"
                else:
                    d += str(strftime("%H:%M:%S", gmtime(int(float(entry['duration']))))) + "\n"
            x += 1

        embed=discord.Embed(title="Queue:", description="", color=0xa032a8)
        try:
            embed.add_field(name="⠀", value=p, inline=True)
            embed.add_field(name="List", value=qu, inline=True)
            embed.add_field(name="Length", value=d, inline=True)
        except:
            embed.add_field(name="List", value="Queue is **empty**", inline=False)

        try:
            queue_embed
        except:
            queue_embed = await ctx.send(embed=embed)
        else:
            if queue_embed is None:
                queue_embed = await ctx.send(embed=embed)
            else:
                await queue_embed.edit(embed=embed)
        return

    if action == "remove":
        print(str(server_id) + " | " + "Removing item #" + str(selection) + " from queue")
        selection = int(selection)
        position = queue_list[server_id][0]
        id = queue_list[server_id][selection]['id']
        if queue_list[server_id][selection]['thumbnail'] != "/assets/unknown.png":
            thumbnail = None
        else:
            thumbnail = queue_list[server_id][selection]['thumbnail']

        if selection is position:
            await ctx.send(":no_entry_sign: Error, cannot remove currently playing item", delete_after=3)
            return

        if selection != 0 and not int(selection) > len(queue_list[server_id]):
            try:
                os.remove(id)
                if not thumbnail is None:
                    os.remove(thumbnail)
                else:
                    pass
            except OSError:
                print(str(server_id) + " | " + "Error while deleting song or thumbnail")
                pass

            if selection < position and position > 1:
                try:
                    queue_list[server_id][0] -= 1
                except:
                    print(str(server_id) + " | " + "Queue position out of range.")
                    pass

            await ctx.send(":white_check_mark: Removed item #" + str(selection) + " from queue.", delete_after=3)
            queue_list[server_id].pop(selection)
            await q(ctx)
        else:
            await ctx.send(":no_entry_sign: Error, item #" + str(selection) + "not a valid queue item", delete_after=3)
        return

@bot.command()
async def loop(ctx, number = None):
    server_id, voice_channel, user_voice_channel = await get_ids(ctx)

    if voice_channel is None or not voice_channel.is_playing() and not voice_channel.is_paused():
        await ctx.send(":no_entry_sign: Bot must be playing to loop!", delete_after=3)
        return

    if user_voice_channel is None or user_voice_channel.channel != voice_channel.channel:
        # If the user is not in a voice channel, return an error message
        await ctx.send(":no_entry_sign: You must be in the same voice channel as the bot to use this command.", delete_after=3)
        return

    if server_info[server_id]["loop"] is False:
        print(str(server_id) + " | " + "Looping current song.")
        server_info[server_id]["loop"] = True
        print(server_info[server_id]["loop"])
        return
    else:
        print(str(server_id) + " | " + "Not looping current song.")
        server_info[server_id]["loop"] = False
        print(server_info[server_id]["loop"])
        return

@bot.event
async def on_command_error(ctx, error):
    server_id, voice_channel, user_voice_channel = await get_ids(ctx)
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Unknown command", delete_after=3)

# Run the bot using the Discord bot token
bot.run("<BOT TOKEN GOES HERE>")
