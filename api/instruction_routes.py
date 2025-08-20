from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database.database import get_db, SystemInstruction
from service.models.schemas import InstructionsUpdate, Instruction
from typing import List

router = APIRouter()

@router.get("/instructions", response_model=List[Instruction])
def get_instructions(db: Session = Depends(get_db)):
    """
    Lấy tất cả các instruction chung của hệ thống từ database.
    """
    instructions = db.query(SystemInstruction).all()
    return instructions

@router.put("/instructions", response_model=List[Instruction])
def update_instructions(
    update_data: InstructionsUpdate,
    db: Session = Depends(get_db)
):
    """
    Cập nhật hoặc tạo mới (upsert) các instruction của hệ thống.
    """
    updated_instructions = []
    for item in update_data.instructions:
        instruction = db.query(SystemInstruction).filter(SystemInstruction.key == item.key).first()
        if instruction:
            instruction.value = item.value
        else:
            instruction = SystemInstruction(key=item.key, value=item.value)
            db.add(instruction)
        updated_instructions.append(instruction)
    
    db.commit()
    
    for instruction in updated_instructions:
        db.refresh(instruction)
        
    return updated_instructions
