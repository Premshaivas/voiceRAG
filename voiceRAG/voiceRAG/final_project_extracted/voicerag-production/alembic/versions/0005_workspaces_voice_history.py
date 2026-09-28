from alembic import op
import sqlalchemy as sa

revision = "0005_workspaces_voice_history"
down_revision = "0004_transcript_words"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("workspaces", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(200), nullable=False), sa.Column("created_by", sa.String(36), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_workspaces_created_by", "workspaces", ["created_by"])
    op.create_table("workspace_members", sa.Column("id", sa.String(36), primary_key=True), sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("role", sa.String(32), nullable=False, server_default="member"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_workspace_members_workspace_id", "workspace_members", ["workspace_id"])
    op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])
    op.create_table("voice_conversations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("title", sa.String(300), nullable=False, server_default="Voice conversation"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_voice_conversations_owner_id", "voice_conversations", ["owner_id"])
    op.create_table("voice_messages", sa.Column("id", sa.String(36), primary_key=True), sa.Column("conversation_id", sa.String(36), sa.ForeignKey("voice_conversations.id", ondelete="CASCADE"), nullable=False), sa.Column("role", sa.String(32), nullable=False), sa.Column("text", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_voice_messages_conversation_id", "voice_messages", ["conversation_id"])
    op.create_index("ix_voice_messages_created_at", "voice_messages", ["created_at"])


def downgrade():
    op.drop_table("voice_messages")
    op.drop_table("voice_conversations")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
