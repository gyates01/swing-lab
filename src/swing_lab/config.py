import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
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


def get_api_key() -> str | None:
    """Return the Swing Lab Anthropic API key, falling back to the generic key."""
    return os.environ.get("SWING_LAB_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
