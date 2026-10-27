"""Error and finding types shared by the procurement planner."""

from __future__ import annotations


class InputError(Exception):
    """A structural or semantic input error that makes planning impossible."""

    def __init__(self, code, message, where=None):
        self.code = code
        self.message = message
        self.where = where
        super().__init__("%s: %s" % (where or code, message))

    def as_finding(self):
        return {
            "level": "blocking",
            "code": self.code,
            "where": self.where,
            "message": self.message,
        }


class Findings:
    """Ordered validation findings with deterministic de-duplication."""

    def __init__(self):
        self._items = []
        self._seen = set()

    def add(self, level, code, where, message):
        if level not in ("blocking", "warning"):
            raise AssertionError("invalid finding level: %r" % (level,))
        key = (level, code, where or "", message)
        if key in self._seen:
            return
        self._seen.add(key)
        self._items.append({
            "level": level,
            "code": code,
            "where": where,
            "message": message,
        })

    def blocking(self, code, where, message):
        self.add("blocking", code, where, message)

    def warning(self, code, where, message):
        self.add("warning", code, where, message)

    def extend(self, items):
        for item in items:
            self.add(item["level"], item["code"], item.get("where"),
                     item["message"])

    def sorted(self):
        order = {"blocking": 0, "warning": 1}
        return sorted(self._items,
                      key=lambda item: (order[item["level"]],
                                        item.get("where") or "",
                                        item["code"], item["message"]))

    @property
    def blocking_count(self):
        return sum(1 for item in self._items if item["level"] == "blocking")

    @property
    def warning_count(self):
        return sum(1 for item in self._items if item["level"] == "warning")

    def __len__(self):
        return len(self._items)
