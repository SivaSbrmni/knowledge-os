from typing import Protocol

from knowledge_os.domain.mesh import MeshContext


class MeshNode(Protocol):
    node_id: str

    async def run(self, ctx: MeshContext) -> MeshContext: ...
