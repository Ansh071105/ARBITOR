def compact_pc_id(value):
    text = (value or "").strip().upper()
    if not text:
        return "PC-LOCAL"
    text = text.split(".")[0]
    if len(text) <= 12:
        return text
    return text[:8] + "-" + text[-3:]
