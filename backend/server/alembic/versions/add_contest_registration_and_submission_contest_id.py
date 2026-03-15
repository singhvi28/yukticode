"""add contest_registrations and submission.contest_id

Revision ID: add_contest_reg
Revises:
Create Date: 2025-03-15

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_contest_reg"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("contest_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_submissions_contest_id",
        "submissions",
        "contests",
        ["contest_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "contest_registrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("contest_id", sa.Integer(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["contest_id"], ["contests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_contest_registrations_id"), "contest_registrations", ["id"], unique=False)


def downgrade() -> None:
    op.drop_table("contest_registrations")
    op.drop_constraint("fk_submissions_contest_id", "submissions", type_="foreignkey")
    op.drop_column("submissions", "contest_id")
