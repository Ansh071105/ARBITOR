from threading import Lock

from arbitor_app.core.config import BLOCKED_KEYWORDS, domain_of


class PolicyEngine:
    def __init__(self, db):
        self.db = db
        self.lock = Lock()
        self.exact = set()
        self.suffix = set()
        self.internal_repo = set()
        self.reload()

    def reload(self):
        with self.lock:
            self.exact.clear()
            self.suffix.clear()
            self.internal_repo = self.db.internal_repo_domains()
            for rtype, value in self.db.policy_rules():
                v = value.strip().lower()
                if rtype == "exact":
                    self.exact.add(v)
                else:
                    if not v.startswith("."):
                        v = "." + v
                    self.suffix.add(v)

    def add_rule(self, value):
        ok = self.db.add_rule(value)
        self.reload()
        return ok

    def whitelisted(self, domain):
        d = domain.strip().lower()
        if not d:
            return False
        if d in self.exact:
            return True
        for suf in self.suffix:
            if d.endswith(suf):
                return True
        return False

    def is_internal_repo(self, domain):
        return domain.strip().lower() in self.internal_repo

    def evaluate_url(self, url):
        d = domain_of(url)
        if not d:
            return False, "Invalid URL", ""
        if any(b in d for b in BLOCKED_KEYWORDS):
            return False, "Domain is blocked by policy", d
        if self.whitelisted(d) or self.is_internal_repo(d):
            return True, "Allowed by whitelist", d
        return False, "Domain not in whitelist", d
