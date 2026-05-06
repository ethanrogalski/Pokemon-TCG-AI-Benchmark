import { Request, Response } from "express";
import { Controller } from "./controller";

export class LiveGames extends Controller {
  public init(): void {
    this.app.get("/v1/live-games", this.getLiveGames.bind(this));
  }

  private getLiveGames(req: Request, res: Response): void {
    // Mock live games data for demo purposes
    const mockGames = [
      {
        id: "4521",
        playerA: "Claude 3.5 Haiku",
        playerB: "GPT-4",
        status: "In Progress",
        phase: "Battle Phase",
        startedAt: "2m ago",
        duration: "08:42",
        watchers: 12,
        score: "4 - 3",
        lastAction: "Claude attached Lightning Energy to Active",
      },
      {
        id: "4487",
        playerA: "Gemini Pro",
        playerB: "Claude 3 Opus",
        status: "In Progress",
        phase: "Setup Phase",
        startedAt: "5m ago",
        duration: "02:15",
        watchers: 8,
        score: "0 - 0",
        lastAction: "Gemini is setting up deck",
      },
      {
        id: "4465",
        playerA: "Simple Bot",
        playerB: "GPT-4",
        status: "Finished",
        phase: "Game End",
        startedAt: "12m ago",
        duration: "15:33",
        watchers: 3,
        score: "6 - 2",
        lastAction: "GPT-4 wins by knockout",
      },
    ];

    res.json({ games: mockGames });
  }
}
