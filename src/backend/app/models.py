import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from app.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Game(Base):
    __tablename__ = "games"

    game_id = Column(String, primary_key=True, default=_new_uuid)
    ai1_model = Column(String, nullable=False)   # claude | gemini | llama
    ai2_model = Column(String, nullable=False)
    winner_model = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)


class GameState(Base):
    __tablename__ = "game_states"

    state_id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(String, ForeignKey("games.game_id"), nullable=False)
    move_number = Column(Integer, nullable=False)
    state_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

# When a tournament is created, make sure to create all 15 tournament matches and fill them will null
# Fill these up as the tournament is completed
# Round 1 has matches 1 - 8, Round 2 has matches 9-12, Round 3 has matches 13-14, Round 4 has match 15

class Tournament(Base):
    __tablename__ = "tournaments"

    tournament_id = Column(String, primary_key=True, default=_new_uuid)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending | in_progress | completed
    winner = Column(String, nullable=True)  # ai_model name of the champion
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)


class TournamentParticipant(Base):
    __tablename__ = "tournament_participants"

    participant_id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(String, ForeignKey("tournaments.tournament_id"), nullable=False)
    ai_model = Column(String, nullable=False)  # claude | gemini | llama
    seed = Column(Integer, nullable=False)  # 1–16, determines bracket position


class TournamentMatch(Base):
    __tablename__ = "tournament_matches"

    match_id = Column(Integer, primary_key=True, autoincrement=True)
    tournament_id = Column(String, ForeignKey("tournaments.tournament_id"), nullable=False)
    game_id = Column(String, ForeignKey("games.game_id"), nullable=True)  # null until played
    round = Column(Integer, nullable=False)         # 1=R1(8 matches), 2=QF, 3=SF, 4=Final
    match_number = Column(Integer, nullable=False)  # position within the round (1-indexed)
    participant1_id = Column(Integer, ForeignKey("tournament_participants.participant_id"), nullable=True)
    participant2_id = Column(Integer, ForeignKey("tournament_participants.participant_id"), nullable=True)
    winner_participant_id = Column(Integer, ForeignKey("tournament_participants.participant_id"), nullable=True)


class Leaderboard(Base):
    __tablename__ = "leaderboard"

    ai_model = Column(String, primary_key=True)  # claude | gemini | llama
    wins = Column(Integer, nullable=False, default=0)
    losses = Column(Integer, nullable=False, default=0)
    rank = Column(Integer, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
