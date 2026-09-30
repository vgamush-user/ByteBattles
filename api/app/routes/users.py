from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy.orm import Session

from ..utils import oauth2, password_manager
from ..schemas.user import UserResponse, UserUpdate, UserResponseUnknown, RoleUpdate
from ..database import get_db

from shared.models import User, UserType

router = APIRouter(
    prefix='/users',
    tags=["Users"]
)


@router.get('/me', status_code=status.HTTP_200_OK, response_model=UserResponse)
def get_current_user(current_user: User = Depends(oauth2.get_current_user)):
    return current_user

@router.patch('/me', status_code=status.HTTP_200_OK, response_model=UserResponse)
def update_current_user(updates: UserUpdate, current_user: User = Depends(oauth2.get_current_user), db: Session = Depends(get_db)):

    if updates.password and updates.conf_password:
        if updates.password != updates.conf_password:
            raise HTTPException(detail="confirm password and given password don't match", status_code=status.HTTP_400_BAD_REQUEST)
        else:
            current_user.password_hash = password_manager.hash(updates.password)
    elif updates.password or updates.conf_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    
    if updates.username:
        if current_user.username != updates.username and db.query(User).filter(User.username == updates.username).first():
            raise HTTPException(detail="username already in use", status_code=status.HTTP_409_CONFLICT)
        else:
            current_user.username = updates.username
        
    if updates.email:
        if current_user.email != updates.email and db.query(User).filter(User.email == updates.email).first():
            raise HTTPException(detail="email already in use", status_code=status.HTTP_409_CONFLICT)
        else:
            current_user.email = updates.email

    db.commit()
    db.refresh(current_user)

    return current_user

@router.delete('/me', status_code=status.HTTP_204_NO_CONTENT)
def delete_current_user(current_user: User = Depends(oauth2.get_current_user), db: Session = Depends(get_db)):
    db.delete(current_user)
    db.commit()

@router.get('/{username}', status_code=status.HTTP_200_OK)
def get_user(username: str, db: Session = Depends(get_db), current_user: User | None = Depends(oauth2.get_optional_current_user)):
    if current_user and current_user.username == username:
        return UserResponse(
            username=current_user.username,
            email=current_user.email,
            created_at=current_user.created_at,
            is_verified=current_user.is_verified
        )

    user = db.query(User).filter(User.username == username, User.is_verified == True).first()
    if not user:
        raise HTTPException(detail="User with the given username was not found", status_code=status.HTTP_404_NOT_FOUND)
    
    return UserResponseUnknown(
        username=user.username,
        created_at=user.created_at
    )

@router.patch('/{username}/promote', status_code=status.HTTP_200_OK, response_model=UserResponse)
def promote_user(username: str, current_admin: User = Depends(oauth2.get_current_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(detail="User with the given username was not found", status_code=status.HTTP_404_NOT_FOUND)
    
    user.user_type = UserType.ADMIN
    db.commit()
    db.refresh(user)
    return user

@router.patch('/{username}/role', status_code=status.HTTP_200_OK, response_model=UserResponse)
def update_user_role(username: str, role_data: RoleUpdate, current_admin: User = Depends(oauth2.get_current_admin), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(detail="User with the given username was not found", status_code=status.HTTP_404_NOT_FOUND)
    
    user.user_type = role_data.user_type
    db.commit()
    db.refresh(user)
    return user