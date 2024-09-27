import discord, subprocess, glob, os, os.path, ffmpeg
import re, time, datetime, yt_dlp, typing, functools
from time import strftime, gmtime
from yt_dlp import YoutubeDL
from asyncio import sleep
from discord.ext import commands
from StringProgressBar import progressBar
import logging
import json
from pprint import pprint

## LOCAL IMPORTS ##
#####
import utils

logging.basicConfig()
intents = discord.Intents.default()
intents.message_content = True

# Dictionary to store queues for individual servers
server_info = {}

# Create a new Discord client
bot = commands.Bot(command_prefix="!",intents=discord.Intents.all(), shard_count=1)


@bot.event
async def on_ready():
    print("Bot is ready!")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening, name="ななひら"
        )
    )


@bot.command()
async def play(ctx, *, query: str = None):
    # Get all the id and channel info
    server_id, voice_channel, user_voice_channel = await utils.getIds(ctx)

    # Create a queue and info dictionary for the current server
    if server_id not in server_info:
        server_info[server_id] = {
            "loop": False,
            "paused": False,
            "elapsed": 0,
            "queue_position": 0,
            "queue": [],
        }

    # Create the server ID folder for storing downloads
    if not os.path.exists(str(server_id)):
            os.makedirs(str(server_id))

    global paused

    # If the user is not in a voice channel, return an error message
    if user_voice_channel is None:
        await ctx.send(":no_entry_sign: You must be in a voice channel to use this command.")
        return

    # Connect to the voice channel if not already connected
    if not voice_channel:
        voice_channel = await user_voice_channel.channel.connect()

    # If the user is not in a voice channel or the voice channel is not the same one as the bot, return an error message
    if await utils.notSameChannel(ctx):
        await ctx.send(":no_entry_sign: You must be in the same voice channel as the bot to use this command.")
        return

    if query == None and not ctx.message.attachments:
        # If the bot is already playing, return an error message
        if voice_channel.is_playing():
            await ctx.send(":no_entry_sign: The bot is already playing")
            return

        # If the bot is paused, resume playback
        if voice_channel.is_paused():
            voice_channel.resume()
            paused = False
            return

        await ctx.send(":no_entry_sign: Must input a valid query or attachment.", delete_after=3)
        await voice_channel.disconnect()
        return

    if ctx.message.attachments:
        success_list = []
        notice = await ctx.send(":arrow_double_up: Uploading...", suppress_embeds=True)
        success_string = ":white_check_mark: Successfully uploaded: \n"
        for song in ctx.message.attachments:
            filename, thumbname = utils.getFileNames(server_id)

            # Make sure the file is either audio or video
            filetype = song.content_type
            if filetype is None or (filetype.split('/')[0] != "audio" and filetype.split('/')[0] != "video"):
                await notice.edit(content=":no_entry_sign: Not a valid video or audio file...")
                continue

            # Save the song to the temp folder
            await song.save(filename)

            # Get all the info about the file and create an "item" for it
            item = utils.parseMediaFile(song, filename, thumbname)
            success_list.append(item["name"]);

            success_string += " –`" + item["name"] + "`\n"

            await notice.edit(content=success_string)
            server_info[server_id]["queue"].append(item)

        if len(success_list) > 0:
            await notice.edit(content=success_string, delete_after=3)
        else:
            await notice.edit(content=f":no_entry_sign: No files successfully uploaded.", delete_after=3)
            return
    elif query[0:4] != "http" and query[0:3] != "www":
        filename, _ = utils.getFileNames(server_id)

        # Let the user know the bot is searching for a video
        notice = await ctx.send(":mag_right: Searching for \"" + query + "\" ...", suppress_embeds=True)

        # Search metadata for youtube video
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            search_list = ydl.extract_info(f"ytsearch:{query}", download = False)["entries"]
            if len(search_list) == 0:
                await notice.edit(content=":question: No songs found for query, try something else!", delete_after=3)
                return

            info = search_list[0]
            title = info["title"]
            audio_url = info["webpage_url"]
            thumb_url = info["thumbnail"]
            duration = info["duration"]

        print(str(server_id) + " | " + audio_url)

        # Create the item dictionary
        item = {
            "name": title,
            "artist": None,
            "album": None,
            "url": audio_url,
            "id": filename,
            "thumbnail": None,
            "thumbnail_url": thumb_url,
            "duration": int(float(duration)),
            "color": None,
        }

        await notice.edit(content=":white_check_mark: Found " + title + ": " + audio_url, suppress=True, delete_after=3)
        server_info[server_id]["queue"].append(item)
    elif query[0:4] == "http" or query[0:3] == "www":
        filename, _ = utils.getFileNames(server_id)

        notice = await ctx.send(":mag_right: Adding video \"" + query + "\" ...", suppress_embeds=True)

        if "youtube" not in query and "youtu.be" not in query:
            await notice.edit(content=":no_entry_sign: Must be a valid youtube link.", delete_after=3)
            await voice_channel.disconnect()
            return

        # Search metadata for youtube video
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(query, download = False)
            title = info["title"]
            thumb_url = info["thumbnail"]
            duration = info["duration"]

        print(str(server_id) + " | " + query)

        # Create the item dictionary
        item = {
            "name": title,
            "artist": None,
            "album": None,
            "url": query,
            "id": filename,
            "thumbnail": None,
            "thumbnail_url": thumb_url,
            "duration": int(float(duration)),
            "color": None,
        }

        await notice.edit(content=":white_check_mark: Found \"" + title + "\": " + query, suppress=True, delete_after=3)
        server_info[server_id]["queue"].append(item)
    else:
        print("Error")
        await ctx.send("Something went wrong, please try a different query.", delete_after=3)
        return

    # It's already playing, don't start another playback stream!
    if voice_channel.is_playing():
        return

    # Loop that repeats as long as the queue position has not reached the length of the queue
    while len(server_info[server_id]["queue"]) >= server_info[server_id]["queue_position"]:
        embed = discord.Embed(title="▶️ Playing: ", description="Name: " + "\nURL: ", color=0x42f5a7)
        playing = await ctx.send(embed=embed)

        # Get the current queue item
        queue_position = server_info[server_id]["queue_position"]
        queue = server_info[server_id]["queue"]
        current_item = queue[queue_position]

        # Set song variables
        song_id = current_item['id']
        song_url = current_item['url']
        song_name = current_item['name']
        song_thumb = current_item['thumbnail']
        song_duration = current_item['duration']
        song_thumb_url = current_item['thumbnail_url']
        song_thumbname = str(int(time.time())) + ".png"

        color = 0x42f5a7
        if current_item["color"] is not None:
            color = (current_item["color"][0] << 16) | (current_item["color"][1] << 8) | current_item["color"][2]

        # Create the embed
        if current_item["artist"] and current_item["album"]:
            song_desc = "Artist: " + current_item['artist'] + "\nAlbum: " + current_item['album']
        else:
            song_desc = ""

        embed = discord.Embed(title=":arrow_forward: Playing: " + song_name, url=song_url, description=song_desc, color=color)
        if song_thumb is not None:
            await playing.add_files(discord.File(song_thumb, filename=song_thumbname))
            embed.set_thumbnail(url="attachment://" + song_thumbname)
        elif song_thumb_url is not None:
            embed.set_thumbnail(url=song_thumb_url)

        await playing.edit(embed = embed)

        song_source = None
        pipe = False
        if song_url is not None and song_url != "":
            song_source = subprocess.Popen(
                ['yt-dlp', '-q', '-o', '-', '-x', song_url],
                stdout=subprocess.PIPE,
            ).stdout
            pipe = True
            print(str(server_id) + " | " + "Playing song through yt-dlp")
        else:
            print(str(server_id) + " | " + "Playing song from file")
            song_source = song_id

        # Play the converted audio in the voice channel from the temporary file
        # or the FFMPEG stream
        player = voice_channel.play(discord.FFmpegPCMAudio(source=song_source, pipe=pipe))
        time1 = int(time.time())
        total = song_duration

        # Wait for audio to finish playing
        while voice_channel.is_playing() or voice_channel.is_paused():
            await sleep(1)
            time2 = int(time.time())
            current = time2 - time1
            server_info[server_id]["elapsed"] = current
            bardata = progressBar.splitBar(total, current, size=20)

            # Create embed
            embed=discord.Embed(title="▶️ Playing: " + song_name, url=song_url, description=song_desc, color=color)

            if song_thumb is not None:
                embed.set_thumbnail(url="attachment://" + song_thumbname)
            elif song_thumb_url is not None:
                embed.set_thumbnail(url=song_thumb_url)

            embed.add_field(
                name=str(datetime.timedelta(seconds=current)) + "/" + str(datetime.timedelta(seconds=total)),
                value=bardata[0],
                inline=False
            )
            await playing.edit(embed=embed)

        server_info[server_id]["elapsed"] = 0
        if not server_info[server_id]["loop"]:
            # Increment the queue position by 1
            try:
                server_info[server_id]["queue_position"] += 1
            except:
                print(str(server_id) + " | " + "Queue position out of range.")
                break
        print(str(server_id) + " | " + "Play position: "  + str(queue_position))

    print(str(server_id) + " | " + "Queue finished.")


    # Disconnect from the voice channel if the loop finishes
    await voice_channel.disconnect()

    server_info[server_id]["queue"].clear()
    server_info[server_id]["queue_position"] = 0

    # Remove all queued files and folders... This is a bit dangerous, maybe it
    # should be made failsafe somehow? TODO
    fileList = glob.glob(os.path.join(str(server_id),'*'))
    for filePath in fileList:
        try:
            os.remove(filePath)
        except OSError:
            print("Error while deleting file ", filePath)
    os.rmdir(str(server_id))


@bot.command()
async def skip(ctx, direction = None, number = None):
    # Get all the id and channel info
    server_id, voice_channel, user_voice_channel = await utils.getIds(ctx)

    if voice_channel is None:
        await ctx.send(":no_entry_sign: Bot must be playing to skip!", delete_after=3)
        return

    if await utils.notSameChannel(ctx):
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
                    server_info[server_id]["queue_position"] += int(direction) - 1
        except:
            pass
        if number != None and number > 0:
            server_info[server_id]["queue_position"] += number - 1

        # Stop the audio playback
        voice_channel.stop()
    elif direction == "back" and not server_info[server_id]["queue_position"] == 0:

        # Decrement the queue position
        back = 2

        # Decrement the queue position if the number is set
        if number != None and number > 0:
            back = number + 1

        server_info[server_id]["queue_position"] -= back

        # Stop the audio playback of the current track
        voice_channel.stop()
    elif direction == "to" and number is not None:
        server_info[server_id]["queue_position"] = number - 1

        voice_channel.stop()
    elif server_info[server_id]["queue_position"] == 0:
        await ctx.send(":no_entry_sign: Already at first song in queue.", delete_after=3)
    else:
        await ctx.send(":no_entry_sign: Invalid argument.", delete_after=3)


@bot.command()
async def stop(ctx):
    # Get all the id and channel info
    server_id, voice_channel, user_voice_channel = await utils.getIds(ctx)

    if voice_channel is None:
        await ctx.send(":no_entry_sign: Bot must be playing to stop!", delete_after=3)
        return

    if await utils.notSameChannel(ctx):
        # If the user is not in a voice channel, return an error message
        await ctx.send(":no_entry_sign: You must be in the same voice channel as the bot to use this command.", delete_after=3)
        return

    server_info[server_id]["queue"].clear()
    server_info[server_id]["queue_position"] = 0
    await sleep(0.5)
    voice_channel.stop()
    await voice_channel.disconnect()

#
# @bot.command()
# async def pause(ctx):
#     # Get all the id and channel info
#     server_id, voice_channel, user_voice_channel = await utils.getIds(ctx)
#
#     if voice_channel is None or not voice_channel.is_playing():
#         await ctx.send(":no_entry_sign: Bot must be playing to pause!", delete_after=3)
#         return
#     if user_voice_channel is None or user_voice_channel.channel != voice_channel.channel:
#         # If the user is not in a voice channel, return an error message
#         await ctx.send(":no_entry_sign: You must be in the same voice channel as the bot to use this command.", delete_after=3)
#         return
#
#     voice_channel.pause()


@bot.command()
async def queue(ctx, action = None, selection = None):
    await q(ctx, action, selection)


@bot.command()
async def q(ctx, action = None, selection = None):
    # Get all the id and channel info
    server_id, voice_channel, user_voice_channel = await utils.getIds(ctx)

    if voice_channel is None:
        await ctx.send(":no_entry_sign: Bot must be in a channel to view the queue!", delete_after=3)
        return

    if await utils.notSameChannel(ctx):
        # If the user is not in a voice channel, return an error message
        await ctx.send(":no_entry_sign: You must be in the same voice channel as the bot to use this command.", delete_after=3)
        return

    if action == "show" or action == "list" or action == None:
        print(str(server_id) + " | " + "Updating queue, position: " + str(server_info[server_id]["queue_position"]))
        index = 0
        queue_string = ""
        duration_string = ""
        position_string = ""
        total_duration = 0
        for entry in server_info[server_id]["queue"]:
            if index == server_info[server_id]["queue_position"]:
                position_string += ":arrow_right:\n"
            else:
                position_string += "⠀\n"


            if len(entry['name']) >= 30:
                entry_cut = entry['name'][0:30]
            else:
                entry_cut = entry['name']

            queue_string += "**" + str(index + 1) + ":** " + entry_cut + "\n"
            if entry['duration'] < 3600:
                duration_string += str(strftime("%M:%S", gmtime(entry['duration']))) + "\n"
            else:
                duration_string += str(strftime("%H:%M:%S", gmtime(entry['duration']))) + "\n"

            if index == server_info[server_id]["queue_position"]:
                total_duration += entry['duration'] - server_info[server_id]["elapsed"]
            if index > server_info[server_id]["queue_position"]:
                total_duration += entry['duration']
            index += 1

        # Calculate the time remaining in the queue
        total_duration = str(strftime("%H:%M:%S", gmtime(total_duration)))

        embed = discord.Embed(title=f"Queue ({total_duration} left):", description="", color=0xa032a8)
        try:
            embed.add_field(name="⠀", value=position_string, inline=True)
            embed.add_field(name="List", value=queue_string, inline=True)
            embed.add_field(name=f"Length", value=duration_string, inline=True)
        except:
            embed.add_field(name="List", value="Queue is **empty**", inline=False)

        # Send the constructed queue
        queue_embed = await ctx.send(embed=embed)

    elif action == "remove" and selection is not None:
        print(str(server_id) + " | " + "Removing item #" + str(selection) + " from queue")
        selection = int(selection) - 1
        current_position = server_info[server_id]["queue_position"]

        path = server_info[server_id]["queue"][selection]["id"]
        if server_info[server_id]["queue"][selection]["thumbnail"] != "/assets/unknown.png":
            thumbnail = None
        else:
            thumbnail = server_info[server_id]["queue"][selection]['thumbnail']

        if selection is current_position:
            await ctx.send(":no_entry_sign: Error, cannot remove currently playing item", delete_after=3)
            return

        if not selection < 0 and not selection > len(server_info[server_id]["queue"]):
            try:
                os.remove(path)
                if thumbnail is not None:
                    os.remove(thumbnail)
                else:
                    pass
            except OSError:
                print(str(server_id) + " | " + "Error while deleting song or thumbnail")
                pass

            if selection < current_position and current_position:
                try:
                    server_info[server_id]["queue_position"] -= 1
                except:
                    print(str(server_id) + " | " + "Queue position out of range.")
                    pass

            await ctx.send(":white_check_mark: Removed item #" + str(selection + 1) + " from queue.", delete_after=3)
            server_info[server_id]["queue"].pop(selection)
            await q(ctx)
        elif action == "remove" and selection is None:
            await ctx.send(":no_entry_sign: Error, please select a queue item to remove", delete_after=3)
        else:
            await ctx.send(":no_entry_sign: Error, item #" + str(selection) + "not a valid queue item", delete_after=3)


@bot.command()
async def loop(ctx, number = None):
    server_id, voice_channel, user_voice_channel = await utils.getIds(ctx)

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
    server_id, voice_channel, user_voice_channel = await utils.getIds(ctx)
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Unknown command", delete_after=3)
    else:
        print(error)

# Run the bot using the Discord bot token
bot.run(os.environ['DISCORD_SECRET'])
