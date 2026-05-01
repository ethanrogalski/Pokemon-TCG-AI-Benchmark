from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Game, Leaderboard, Tournament, TournamentMatch, TournamentParticipant

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GameCreate(BaseModel):
    ai1_model: str
    ai2_model: str
    winner_model: Optional[str] = None  # None if game not yet complete


class TournamentCreate(BaseModel):
    name: str
    participants: list[str]  # list of ai_model names, length must be 16


class MatchResult(BaseModel):
    winner_participant_id: int
    game_id: Optional[str] = None  # ptcg-server game ID for replay lookup


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/")
def read_root():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------

@router.post("/games", status_code=201)
def create_game(body: GameCreate, db: Session = Depends(get_db)):
    game = Game(
        ai1_model=body.ai1_model,
        ai2_model=body.ai2_model,
        winner_model=body.winner_model,
        completed_at=datetime.now(timezone.utc) if body.winner_model else None,
    )

    if body.winner_model:
        if body.winner_model not in (body.ai1_model, body.ai2_model):
            raise HTTPException(status_code=400, detail="winner_model must be one of the two players.")
        loser = body.ai2_model if body.winner_model == body.ai1_model else body.ai1_model
        _update_leaderboard(db, winner=body.winner_model, loser=loser)

    db.add(game)
    db.flush()
    db.commit()
    db.refresh(game)
    return game


@router.get("/games")
def list_games(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return db.query(Game).order_by(Game.created_at.desc()).offset(offset).limit(limit).all()


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

@router.get("/leaderboard")
def get_leaderboard(db: Session = Depends(get_db)):
    return db.query(Leaderboard).order_by(Leaderboard.rank.nulls_last()).all()


# ---------------------------------------------------------------------------
# Tournaments
# ---------------------------------------------------------------------------

@router.get("/tournaments")
def list_tournaments(db: Session = Depends(get_db)):
    return db.query(Tournament).order_by(Tournament.created_at.desc()).all()


@router.post("/tournaments", status_code=201)
def create_tournament(body: TournamentCreate, db: Session = Depends(get_db)):
    if len(body.participants) != 16:
        raise HTTPException(status_code=400, detail="Tournament requires exactly 16 participants.")

    tournament = Tournament(name=body.name)
    db.add(tournament)
    db.flush()

    # Seed participants
    participants = []
    for seed, model in enumerate(body.participants, start=1):
        p = TournamentParticipant(
            tournament_id=tournament.tournament_id,
            ai_model=model,
            seed=seed,
        )
        db.add(p)
        participants.append(p)
    db.flush()

    # Round 1 (matches 1-8): pair by seed (1v16, 2v15, ..., 8v9)
    for match_number in range(1, 9):
        p1 = participants[match_number - 1]
        p2 = participants[16 - match_number]
        db.add(TournamentMatch(
            tournament_id=tournament.tournament_id,
            round_number=1,
            match_number=match_number,
            participant1_id=p1.participant_id,
            participant2_id=p2.participant_id,
        ))

    # Rounds 2-4: slots filled as results come in
    # Round 2 has four matches, 9-12. Round 3 has two matches, 13-14. Round 4 (final) is match 15.
    for rnd, count, start in [(2, 4, 9), (3, 2, 13), (4, 1, 15)]:
        for i in range(count):
            db.add(TournamentMatch(
                tournament_id=tournament.tournament_id,
                round_number=rnd,
                match_number=start + i,
            ))

    db.commit()
    db.refresh(tournament)
    return tournament


@router.get("/tournaments/{tournament_id}")
def get_tournament(tournament_id: str, db: Session = Depends(get_db)):
    tournament = db.query(Tournament).filter(Tournament.tournament_id == tournament_id).first()
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found.")

    matches = (
        db.query(TournamentMatch)
        .filter(TournamentMatch.tournament_id == tournament_id)
        .order_by(TournamentMatch.round_number, TournamentMatch.match_number)
        .all()
    )
    participants = (
        db.query(TournamentParticipant)
        .filter(TournamentParticipant.tournament_id == tournament_id)
        .all()
    )
    return {"tournament": tournament, "participants": participants, "matches": matches}


@router.post("/tournaments/{tournament_id}/matches/{match_id}/result")
def record_match_result(
    tournament_id: str,
    match_id: int,
    body: MatchResult,
    db: Session = Depends(get_db),
):
    match = db.query(TournamentMatch).filter(
        TournamentMatch.match_id == match_id,
        TournamentMatch.tournament_id == tournament_id,
    ).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found.")
    if match.participant1_id is None or match.participant2_id is None:
        raise HTTPException(status_code=400, detail="Match participants not yet determined.")
    if match.winner_participant_id is not None:
        raise HTTPException(status_code=400, detail="Match already has a result.")

    if body.winner_participant_id not in [match.participant1_id, match.participant2_id]:
        raise HTTPException(status_code=400, detail="Winner must be one of the match participants.")
    match.winner_participant_id = body.winner_participant_id
    if body.game_id:
        match.game_id = body.game_id

    # Advance winner into the next round
    _advance_bracket(db, tournament_id, match, body.winner_participant_id)

    # Update global leaderboard
    winner_p = db.query(TournamentParticipant).filter(
        TournamentParticipant.participant_id == body.winner_participant_id
    ).first()
    loser_id = (
        match.participant2_id
        if body.winner_participant_id == match.participant1_id
        else match.participant1_id
    )
    loser_p = db.query(TournamentParticipant).filter(
        TournamentParticipant.participant_id == loser_id
    ).first()
    if winner_p and loser_p:
        _update_leaderboard(db, winner=winner_p.ai_model, loser=loser_p.ai_model)

    # Mark tournament complete when the final (match 15) is decided
    if match.match_number == 15 and winner_p:
        tournament = db.query(Tournament).filter(Tournament.tournament_id == tournament_id).first()
        # Just for Python's type checker
        if tournament:
            tournament.status = "completed"
            tournament.winner = winner_p.ai_model
            tournament.completed_at = datetime.now(timezone.utc)

    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _update_leaderboard(db: Session, winner: str, loser: str):
    for model, field in [(winner, "wins"), (loser, "losses")]:
        row = db.query(Leaderboard).filter(Leaderboard.ai_model == model).first()
        if not row:
            row = Leaderboard(ai_model=model, wins=0, losses=0)
            db.add(row)
            db.flush()
        if field == "wins":
            row.wins += 1
        else:
            row.losses += 1
        row.updated_at = datetime.now(timezone.utc)

    # Recalculate ranks by win count descending
    all_rows = db.query(Leaderboard).order_by(Leaderboard.wins.desc()).all()
    for rank, row in enumerate(all_rows, start=1):
        row.rank = rank


# Which next-round match each match feeds into, and which participant slot (1 or 2)
_NEXT_MATCH: dict[int, tuple[int, int]] = {
    1: (9, 1),  2: (9, 2),
    3: (10, 1), 4: (10, 2),
    5: (11, 1), 6: (11, 2),
    7: (12, 1), 8: (12, 2),
    9: (13, 1), 10: (13, 2),
    11: (14, 1), 12: (14, 2),
    13: (15, 1), 14: (15, 2),
}


def _advance_bracket(db: Session, tournament_id: str, match: TournamentMatch, winner_id: int):
    next_info = _NEXT_MATCH.get(match.match_number)
    if not next_info:
        return  # final — no next match
    next_match_number, slot = next_info
    next_match = db.query(TournamentMatch).filter(
        TournamentMatch.tournament_id == tournament_id,
        TournamentMatch.match_number == next_match_number,
    ).first()
    if not next_match:
        return
    if slot == 1:
        next_match.participant1_id = winner_id
    else:
        next_match.participant2_id = winner_id
