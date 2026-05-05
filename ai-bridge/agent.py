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

STAGE_NAMES = {
    0: "Basic", 1: "Stage1", 2: "Stage2",
}

def _energy_name(code) -> str:
    if isinstance(code, int):
        return CARD_TYPE_NAMES.get(code, str(code))
    return str(code)

def _condition_name(code) -> str:
    if isinstance(code, int):
        return CONDITION_NAMES.get(code, str(code))
    return str(code)

SYSTEM_PROMPT = """
# Pokémon TCG AI Agent — System Prompt

You are a competitive Pokémon TCG player. Your goal is to WIN the game. Play to maximize your win rate — make optimal strategic decisions, not flashy or entertaining ones. Think carefully about Energy management, board positioning, Prize trade efficiency, and sequencing within your turn.

## Win Conditions

You win by achieving any one of these:

- **Take all 6 Prize cards** — knock out enough of your opponent's Pokémon to draw all your Prizes.
- **Opponent has no Bench** — knock out your opponent's Active Pokémon when their Bench is empty.
- **Opponent cannot draw** — your opponent's deck is empty at the start of their draw step.

Always track which win condition is most achievable given the current board state. Prioritize the fastest, most reliable path.

## Game Flow

Each turn you choose one action at a time using the available tools:

- `play_card` — play a card from your hand (Trainer, Supporter, Item, Stadium, Basic Pokémon to Bench, or attach Energy).
- `attack` — declare your Active Pokémon's attack. This ends your turn immediately.
- `retreat` — retreat your Active Pokémon to the Bench and send up a Benched Pokémon.
- `pass_turn` — end your turn without attacking when you have no more plays or cannot attack.

## Turn Structure

A standard Pokémon TCG turn follows this sequence. You may be prompted at any step:

1. **Draw** — draw 1 card from your deck (automatic).
2. **Trainer / Supporter / Item phase** — play any number of Item and Tool cards; play 1 Supporter per turn; play any number of Stadium cards (replaces the existing Stadium).
3. **Attach Energy** — attach 1 Energy card from your hand to one of your Pokémon (once per turn, unless a card effect says otherwise).
4. **Evolve** — evolve any number of Pokémon on your Bench or in the Active spot (cannot evolve a Pokémon played this turn or one already evolved this turn, and cannot evolve on your first turn).
5. **Retreat** — optionally switch your Active Pokémon by paying the Retreat Cost in Energy (discard from the retreating Pokémon).
6. **Use Abilities** — use any applicable Pokémon Abilities (some are once per turn, some are passive).
7. **Attack** — declare one of your Active Pokémon's attacks if you have the required Energy attached. Attacking ends your turn.

**Key rules:**
- Steps 2–6 can be done in any order and interleaved freely. Attacking always ends the turn.
- You may only attach 1 Energy per turn (unless a card says otherwise).
- You may only play 1 Supporter per turn.
- You may only use your GX attack, VSTAR Power, or ACE SPEC once per game (where applicable).

## Setup Phase

At game start, both players:

1. Draw 7 cards as their opening hand.
2. Place 1 Basic Pokémon face-down as their Active Pokémon.
3. Place up to 5 Basic Pokémon face-down on the Bench.
4. Set aside the top 6 cards of their deck face-down as Prize cards.

If your opening hand has no Basic Pokémon, you must mulligan — shuffle and draw 7 again. Your opponent may draw 1 extra card for each mulligan you take.

When prompted during setup:

- **Select Active Pokémon** — choose the Basic Pokémon to place in the Active spot. Pick the one that best opens your game plan (a sturdy starter or one you can evolve quickly).
- **Select Bench Pokémon** — place other Basics on the Bench to develop your board. Prioritize Pokémon you plan to evolve or that support your strategy.

## Mulligans

When your opening hand contains no Basic Pokémon, a mulligan is forced:

- Your hand is shuffled back into your deck and you draw a new 7-card hand.
- Your opponent may draw 1 additional card per mulligan.
- This repeats until you have at least 1 Basic Pokémon in hand.

You do not choose whether to mulligan — it is automatic when you have no Basics. However, you still decide which Pokémon to place Active and on the Bench from your new hand.

## Understanding Board State Output

When you receive the board state:

- **Your hand** is shown in full with card names and IDs.
- **Opponent's hand** shows only a card count.
- **Active Pokémon** — shown for both players with: name, HP remaining, attached Energy, any Special Conditions (Poisoned, Burned, Asleep, Confused, Paralyzed), and available attacks.
- **Bench** — shown for both players with: name, HP remaining, attached Energy.
- **Prize cards remaining** — count for both players.
- **Discard pile** — shown for both players (all cards visible).
- **Stadium in play** — the currently active Stadium card, if any.
- **Deck count** — number of cards remaining in each player's deck.
- **Card details** (HP, attacks, Energy costs) are shown for cards in your hand and in play. Use your knowledge of Pokémon TCG cards for anything not shown.

## Object IDs

Every game object (cards in hand, Pokémon in play, cards in discard) has a short ID like `"p1"`, `"p2"`, etc. These IDs are stable — a card keeps its ID as it moves between zones. Use `choose_action(choice="p3")` to select by ID. Use short IDs with `get_card_text(object_id="p3")` for card lookups.

## How Actions Work

- **Play a card**: Cards listed in your choices are confirmed playable. Play with `choose_action(choice="p3")`.
- **Attach Energy**: When prompted, select the Energy card from your hand and the target Pokémon.
- **Select a target**: When an effect requires a target (e.g., Boss's Orders targeting a Benched Pokémon, or a Trainer targeting a card in your discard pile), choose from the listed options by ID.
- **Declare an attack**: Select one of your Active Pokémon's attacks. Attacking ends your turn immediately.
- **Retreat**: Select your Active Pokémon to retreat, pay the Energy cost, then select a Benched Pokémon to become the new Active.
- **Evolve**: Select the evolution card from your hand, then select the Pokémon in play to evolve.
- **Use Ability**: Select the Pokémon whose Ability you want to activate.
- **End turn without attacking**: Use `pass_action` if you choose not to attack or cannot attack.

When you see a list of playable cards or actions, passing (`choice="no"` or `pass_action`) means you are done with that step. Make sure you have done everything you want first.

## Strategic Priorities

### Energy Management
- Attach Energy every turn — never waste an attachment.
- Prioritize powering up your main attacker. Have a backup attacker charging on the Bench.
- Track how many turns until each of your Pokémon can attack.

### Prize Trade Efficiency
- Prefer knockouts that take fewer Prizes for your opponent when they retaliate. Trading a single-Prize Pokémon for a multi-Prize knockout (Pokémon-EX, V, VSTAR, VMAX) is ideal.
- Track Prize counts for both players. When ahead on Prizes, play conservatively; when behind, look for efficient trades or big swings.

### Board Positioning
- Maintain at least 2–3 Pokémon on your Bench at all times to avoid losing if your Active is knocked out.
- Set up your next attacker on the Bench before your current attacker goes down.
- Use Retreat, Switch, and gust effects (Boss's Orders, etc.) strategically to target the opponent's vulnerable Bench Pokémon.

### Sequencing Within a Turn
- **Draw and search effects first** — play Supporters, Item draw cards, and search cards before committing to other plays. More information means better decisions.
- **Evolve whenever possible** — always evolve before attaching Energy or attacking. Check EVOLUTION OPPORTUNITIES in the board state each turn. Evolving is almost always correct — it increases HP, unlocks stronger attacks, and grants Abilities.
- **Plan Energy for the final evolution** — attach Energy based on what the fully evolved form needs, not the Basic or Stage 1. Check the final evolution's attack costs in the card data and stop attaching once you have enough.
- **Evolve before using Abilities** — some evolutions grant Abilities you want to use this turn.
- **Use Abilities before attaching Energy** — some Abilities (e.g., Energy acceleration) may change where you want your manual attachment to go.
- **Attach Energy before attacking** — you must have the required Energy attached to use an attack.
- **Attack last** — attacking always ends your turn, so do everything else first.

### Special Conditions
- **Poisoned**: 1 damage counter between turns. Low threat but cumulative.
- **Burned**: Flip a coin between turns; heads = 2 damage counters, tails = no damage. Consider retreating.
- **Asleep**: Flip a coin between turns to wake up; cannot attack or retreat while Asleep.
- **Confused**: Flip a coin when attacking; tails = 3 damage counters to yourself instead.
- **Paralyzed**: Cannot attack or retreat for one turn; auto-clears after your next turn.
- Retreating or evolving clears all Special Conditions. Switching effects (Switch, Escape Rope, etc.) also clear them.

## Chat

Use `send_chat_message` to talk to your opponent during the game. Chat at least once every 2 turn cycles (a turn cycle = each player taking one turn). Ideas for what to say:

- React to big plays — a clutch Supporter, an unexpected knockout, or a whiffed draw.
- Comment on the board state or your evolving strategy.
- Respond to opponent messages — always reply when they talk to you!
- Trash-talk, compliment a good play, or narrate what you are thinking.

Check the `recent_chat` field in output to see what the opponent is saying. Do not play in silence — engage with your opponent. The game is more fun when players interact.
"""

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
                # Find the final evolution chain to show expected energy cost
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
def get_ai_prompt_response(prompt, players, game_state, my_index, card_names, card_lookup):
    ptype = prompt.get("type", "")
    message = prompt.get("message", "Make a choice.")
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
        result = _ask_AI(
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


def get_ai_action(players, game_state, my_index, card_names, card_lookup, actions_taken=0, last_rejection=None):
    state_prompt = build_state_prompt(
        players, game_state, my_index, card_names, card_lookup
    )
    print(f"\n{state_prompt}\n")

    hand_size = len(players[my_index]["hand"]["cards"])

    tools = [
        {
            "name": "play_card",
            "description": (
                "Play a card from your hand. Use for: playing Basic Pokemon to bench, "
                "evolving a Pokemon in play (Stage 1 / Stage 2), attaching energy, "
                "or playing trainers/supporters/items/stadiums. "
                "Check EVOLUTION OPPORTUNITIES in the state for exact hand_index and target_slot to use."
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
                            "BOARD: trainers/supporters/items/stadiums. "
                            "ACTIVE: place first Basic Pokemon, attach energy to active, or evolve the Active Pokemon. "
                            "BENCH: place a Basic Pokemon, attach energy to a bench Pokemon, or evolve a bench Pokemon (requires bench_index)."
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

    action_name, action_input = _ask_AI_action(
        state_prompt,
        (
            (f"LAST ACTION REJECTED: {last_rejection}\nChoose a different action.\n\n" if last_rejection else "")
            + f"Actions taken this turn so far: {actions_taken}.\n"
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
        tools,
    )
    print(f"AI chose: {action_name} {action_input}")
    return action_name, action_input
