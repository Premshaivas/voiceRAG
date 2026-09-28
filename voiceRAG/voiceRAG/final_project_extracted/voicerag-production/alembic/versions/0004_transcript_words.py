from alembic import op
import sqlalchemy as sa

revision = "0004_transcript_words"
down_revision = "0003_admin_audit"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("transcripts", sa.Column("words_json", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("transcripts", "words_json")
