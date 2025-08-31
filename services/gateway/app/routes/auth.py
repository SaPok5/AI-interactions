from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
import jwt
import bcrypt
import redis
import json
from datetime import datetime, timedelta
from typing import Optional
import uuid

from ..config import settings

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()

# Redis client for user storage (in production, use a proper database)
redis_client = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)

class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class SigninRequest(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    created_at: str

class AuthResponse(BaseModel):
    user: UserResponse
    token: str

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_jwt_token(user_id: str) -> str:
    """Create a JWT token for the user"""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(days=7),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

def verify_jwt_token(token: str) -> Optional[str]:
    """Verify JWT token and return user_id"""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload.get("user_id")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user from JWT token"""
    user_id = verify_jwt_token(credentials.credentials)
    user_data = redis_client.get(f"user:{user_id}")
    
    if not user_data:
        raise HTTPException(status_code=401, detail="User not found")
    
    return json.loads(user_data)

@router.post("/signup", response_model=AuthResponse)
async def signup(request: SignupRequest):
    """Register a new user"""
    # Check if user already exists
    existing_user = redis_client.get(f"user_email:{request.email}")
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    user_id = str(uuid.uuid4())
    hashed_password = hash_password(request.password)
    
    user_data = {
        "id": user_id,
        "name": request.name,
        "email": request.email,
        "password": hashed_password,
        "created_at": datetime.utcnow().isoformat()
    }
    
    # Store user data
    redis_client.set(f"user:{user_id}", json.dumps(user_data))
    redis_client.set(f"user_email:{request.email}", user_id)
    
    # Create JWT token
    token = create_jwt_token(user_id)
    
    # Return response without password
    user_response = UserResponse(
        id=user_data["id"],
        name=user_data["name"],
        email=user_data["email"],
        created_at=user_data["created_at"]
    )
    
    return AuthResponse(user=user_response, token=token)

@router.post("/signin", response_model=AuthResponse)
async def signin(request: SigninRequest):
    """Sign in an existing user"""
    # Get user by email
    user_id = redis_client.get(f"user_email:{request.email}")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    user_data = redis_client.get(f"user:{user_id}")
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    user = json.loads(user_data)
    
    # Verify password
    if not verify_password(request.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Create JWT token
    token = create_jwt_token(user_id)
    
    # Return response without password
    user_response = UserResponse(
        id=user["id"],
        name=user["name"],
        email=user["email"],
        created_at=user["created_at"]
    )
    
    return AuthResponse(user=user_response, token=token)

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user profile"""
    return UserResponse(
        id=current_user["id"],
        name=current_user["name"],
        email=current_user["email"],
        created_at=current_user["created_at"]
    )

@router.post("/logout")
async def logout():
    """Logout user (client-side token removal)"""
    return {"message": "Logged out successfully"}
