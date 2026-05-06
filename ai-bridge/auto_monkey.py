"""
auto_monkey.py

This script implements monkey so that it auto accepts game invites and plays using the AI engine.
The deck is chosen by us (manually).
If game is ongoing probably use MCP.py instead.

Usage:
    python auto_monkey.py

Optional env vars (in .env):
    SERVER_URL   — defaults to http://localhost:8080
    BOT_USERNAME — defaults to monkey
    BOT_PASSWORD — defaults to monkey
    DECK_ID      — ID of the deck monkey should use (defaults to first deck found)
"""

import base64
import json
import os
import sys
import traceback
import threading
import socketio
import requests
from dotenv import load_dotenv

load_dotenv()

from agent import get_ai_action, get_ai_prompt_response

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8080")
USERNAME = os.environ.get("BOT_USERNAME", "monkey")
PASSWORD = os.environ.get("BOT_PASSWORD", "monkey")

PLAYER_TURN_PHASE = 2
MY_PLAYER_TYPE = 2
OPP_PLAYER_TYPE = 1
SLOT_MAP = {"BOARD": 0, "ACTIVE": 1, "BENCH": 2}
MAX_ACTIONS_PER_TURN = 30

# ---------------------------------------------------------
# 1. Login
# ---------------------------------------------------------
resp = requests.post(f"{SERVER_URL}/v1/login", json={"name": USERNAME, "password": PASSWORD})
if not resp.ok or "token" not in resp.json():
    print("Login failed:", resp.json())
    sys.exit(1)

token = resp.json()["token"]
print(f"Logged in as {USERNAME}.")

# ---------------------------------------------------------
# 2. Fetch card data
# ---------------------------------------------------------
card_lookup = {}
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
# 3. Fetch monkey's deck (for accepting game invitations)
# ---------------------------------------------------------
bot_deck = []
try:
    r = requests.get(f"{SERVER_URL}/v1/decks/list", headers={"Auth-Token": token})
    if r.ok:
        decks = r.json().get("decks", [])
        if not decks:
            print("No decks found for monkey. Please create a deck in the UI first.")
            sys.exit(1)
        preferred_id = int(os.environ.get("DECK_ID", "8"))
        deck_obj = next((d for d in decks if d.get("id") == preferred_id), decks[0])
        raw_cards = deck_obj.get("cards", "[]")
        bot_deck = json.loads(raw_cards) if isinstance(raw_cards, str) else raw_cards
        print(f"Using deck: {deck_obj.get('name', 'Unknown')} ({len(bot_deck)} cards)")
    else:
        print(f"Failed to fetch decks ({r.status_code}). Make sure monkey has at least one deck.")
        sys.exit(1)
except Exception as e:
    print(f"Deck fetch error: {e}")
    sys.exit(1)

# ---------------------------------------------------------
# 4. Game state (reset between games)
# ---------------------------------------------------------
GAME_ID = None

actions_this_turn = 0
last_turn_number = -1
turn_passed = False
attack_committed = False
chat_sent_this_turn = False
supporter_played_this_turn = False
energy_attached_this_turn = False
last_sent_prompt_id = None
last_rejection = None
rejected_this_turn = ["This is a list of actions you have tried to take that have been rejected. Do not try to play these actions again. This list will clear once you perform an action that is valid and accepted by the server."]
last_prompt_rejection = None
last_rejected_prompt_id = None
_current_context = None
_waiting_for_prompt_ack = False  # True after sending resolvePrompt, until ack fires
prompt_fail_count = 0            # consecutive rejections of the current prompt
_state_lock = threading.Lock()   # only one stateChange processed at a time


def _reset_game_state():
    global actions_this_turn, last_turn_number, turn_passed, attack_committed
    global chat_sent_this_turn, supporter_played_this_turn, energy_attached_this_turn, last_sent_prompt_id, last_rejection, rejected_this_turn
    global last_prompt_rejection, last_rejected_prompt_id, _current_context, _waiting_for_prompt_ack, prompt_fail_count
    actions_this_turn = 0
    last_turn_number = -1
    turn_passed = False
    attack_committed = False
    chat_sent_this_turn = False
    supporter_played_this_turn = False
    energy_attached_this_turn = False
    last_sent_prompt_id = None
    last_rejection = None
    rejected_this_turn = ["This is a list of actions you have tried to take that have been rejected. Do not try to play these actions again. This list will clear once you perform an action that is valid and accepted by the server."]
    last_prompt_rejection = None
    last_rejected_prompt_id = None
    _current_context = None
    _waiting_for_prompt_ack = False
    prompt_fail_count = 0


# ---------------------------------------------------------
# 5. Prompt resolver
# ---------------------------------------------------------
def resolve_prompt(prompt, players, game_state, my_index, card_names, card_lookup, last_rejection=None, prompt_fail_count=0):
    ptype = prompt.get("type", "")

    if ptype == "Invite player":
        print("[prompt] Accepting game invitation with deck.")
        return bot_deck

    if ptype in ("Alert", "Coin flip", "WaitPrompt", "Show mulligan", "Show cards", "Confirm cards"):
        return True

    if ptype == "Choose prize":
        opts = prompt.get("options", {})
        count = opts.get("count", opts.get("max", opts.get("min", 1)))
        return list(range(count))

    if ptype == "Shuffle deck":
        deck_cards = players[my_index].get("deck", {}).get("cards", [])
        return list(range(len(deck_cards)))

    return get_ai_prompt_response(prompt, players, game_state, my_index, card_names, card_lookup, last_rejection=last_rejection, prompt_fail_count=prompt_fail_count)


def _is_rejection(ack_data):
    if ack_data is None or ack_data is True:
        return False
    if isinstance(ack_data, dict) and ack_data.get("message") == "ok":
        return False
    return True


def _emit_sync(event_name, data, timeout=10):
    """Emit a socket.io event and block until the server ack arrives."""
    result = [None]
    done = threading.Event()

    def ack(ack_data=None, *_):
        result[0] = ack_data
        done.set()

    sio.emit(event_name, data, callback=ack)
    if not done.wait(timeout=timeout):
        print(f"[emit_sync] TIMEOUT waiting for ack on {event_name}")
        return {"message": "error", "data": "TIMEOUT"}
    return result[0]


# ---------------------------------------------------------
# 6. Action dispatcher
# ---------------------------------------------------------

# This is now synchronous
# It emits an action, waits for the server ack, and returns "done", "wait", or "retry" based on the result.
def _take_action(players, game_state, my_index, card_names):
    """Emit one action, wait for ack, return 'done' / 'wait' / 'retry'."""
    global actions_this_turn, turn_passed, attack_committed, chat_sent_this_turn
    global supporter_played_this_turn, energy_attached_this_turn, last_rejection, rejected_this_turn

    if attack_committed or turn_passed:
        return "done"

    if _waiting_for_prompt_ack:
        return "wait"

    if actions_this_turn >= MAX_ACTIONS_PER_TURN:
        print("Action limit reached, passing turn.")
        turn_passed = True
        sio.emit("game:action:passTurn", {"gameId": GAME_ID})
        return "done"

    action_name, action_input = get_ai_action(
        players, game_state, my_index, card_names, card_lookup, actions_this_turn,
        last_rejection=last_rejection,
        supporter_played_this_turn=supporter_played_this_turn,
        energy_attached_this_turn=energy_attached_this_turn,
        rejected_this_turn=rejected_this_turn,
    )
    last_rejection = None

    if action_name == "play_card":
        hand_index = action_input.get("hand_index", 0)
        slot = SLOT_MAP.get(action_input.get("target_slot", "BOARD"), 0)
        bench_index = action_input.get("bench_index", 0)

        hand_cards = players[my_index]["hand"]["cards"]
        _card_name = card_names[hand_cards[hand_index]] if hand_index < len(hand_cards) and isinstance(hand_cards[hand_index], int) and hand_cards[hand_index] < len(card_names) else ""
        _is_supporter = card_lookup.get(_card_name, {}).get("trainerType") == 1
        _is_energy = card_lookup.get(_card_name, {}).get("superType") == 3

        ack_data = _emit_sync("game:action:playCard", {
            "gameId": GAME_ID,
            "handIndex": hand_index,
            "target": {"player": MY_PLAYER_TYPE, "slot": slot, "index": bench_index},
        })

        if _is_rejection(ack_data):
            reason = f"play_card(hand={hand_index} '{_card_name}', slot={action_input.get('target_slot')}) rejected: {ack_data.get('data', ack_data) if isinstance(ack_data, dict) else ack_data}"
            print(f"[action] REJECTED {reason}")
            if isinstance(ack_data, dict) and ack_data.get("data") in ("ACTION_IN_PROGRESS", "NOT_YOUR_TURN"):
                return "wait"
            rejected_this_turn.append(reason)
            last_rejection = reason
            return "retry"

        actions_this_turn += 1
        rejected_this_turn = ["This is a list of actions you have tried to take that have been rejected. Do not try to play these actions again. This list will clear once you perform an action that is valid and accepted by the server."]
        if _is_supporter:
            supporter_played_this_turn = True
        if _is_energy:
            energy_attached_this_turn = True
        print(f"[action] play_card hand={hand_index} accepted")
        return "wait"  # wait for next stateChange with updated board state

    elif action_name == "attack":
        attack_name = action_input.get("attack_name", "")
        chat_msg = action_input.get("message", "")[:256]
        if not chat_sent_this_turn and chat_msg:
            print(f"[chat] Attack chat: {chat_msg!r}")
            sio.emit("game:action:appendLog", {"gameId": GAME_ID, "message": chat_msg})
            chat_sent_this_turn = True

        attack_committed = True
        ack_data = _emit_sync("game:action:attack", {"gameId": GAME_ID, "attack": attack_name})

        if _is_rejection(ack_data):
            reason = f"attack({attack_name!r}) rejected: {ack_data.get('data', ack_data) if isinstance(ack_data, dict) else ack_data}"
            print(f"[action] REJECTED {reason}")
            attack_committed = False
            if isinstance(ack_data, dict) and ack_data.get("data") in ("ACTION_IN_PROGRESS", "NOT_YOUR_TURN"):
                return "wait"
            rejected_this_turn.append(reason)
            last_rejection = reason
            return "retry"

        actions_this_turn += 1
        rejected_this_turn = ["This is a list of actions you have tried to take that have been rejected. Do not try to play these actions again. This list will clear once you perform an action that is valid and accepted by the server."]
        print(f"[action] attack {attack_name!r} accepted")
        return "done"

    elif action_name == "retreat":
        bench_index = action_input.get("bench_index", 0)
        attack_committed = True
        sio.emit("game:action:retreatStart", {"gameId": GAME_ID})
        ack_data = _emit_sync("game:action:retreat", {"gameId": GAME_ID, "to": bench_index})

        if _is_rejection(ack_data):
            reason = f"retreat(bench={bench_index}) rejected: {ack_data.get('data', ack_data) if isinstance(ack_data, dict) else ack_data}"
            print(f"[action] REJECTED {reason}")
            attack_committed = False
            if isinstance(ack_data, dict) and ack_data.get("data") in ("ACTION_IN_PROGRESS", "NOT_YOUR_TURN"):
                return "wait"
            rejected_this_turn.append(reason)
            last_rejection = reason
            return "retry"

        actions_this_turn += 1
        rejected_this_turn = ["This is a list of actions you have tried to take that have been rejected. Do not try to play these actions again. This list will clear once you perform an action that is valid and accepted by the server."]
        attack_committed = False  # retreat doesn't end the turn; can still attack
        print(f"[action] retreat to bench={bench_index} accepted")
        return "wait"  # wait for next stateChange with updated board state

    elif action_name == "use_ability":
        ability_name = action_input.get("ability_name", "")
        slot = SLOT_MAP.get(action_input.get("target_slot", "ACTIVE"), 1)
        bench_index = action_input.get("bench_index", 0)

        ack_data = _emit_sync("game:action:ability", {
            "gameId": GAME_ID,
            "ability": ability_name,
            "target": {"player": MY_PLAYER_TYPE, "slot": slot, "index": bench_index},
        })

        if _is_rejection(ack_data):
            reason = f"use_ability({ability_name!r}) rejected: {ack_data.get('data', ack_data) if isinstance(ack_data, dict) else ack_data}"
            print(f"[action] REJECTED {reason}")
            if isinstance(ack_data, dict) and ack_data.get("data") in ("ACTION_IN_PROGRESS", "NOT_YOUR_TURN"):
                return "wait"
            rejected_this_turn.append(reason)
            last_rejection = reason
            return "retry"

        actions_this_turn += 1
        rejected_this_turn = ["This is a list of actions you have tried to take that have been rejected. Do not try to play these actions again. This list will clear once you perform an action that is valid and accepted by the server."]
        print(f"[action] use_ability {ability_name!r} accepted")
        return "wait"

    elif action_name == "pass_turn":
        turn_passed = True
        reason_text = action_input.get("reason", "")
        print(f"Passing: {reason_text}")
        if reason_text:
            sio.emit("game:action:appendLog", {"gameId": GAME_ID, "message": reason_text[:256]})
            chat_sent_this_turn = True

        ack_data = _emit_sync("game:action:passTurn", {"gameId": GAME_ID})

        if _is_rejection(ack_data):
            reason = f"pass_turn rejected: {ack_data.get('data', ack_data) if isinstance(ack_data, dict) else ack_data}"
            print(f"[action] REJECTED {reason}")
            turn_passed = False
            if isinstance(ack_data, dict) and ack_data.get("data") in ("ACTION_IN_PROGRESS", "NOT_YOUR_TURN"):
                return "wait"
            rejected_this_turn.append(reason)
            last_rejection = reason
            return "retry"

        actions_this_turn += 1
        print("[action] pass_turn accepted")
        return "done"

    else:
        print(f"[action] Unknown action: {action_name!r}")
        return "wait"


# ---------------------------------------------------------
# 7. State change handler
# ---------------------------------------------------------

# This is still asyncrhonous
# Handles state changes from the server (like prompts)
# Then does an action
# Is looped by the sio
def on_state_change(data):
    if not _state_lock.acquire(blocking=False):
        return  # another thread is already processing a stateChange — drop this one

    global actions_this_turn, last_turn_number, turn_passed, attack_committed
    global chat_sent_this_turn, supporter_played_this_turn, energy_attached_this_turn, last_sent_prompt_id, last_rejection, rejected_this_turn, last_prompt_rejection, last_rejected_prompt_id, _current_context, _waiting_for_prompt_ack, prompt_fail_count

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
            print(f"Game over! Winner: {winner_name}.")
            print("Waiting for the next game invitation...")
            _reset_game_state()
            return

        card_names = game_state.get("cardNames", [])
        my_player_id = players[my_index].get("id")
        _current_context = (players, game_state, my_index, card_names)

        prompts = game_state.get("prompts", [])
        my_prompt = next(
            (p for p in prompts if p.get("playerId") == my_player_id and p.get("result") is None),
            None,
        )
        if my_prompt:
            prompt_id = my_prompt.get("id")
            if prompt_id == last_sent_prompt_id:
                return
            if prompt_id != last_rejected_prompt_id:
                last_prompt_rejection = None
                prompt_fail_count = 0
            last_sent_prompt_id = prompt_id
            _waiting_for_prompt_ack = True  # set before any prints so concurrent threads see it immediately
            ptype = my_prompt.get("type", "")
            print(f"[prompt] id={prompt_id} type={ptype} — {my_prompt.get('message', '')}")

            if ptype in ("Choose cards", "Choose pokemon"):
                opts = my_prompt.get("options", {})
                cards_data = my_prompt.get("cards", {}).get("cards", [])
                print(f"[prompt] RAW options={json.dumps(opts)}")
                print(f"[prompt] RAW cards ({len(cards_data)} total)={json.dumps(cards_data[:20])}")
                named = [(i, card_names[c] if isinstance(c, int) and c < len(card_names) else str(c))
                         for i, c in enumerate(cards_data)]
                print(f"[prompt] named cards: {named[:30]}")

            result = resolve_prompt(my_prompt, players, game_state, my_index, card_names, card_lookup, last_prompt_rejection, prompt_fail_count=prompt_fail_count)
            print(f"[prompt] sending result: {result!r}")

            def on_resolve_ack(ack_data=None, *_):
                global last_sent_prompt_id, last_prompt_rejection, last_rejected_prompt_id, _waiting_for_prompt_ack, prompt_fail_count
                _waiting_for_prompt_ack = False
                if _is_rejection(ack_data):
                    print(f"[prompt] SERVER REJECTED resolvePrompt id={prompt_id}: {ack_data}")
                    last_prompt_rejection = ack_data.get("data", str(ack_data)) if isinstance(ack_data, dict) else str(ack_data)
                    last_rejected_prompt_id = prompt_id
                    last_sent_prompt_id = None
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
            rejected_this_turn = ["This is a list of actions you have tried to take that have been rejected. Do not try to play these actions again. This list will clear once you perform an action that is valid and accepted by the server."]
            _waiting_for_prompt_ack = False
            prompt_fail_count = 0
            last_turn_number = turn

        if _waiting_for_prompt_ack:
            return

        # Loop only on rejections — everything else waits for the next stateChange
        while not attack_committed and not turn_passed:
            result = _take_action(players, game_state, my_index, card_names)
            if result != "retry":
                break

    except Exception:
        print("[on_state_change error]")
        traceback.print_exc()
    finally:
        _state_lock.release()


# ---------------------------------------------------------
# 8. Connect and wait for invitations
# ---------------------------------------------------------
sio = socketio.Client()


@sio.on("core:createGame")
def on_core_create_game(data):
    global GAME_ID
    players = data.get("players", [])
    if not any(p.get("name") == USERNAME for p in players):
        return  # game doesn't involve monkey
    game_id = data.get("gameId")
    print(f"\nGame invitation received! Game ID: {game_id}")
    GAME_ID = game_id
    _reset_game_state()
    sio.on(f"game[{game_id}]:stateChange", on_state_change)
    sio.emit("game:rejoin", {"gameId": game_id})
    print(f"Joined game {game_id}. Waiting for game to start...")


@sio.event
def connect():
    print("Connected to Twinleaf server!")
    print(f"Waiting for someone to challenge {USERNAME}...")


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
