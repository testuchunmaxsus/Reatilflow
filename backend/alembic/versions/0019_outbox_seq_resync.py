"""outbox_event_seq resync — duplicate seq bug fix.

MUAMMO: `OutboxEvent.seq` modelda HAM Postgres `Sequence`, HAM Python
`default=_next_seq` (counter) bilan e'lon qilingan edi. Python default Sequence'ni
BEKOR qilib, Postgres'da ham har-jarayon xotira counter'i ishlatilgan →
`outbox_event_seq` sequence jadval max(seq)'dan orqada qoladi → yangi nextval
mavjud qator bilan to'qnashadi (`duplicate key value violates unique constraint
"ix_outbox_event_seq"`). Bu har qanday outbox-yozuvchi amalni (assign-agent,
buyurtma, holat o'zgarishi) buzadi.

YECHIM: model `_seq_default` orqali Postgres'da `nextval('outbox_event_seq')`
ishlatadigan qilindi. Bu migratsiya sequence'ni mavjud max(seq)'ga sinxronlaydi —
shunda keyingi nextval to'qnashmaydi.

SQLite: no-op (sequence yo'q).

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Sequence'ni mavjud max(seq)'ga surish. is_called=false → keyingi nextval
        # aynan shu qiymatni qaytaradi; shuning uchun max+1 beramiz (toza start).
        # Jadval bo'sh bo'lsa → 1 dan boshlanadi.
        bind.execute(
            sa.text(
                "SELECT setval('outbox_event_seq', "
                "COALESCE((SELECT MAX(seq) FROM outbox_event), 0) + 1, false)"
            )
        )


def downgrade() -> None:
    # Sequence resync — orqaga qaytarish shart emas (no-op).
    pass
