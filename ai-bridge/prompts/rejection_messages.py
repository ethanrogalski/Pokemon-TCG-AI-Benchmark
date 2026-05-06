REJECTION_MESSAGES = {
    "CAN_ONLY_SELECT_TWO_DIFFERENT_ENERGY_TYPES": (
        "You picked two energy cards of the SAME type. "
        "You must pick energy cards of DIFFERENT types (e.g. one Fire Energy and one Psychic Energy)."
    ),
    "PROMPT_INVALID_RESULT": (
        "Your selection was invalid. Check the eligible indices and constraints carefully."
    ),
    "CANNOT_ATTACK_ON_FIRST_TURN": (
        "You cannot attack on the very first turn of the game. Pass your turn instead."
    ),
    "ENERGY_ALREADY_ATTACHED": (
        "You already attached an Energy card this turn. You may only attach 1 Energy per turn. Do not play another Energy card."
    ),
    "CANNOT_PLAY_THIS_CARD": (
        "That card cannot be played in that slot or at this time. Check the card type and target slot. Choose a different card to play."
    ),
    "UNKNOWN_CARD": (
        "The hand_index you chose is out of range. Use an index between 0 and the last card shown in your hand."
    ),
    "NOT_ENOUGH_ENERGY": (
        "You do not have enough Energy cards attached to that Pokémon to use the action you just tried. This could be an attack or a retreat or ability. Check the Energy requirements for the action and the Energy cards attached to that Pokémon."
    
    ),
    "UNKNOWN_ATTACK": (
        "That attack name does not exist on your active Pokémon. Use the exact attack name shown in the board state."
    ),
    "CANNOT_RETREAT": (
        "You cannot retreat right now. Your Pokémon may not have enough energy to pay the retreat cost, "
        "or a card effect is preventing retreat."
    ),
    "RETREAT_ALREADY_USED": (
        "You already retreated this turn. You can only retreat once per turn."
    ),
    "POKEMON_CANT_EVOLVE_THIS_TURN": (
        "That Pokémon cannot evolve this turn. You cannot evolve a Pokémon that was played this turn, "
        "already evolved this turn, or on your very first turn."
    ),
    "POKEMON_TOOL_ALREADY_ATTACHED": (
        "That Pokémon already has a Tool card attached. Only one Tool can be attached per Pokémon."
    ),
    "BLOCKED_BY_ABILITY": (
        "That action is blocked by an Ability in play. Check both players' Pokémon for Abilities that restrict this action."
    ),
    "BLOCKED_BY_EFFECT": (
        "That action is blocked by a card effect currently in play."
    ),
    "BLOCKED_BY_SPECIAL_CONDITION": (
        "That action is blocked by a Special Condition (Asleep or Paralyzed prevents attacking and retreating)."
    ),
    "SAME_STADIUM_ALREADY_IN_PLAY": (
        "That Stadium is already in play. You cannot play a duplicate of the current Stadium."
    ),
    "SUPPORTER_ALREADY_PLAYED": (
        "You already played a Supporter this turn. You may only play one Supporter per turn. You cannot play another supporter card."
        "Also, you cannot play any Supporter on your very first turn of the game."
    ),
    "INVALID_PROMPT_RESULT": (
        "Your response did not match the expected format. Check the prompt instructions and input schema carefully."
    )
}
