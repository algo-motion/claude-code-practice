from dataclasses import dataclass, field


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str
    groups: tuple = field(default_factory=tuple)
    is_admin: bool = False

    @property
    def initials(self):
        parts = self.name.split()
        return (parts[0][0] + parts[-1][0]).upper() if len(parts) > 1 else self.name[:2].upper()

    def to_json(self):
        return {"id": self.id, "email": self.email, "name": self.name, "initials": self.initials,
                "groups": list(self.groups), "role": "admin" if self.is_admin else "staff"}


class DocStatus:
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    INGESTING = "INGESTING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    DELETED = "DELETED"


def doc_to_json(d):
    """Dạng tài liệu trả về cho UI."""
    updated = d.get("updated_at", "")[:10]
    y, m, day = (updated.split("-") + ["", "", ""])[:3]
    return {
        "id": d["id"], "title": d["title"], "type": d.get("type", "PDF"), "dept": d.get("dept", "—"),
        "groups": d.get("groups", []), "group": ", ".join(d.get("groups", [])),
        "pages": d.get("pages", 0), "size": d.get("size", ""), "owner": d.get("owner", ""),
        "status": d.get("status"), "job_id": d.get("job_id"),
        "updated": f"{day}/{m}/{y}" if y else "",
        "summary": d.get("summary") or [],
    }
