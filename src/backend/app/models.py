import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Game(Base):
    __tablename__ = "games"

    game_id: Mapped[str] = mapped_column(primary_key=True, default=_new_uuid)
    ai1_model: Mapped[str]
    ai2_model: Mapped[str]
    winner_model: Mapped[Optional[str]]
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]]


class Tournament(Base):
    __tablename__ = "tournaments"

    tournament_id: Mapped[str] = mapped_column(primary_key=True, default=_new_uuid)
    name: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending")  # pending | in_progress | completed
    winner: Mapped[Optional[str]]
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]]


class TournamentParticipant(Base):
    __tablename__ = "tournament_participants"

    participant_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tournament_id: Mapped[str] = mapped_column(ForeignKey("tournaments.tournament_id"))
    ai_model: Mapped[str]
    seed: Mapped[int]


class TournamentMatch(Base):
    __tablename__ = "tournament_matches"

    match_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tournament_id: Mapped[str] = mapped_column(ForeignKey("tournaments.tournament_id"))
    game_id: Mapped[Optional[str]] = mapped_column(ForeignKey("games.game_id"), default=None)
    round_number: Mapped[int]
    match_number: Mapped[int]
    participant1_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tournament_participants.participant_id"), default=None)
    participant2_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tournament_participants.participant_id"), default=None)
    winner_participant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tournament_participants.participant_id"), default=None)


class Leaderboard(Base):
    __tablename__ = "leaderboard"

    ai_model: Mapped[str] = mapped_column(primary_key=True)
    wins: Mapped[int] = mapped_column(default=0)
    losses: Mapped[int] = mapped_column(default=0)
    rank: Mapped[Optional[int]] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
