"""
agent.py — AI decision engine for the Pokemon TCG bot.

Swap this file (or change the import in MCP.py) to use a different AI provider.

Contract:
    get_ai_action(players, game_state, my_index, card_names, card_lookup)
        -> (action_name: str, action_input: dict)

    action_name values:
        "play_card"  -> { hand_index: int, target_slot: "BOARD"|"ACTIVE"|"BENCH", bench_index?: int }
        "attack"     -> { attack_name: str }
        "pass_turn"  -> {}
"""

# change two lines below to specific ai agent
import anthropic

anthropic_client = anthropic.Anthropic()

SYSTEM_PROMPT = """You are an expert Pokemon Trading Card Game player. Your goal is to WIN.

RULES YOU MUST FOLLOW:
- You can play multiple cards per turn but only ONE Supporter per turn
- You can attach ONE energy per turn (to any Pokemon you control)
- Basic Pokemon go to Bench (use target_slot=BENCH) or Active if empty (use ACTIVE)
- Trainer/Supporter/Item/Stadium cards use target_slot=BOARD
- Energy cards use target_slot=ACTIVE (for active) or BENCH with bench_index for bench Pokemon
- Attacking ends your turn — only attack when ready

STRATEGY:
- Early game: fill bench with Basics, attach energy to your main attacker, use draw supporters
- Mid game: evolve when possible, keep energy building on attackers
- Late game: attack aggressively, target knockouts for prizes
- Always consider: can I knock out their active Pokemon this turn?
- Use your knowledge of Pokemon TCG cards — you know what each card does

You will be called once per action. Play one card at a time, then attack when ready."""


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
        attack_str = (
            ", ".join(
                f"{a['name']} [{a.get('damage', '?')} dmg, cost: {'+'.join(a.get('cost', []))}]"
                for a in my_active["attacks"]
            )
            if my_active["attacks"]
            else "unknown (use your knowledge of this card)"
        )
        lines += [
            f"  {my_active['name']} | HP: {my_active['hp']} | Damage taken: {my_active['damage']}",
            f"  Energy attached: {', '.join(my_active['energies']) if my_active['energies'] else 'none'}",
            f"  Attacks: {attack_str}",
            f"  Special conditions: {', '.join(my_active['conditions']) if my_active['conditions'] else 'none'}",
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
            lines.append(f"  {b['name']} | HP: {b['hp']} | Damage: {b['damage']}")
    else:
        lines.append("  (empty)")

    return "\n".join(lines)


def get_ai_action(players, game_state, my_index, card_names, card_lookup):
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
            "description": "Use your active Pokemon's attack. This ENDS your turn. Only attack if you have enough energy.",
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
            "name": "pass_turn",
            "description": "End your turn without attacking. Use when you truly cannot attack.",
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
        model="claude-opus-4-6",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        tools=tools,
        tool_choice={"type": "any"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"{state_prompt}\n\n"
                    "Choose your next action. You can play cards one at a time — "
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
