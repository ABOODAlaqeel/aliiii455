from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import uuid

app = Flask(__name__)
CORS(app)

# مسار ملف الكوكيز (قم بتصديره من متصفحك واحفظه كـ cookies.txt في جذر المشروع)
COOKIE_FILE = os.path.join(os.getcwd(), "cookies.txt")

# مجلد التخزين المؤقت للملفات
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# إعدادات yt_dlp المشتركة لمحاكاة متصفح مسجّل دخول
common_ydl_opts = {
    'quiet': True,
    'cookiefile': COOKIE_FILE,
    'http_headers': {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/115.0.0.0 Safari/537.36'
        )
    }
}

def clean_youtube_url(url):
    if "youtu.be" in url:
        vid = url.split('/')[-1].split('?')[0]
        return f"https://www.youtube.com/watch?v={vid}"
    if "youtube.com" in url:
        return url.split('&')[0]
    return url

@app.route('/')
def home():
    return jsonify({'status': 'Server is up and running!'})

@app.route('/video-info', methods=['POST'])
def video_info():
    data = request.get_json() or {}
    if 'url' not in data or not data['url']:
        return jsonify({'error': 'Missing "url" in request body'}), 400

    url = clean_youtube_url(data['url'])
    ydl_opts = {
        **common_ydl_opts,
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
    data = request.get_json() or {}
    if 'url' not in data or not data['url'] or 'format_id' not in data:
        return jsonify({'error': 'Missing "url" or "format_id" in request'}), 400

    url = clean_youtube_url(data['url'])
    format_id = data['format_id']
    temp_file = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex}.mp4")

    ydl_opts = {
        **common_ydl_opts,
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
    data = request.get_json() or {}
    if 'url' not in data or not data['url']:
        return jsonify({'error': 'Missing "url" in request body'}), 400

    url = clean_youtube_url(data['url'])
    temp_file = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex}.mp3")

    ydl_opts = {
        **common_ydl_opts,
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
