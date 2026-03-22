from arbitor_app.core.config import domain_of


class DownloadControlEngine:
    def __init__(self, policy, db):
        self.policy = policy
        self.db = db
        self.high_risk_ext = {".exe", ".msi", ".zip", ".rar", ".7z", ".iso"}
        self.doc_ext = {".pdf", ".doc", ".docx", ".txt", ".csv", ".ppt", ".pptx", ".xls", ".xlsx"}
        self.exe_mime = {"application/x-msdownload", "application/x-dosexec", "application/x-executable", "application/x-msdos-program"}

    def evaluate(self, file_name, mime_type, source_url):
        fname = file_name.strip().lower()
        if not fname:
            return False, "File name is required", ""

        parts = [p for p in fname.split(".") if p]
        if len(parts) < 2:
            return False, "Missing file extension", ""

        ext = "." + parts[-1]
        prev = "." + parts[-2] if len(parts) >= 3 else ""
        src = domain_of(source_url)
        if not src:
            return False, "Invalid source URL", ""

        if prev and prev in self.doc_ext and ext in self.db.blocked_extensions():
            return False, "Double extension attack detected", ""

        approval = self.db.active_faculty_approval(src, ext, lab_id=self.db.lab_id, pc_id=self.db.pc_id)
        approval_ref = f"FAC-{approval['approval_id']}" if approval else ""
        internal_repo = self.policy.is_internal_repo(src)
        domain_allowed = self.policy.whitelisted(src) or internal_repo or bool(approval)

        if not domain_allowed:
            return False, "Source repository is not approved", ""

        mime = mime_type.strip().lower()
        blocked = self.db.blocked_extensions()
        allowed = self.db.allowed_extensions()

        if ext in blocked and not (internal_repo or approval):
            return False, f"Blocked extension detected: {ext}", ""
        if ext not in allowed and not (internal_repo or approval):
            return False, f"Extension is not allowed: {ext}", ""
        if mime in self.exe_mime and not (internal_repo or approval):
            return False, "Executable MIME blocked", ""
        if ext in self.doc_ext and ("x-msdownload" in mime or "executable" in mime):
            return False, "Renamed file detected by MIME mismatch", ""
        if ext in self.high_risk_ext and not (internal_repo or approval):
            return False, f"High-risk extension requires faculty/internal approval: {ext}", ""

        if internal_repo and not approval_ref:
            approval_ref = "INTERNAL_REPO"
        if not approval_ref:
            approval_ref = "WHITELIST_RULE"
        return True, "Download allowed", approval_ref
