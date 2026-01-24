from __future__ import annotations

from sqlalchemy.orm import Session
from apps.api.models import Product
from apps.api.state_service import change_product_state


def upload_media(*, db: Session, product: Product, actor: str):
    return change_product_state(
        db=db,
        product=product,
        transition="upload_media",
        actor=actor,
    )


def start_ai(*, db: Session, product: Product, actor: str):
    return change_product_state(
        db=db,
        product=product,
        transition="start_ai",
        actor=actor,
    )


def confirm_product_data(*, db: Session, product: Product, actor: str):
    return change_product_state(
        db=db,
        product=product,
        transition="confirm",
        actor=actor,
    )


def publish_product(*, db: Session, product: Product, actor: str):
    return change_product_state(
        db=db,
        product=product,
        transition="publish",
        actor=actor,
    )


def retry_ai(*, db: Session, product: Product, actor: str):
    return change_product_state(
        db=db,
        product=product,
        transition="retry_ai",
        actor=actor,
    )