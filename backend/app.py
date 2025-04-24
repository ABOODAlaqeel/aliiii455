from flask import Flask, request, jsonify, Response, stream_with_context, send_from_directory
from flask_cors import CORS
import yt_dlp, requests, os

app = Flask(__name__, static_folder='temp_downloads', static_url_path='/static')
CORS(app)

# مسار ملف الكوكيز
COOKIE_FILE = os.path.join(os.getcwd(), "cookies.txt")

# إعدادات yt_dlp العامة
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

@app.route('/', methods=['GET'])
def index():
    return jsonify({'message': 'مرحباً بك في YouTube-DL API. استخدم /video-info.'})

@app.errorhandler(400)
def bad_request(err): return jsonify({'error': err.description}), 400
@app.errorhandler(404)
def not_found(err):    return jsonify({'error': err.description}), 404

@app.route('/video-info', methods=['POST'])
def video_info():
    data = request.get_json() or {}
    url = data.get('url')
    if not url:
        return jsonify({'error': 'Missing "url"'}), 400

    url = clean_youtube_url(url)
    opts = {
        **common_ydl_opts,
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        video_only = [f for f in info['formats'] if f.get('vcodec') != 'none' and f.get('acodec') == 'none']
        audio_only = [f for f in info['formats'] if f.get('acodec') != 'none' and f.get('vcodec') == 'none']

        for f in info['formats']:
            has_audio = f.get('acodec') != 'none'
            has_video = f.get('vcodec') != 'none'
            entry = {
                'format_id': f['format_id'],
                'ext': f['ext'],
                'resolution': f.get('height'),
                'filesize': f.get('filesize'),
                'merged': False
            }
            if has_audio and has_video:
                entry['type'] = 'video+audio'
            elif has_video:
                entry['type'] = 'video-only'
            elif has_audio:
                entry['type'] = 'audio-only'
            else:
                continue
            formats.append(entry)

        # إضافة صيغ مدموجة يدوياً (video-only + audio-only)
        for vf in video_only:
            af = next((a for a in audio_only if a['ext'] == 'm4a'), None)
            if af:
                formats.append({
                    'format_id': f"{vf['format_id']}+{af['format_id']}",
                    'ext': 'mp4',
                    'resolution': vf.get('height'),
                    'filesize': (vf.get('filesize') or 0) + (af.get('filesize') or 0),
                    'type': 'video+audio',
                    'merged': True
                })

        # التراجم اليدوية
        subtitles = []
        for lang, subs in info.get('subtitles', {}).items():
            for sub in subs:
                subtitles.append({
                    'language': lang,
                    'ext': sub.get('ext'),
                    'url': sub.get('url'),
                })

        # التراجم الآلية
        automatic_subtitles = []
        for lang, subs in info.get('automatic_captions', {}).items():
            for sub in subs:
                automatic_subtitles.append({
                    'language': lang,
                    'ext': sub.get('ext'),
                    'url': sub.get('url'),
                })

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
        return jsonify({'error': str(e)}), 400

def stream_url(url, filename):
    """Proxy streaming helper"""
    r = requests.get(url, stream=True)
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    return Response(
        stream_with_context(r.iter_content(chunk_size=8192)),
        headers=headers,
        content_type=r.headers.get('Content-Type', 'application/octet-stream')
    )

@app.route('/download-video', methods=['GET'])
def download_video():
    url    = request.args.get('url')
    fmt    = request.args.get('format_id')
    merged = request.args.get('merged', 'false').lower() == 'true'
    if not url or not fmt:
        return jsonify({'error':'Missing "url" or "format_id"'}),400

    url = clean_youtube_url(url)
    with yt_dlp.YoutubeDL(common_ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if merged and '+' in fmt:
        vf_id, af_id = fmt.split('+')
        vf = next(f for f in info['formats'] if f['format_id'] == vf_id)
        af = next(f for f in info['formats'] if f['format_id'] == af_id)
        temp_dir = 'temp_downloads'
        os.makedirs(temp_dir, exist_ok=True)
        output = os.path.join(temp_dir, f"{info.get('id')}_merged.mp4")
        os.system(f'ffmpeg -y -i "{vf["url"]}" -i "{af["url"]}" -c:v copy -c:a aac "{output}"')
        return send_from_directory(temp_dir, os.path.basename(output), as_attachment=True)
    else:
        entry = next((f for f in info['formats'] if f['format_id'] == fmt), None)
        if not entry or not entry.get('url'):
            return jsonify({'error':'Format not found'}),404
        filename = f"{info.get('title')}.{entry['ext']}"
        return stream_url(entry['url'], filename)

@app.route('/download-audio', methods=['GET'])
def download_audio():
    url = request.args.get('url')
    if not url:
        return jsonify({'error':'Missing "url"'}),400

    url = clean_youtube_url(url)
    opts = {**common_ydl_opts, 'format':'bestaudio/best','skip_download':True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entry = next((f for f in info['formats'] if f.get('acodec')!='none'), None)
    if not entry or not entry.get('url'):
        return jsonify({'error':'Audio format not found'}),404
    filename = f"{info.get('title')}.mp3"
    return stream_url(entry['url'], filename)

@app.route('/download-subtitle', methods=['GET'])
def download_subtitle():
    url      = request.args.get('url')
    language = request.args.get('language')
    auto     = request.args.get('auto','0') == '1'
    if not url or not language:
        return jsonify({'error':'Missing "url" or "language"'}),400

    url = clean_youtube_url(url)
    opts = {
        **common_ydl_opts,
        'skip_download': True,
        'writesubtitles': not auto,
        'writeautomaticsub': auto
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    subs = info['automatic_captions'] if auto else info['subtitles']
    tracks = subs.get(language, [])
    if not tracks:
        return jsonify({'error':'Subtitle not found'}),404
    sub = tracks[0]
    filename = f"{info.get('title')}_{language}{'_auto' if auto else ''}.{sub.get('ext')}"
    return stream_url(sub.get('url'), filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(debug=True, host='0.0.0.0', port=port)
