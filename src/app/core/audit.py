import logging

audit_log = logging.getLogger("app.audit")
audit_log.setLevel(logging.INFO)
if not audit_log.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    audit_log.addHandler(handler)
