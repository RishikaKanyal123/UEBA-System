# This is the standard schema for ALL events in our UEBA system
# Every raw log file gets converted to match these columns

UNIFIED_SCHEMA = {
    "event_id":       "str",   # Unique ID for this event (e.g. LOG_000001)
    "timestamp":      "datetime",  # When it happened (2023-01-15 09:32:00)
    "user_id":        "str",   # Who did it (e.g. ACM2278)
    "event_type":     "str",   # What they did: LOGIN, LOGOUT, FILE_ACCESS,
                               #   USB_INSERT, EMAIL_SEND, WEB_VISIT
    "source_ip":      "str",   # IP address they came from (nullable)
    "hostname":       "str",   # Which PC/machine (e.g. PC-1042)
    "details":        "str",   # Extra info (filename, URL, email recipient)
    "is_after_hours": "bool",  # True if event happened outside 8am-6pm
    "day_of_week":    "int",   # 0=Monday, 6=Sunday
    "hour_of_day":    "int",   # 0-23
    "risk_score":     "float", # Filled in later by detection engine (0-100)
    "is_anomaly":     "bool",  # Filled in later (True = flagged)
}

# Event type constants — use these everywhere, never raw strings
EVENT_LOGON      = "LOGIN"
EVENT_LOGOFF     = "LOGOUT"
EVENT_FILE       = "FILE_ACCESS"
EVENT_USB        = "USB_INSERT"
EVENT_EMAIL      = "EMAIL_SEND"
EVENT_HTTP       = "WEB_VISIT"

# After-hours definition
WORK_START_HOUR = 8   # 8:00 AM
WORK_END_HOUR   = 18  # 6:00 PM
WORK_DAYS       = [0, 1, 2, 3, 4]  # Monday to Friday