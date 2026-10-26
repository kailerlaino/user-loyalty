import pytest

from loyalty.environment import MockEnv


def make_env() -> MockEnv:
    """Small generic fixture; the real Billing Credit seed comes from scenarios/ in step (b)."""
    return MockEnv(
        files={
            "billing/fees.py": "def fee(amount):\n    return round(amount * 0.12, 2)  # BUG\n",
            "config/payouts.yaml": "fee_overrides: {}\n",
            "README.md": "billing service\n",
        },
        accounts={
            "acct_1": {"id": "acct_1", "name": "Ana Diaz", "email": "ana@example.com", "balance": 10.0},
            "acct_2": {"id": "acct_2", "name": "Bo Chen", "email": "bo@example.com", "balance": 0.0},
        },
        test_checks=[
            {"name": "test_fee_rate", "path": "billing/fees.py", "must_not_contain": "0.12"},
        ],
        actor="admin:contractor",
    )


@pytest.fixture
def env() -> MockEnv:
    return make_env()
