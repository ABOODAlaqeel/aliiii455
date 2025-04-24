from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import uuid

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def clean_youtube_url(url):
    if "youtu.be" in url:
        video_id = url.split('/')[-1].split('?')[0]
        return f"https://www.youtube.com/watch?v={video_id}"
    elif "youtube.com" in url:
        return url.split('&')[0]
    return url

@app.route('/')
def home():
    return "Welcome to the YouTube Downloader API! Use /video-info to get video details and /download-video or /download-audio to download."

@app.route('/video-info', methods=['POST'])
def video_info():
    data = request.get_json()
    url = clean_youtube_url(data.get('url'))

    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = [{
            'format_id': f['format_id'],
            'ext': f['ext'],
            'resolution': f.get('height'),
            'filesize': f.get('filesize'),
            'has_audio': f.get('acodec') != 'none',
            'has_video': f.get('vcodec') != 'none',
            'url': f['url']
        } for f in info['formats']]

        return jsonify({
            'video_id': info.get('id'),
            'title': info.get('title'),
            'uploader': info.get('uploader'),
            'thumbnail': info.get('thumbnail'),
            'duration': info.get('duration'),
            'formats': formats,
            'subtitles': info.get('subtitles'),
            'auto_subtitles': info.get('automatic_captions')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/download-video', methods=['POST'])
def download_video():
    data = request.get_json()
    url = clean_youtube_url(data.get('url'))
    format_id = data.get('format_id')

    temp_file = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex}.mp4")

    ydl_opts = {
        'quiet': True,
        'format': format_id,
        'outtmpl': temp_file,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        return send_file(temp_file, as_attachment=True, download_name="video.mp4", mimetype="video/mp4")
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/download-audio', methods=['POST'])
def download_audio():
    data = request.get_json()
    url = clean_youtube_url(data.get('url'))

    temp_file = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex}.mp3")

    ydl_opts = {
        'quiet': True,
        'format': 'bestaudio/best',
        'outtmpl': temp_file,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        return send_file(temp_file, as_attachment=True, download_name="audio.mp3", mimetype="audio/mp3")
    except Exception as e:
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=10000)
