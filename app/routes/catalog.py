from fastapi import APIRouter

from app.config import get_settings
from app.errors import DomainProblem
from app.schemas.catalog import ProductPublic
from app.services.catalog import PRODUCTS


router = APIRouter(prefix="/v1/catalog", tags=["catalog"])


@router.get("/products", response_model=list[ProductPublic])
def list_products() -> list[ProductPublic]:
    demo = get_settings().demo_offer_mapping_enabled
    return [item.to_public(demo) for item in PRODUCTS.values()]


@router.get("/products/{slug}", response_model=ProductPublic)
def get_product(slug: str) -> ProductPublic:
    product = PRODUCTS.get(slug)
    if product is None:
        raise DomainProblem(404, "PRODUCT_NOT_FOUND", "المنتج غير موجود", "تعذر العثور على المنتج المطلوب.")
    return product.to_public(get_settings().demo_offer_mapping_enabled)
