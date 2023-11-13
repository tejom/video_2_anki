import json
import argparse
from pathlib import Path
import os
import subprocess
import logging
from tempfile import TemporaryDirectory

import spacy
import argostranslate.package
import argostranslate.translate
import whisper
from pytube import YouTube

FILE_DELIM = ";"
TAGS = "#tags:{tags}"
AUDIO_FMT = "[sound:{fname}]"

AUDIO_BUFFER = 0.35

SPACY_MODELS = {"es": "es_core_news_sm"}

log = logging.getLogger()


def download_youtube_audio(video_src, out_dir) -> Path:
    yt = YouTube(video_src)
    audio_stream = yt.streams.get_audio_only()
    title = ''.join(filter(str.isalnum, yt.title))
    file_name = audio_stream.download(output_path=out_dir, filename=f'yt_audio_{title}.mp4')
    log.info(f"Downloaded {yt.title} to {file_name}")
    return Path(file_name)


def build_words_with_ts(data):
    words_ts = []

    for seg in data["segments"]:
        for w in seg["words"]:
            words_ts.append((w["word"].strip(), w["start"], w["end"]))
    return words_ts


def build_sentence_start_end(doc, words_ts, audio_buffer):
    """
    doc: spacy doc
    words_ts: from build_words_with_ts (word, start, end)

    return: (start, end, text)
    """
    sentence_ts = []

    word_idx = 0
    end_word_idx = 0
    for sent in doc.sents:
        sent_words = sent.text.split(" ")
        end_word_idx += len(sent_words)

        try:
            assert sent_words[0] == words_ts[word_idx][0]
        except AssertionError:
            log.error(
                f"mismatched word - {word_idx=} {end_word_idx=} {sent_words[0]=} { words_ts[word_idx][0]=}"
            )
            raise

        start = (
            words_ts[word_idx][1] - audio_buffer
            if words_ts[word_idx][1] > 0
            else words_ts[word_idx][1]
        )
        end = words_ts[end_word_idx - 1][2] + audio_buffer

        sentence_ts.append((start, end, sent.text))
        word_idx = end_word_idx
    return sentence_ts


def split_video_into_audio_seg(in_video, timestamps, out_name, out_dir):
    """
    in_video: file to slice up
    timestamps: tuple (start, end) as str
    out_name: base name for the clips
    out_dir: dir to save slices in
    """
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    created_files = []
    for (n, (s, e)) in enumerate(timestamps):
        fname = f"{out_name}-{n}-clip.mp4"
        args = [
            "ffmpeg",
            "-ss",
            s,
            "-to",
            e,
            "-i",
            in_video,
            "-map",
            "0:a",
            "-y",
            f"{out_dir}/{fname}",
        ]
        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        created_files.append(fname)
    return created_files


def translate_setup(from_code, to_code):
    argostranslate.package.update_package_index()
    available_packages = argostranslate.package.get_available_packages()
    package_to_install = next(
        filter(
            lambda x: x.from_code == from_code and x.to_code == to_code,
            available_packages,
        )
    )
    argostranslate.package.install_from_path(package_to_install.download())


def translate_sentences(sents, from_code, to_code):
    return [argostranslate.translate.translate(s, from_code, to_code) for s in sents]


def write_anki_import(file_path, sentences, translation, audio_files, tags=None):
    assert len(sentences) == len(translation) == len(audio_files)
    with open(file_path, "w", encoding="utf-8") as f:
        if tags:
            f.write(TAGS.format(tags=tags) + "\n")

        for i, audio in enumerate(audio_files):
            a = AUDIO_FMT.format(fname=audio)
            f.write(f"{a}{FILE_DELIM}{sentences[i]}<br>{translation[i]}\n")


def transcribe(in_file, lang_code):
    model = whisper.load_model("small")
    result = model.transcribe(in_file, word_timestamps=True, **{"language": lang_code})
    return result


def main(
    source: str,
    input_language: str,
    output_language: str,
    audio_save_dir: Path,
    json_transcribe_file: Path,
    audio_buffer: float,
    save_json_file: Path,
):
    """
    source_file: the file to process
    input_language, output_language: the input anf output language codes
    audio_save_dir : where to save the audi clips
    json_transcribe_file: optional input file to use instead of doing transcribe with this script, needs word timestamps
    audio_buffer amount of time to add onto audio clips start and end
    save_json_file: location to save transcript json file after transcribe
    """
    if "youtube" in source and source.startswith("http"):
        tmp_dir = TemporaryDirectory()
        source_file = download_youtube_audio(source, tmp_dir.name)
    else:
        source_file = Path(source)
    
    # assert all files exist
    assert source_file.exists()
    assert audio_save_dir.exists() and audio_save_dir.is_dir()
    if json_transcribe_file:
        assert json_transcribe_file.exists()
    if save_json_file:
        assert save_json_file.exists()

    spacy_model = SPACY_MODELS.get(input_language)
    base_name = source_file.parts[-1].split(".")[0]

    spacy.prefer_gpu()
    es_nlp = spacy.load(spacy_model, exclude=["parser"])
    es_nlp.enable_pipe("senter")
    log.info("spacy loaded...")
    translate_setup(input_language, output_language)

    if json_transcribe_file:
        with open(json_transcribe_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        log.info("whisper transcribe loaded")
    else:
        log.info("start whisper transcribe")
        data = transcribe(str(source_file), input_language)
        log.info("whisper transcribe done")
        if save_json_file:
            with open(save_json_file, "w", encoding="utf-8") as f:
                json.dump(data, f)

    words_ts = build_words_with_ts(data)
    log.info("built sentence ts data...")

    src_txt = " ".join([w[0] for w in words_ts])
    doc = es_nlp(src_txt)
    sentence_ts = build_sentence_start_end(doc, words_ts, audio_buffer)
    _ts = [(str(s), str(e)) for (s, e, _) in sentence_ts]

    log.info("starting file split")
    created_files = split_video_into_audio_seg(
        source_file, _ts, base_name, audio_save_dir
    )
    sents = [t for (_s, _e, t) in sentence_ts]
    log.info("audio_created")
    log.info("starting translation")
    translations = translate_sentences(sents, input_language, output_language)

    log.info(f"writing anki to ./{base_name}.txt")
    write_anki_import(f"./{base_name}.txt", sents, translations, created_files)
    log.info("done")


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(message)s",
        datefmt="%H:%M:%S",
    )


if __name__ == "__main__":
    setup_logging()

    log.info("starting...")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "source", help="The full path to the video to process or Youtube video to download", type=str
    )
    parser.add_argument(
        "--input-language",
        "-i",
        help=f"Language code for input language ({'.'.join(SPACY_MODELS.keys())})",
        default="es",
        type=str,
    )
    parser.add_argument(
        "--output-language",
        "-o",
        help=f"Language code for output language ({'.'.join(SPACY_MODELS.keys())})",
        default="en",
        type=str,
    )
    parser.add_argument(
        "--audio-save-dir",
        "-s",
        help="Directory to save audio clips in",
        default="./out",
        type=Path,
    )
    parser.add_argument(
        "--json-transcribe-file",
        "-j",
        help="Path to load whisper's json transcription file, will skip doing a new transcription",
        type=Path,
    )
    parser.add_argument(
        "--audio-buffer",
        "-b",
        help="Time to add on to start and end of audio sentence clips",
        default=AUDIO_BUFFER,
        type=float,
    )
    parser.add_argument(
        "--save_json_file",
        "-w",
        help="location to save whisper's json data from transcription, can be used to reload and avoid rerunning transcription",
        type=Path,
    )

    args = parser.parse_args()
    main(**args.__dict__)
