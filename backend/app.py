from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import yt_dlp
import requests
import os
from urllib.parse import quote

app = Flask(__name__)
CORS(app)

# إعداد ملف الكوكيز
COOKIE_FILE = os.path.join(os.getcwd(), "cookies.txt")
if not os.path.exists(COOKIE_FILE):
    open(COOKIE_FILE, "w").close()

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

def clean_youtube_url(url: str) -> str:
    if "youtu.be" in url:
        vid = url.rsplit("/", 1)[-1].split("?")[0]
        return f"https://www.youtube.com/watch?v={vid}"
    if "youtube.com" in url:
        return url.split("&")[0]
    return url

@app.route('/video-info', methods=['POST'])
def video_info():
    try:
        data = request.get_json() or {}
        url  = data.get('url')
        if not url:
            return jsonify({'error': 'Missing "url"'}), 400

        url = clean_youtube_url(url)
        opts = {
            **common_ydl_opts,
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        for f in info.get('formats', []):
            hasA = f.get('acodec') != 'none'
            hasV = f.get('vcodec') != 'none'
            if not hasA and not hasV:
                continue
            formats.append({
                'format_id': f['format_id'],
                'ext': f['ext'],
                'resolution': f.get('height'),
                'filesize': f.get('filesize'),
                'type': 'video+audio' if hasA and hasV else 'video-only' if hasV else 'audio-only'
            })

        subtitles = [
            {'language': lang, 'ext': sub['ext'], 'url': sub['url']}
            for lang, subs in info.get('subtitles', {}).items() for sub in subs
        ]
        automatic_subtitles = [
            {'language': lang, 'ext': sub['ext'], 'url': sub['url']}
            for lang, subs in info.get('automatic_captions', {}).items() for sub in subs
        ]

        return jsonify({
            'video_id': info.get('id'),
            'title': info.get('title'),
            'uploader': info.get('uploader'),
            'thumbnail': info.get('thumbnail'),
            'duration': info.get('duration'),
            'formats': formats,
            'subtitles': subtitles,
            'automatic_subtitles': automatic_subtitles
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def stream_url(url, filename, content_type=None):
    headers = common_ydl_opts['http_headers']
    r = requests.get(url, stream=True, headers=headers, timeout=30)
    ct = content_type or r.headers.get('Content-Type', 'application/octet-stream')
    dispo = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(
        stream_with_context(r.iter_content(8192)),
        headers={'Content-Disposition': dispo},
        content_type=ct
    )

@app.route('/download-video', methods=['GET'])
def download_video():
    try:
        url = request.args.get('url')
        fmt = request.args.get('format_id')
        if not url or not fmt:
            return jsonify({'error': 'Missing "url" or "format_id"'}), 400

        url = clean_youtube_url(url)
        with yt_dlp.YoutubeDL(common_ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        entry = next((f for f in info['formats'] if f['format_id'] == fmt), None)
        if not entry or not entry.get('url'):
            return jsonify({'error': 'Format not found'}), 404

        filename = f"{info['title']}.{entry['ext']}"
        return stream_url(entry['url'], filename)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download-audio', methods=['GET'])
def download_audio():
    try:
        url = request.args.get('url')
        if not url:
            return jsonify({'error': 'Missing "url"'}), 400

        url = clean_youtube_url(url)
        opts = {**common_ydl_opts, 'format': 'bestaudio/best', 'skip_download': True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        entry = next((f for f in info['formats'] if f.get('acodec') != 'none'), None)
        if not entry or not entry.get('url'):
            return jsonify({'error': 'Audio format not found'}), 404

        filename = f"{info['title']}.mp3"
        return stream_url(entry['url'], filename, content_type='audio/mpeg')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download-subtitle', methods=['GET'])
def download_subtitle():
    try:
        url = request.args.get('url')
        language = request.args.get('language')
        auto = request.args.get('auto', '0').lower() in ('1', 'true')
        if not url or not language:
            return jsonify({'error': 'Missing "url" or "language"'}), 400

        url = clean_youtube_url(url)
        opts = {
            **common_ydl_opts,
            'skip_download': True,
            'writesubtitles': not auto,
            'writeautomaticsub': auto
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        subs = (info['automatic_captions'] if auto else info['subtitles']).get(language, [])
        if not subs:
            return jsonify({'error': 'Subtitle not found'}), 404

        sub = subs[0]
        fn = f"{info['title']}_{language}{'_auto' if auto else ''}.{sub['ext']}"
        return stream_url(sub['url'], fn, content_type='text/plain; charset=utf-8')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
