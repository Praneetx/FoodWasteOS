from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_restaurant
from app.core.security import CurrentUser
from app.db.models import Restaurant, User
from app.db.session import get_db
from app.schemas.profile import MeOut, RestaurantOut, UserOut

router = APIRouter(tags=["profile"])


@router.get("/me", response_model=MeOut)
def me(
    user: CurrentUser = Depends(get_current_user),
    restaurant: Restaurant = Depends(get_restaurant),
    db: Session = Depends(get_db),
) -> MeOut:
    profile = db.get(User, user.id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
    return MeOut(
        user=UserOut.model_validate(profile),
        restaurant=RestaurantOut.model_validate(restaurant),
    )
