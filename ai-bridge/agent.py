"""
agent.py — AI decision engine for the Pokemon TCG bot.

Swap this file (or change the import in MCP.py) to use a different AI provider.

Contract:
    get_ai_action(players, game_state, my_index, card_names, card_lookup)
        -> (action_name: str, action_input: dict)

    action_name values:
        "play_card"  -> { hand_index: int, target_slot: "BOARD"|"ACTIVE"|"BENCH", bench_index?: int }
        "attack"     -> { attack_name: str }
        "retreat"    -> { bench_index: int }
        "pass_turn"  -> {}
"""

# change two lines below to specific ai agent
import anthropic
import json as _json
import os as _os

anthropic_client = anthropic.AnthropicBedrock()

CARD_TYPE_NAMES = {
    0: "Any", 1: "Grass", 2: "Fire", 3: "Water", 4: "Lightning",
    5: "Psychic", 6: "Fighting", 7: "Dark", 8: "Metal", 9: "Colorless",
    10: "Fairy", 11: "Dragon", 12: "None",
}

CONDITION_NAMES = {
    0: "Paralyzed", 1: "Confused", 2: "Asleep", 3: "Poisoned", 4: "Burned",
}

STAGE_NAMES = {
    2: "Basic", 3: "Stage1", 4: "Stage2",
}

def _energy_name(code) -> str:
    if isinstance(code, int):
        return CARD_TYPE_NAMES.get(code, str(code))
    return str(code)

def _condition_name(code) -> str:
    if isinstance(code, int):
        return CONDITION_NAMES.get(code, str(code))
    return str(code)

_PROMPT_PATH = _os.path.join(_os.path.dirname(__file__), "prompts", "pokemon_tcg_ai_prompt.md")
with open(_PROMPT_PATH, encoding="utf-8") as _f:
    SYSTEM_PROMPT = _f.read()

from prompts.rejection_messages import REJECTION_MESSAGES
from prompts.tools import build_action_tools


def get_card_name(card_id, card_names):
    if isinstance(card_id, int) and 0 <= card_id < len(card_names):
        return card_names[card_id]
    return "Unknown"


def describe_pokemon_slot(poke_list, card_names, card_lookup):
    if not poke_list or not poke_list.get("cards"):
        return None
    name = get_card_name(poke_list["cards"][0], card_names)
    damage = poke_list.get("damage", 0)
    card_info = card_lookup.get(name, {})
    hp = card_info.get("hp", "?")

    energy_ids = []
    energies_field = poke_list.get("energies")
    if isinstance(energies_field, dict):
        energy_ids = energies_field.get("cards", [])
    energies = [get_card_name(e, card_names) for e in energy_ids]

    attacks = card_info.get("attacks", [])
    abilities = card_info.get("powers", [])
    retreat = card_info.get("retreat", [])
    conditions = poke_list.get("specialConditions", [])

    return {
        "name": name,
        "hp": hp,
        "damage": damage,
        "energies": energies,
        "attacks": attacks,
        "abilities": abilities,
        "retreat": retreat,
        "conditions": conditions,
    }

# Takes game state and turns it into string describing the current situation.
# Fed into Claude.
def build_state_prompt(players, game_state, my_index, card_names, card_lookup, supporter_played_this_turn=False, energy_attached_this_turn=False):
    me = players[my_index]
    opp = players[1 - my_index]

    turn = game_state.get("turn", "?")
    my_prizes = sum(len(p.get("cards", [])) for p in me.get("prizes", []))
    opp_prizes = sum(len(p.get("cards", [])) for p in opp.get("prizes", []))

    hand_lines = []
    for i, card_id in enumerate(me["hand"]["cards"]):
        name = get_card_name(card_id, card_names)
        info = card_lookup.get(name, {})
        super_type = info.get("superType", "")
        trainer_type = info.get("trainerType", "")
        stage_int = info.get("stage")
        stage_str = STAGE_NAMES.get(stage_int, "") if stage_int is not None else ""
        evolves_from = info.get("evolvesFrom", "")
        if stage_str and stage_str not in ("None", ""):
            if evolves_from and stage_str != "Basic":
                type_str = f"{stage_str} (evolves from {evolves_from})"
            else:
                type_str = stage_str
        else:
            type_str = f"{super_type} {trainer_type}".strip() or "Unknown"
        hand_lines.append(f"  [{i}] {name} ({type_str})")

    my_active = describe_pokemon_slot(me.get("active"), card_names, card_lookup)
    my_bench = [
        describe_pokemon_slot(b, card_names, card_lookup) for b in me.get("bench", [])
    ]
    my_bench = [b for b in my_bench if b]

    opp_active = describe_pokemon_slot(opp.get("active"), card_names, card_lookup)
    opp_bench = [
        describe_pokemon_slot(b, card_names, card_lookup) for b in opp.get("bench", [])
    ]
    opp_bench = [b for b in opp_bench if b]

    lines = [
        f"=== POKEMON TCG - Turn {turn} ===",
        f"Prize cards remaining — You: {my_prizes} | Opponent: {opp_prizes}",
        "",
        f"YOUR HAND ({len(me['hand']['cards'])} cards):",
        *(hand_lines if hand_lines else ["  (empty)"]),
        "",
        "YOUR ACTIVE POKEMON:",
    ]

    def _fmt_attack_mine(a, attached_count):
        cost = a.get("cost", [])
        cost_str = '+'.join(_energy_name(c) for c in cost)
        needed = len(cost)
        usable = "CAN USE" if attached_count >= needed else f"CANNOT USE (need {needed} energy, have {attached_count})"
        text = a.get("text", "")
        effect = f" — {text}" if text else ""
        return f"    {a['name']} [{a.get('damage', '?')} dmg, cost: {cost_str}]{effect} ({usable})"

    def _fmt_attack_opp(a):
        cost = a.get("cost", [])
        cost_str = '+'.join(_energy_name(c) for c in cost)
        text = a.get("text", "")
        effect = f" — {text}" if text else ""
        return f"    {a['name']} [{a.get('damage', '?')} dmg, cost: {cost_str}]{effect}"

    def _fmt_ability(p):
        return f"    [Ability] {p.get('name', '?')}: {p.get('text', '')}"

    def _fmt_retreat(retreat):
        if not retreat:
            return "free"
        return '+'.join(_energy_name(c) for c in retreat)

    def _append_pokemon_lines(lines, poke, is_mine=True):
        attached_count = len(poke["energies"])
        lines += [
            f"  {poke['name']} | HP: {poke['hp']} | Damage taken: {poke['damage']} "
            f"| Retreat cost: {_fmt_retreat(poke['retreat'])}",
            f"  Energy attached: {', '.join(poke['energies']) if poke['energies'] else 'none'}",
            f"  Conditions: {', '.join(_condition_name(c) for c in poke['conditions']) if poke['conditions'] else 'none'}",
        ]
        if poke["abilities"]:
            lines.append("  Abilities:")
            lines += [_fmt_ability(p) for p in poke["abilities"]]
        if poke["attacks"]:
            lines.append("  Attacks:")
            if is_mine:
                lines += [_fmt_attack_mine(a, attached_count) for a in poke["attacks"]]
            else:
                lines += [_fmt_attack_opp(a) for a in poke["attacks"]]
        else:
            lines.append("  Attacks: unknown (use your knowledge of this card)")

    if my_active:
        _append_pokemon_lines(lines, my_active, is_mine=True)
    else:
        lines.append("  (none - you must play a Basic Pokemon to Active)")

    lines += ["", "YOUR BENCH:"]
    if my_bench:
        for b in my_bench:
            _append_pokemon_lines(lines, b, is_mine=True)
    else:
        lines.append("  (empty)")

    lines += ["", "OPPONENT'S ACTIVE POKEMON:"]
    if opp_active:
        _append_pokemon_lines(lines, opp_active, is_mine=False)
    else:
        lines.append("  (none)")

    lines += ["", "OPPONENT'S BENCH:"]
    if opp_bench:
        for b in opp_bench:
            _append_pokemon_lines(lines, b, is_mine=False)
    else:
        lines.append("  (empty)")

    def _fmt_discard(player):
        discard_ids = player.get("discard", {}).get("cards", [])
        if not discard_ids:
            return ["  (empty)"]
        from collections import Counter
        name_counts = Counter(get_card_name(c, card_names) for c in discard_ids)
        result = []
        seen = set()
        for card_id in discard_ids:
            name = get_card_name(card_id, card_names)
            if name in seen:
                continue
            seen.add(name)
            count_str = f" x{name_counts[name]}" if name_counts[name] > 1 else ""
            info = card_lookup.get(name, {})
            super_type = info.get("superType", "")
            if super_type == "Pokemon":
                result.append(f"  {name}{count_str} (Pokemon | HP: {info.get('hp', '?')})")
                for p in info.get("powers", []):
                    result.append(f"    [Ability] {p.get('name', '?')}: {p.get('text', '')}")
                for a in info.get("attacks", []):
                    cost_str = '+'.join(_energy_name(c) for c in a.get("cost", []))
                    text = a.get("text", "")
                    effect = f" — {text}" if text else ""
                    result.append(f"    {a['name']} [{a.get('damage', '?')} dmg, cost: {cost_str}]{effect}")
            elif super_type == "Trainer":
                trainer_type = info.get("trainerType", "")
                card_text = info.get("text", "")
                result.append(f"  {name}{count_str} ({trainer_type}){': ' + card_text if card_text else ''}")
            else:
                result.append(f"  {name}{count_str}")
        return result

    # Build evolution opportunities: match hand evolution cards to in-play Pokemon they can evolve
    evo_lines = []
    in_play = []
    if my_active:
        in_play.append(("ACTIVE", None, my_active["name"]))
    for bi, b in enumerate(my_bench):
        in_play.append(("BENCH", bi, b["name"]))

    for i, card_id in enumerate(me["hand"]["cards"]):
        name = get_card_name(card_id, card_names)
        info = card_lookup.get(name, {})
        if info.get("superType") != "Pokemon":
            continue
        evolves_from = info.get("evolvesFrom", "")
        if not evolves_from:
            continue
        for slot_label, bench_idx, in_play_name in in_play:
            if in_play_name.lower() == evolves_from.lower():
                target = slot_label if slot_label == "ACTIVE" else f"BENCH slot {bench_idx}"
                final_attacks = info.get("attacks", [])
                min_cost = min((len(a.get("cost", [])) for a in final_attacks), default="?")
                evo_lines.append(
                    f"  Hand [{i}] {name} can evolve your {in_play_name} ({target}) — "
                    f"use play_card(hand_index={i}, target_slot='{slot_label}'"
                    + (f", bench_index={bench_idx}" if bench_idx is not None else "")
                    + f") | {name} cheapest attack costs {min_cost} energy"
                )

    if evo_lines:
        lines += ["", "EVOLUTION OPPORTUNITIES (use these before attaching energy or attacking):"]
        lines += evo_lines
    else:
        lines += ["", "EVOLUTION OPPORTUNITIES: none available this turn"]

    lines += ["", "YOUR DISCARD PILE:"]
    lines += _fmt_discard(me)

    lines += ["", "OPPONENT'S DISCARD PILE:"]
    lines += _fmt_discard(opp)

    my_deck_count = len(me.get("deck", {}).get("cards", []))
    opp_deck_count = len(opp.get("deck", {}).get("cards", []))
    lines.append(f"\nDECK SIZES: You {my_deck_count} | Opponent {opp_deck_count}")

    stadium_card = None
    for p in players:
        cards = p.get("stadium", {}).get("cards", [])
        if cards:
            stadium_card = get_card_name(cards[0], card_names)
            break
    lines.append(f"\nSTADIUM IN PLAY: {stadium_card or 'none'}")

    chat_lines = [
        f"  {'You' if log.get('client') == my_index else 'Opponent'}: {log.get('params', {}).get('text', '')}"
        for log in game_state.get("logs", [])
        if log.get("message") == "LOG_TEXT"
    ]
    if chat_lines:
        lines += ["\nRECENT CHAT:"] + chat_lines

    restrictions = []
    if turn == 1:
        restrictions.append("It is Turn 1 — you CANNOT attack this turn.")
    if supporter_played_this_turn:
        restrictions.append("Supporter already played — do NOT play another Supporter this turn.")
    if energy_attached_this_turn:
        restrictions.append("Energy already attached this turn — do NOT attach another Energy card.")
    if restrictions:
        lines.append("\nTURN RESTRICTIONS: " + " | ".join(restrictions))

    return "\n".join(lines)


# CardTarget.player is relative to the acting player:
#   BOTTOM_PLAYER (2) = own Pokemon, TOP_PLAYER (1) = opponent's Pokemon
MY_PLAYER_TYPE = 2
OPP_PLAYER_TYPE = 1


def _ask_claude(state_summary, description, tool):
    resp = anthropic_client.messages.create(
        model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        tools=[tool],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": f"{state_summary}\n\n{description}"}],
    )
    for block in resp.content:
        if block.type == "tool_use":
            return block.input
    return None

def _ask_claude_action(state_summary, description, tools, max_tokens=1024):
    resp = anthropic_client.messages.create(
        model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        tools=tools,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": f"{state_summary}\n\n{description}"}],
    )
    for block in resp.content:
        if block.type == "tool_use":
            return block.name, block.input
    return "pass_turn", {"reason": "No tool use returned"}

# Swap these two functions to change AI provider
def _ask_AI(state_summary, description, tool):
    return _ask_claude(state_summary, description, tool)

def _ask_AI_action(state_summary, description, tools, max_tokens=1024):
    return _ask_claude_action(state_summary, description, tools, max_tokens)

# Many prompt types
# Show mulligan, show cards, select, selectOption, confirm cards, choose cards, choose pokemon
# Should also add attach energy
def get_ai_prompt_response(prompt, players, game_state, my_index, card_names, card_lookup, last_rejection=None, prompt_fail_count=0):
    ptype = prompt.get("type", "")
    message = prompt.get("message", "Make a choice.")
    if last_rejection:
        explanation = next((v for k, v in REJECTION_MESSAGES.items() if k in str(last_rejection)), f"Server rejected your answer: {last_rejection}")
        message = f"PREVIOUS ANSWER REJECTED — {explanation}\nYou must choose differently.\n\n{message}"
    opts = prompt.get("options", {})
    state_summary = build_state_prompt(players, game_state, my_index, card_names, card_lookup)

    if ptype == "Confirm":
        result = _ask_AI(
            state_summary,
            f"You are being asked to confirm: {message}\nShould you say yes?",
            {
                "name": "confirm",
                "description": "Answer yes or no.",
                "input_schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "boolean", "description": "true=yes, false=no"}},
                    "required": ["answer"],
                },
            },
        )
        return result["answer"] if result else False

    elif ptype == "SelectOption":
        print(f"Prompt options: {opts}")
        values = prompt.get("values", [])
        options_str = "\n".join(f"  [{i}] {v}" for i, v in enumerate(values))
        result = _ask_AI(
            state_summary,
            f"{message}\nOptions:\n{options_str}",
            {
                "name": "select_option",
                "description": "Pick one option by index.",
                "input_schema": {
                    "type": "object",
                    "properties": {"index": {"type": "integer", "description": f"0 to {max(0, len(values)-1)}"}},
                    "required": ["index"],
                },
            },
        )
        return result["index"] if result else 0

    elif ptype == "Choose cards":
        cards_data = prompt.get("cards", {}).get("cards", [])
        prompt_filter = prompt.get("filter", {})
        filter_super = prompt_filter.get("superType")
        filter_trainer = prompt_filter.get("trainerType")
        min_count = opts.get("min", 0)
        max_count = opts.get("max", 1)
        max_basics = opts.get("maxBasics")      # None = no limit
        max_evolutions = opts.get("maxEvolutions")  # None = no limit

        # Exclude blocked indices (server marks these as unselectable).
        blocked = set(opts.get("blocked", []))
        eligible = []
        for i, card_id in enumerate(cards_data):
            if i in blocked:
                continue
            name = get_card_name(card_id, card_names)
            info = card_lookup.get(name)
            if info is not None:
                if filter_super and info.get("superType") != filter_super:
                    continue
                if filter_trainer and info.get("trainerType") != filter_trainer:
                    continue
            eligible.append((i, name, info))

        print(f"[prompt] Choose cards: {len(eligible)} eligible of {len(cards_data)}, min={min_count} max={max_count}")

        if not eligible:
            return []

        if prompt_fail_count >= 2 and min_count == 0:
            print(f"[prompt] Choose cards: {prompt_fail_count} consecutive rejections, min=0 — sending empty selection as fallback")
            return []

        # Returns the stage string used for labels AND for constraint enforcement.
        # "Basic", "Stage1", "Stage2" — both Stage1 and Stage2 count as evolutions.
        def _card_kind(info):
            if info is None:
                return ""
            return STAGE_NAMES.get(info.get("stage"), "")

        card_lines = []
        for j, (_, name, info) in enumerate(eligible):
            kind = _card_kind(info)
            evolves_from = (info or {}).get("evolvesFrom", "")
            if kind == "Stage1" and evolves_from:
                label = f"Stage 1, evolves from {evolves_from}"
            elif kind == "Stage2" and evolves_from:
                label = f"Stage 2, evolves from {evolves_from}"
            elif kind == "Basic":
                label = "Basic"
            else:
                label = kind
            suffix = f" [{label}]" if label else ""
            card_lines.append(f"  [{j}] {name}{suffix}")
        cards_str = "\n".join(card_lines)

        # Dump all opts except `blocked` (already applied above as the eligible filter).
        opts_for_claude = {k: v for k, v in opts.items() if k != "blocked"}
        constraint_str = f"Server constraints (you MUST respect ALL of these): {_json.dumps(opts_for_claude)}"

        result = _ask_AI(
            state_summary,
            f"{message}\nEligible cards (blocked indices already removed):\n{cards_str}\n{constraint_str}",
            {
                "name": "choose_cards",
                "description": f"Choose {min_count}-{max_count} cards by eligible-list index. Obey all server constraints.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": f"Indices into the eligible list above (0 to {max(0, len(eligible)-1)}). Must satisfy all constraints in opts.",
                        }
                    },
                    "required": ["indices"],
                },
            },
        )
        ai_indices = result.get("indices", []) if isinstance(result, dict) else list(range(min(min_count, len(eligible))))

        # Safety net: enforce maxBasics/maxEvolutions even if Claude ignored them.
        validated = []
        basics_used = 0
        evos_used = 0
        for j in ai_indices:
            if j >= len(eligible) or len(validated) >= max_count:
                continue
            _, _, info = eligible[j]
            kind = _card_kind(info)
            if kind == "Basic":
                if max_basics is not None and basics_used >= max_basics:
                    continue
                basics_used += 1
            elif kind in ("Stage1", "Stage2"):
                if max_evolutions is not None and evos_used >= max_evolutions:
                    continue
                evos_used += 1
            validated.append(j)

        # (code-level energy deduplication removed — rejection message now explains the constraint)

        print(f"[prompt] AI chose eligible indices {ai_indices} → validated {validated} → original indices {[eligible[j][0] for j in validated]}")
        return [eligible[j][0] for j in validated]

    elif ptype == "Choose pokemon":
        print(f"Prompt pokemon options: {opts}")
        me = players[my_index]
        opp = players[1 - my_index]
        my_type = MY_PLAYER_TYPE
        opp_type = OPP_PLAYER_TYPE
        targets = []
        if me.get("active", {}).get("cards"):
            name = get_card_name(me["active"]["cards"][0], card_names)
            targets.append({"desc": f"Your Active: {name}", "player": my_type, "slot": 1, "index": 0})
        for i, b in enumerate(me.get("bench", [])):
            if b.get("cards"):
                name = get_card_name(b["cards"][0], card_names)
                targets.append({"desc": f"Your Bench [{i}]: {name}", "player": my_type, "slot": 2, "index": i})
        if opp.get("active", {}).get("cards"):
            name = get_card_name(opp["active"]["cards"][0], card_names)
            targets.append({"desc": f"Opponent Active: {name}", "player": opp_type, "slot": 1, "index": 0})
        for i, b in enumerate(opp.get("bench", [])):
            if b.get("cards"):
                name = get_card_name(b["cards"][0], card_names)
                targets.append({"desc": f"Opponent Bench [{i}]: {name}", "player": opp_type, "slot": 2, "index": i})
        targets_str = "\n".join(f"  [{i}] {t['desc']}" for i, t in enumerate(targets))
        min_count = opts.get("min", 1)
        max_count = opts.get("max", 1)
        result = _ask_AI(
            state_summary,
            f"{message}\nAvailable Pokemon:\n{targets_str}\nChoose {min_count}-{max_count}.",
            {
                "name": "choose_pokemon",
                "description": f"Choose {min_count}-{max_count} Pokemon by index.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Indices from the list above",
                        }
                    },
                    "required": ["indices"],
                },
            },
        )
        chosen = (result.get("indices", [0]) if isinstance(result, dict) else [0])[:max_count]
        return [
            {"player": targets[i]["player"], "slot": targets[i]["slot"], "index": targets[i]["index"]}
            for i in chosen if i < len(targets)
        ]

    elif ptype == "Choose energy":
        print(f"Prompt energy options: {opts}")
        energy_data = prompt.get("energy", [])
        energy_str = "\n".join(
            f"  [{i}] {get_card_name(e.get('card', 0), card_names)} provides {e.get('provides', [])}"
            for i, e in enumerate(energy_data)
        )
        min_count = opts.get("min", 1)
        max_count = opts.get("max", 1)
        result = _ask_AI(
            state_summary,
            f"{message}\nAvailable energy:\n{energy_str}\nChoose {min_count}-{max_count}.",
            {
                "name": "choose_energy",
                "description": "Choose energy by index.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Energy indices to select",
                        }
                    },
                    "required": ["indices"],
                },
            },
        )
        indices = result["indices"] if result else list(range(min_count))
        return indices[:max_count]

    elif ptype == "Choose attack":
        print(f"Prompt attack options: {opts}")
        cards_data = prompt.get("cards", {}).get("cards", [])
        attack_options = []
        for ci, card_id in enumerate(cards_data):
            name = get_card_name(card_id, card_names)
            info = card_lookup.get(name, {})
            for atk in info.get("attacks", []):
                attack_options.append({"card_index": ci, "attack": atk["name"], "desc": f"{name} — {atk['name']}"})
        atk_str = "\n".join(f"  [{i}] {a['desc']}" for i, a in enumerate(attack_options))
        result = _ask_AI(
            state_summary,
            f"{message}\nAvailable attacks:\n{atk_str}",
            {
                "name": "choose_attack",
                "description": "Choose an attack by index.",
                "input_schema": {
                    "type": "object",
                    "properties": {"index": {"type": "integer", "description": "Attack option index"}},
                    "required": ["index"],
                },
            },
        )
        idx = result["index"] if result else 0
        if idx < len(attack_options):
            chosen = attack_options[idx]
            return {"index": chosen["card_index"], "attack": chosen["attack"]}
        return None

    elif ptype == "Select":
        return 0  # first option = draw max cards (options sorted high→low)

    elif ptype == "Shuffle prizes":
        prizes = players[my_index].get("prizes", [])
        return list(range(len(prizes)))

    elif ptype == "Attach energy":
        active = players[my_index].get("active", {})
        slot = 1 if active.get("cards") else 2
        return [{"to": {"player": MY_PLAYER_TYPE, "slot": slot, "index": 0}, "index": 0}]

    print(f"[prompt] Unknown type '{ptype}', returning None")
    return None


def get_ai_action(players, game_state, my_index, card_names, card_lookup, actions_taken=0, last_rejection=None, chat_sent_this_turn=False, supporter_played_this_turn=False, energy_attached_this_turn=False):
    state_prompt = build_state_prompt(
        players, game_state, my_index, card_names, card_lookup,
        supporter_played_this_turn=supporter_played_this_turn,
        energy_attached_this_turn=energy_attached_this_turn,
    )
    print(f"\n{state_prompt}\n")

    hand_size = len(players[my_index]["hand"]["cards"])
    tools = build_action_tools(hand_size, chat_sent_this_turn)

    print(f"Actions taken this turn: {actions_taken}.")

    action_name, action_input = _ask_AI_action(
        state_prompt,
        (
            (f"LAST ACTION REJECTED: {last_rejection}\nChoose a different action.\n\n" if last_rejection else "")
            + f"Actions taken this turn so far: {actions_taken}.\n"
            + "Choose your next action.\n"
            + "IMPORTANT: Before attacking or passing, play ALL beneficial cards from your hand — "
            "items, supporters, trainers, Pokémon to bench, energy attachment. "
            "You can take many actions in a single turn. Only attack when ready, and only pass when there is truly nothing left to play. "
            "You are trying to WIN this game."
        ),
        tools,
    )
    print(f"AI chose: {action_name} {action_input}")
    return action_name, action_input
