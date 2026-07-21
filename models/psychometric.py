import pandas as pd, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logs.database import get_connection
from logs.schema import PROCESSED_DIR

PSYCH_MODIFIERS_CSV = os.path.join(PROCESSED_DIR, "psychometric_modifiers.csv")

# Research basis (project doc Section 3.1 / Shaw & Stock 2011): high
# Neuroticism, low Conscientiousness, and low Agreeableness correlate
# with workplace rule-breaking. Openness and Extraversion are not used —
# no comparable evidence links them to insider-threat risk.
MODIFIER_MIN = 0.8
MODIFIER_MAX = 1.4


def compute_modifiers():
    conn = get_connection()
    df = pd.read_sql(
        'SELECT user_id, neuroticism, conscientiousness, agreeableness FROM psychometric_profiles',
        conn
    )
    conn.close()

    if df.empty:
        print("No psychometric profiles found.")
        return df

    # Normalise each trait 0-1 relative to THIS population's own range,
    # since the raw OCEAN scale isn't guaranteed (could be 1-5, 0-1, etc.)
    def norm(s):
        lo, hi = s.min(), s.max()
        return (s - lo) / (hi - lo) if hi > lo else s * 0 + 0.5

    n_norm = norm(df['neuroticism'])          # high N = more risk
    c_risk = 1 - norm(df['conscientiousness']) # low C = more risk
    a_risk = 1 - norm(df['agreeableness'])     # low A = more risk

    # Average the three risk-relevant traits into one 0-1 "risky personality"
    # score, then map it linearly onto the doc's specified 0.8-1.4 range.
    risk_component = (n_norm + c_risk + a_risk) / 3
    df['modifier'] = (MODIFIER_MIN + risk_component * (MODIFIER_MAX - MODIFIER_MIN)).round(3)

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    df[['user_id', 'modifier']].to_csv(PSYCH_MODIFIERS_CSV, index=False)
    print(f"Psychometric modifiers computed for {len(df)} users.")
    print(f"Modifier range: {df['modifier'].min()} - {df['modifier'].max()} (mean {df['modifier'].mean():.3f})")
    print(f"Saved: {PSYCH_MODIFIERS_CSV}")
    return df[['user_id', 'modifier']]


if __name__ == '__main__':
    compute_modifiers()