def build_action_tools(hand_size):
    return [
        {
            "name": "play_card",
            "description": (
                "Play a card from your hand. Use for trainers, supporters, items, stadiums, "
                "playing Basic Pokemon to bench, attaching energy to a Pokemon, or evolving a Pokemon."
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
                            "ACTIVE: to place first Pokemon, attach energy to active, or evolve the Active Pokemon. "
                            "BENCH: to place a Basic Pokemon on bench, attach energy to a bench Pokemon, or evolve a bench Pokemon."
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
            "description": (
                "Use your active Pokemon's attack. This ENDS your turn. "
                "You cannot use an attack if the pokemon has less energy (or not the right energy types) as required. "
                "Include a message explaining why you chose this attack — spectators should understand your reasoning."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "attack_name": {
                        "type": "string",
                        "description": "The exact name of the attack. Use your knowledge of the card.",
                    },
                    "message": {
                        "type": "string",
                        "description": "1-2 sentences for spectators explaining why you are using this attack and what you are trying to achieve. Max 256 chars.",
                    },
                },
                "required": ["attack_name", "message"],
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
            "name": "use_ability",
            "description": (
                "Activate a once-per-turn Ability on one of your Pokémon. "
                "Only use for Abilities that say 'Once during your turn' or similar. "
                "Passive Abilities are always active and do NOT need activation. "
                "Use abilities BEFORE attaching energy or attacking."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "ability_name": {
                        "type": "string",
                        "description": "Exact name of the Ability as shown in the board state.",
                    },
                    "target_slot": {
                        "type": "string",
                        "enum": ["ACTIVE", "BENCH"],
                        "description": "Where the Pokémon with the ability is located.",
                    },
                    "bench_index": {
                        "type": "integer",
                        "description": "Bench slot 0-4. Required when target_slot=BENCH.",
                    },
                },
                "required": ["ability_name", "target_slot"],
            },
        },
        {
            "name": "pass_turn",
            "description": (
                "End your turn without attacking. Only use this after you have played ALL useful cards "
                "from your hand (trainers, items, supporters, Pokémon to bench, energy attachment, abilities). "
                "Do NOT pass if there are still cards to play or abilities to use that could be beneficial."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "1-2 sentences for spectators explaining why you are passing and what your strategy is going forward. This will be sent as a chat message.",
                    }
                },
                "required": ["reason"],
            },
        },
    ]
