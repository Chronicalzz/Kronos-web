import os
import subprocess
import shutil
import uuid
from flask import Flask, render_template, request, send_file, jsonify

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def check_dependency(exe):
    # Automatically tracks down 'ffmpeg' or 'yt-dlp' on Render's Linux paths
    return shutil.which(exe)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/download", methods=["POST"])
def start_download():
    data = request.json or {}
    url = data.get("url")
    fmt = data.get("format", "audio")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    # Generate unique filenames to prevent multi-user collisions in the cloud
    unique_id = str(uuid.uuid4())
    temp_file = os.path.join(BASE_DIR, f"temp_{unique_id}.webm")
    
    if fmt == "audio":
        output_file = os.path.join(BASE_DIR, f"kronos_{unique_id}.wav")
        download_name = "kronos_output.wav"
    else:
        output_file = os.path.join(BASE_DIR, f"kronos_{unique_id}.mov")
        download_name = "kronos_output.mov"

    ytdlp_bin = check_dependency("yt-dlp")
    ffmpeg_bin = check_dependency("ffmpeg")

    if not ytdlp_bin or not ffmpeg_bin:
        return jsonify({"error": "Server environment missing core dependencies."}), 500

    try:
        # 1. Fetch via yt-dlp (works flawlessly for TikTok, YouTube, etc.)
        # Added a generic User-Agent header to avoid bot-blocking walls
        subprocess.run(
            [ytdlp_bin, "--user-agent", "Mozilla/5.0", "-f", "bestvideo+bestaudio/best", "-o", temp_file, url],
            check=True
        )

        # 2. Convert via FFmpeg with your exact production codecs
        if fmt == "audio":
            subprocess.run([
                ffmpeg_bin, "-y", "-i", temp_file,
                "-vn", "-acodec", "pcm_s16le", "-ar", "48000",
                output_file
            ], check=True)
        else:
            subprocess.run([
                ffmpeg_bin, "-y", "-i", temp_file,
                "-c:v", "prores_ks", "-profile:v", "3",
                "-c:a", "pcm_s16le",
                output_file
            ], check=True)

        # Clean up the original raw download immediately
        if os.path.exists(temp_file):
            os.remove(temp_file)

        if not os.path.exists(output_file):
            return jsonify({"error": "File conversion layer failed to output data."}), 500

        # 3. Stream & Auto-Delete Solution
        # This generator reads the file, passes it to the user, then cleans up the server storage.
        def generate_and_cleanup():
            with open(output_file, 'rb') as target_file:
                yield from target_file
            try:
                os.remove(output_file)
            except Exception as e:
                print(f"Error removing file: {e}")

        return app.response_class(
            generate_and_cleanup(),
            headers={
                "Content-Disposition": f"attachment; filename={download_name}",
                "Content-Type": "application/octet-stream"
            }
        )

    except subprocess.CalledProcessError as e:
        # Handle media extraction routine specific faults elegantly
        if os.path.exists(temp_file): os.remove(temp_file)
        if os.path.exists(output_file): os.remove(output_file)
        return jsonify({"error": f"Extraction backend failed. Link might be private or unsupported. Details: {e}"}), 500
    except Exception as e:
        if os.path.exists(temp_file): os.remove(temp_file)
        if os.path.exists(output_file): os.remove(output_file)
        return jsonify({"error": f"Unexpected server exception: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
