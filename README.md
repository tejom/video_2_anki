# video_2_anki

This script chains together a bunch of AI/ML models to create audio clips separate by sentences that can be used as Anki cards
The output from the script is audio clips, and a txt file that can be used by Anki to import the cards
The front of the card is the audio, the back is the transcription and translation. All of the AI tools run locally. No payments required

## Set Up:
use the requirements.txt

ex: `pip install -r requirements.txt`

Make sure you have ffmpeg installed. It's used for splitting the videos.

https://www.ffmpeg.org/

### Dependency docs and custom set up:

- For Spacy languages or GPU usage check https://spacy.io/usage
- Argo Translate https://github.com/argosopentech/argos-translate/tree/master
- Whsiper https://github.com/openai/whisper/tree/main
- Anki File locations https://docs.ankiweb.net/files.html#file-locations

## Use:
Generate clips from a video, save the audio clips and generate a txt file that can be imported into Anki

eg. `./video_2_anki --audio-save-dir=/path/to/Anki2/User\ 1/collection.media foreign_language_video.mp4`

Or download straight from YouTube

eg. `./video_2_anki --audio-save-dir=/path/to/Anki2/User\ 1/collection.media  https://www.youtube.com/watch?v=some-video-id`

This will save all the videos to the path, using the Anki path means you can just import the txt file.

Txt file example:
```
[sound:slow_spanish-0-clip.mp4];Hola a todos.<br>Hello, everyone.
[sound:slow_spanish-1-clip.mp4];¿Cómo están?<br>How are you?
```

`./video_2_anki --help` for more detailed options

## Limitations:
Only supports Spanish to English, but other languages can be added!
