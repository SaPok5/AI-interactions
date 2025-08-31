"""
Authentication Service - Complete Implementation
Handles user registration, login, JWT tokens, and RBAC
"""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
import structlog

from .config import settings
from .database import engine, get_db, create_tables
from .models import User, UserRole, Session
from .schemas import UserCreate, UserResponse, Token, UserLogin
from .auth import (
    authenticate_user, create_access_token, get_password_hash,
    verify_token, get_current_user, require_roles
)
from .crud import create_user, get_user_by_email, get_user_by_id

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("🔐 Starting Authentication Service")
    
    # Create database tables
    await create_tables()
    logger.info("✅ Database tables created")
    
    yield
    
    logger.info("🛑 Shutting down Authentication Service")

app = FastAPI(
    title="Authentication Service",
    description="Enterprise authentication with JWT and RBAC",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@app.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user"""
    # Check if user already exists
    existing_user = await get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    user = await create_user(db, user_data, hashed_password)
    
    logger.info("User registered", user_id=user.id, email=user.email)
    return user

@app.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Login and get access token"""
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": str(user.id)})
    
    logger.info("User logged in", user_id=user.id, email=user.email)
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user information"""
    return current_user

@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"]))
):
    """Get user by ID (admin only)"""
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/verify")
async def verify_token_endpoint(token: str = Depends(oauth2_scheme)):
    """Verify JWT token"""
    payload = verify_token(token)
    return {"valid": True, "user_id": payload["sub"]}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "auth"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
