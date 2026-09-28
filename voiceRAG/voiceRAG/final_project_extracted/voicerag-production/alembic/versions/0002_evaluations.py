from alembic import op
import sqlalchemy as sa

revision = "0002_evaluations"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("evaluation_datasets", sa.Column("id", sa.String(36), primary_key=True), sa.Column("owner_id", sa.String(36)), sa.Column("name", sa.String(255), nullable=False), sa.Column("description", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"))
    op.create_index("ix_evaluation_datasets_owner_id", "evaluation_datasets", ["owner_id"])
    op.create_table("evaluation_cases", sa.Column("id", sa.String(36), primary_key=True), sa.Column("dataset_id", sa.String(36), nullable=False), sa.Column("question", sa.Text(), nullable=False), sa.Column("expected_answer", sa.Text(), nullable=False), sa.Column("expected_document_ids_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.ForeignKeyConstraint(["dataset_id"], ["evaluation_datasets.id"], ondelete="CASCADE"))
    op.create_index("ix_evaluation_cases_dataset_id", "evaluation_cases", ["dataset_id"])
    op.create_table("evaluation_runs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("dataset_id", sa.String(36), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("case_count", sa.Integer(), nullable=False), sa.Column("metrics_json", sa.Text(), nullable=False), sa.Column("error", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.ForeignKeyConstraint(["dataset_id"], ["evaluation_datasets.id"], ondelete="CASCADE"))
    op.create_index("ix_evaluation_runs_dataset_id", "evaluation_runs", ["dataset_id"])
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"])
    op.create_table("evaluation_results", sa.Column("id", sa.String(36), primary_key=True), sa.Column("run_id", sa.String(36), nullable=False), sa.Column("case_id", sa.String(36), nullable=False), sa.Column("answer", sa.Text(), nullable=False), sa.Column("retrieved_document_ids_json", sa.Text(), nullable=False), sa.Column("citations_json", sa.Text(), nullable=False), sa.Column("retrieval_recall", sa.Float(), nullable=False), sa.Column("citation_precision", sa.Float(), nullable=False), sa.Column("citation_recall", sa.Float(), nullable=False), sa.Column("answer_f1", sa.Float(), nullable=False), sa.Column("latency_ms", sa.Float(), nullable=False), sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["case_id"], ["evaluation_cases.id"]))
    op.create_index("ix_evaluation_results_run_id", "evaluation_results", ["run_id"])
    op.create_index("ix_evaluation_results_case_id", "evaluation_results", ["case_id"])


def downgrade():
    op.drop_table("evaluation_results")
    op.drop_table("evaluation_runs")
    op.drop_table("evaluation_cases")
    op.drop_table("evaluation_datasets")
