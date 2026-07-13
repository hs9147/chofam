"""payment 모듈 API — 토스 결제 승인·취소·조회. 여러 서비스가 x-api-key로 호출한다."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import ApiKey, Payment, PaymentStatus
from ..security import require_admin, require_api_key
from ..services import toss
from ..services.toss import TossError

router = APIRouter(prefix="/payments", tags=["payments"])


class ConfirmBody(BaseModel):
    payment_key: str = Field(alias="paymentKey")
    order_id: str = Field(alias="orderId")
    amount: int = Field(gt=0)

    model_config = {"populate_by_name": True}


class CancelBody(BaseModel):
    reason: str = "고객 요청"


def _payment_out(p: Payment) -> dict:
    return {
        "id": p.id,
        "order_id": p.order_id,
        "payment_key": p.payment_key,
        "amount": p.amount,
        "status": p.status.value,
        "method": p.method,
        "source": p.source,
        "fail_reason": p.fail_reason,
        "created_at": p.created_at.isoformat(),
    }


@router.post("/confirm")
async def confirm_payment(
    body: ConfirmBody,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(require_api_key),
):
    existing = db.execute(
        select(Payment).where(Payment.order_id == body.order_id)
    ).scalar_one_or_none()
    if existing is not None:
        # 같은 결제의 재시도(멱등)만 허용, 다른 내용이면 충돌
        if (
            existing.status == PaymentStatus.confirmed
            and existing.payment_key == body.payment_key
            and existing.amount == body.amount
        ):
            return _payment_out(existing)
        raise HTTPException(status_code=409, detail="orderId already used")

    record = Payment(
        order_id=body.order_id,
        payment_key=body.payment_key,
        amount=body.amount,
        source=key.name,
        status=PaymentStatus.ready,
    )
    db.add(record)
    db.commit()

    try:
        data = await asyncio.to_thread(toss.confirm, body.payment_key, body.order_id, body.amount)
    except TossError as e:
        record.status = PaymentStatus.failed
        record.fail_reason = f"{e.code}: {e}"
        db.commit()
        audit.record(db, key.name, "payment.failed", body.order_id, {"code": e.code})
        raise HTTPException(status_code=e.status, detail=f"{e.code}: {e}")

    record.status = PaymentStatus.confirmed
    record.method = data.get("method")
    db.commit()
    audit.record(db, key.name, "payment.confirm", body.order_id, {"amount": body.amount})
    return _payment_out(record)


@router.post("/{payment_key}/cancel")
async def cancel_payment(
    payment_key: str,
    body: CancelBody,
    db: Session = Depends(get_db),
    admin: ApiKey = Depends(require_admin),
):
    record = db.execute(
        select(Payment).where(Payment.payment_key == payment_key)
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="payment not found")
    if record.status != PaymentStatus.confirmed:
        raise HTTPException(status_code=409, detail=f"payment is {record.status.value}")

    try:
        await asyncio.to_thread(toss.cancel, payment_key, body.reason)
    except TossError as e:
        raise HTTPException(status_code=e.status, detail=f"{e.code}: {e}")

    record.status = PaymentStatus.canceled
    db.commit()
    audit.record(db, admin.name, "payment.cancel", record.order_id, {"reason": body.reason})
    return _payment_out(record)


@router.get("")
def list_payments(
    status: PaymentStatus | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_admin),
):
    q = select(Payment).order_by(Payment.id.desc()).limit(min(limit, 200))
    if status is not None:
        q = q.where(Payment.status == status)
    return [_payment_out(p) for p in db.execute(q).scalars()]
