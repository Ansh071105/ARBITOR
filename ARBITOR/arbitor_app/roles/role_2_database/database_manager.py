import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

from arbitor_app.core.config import now_iso, resolve_lab_id, resolve_pc_id


class DatabaseManager:
    def __init__(self, db_path="arbitor_local.db", pg_dsn=None):
        self.db_path = str(Path(db_path))
        self.pg_dsn = (pg_dsn or os.getenv("ARBITOR_PG_DSN", "")).strip()
        self.pc_id = resolve_pc_id()
        self.lab_id = resolve_lab_id()
        self.lock = Lock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        with self.conn:
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            self.conn.execute("PRAGMA foreign_keys=ON;")
        self._schema()

    def _schema(self):
        script = """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            session_id TEXT NOT NULL UNIQUE,
            machine_id TEXT NOT NULL,
            lab_id TEXT NOT NULL DEFAULT 'LAB-1',
            started_at TEXT NOT NULL,
            heartbeat_at TEXT NOT NULL,
            ended_at TEXT,
            end_reason TEXT,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            suspended_at TEXT,
            synced INTEGER NOT NULL DEFAULT 0,
            sync_attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        );

        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            created_at TEXT NOT NULL,
            level TEXT NOT NULL,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            payload TEXT NOT NULL,
            synced INTEGER NOT NULL DEFAULT 0,
            sync_attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        );

        CREATE TABLE IF NOT EXISTS download_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            file_name TEXT NOT NULL,
            file_extension TEXT NOT NULL,
            source_domain TEXT NOT NULL,
            mime_type TEXT,
            status TEXT NOT NULL,
            decision_reason TEXT NOT NULL,
            approval_ref TEXT,
            attempt_time TEXT NOT NULL,
            synced INTEGER NOT NULL DEFAULT 0,
            sync_attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        );

        CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            violation_type TEXT NOT NULL,
            resource TEXT NOT NULL,
            description TEXT NOT NULL,
            severity TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            synced INTEGER NOT NULL DEFAULT 0,
            sync_attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        );

        CREATE TABLE IF NOT EXISTS policy_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_type TEXT NOT NULL,
            rule_value TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            UNIQUE(rule_type, rule_value)
        );

        CREATE TABLE IF NOT EXISTS allowed_extensions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_extension TEXT NOT NULL UNIQUE,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS blocked_extensions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_extension TEXT NOT NULL UNIQUE,
            reason TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS internal_repo_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL UNIQUE,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS faculty_approvals (
            approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_domain TEXT NOT NULL,
            file_extension TEXT NOT NULL,
            subject TEXT NOT NULL,
            batch TEXT NOT NULL,
            lab_scope TEXT NOT NULL DEFAULT '*',
            pc_scope TEXT NOT NULL DEFAULT '*',
            expires_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS sync_logs (
            sync_id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id INTEGER,
            sync_time TEXT NOT NULL,
            sync_status TEXT NOT NULL,
            details TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_logs_sync ON activity_logs (synced, created_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (username, status);
        CREATE INDEX IF NOT EXISTS idx_download_sync ON download_attempts (synced, attempt_time);
        CREATE INDEX IF NOT EXISTS idx_violation_sync ON violations (synced, detected_at);
        CREATE INDEX IF NOT EXISTS idx_faculty_expiry ON faculty_approvals (enabled, expires_at);
        """
        with self.lock, self.conn:
            self.conn.executescript(script)
            session_cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(sessions)").fetchall()}
            for col_sql in [
                ("suspended_at", "ALTER TABLE sessions ADD COLUMN suspended_at TEXT"),
                ("synced", "ALTER TABLE sessions ADD COLUMN synced INTEGER NOT NULL DEFAULT 0"),
                ("sync_attempts", "ALTER TABLE sessions ADD COLUMN sync_attempts INTEGER NOT NULL DEFAULT 0"),
                ("last_error", "ALTER TABLE sessions ADD COLUMN last_error TEXT"),
                ("lab_id", "ALTER TABLE sessions ADD COLUMN lab_id TEXT NOT NULL DEFAULT 'LAB-1'"),
            ]:
                if col_sql[0] not in session_cols:
                    self.conn.execute(col_sql[1])
            faculty_cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(faculty_approvals)").fetchall()}
            for col_sql in [
                ("lab_scope", "ALTER TABLE faculty_approvals ADD COLUMN lab_scope TEXT NOT NULL DEFAULT '*'"),
                ("pc_scope", "ALTER TABLE faculty_approvals ADD COLUMN pc_scope TEXT NOT NULL DEFAULT '*'"),
            ]:
                if col_sql[0] not in faculty_cols:
                    self.conn.execute(col_sql[1])
            legacy_logs = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'"
            ).fetchone()
            if legacy_logs:
                self.conn.execute(
                    """INSERT INTO activity_logs(session_id, created_at, level, category, message, payload, synced, sync_attempts, last_error)
                       SELECT NULL, created_at, level, category, message, payload, synced, sync_attempts, last_error
                       FROM audit_logs
                       WHERE NOT EXISTS (SELECT 1 FROM activity_logs LIMIT 1)"""
                )
            self.conn.execute(
                "UPDATE sessions SET status='TERMINATED' WHERE status='ENDED'"
            )
            self.conn.execute(
                "UPDATE sessions SET lab_id=? WHERE lab_id IS NULL OR TRIM(lab_id)=''",
                (self.lab_id,),
            )
            for rtype, rval in [
                ("exact", "nptel.ac.in"),
                ("exact", "iitb.ac.in"),
                ("exact", "spit.ac.in"),
                ("exact", "python.org"),
                ("exact", "php.net"),
                ("exact", "oracle.com"),
                ("exact", "mysql.com"),
                ("exact", "kaggle.com"),
                ("suffix", ".edu"),
                ("suffix", ".gov"),
                ("suffix", ".gov.in"),
                ("suffix", ".bank"),
            ]:
                self.conn.execute(
                    "INSERT OR IGNORE INTO policy_rules(rule_type, rule_value, enabled, created_at) VALUES (?, ?, 1, ?)",
                    (rtype, rval, now_iso()),
                )
            for ext in [".pdf", ".doc", ".docx", ".txt", ".csv", ".ppt", ".pptx", ".xls", ".xlsx", ".zip", ".py", ".sql"]:
                self.conn.execute(
                    "INSERT OR IGNORE INTO allowed_extensions(file_extension, enabled, created_at) VALUES (?, 1, ?)",
                    (ext, now_iso()),
                )
            for ext, reason in [
                (".exe", "Executable blocked by default"),
                (".msi", "Installer blocked by default"),
                (".bat", "Script execution blocked"),
                (".cmd", "Script execution blocked"),
                (".ps1", "PowerShell scripts blocked"),
                (".scr", "Screensaver executable blocked"),
                (".jar", "Binary archive blocked"),
                (".vbs", "VB script blocked"),
                (".js", "Script execution blocked"),
                (".com", "Legacy executable blocked"),
            ]:
                self.conn.execute(
                    "INSERT OR IGNORE INTO blocked_extensions(file_extension, reason, enabled, created_at) VALUES (?, ?, 1, ?)",
                    (ext, reason, now_iso()),
                )
            for repo_domain in ["repo.campus.local", "downloads.college.local"]:
                self.conn.execute(
                    "INSERT OR IGNORE INTO internal_repo_sources(domain, enabled, created_at) VALUES (?, 1, ?)",
                    (repo_domain, now_iso()),
                )

    def log(self, level, category, message, payload=None):
        payload = payload or {}
        sid = payload.get("sid") if isinstance(payload, dict) else None
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO activity_logs(session_id, created_at, level, category, message, payload, synced, sync_attempts) VALUES (?, ?, ?, ?, ?, ?, 0, 0)",
                (sid, now_iso(), level.upper(), category.upper(), message, json.dumps(payload, ensure_ascii=False)),
            )

    def session_start(self, username, session_id, machine_id):
        ts = now_iso()
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO sessions(username, session_id, machine_id, lab_id, started_at, heartbeat_at, status, synced, sync_attempts) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', 0, 0)",
                (username, session_id, machine_id, self.lab_id, ts, ts),
            )

    def session_resume(self, session_id):
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE sessions SET status='ACTIVE', suspended_at=NULL, heartbeat_at=?, end_reason='resumed_after_power_loss', synced=0 WHERE session_id=? AND status='SUSPENDED'",
                (now_iso(), session_id),
            )

    def session_heartbeat(self, session_id):
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE sessions SET heartbeat_at=?, synced=0 WHERE session_id=? AND status='ACTIVE'",
                (now_iso(), session_id),
            )

    def session_suspend(self, session_id, reason="power_loss"):
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE sessions SET status='SUSPENDED', suspended_at=?, end_reason=?, synced=0 WHERE session_id=? AND status='ACTIVE'",
                (now_iso(), reason, session_id),
            )

    def suspend_orphan_active_sessions(self, machine_id):
        with self.lock, self.conn:
            cur = self.conn.execute(
                "UPDATE sessions SET status='SUSPENDED', suspended_at=?, end_reason='power_loss_recovery', synced=0 WHERE machine_id=? AND status='ACTIVE'",
                (now_iso(), machine_id),
            )
            return cur.rowcount

    def latest_suspended_session(self, machine_id):
        with self.lock:
            return self.conn.execute(
                "SELECT session_id, username, machine_id, started_at, suspended_at FROM sessions WHERE machine_id=? AND status='SUSPENDED' ORDER BY id DESC LIMIT 1",
                (machine_id,),
            ).fetchone()

    def terminate_expired_suspended(self, machine_id, safe_timeout_minutes=180):
        cutoff = (datetime.utcnow() - timedelta(minutes=safe_timeout_minutes)).replace(microsecond=0).isoformat() + "Z"
        with self.lock, self.conn:
            cur = self.conn.execute(
                "UPDATE sessions SET ended_at=?, end_reason='suspended_timeout', status='TERMINATED', synced=0 WHERE machine_id=? AND status='SUSPENDED' AND suspended_at IS NOT NULL AND suspended_at < ?",
                (now_iso(), machine_id, cutoff),
            )
            return cur.rowcount

    def has_active_session_for_user(self, username, exclude_session_id=None):
        with self.lock:
            if exclude_session_id:
                row = self.conn.execute(
                    "SELECT session_id FROM sessions WHERE username=? AND status='ACTIVE' AND session_id<>? ORDER BY id DESC LIMIT 1",
                    (username, exclude_session_id),
                ).fetchone()
            else:
                row = self.conn.execute(
                    "SELECT session_id FROM sessions WHERE username=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1",
                    (username,),
                ).fetchone()
        return row["session_id"] if row else None

    def remote_active_session(self, username):
        if not self.pg_dsn:
            return None
        try:
            import psycopg2
            with psycopg2.connect(self.pg_dsn, connect_timeout=2) as c:
                with c.cursor() as cur:
                    cur.execute(
                        "SELECT session_id FROM sessions WHERE username=%s AND session_status='ACTIVE' ORDER BY session_pk DESC LIMIT 1",
                        (username,),
                    )
                    row = cur.fetchone()
                    return row[0] if row else None
        except Exception:
            return None

    def session_end(self, session_id, reason):
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE sessions SET ended_at=?, end_reason=?, status='TERMINATED', synced=0 WHERE session_id=? AND status IN ('ACTIVE', 'SUSPENDED', 'VIOLATION')",
                (now_iso(), reason, session_id),
            )

    def mark_session_violation(self, session_id, reason):
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE sessions SET ended_at=?, end_reason=?, status='VIOLATION', synced=0 WHERE session_id=? AND status='ACTIVE'",
                (now_iso(), reason, session_id),
            )

    def policy_rules(self):
        with self.lock:
            rows = self.conn.execute("SELECT rule_type, rule_value FROM policy_rules WHERE enabled=1").fetchall()
        return [(r["rule_type"], r["rule_value"]) for r in rows]

    def add_rule(self, value):
        v = value.strip().lower()
        if not v:
            return False
        rtype = "suffix" if v.startswith(".") or v.startswith("*.") else "exact"
        if v.startswith("*."):
            v = "." + v[2:]
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO policy_rules(rule_type, rule_value, enabled, created_at) VALUES (?, ?, 1, ?)",
                (rtype, v, now_iso()),
            )
        return True

    def add_allowed_extension(self, ext):
        value = ext.strip().lower()
        if not value:
            return False, "Extension is required."
        if not value.startswith("."):
            value = "." + value
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO allowed_extensions(file_extension, enabled, created_at) VALUES (?, 1, ?)",
                (value, now_iso()),
            )
            self.conn.execute(
                "UPDATE blocked_extensions SET enabled=0 WHERE file_extension=?",
                (value,),
            )
        return True, f"Allowed extension added: {value}"

    def add_blocked_extension(self, ext, reason="Blocked by policy"):
        value = ext.strip().lower()
        if not value:
            return False, "Extension is required."
        if not value.startswith("."):
            value = "." + value
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO blocked_extensions(file_extension, reason, enabled, created_at) VALUES (?, ?, 1, ?)",
                (value, reason.strip() or "Blocked by policy", now_iso()),
            )
            self.conn.execute(
                "UPDATE allowed_extensions SET enabled=0 WHERE file_extension=?",
                (value,),
            )
        return True, f"Blocked extension added: {value}"

    def allowed_extensions(self):
        with self.lock:
            rows = self.conn.execute(
                "SELECT file_extension FROM allowed_extensions WHERE enabled=1 ORDER BY file_extension"
            ).fetchall()
        return {r["file_extension"].lower() for r in rows}

    def blocked_extensions(self):
        with self.lock:
            rows = self.conn.execute(
                "SELECT file_extension FROM blocked_extensions WHERE enabled=1 ORDER BY file_extension"
            ).fetchall()
        return {r["file_extension"].lower() for r in rows}

    def internal_repo_domains(self):
        with self.lock:
            rows = self.conn.execute("SELECT domain FROM internal_repo_sources WHERE enabled=1").fetchall()
        return {r["domain"].lower() for r in rows}

    def add_faculty_approval(
        self,
        source_domain,
        file_extension,
        minutes,
        subject="General",
        batch="ALL",
        created_by="faculty",
        lab_scope="*",
        pc_scope="*",
    ):
        dom = domain_of(source_domain)
        ext = file_extension.strip().lower()
        if dom == "" or ext == "":
            return False, "Domain and extension are required."
        if not ext.startswith("."):
            ext = "." + ext
        try:
            mins = int(minutes)
        except Exception:
            return False, "Approval window must be an integer."
        if mins < 1 or mins > 1440:
            return False, "Approval window must be 1 to 1440 minutes."
        expires = (datetime.utcnow() + timedelta(minutes=mins)).replace(microsecond=0).isoformat() + "Z"
        lab = (lab_scope or "*").strip().upper()
        pc = (pc_scope or "*").strip().upper()
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO faculty_approvals(source_domain, file_extension, subject, batch, lab_scope, pc_scope, expires_at, created_by, created_at, enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (dom, ext, subject, batch, lab, pc, expires, created_by, now_iso()),
            )
        return True, f"Temporary approval active until {expires}"

    def trim_expired_approvals(self):
        with self.lock, self.conn:
            self.conn.execute(
                "UPDATE faculty_approvals SET enabled=0 WHERE enabled=1 AND expires_at <= ?",
                (now_iso(),),
            )

    def active_faculty_approval(self, source_domain, file_extension, lab_id=None, pc_id=None):
        dom = domain_of(source_domain)
        ext = file_extension.strip().lower()
        if ext and not ext.startswith("."):
            ext = "." + ext
        lab = (lab_id or self.lab_id).strip().upper()
        pc = (pc_id or self.pc_id).strip().upper()
        with self.lock:
            return self.conn.execute(
                "SELECT approval_id, expires_at FROM faculty_approvals WHERE enabled=1 AND expires_at>? AND source_domain IN (?, '*') AND file_extension IN (?, '*') AND lab_scope IN (?, '*') AND pc_scope IN (?, '*') ORDER BY approval_id DESC LIMIT 1",
                (now_iso(), dom, ext, lab, pc),
            ).fetchone()

    def add_download_attempt(self, session_id, file_name, mime_type, source_url, status, decision_reason, approval_ref=""):
        ext = ""
        clean = file_name.strip().lower()
        parts = [p for p in clean.split(".") if p]
        if len(parts) >= 2:
            ext = "." + parts[-1]
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO download_attempts(session_id, file_name, file_extension, source_domain, mime_type, status, decision_reason, approval_ref, attempt_time, synced, sync_attempts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)",
                (
                    session_id,
                    file_name.strip(),
                    ext,
                    domain_of(source_url),
                    (mime_type or "").strip().lower(),
                    status.upper(),
                    decision_reason,
                    approval_ref,
                    now_iso(),
                ),
            )

    def add_violation(self, session_id, violation_type, resource, description, severity="HIGH"):
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO violations(session_id, violation_type, resource, description, severity, detected_at, synced, sync_attempts) VALUES (?, ?, ?, ?, ?, ?, 0, 0)",
                (session_id, violation_type.upper(), resource, description, severity.upper(), now_iso()),
            )

    def recent_logs(self, limit=120):
        with self.lock:
            return self.conn.execute(
                "SELECT created_at, level, category, message FROM activity_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def recent_sessions(self, limit=12):
        with self.lock:
            return self.conn.execute(
                "SELECT username, started_at, ended_at, status, end_reason FROM sessions ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def all_sessions(self, limit=500):
        with self.lock:
            return self.conn.execute(
                "SELECT username, machine_id, lab_id, started_at, ended_at, status, end_reason FROM sessions ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def recent_violations(self, limit=200):
        with self.lock:
            return self.conn.execute(
                "SELECT session_id, violation_type, resource, severity, detected_at FROM violations ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def unsynced(self, limit=150):
        with self.lock:
            return self.conn.execute(
                "SELECT id, session_id, created_at, level, category, message, payload FROM activity_logs WHERE synced=0 ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()

    def mark_synced(self, ids):
        if not ids:
            return
        marks = ",".join(["?"] * len(ids))
        with self.lock, self.conn:
            self.conn.execute(f"UPDATE activity_logs SET synced=1, last_error=NULL WHERE id IN ({marks})", ids)

    def mark_sync_error(self, ids, err):
        if not ids:
            return
        marks = ",".join(["?"] * len(ids))
        with self.lock, self.conn:
            self.conn.execute(
                f"UPDATE activity_logs SET sync_attempts=sync_attempts+1, last_error=? WHERE id IN ({marks})",
                [err[:180]] + ids,
            )

    def _unsynced_rows(self, table_name, limit):
        with self.lock:
            return self.conn.execute(
                f"SELECT * FROM {table_name} WHERE synced=0 ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()

    def _mark_table_synced(self, table_name, ids):
        if not ids:
            return
        marks = ",".join(["?"] * len(ids))
        with self.lock, self.conn:
            self.conn.execute(f"UPDATE {table_name} SET synced=1, last_error=NULL WHERE id IN ({marks})", ids)

    def _mark_table_sync_error(self, table_name, ids, err):
        if not ids:
            return
        marks = ",".join(["?"] * len(ids))
        with self.lock, self.conn:
            self.conn.execute(
                f"UPDATE {table_name} SET sync_attempts=sync_attempts+1, last_error=? WHERE id IN ({marks})",
                [err[:180]] + ids,
            )

    def _record_sync_log(self, table_name, record_id, sync_status, details=""):
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO sync_logs(table_name, record_id, sync_time, sync_status, details) VALUES (?, ?, ?, ?, ?)",
                (table_name, record_id, now_iso(), sync_status, (details or "")[:240]),
            )

    def sync_to_postgres(self, batch=150):
        tables = ("sessions", "activity_logs", "download_attempts", "violations")
        pending = {t: self._unsynced_rows(t, batch) for t in tables}
        if not any(pending.values()):
            return 0, "No pending runtime records"
        if not self.pg_dsn:
            return 0, "PostgreSQL DSN not configured"
        try:
            import psycopg2
        except Exception:
            return 0, "psycopg2 not installed"
        try:
            with psycopg2.connect(self.pg_dsn, connect_timeout=4) as c:
                with c.cursor() as cur:
                    cur.execute(
                        "CREATE TABLE IF NOT EXISTS sessions (session_pk BIGSERIAL PRIMARY KEY, source_pc TEXT NOT NULL, source_id BIGINT NOT NULL, session_id TEXT NOT NULL, username TEXT NOT NULL, pc_id TEXT NOT NULL, lab_id TEXT NOT NULL, login_time TEXT NOT NULL, heartbeat_at TEXT NOT NULL, logout_time TEXT, session_status TEXT NOT NULL, termination_reason TEXT, suspended_at TEXT, UNIQUE(source_pc, source_id))"
                    )
                    cur.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS lab_id TEXT")
                    cur.execute(
                        "CREATE TABLE IF NOT EXISTS activity_logs (log_pk BIGSERIAL PRIMARY KEY, source_pc TEXT NOT NULL, source_id BIGINT NOT NULL, session_id TEXT, created_at TEXT NOT NULL, level TEXT NOT NULL, category TEXT NOT NULL, message TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(source_pc, source_id))"
                    )
                    cur.execute(
                        "CREATE TABLE IF NOT EXISTS download_attempts (download_pk BIGSERIAL PRIMARY KEY, source_pc TEXT NOT NULL, source_id BIGINT NOT NULL, session_id TEXT, file_name TEXT NOT NULL, file_extension TEXT NOT NULL, source_domain TEXT NOT NULL, mime_type TEXT, status TEXT NOT NULL, decision_reason TEXT NOT NULL, approval_ref TEXT, attempt_time TEXT NOT NULL, UNIQUE(source_pc, source_id))"
                    )
                    cur.execute(
                        "CREATE TABLE IF NOT EXISTS violations (violation_pk BIGSERIAL PRIMARY KEY, source_pc TEXT NOT NULL, source_id BIGINT NOT NULL, session_id TEXT, violation_type TEXT NOT NULL, resource TEXT NOT NULL, description TEXT NOT NULL, severity TEXT NOT NULL, detected_at TEXT NOT NULL, UNIQUE(source_pc, source_id))"
                    )
                    cur.execute(
                        "CREATE TABLE IF NOT EXISTS alerts (alert_id BIGSERIAL PRIMARY KEY, session_id TEXT, message TEXT NOT NULL, severity TEXT NOT NULL, alert_time TEXT NOT NULL, viewed BOOLEAN NOT NULL DEFAULT FALSE)"
                    )

                    done = []
                    for r in pending["sessions"]:
                        cur.execute(
                            "INSERT INTO sessions(source_pc, source_id, session_id, username, pc_id, lab_id, login_time, heartbeat_at, logout_time, session_status, termination_reason, suspended_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (source_pc, source_id) DO UPDATE SET heartbeat_at=EXCLUDED.heartbeat_at, logout_time=EXCLUDED.logout_time, session_status=EXCLUDED.session_status, termination_reason=EXCLUDED.termination_reason, suspended_at=EXCLUDED.suspended_at",
                            (self.pc_id, r["id"], r["session_id"], r["username"], r["machine_id"], r["lab_id"], r["started_at"], r["heartbeat_at"], r["ended_at"], r["status"], r["end_reason"], r["suspended_at"]),
                        )
                        done.append(r["id"])
                    self._mark_table_synced("sessions", done)
                    if done:
                        self._record_sync_log("sessions", done[-1], "success", f"synced={len(done)}")

                    done = []
                    for r in pending["activity_logs"]:
                        cur.execute(
                            "INSERT INTO activity_logs(source_pc, source_id, session_id, created_at, level, category, message, payload) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (source_pc, source_id) DO NOTHING",
                            (self.pc_id, r["id"], r["session_id"], r["created_at"], r["level"], r["category"], r["message"], r["payload"]),
                        )
                        done.append(r["id"])
                    self._mark_table_synced("activity_logs", done)
                    if done:
                        self._record_sync_log("activity_logs", done[-1], "success", f"synced={len(done)}")

                    done = []
                    for r in pending["download_attempts"]:
                        cur.execute(
                            "INSERT INTO download_attempts(source_pc, source_id, session_id, file_name, file_extension, source_domain, mime_type, status, decision_reason, approval_ref, attempt_time) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (source_pc, source_id) DO NOTHING",
                            (self.pc_id, r["id"], r["session_id"], r["file_name"], r["file_extension"], r["source_domain"], r["mime_type"], r["status"], r["decision_reason"], r["approval_ref"], r["attempt_time"]),
                        )
                        done.append(r["id"])
                    self._mark_table_synced("download_attempts", done)
                    if done:
                        self._record_sync_log("download_attempts", done[-1], "success", f"synced={len(done)}")

                    done = []
                    for r in pending["violations"]:
                        cur.execute(
                            "INSERT INTO violations(source_pc, source_id, session_id, violation_type, resource, description, severity, detected_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (source_pc, source_id) DO NOTHING",
                            (self.pc_id, r["id"], r["session_id"], r["violation_type"], r["resource"], r["description"], r["severity"], r["detected_at"]),
                        )
                        cur.execute(
                            "INSERT INTO alerts(session_id, message, severity, alert_time, viewed) VALUES (%s,%s,%s,%s,FALSE)",
                            (r["session_id"], f"{r['violation_type']} violation on {r['resource']}", "high" if (r["severity"] or "").upper() == "HIGH" else "medium", r["detected_at"]),
                        )
                        done.append(r["id"])
                    self._mark_table_synced("violations", done)
                    if done:
                        self._record_sync_log("violations", done[-1], "success", f"synced={len(done)}")

            synced_total = sum(len(pending[t]) for t in tables)
            return synced_total, f"Synced {synced_total} runtime records"
        except Exception as ex:
            err = str(ex)
            for table_name in tables:
                ids = [r["id"] for r in pending[table_name]]
                self._mark_table_sync_error(table_name, ids, err)
                if ids:
                    self._record_sync_log(table_name, ids[-1], "failed", err)
            return 0, f"Sync failed: {ex}"

    def close(self):
        with self.lock:
            self.conn.close()
