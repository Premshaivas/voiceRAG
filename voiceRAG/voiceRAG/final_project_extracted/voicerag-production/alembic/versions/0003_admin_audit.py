from alembic import op
import sqlalchemy as sa

revision = "0003_admin_audit"
down_revision = "0002_evaluations"
branch_labels = None
depends_on = None


def upgrade():
    userrole_enum = sa.Enum("user", "admin", name="userrole")
    userrole_enum.create(op.get_bind(), checkfirst=True)
    op.add_column("users", sa.Column("role", userrole_enum, nullable=True))
    op.execute("UPDATE users SET role = 'user' WHERE role IS NULL")
    op.alter_column("users", "role", nullable=False, server_default="user")
    op.create_index("ix_users_role", "users", ["role"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=150), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade():
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_column("users", "role")
    sa.Enum("user", "admin", name="userrole").drop(op.get_bind(), checkfirst=True)
