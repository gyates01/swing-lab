import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env", override=False)
DATA_DIR = ROOT / "data"
REPORTS_DIR = DATA_DIR / "reports"
DB_PATH = DATA_DIR / "swing.db"

OBSIDIAN_VAULT = Path("E:/Downloads/Other/Obsidian Vault")
OBSIDIAN_STRATEGY_NOTE = OBSIDIAN_VAULT / "Active" / "Claude for Trading — Methods, Strategies & Personal Framework.md"
OBSIDIAN_SWING_LAB_DIR = OBSIDIAN_VAULT / "Active" / "Swing Lab"

# Momentum lookback windows (trading days)
MOMENTUM_LONG_MONTHS = 12
MOMENTUM_SKIP_MONTHS = 1  # skip most recent month to avoid reversal

# Macro gate thresholds
GATE_FULL = 70    # score >= 70 → full sizing
GATE_PARTIAL = 40 # score 40-69 → 60% sizing
# score < 40 → stand down

# Universe
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# Position sizing
MAX_POSITION_PCT = 0.08   # max 8% in any single name
TOP_N_PICKS = 20          # scanner output size
REVIEW_TOP_N = 6          # candidates sent to Claude review

# Recommendation engine
RECOMMEND_TOP_N = 3          # number of ranked recommendations to output
RECOMMEND_RED_FLAG_MAX = 2   # skip candidates with more than this many red flags

# Rebalance: bi-weekly (every other Sunday)
REBALANCE_DAY_OF_WEEK = 6  # Sunday
REBALANCE_EVERY_N_WEEKS = 2

# Postmortem
POSTMORTEM_TRADE_LIMIT = 30

# Broker integration (Robinhood)
BROKER = "robinhood"
KEYRING_SERVICE = "swing_lab_robinhood"
SYNC_LOOKBACK_DAYS = 90        # how far back `sync` pulls filled orders
REC_MATCH_WINDOW_DAYS = 5      # trading-day window to link a trade to a recommendation

# Outcome capture options (used by dashboard + CLI)
OUTCOME_THESIS_OPTIONS = ("yes", "partial", "no", "unclear")
OUTCOME_DRIVER_OPTIONS = (
    "target_hit", "stop_loss", "thesis_broken", "macro_shift",
    "sector_rotation", "time_stop", "discretionary",
)

# Claude model + analyst agent settings
MODEL = "claude-opus-4-8"
ANALYST_MAX_TURNS = 5
ANALYST_SNAPSHOT_TTL_SECONDS = 300


def get_api_key() -> str:
    key = os.environ.get("SWING_LAB_ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "SWING_LAB_ANTHROPIC_API_KEY is not set. "
            "Add it to your shell env or create a .env file at the repo root."
        )
    return key


_CRED_KEYS = ("username", "password", "totp_seed")


def store_broker_credentials(username: str, password: str, totp_seed: str) -> None:
    """Persist Robinhood credentials to the OS keyring (Windows Credential Manager)."""
    import keyring
    values = {"username": username, "password": password, "totp_seed": totp_seed}
    for key in _CRED_KEYS:
        keyring.set_password(KEYRING_SERVICE, key, values[key])


def get_broker_credentials() -> dict:
    """Return {username, password, totp_seed} from the keyring, or raise if unset.

    Only username and password are required. A blank `totp_seed` is valid: it
    means the account uses device-approval (mobile-app prompt) 2FA rather than an
    authenticator-app TOTP secret.
    """
    import keyring
    creds = {key: keyring.get_password(KEYRING_SERVICE, key) for key in _CRED_KEYS}
    if not creds["username"] or not creds["password"]:
        raise RuntimeError(
            "Robinhood credentials not found. Run `swing-lab broker-login` first."
        )
    creds["totp_seed"] = creds["totp_seed"] or ""
    return creds
