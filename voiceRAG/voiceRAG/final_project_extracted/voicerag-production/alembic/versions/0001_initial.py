from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users", sa.Column("id", sa.String(36), primary_key=True), sa.Column("email", sa.String(320), nullable=False), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table("documents", sa.Column("id", sa.String(36), primary_key=True), sa.Column("owner_id", sa.String(36)), sa.Column("title", sa.String(500), nullable=False), sa.Column("filename", sa.String(500), nullable=False), sa.Column("storage_path", sa.String(1000), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("error", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.ForeignKeyConstraint(["owner_id"], ["users.id"]))
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_table("transcripts", sa.Column("id", sa.String(36), primary_key=True), sa.Column("document_id", sa.String(36), nullable=False, unique=True), sa.Column("assemblyai_id", sa.String(255)), sa.Column("text", sa.Text(), nullable=False), sa.Column("language_code", sa.String(32)), sa.Column("speech_model", sa.String(128)), sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"))
    op.create_table("jobs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("document_id", sa.String(36)), sa.Column("kind", sa.String(100), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("error", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.ForeignKeyConstraint(["document_id"], ["documents.id"]))
    op.create_table("outbox_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("event_type", sa.String(150), nullable=False), sa.Column("aggregate_id", sa.String(36), nullable=False), sa.Column("payload", sa.Text(), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table("multipart_uploads", sa.Column("id", sa.String(36), primary_key=True), sa.Column("owner_id", sa.String(36)), sa.Column("object_key", sa.String(1000), nullable=False, unique=True), sa.Column("storage_upload_id", sa.String(255), nullable=False, unique=True), sa.Column("filename", sa.String(500), nullable=False), sa.Column("content_type", sa.String(255), nullable=False), sa.Column("size_bytes", sa.Integer(), nullable=False), sa.Column("part_size_bytes", sa.Integer(), nullable=False), sa.Column("part_count", sa.Integer(), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.ForeignKeyConstraint(["owner_id"], ["users.id"]))
    op.create_table("refresh_sessions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), nullable=False), sa.Column("family_id", sa.String(36), nullable=False), sa.Column("token_hash", sa.String(128), nullable=False, unique=True), sa.Column("csrf_hash", sa.String(128), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("used", sa.Boolean(), nullable=False), sa.Column("revoked", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"))


def downgrade():
    for table in ("refresh_sessions", "multipart_uploads", "outbox_events", "jobs", "transcripts", "documents", "users"):
        op.drop_table(table)
