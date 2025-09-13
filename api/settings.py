from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Request
from sqlalchemy.orm import Session
import os
import shutil
from database.database import get_db, ChatbotSettings as ChatbotSettingsModel
from service.models import schemas

router = APIRouter()

@router.post("/settings/", response_model=schemas.ChatbotSettings)
def create_settings(settings: schemas.ChatbotSettingsCreate, db: Session = Depends(get_db)):
    db_settings = db.query(ChatbotSettingsModel).filter(ChatbotSettingsModel.customer_id == settings.customer_id).first()
    if db_settings:
        raise HTTPException(status_code=400, detail="Settings already exist for this customer")
    db_settings = ChatbotSettingsModel(**settings.dict())
    db.add(db_settings)
    db.commit()
    db.refresh(db_settings)
    return db_settings

@router.get("/settings/{customer_id}", response_model=schemas.ChatbotSettings)
def get_settings(customer_id: str, db: Session = Depends(get_db)):
    db_settings = db.query(ChatbotSettingsModel).filter(ChatbotSettingsModel.customer_id == customer_id).first()
    if db_settings is None:
        # Return default settings if not found, but do not save them to the DB
        return schemas.ChatbotSettings(
            customer_id=customer_id,
            chatbot_icon_url='',
            chatbot_message_default='',
            chatbot_callout=''
        )
    return db_settings

@router.put("/settings/{customer_id}", response_model=schemas.ChatbotSettings)
def update_settings(customer_id: str, settings: schemas.ChatbotSettingsUpdate, db: Session = Depends(get_db)):
    db_settings = db.query(ChatbotSettingsModel).filter(ChatbotSettingsModel.customer_id == customer_id).first()
    if db_settings is None:
        # If settings don't exist, create them
        new_settings_data = settings.dict()
        new_settings_data['customer_id'] = customer_id
        db_settings = ChatbotSettingsModel(**new_settings_data)
        db.add(db_settings)
    else:
        # If settings exist, update them
        update_data = settings.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_settings, key, value)
    
    db.commit()
    db.refresh(db_settings)
    return db_settings

@router.post("/settings/{customer_id}/upload-icon", response_model=schemas.ChatbotSettings)
async def upload_chatbot_icon(customer_id: str, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    # Ensure the images directory exists
    upload_dir = os.path.join("JS_Chatbot", "images")
    os.makedirs(upload_dir, exist_ok=True)

    # Determine the file extension
    file_extension = os.path.splitext(file.filename)[1]
    if not file_extension:
        file_extension = ".png" # Default extension if none is found

    # Create a new filename using the customer_id
    new_filename = f"{customer_id}{file_extension}"
    file_path = os.path.join(upload_dir, new_filename)

    # Save the uploaded file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()

    # Construct the full URL for the icon
    icon_url = f"{str(request.base_url).strip('/')}/static/images/{new_filename}"

    # Update the database
    db_settings = db.query(ChatbotSettingsModel).filter(ChatbotSettingsModel.customer_id == customer_id).first()
    if db_settings is None:
        # If settings don't exist, create them
        db_settings = ChatbotSettingsModel(
            customer_id=customer_id,
            chatbot_icon_url=icon_url
        )
        db.add(db_settings)
    else:
        # If settings exist, update the icon URL
        db_settings.chatbot_icon_url = icon_url

    db.commit()
    db.refresh(db_settings)
    return db_settings
