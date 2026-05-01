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

anthropic_client = anthropic.AnthropicBedrock()

CARD_TYPE_NAMES = {
    0: "Any", 1: "Grass", 2: "Fire", 3: "Water", 4: "Lightning",
    5: "Psychic", 6: "Fighting", 7: "Dark", 8: "Metal", 9: "Colorless",
    10: "Fairy", 11: "Dragon", 12: "None",
}

CONDITION_NAMES = {
    0: "Paralyzed", 1: "Confused", 2: "Asleep", 3: "Poisoned", 4: "Burned",
}

def _energy_name(code) -> str:
    if isinstance(code, int):
        return CARD_TYPE_NAMES.get(code, str(code))
    return str(code)

def _condition_name(code) -> str:
    if isinstance(code, int):
        return CONDITION_NAMES.get(code, str(code))
    return str(code)

SYSTEM_PROMPT = """You are an expert Pokemon Trading Card Game player. Your goal is to WIN.

RULES YOU MUST FOLLOW:
- You can play multiple cards per turn but only ONE Supporter per turn
- You can attach ONE energy per turn (to any Pokemon you control)
- Basic Pokemon go to Bench (use target_slot=BENCH) or Active if empty (use ACTIVE)
- Trainer/Supporter/Item/Stadium cards use target_slot=BOARD
- Energy cards use target_slot=ACTIVE (for active) or BENCH with bench_index for bench Pokemon
- Attacking ends your turn — only attack when ready
- "Colorless" energy cost means ANY energy type satisfies it — Fire, Psychic, Water, etc. all count
- Attack cost shows energy types needed on the Pokemon, not a number of turns

STRATEGY:
- Early game: fill bench with Basics, attach energy to your main attacker, use draw supporters
- Mid game: evolve when possible, keep energy building on attackers
- Late game: attack aggressively, target knockouts for prizes
- Always consider: can I knock out their active Pokemon this turn?
- Use your knowledge of Pokemon TCG cards — you know what each card does

You will be called once per action. Each call you must choose ONE action. As soon as your active Pokemon can attack, attack — do not keep playing cards to delay it. If you have already played setup cards (energy, trainers, supporters) and your attacker is ready, attack immediately."""


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
    conditions = poke_list.get("specialConditions", [])

    return {
        "name": name,
        "hp": hp,
        "damage": damage,
        "energies": energies,
        "attacks": attacks,
        "conditions": conditions,
    }


def build_state_prompt(players, game_state, my_index, card_names, card_lookup):
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

    if my_active:
        attached_count = len(my_active["energies"])
        # Format attack into a string
        # Tells AI properties about the attack (specifically can use)
        def _fmt_attack(a):
            cost = a.get("cost", [])
            cost_str = '+'.join(_energy_name(c) for c in cost)
            needed = len(cost)
            usable = "CAN USE" if attached_count >= needed else f"CANNOT USE (need {needed} energy, have {attached_count})"
            return f"{a['name']} [{a.get('damage', '?')} dmg, cost: {cost_str}] ({usable})"
        attack_str = (
            ", ".join(_fmt_attack(a) for a in my_active["attacks"])
            if my_active["attacks"]
            else "unknown (use your knowledge of this card)"
        )
        lines += [
            f"  {my_active['name']} | HP: {my_active['hp']} | Damage taken: {my_active['damage']}",
            f"  Energy attached: {', '.join(my_active['energies']) if my_active['energies'] else 'none'}",
            f"  Attacks: {attack_str}",
            f"  Special conditions: {', '.join(_condition_name(c) for c in my_active['conditions']) if my_active['conditions'] else 'none'}",
        ]
    else:
        lines.append("  (none - you must play a Basic Pokemon to Active)")

    lines += ["", "YOUR BENCH:"]
    if my_bench:
        for b in my_bench:
            lines.append(
                f"  {b['name']} | HP: {b['hp']} | Damage: {b['damage']} "
                f"| Energy: {', '.join(b['energies']) if b['energies'] else 'none'}"
            )
    else:
        lines.append("  (empty)")

    lines += ["", "OPPONENT'S ACTIVE POKEMON:"]
    if opp_active:
        lines += [
            f"  {opp_active['name']} | HP: {opp_active['hp']} | Damage taken: {opp_active['damage']}",
            f"  Special conditions: {', '.join(opp_active['conditions']) if opp_active['conditions'] else 'none'}",
        ]
    else:
        lines.append("  (none)")

    lines += ["", "OPPONENT'S BENCH:"]
    if opp_bench:
        for b in opp_bench:
            lines.append(
                f"  {b['name']} | HP: {b['hp']} | Damage: {b['damage']} "
                f"| Energy: {', '.join(b['energies']) if b['energies'] else 'none'}"
            )
    else:
        lines.append("  (empty)")

    return "\n".join(lines)


PLAYER_TYPE_MAP = [1, 2]  # index -> PlayerType enum (TOP=1, BOTTOM=2)


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


def get_ai_prompt_response(prompt, players, game_state, my_index, card_names, card_lookup):
    ptype = prompt.get("type", "")
    message = prompt.get("message", "Make a choice.")
    opts = prompt.get("options", {})
    state_summary = build_state_prompt(players, game_state, my_index, card_names, card_lookup)

    if ptype == "Confirm":
        result = _ask_claude(
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
        result = _ask_claude(
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

        # Exclude blocked indices (server marks these as unselectable).
        # If a card isn't in card_lookup, include it unless it's blocked.
        blocked = set(opts.get("blocked", []))
        eligible = []
        for i, card_id in enumerate(cards_data):
            if i in blocked:
                continue
            name = get_card_name(card_id, card_names)
            info = card_lookup.get(name)  # None if not found
            if info is not None:
                if filter_super and info.get("superType") != filter_super:
                    continue
                if filter_trainer and info.get("trainerType") != filter_trainer:
                    continue
            eligible.append((i, name))

        print(f"[prompt] Choose cards: {len(eligible)} eligible of {len(cards_data)}, min={min_count} max={max_count}")

        if not eligible:
            return []  # min=0; nothing eligible, pick nothing

        cards_str = "\n".join(f"  [{j}] {name}" for j, (_, name) in enumerate(eligible))
        result = _ask_claude(
            state_summary,
            f"{message}\nEligible cards:\n{cards_str}\nChoose {min_count} to {max_count}.",
            {
                "name": "choose_cards",
                "description": f"Choose {min_count}-{max_count} cards by index.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": f"Indices into the eligible list above (0 to {max(0, len(eligible)-1)})",
                        }
                    },
                    "required": ["indices"],
                },
            },
        )
        ai_indices = result["indices"] if result else list(range(min(min_count, len(eligible))))
        print(f"[prompt] AI chose eligible indices {ai_indices} → original indices {[eligible[j][0] for j in ai_indices if j < len(eligible)]}")
        return [eligible[j][0] for j in ai_indices if j < len(eligible)][:max_count]

    elif ptype == "Choose pokemon":
        print(f"Prompt pokemon options: {opts}")
        me = players[my_index]
        opp = players[1 - my_index]
        my_type = PLAYER_TYPE_MAP[my_index]
        opp_type = PLAYER_TYPE_MAP[1 - my_index]
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
        result = _ask_claude(
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
        chosen = (result["indices"] if result else [0])[:max_count]
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
        result = _ask_claude(
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
        result = _ask_claude(
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

    print(f"[prompt] Unknown type '{ptype}', returning None")
    return None


def get_ai_action(players, game_state, my_index, card_names, card_lookup, actions_taken=0):
    state_prompt = build_state_prompt(
        players, game_state, my_index, card_names, card_lookup
    )
    print(f"\n{state_prompt}\n")

    hand_size = len(players[my_index]["hand"]["cards"])

    tools = [
        {
            "name": "play_card",
            "description": (
                "Play a card from your hand. Use for trainers, supporters, items, stadiums, "
                "playing Basic Pokemon to bench, or attaching energy to a Pokemon."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "hand_index": {
                        "type": "integer",
                        "description": f"Index of the card in hand (0 to {max(0, hand_size - 1)})",
                    },
                    "target_slot": {
                        "type": "string",
                        "enum": ["BOARD", "ACTIVE", "BENCH"],
                        "description": (
                            "BOARD: for trainers/supporters/items/stadiums. "
                            "ACTIVE: to place first Pokemon or attach energy to active. "
                            "BENCH: to place a Basic Pokemon on bench or attach energy to bench Pokemon."
                        ),
                    },
                    "bench_index": {
                        "type": "integer",
                        "description": "Which bench slot (0-4). Required when target_slot=BENCH.",
                    },
                },
                "required": ["hand_index", "target_slot"],
            },
        },
        {
            "name": "attack",
            "description": "Use your active Pokemon's attack. This ENDS your turn. Choose this whenever your active Pokemon has enough energy to use an attack — don't delay attacking by playing unnecessary cards.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "attack_name": {
                        "type": "string",
                        "description": "The exact name of the attack. Use your knowledge of the card.",
                    }
                },
                "required": ["attack_name"],
            },
        },
        {
            "name": "retreat",
            "description": (
                "Retreat your active Pokemon to the bench, replacing it with a bench Pokemon. "
                "Use when your active Pokemon is about to be knocked out and you have a better "
                "attacker on the bench. Costs retreat energy."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "bench_index": {
                        "type": "integer",
                        "description": "0-based index of the bench Pokemon to switch in (0-4).",
                    }
                },
                "required": ["bench_index"],
            },
        },
        {
            "name": "pass_turn",
            "description": "End your turn without attacking. Use when you have no energy to attack, or when you have already played the cards you needed and attacking is not yet possible.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Why you are passing instead of attacking.",
                    }
                },
                "required": [],
            },
        },
    ]

    # change this for specific ai agent
    response = anthropic_client.messages.create(
        model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=tools,
        tool_choice={"type": "any"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"{state_prompt}\n\n"
                    f"Actions taken this turn so far: {actions_taken}.\n"
                    + (
                        "You have played enough cards. ATTACK NOW if you have sufficient energy, "
                        "or PASS if you cannot attack. Do not play more cards.\n"
                        if actions_taken >= 5
                        else (
                            "Consider whether attacking or passing is now better than playing another card.\n"
                            if actions_taken >= 3
                            else ""
                        )
                    )
                    + "Choose your next action. You can play cards one at a time — "
                    "pick the single best action to take right now."
                ),
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use":
            print(f"AI chose: {block.name} {block.input}")
            return block.name, block.input

    return "pass_turn", {"reason": "No tool use returned"}
