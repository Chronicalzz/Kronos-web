import os
import subprocess
import shutil
import uuid
from flask import Flask, render_template, request, send_file, jsonify

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def check_dependency(exe):
    # This automatically finds 'ffmpeg' or 'yt-dlp' globally in cloud server path environments
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

    # Create unique file paths to handle multiple concurrent server users
    unique_id = str(uuid.uuid4())
    temp_file = os.path.join(BASE_DIR, f"temp_{unique_id}.webm")
    
    if fmt == "audio":
        output_file = os.path.join(BASE_DIR, f"kronos_{unique_id}.wav")
    else:
        output_file = os.path.join(BASE_DIR, f"kronos_{unique_id}.mov")

    ytdlp_bin = check_dependency("yt-dlp")
    ffmpeg_bin = check_dependency("ffmpeg")

    if not ytdlp_bin or not ffmpeg_bin:
        return jsonify({"error": "Server error: Dependencies missing from environment paths."}), 500

    try:
        # 1. Download via yt-dlp
        subprocess.run(
            [ytdlp_bin, "-f", "bestvideo+bestaudio/best", "-o", temp_file, url],
            check=True
        )

        # 2. Convert via FFmpeg (Preserves your exact After Effects optimizations)
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

        # Remove the source temporary video footprint
        if os.path.exists(temp_file):
            os.remove(temp_file)

        # Stream file delivery to the client
        response_stream = send_file(
            output_file, 
            as_attachment=True, 
            download_name=f"kronos_output{'.wav' if fmt == 'audio' else '.mov'}"
        )
        
        # Clean up the output file from the server immediately after delivery finishes
        @app.after_request
        def remove_file(response):
            try:
                if os.path.exists(output_file):
                    os.remove(output_file)
            except Exception:
                pass
            return response

        return response_stream

    except Exception as e:
        if os.path.exists(temp_file): os.remove(temp_file)
        if os.path.exists(output_file): os.remove(output_file)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)