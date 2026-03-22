import json
import re
import time
import uuid
from pathlib import Path
from threading import Lock

from arbitor_app.core.config import now_iso


class SessionAuthEngine:
    def __init__(self, db, credentials, cache_path="session_cache.json"):
        self.db = db
        self.credentials = dict(credentials)
        self.cache_path = Path(cache_path)
        self.lock = Lock()
        self.machine_id = self.db.pc_id
        self.max_attempts = 3
        self.cooldown_secs = 30
        self.conflict_cooldown_secs = 180
        self.active_user = {}
        self.user_by_sid = {}
        self.user_binding = {}
        self.failed = {}
        self.conflict_block = {}
        self._load_cache()
        self.db.suspend_orphan_active_sessions(self.machine_id)
        self.db.terminate_expired_suspended(self.machine_id, safe_timeout_minutes=180)

    def _load_cache(self):
        if not self.cache_path.exists():
            return
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            self.active_user = data.get("active_user", {})
            self.user_binding = data.get("user_binding", {})
            self.user_by_sid = {}
            now = time.time()
            stale = []
            for user, s in self.active_user.items():
                hb = s.get("hb_epoch", now)
                if now - hb > 7200:
                    stale.append(user)
                    continue
                sid = s.get("sid")
                if sid:
                    self.user_by_sid[sid] = user
            for u in stale:
                self.active_user.pop(u, None)
            self._save_cache()
        except Exception:
            self.active_user = {}
            self.user_binding = {}
            self.user_by_sid = {}

    def _save_cache(self):
        self.cache_path.write_text(
            json.dumps({"active_user": self.active_user, "user_binding": self.user_binding, "saved_at": now_iso()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _normalize_machine_id(self, value):
        text = (value or "").strip().upper()
        if not text:
            return ""
        text = text.split(".")[0]
        legacy = re.match(r"^(.*)-(\d{6,})$", text)
        if legacy:
            return legacy.group(1)
        return text

    def _same_machine(self, bound_value):
        current = self._normalize_machine_id(self.machine_id)
        bound = self._normalize_machine_id(bound_value)
        return bool(current and bound and current == bound)

    def login(self, username, password):
        user = username.strip()
        if not user:
            return False, "Please enter ID.", None
        now = time.time()
        self.db.trim_expired_approvals()
        self.db.terminate_expired_suspended(self.machine_id, safe_timeout_minutes=180)
        with self.lock:
            conflict_until = self.conflict_block.get(user, 0)
            if conflict_until > now:
                return False, f"Credential temporarily blocked due to session conflict. Retry in {int(conflict_until-now)}s.", None

            f = self.failed.get(user)
            if f and f.get("until", 0) > now:
                return False, f"Too many attempts. Try again in {int(f['until']-now)}s.", None

            expected = self.credentials.get(user)
            if expected is None or expected != password:
                s = self.failed.setdefault(user, {"count": 0, "until": 0})
                s["count"] += 1
                if s["count"] >= self.max_attempts:
                    s["count"] = 0
                    s["until"] = now + self.cooldown_secs
                    self.db.log("WARNING", "AUTH", "Login cooldown triggered", {"username": user})
                    return False, f"Invalid credentials. Cooldown {self.cooldown_secs}s applied.", None
                self.db.log("WARNING", "AUTH", "Invalid credentials", {"username": user})
                return False, "Invalid ID or password.", None

            suspended = self.db.latest_suspended_session(self.machine_id)
            if suspended:
                suspended_user = suspended["username"]
                if suspended_user != user:
                    self.conflict_block[user] = now + self.conflict_cooldown_secs
                    return False, f"PC is reserved for suspended session: {suspended_user}. Contact admin or wait for timeout.", None
                sid = suspended["session_id"]
                data = {
                    "sid": sid,
                    "username": user,
                    "machine_id": self.machine_id,
                    "started": suspended["started_at"],
                    "hb": now_iso(),
                    "hb_epoch": now,
                }
                self.active_user[user] = data
                self.user_by_sid[sid] = user
                self.user_binding[user] = self.machine_id
                self.failed.pop(user, None)
                self.conflict_block.pop(user, None)
                self._save_cache()
                self.db.session_resume(sid)
                self.db.log("INFO", "AUTH", "Suspended session resumed", {"username": user, "sid": sid})
                return True, "Resumed suspended session", data

            bound = self.user_binding.get(user)
            if bound and bound != self.machine_id:
                if self._same_machine(bound):
                    self.user_binding[user] = self.machine_id
                    self._save_cache()
                    self.db.log("INFO", "AUTH", "Machine binding normalized", {"username": user, "from": bound, "to": self.machine_id})
                else:
                    self.db.log("CRITICAL", "AUTH", "Machine binding violation", {"username": user, "machine": self.machine_id, "bound": bound})
                    return False, "This ID is bound to another PC.", None

            active_sid = self.db.has_active_session_for_user(user)
            remote_active_sid = self.db.remote_active_session(user)
            if active_sid or remote_active_sid:
                self.conflict_block[user] = now + self.conflict_cooldown_secs
                self.db.log("WARNING", "AUTH", "Credential conflict", {"username": user, "active_sid": active_sid})
                return False, "An active session already exists for this ID.", None

            if user in self.active_user:
                self.conflict_block[user] = now + self.conflict_cooldown_secs
                self.db.log("WARNING", "AUTH", "Credential conflict", {"username": user})
                return False, "An active session already exists for this ID.", None

            sid = str(uuid.uuid4())
            data = {
                "sid": sid,
                "username": user,
                "machine_id": self.machine_id,
                "started": now_iso(),
                "hb": now_iso(),
                "hb_epoch": now,
            }
            self.active_user[user] = data
            self.user_by_sid[sid] = user
            self.user_binding[user] = self.machine_id
            self.failed.pop(user, None)
            self.conflict_block.pop(user, None)
            self._save_cache()

        self.db.session_start(user, sid, self.machine_id)
        self.db.log("INFO", "AUTH", "Login successful", {"username": user, "sid": sid})
        return True, "OK", data

    def heartbeat(self, sid):
        with self.lock:
            user = self.user_by_sid.get(sid)
            if not user:
                return False
            s = self.active_user.get(user)
            if not s:
                return False
            s["hb"] = now_iso()
            s["hb_epoch"] = time.time()
        self.db.session_heartbeat(sid)
        return True

    def active_users(self):
        with self.lock:
            return list(self.active_user.keys())

    def end(self, sid, reason="logout"):
        with self.lock:
            user = self.user_by_sid.pop(sid, None)
            if not user:
                return
            self.active_user.pop(user, None)
            self._save_cache()
        self.db.session_end(sid, reason)
        self.db.log("INFO", "AUTH", "Session ended", {"sid": sid, "reason": reason})
        self.db.sync_to_postgres(batch=500)

    def suspend(self, sid, reason="power_loss"):
        with self.lock:
            user = self.user_by_sid.get(sid)
            if user and user in self.active_user:
                self.active_user[user]["hb"] = now_iso()
                self.active_user[user]["hb_epoch"] = time.time()
            self._save_cache()
        self.db.session_suspend(sid, reason)
        self.db.log("WARNING", "AUTH", "Session suspended", {"sid": sid, "reason": reason})
