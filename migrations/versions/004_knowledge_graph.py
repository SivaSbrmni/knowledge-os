"""Phase 2 knowledge graph, ingestion runs, derived artifacts."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("knowledge_assets", sa.Column("layer", sa.String(32), nullable=False, server_default="tenant"))
    op.add_column("knowledge_assets", sa.Column("ingest_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("knowledge_assets", sa.Column("pipeline_version", sa.String(16), nullable=False, server_default="1.0"))
    op.add_column("knowledge_assets", sa.Column("superseded_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_knowledge_assets_content_hash", "knowledge_assets", ["workspace_id", "content_hash"])

    op.add_column("knowledge_chunks", sa.Column("layer", sa.String(32), nullable=False, server_default="tenant"))
    op.add_column("chunk_embeddings", sa.Column("layer", sa.String(32), nullable=False, server_default="tenant"))

    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("pipeline_version", sa.String(16), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_assets.id"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "content_hash", "pipeline_version", name="uq_ingestion_idempotency"),
    )

    op.create_table(
        "knowledge_graph_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("edge_type", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_graph_edges_workspace", "knowledge_graph_edges", ["workspace_id"])
    op.create_index("ix_graph_edges_source", "knowledge_graph_edges", ["source_id", "edge_type"])

    op.create_table(
        "derived_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("source_asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_assets.id"), nullable=False),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("layer", sa.String(32), nullable=False, server_default="tenant"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_derived_artifacts_source", "derived_artifacts", ["source_asset_id"])


def downgrade() -> None:
    op.drop_table("derived_artifacts")
    op.drop_table("knowledge_graph_edges")
    op.drop_table("ingestion_runs")
    op.drop_column("chunk_embeddings", "layer")
    op.drop_column("knowledge_chunks", "layer")
    op.drop_index("ix_knowledge_assets_content_hash", "knowledge_assets")
    op.drop_column("knowledge_assets", "superseded_by")
    op.drop_column("knowledge_assets", "pipeline_version")
    op.drop_column("knowledge_assets", "ingest_run_id")
    op.drop_column("knowledge_assets", "layer")
