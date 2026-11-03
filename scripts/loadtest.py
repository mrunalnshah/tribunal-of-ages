"""A load test of the API, for docs/SCORECARD.md. Run it against your local stack only:
the free Space is shared hardware, and load-testing it would abuse a free service.

    DAILY_BUDGET=20 VISITOR_DAILY_LIMIT=1000 docker compose --profile full up -d --build
    uv run locust -f scripts/loadtest.py --host http://localhost:8000 \\
        --headless --users 100 --spawn-rate 10 --run-time 2m --only-summary

Each simulated visitor loads the catalog, checks the API's readiness now and then, and
sometimes submits a case. A verdict answered 429 counts as a success: once the budget is
spent, refusing at once is the designed behavior under a flood, and this measures how fast.
"""

from locust import HttpUser, between, task

CASE = {
    "crime": "My roommate ate my leftover pizza from the fridge.",
    "outrage": 3,
    "record": False,  # load tests stay out of the public record
}


class Visitor(HttpUser):
    wait_time = between(1, 3)

    @task(10)
    def catalog(self) -> None:
        self.client.get("/api/v1/catalog")

    @task(2)
    def ready(self) -> None:
        self.client.get("/readyz")  # touches Qdrant, like every search does

    @task(1)
    def verdict(self) -> None:
        with self.client.post("/api/v1/verdicts", json=CASE, catch_response=True) as response:
            if response.status_code in (200, 429):
                response.success()
