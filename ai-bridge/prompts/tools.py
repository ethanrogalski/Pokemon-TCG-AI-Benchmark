def build_action_tools(hand_size, chat_sent_this_turn):
    return [
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
            "name": "pass_turn",
            "description": (
                "End your turn without attacking. Only use this after you have played ALL useful cards "
                "from your hand (trainers, items, supporters, Pokémon to bench, energy attachment). "
                "Do NOT pass if there are still cards to play that could be beneficial."
                "Do not be afraid to put pokemon on your bench"
                "if it helps your position."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "1-2 sentences for spectators explaining why you are passing and what your strategy is going forward. This will be sent as a chat message.",
                    }
                },
                "required": [],
            },
        },
        {
            "name": "send_chat_message",
            "description": (
                "You have already chatted this turn. Do NOT use again unless responding to your opponent."
                if chat_sent_this_turn else
                "Narrate your strategy for spectators. Does NOT end your turn — you will be called for another action immediately after. "
                "Use once per turn to explain what you are doing and why — your plan, a key decision, or a reaction to the board state."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "1-2 sentences of strategic commentary for spectators. Max 256 characters.",
                    }
                },
                "required": ["message"],
            },
        },
    ]
