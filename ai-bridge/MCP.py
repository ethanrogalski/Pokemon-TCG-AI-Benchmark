import base64
import json
import os
import sys
import traceback
import socketio
import requests
from dotenv import load_dotenv

load_dotenv()

from agent import get_ai_action, get_ai_prompt_response  # swap this import to change AI providers

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
        data = r.json()
        cards_list = data.get("cardsInfo", {}).get("cards", []) if isinstance(data, dict) else data
        for c in cards_list:
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
attack_committed = False
last_sent_prompt_id = None


def resolve_prompt(prompt, players, game_state, my_index, card_names, card_lookup):
    ptype = prompt.get("type", "")

    if ptype in ("Alert", "Coin flip", "WaitPrompt"):
        return True

    if ptype == "Choose prize":
        count = prompt.get("options", {}).get("min", 1)
        prizes = players[my_index].get("prizes", [])
        non_empty = [i for i, p in enumerate(prizes) if p.get("cards")]
        return non_empty[:count]

    if ptype == "Shuffle deck":
        deck_cards = players[my_index].get("deck", {}).get("cards", [])
        return list(range(len(deck_cards)))

    if ptype == "Attach energy":
        my_player_type = PLAYER_TYPE_MAP[my_index]
        active = players[my_index].get("active", {})
        slot = 1 if active.get("cards") else 2  # ACTIVE=1, BENCH=2
        return [{"to": {"player": my_player_type, "slot": slot, "index": 0}, "index": 0}]

    return get_ai_prompt_response(prompt, players, game_state, my_index, card_names, card_lookup)


def on_state_change(data):
    global actions_this_turn, last_turn_number, turn_passed, attack_committed, last_sent_prompt_id

    try:
        raw_state = base64.b64decode(data["stateData"]).decode("utf-8")
        parsed = json.loads(raw_state)
        players = parsed[0]
        game_state = parsed[1]

        my_index = next((i for i, p in enumerate(players) if p["name"] == USERNAME), None)
        if my_index is None:
            return

        if game_state.get("phase") == 7:  # GamePhase.FINISHED
            winner = game_state.get("winner", -1)
            winner_name = players[winner]["name"] if winner in (0, 1) else "draw"
            print(f"Game over! Winner: {winner_name}. Exiting.")
            sio.disconnect()
            sys.exit(0)

        card_names = game_state.get("cardNames", [])
        my_player_id = players[my_index].get("id")

        # Resolve any pending prompt first (can arrive in any phase)
        prompts = game_state.get("prompts", [])
        my_prompt = next(
            (p for p in prompts if p.get("playerId") == my_player_id and p.get("result") is None),
            None,
        )
        if my_prompt:
            prompt_id = my_prompt.get("id")
            if prompt_id == last_sent_prompt_id:
                return  # already sent resolve for this ID, waiting for server
            last_sent_prompt_id = prompt_id
            ptype = my_prompt.get("type", "")
            print(f"[prompt] id={prompt_id} type={ptype} — {my_prompt.get('message', '')}")
            # Dump full prompt for hard-to-debug types
            if ptype in ("Choose cards", "Choose pokemon"):
                opts = my_prompt.get("options", {})
                cards_data = my_prompt.get("cards", {}).get("cards", [])
                print(f"[prompt] RAW options={json.dumps(opts)}")
                print(f"[prompt] RAW cards ({len(cards_data)} total)={json.dumps(cards_data[:20])}")
                named = [(i, card_names[c] if isinstance(c, int) and c < len(card_names) else str(c))
                         for i, c in enumerate(cards_data)]
                print(f"[prompt] named cards: {named[:30]}")
            result = resolve_prompt(my_prompt, players, game_state, my_index, card_names, card_lookup)
            print(f"[prompt] sending result: {result!r}")

            def on_resolve_ack(data=None, *_):
                if isinstance(data, dict) and data.get("message") == "ok":
                    print(f"[prompt] SERVER ACCEPTED resolvePrompt id={prompt_id}")
                elif data is None or data is True:
                    print(f"[prompt] SERVER ACCEPTED resolvePrompt id={prompt_id}")
                else:
                    print(f"[prompt] SERVER REJECTED resolvePrompt id={prompt_id}: {data}")

            sio.emit("game:action:resolvePrompt", {"gameId": GAME_ID, "id": prompt_id, "result": result},
                     callback=on_resolve_ack)
            return
        else:
            last_sent_prompt_id = None

        phase = game_state.get("phase")
        active_player = game_state.get("activePlayer")
        turn = game_state.get("turn", 0)

        if phase != PLAYER_TURN_PHASE or active_player != my_index:
            return

        if turn != last_turn_number:
            actions_this_turn = 0
            turn_passed = False
            attack_committed = False
            last_turn_number = turn

        if attack_committed or turn_passed:
            return

        if actions_this_turn >= MAX_ACTIONS_PER_TURN:
            if not turn_passed:
                print("Action limit reached, passing turn.")
                turn_passed = True
                sio.emit("game:action:passTurn", {"gameId": GAME_ID})
            return

        my_player_type = PLAYER_TYPE_MAP[my_index]

        action_name, action_input = get_ai_action(players, game_state, my_index, card_names, card_lookup, actions_this_turn)
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
            attack_committed = True
            sio.emit("game:action:attack", {"gameId": GAME_ID, "attack": action_input.get("attack_name", "")})

        elif action_name == "retreat":
            attack_committed = True  # retreat also ends the turn
            bench_index = action_input.get("bench_index", 0)
            sio.emit("game:action:retreatStart", {"gameId": GAME_ID})
            sio.emit("game:action:retreat", {"gameId": GAME_ID, "to": bench_index})

        elif action_name == "pass_turn":
            turn_passed = True
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
