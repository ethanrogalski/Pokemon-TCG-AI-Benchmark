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
# CardTarget.player is relative to the acting player:
#   BOTTOM_PLAYER (2) = the acting player's own Pokemon
#   TOP_PLAYER    (1) = the opponent's Pokemon
MY_PLAYER_TYPE = 2   # PlayerType.BOTTOM_PLAYER
OPP_PLAYER_TYPE = 1  # PlayerType.TOP_PLAYER
SLOT_MAP = {"BOARD": 0, "ACTIVE": 1, "BENCH": 2}
MAX_ACTIONS_PER_TURN = 30

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
    r = requests.get(f"{SERVER_URL}/v1/cards/all", headers={"Auth-Token": token})
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
chat_sent_this_turn = False
supporter_played_this_turn = False
energy_attached_this_turn = False
last_sent_prompt_id = None
last_rejection = None
last_prompt_rejection = None
last_rejected_prompt_id = None
_current_context = None  # (players, game_state, my_index, card_names) — cached for rejection callbacks
_waiting_for_prompt_ack = False  # True after sending resolvePrompt, until ack fires
prompt_fail_count = 0            # consecutive rejections of the current prompt
_server_busy = False             # True when server returned ACTION_IN_PROGRESS; cleared on next stateChange

# Prompts resolved auto
# - "Alert", "Coin flip", "WaitPrompt" = just acknowledge
# - "Choose prize" = pick the first non-empty prize(s)
# - "Shuffle deck" = shuffle all cards in deck
# - "Attach energy" = attach the first energy in hand to active if empty, otherwise - should prolly not be auto
# - Everything else sent to AI
def resolve_prompt(prompt, players, game_state, my_index, card_names, card_lookup, prompt_fail_count=0):
    ptype = prompt.get("type", "")

    if ptype in ("Alert", "Coin flip", "WaitPrompt", "Show mulligan", "Show cards", "Confirm cards"):
        return True

    if ptype == "Choose prize":
        count = prompt.get("options", {}).get("min", 1)
        prizes = players[my_index].get("prizes", [])
        non_empty = [i for i, p in enumerate(prizes) if p.get("cards")]
        return non_empty[:count]

    if ptype == "Shuffle deck":
        deck_cards = players[my_index].get("deck", {}).get("cards", [])
        return list(range(len(deck_cards)))

    return get_ai_prompt_response(prompt, players, game_state, my_index, card_names, card_lookup, last_rejection=last_prompt_rejection, prompt_fail_count=prompt_fail_count)


def _is_rejection(ack_data):
    if ack_data is None or ack_data is True:
        return False
    if isinstance(ack_data, dict) and ack_data.get("message") == "ok":
        return False
    return True


def _take_action(players, game_state, my_index, card_names):
    global actions_this_turn, turn_passed, attack_committed, chat_sent_this_turn, supporter_played_this_turn, energy_attached_this_turn, last_rejection

    if attack_committed or turn_passed:
        return

    if _waiting_for_prompt_ack or _server_busy:
        return

    if actions_this_turn >= MAX_ACTIONS_PER_TURN:
        if not turn_passed:
            print("Action limit reached, passing turn.")
            turn_passed = True
            sio.emit("game:action:passTurn", {"gameId": GAME_ID})
        return

    action_name, action_input = get_ai_action(
        players, game_state, my_index, card_names, card_lookup, actions_this_turn,
        last_rejection=last_rejection,
        chat_sent_this_turn=chat_sent_this_turn,
        supporter_played_this_turn=supporter_played_this_turn,
        energy_attached_this_turn=energy_attached_this_turn,
    )
    last_rejection = None
    actions_this_turn += 1

    if action_name == "play_card":
        hand_index = action_input.get("hand_index", 0)
        slot = SLOT_MAP.get(action_input.get("target_slot", "BOARD"), 0)
        bench_index = action_input.get("bench_index", 0)

        hand_cards = players[my_index]["hand"]["cards"]
        _card_name = card_names[hand_cards[hand_index]] if hand_index < len(hand_cards) and isinstance(hand_cards[hand_index], int) and hand_cards[hand_index] < len(card_names) else ""
        _is_supporter = card_lookup.get(_card_name, {}).get("trainerType") == 1
        _is_energy = card_lookup.get(_card_name, {}).get("superType") == 3

        def on_play_ack(ack_data=None, *_):
            global last_rejection, supporter_played_this_turn, energy_attached_this_turn, _server_busy
            if _is_rejection(ack_data):
                reason = f"play_card(hand={hand_index}, slot={action_input.get('target_slot')}) rejected by server: {ack_data}"
                print(f"[action] REJECTED {reason}")
                if isinstance(ack_data, dict) and ack_data.get("data") in ("ACTION_IN_PROGRESS", "NOT_YOUR_TURN"):
                    _server_busy = True
                    return
                last_rejection = reason
                _take_action(players, game_state, my_index, card_names)
            else:
                if _is_supporter:
                    supporter_played_this_turn = True
                if _is_energy:
                    energy_attached_this_turn = True
                print(f"[action] play_card hand={hand_index} accepted")

        sio.emit("game:action:playCard", {
            "gameId": GAME_ID,
            "handIndex": hand_index,
            "target": {"player": MY_PLAYER_TYPE, "slot": slot, "index": bench_index},
        }, callback=on_play_ack)

    elif action_name == "attack":
        attack_name = action_input.get("attack_name", "")
        attack_committed = True

        chat_msg = action_input.get("message", "")[:256]
        if not chat_sent_this_turn and chat_msg:
            print(f"[chat] Attack chat: {chat_msg!r}")
            sio.emit("game:action:appendLog", {"gameId": GAME_ID, "message": chat_msg})
            chat_sent_this_turn = True

        def on_attack_ack(ack_data=None, *_):
            global attack_committed, last_rejection, _server_busy
            if _is_rejection(ack_data):
                reason = f"attack({attack_name!r}) rejected by server: {ack_data}"
                print(f"[action] REJECTED {reason}")
                attack_committed = False
                if isinstance(ack_data, dict) and ack_data.get("data") in ("ACTION_IN_PROGRESS", "NOT_YOUR_TURN"):
                    _server_busy = True
                    return
                last_rejection = reason
                _take_action(players, game_state, my_index, card_names)
            else:
                print(f"[action] attack {attack_name!r} accepted")

        sio.emit("game:action:attack", {"gameId": GAME_ID, "attack": attack_name}, callback=on_attack_ack)

    elif action_name == "retreat":
        bench_index = action_input.get("bench_index", 0)
        attack_committed = True

        def on_retreat_ack(ack_data=None, *_):
            global attack_committed, last_rejection, _server_busy
            if _is_rejection(ack_data):
                reason = f"retreat(bench={bench_index}) rejected by server: {ack_data}"
                print(f"[action] REJECTED {reason}")
                attack_committed = False
                if isinstance(ack_data, dict) and ack_data.get("data") in ("ACTION_IN_PROGRESS", "NOT_YOUR_TURN"):
                    _server_busy = True
                    return
                last_rejection = reason
                _take_action(players, game_state, my_index, card_names)
            else:
                print(f"[action] retreat to bench={bench_index} accepted")
                attack_committed = False  # retreat doesn't end the turn; next stateChange can trigger attack

        sio.emit("game:action:retreatStart", {"gameId": GAME_ID})
        sio.emit("game:action:retreat", {"gameId": GAME_ID, "to": bench_index}, callback=on_retreat_ack)

    elif action_name == "send_chat_message":
        msg = action_input.get("message", "")[:256]
        print(f"[chat] Sending: {msg!r}")
        sio.emit("game:action:appendLog", {"gameId": GAME_ID, "message": msg})
        chat_sent_this_turn = True
        _take_action(players, game_state, my_index, card_names)

    elif action_name == "pass_turn":
        turn_passed = True
        reason_text = action_input.get("reason", "")
        print(f"Passing: {reason_text}")
        if reason_text:
            sio.emit("game:action:appendLog", {"gameId": GAME_ID, "message": reason_text[:256]})
            chat_sent_this_turn = True

        def on_pass_ack(ack_data=None, *_):
            global turn_passed, last_rejection, _server_busy
            if _is_rejection(ack_data):
                reason = f"pass_turn rejected by server: {ack_data}"
                print(f"[action] REJECTED {reason}")
                turn_passed = False
                if isinstance(ack_data, dict) and ack_data.get("data") in ("ACTION_IN_PROGRESS", "NOT_YOUR_TURN"):
                    _server_busy = True
                    return
                last_rejection = reason
                _take_action(players, game_state, my_index, card_names)
            else:
                print("[action] pass_turn accepted")

        sio.emit("game:action:passTurn", {"gameId": GAME_ID}, callback=on_pass_ack)


def on_state_change(data):
    global actions_this_turn, last_turn_number, turn_passed, attack_committed, chat_sent_this_turn, supporter_played_this_turn, energy_attached_this_turn, last_sent_prompt_id, last_rejection, last_prompt_rejection, last_rejected_prompt_id, _current_context, _waiting_for_prompt_ack, prompt_fail_count, _server_busy

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
        _current_context = (players, game_state, my_index, card_names)

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
            if prompt_id != last_rejected_prompt_id:
                last_prompt_rejection = None  # different prompt — stale rejection doesn't apply
                prompt_fail_count = 0
            last_sent_prompt_id = prompt_id
            _waiting_for_prompt_ack = True  # set before any prints so concurrent threads see it immediately
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
            result = resolve_prompt(my_prompt, players, game_state, my_index, card_names, card_lookup, prompt_fail_count=prompt_fail_count)
            print(f"[prompt] sending result: {result!r}")

            def on_resolve_ack(ack_data=None, *_):
                global last_sent_prompt_id, last_prompt_rejection, last_rejected_prompt_id, _waiting_for_prompt_ack, prompt_fail_count
                _waiting_for_prompt_ack = False
                if _is_rejection(ack_data):
                    print(f"[prompt] SERVER REJECTED resolvePrompt id={prompt_id}: {ack_data}")
                    last_prompt_rejection = ack_data.get("data", str(ack_data)) if isinstance(ack_data, dict) else str(ack_data)
                    last_rejected_prompt_id = prompt_id
                    last_sent_prompt_id = None  # allow retry on next stateChange
                    prompt_fail_count += 1
                else:
                    print(f"[prompt] SERVER ACCEPTED resolvePrompt id={prompt_id}")
                    last_prompt_rejection = None
                    last_rejected_prompt_id = None
                    prompt_fail_count = 0

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

        if turn < last_turn_number:
            return  # stale stateChange from a previous turn — discard

        if turn != last_turn_number:
            actions_this_turn = 0
            turn_passed = False
            attack_committed = False
            chat_sent_this_turn = False
            supporter_played_this_turn = False
            energy_attached_this_turn = False
            last_rejection = None
            _waiting_for_prompt_ack = False
            prompt_fail_count = 0
            _server_busy = False
            last_turn_number = turn

        if _waiting_for_prompt_ack:
            return

        _server_busy = False
        _take_action(players, game_state, my_index, card_names)

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

