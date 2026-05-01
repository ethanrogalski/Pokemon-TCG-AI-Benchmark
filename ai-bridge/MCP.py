import base64
import json
import os
import traceback
import socketio
import requests

from agent import get_ai_action  # swap this import to change AI providers

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8080")
USERNAME = os.environ.get("BOT_USERNAME", "monkey")
PASSWORD = os.environ.get("BOT_PASSWORD", "monkey")
GAME_ID = int(os.environ.get("GAME_ID", "1"))

PLAYER_TURN_PHASE = 2
PLAYER_TYPE_MAP = [1, 2]  # index -> PlayerType enum (TOP=1, BOTTOM=2)
SLOT_MAP = {"BOARD": 0, "ACTIVE": 1, "BENCH": 2}
MAX_ACTIONS_PER_TURN = 15

# ---------------------------------------------------------
# 1. Login
# ---------------------------------------------------------
resp = requests.post(f"{SERVER_URL}/v1/login", json={"name": USERNAME, "password": PASSWORD})
if not resp.ok or "token" not in resp.json():
    print("Login failed:", resp.json())
    exit(1)

token = resp.json()["token"]
print("Logged in.")

# ---------------------------------------------------------
# 2. Fetch card data for attack/HP lookups
# ---------------------------------------------------------
card_lookup = {}  # fullName -> card dict

try:
    r = requests.get(f"{SERVER_URL}/v1/cards/all", headers={"Authorization": f"Bearer {token}"})
    if r.ok:
        cards = r.json()
        if isinstance(cards, list):
            for c in cards:
                key = c.get("fullName") or c.get("name", "")
                if key:
                    card_lookup[key] = c
        print(f"Loaded {len(card_lookup)} cards.")
    else:
        print(f"Card data unavailable ({r.status_code}), AI will use general knowledge.")
except Exception as e:
    print(f"Card data fetch error: {e}")

# ---------------------------------------------------------
# 3. Game state handler
# ---------------------------------------------------------
actions_this_turn = 0
last_turn_number = -1
turn_passed = False


def on_state_change(data):
    global actions_this_turn, last_turn_number, turn_passed

    try:
        raw_state = base64.b64decode(data["stateData"]).decode("utf-8")
        parsed = json.loads(raw_state)
        players = parsed[0]
        game_state = parsed[1]

        phase = game_state.get("phase")
        active_player = game_state.get("activePlayer")
        turn = game_state.get("turn", 0)

        my_index = next((i for i, p in enumerate(players) if p["name"] == USERNAME), None)
        if my_index is None:
            return

        if phase != PLAYER_TURN_PHASE or active_player != my_index:
            return

        if turn != last_turn_number:
            actions_this_turn = 0
            turn_passed = False
            last_turn_number = turn

        if actions_this_turn >= MAX_ACTIONS_PER_TURN:
            if not turn_passed:
                print("Action limit reached, passing turn.")
                turn_passed = True
                sio.emit("game:action:passTurn", {"gameId": GAME_ID})
            return

        card_names = game_state.get("cardNames", [])
        my_player_type = PLAYER_TYPE_MAP[my_index]

        action_name, action_input = get_ai_action(players, game_state, my_index, card_names, card_lookup)
        actions_this_turn += 1

        if action_name == "play_card":
            hand_index = action_input.get("hand_index", 0)
            slot = SLOT_MAP.get(action_input.get("target_slot", "BOARD"), 0)
            bench_index = action_input.get("bench_index", 0)
            sio.emit("game:action:playCard", {
                "gameId": GAME_ID,
                "handIndex": hand_index,
                "target": {"player": my_player_type, "slot": slot, "index": bench_index},
            })

        elif action_name == "attack":
            sio.emit("game:action:attack", {"gameId": GAME_ID, "attack": action_input.get("attack_name", "")})

        elif action_name == "retreat":
            bench_index = action_input.get("bench_index", 0)
            sio.emit("game:action:retreatStart", {"gameId": GAME_ID})
            sio.emit("game:action:retreat", {"gameId": GAME_ID, "to": bench_index})

        elif action_name == "pass_turn":
            print(f"Passing: {action_input.get('reason', '')}")
            sio.emit("game:action:passTurn", {"gameId": GAME_ID})

    except Exception:
        print("[on_state_change error]")
        traceback.print_exc()


# ---------------------------------------------------------
# 4. Connect and run
# ---------------------------------------------------------
sio = socketio.Client()
sio.on(f"game[{GAME_ID}]:stateChange", on_state_change)


@sio.event
def connect():
    print("Connected to Twinleaf server!")
    sio.emit("game:rejoin", {"gameId": GAME_ID})
    print(f"Rejoined game {GAME_ID}.")


@sio.event
def disconnect():
    print("Disconnected from server.")


@sio.event
def connect_error(data):
    print("Connection failed:", data)


sio.connect(
    f"{SERVER_URL}?token={token}",
    transports=["websocket"],
    socketio_path="/socket.io",
)

sio.wait()
