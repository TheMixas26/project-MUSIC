import os
import random
from flask import Flask, jsonify, send_file
from server_mdns import register_mdns

app = Flask(__name__)

MUSIC_ROOT = os.path.expanduser("~/Музыка/Music")   # /home/amoderny/Музыка/Music

tracks = []
track_index = 0

state = {
    "power": False,
    "track": None,
    "volume": 1.0
}


def scan_music():
    global tracks
    tracks = []  # Очищаем список перед сканированием
    
    print(f"Сканируем папку: {MUSIC_ROOT}")
    folder_count = 0
    
    for root, dirs, files in os.walk(MUSIC_ROOT):
        folder_count += 1
        mp3_count = 0
        
        for file in files:
            if file.lower().endswith(('.mp3', '.flac', '.ogg', '.wav', '.m4a')):
                full = os.path.join(root, file)
                tracks.append(full)
                mp3_count += 1
        
        if mp3_count > 0:
            print(f"Папка {root}: найдено {mp3_count} файлов")
    
    tracks.sort()
    print(f"Всего просканировано папок: {folder_count}")
    print(f"Всего найдено треков: {len(tracks)}")


def get_track_name(path):
    return os.path.basename(path)


def current_track():
    if not tracks:
        return None
    return tracks[track_index]


@app.route("/state")
def get_state():
    return jsonify({
        "power": state["power"],
        "track": get_track_name(state["track"]) if state["track"] else "",
        "volume": state["volume"]
    })


@app.route("/finished")
def finished():
    global track_index

    track_index = (track_index + 1) % len(tracks)
    state["track"] = tracks[track_index]

    return "ok"


@app.route("/play")
def play():
    if not tracks:
        return "no tracks"

    state["power"] = True

    if state["track"] is None:
        state["track"] = tracks[track_index]

    return "ok"


@app.route("/stop")
def stop():
    state["power"] = False
    return "ok"


@app.route("/next")
def next_track():
    global track_index

    track_index = (track_index + 1) % len(tracks)
    state["track"] = tracks[track_index]

    return "ok"


@app.route("/prev")
def prev_track():
    global track_index

    track_index = (track_index - 1) % len(tracks)
    state["track"] = tracks[track_index]

    return "ok"


@app.route("/play/<int:id>")
def play_id(id):
    global track_index

    if id < 0 or id >= len(tracks):
        return "bad id"

    track_index = id
    state["track"] = tracks[track_index]
    state["power"] = True

    return "ok"


@app.route("/tracks")
def list_tracks():
    result = []

    for i, t in enumerate(tracks):
        result.append({
            "id": i,
            "name": get_track_name(t)
        })

    return jsonify(result)

@app.route("/volume/<int:vol>")
def set_volume(vol):
    if 0 <= vol <= 100:
        state["volume"] = vol/100
        return "ok"

    else:
        return "bad volume", 400
    


@app.route("/music/<name>")
def serve_music(name):

    for path in tracks:
        if os.path.basename(path) == name:
            return send_file(path)

    return "not found", 404


if __name__ == "__main__":

    scan_music()




    if not tracks:
        print("No music found")

    else:
        state["track"] = tracks[0]

    register_mdns(port=8000, service_name="musicplayer")
    app.run(host="0.0.0.0", port=8000)
