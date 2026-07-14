UNIFIED_SCHEMA = {
    # ---- identity ------------------------------------------------
    "event_id":       "str",       # Original CSV `id` (e.g. {S00001-R1})
    "timestamp":      "datetime",  # Parsed from CSV `date` field
    "user_id":        "str",       # CSV `user` column (e.g. ACM2278)
    "pc":             "str",       # CSV `pc`  column (e.g. PC-1042)
 
    # ---- classification ------------------------------------------
    "event_type":     "str",       # One of the EVENT_* constants below
 
    # ---- event-specific payload ----------------------------------
    # Logon/Device   → maps to `activity`      (Logon/Logoff/Connect/Disconnect)
    # File           → maps to `filename`
    # Email          → maps to recipient list  (to + cc + bcc) / sender
    # HTTP           → maps to `url`
    "details":        "str",
 
    # Email-only extras (NULL for non-email events)
    "email_from":     "str",
    "email_to":       "str",
    "email_cc":       "str",
    "email_bcc":      "str",
    "email_size":     "int",
    "email_attachments": "int",    # number of attachments
 
    # Content field (file, email, http) — store as text / summary
    "content":        "str",
 
    # ---- derived time features -----------------------------------
    "is_after_hours": "bool",      # True if outside 08:00–18:00 Mon-Fri
    "day_of_week":    "int",       # 0 = Monday … 6 = Sunday
    "hour_of_day":    "int",       # 0–23
 
    # ---- scoring (filled by detection engine) --------------------
    "risk_score":     "float",     # 0.0–100.0
    "is_anomaly":     "bool",      # True = flagged by ML / rule engine
}
 
# ------------------------------------------------------------------
# EVENT TYPE CONSTANTS
# Use these everywhere — never bare strings.
# ------------------------------------------------------------------
EVENT_LOGON        = "LOGON"          # logon.csv  activity == "Logon"
EVENT_LOGOFF       = "LOGOFF"         # logon.csv  activity == "Logoff"
EVENT_USB_CONNECT  = "USB_CONNECT"    # device.csv activity == "Connect"
EVENT_USB_DISCONNECT = "USB_DISCONNECT" # device.csv activity == "Disconnect"
EVENT_FILE         = "FILE_ACCESS"    # file.csv
EVENT_EMAIL        = "EMAIL"          # email.csv
EVENT_HTTP         = "WEB_VISIT"      # http.csv
 
# Convenience set for quick membership tests
ALL_EVENT_TYPES = {
    EVENT_LOGON, EVENT_LOGOFF,
    EVENT_USB_CONNECT, EVENT_USB_DISCONNECT,
    EVENT_FILE, EVENT_EMAIL, EVENT_HTTP,
}
 
# ------------------------------------------------------------------
# AFTER-HOURS DEFINITION
# ------------------------------------------------------------------
WORK_START_HOUR = 8    # 08:00
WORK_END_HOUR   = 18   # 18:00
WORK_DAYS       = {0, 1, 2, 3, 4}   # Monday–Friday
 
def is_after_hours(dt) -> bool:
    """Return True if the datetime `dt` is outside normal working hours."""
    if dt.weekday() not in WORK_DAYS:
        return True
    return not (WORK_START_HOUR <= dt.hour < WORK_END_HOUR)
 
# ------------------------------------------------------------------
# COLUMN MAPPINGS — raw CSV → unified schema
# Used by the ingestion scripts to rename columns consistently.
# ------------------------------------------------------------------
 
LOGON_COL_MAP = {
    "id":       "event_id",
    "date":     "timestamp",
    "user":     "user_id",
    "pc":       "pc",
    "activity": "details",     # "Logon" / "Logoff"
}
 
DEVICE_COL_MAP = {
    "id":       "event_id",
    "date":     "timestamp",
    "user":     "user_id",
    "pc":       "pc",
    "activity": "details",     # "Connect" / "Disconnect"
}
 
FILE_COL_MAP = {
    "id":       "event_id",
    "date":     "timestamp",
    "user":     "user_id",
    "pc":       "pc",
    "filename": "details",
    "content":  "content",
}
 
EMAIL_COL_MAP = {
    "id":       "event_id",
    "date":     "timestamp",
    "user":     "user_id",
    "pc":       "pc",
    "to":       "email_to",
    "cc":       "email_cc",
    "bcc":      "email_bcc",
    "from":     "email_from",
    "size":     "email_size",
    "attachments": "email_attachments",
    "content":  "content",
}
 
HTTP_COL_MAP = {
    "id":       "event_id",
    "date":     "timestamp",
    "user":     "user_id",
    "pc":       "pc",
    "url":      "details",
    "content":  "content",
}
 
PSYCHOMETRIC_COL_MAP = {
    "employee": "employee_name",
    "user_id":  "user_id",
    "O":        "openness",
    "C":        "conscientiousness",
    "E":        "extraversion",
    "A":        "agreeableness",
    "N":        "neuroticism",
}
 
INSIDERS_COL_MAP = {
    "dataset":  "dataset",
    "scenario": "scenario",
    "details":  "scenario_details",
    "user":     "user_id",
    "start":    "start_date",
    "end":      "end_date",
}

# ------------------------------------------------------------------
# FILE PATHS — processed outputs
# ------------------------------------------------------------------
# import os

# PROCESSED_DIR  = os.path.join("data", "processed")
# FEATURES_CSV   = os.path.join(PROCESSED_DIR, "user_daily_features.csv")
# BASELINES_CSV  = os.path.join(PROCESSED_DIR, "user_baselines.csv")

# ------------------------------------------------------------------
# FILE PATHS — processed outputs
# ------------------------------------------------------------------
import os

PROJECT_ROOT   = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR  = os.path.join(PROJECT_ROOT, "..", "data", "processed")
FEATURES_CSV   = os.path.join(PROCESSED_DIR, "user_daily_features.csv")
BASELINES_CSV  = os.path.join(PROCESSED_DIR, "user_baselines.csv")
RISK_SCORES_CSV = os.path.join(PROCESSED_DIR, "risk_scores.csv")