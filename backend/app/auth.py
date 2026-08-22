import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """Authenticated actor and the workspaces it may access."""

    actor: str
    workspace_ids: frozenset[uuid.UUID]

    def can_access(self, workspace_id: uuid.UUID) -> bool:
        return workspace_id in self.workspace_ids
